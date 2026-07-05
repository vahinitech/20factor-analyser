# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Auto-detect whether an OCR engine should run on GPU or CPU.

Each pluggable backend (paddle, trocr, surya) picks its device
through resolve_use_gpu() below: an explicit VAHINI_*_GPU=1/0 env var
always wins (existing deploys that set VAHINI_OCR_GPU=0 keep working
unchanged); left unset, the engine's own installed build is checked for
real CUDA capability and the GPU is used automatically when it's there.

The per-engine check matters: an NVIDIA GPU being physically present does
not mean an engine can use it. The default paddle install is
CPU-only (paddlepaddle, not paddlepaddle-gpu) and PyTorch's CPU wheel has
no CUDA runtime linked in, so blindly requesting device="gpu" on either
would error instead of falling back. Checking the installed build's own
capability flag (paddle.is_compiled_with_cuda(), torch.cuda.is_available())
avoids that failure mode entirely.
"""

import os
import subprocess


def _torch_cuda_available():
    """True if the installed torch build can actually reach a CUDA GPU.
    Covers trocr and surya, which both sit on torch."""
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _paddle_cuda_available():
    """True if the installed paddlepaddle build can actually reach a CUDA
    GPU. is_compiled_with_cuda() alone only says the wheel supports CUDA,
    not that a device exists, so both are checked."""
    try:
        import paddle

        if not paddle.is_compiled_with_cuda():
            return False
        return paddle.device.cuda.device_count() > 0
    except Exception:
        return False


def nvidia_gpu_present():
    """Hardware-only check, no ML library required: is there an NVIDIA GPU
    on this machine at all. Used for /health diagnostics (e.g. "there is a
    GPU here, but the installed paddle build is CPU-only") -- never used to
    pick a device by itself, since a driver alone doesn't mean an engine's
    installed build can use it."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            timeout=2,
            check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def gpu_count():
    """How many NVIDIA GPUs `nvidia-smi` reports on this machine. 0 if
    nvidia-smi is missing, errors, or there simply is no GPU -- never
    raises. Used for /health and benchmark_ocr.py diagnostics; not used to
    pick a device (see nvidia_gpu_present's docstring for why)."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            timeout=2,
            check=False,
        )
        if result.returncode != 0:
            return 0
        return len(
            [ln for ln in result.stdout.decode().splitlines() if ln.strip()]
        )
    except Exception:
        return 0


def gpu_capable(engine="torch"):
    """True if this machine's installed `engine` build can use a GPU
    right now. `engine` is "paddle", "torch", or "any" (either)."""
    if engine == "paddle":
        return _paddle_cuda_available()
    if engine == "torch":
        return _torch_cuda_available()
    return _torch_cuda_available() or _paddle_cuda_available()


def resolve_use_gpu(env_name, engine="torch"):
    """Decide GPU vs CPU for one engine.

    An explicit "1"/"0" in the named env var always wins. Left unset,
    auto-detect: use the GPU only if this machine's installed `engine`
    build can actually reach one, else fall back to CPU.
    """
    raw = os.environ.get(env_name)
    if raw is not None:
        return raw.strip() == "1"
    return gpu_capable(engine)
