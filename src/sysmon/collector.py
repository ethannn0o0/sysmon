"""Collect system information. Pure data, no printing -- easy to test."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import List

import psutil


@dataclass
class ProcInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float


@dataclass
class Snapshot:
    cpu_percent: float
    cpu_per_core: List[float]
    mem_percent: float
    mem_used: int
    mem_total: int
    disk_percent: float
    disk_used: int
    disk_total: int
    processes: List[ProcInfo]


def format_bytes(n: float) -> str:
    """Turn a byte count into a human-readable string, e.g. 1536 -> '1.5 KB'."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def top_processes(limit: int = 10, sort_by: str = "cpu", name_filter: str = "") -> List[ProcInfo]:
    """Return the top `limit` processes sorted by 'cpu' or 'memory'.

    If `name_filter` is given, only processes whose name contains it
    (case-insensitive) are considered, before the limit is applied.
    """
    needle = name_filter.lower()
    procs: List[ProcInfo] = []
    cores = psutil.cpu_count() or 1
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            if needle and needle not in (info["name"] or "").lower():
                continue
            if info["pid"] == 0:
                continue  # Windows "System Idle Process": it measures idle time, not usage
            procs.append(
                ProcInfo(
                    pid=info["pid"],
                    name=info["name"] or "?",
                    # psutil reports the sum over all cores; normalise to 0-100% of the machine
                    cpu_percent=(info["cpu_percent"] or 0.0) / cores,
                    memory_percent=info["memory_percent"] or 0.0,
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue  # process vanished or is off-limits; skip it
    key = (lambda x: x.memory_percent) if sort_by == "memory" else (lambda x: x.cpu_percent)
    procs.sort(key=key, reverse=True)
    return procs[:limit]


def system_disk_path() -> str:
    """The drive the OS lives on (the C: drive on Windows, / elsewhere), not whichever partition lists first."""
    if os.name == "nt":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


def take_snapshot(limit: int = 10, sort_by: str = "cpu", name_filter: str = "") -> Snapshot:
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(system_disk_path())
    return Snapshot(
        cpu_percent=sum(per_core) / len(per_core) if per_core else 0.0,
        cpu_per_core=per_core,
        mem_percent=mem.percent,
        mem_used=mem.used,
        mem_total=mem.total,
        disk_percent=disk.percent,
        disk_used=disk.used,
        disk_total=disk.total,
        processes=top_processes(limit, sort_by, name_filter),
    )


def snapshot_to_json(snap: Snapshot) -> str:
    """Serialise a Snapshot (plus a UTC timestamp) as pretty-printed JSON."""
    data = asdict(snap)
    data["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return json.dumps(data, indent=2, ensure_ascii=False)


def prime_cpu_counters() -> None:
    """psutil's cpu_percent needs one earlier call to give meaningful numbers."""
    psutil.cpu_percent(interval=None, percpu=True)
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


class KillError(Exception):
    """Raised when a process cannot (or should not) be killed."""


def kill_process(pid: int, force: bool = False, timeout: float = 3.0) -> str:
    """Terminate a process by PID and return its name.

    By default asks the process to exit (terminate); with force=True kills it
    outright. Raises KillError if it is still alive after `timeout` seconds.
    """
    if (os.name == "nt" and pid <= 4) or pid <= 1:
        raise KillError(f"PID {pid} is a core system process; refusing to touch it")
    if pid == os.getpid():
        raise KillError("refusing to kill sysmon itself")
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        if force:
            proc.kill()
        else:
            proc.terminate()
        try:
            proc.wait(timeout)
        except psutil.TimeoutExpired:
            raise KillError(f"{name} (PID {pid}) did not exit within {timeout:.0f}s; retry with --force")
    except psutil.NoSuchProcess:
        raise KillError(f"no process with PID {pid}") from None
    except psutil.AccessDenied:
        raise KillError(f"access denied for PID {pid} (try an administrator terminal)") from None
    return name


def process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except psutil.NoSuchProcess:
        raise KillError(f"no process with PID {pid}") from None
    except psutil.AccessDenied:
        return "?"
