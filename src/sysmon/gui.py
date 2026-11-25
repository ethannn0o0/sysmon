"""Floating always-on-top monitor window (PySide6) with skins and a cartoon mascot.

Left-drag to move, double-click to collapse/expand, right-click for the menu.
Position and preferences are remembered between runs.
Install the optional dependency first:  pip install -e ".[gui]"
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QPoint, QPointF, QRectF, QSettings, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (QActionGroup, QColor, QDesktopServices, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

from sysmon.collector import Snapshot, format_bytes, prime_cpu_counters, take_snapshot
from sysmon.skins import (MIDNIGHT, Skin, default_skins_dir, ensure_user_dir, find_skin, load_skins,
                          mood_for)

NAME_WIDTH = 165  # pixels available for a process name before it is elided
MASCOT_SIZE = 60
INK = QColor("#2a2a3a")  # eyes / mouth


class Sampler(QObject):
    """Collects snapshots on a background thread so the window never freezes."""

    ready = Signal(object)  # emitted with a Snapshot
    refresh = Signal()  # ask for an immediate sample (queued onto the worker thread)

    def __init__(self, top: int, sort_by: str, name_filter: str, interval_ms: int) -> None:
        super().__init__()
        # Plain attributes: written by the UI thread, read here. A stale value for
        # one tick is harmless.
        self.top, self.sort_by, self.name_filter = top, sort_by, name_filter
        self.interval_ms = interval_ms
        self._timer: Optional[QTimer] = None
        self.refresh.connect(self.sample)

    def start(self) -> None:  # runs in the worker thread (connected to thread.started)
        prime_cpu_counters()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.sample)
        self._timer.start(self.interval_ms)
        QTimer.singleShot(500, self.sample)  # let counters accumulate first

    def sample(self) -> None:
        self.ready.emit(take_snapshot(self.top, self.sort_by, self.name_filter))


class Bar(QWidget):
    """A thin rounded progress bar coloured by the current skin."""

    def __init__(self) -> None:
        super().__init__()
        self.percent = 0.0
        self.skin: Skin = MIDNIGHT
        self.setFixedHeight(8)
        self.setMinimumWidth(120)

    def set_percent(self, percent: float) -> None:
        self.percent = max(0.0, min(100.0, percent))
        self.update()

    def set_skin(self, skin: Skin) -> None:
        self.skin = skin
        self.update()

    def fill_color(self) -> QColor:
        s = self.skin
        return QColor(s.good if self.percent < 60 else s.warn if self.percent < 85 else s.bad)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        p.setBrush(QColor(self.skin.track))
        p.drawRoundedRect(r, 4, 4)
        p.setBrush(self.fill_color())
        p.drawRoundedRect(QRectF(0, 0, r.width() * self.percent / 100, r.height()), 4, 4)


class Mascot(QWidget):
    """A small cartoon character whose face follows the system load.

    Drawn with QPainter (no image files needed); a skin may instead supply PNG frames.
    """

    SPEED = {"idle": 0.10, "busy": 0.22, "overload": 0.55}  # animation phase per tick

    def __init__(self) -> None:
        super().__init__()
        self.skin: Skin = MIDNIGHT
        self.mood = "idle"
        self.tick = 0
        self.phase = 0.0
        self.pixmaps: dict[str, QPixmap] = {}
        self.setFixedSize(MASCOT_SIZE, MASCOT_SIZE)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(50)  # 20 fps is plenty for a tiny widget and costs almost nothing

    def set_skin(self, skin: Skin) -> None:
        self.skin = skin
        self.pixmaps = {}
        for mood in ("idle", "busy", "overload"):
            path = skin.frame_for(mood)
            if path is not None:
                pm = QPixmap(str(path))
                if not pm.isNull():
                    self.pixmaps[mood] = pm
        self.setVisible(skin.has_mascot)
        self.update()

    def set_mood(self, mood: str) -> None:
        if mood != self.mood:
            self.mood = mood
            self.update()

    def advance(self) -> None:
        if not self.isVisible():
            return
        self.tick += 1
        self.phase += self.SPEED[self.mood]
        self.update()

    # ---- drawing ----------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        if not self.skin.has_mascot:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bounce = math.sin(self.phase) * (1.5 if self.mood == "idle" else 2.5)
        jitter = math.sin(self.phase * 3) * 1.2 if self.mood == "overload" else 0.0
        p.translate(jitter, bounce)

        pm = self.pixmaps.get(self.mood) or self.pixmaps.get("idle")
        if pm is not None:
            scaled = pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
            return
        self._draw_builtin(p)

    def _draw_builtin(self, p: QPainter) -> None:
        body = QColor(self.skin.mascot_color)
        outline = QColor(INK)
        outline.setAlpha(120)
        p.setPen(QPen(outline, 1.5))
        p.setBrush(body)

        kind = self.skin.mascot_kind
        if kind == "cat":
            for sign in (-1, 1):  # triangular ears
                cx = 30 + sign * 14
                p.drawPolygon(QPolygonF([QPointF(cx - 7, 24), QPointF(cx + sign * 3, 8), QPointF(cx + 7, 24)]))
        elif kind == "bunny":
            tilt = math.sin(self.phase) * 2 if self.mood != "idle" else 0
            for sign in (-1, 1):  # long ears
                p.drawEllipse(QRectF(30 + sign * 9 - 5 + tilt * sign, 3, 10, 24))
        p.drawEllipse(QRectF(8, 20, 44, 36))  # body

        blink = self.mood == "idle" and (self.tick % 70) < 3
        ex = (21, 39)
        ey = 36
        p.setBrush(INK)
        if self.mood == "overload":
            for x in ex:  # wide eyes with small jittering pupils
                p.setBrush(Qt.white)
                p.drawEllipse(QPointF(x, ey), 5.5, 5.5)
                p.setBrush(INK)
                p.drawEllipse(QPointF(x + math.sin(self.phase * 2), ey), 2, 2)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath(QPointF(23, 48))  # wavy mouth
            for i in range(4):
                path.lineTo(23 + (i + 1) * 3.5, 48 + (2.5 if i % 2 == 0 else -0.5))
            p.setPen(QPen(INK, 1.8))
            p.drawPath(path)
            drop = (self.tick % 14) / 14  # sweat drop sliding down
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#8ecbff"))
            p.drawEllipse(QPointF(50, 24 + drop * 12), 2.6, 3.4)
        else:
            for x in ex:
                if blink:
                    p.setPen(QPen(INK, 1.8))
                    p.drawLine(QPointF(x - 3, ey), QPointF(x + 3, ey))
                    p.setPen(Qt.NoPen)
                else:
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(QPointF(x, ey), 2.6, 3.0)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(INK, 1.8))
            if self.mood == "idle":  # happy smile + blush
                p.drawArc(QRectF(25, 40, 10, 8), 200 * 16, 140 * 16)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 150, 170, 110))
                for x in (14, 46):
                    p.drawEllipse(QPointF(x, 45), 4, 2.6)
            else:  # busy: focused flat mouth and a small sweat drop
                p.drawLine(QPointF(26, 46), QPointF(34, 46))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#8ecbff"))
                p.drawEllipse(QPointF(48, 26), 2.2, 3.0)


class ProcRow(QWidget):
    def __init__(self, font: QFont) -> None:
        super().__init__()
        self._metrics = QFontMetrics(font)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.name = QLabel("")
        self.value = QLabel("")
        for label in (self.name, self.value):
            label.setFont(font)
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value.setFixedWidth(50)
        row.addWidget(self.name, 1)
        row.addWidget(self.value)

    def set(self, name: str, value: str, tooltip: str = "") -> None:
        self.name.setText(self._metrics.elidedText(name, Qt.ElideRight, NAME_WIDTH))
        self.value.setText(value)
        self.setToolTip(tooltip)


class FloatingMonitor(QWidget):
    def __init__(self, top: int = 5, sort_by: str = "cpu", interval: float = 1.0,
                 name_filter: str = "", settings: Optional[QSettings] = None,
                 skins_dir: Optional[Path] = None) -> None:
        super().__init__()
        self.top = top
        self.name_filter = name_filter
        self.settings = settings or QSettings("sysmon", "sysmon")
        self.skins_dir = skins_dir if skins_dir is not None else default_skins_dir()
        self.sort_by = self.settings.value("sort_by", sort_by, type=str)
        self.compact = self.settings.value("compact", False, type=bool)
        self._drag_offset = QPoint()
        self._thread: Optional[QThread] = None

        self.setWindowTitle("sysmon")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.set_always_on_top(self.settings.value("topmost", True, type=bool), show=False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(270)
        self.setWindowOpacity(self.settings.value("opacity", 1.0, type=float))
        self.setToolTip("Drag to move · double-click to collapse · right-click for menu")

        mono = QFont("Consolas", 9)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self.mascot = Mascot()
        header.addWidget(self.mascot)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel("sysmon")
        self.title.setObjectName("dim")
        self.status = QLabel("")
        self.status.setFont(QFont("Segoe UI", 10))
        titles.addStretch(1)
        titles.addWidget(self.title)
        titles.addWidget(self.status)
        titles.addStretch(1)
        header.addLayout(titles, 1)
        layout.addLayout(header)

        self.bars: dict[str, tuple[Bar, QLabel]] = {}
        for key in ("CPU", "MEM", "DISK"):
            row = QHBoxLayout()
            name = QLabel(key)
            name.setFont(mono)
            name.setFixedWidth(34)
            bar = Bar()
            value = QLabel("0%")
            value.setFont(mono)
            value.setFixedWidth(40)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(value)
            layout.addLayout(row)
            self.bars[key] = (bar, value)

        self.proc_rows: list[ProcRow] = []
        self.proc_box = QWidget()
        box = QVBoxLayout(self.proc_box)
        box.setContentsMargins(0, 6, 0, 0)
        box.setSpacing(2)
        for _ in range(self.top):
            row = ProcRow(mono)
            box.addWidget(row)
            self.proc_rows.append(row)
        layout.addWidget(self.proc_box)
        self.proc_box.setVisible(not self.compact)

        self.skin: Skin = MIDNIGHT
        self.apply_skin(find_skin(load_skins(self.skins_dir), self.settings.value("skin", MIDNIGHT.name, type=str)))
        self.mood = "idle"
        self._refresh_status()

        self.sampler = Sampler(self.top, self.sort_by, self.name_filter, max(200, int(interval * 1000)))
        self.sampler.ready.connect(self.apply_snapshot)

    # ---- skins ------------------------------------------------------------------
    def apply_skin(self, skin: Skin, save: bool = False) -> None:
        self.skin = skin
        self.setStyleSheet(
            f"QLabel {{ color: {skin.text}; }} QLabel#dim {{ color: {skin.dim}; font-weight: bold; }}"
        )
        for bar, _ in self.bars.values():
            bar.set_skin(skin)
        self.mascot.set_skin(skin)
        self.title.setVisible(True)
        self.adjustSize()
        self.update()
        if save:
            self.save_settings()

    def _refresh_status(self) -> None:
        self.status.setText(self.skin.lines.get(getattr(self, "mood", "idle"), ""))
        self.status.setVisible(self.skin.has_mascot)

    # ---- painting & placement ----------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        bg = QColor(self.skin.bg)
        bg.setAlphaF(self.skin.bg_alpha)
        p.setBrush(bg)
        r = self.skin.radius
        p.drawRoundedRect(QRectF(self.rect()), r, r)

    def place(self) -> None:
        """Restore the saved position if it is still on a screen, else bottom-right."""
        self.adjustSize()
        if self.settings.contains("x") and self.settings.contains("y"):
            pos = QPoint(self.settings.value("x", type=int), self.settings.value("y", type=int))
            if any(s.availableGeometry().contains(pos) for s in QApplication.screens()):
                self.move(pos)
                return
        screen = self.screen().availableGeometry()
        self.move(screen.right() - self.width() - 20, screen.bottom() - self.height() - 20)

    def save_settings(self) -> None:
        s = self.settings
        s.setValue("x", self.x())
        s.setValue("y", self.y())
        s.setValue("sort_by", self.sort_by)
        s.setValue("compact", self.compact)
        s.setValue("topmost", bool(self.windowFlags() & Qt.WindowStaysOnTopHint))
        s.setValue("opacity", self.windowOpacity())
        s.setValue("skin", self.skin.name)
        s.sync()

    # ---- interaction -----------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if not e.buttons() & Qt.LeftButton:
            return
        target = e.globalPosition().toPoint() - self._drag_offset
        area = self.screen().availableGeometry()  # keep the window fully on screen
        target.setX(max(area.left(), min(target.x(), area.right() - self.width() + 1)))
        target.setY(max(area.top(), min(target.y(), area.bottom() - self.height() + 1)))
        self.move(target)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.save_settings()

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.set_compact(not self.compact)

    def set_compact(self, compact: bool) -> None:
        self.compact = compact
        self.proc_box.setVisible(not compact)
        self.adjustSize()
        self.save_settings()

    def set_sort(self, key: str) -> None:
        self.sort_by = self.sampler.sort_by = key
        self.sampler.refresh.emit()  # re-sample now instead of waiting for the next tick
        self.save_settings()

    def set_always_on_top(self, on: bool, show: bool = True) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        if show:
            self.show()  # changing window flags hides the window; show it again
            self.save_settings()

    def set_opacity(self, value: float) -> None:
        self.setWindowOpacity(value)
        self.save_settings()

    def open_skins_folder(self) -> None:
        folder = ensure_user_dir(self.skins_dir)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        skins_menu = menu.addMenu("Skin")
        skin_group = QActionGroup(skins_menu)
        for skin in load_skins(self.skins_dir):  # re-scanned each time, so new skins show up at once
            act = skins_menu.addAction(skin.name)
            act.setCheckable(True)
            act.setChecked(skin.name == self.skin.name)
            act.triggered.connect(lambda _=False, s=skin: self.apply_skin(s, save=True))
            skin_group.addAction(act)
        skins_menu.addSeparator()
        skins_menu.addAction("Open skins folder…").triggered.connect(self.open_skins_folder)
        menu.addSeparator()
        group = QActionGroup(menu)
        for label, key in (("Sort by CPU", "cpu"), ("Sort by memory", "memory")):
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.sort_by == key)
            act.triggered.connect(lambda _=False, k=key: self.set_sort(k))
            group.addAction(act)
        menu.addSeparator()
        collapse = menu.addAction("Compact mode")
        collapse.setCheckable(True)
        collapse.setChecked(self.compact)
        collapse.triggered.connect(self.set_compact)
        top = menu.addAction("Always on top")
        top.setCheckable(True)
        top.setChecked(bool(self.windowFlags() & Qt.WindowStaysOnTopHint))
        top.triggered.connect(self.set_always_on_top)
        opacity = menu.addMenu("Opacity")
        for pct in (100, 90, 70, 50):
            opacity.addAction(f"{pct}%").triggered.connect(lambda _=False, v=pct: self.set_opacity(v / 100))
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(QApplication.quit)
        menu.exec(e.globalPos())

    # ---- data ------------------------------------------------------------------
    def apply_snapshot(self, snap: Snapshot) -> None:
        for key, pct in (("CPU", snap.cpu_percent), ("MEM", snap.mem_percent), ("DISK", snap.disk_percent)):
            bar, value = self.bars[key]
            bar.set_percent(pct)
            value.setText(f"{pct:.0f}%")
        self.bars["MEM"][0].setToolTip(f"{format_bytes(snap.mem_used)} / {format_bytes(snap.mem_total)}")
        self.bars["DISK"][0].setToolTip(f"{format_bytes(snap.disk_used)} / {format_bytes(snap.disk_total)}")
        for i, row in enumerate(self.proc_rows):
            if i < len(snap.processes):
                p = snap.processes[i]
                val = p.memory_percent if self.sort_by == "memory" else p.cpu_percent
                row.set(p.name, f"{val:.1f}%", f"{p.name} (PID {p.pid})")
            else:
                row.set("(no matching processes)" if i == 0 else "", "")
        self.mood = mood_for(snap.cpu_percent, snap.mem_percent)
        self.mascot.set_mood(self.mood)
        self._refresh_status()

    def start(self) -> None:
        self._thread = QThread(self)
        self.sampler.moveToThread(self._thread)
        self._thread.started.connect(self.sampler.start)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None

    def closeEvent(self, e) -> None:
        self.save_settings()
        self.stop()
        super().closeEvent(e)


def main(top: int = 5, sort_by: str = "cpu", interval: float = 1.0, name_filter: str = "") -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    win = FloatingMonitor(top, sort_by, interval, name_filter)
    win.place()
    win.show()
    win.start()
    app.aboutToQuit.connect(win.close)
    return app.exec()
