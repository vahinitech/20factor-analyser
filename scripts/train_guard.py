# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Where a training run computes, and how it keeps out of other work's way.

Device: a CUDA GPU, else Apple's GPU (MPS, a Mac Studio), else the CPU.
A run asked for one that is missing falls back down that list and says
so; it never fails for want of a GPU.

On the CPU a run shares the machine (the vahinitech.com server runs
production next to it), so it restricts itself:

- threads: half the cores by default, never all of them;
- priority: niced, so production is served first;
- memory: before each batch it reads the memory the machine still has
  free and its own size. Below the floor it saves a checkpoint and
  waits; still below after max_pauses waits, it saves and exits with
  EXIT_RESUME, and --resume continues from the checkpoint. Above its own
  ceiling it saves and exits at once: a run that grows that large is
  the run to stop, not production.
- load: a machine busier than its cores (one-minute load average) is
  treated like low memory, so the run waits.

On a GPU the same limits apply to the host memory; the thread and nice
limits do not. Every number is a command-line flag.
"""

import os
import sys
import time

EXIT_RESUME = 75  # EX_TEMPFAIL: run again with --resume

OK, PAUSE, STOP = "ok", "pause", "stop"


def pick_device(want, torch_mod):
    """("cuda" | "mps" | "cpu", note). want: "auto", "cuda", "mps" or
    "cpu". A device asked for and missing falls back, with a note."""
    have_cuda = bool(torch_mod.cuda.is_available())
    mps = getattr(getattr(torch_mod, "backends", None), "mps", None)
    have_mps = bool(mps is not None and mps.is_available())
    order = {
        "auto": ["cuda", "mps", "cpu"],
        "cuda": ["cuda", "mps", "cpu"],
        "mps": ["mps", "cuda", "cpu"],
        "cpu": ["cpu"],
    }[want]
    have = {"cuda": have_cuda, "mps": have_mps, "cpu": True}
    for dev in order:
        if have[dev]:
            note = (
                ""
                if dev == order[0] or want == "auto"
                else (f"{want} is not available here; using {dev}")
            )
            return dev, note
    return "cpu", ""


def cpu_threads(requested, cores):
    """Threads for a CPU run: the request, else half the cores, and
    always at least one core left free."""
    cores = max(1, int(cores or 1))
    n = int(requested) if requested else max(1, cores // 2)
    return max(1, min(n, cores - 1 if cores > 1 else 1))


def decide(avail_mb, rss_mb, load1, cores, limits):
    """OK, PAUSE or STOP for one check. limits: floor_mb (memory the
    machine must keep free), max_rss_mb (this run's ceiling) and
    max_load (load average per core; None: no load check)."""
    if limits.get("max_rss_mb") and rss_mb > limits["max_rss_mb"]:
        return STOP
    if avail_mb < limits.get("floor_mb", 0):
        return PAUSE
    max_load = limits.get("max_load")
    if max_load is not None and load1 is not None:
        if load1 > max_load * max(1, cores):
            return PAUSE
    return OK


def memory_mb():
    """(available on the machine, this process's resident size), in MB."""
    try:
        import psutil  # pylint: disable=import-outside-toplevel

        vm = psutil.virtual_memory()
        rss = psutil.Process(os.getpid()).memory_info().rss
        return vm.available / 2**20, rss / 2**20
    except ImportError:
        pass
    avail = None
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) / 1024.0
    except OSError:
        avail = None
    rss = 0.0
    try:
        with open("/proc/self/statm", encoding="ascii") as f:
            rss = int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
            rss /= 2**20
    except (OSError, ValueError):
        pass
    return (avail if avail is not None else float("inf")), rss


def load_average():
    try:
        return os.getloadavg()[0]
    except (AttributeError, OSError):
        return None


class Guard:
    """Checks memory and load between batches. save() is called before
    any wait or exit, so no work is lost."""

    def __init__(self, limits, save, log=print, sleep=time.sleep):
        self.limits = dict(limits)
        self.save = save
        self.log = log
        self.sleep = sleep
        self.cores = os.cpu_count() or 1

    def check(self, probe=None):
        """Return when it is safe to go on; exit the process otherwise."""
        probe = probe or (lambda: (*memory_mb(), load_average()))
        pauses = 0
        while True:
            avail, rss, load1 = probe()
            verdict = decide(avail, rss, load1, self.cores, self.limits)
            if verdict == OK:
                return
            self.save()
            if verdict == STOP:
                self.log(
                    f"guard: this run uses {rss:.0f} MB, over its "
                    f"{self.limits['max_rss_mb']} MB ceiling; checkpoint "
                    f"saved, stopping. Resume with --resume."
                )
                sys.exit(EXIT_RESUME)
            pauses += 1
            if pauses > self.limits.get("max_pauses", 10):
                self.log(
                    f"guard: the machine stayed short ({avail:.0f} MB free, "
                    f"load {load1}); checkpoint saved, stopping. Resume "
                    f"with --resume."
                )
                sys.exit(EXIT_RESUME)
            self.log(
                f"guard: {avail:.0f} MB free (floor "
                f"{self.limits.get('floor_mb')} MB), load {load1}; "
                f"waiting {self.limits.get('pause_s', 60)} s"
            )
            self.sleep(self.limits.get("pause_s", 60))


def restrict_cpu(torch_mod, threads):
    """Fewer threads and a lower priority for a run on a shared CPU."""
    torch_mod.set_num_threads(threads)
    try:
        torch_mod.set_num_interop_threads(1)
    except RuntimeError:
        pass  # already set once in this process
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass
