"""Command-line entry point."""

from __future__ import annotations

import argparse
import time
from typing import List, Optional

from rich.console import Console
from rich.live import Live

from sysmon import __version__
from sysmon.collector import KillError, kill_process, prime_cpu_counters, process_name, snapshot_to_json, take_snapshot
from sysmon.display import render


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sysmon", description="A tiny terminal system monitor.")
    p.add_argument("-n", "--top", type=int, default=10, help="number of processes to show (default 10)")
    p.add_argument("-s", "--sort", choices=["cpu", "memory"], default="cpu", help="sort processes by (default cpu)")
    p.add_argument("-i", "--interval", type=float, default=1.0, help="refresh interval in seconds (default 1.0)")
    p.add_argument("-f", "--filter", default="", metavar="TEXT", help="only show processes whose name contains TEXT (case-insensitive)")
    p.add_argument("--once", action="store_true", help="print one snapshot and exit")
    p.add_argument("--gui", action="store_true", help="open a floating always-on-top window")
    p.add_argument("--json", action="store_true", help="print one snapshot as JSON and exit")
    p.add_argument("-o", "--output", metavar="FILE", help="with --json, write to FILE instead of stdout")
    p.add_argument("-V", "--version", action="version", version=f"sysmon {__version__}")
    sub = p.add_subparsers(dest="command")
    k = sub.add_parser("kill", help="terminate a process by PID")
    k.add_argument("pid", type=int, help="PID of the process to terminate")
    k.add_argument("-f", "--force", action="store_true", help="kill immediately instead of asking politely")
    k.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    return p


def run_kill(args, console: Console) -> int:
    try:
        name = process_name(args.pid)
        if not args.yes:
            answer = input(f"Terminate {name} (PID {args.pid})? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                console.print("Cancelled.")
                return 1
        kill_process(args.pid, force=args.force)
    except KillError as e:
        console.print(f"[red]error:[/red] {e}")
        return 1
    console.print(f"[green]Terminated[/green] {name} (PID {args.pid})")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()

    if args.command == "kill":
        return run_kill(args, console)

    if args.gui:
        try:
            from sysmon.gui import main as gui_main  # lazy: the CLI works without PySide6
        except ImportError:
            console.print('[red]error:[/red] the floating window needs PySide6: pip install "sysmon[gui]"')
            return 2

        return gui_main(min(args.top, 15), args.sort, args.interval, args.filter)

    if args.output and not args.json:
        console.print("[red]error:[/red] --output requires --json")
        return 2

    prime_cpu_counters()
    time.sleep(0.5)  # let counters accumulate so the first reading is meaningful

    if args.json:
        text = snapshot_to_json(take_snapshot(args.top, args.sort, args.filter))
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            console.print(f"Wrote snapshot to {args.output}")
        else:
            print(text)  # plain print: keep stdout clean for piping, no rich markup
        return 0

    if args.once:
        console.print(render(take_snapshot(args.top, args.sort, args.filter), args.sort, args.filter))
        return 0

    try:
        with Live(console=console, refresh_per_second=4, screen=False) as live:
            while True:
                live.update(render(take_snapshot(args.top, args.sort, args.filter), args.sort, args.filter))
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass  # Ctrl+C is the normal way to quit
    return 0
