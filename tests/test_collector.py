from sysmon.collector import format_bytes, take_snapshot, top_processes


def test_format_bytes():
    assert format_bytes(0) == "0 B"
    assert format_bytes(1536) == "1.5 KB"
    assert format_bytes(5 * 1024**3) == "5.0 GB"


def test_top_processes_limit_and_sorting():
    procs = top_processes(limit=5, sort_by="memory")
    assert 0 < len(procs) <= 5
    mems = [p.memory_percent for p in procs]
    assert mems == sorted(mems, reverse=True)


def test_snapshot_ranges():
    snap = take_snapshot(limit=3)
    assert 0 <= snap.mem_percent <= 100
    assert 0 <= snap.disk_percent <= 100
    assert snap.mem_total > 0
    assert len(snap.processes) <= 3


def test_kill_process_roundtrip():
    import subprocess
    import sys

    import pytest

    from sysmon.collector import KillError, kill_process

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        kill_process(child.pid, force=True)
        assert child.wait(timeout=5) is not None
    finally:
        if child.poll() is None:
            child.kill()

    with pytest.raises(KillError):
        kill_process(child.pid)  # already gone


def test_kill_refuses_self_and_system():
    import os

    import pytest

    from sysmon.collector import KillError, kill_process

    with pytest.raises(KillError):
        kill_process(os.getpid())
    with pytest.raises(KillError):
        kill_process(0)


def test_snapshot_to_json_roundtrip():
    import json

    from sysmon.collector import snapshot_to_json

    data = json.loads(snapshot_to_json(take_snapshot(limit=2)))
    assert {"cpu_percent", "mem_total", "disk_total", "processes", "timestamp"} <= data.keys()
    assert len(data["processes"]) <= 2
    assert {"pid", "name", "cpu_percent", "memory_percent"} <= data["processes"][0].keys()


def test_name_filter_matches_case_insensitively():
    import psutil

    me = psutil.Process().name()
    procs = top_processes(limit=1000, name_filter=me.upper()[:4])
    assert procs and all(me.lower()[:4] in p.name.lower() for p in procs)
    assert top_processes(limit=10, name_filter="no-such-process-xyz") == []
