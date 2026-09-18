"""Limit this process tree, without changing machine-wide settings."""
import ctypes
import multiprocessing as mp
import os


def limit_threads() -> None:
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[name] = "1"


def _windows_affinity(mask: int | None = None) -> int:
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
    kernel.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    handle = kernel.GetCurrentProcess()
    current, system = ctypes.c_size_t(), ctypes.c_size_t()
    if not kernel.GetProcessAffinityMask(handle, ctypes.byref(current), ctypes.byref(system)):
        raise ctypes.WinError(ctypes.get_last_error())
    if mask is not None and not kernel.SetProcessAffinityMask(handle, mask):
        raise ctypes.WinError(ctypes.get_last_error())
    return current.value


def configure_process_tree(workers: int) -> list[int]:
    limit_threads()
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    if os.name == "nt":
        current = _windows_affinity()
        cpus = [i for i in range(64) if current & (1 << i)][:workers]
        _windows_affinity(1 << cpus[0])
    elif hasattr(os, "sched_getaffinity"):
        cpus = sorted(os.sched_getaffinity(0))[:workers]
        os.sched_setaffinity(0, {cpus[0]})
    else:
        cpus = list(range(min(workers, os.cpu_count() or 1)))
    return cpus


def worker_initializer(cpus: list[int] | None) -> None:
    limit_threads()
    if not cpus:
        return
    identity = mp.current_process()._identity
    cpu = cpus[((identity[-1] if identity else 1)-1) % len(cpus)]
    if os.name == "nt":
        _windows_affinity(1 << cpu)
    elif hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {cpu})
