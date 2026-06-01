# POEasy 2.0

A lightweight Windows macro utility that maps a single keypress or key combination to a sequence of keystrokes fired with configurable random delays.

It is designed for repetitive task automation where human-like timing variance is preferred over robotic, fixed-rate inputs.

<img width="1064" height="853" alt="POEasy interface layout" src="https://github.com/user-attachments/assets/bb82140e-68bc-4de6-8fa8-f6865d6c9090" />

## Features

- **Custom macro sequences**: Supports standard keys and modifier combinations (`Ctrl+G`, `Shift+A`, `Ctrl+Shift+B`, etc.).
- **Randomized delays**: Configure custom min/max delay ranges (in milliseconds) between keystrokes for each macro.
- **Dynamic hotkey updates**: Modify triggers, sequences, or delays while the utility is running without needing a restart.
- **Trigger key capture**: Set macro triggers by pressing keys directly inside the input interface.
- **Tray integration**: Minimizes to the system tray and runs unobtrusively in the background.
- **Auto-start**: Toggle auto-start behavior directly from the system tray context menu.
- **Single-instance lock**: Prevents launching duplicate instances of the application.
- **Dark interface**: Modern dark theme featuring inline editable names and click-to-delete chip bubbles.
- **Portable settings**: Configurations are saved in a local `poeasy_settings.json` file beside the executable.

## Usage

| Action | Instructions |
|---|---|
| Start macros | Click **Start** or press **F10** |
| Stop macros | Click **Stop** or press **F11** |
| Add a macro | Click **+ Add Shortcut** |
| Set trigger | Click the trigger field and press your key combination |
| Set sequence | Click the keys field and enter characters or modifier combinations |
| Delete a token | Hover over a token and click the **x** |
| Minimize to tray | Minimize or close the main window |
| Quit | Right-click the system tray icon and select **Quit** |

## Download

Download the latest version of `POEasy.exe` from the [Releases](https://github.com/infinition/POEasy/releases) page. The utility is fully portable and requires no installation.

## Build from Source

Ensure you have Python 3.12+ installed on Windows.

Install dependencies and run the build script:
```bash
pip install PyQt6 keyboard pyinstaller
python build.py
```

The compiled binary will be placed at `dist/POEasy.exe`.

## How it Works

When a trigger key is pressed, POEasy dispatches each keystroke in the mapped sequence with a random delay (bounded by the configured min/max range) between inputs. Modifier combinations like `Ctrl+G` are intercepted and dispatched as single atomic operations using low-level keyboard hooks.

## Star History

<a href="https://www.star-history.com/?repos=infinition%2FPOEasy&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=infinition/POEasy&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=infinition/POEasy&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=infinition/POEasy&type=date&legend=top-left" />
 </picture>
</a>

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
