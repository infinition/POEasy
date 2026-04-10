# POEasy 2.0

A lightweight Windows macro tool that maps a single keypress (or key combination) to a sequence of keystrokes fired with configurable random delays between each one.

Built for repetitive key-sequence tasks where you want human-like timing variance instead of robotic fixed-rate input.

## Features

- **Per-macro key sequences** with support for single keys and modifier combos (`Ctrl+G`, `Shift+A`, `Ctrl+Shift+B`, etc.)
- **Per-macro random delays** - each macro gets its own min/max delay range (ms) between keystrokes
- **Live reload** - change any trigger, sequence, or delay while running; hotkeys update automatically, no restart needed
- **Trigger key capture** - press any key or combo directly in the UI to set it as the trigger
- **System tray** - minimizes to tray, runs silently in the background
- **Start with Windows** - optional, toggleable from tray right-click menu (registry-based)
- **Single instance** - prevents launching multiple copies
- **Dark UI** - clean, polished dark theme with inline editable names and hover-to-delete chip bubbles
- **Portable settings** - `poeasy_settings.json` saved next to the executable

## Usage

| Action | How |
|--------|-----|
| Start macros | Click **Start** or press **F10** |
| Stop macros | Click **Stop** or press **F11** |
| Add a macro | Click **+ Add Shortcut** |
| Set trigger | Click the trigger field, press your key/combo |
| Set sequence | Click the keys field, type single chars or press combos |
| Delete a token | Hover over it, click the **x** |
| Minimize to tray | Minimize or close the window |
| Quit | Right-click tray icon, **Quit** |

## Download

Grab the latest `POEasy.exe` from the [Releases](https://github.com/infinition/POEasy/releases) page. No installation required - just run it.

## Build from source

Requirements: Python 3.12+, Windows.

```bash
pip install PyQt6 keyboard pyinstaller
python build.py
```

The executable lands in `dist/POEasy.exe`.

## How it works

When you press a trigger key, POEasy fires each key in the mapped sequence with a random delay (within your configured min–max range) between keystrokes. Modifier combos like `Ctrl+G` are sent as a single atomic keypress via the `keyboard` library's low-level hooks.

## License

[MIT](LICENSE)
