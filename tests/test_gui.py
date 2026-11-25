import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no real display needed

from PySide6.QtCore import QPoint, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from sysmon.collector import ProcInfo, Snapshot  # noqa: E402
from sysmon.gui import FloatingMonitor  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "sysmon.ini"), QSettings.IniFormat)


@pytest.fixture(autouse=True)
def isolated_skins(tmp_path, monkeypatch):
    """Never read or write the real ~/.sysmon/skins during tests."""
    monkeypatch.setattr("sysmon.gui.default_skins_dir", lambda: tmp_path / "no-skins")


def fake_snapshot(name="chrome.exe"):
    return Snapshot(
        cpu_percent=42.0, cpu_per_core=[42.0], mem_percent=70.0, mem_used=7 * 1024**3,
        mem_total=10 * 1024**3, disk_percent=90.0, disk_used=9 * 1024**3, disk_total=10 * 1024**3,
        processes=[ProcInfo(pid=123, name=name, cpu_percent=12.5, memory_percent=3.0)],
    )


def test_apply_snapshot_updates_widgets(app, settings):
    win = FloatingMonitor(top=3, settings=settings)
    snap = fake_snapshot()
    snap.net_down, snap.net_up, snap.disk_read, snap.disk_write = 1024**2, 2048, 0, 5 * 1024**2
    win.apply_snapshot(snap)
    assert win.net_label.text() == "NET ↓ 1.0 MB/s  ↑ 2.0 KB/s"
    assert win.io_label.text() == "I/O R 0 B/s  W 5.0 MB/s"
    assert win.bars["CPU"][1].text() == "42%"
    assert win.bars["MEM"][0].toolTip() == "7.0 GB / 10.0 GB"
    assert win.proc_rows[0].value.text() == "12.5%"
    assert win.proc_rows[0].toolTip() == "chrome.exe (PID 123)"
    assert win.proc_rows[1].name.text() == ""  # fewer processes than rows


def test_long_process_names_are_elided_not_cut_mid_glyph(app, settings):
    win = FloatingMonitor(top=1, settings=settings)
    win.apply_snapshot(fake_snapshot("NVDisplay.Container.exe.with.a.very.long.name"))
    shown = win.proc_rows[0].name.text()
    assert shown.endswith("…") and len(shown) < 45
    assert "very.long.name" in win.proc_rows[0].toolTip() or "NVDisplay" in win.proc_rows[0].toolTip()


def test_background_sampler_delivers_snapshots(app, settings):
    win = FloatingMonitor(top=3, interval=0.2, settings=settings)
    win.start()
    try:
        for _ in range(80):  # up to ~8 s for the first snapshot to reach the UI
            QTest.qWait(100)
            if win.proc_rows[0].name.text().strip():
                break
        assert win.proc_rows[0].name.text().strip()
        assert win.bars["MEM"][1].text().endswith("%")
    finally:
        win.stop()


def test_compact_mode_shrinks_window_and_persists(app, settings):
    win = FloatingMonitor(top=5, settings=settings)
    win.show()
    full = win.height()
    win.set_compact(True)
    assert win.height() < full
    again = FloatingMonitor(top=5, settings=settings)
    assert again.compact is True


def test_preferences_are_remembered(app, settings):
    win = FloatingMonitor(top=2, settings=settings)
    win.set_sort("memory")
    win.set_opacity(0.7)
    again = FloatingMonitor(top=2, sort_by="cpu", settings=settings)
    assert again.sort_by == "memory"
    assert abs(again.windowOpacity() - 0.7) < 0.01


def test_saved_position_off_screen_falls_back(app, settings):
    settings.setValue("x", -99999)
    settings.setValue("y", -99999)
    win = FloatingMonitor(top=2, settings=settings)
    win.place()
    area = win.screen().availableGeometry()
    assert area.contains(win.pos())


def test_drag_is_clamped_to_screen(app, settings):
    win = FloatingMonitor(top=2, settings=settings)
    win.show()
    win.move(100, 100)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
    win.mouseMoveEvent(_FakeMove(win, QPoint(-5000, -5000)))
    area = win.screen().availableGeometry()
    assert win.x() >= area.left() and win.y() >= area.top()
    win.mouseMoveEvent(_FakeMove(win, QPoint(99999, 99999)))
    assert win.x() + win.width() <= area.right() + 1
    assert win.y() + win.height() <= area.bottom() + 1


class _FakeMove:
    """Minimal stand-in for a QMouseEvent: left button held, cursor at `pos`."""

    def __init__(self, win, pos):
        self._pos = pos

    def buttons(self):
        return Qt.LeftButton

    def globalPosition(self):
        from PySide6.QtCore import QPointF

        return QPointF(self._pos)


def test_skin_choice_is_applied_and_remembered(app, settings):
    win = FloatingMonitor(top=2, settings=settings)
    assert win.mascot.isHidden()  # the default skin has no mascot
    from sysmon.skins import BUILTIN_SKINS

    kitty = next(sk for sk in BUILTIN_SKINS if sk.name == "Kitty")
    win.apply_skin(kitty, save=True)
    assert win.skin.name == "Kitty" and not win.mascot.isHidden()
    assert "#f5e0ee" in win.styleSheet()  # skin text colour reaches the labels
    assert FloatingMonitor(top=2, settings=settings).skin.name == "Kitty"


def test_mascot_mood_and_status_follow_load(app, settings):
    from sysmon.skins import BUILTIN_SKINS

    win = FloatingMonitor(top=2, settings=settings)
    win.apply_skin(next(sk for sk in BUILTIN_SKINS if sk.name == "Slime"))
    calm = fake_snapshot()
    calm.cpu_percent, calm.mem_percent = 5.0, 40.0
    win.apply_snapshot(calm)
    assert win.mascot.mood == "idle" and win.status.text() == "boing~"
    hot = fake_snapshot()
    hot.cpu_percent = 97.0
    win.apply_snapshot(hot)
    assert win.mascot.mood == "overload" and win.status.text() == "melting!!"


def test_every_builtin_mascot_paints_in_every_mood(app, settings):
    from sysmon.skins import BUILTIN_SKINS

    win = FloatingMonitor(top=1, settings=settings)
    for skin in BUILTIN_SKINS:
        win.apply_skin(skin)
        for mood in ("idle", "busy", "overload"):
            win.mascot.set_mood(mood)
            win.mascot.advance()
            win.mascot.grab()  # raises or crashes if painting is broken


def test_user_skin_with_png_frames_loads(app, settings, tmp_path):
    import json

    from PySide6.QtGui import QColor, QPixmap

    folder = tmp_path / "skins" / "mine"
    folder.mkdir(parents=True)
    pm = QPixmap(16, 16)
    pm.fill(QColor("red"))
    assert pm.save(str(folder / "idle.png"))
    (folder / "skin.json").write_text(json.dumps({"name": "Mine", "mascot": {"frames": {"idle": "idle.png"}}}))
    win = FloatingMonitor(top=1, settings=settings, skins_dir=tmp_path / "skins")
    from sysmon.skins import find_skin, load_skins

    win.apply_skin(find_skin(load_skins(tmp_path / "skins"), "Mine"))
    assert set(win.mascot.pixmaps) == {"idle", "busy", "overload"}  # missing moods reuse the idle image
    assert not win.mascot.isHidden()
    win.mascot.set_mood("overload")  # no overload frame: falls back to idle, must not crash
    win.mascot.grab()


def test_right_click_menu_has_expected_entries(app, settings):
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QContextMenuEvent

    win = FloatingMonitor(top=2, settings=settings)
    win.show()
    seen = {}

    def inspect_and_close():
        from PySide6.QtWidgets import QApplication

        menu = QApplication.activePopupWidget()
        seen["top"] = [a.text() for a in menu.actions() if a.text()]
        skins = next(a.menu() for a in menu.actions() if a.text() == "Skin")
        seen["skins"] = [a.text() for a in skins.actions() if a.text()]
        menu.close()

    QTimer.singleShot(200, inspect_and_close)
    win.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(5, 5), win.mapToGlobal(QPoint(5, 5))))
    assert {"Skin", "Sort by CPU", "Sort by memory", "Compact mode", "Always on top", "Opacity", "Quit"} <= set(seen["top"])
    assert {"Midnight", "Slime", "Kitty", "Sunny Bunny"} <= set(seen["skins"])
    assert "Open skins folder…" in seen["skins"]


def _sleeper():
    import subprocess
    import sys

    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def test_end_process_declined_keeps_it_alive(app, settings, monkeypatch):
    win = FloatingMonitor(top=1, settings=settings)
    monkeypatch.setattr(win, "confirm_kill", lambda name, pid: False)
    child = _sleeper()
    try:
        assert win.end_process(child.pid, "python.exe") is False
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()


def test_end_process_confirmed_kills_it(app, settings, monkeypatch):
    win = FloatingMonitor(top=1, settings=settings)
    monkeypatch.setattr(win, "confirm_kill", lambda name, pid: True)
    child = _sleeper()
    try:
        assert win.end_process(child.pid, "python.exe") is True
        assert child.wait(timeout=5) is not None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_end_process_reports_protected_pid(app, settings, monkeypatch):
    win = FloatingMonitor(top=1, settings=settings)
    errors = []
    monkeypatch.setattr(win, "confirm_kill", lambda name, pid: True)
    monkeypatch.setattr(win, "show_error", errors.append)
    assert win.end_process(os.getpid(), "me") is False  # refusing to kill itself
    assert errors and "itself" in errors[0]


def test_right_click_on_process_row_offers_end_process(app, settings):
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QContextMenuEvent

    win = FloatingMonitor(top=2, settings=settings)
    win.show()
    win.apply_snapshot(fake_snapshot())
    app.processEvents()
    row = win.proc_rows[0]
    pos = row.mapTo(win, row.rect().center())
    seen = {}

    def inspect_and_close():
        from PySide6.QtWidgets import QApplication

        menu = QApplication.activePopupWidget()
        seen["first"] = [a.text() for a in menu.actions() if a.text()][0]
        menu.close()

    QTimer.singleShot(200, inspect_and_close)
    win.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, pos, win.mapToGlobal(pos)))
    assert seen["first"].startswith("End process: chrome.exe (PID 123)")
