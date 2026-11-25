"""Turn a Snapshot into rich renderables."""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from sysmon.collector import Snapshot, format_bytes, format_rate


def _bar(percent: float, width: int = 30) -> Text:
    filled = int(width * percent / 100)
    color = "green" if percent < 60 else "yellow" if percent < 85 else "red"
    bar = Text("█" * filled, style=color)
    bar.append("░" * (width - filled), style="dim")
    bar.append(f" {percent:5.1f}%")
    return bar


def render(snap: Snapshot, sort_by: str = "cpu", name_filter: str = ""):
    usage = Table.grid(padding=(0, 2))
    usage.add_column(justify="right", style="bold")
    usage.add_column()
    usage.add_row("CPU", _bar(snap.cpu_percent))
    usage.add_row(
        "MEM",
        _bar(snap.mem_percent) + Text(f"  {format_bytes(snap.mem_used)} / {format_bytes(snap.mem_total)}"),
    )
    usage.add_row(
        "DISK",
        _bar(snap.disk_percent) + Text(f"  {format_bytes(snap.disk_used)} / {format_bytes(snap.disk_total)}"),
    )

    usage.add_row("NET", Text(f"↓ {format_rate(snap.net_down)}   ↑ {format_rate(snap.net_up)}"))
    usage.add_row("I/O", Text(f"R {format_rate(snap.disk_read)}   W {format_rate(snap.disk_write)}"))

    title = f"Top processes (sorted by {sort_by})"
    if name_filter:
        title += f" matching '{name_filter}'"
    table = Table(title=title, expand=True)
    table.add_column("PID", justify="right")
    table.add_column("Name")
    table.add_column("CPU %", justify="right")
    table.add_column("MEM %", justify="right")
    if not snap.processes:
        table.add_row("-", "(no matching processes)", "-", "-")
    for p in snap.processes:
        table.add_row(str(p.pid), p.name, f"{p.cpu_percent:.1f}", f"{p.memory_percent:.1f}")

    return Group(Panel(usage, title="sysmon", border_style="cyan"), table)
