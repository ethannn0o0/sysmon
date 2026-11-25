# sysmon

A tiny terminal system monitor written in Python, built on [psutil](https://github.com/giampaolo/psutil) and [rich](https://github.com/Textualize/rich).

Shows CPU, memory and disk usage plus the top processes, refreshing live.

## Install

```bash
pip install -e .          # from the project root
pip install -e ".[dev]"   # with test dependencies
pip install -e ".[gui]"   # with the floating window (PySide6)
```

## Usage

```bash
sysmon                    # live view, Ctrl+C to quit
sysmon --once             # print a single snapshot
sysmon -n 20 -s memory    # top 20 processes by memory
sysmon -f chrome          # only processes whose name contains 'chrome'
sysmon --gui              # floating always-on-top window (drag to move, right-click for menu)
sysmon -i 2               # refresh every 2 seconds
python -m sysmon          # run without installing the script
sysmon kill 1234          # terminate PID 1234 (asks for confirmation)
sysmon kill 1234 -f -y    # force-kill, no confirmation
sysmon --json             # print one snapshot as JSON (pipe-friendly)
sysmon --json -o out.json # write the snapshot to a file
```

## Skins

Right-click the floating window -> **Skin**. Built-in skins: Midnight, Slime, Kitty, Sunny Bunny.
The cartoon mascot changes expression with system load (idle / busy / overload).

Make your own: choose **Skin -> Open skins folder...** (creates `~/.sysmon/skins/` with an example),
copy the example folder and edit its `skin.json`. New skins appear in the menu immediately.

```json
{
  "name": "My Skin",
  "colors": {"bg": "#1e1e2e", "track": "#45475a", "text": "#cdd6f4", "dim": "#6c7086",
             "good": "#a6e3a1", "warn": "#f9e2af", "bad": "#f38ba8"},
  "bg_alpha": 0.9,
  "radius": 12,
  "mascot": {
    "builtin": "cat",
    "color": "#f5c2e7",
    "frames": {"idle": "idle.png", "busy": "busy.png", "overload": "overload.png"}
  },
  "lines": {"idle": "purr~", "busy": "hunting...", "overload": "nyaaa!!"}
}
```

- Every field is optional; invalid values fall back to defaults and a broken skin is skipped.
- `mascot.builtin` is `blob`, `cat` or `bunny` (drawn in code). `frames` are your own images
  (png/jpg/webp, inside the skin folder) and take priority; `idle` is required, missing moods reuse it.
- Mood: overload at CPU >= 80% or memory >= 92%; busy at CPU >= 40% or memory >= 80%.
- Only install skins you trust to look at; skins contain no code, just colours and images.

## Development

```bash
pytest
```

## Roadmap

- [x] Kill a process by PID
- [x] Process name filter / search
- [ ] Network and disk I/O rates
- [x] Export snapshot as JSON
- [ ] Interactive UI with [Textual](https://github.com/Textualize/textual)

## License

MIT
