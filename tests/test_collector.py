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
    assert {"net_up", "net_down", "disk_read", "disk_write"} <= data.keys()
    assert len(data["processes"]) <= 2
    assert {"pid", "name", "cpu_percent", "memory_percent"} <= data["processes"][0].keys()


def test_name_filter_matches_case_insensitively():
    import psutil

    me = psutil.Process().name()
    procs = top_processes(limit=1000, name_filter=me.upper()[:4])
    assert procs and all(me.lower()[:4] in p.name.lower() for p in procs)
    assert top_processes(limit=10, name_filter="no-such-process-xyz") == []


def test_system_disk_path_is_the_os_drive(monkeypatch):
    import os

    from sysmon import collector

    if os.name == "nt":
        monkeypatch.setenv("SystemDrive", "D:")
        assert collector.system_disk_path() == "D:\\"
    else:
        assert collector.system_disk_path() == "/"
    monkeypatch.undo()
    assert take_snapshot(limit=1).disk_total > 0


def test_format_rate():
    from sysmon.collector import format_rate

    assert format_rate(0) == "0 B/s"
    assert format_rate(1536) == "1.5 KB/s"
    assert format_rate(3 * 1024**2) == "3.0 MB/s"


def _tracker_with(readings):
    from sysmon.collector import RateTracker

    tracker = RateTracker()
    it = iter(readings)
    tracker._read = lambda: next(it)  # instance attribute shadows the real counter reader
    return tracker


def test_rate_tracker_computes_bytes_per_second():
    # readings are (time, net sent, net recv, disk read, disk write)
    t = _tracker_with([(0.0, 0, 0, 0, 0), (2.0, 2000, 6000, 400, 800)])
    first = t.sample()
    assert (first.net_up, first.net_down) == (0.0, 0.0)  # nothing to compare against yet
    r = t.sample()
    assert (r.net_up, r.net_down, r.disk_read, r.disk_write) == (1000.0, 3000.0, 200.0, 400.0)


def test_rate_tracker_counter_reset_is_zero_not_negative():
    t = _tracker_with([(0.0, 5000, 5000, 5000, 5000), (1.0, 100, 100, 100, 100)])
    t.sample()
    r = t.sample()
    assert r.net_up == r.net_down == r.disk_read == r.disk_write == 0.0


def test_rate_tracker_ignores_calls_that_are_too_close():
    t = _tracker_with([(0.0, 0, 0, 0, 0), (1.0, 1000, 0, 0, 0), (1.05, 999999, 0, 0, 0), (2.0, 3000, 0, 0, 0)])
    t.sample()
    assert t.sample().net_up == 1000.0
    assert t.sample().net_up == 1000.0  # only 0.05 s later: reuse the previous rate, do not spike
    assert t.sample().net_up == 2000.0  # measured against the 1.0 s reading, not the skipped one
