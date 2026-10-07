# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""How many scans this host can run at once, from its memory, cores and GPUs.

Measured on the deploy box (stage, 2026-10-07: 4 cores, 7.9 GB shared host,
PP-OCRv5 mobile det + en rec on CPU, 960x1280 and 3024x4032 photos):

- process with models loaded and warm: ~1.0 GB (en), ~1.1 GB (en + te)
- each extra OCR engine copy: 70-210 MB (BASE already holds the first)
- working memory of one running scan: ~0.6 GB (kernel memory.peak 1.61 GB
  against ~1.0 GB idle)
- one scan's OCR: 2.74 s on 4 threads, 3.01 s on 2, 5.15 s on 1, so a scan
  gains almost nothing past 2 threads and two 2-thread scans side by side
  roughly double throughput on 4 cores, given the memory

So the plan is the smallest of three limits:

  by_cpu    = cores // THREADS_PER_SCAN       (CPU hosts)
  by_gpu    = gpus * SCANS_PER_GPU            (GPU hosts; not yet measured)
  by_memory = (limit * SAFETY - BASE + REPLICA) // (SCAN + REPLICA)

with one OCR engine copy per slot, each limited to cores // slots threads.
Every number is an environment override, and VAHINI_MAX_ACTIVE_SCANS, when
set, wins outright. The plan is logged at startup and reported by /health.
"""

import math
import os

import gpu_detect

HARD_MAX = 16
SAFETY = 0.9


def _env_num(name, default, minimum=0):
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def constants():
    return {
        "base_mb": _env_num("VAHINI_SCAN_BASE_MB", 1100, 1),
        "scan_mb": _env_num("VAHINI_SCAN_MEM_MB", 600, 1),
        "replica_mb": _env_num("VAHINI_SCAN_REPLICA_MB", 200),
        "threads_per_scan": int(_env_num("VAHINI_SCAN_THREADS", 2, 1)),
        "scans_per_gpu": int(_env_num("VAHINI_SCANS_PER_GPU", 2, 1)),
        "queue_per_slot": int(_env_num("VAHINI_SCAN_QUEUE_PER_SLOT", 4)),
    }


def _read(path):
    try:
        with open(path, encoding="ascii") as f:
            return f.read().strip()
    except OSError:
        return None


def memory_limit_mb(root="/sys/fs/cgroup", meminfo="/proc/meminfo"):
    """The container's memory limit (cgroup v2, then v1), else the memory
    the host has available now. Returns (mb, source)."""
    v2 = _read(os.path.join(root, "memory.max"))
    if v2 and v2 != "max" and v2.isdigit():
        return int(v2) // 2**20, "cgroup memory.max"
    v1 = _read(os.path.join(root, "memory", "memory.limit_in_bytes"))
    if v1 and v1.isdigit() and int(v1) < 2**60:
        return int(v1) // 2**20, "cgroup v1 limit"
    text = _read(meminfo) or ""
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024, "host MemAvailable"
    return 0, "unknown"


def usable_cores(root="/sys/fs/cgroup"):
    """CPUs this process may use: its affinity, capped by a cgroup quota."""
    try:
        cores = len(os.sched_getaffinity(0))
    except AttributeError:
        cores = os.cpu_count() or 1
    quota = (_read(os.path.join(root, "cpu.max")) or "").split()
    if len(quota) == 2 and quota[0].isdigit() and quota[1].isdigit():
        cores = min(cores, max(1, math.ceil(int(quota[0]) / int(quota[1]))))
    return max(1, cores)


def gpus_in_use():
    """GPUs the OCR engine will actually run on: none unless VAHINI_OCR_GPU
    asks for them, however many the machine has."""
    wanted = os.environ.get("VAHINI_OCR_GPU", "0").strip().lower()
    if wanted not in ("1", "true", "yes", "on"):
        return 0
    return gpu_detect.gpu_count()


def plan(memory_mb, cores, gpus, const=None):
    """Pure capacity arithmetic; see the module docstring."""
    c = const or constants()
    per_slot = c["scan_mb"] + c["replica_mb"]
    budget = memory_mb * SAFETY - c["base_mb"] + c["replica_mb"]
    by_memory = max(1, int(budget // per_slot)) if memory_mb else 1
    if gpus:
        by_compute, compute = gpus * c["scans_per_gpu"], "gpu"
    else:
        by_compute, compute = max(1, cores // c["threads_per_scan"]), "cpu"
    active = max(1, min(by_memory, by_compute, HARD_MAX))
    if active == by_memory and by_memory < by_compute:
        limit = "memory"
    elif active == HARD_MAX:
        limit = "hard cap"
    else:
        limit = compute
    return {
        "active": active,
        "queued": active * c["queue_per_slot"],
        "threads_per_engine": max(1, cores // active) if not gpus else None,
        "limited_by": limit,
        "by_memory": by_memory,
        "by_compute": by_compute,
        "memory_mb": memory_mb,
        "cores": cores,
        "gpus": gpus,
    }


def detect_plan():
    """The plan for this process, honouring explicit overrides."""
    memory_mb, source = memory_limit_mb()
    result = plan(memory_mb, usable_cores(), gpus_in_use())
    result["memory_source"] = source
    explicit_active = os.environ.get("VAHINI_MAX_ACTIVE_SCANS")
    explicit_queue = os.environ.get("VAHINI_MAX_QUEUED_SCANS")
    if explicit_active and explicit_active.strip().isdigit():
        result["active"] = max(1, int(explicit_active))
        result["limited_by"] = "VAHINI_MAX_ACTIVE_SCANS"
        if result["threads_per_engine"]:
            result["threads_per_engine"] = max(
                1, result["cores"] // result["active"]
            )
    if explicit_queue and explicit_queue.strip().isdigit():
        result["queued"] = int(explicit_queue)
    return result
