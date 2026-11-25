"""Skins: colours + an optional cartoon mascot. No Qt here, so it is easy to test.

A user skin is a folder under ~/.sysmon/skins/ containing a skin.json:

    {
      "name": "My Skin",
      "colors": {"bg": "#1e1e2e", "text": "#cdd6f4", "good": "#a6e3a1"},
      "bg_alpha": 0.9,
      "radius": 12,
      "mascot": {
        "builtin": "cat",                 # blob | cat | bunny   (drawn in code), or
        "color": "#f5c2e7",
        "frames": {"idle": "idle.png", "busy": "busy.png", "overload": "overload.png"}
      },
      "lines": {"idle": "chill~", "busy": "working...", "overload": "too hot!!"}
    }

Every field is optional; anything missing or invalid falls back to the default.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional

MOODS = ("idle", "busy", "overload")
BUILTIN_MASCOTS = ("blob", "cat", "bunny")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
COLOR_KEYS = ("bg", "track", "text", "dim", "good", "warn", "bad")


def default_skins_dir() -> Path:
    return Path.home() / ".sysmon" / "skins"


@dataclass(frozen=True)
class Skin:
    name: str
    bg: str = "#1e1e2e"
    track: str = "#45475a"
    text: str = "#cdd6f4"
    dim: str = "#6c7086"
    good: str = "#a6e3a1"
    warn: str = "#f9e2af"
    bad: str = "#f38ba8"
    bg_alpha: float = 0.9
    radius: int = 12
    mascot_kind: Optional[str] = None  # one of BUILTIN_MASCOTS, or None
    mascot_color: str = "#a6e3a1"
    frames: Dict[str, Path] = field(default_factory=dict)  # mood -> image file
    lines: Dict[str, str] = field(
        default_factory=lambda: {"idle": "chill~", "busy": "working...", "overload": "too hot!!"}
    )

    @property
    def has_mascot(self) -> bool:
        return bool(self.frames) or self.mascot_kind is not None

    def frame_for(self, mood: str) -> Optional[Path]:
        return self.frames.get(mood) or self.frames.get("idle")


MIDNIGHT = Skin(name="Midnight")

BUILTIN_SKINS: List[Skin] = [
    MIDNIGHT,
    Skin(name="Slime", bg="#1b2a24", track="#2f4a3f", text="#d7f5e3", dim="#6f9b86",
         good="#a6e3a1", warn="#f9e2af", bad="#f38ba8", mascot_kind="blob", mascot_color="#8fe3a0",
         lines={"idle": "boing~", "busy": "squish...", "overload": "melting!!"}),
    Skin(name="Kitty", bg="#2b2233", track="#4b3a5a", text="#f5e0ee", dim="#9a7fa8",
         good="#a6e3a1", warn="#f9e2af", bad="#f38ba8", mascot_kind="cat", mascot_color="#f5c2e7",
         lines={"idle": "purr~", "busy": "hunting...", "overload": "nyaaa!!"}),
    Skin(name="Sunny Bunny", bg="#fff6e5", track="#f0dcc0", text="#5a4636", dim="#b09a82",
         good="#6bbf7a", warn="#e8a93a", bad="#e0605e", bg_alpha=0.95, mascot_kind="bunny",
         mascot_color="#ffffff", lines={"idle": "hop hop~", "busy": "digging...", "overload": "eek!!"}),
]


def mood_for(cpu_percent: float, mem_percent: float) -> str:
    """Map load to a mascot mood. CPU drives it; memory only matters when nearly full,
    since memory sits at a high level on many machines all day."""
    if cpu_percent >= 80 or mem_percent >= 92:
        return "overload"
    if cpu_percent >= 40 or mem_percent >= 80:
        return "busy"
    return "idle"


def _color(value, fallback: str) -> str:
    return value if isinstance(value, str) and _HEX.match(value) else fallback


def _inside(base: Path, rel) -> Optional[Path]:
    """Resolve `rel` under `base`; reject absolute paths, '..' escapes and non-images."""
    if not isinstance(rel, str):
        return None
    p = (base / rel).resolve()
    try:
        p.relative_to(base.resolve())
    except ValueError:
        return None
    return p if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES else None


def parse_skin(data: dict, base: Path) -> Skin:
    """Build a Skin from decoded skin.json; invalid fields fall back to defaults."""
    if not isinstance(data, dict):
        raise ValueError("skin.json must contain an object")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        name = base.name
    colors = data.get("colors") if isinstance(data.get("colors"), dict) else {}
    kwargs = {k: _color(colors.get(k), getattr(MIDNIGHT, k)) for k in COLOR_KEYS}

    alpha = data.get("bg_alpha", MIDNIGHT.bg_alpha)
    radius = data.get("radius", MIDNIGHT.radius)
    kwargs["bg_alpha"] = float(alpha) if isinstance(alpha, (int, float)) and 0.2 <= alpha <= 1 else MIDNIGHT.bg_alpha
    kwargs["radius"] = int(radius) if isinstance(radius, int) and 0 <= radius <= 30 else MIDNIGHT.radius

    mascot = data.get("mascot") if isinstance(data.get("mascot"), dict) else {}
    kind = mascot.get("builtin")
    kwargs["mascot_kind"] = kind if kind in BUILTIN_MASCOTS else None
    kwargs["mascot_color"] = _color(mascot.get("color"), MIDNIGHT.mascot_color)
    frames_in = mascot.get("frames") if isinstance(mascot.get("frames"), dict) else {}
    frames = {m: path for m in MOODS if (path := _inside(base, frames_in.get(m)))}
    kwargs["frames"] = frames if "idle" in frames else {}  # frames need at least an idle image

    lines = dict(MIDNIGHT.lines)
    if isinstance(data.get("lines"), dict):
        lines.update({m: v[:24] for m, v in data["lines"].items() if m in MOODS and isinstance(v, str)})
    kwargs["lines"] = lines
    return Skin(name=name.strip()[:30], **kwargs)


def load_skins(user_dir: Optional[Path] = None) -> List[Skin]:
    """Built-in skins followed by valid user skins. A broken skin is skipped, never fatal."""
    skins = list(BUILTIN_SKINS)
    user_dir = user_dir if user_dir is not None else default_skins_dir()
    if user_dir.is_dir():
        for folder in sorted(p for p in user_dir.iterdir() if p.is_dir()):
            manifest = folder / "skin.json"
            if not manifest.is_file():
                continue
            try:
                skin = parse_skin(json.loads(manifest.read_text(encoding="utf-8")), folder)
            except (OSError, ValueError):  # JSONDecodeError is a ValueError
                continue
            if all(s.name != skin.name for s in skins):  # names must be unique
                skins.append(skin)
    return skins


def find_skin(skins: List[Skin], name: str) -> Skin:
    return next((s for s in skins if s.name == name), skins[0])


EXAMPLE_SKIN = {
    "name": "Example (edit me)",
    "colors": {"bg": "#1d2433", "track": "#34405a", "text": "#e6edf7", "dim": "#7f8fa9",
               "good": "#7fdca4", "warn": "#ffd479", "bad": "#ff7a85"},
    "bg_alpha": 0.9,
    "radius": 14,
    "mascot": {"builtin": "blob", "color": "#7fb8ff"},
    "lines": {"idle": "hello!", "busy": "on it...", "overload": "help!!"},
}


def ensure_user_dir(user_dir: Optional[Path] = None) -> Path:
    """Create the skins folder and, if it is empty, drop in an example to copy from."""
    user_dir = user_dir if user_dir is not None else default_skins_dir()
    user_dir.mkdir(parents=True, exist_ok=True)
    if not any(p.is_dir() for p in user_dir.iterdir()):
        example = user_dir / "example-skin"
        example.mkdir()
        (example / "skin.json").write_text(json.dumps(EXAMPLE_SKIN, indent=2), encoding="utf-8")
    return user_dir
