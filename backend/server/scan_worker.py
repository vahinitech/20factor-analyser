# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Scans run in a child process, so the server outlives a scan that dies.

On 23 October 2026 a school's first check on stage failed with "Recognition
server not reachable": the analyser was killed mid-scan, most likely by the
container's OOM killer, and because one process both answered HTTP and ran
PaddleOCR, every visitor got 502 until the container restarted and the
models loaded again. Design: #299, part 1.

With VAHINI_SCAN_WORKER=1 (set in the image) the server process, the front,
never loads a model. Scan work that scan_slots.run would run on a scan
thread is sent to one child process instead, which holds the models and
runs it on its own scan_0, scan_1, ... threads, one per slot, exactly as
the front would have. Admission (scan_slots.SLOTS) stays in the front, so
the slot and queue caps are unchanged.

- The child raises its own oom_score_adj to 1000 (a process may always
  raise its own), so when the container runs out of memory the kernel
  kills the child, not the front.
- The front notices the child's end on the pipe, fails the calls it was
  running with WorkerDied, and starts a new child. Queued scans wait for
  it; /health keeps answering.
- call() runs a lost scan once more, on the same path. Never a lighter
  one: a reduced reading would give the same photo a different report
  depending on whether the server died first (owner decision on #299;
  same photo, same score, #112). A second loss is ScanLost, which the
  server answers as ocr_unavailable.
- The child answers health requests on its main thread, between
  messages, so /health can report the models while a scan runs.

Stage timings recorded in the child come back with each answer and are
added to the request's record in the front (perf.adopt), so Server-Timing,
/health and the [perf] line read as before.
"""

import importlib.util
import itertools
import os
import pickle
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from multiprocessing.connection import Connection

from server import perf

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Seconds before the n-th restart in a row without the child getting ready:
# a child that dies while starting (a broken model file, say) is not
# restarted in a tight loop. A child that got ready restarts at once.
RESTART_DELAYS = (0, 1, 2, 5, 10, 30)
HEALTH_TIMEOUT_SEC = 2.0
OOM_SCORE_ADJ = "/proc/self/oom_score_adj"

# True in the child, which runs the scans itself.
IN_CHILD = False
SUPERVISOR = None


class WorkerDied(Exception):
    """The child ended while it held this call."""


class ScanLost(Exception):
    """The scan was lost twice: the child died running it, and again
    running it once more."""


def configure(module_name, path, threads):
    """Name the module the child loads (the server's app.py, by the name
    the front loaded it under, so the scan functions it is sent resolve)
    and its scan threads. Starts nothing."""
    global SUPERVISOR  # pylint: disable=global-statement
    if module_name == "__main__":
        # app.py run as a script: the child would load its own __main__,
        # not app.py, and every scan would be lost. Scan in this process.
        print("[scan-worker] off: app.py runs as __main__", flush=True)
        return None
    if SUPERVISOR is None:
        SUPERVISOR = Supervisor(module_name, path, threads)
    return SUPERVISOR


def enabled():
    """Whether scan work goes to the child."""
    return (
        not IN_CHILD
        and SUPERVISOR is not None
        and os.environ.get("VAHINI_SCAN_WORKER", "0").strip() == "1"
    )


def stats():
    """/health's scan_worker."""
    if not enabled():
        return {"enabled": False}
    return SUPERVISOR.stats()


class Supervisor:
    """Starts the child, passes it calls and answers, and restarts it."""

    def __init__(self, module_name, path, threads):
        self.module_name = module_name
        self.path = str(path)
        self.threads = max(1, int(threads))
        self._cond = threading.Condition()
        # Held while writing to the child, apart from _cond, so the watcher
        # can always take _cond to deliver an answer while a large call is
        # being written (with three slots, holding _cond here deadlocked).
        self._send_lock = threading.Lock()
        self._ids = itertools.count(1)
        self._pending = {}
        self._proc = None
        self._conn = None
        self._started = False
        self._stopping = False
        self._state = "starting"
        self._deaths_unready = 0
        self.restarts = 0
        self.last_exit = None

    # ---- the child's life -------------------------------------------------
    def start(self):
        if self.module_name not in sys.modules:
            # The calls name their functions by module (pickle); unknown
            # here, every scan would fail. Say so at start-up instead.
            raise RuntimeError(
                f"scan worker: module {self.module_name!r} is not in "
                "sys.modules; register it before loading it"
            )
        with self._cond:
            if self._started:
                return
            self._started = True
            self._spawn_locked()
        threading.Thread(
            target=self._watch, name="scan-worker-watch", daemon=True
        ).start()

    def _spawn_locked(self):
        # A plain new interpreter, not multiprocessing's spawn, which would
        # run the server's main script again in the child first.
        ours, theirs = socket.socketpair()
        path = os.pathsep.join(
            p for p in (BACKEND_DIR, os.environ.get("PYTHONPATH")) if p
        )
        try:
            proc = subprocess.Popen(  # pylint: disable=consider-using-with
                [
                    sys.executable,
                    "-c",
                    "from server.scan_worker import child_entry; "
                    "child_entry()",
                    str(theirs.fileno()),
                    self.module_name,
                    self.path,
                    str(self.threads),
                ],
                pass_fds=(theirs.fileno(),),
                env={**os.environ, "PYTHONPATH": path},
            )
        finally:
            theirs.close()
        self._proc, self._conn = proc, Connection(ours.detach())
        self._state = "starting"
        self._cond.notify_all()

    def _watch(self):
        while not self._stopping:
            conn = self._conn
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                if not self._stopping:
                    self._restart()
                continue
            except Exception as exc:  # pylint: disable=broad-except
                # An answer this process cannot unpickle. Its call is not
                # known, so end the child: its calls fail as WorkerDied
                # and run once more, instead of this thread dying and
                # every scan after it waiting for ever.
                print(
                    f"[scan-worker] unreadable answer ({exc!r}); "
                    "ending the worker",
                    flush=True,
                )
                self._proc.kill()
                continue
            self._deliver(msg)

    def _deliver(self, msg):
        if msg[0] == "ready":
            with self._cond:
                self._state = "ready"
                self._deaths_unready = 0
            return
        with self._cond:
            future = self._pending.pop(msg[1], None)
        if future is not None and not future.done():
            future.set_result(msg[2:])

    def _restart(self):
        with self._cond:
            proc, conn = self._proc, self._conn
            lost, self._pending = self._pending, {}
            was_ready = self._state == "ready"
            self._conn, self._state = None, "restarting"
        try:
            exitcode = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()  # its pipe broke but it lives on: end it
            exitcode = proc.wait()
        conn.close()
        with self._cond:
            self.restarts += 1
            self.last_exit = exitcode
        for future in lost.values():
            if not future.done():
                future.set_exception(
                    WorkerDied(f"scan worker ended (exit {exitcode})")
                )
        if not was_ready:
            self._deaths_unready += 1
        delay = RESTART_DELAYS[
            min(self._deaths_unready, len(RESTART_DELAYS) - 1)
        ]
        # exit -9 is SIGKILL: in a memory-limited container, the OOM killer.
        print(
            f"[scan-worker] ended with exit {exitcode} while running "
            f"{len(lost)} call(s); starting a new one in {delay} s",
            flush=True,
        )
        time.sleep(delay)
        with self._cond:
            self._spawn_locked()

    def stop(self):
        """End the child (tests; the front's exit ends it anyway)."""
        with self._cond:
            self._stopping = True
            proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    def stats(self):
        with self._cond:
            return {
                "enabled": True,
                "state": self._state,
                "restarts": self.restarts,
                "last_exit": self.last_exit,
            }

    # ---- calls --------------------------------------------------------------
    def _send(self, kind, *payload):
        self.start()
        future = Future()
        with self._cond:
            while self._conn is None:
                self._cond.wait()
            conn = self._conn
            call_id = next(self._ids)
            self._pending[call_id] = future
        try:
            with self._send_lock:
                conn.send((kind, call_id) + payload)
        except (OSError, ValueError) as exc:
            # The child is gone and the watcher has not seen it yet.
            with self._cond:
                self._pending.pop(call_id, None)
            raise WorkerDied(str(exc)) from exc
        except Exception:
            # The call itself would not pickle: not the child's fault.
            with self._cond:
                self._pending.pop(call_id, None)
            raise
        return call_id, future

    def _call_once(self, fn, args):
        _id, future = self._send("scan", fn, args)
        ok, value, rows = future.result()
        perf.adopt(rows)
        if ok:
            return value
        raise value

    def call(self, fn, *args):
        """Run fn(*args) in the child and return its result, raising what
        it raised. A call lost with the child runs once more, the same
        way; lost again, it raises ScanLost."""
        try:
            return self._call_once(fn, args)
        except WorkerDied as first:
            print(
                f"[scan-worker] scan lost ({first}); running it once more",
                flush=True,
            )
            try:
                return self._call_once(fn, args)
            except WorkerDied as second:
                raise ScanLost(str(second)) from second

    def health(self, timeout=HEALTH_TIMEOUT_SEC):
        """The child's model status (the server's _model_health), or None
        when it is not ready or does not answer in time."""
        with self._cond:
            if self._state != "ready":
                return None
        try:
            call_id, future = self._send("health")
        except WorkerDied:
            return None
        try:
            ok, value = future.result(timeout=timeout)
        except (FutureTimeout, WorkerDied):
            with self._cond:
                self._pending.pop(call_id, None)
            return None
        return value if ok else None


# ---- the child --------------------------------------------------------------
def _raise_oom_score():
    try:
        with open(OOM_SCORE_ADJ, "w", encoding="ascii") as f:
            f.write("1000")
    except OSError:
        pass  # not Linux, or no /proc: the restart still covers a death


def _load(module_name, path):
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _portable(exc):
    """exc, or a RuntimeError with its text when the front could not
    rebuild it: an exception unpickles by calling its class with its args,
    which fails for HTTPException(status_code=...) or RungDown(stage,
    reason)."""
    try:
        pickle.loads(pickle.dumps(exc))
        return exc
    except Exception:  # pylint: disable=broad-except
        return RuntimeError(f"{type(exc).__name__}: {exc}")


def _run(send, call_id, fn, args):
    with perf.scan() as record:
        try:
            value, ok = fn(*args), True
        except Exception as exc:  # pylint: disable=broad-except
            value, ok = _portable(exc), False
    rows = perf.export(record)
    try:
        send(("result", call_id, ok, value, rows))
    except Exception:  # pylint: disable=broad-except
        # The answer would not pickle; the front still gets an answer.
        send(
            (
                "result",
                call_id,
                False,
                RuntimeError(f"{type(value).__name__}: {value}"),
                rows,
            )
        )


def child_entry():
    """The child's command line: the socket's descriptor, then
    child_main's arguments."""
    fd, module_name, path, threads = sys.argv[1:5]
    child_main(Connection(int(fd)), module_name, path, int(threads))


def child_main(conn, module_name, path, threads):
    """The child: load the server module, warm its models, then run what
    the front sends until the front goes away."""
    global IN_CHILD  # pylint: disable=global-statement
    IN_CHILD = True
    _raise_oom_score()
    module = _load(module_name, path)
    warm = getattr(module, "_warm_models", None)
    if warm is not None:
        threading.Thread(
            target=warm, name="vahini-engine-warmup", daemon=True
        ).start()
    # Named scan_0, scan_1, ...: each slot's thread gets its own engine
    # copy (ocr_backends._replica_index), as in scan_slots.EXECUTOR.
    pool = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="scan")
    lock = threading.Lock()

    def send(msg):
        with lock:
            conn.send(msg)

    send(("ready",))
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            # The front is gone: end now, without running exit handlers.
            os._exit(0)  # pylint: disable=protected-access
        kind, call_id = msg[0], msg[1]
        if kind == "scan":
            pool.submit(_run, send, call_id, msg[2], msg[3])
        elif kind == "health":
            try:
                # pylint: disable-next=protected-access
                send(("health", call_id, True, module._model_health()))
            except Exception:  # pylint: disable=broad-except
                send(("health", call_id, False, None))
