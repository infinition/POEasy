"""
POEasy 2.0 — Macro overlay for Path of Exile.
Press a single key to fire skill sequences with human-like random delays.
"""

import sys
import json
import random
import re
import time
import os
import threading
import logging
import ctypes
import winreg
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QFrame, QMessageBox, QGridLayout,
    QScrollArea, QSizePolicy, QCheckBox, QSystemTrayIcon, QMenu,
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QEvent, QPoint
from PyQt6.QtGui import (
    QFont, QIcon, QIntValidator, QAction, QPixmap, QPainter,
    QColor, QBrush, QPen, QPolygon, QKeySequence,
)
import keyboard

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(_BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "poeasy.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("POEasy")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
APP_NAME = "POEasy 2.0"

if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(_APP_DIR, "poeasy_settings.json")
ICON_PATH = os.path.join(_APP_DIR, "poeasy.ico")
MAX_SHORTCUTS = 20
MIN_DELAY_DEFAULT = 30
MAX_DELAY_DEFAULT = 80
SAVE_DEBOUNCE_MS = 500
HOTKEY_RELOAD_MS = 600

# Modifier keys to detect combos
_MODIFIER_NAMES = {"ctrl", "shift", "alt", "win", "meta",
                   "control", "lctrl", "rctrl", "lshift", "rshift",
                   "lalt", "ralt", "lwin", "rwin"}

# ---------------------------------------------------------------------------
# Single-instance mutex (Windows)
# ---------------------------------------------------------------------------
_mutex_handle = None


def acquire_single_instance() -> bool:
    global _mutex_handle
    try:
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\POEasy2Mutex")
        last_err = ctypes.windll.kernel32.GetLastError()
        if last_err == 183:
            return False
        return True
    except Exception:
        return True


def release_single_instance():
    global _mutex_handle
    if _mutex_handle:
        try:
            ctypes.windll.kernel32.ReleaseMutex(_mutex_handle)
            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None


# ---------------------------------------------------------------------------
# Windows startup (registry)
# ---------------------------------------------------------------------------
_STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_REG_NAME = "POEasy"


def _get_exe_path() -> str:
    """Return the path to the running executable."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(sys.argv[0])


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, _STARTUP_REG_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as e:
        log.warning("Failed to read startup registry: %s", e)
        return False


def set_startup_enabled(enabled: bool):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                exe = _get_exe_path()
                winreg.SetValueEx(key, _STARTUP_REG_NAME, 0, winreg.REG_SZ, f'"{exe}"')
                log.info("Startup enabled: %s", exe)
            else:
                try:
                    winreg.DeleteValue(key, _STARTUP_REG_NAME)
                except FileNotFoundError:
                    pass
                log.info("Startup disabled.")
    except Exception as e:
        log.error("Failed to update startup registry: %s", e)


# ---------------------------------------------------------------------------
# Key sequence parsing helpers
# ---------------------------------------------------------------------------
def serialize_key_tokens(tokens: list) -> str:
    """Serialize token list to string: single chars raw, combos in parens.
    e.g. ['a','z','r','ctrl+g','shift+a'] -> 'azr(ctrl+g)(shift+a)'
    """
    parts = []
    for t in tokens:
        if len(t) == 1:
            parts.append(t)
        else:
            parts.append(f"({t})")
    return "".join(parts)


def parse_key_tokens(s: str) -> list:
    """Parse 'azr(ctrl+g)(shift+a)' -> ['a','z','r','ctrl+g','shift+a']"""
    tokens = []
    i = 0
    while i < len(s):
        if s[i] == "(":
            j = s.find(")", i)
            if j == -1:
                j = len(s)
            combo = s[i + 1:j].strip()
            if combo:
                tokens.append(combo)
            i = j + 1
        else:
            tokens.append(s[i])
            i += 1
    return tokens


def is_combo(token: str) -> bool:
    """True if token is a combo like 'ctrl+g' (contains + and has modifier)."""
    if "+" not in token:
        return False
    parts = token.lower().split("+")
    return any(p.strip() in _MODIFIER_NAMES for p in parts)


# ---------------------------------------------------------------------------
# Icon generator
# ---------------------------------------------------------------------------
def _generate_icon_pixmap(border_color: QColor, bolt_color: QColor, bolt_outline: QColor,
                          bg_color: QColor = QColor(30, 30, 30)) -> QPixmap:
    size = 256
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(bg_color))
    painter.setPen(QPen(border_color, 6))
    painter.drawEllipse(8, 8, size - 16, size - 16)
    bolt = QPolygon([
        QPoint(145, 30), QPoint(85, 125), QPoint(130, 125),
        QPoint(110, 226), QPoint(175, 118), QPoint(128, 118),
    ])
    painter.setBrush(QBrush(bolt_color))
    painter.setPen(QPen(bolt_outline, 3))
    painter.drawPolygon(bolt)
    painter.end()
    return pixmap


def generate_icons() -> tuple:
    px_off = _generate_icon_pixmap(
        QColor(46, 160, 67), QColor(255, 185, 0), QColor(200, 140, 0),
        bg_color=QColor(30, 30, 30),
    )
    px_on = _generate_icon_pixmap(
        QColor(35, 200, 70), QColor(255, 210, 0), QColor(220, 170, 0),
        bg_color=QColor(30, 140, 50),
    )
    return QIcon(px_off), QIcon(px_on)


def save_icon_to_ico(icon: QIcon, path: str):
    try:
        pixmap = icon.pixmap(256, 256)
        pixmap.save(path, "ICO")
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            pixmap.save(path.replace(".ico", ".png"), "PNG")
    except Exception as e:
        log.warning("Could not save icon: %s", e)


# ---------------------------------------------------------------------------
# Dark theme stylesheet
# ---------------------------------------------------------------------------
DARK_STYLE = """
QMainWindow {
    background-color: #1a1a2e;
    font-family: 'Segoe UI', sans-serif;
}
QWidget {
    background: transparent;
    font-family: 'Segoe UI', sans-serif;
}
QLabel {
    color: #e0e0e0;
    background: transparent;
    border: none;
}
QLineEdit {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 6px;
    color: #e0e0e0;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: #e94560;
}
QLineEdit:focus {
    border: 1px solid #e94560;
}
QLineEdit:disabled {
    background-color: #0d1528;
    color: #555;
}
QPushButton {
    color: white;
    border: none;
    font-weight: bold;
    font-size: 13px;
    border-radius: 6px;
    padding: 8px 16px;
    background: transparent;
}
QPushButton:disabled {
    background-color: #333;
    color: #666;
}
QCheckBox {
    color: #e0e0e0;
    spacing: 6px;
    background: transparent;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid #0f3460;
    background-color: #16213e;
}
QCheckBox::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: #16213e;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #0f3460;
    min-height: 30px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QToolTip {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    padding: 4px 8px;
    border-radius: 4px;
}
QMenu {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
}
QMenu::item:selected {
    background-color: #e94560;
}
"""


# ---------------------------------------------------------------------------
# Combo chip (bubble) widget
# ---------------------------------------------------------------------------
class ComboChip(QFrame):
    """A small rounded pill showing a combo like 'Ctrl+G' with a delete on hover."""
    removed = pyqtSignal(int)  # emits index

    def __init__(self, text: str, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        lbl = QLabel(text)
        lbl.setStyleSheet("color: #e0e0e0; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        layout.addWidget(lbl)

        self._del_btn = QPushButton("\u00d7")
        self._del_btn.setFixedSize(16, 16)
        self._del_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.15); border-radius: 8px;
                color: #ccc; font-size: 12px; padding: 0; font-weight: bold;
            }
            QPushButton:hover { background: #e94560; color: white; }
        """)
        self._del_btn.hide()
        self._del_btn.clicked.connect(lambda: self.removed.emit(self._index))
        layout.addWidget(self._del_btn)

        self.setStyleSheet("""
            ComboChip {
                background-color: #0f3460;
                border-radius: 12px;
                border: 1px solid #1a4a8a;
            }
        """)

    def enterEvent(self, event):
        self._del_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._del_btn.hide()
        super().leaveEvent(event)


# ---------------------------------------------------------------------------
# KeySequenceInput — input with inline bubble chips for combos
# ---------------------------------------------------------------------------
class KeySequenceInput(QWidget):
    """Input showing single keys as text and combos as bubble chips.

    Data: list of tokens — single char ('a') or combo ('ctrl+g').
    Visual: a z r [Ctrl+G] [Shift+A] [input...]
    """
    changed = pyqtSignal()

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._tokens: list = []
        self._placeholder = placeholder

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._container = QFrame()
        self._container.setObjectName("seq_container")
        self._container.setStyleSheet("""
            QFrame#seq_container {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 6px;
            }
        """)
        outer.addWidget(self._container)

        self._hbox = QHBoxLayout(self._container)
        self._hbox.setContentsMargins(6, 4, 6, 4)
        self._hbox.setSpacing(4)

        self._input = _InlineKeyInput(placeholder=self._placeholder)
        self._input.setMinimumWidth(60)
        self._input.combo_pressed.connect(self._on_combo)
        self._input.text_committed.connect(self._on_text_committed)
        self._input.backspace_empty.connect(self._on_backspace_empty)
        self._hbox.addWidget(self._input, 1)

    def _rebuild_chips(self):
        # Remove everything except stretch at end
        while self._hbox.count() > 0:
            item = self._hbox.takeAt(0)
            w = item.widget()
            if w and w is not self._input:
                w.setParent(None)
                w.deleteLater()

        # Re-add token widgets then input
        for i, token in enumerate(self._tokens):
            if is_combo(token):
                chip = ComboChip(token.upper(), i)
                chip.removed.connect(self._remove_token)
                self._hbox.addWidget(chip)
            else:
                chip = _SingleKeyChip(token, i)
                chip.removed.connect(self._remove_token)
                self._hbox.addWidget(chip)

        self._hbox.addWidget(self._input, 1)
        self._input.clear()

    def _on_combo(self, combo_str: str):
        self._tokens.append(combo_str.lower())
        self._rebuild_chips()
        self.changed.emit()

    def _on_text_committed(self, text: str):
        for ch in text:
            if ch.strip():
                self._tokens.append(ch)
        self._rebuild_chips()
        self.changed.emit()

    def _on_backspace_empty(self):
        if self._tokens:
            self._tokens.pop()
            self._rebuild_chips()
            self.changed.emit()

    def _remove_token(self, index: int):
        if 0 <= index < len(self._tokens):
            self._tokens.pop(index)
            self._rebuild_chips()
            self.changed.emit()

    def get_tokens(self) -> list:
        pending = self._input.text().strip()
        if pending:
            for ch in pending:
                if ch.strip():
                    self._tokens.append(ch)
            self._input.clear()
        return list(self._tokens)

    def get_serialized(self) -> str:
        return serialize_key_tokens(self.get_tokens())

    def set_tokens(self, tokens: list):
        self._tokens = list(tokens)
        self._rebuild_chips()

    def set_from_string(self, s: str):
        self._tokens = parse_key_tokens(s)
        self._rebuild_chips()


class _SingleKeyChip(QFrame):
    """A single-char token shown inline with hover-delete."""
    removed = pyqtSignal(int)

    def __init__(self, char: str, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)

        self._lbl = QLabel(char)
        self._lbl.setStyleSheet("color: #e0e0e0; font-size: 13px; background: transparent; border: none;")
        layout.addWidget(self._lbl)

        self._del_btn = QPushButton("\u00d7")
        self._del_btn.setFixedSize(14, 14)
        self._del_btn.setStyleSheet("""
            QPushButton {
                background: rgba(233,69,96,0.6); border-radius: 7px;
                color: white; font-size: 10px; padding: 0;
            }
            QPushButton:hover { background: #e94560; }
        """)
        self._del_btn.hide()
        self._del_btn.clicked.connect(lambda: self.removed.emit(self._index))
        layout.addWidget(self._del_btn)

    def enterEvent(self, event):
        self._del_btn.show()
        self._lbl.setStyleSheet("color: #e94560; font-size: 13px; background: transparent; border: none;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._del_btn.hide()
        self._lbl.setStyleSheet("color: #e0e0e0; font-size: 13px; background: transparent; border: none;")
        super().leaveEvent(event)


def _qt_key_to_name(key: int) -> str:
    """Convert a Qt key code to a keyboard-library-compatible name."""
    # Map common Qt keys to keyboard library names
    _MAP = {
        Qt.Key.Key_Space: "space", Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter",
        Qt.Key.Key_Tab: "tab", Qt.Key.Key_Escape: "esc", Qt.Key.Key_Backspace: "backspace",
        Qt.Key.Key_Delete: "delete", Qt.Key.Key_Insert: "insert",
        Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end",
        Qt.Key.Key_PageUp: "page up", Qt.Key.Key_PageDown: "page down",
        Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down",
        Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right",
        Qt.Key.Key_CapsLock: "caps lock", Qt.Key.Key_NumLock: "num lock",
        Qt.Key.Key_ScrollLock: "scroll lock", Qt.Key.Key_Print: "print screen",
        Qt.Key.Key_Pause: "pause",
    }
    if key in _MAP:
        return _MAP[key]
    # F1-F24
    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        return f"f{key - Qt.Key.Key_F1 + 1}"
    # Regular printable keys — use QKeySequence but force lowercase
    name = QKeySequence(key).toString()
    if name:
        return name.lower()
    return ""


class _InlineKeyInput(QLineEdit):
    """Captures keyboard: detects modifier combos and plain text."""
    combo_pressed = pyqtSignal(str)   # e.g. 'ctrl+g'
    text_committed = pyqtSignal(str)  # plain text before a combo or on blur
    backspace_empty = pyqtSignal()

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: #e0e0e0; "
            "font-size: 13px; padding: 2px 0; }"
        )
        self.setFrame(False)

    def keyPressEvent(self, event):
        mods = event.modifiers()
        key = event.key()

        # Ignore lone modifier presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta, Qt.Key.Key_unknown):
            return

        has_ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        has_shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        has_alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        # Any modifier held (ctrl, shift, alt) → treat as combo
        if has_ctrl or has_shift or has_alt:
            parts = []
            if has_ctrl:
                parts.append("ctrl")
            if has_shift:
                parts.append("shift")
            if has_alt:
                parts.append("alt")

            key_name = _qt_key_to_name(key)
            if key_name:
                parts.append(key_name)
                combo = "+".join(parts)

                # Commit any pending text first
                pending = self.text().strip()
                if pending:
                    self.text_committed.emit(pending)
                    self.clear()

                self.combo_pressed.emit(combo)
                return

        # Backspace on empty input -> delete last token
        if key == Qt.Key.Key_Backspace and not self.text():
            self.backspace_empty.emit()
            return

        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        pending = self.text().strip()
        if pending:
            self.text_committed.emit(pending)
            self.clear()
        super().focusOutEvent(event)


# ---------------------------------------------------------------------------
# Trigger key input — captures a single combo or key
# ---------------------------------------------------------------------------
class TriggerKeyInput(QWidget):
    """Captures a single trigger key/combo via keypress. Shows as a chip or text."""
    changed = pyqtSignal()

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._value = ""  # e.g. "2" or "ctrl+g"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._container = QFrame()
        self._container.setObjectName("trigger_container")
        self._container.setStyleSheet("""
            QFrame#trigger_container {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 6px;
                padding: 2px 4px;
            }
        """)
        layout.addWidget(self._container)

        self._inner = QHBoxLayout(self._container)
        self._inner.setContentsMargins(6, 4, 6, 4)
        self._inner.setSpacing(4)

        self._chip_holder = QHBoxLayout()
        self._chip_holder.setSpacing(4)
        self._inner.addLayout(self._chip_holder)

        self._input = _TriggerCaptureInput(placeholder)
        self._input.key_captured.connect(self._on_key_captured)
        self._inner.addWidget(self._input)

    def _on_key_captured(self, key_str: str):
        self._value = key_str
        self._rebuild()
        self.changed.emit()

    def _rebuild(self):
        # Clear chips
        while self._chip_holder.count():
            item = self._chip_holder.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        if self._value:
            chip = ComboChip(self._value.upper(), 0)
            chip.removed.connect(self._clear)
            self._chip_holder.addWidget(chip)
            self._input.clear()
            self._input.setPlaceholderText("")
        else:
            self._input.setPlaceholderText("Press a key or combo...")

    def _clear(self, _idx=0):
        self._value = ""
        self._rebuild()
        self.changed.emit()

    def get_value(self) -> str:
        return self._value

    def set_value(self, v: str):
        self._value = v
        self._rebuild()


class _TriggerCaptureInput(QLineEdit):
    """Captures a single key or combo for use as trigger."""
    key_captured = pyqtSignal(str)

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setReadOnly(True)
        self.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: #e0e0e0; "
            "font-size: 13px; padding: 2px 0; }"
        )
        self.setFrame(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def keyPressEvent(self, event):
        mods = event.modifiers()
        key = event.key()

        # Ignore lone modifier presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta, Qt.Key.Key_unknown):
            return

        has_ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        has_shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        has_alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        parts = []
        if has_ctrl:
            parts.append("ctrl")
        if has_shift:
            parts.append("shift")
        if has_alt:
            parts.append("alt")

        key_name = _qt_key_to_name(key)
        if not key_name:
            return

        parts.append(key_name)
        result = "+".join(parts)
        self.key_captured.emit(result)

    def mousePressEvent(self, event):
        self.setFocus()
        super().mousePressEvent(event)






# ---------------------------------------------------------------------------
# Editable label widget
# ---------------------------------------------------------------------------
class EditableLabel(QWidget):
    text_changed = pyqtSignal(str)

    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.label = QLabel(initial_text)
        self.label.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 14px;")

        self.edit_btn = QPushButton("\u270e")
        self.edit_btn.setToolTip("Rename")
        self.edit_btn.setFixedSize(26, 26)
        self.edit_btn.setStyleSheet("""
            QPushButton { background-color: #0f3460; border-radius: 4px; font-size: 14px; padding: 0; }
            QPushButton:hover { background-color: #e94560; }
        """)
        self.edit_btn.clicked.connect(self._start_editing)

        self.line_edit = QLineEdit(initial_text)
        self.line_edit.setMaximumWidth(200)
        self.line_edit.setHidden(True)
        self.line_edit.editingFinished.connect(self._finish_editing)

        layout.addWidget(self.label)
        layout.addWidget(self.line_edit)
        layout.addWidget(self.edit_btn)
        layout.addStretch()

    def _start_editing(self):
        self.line_edit.setText(self.label.text())
        self.label.hide()
        self.line_edit.show()
        self.line_edit.setFocus()
        self.line_edit.selectAll()

    def _finish_editing(self):
        text = self.line_edit.text().strip()
        if text:
            self.label.setText(text)
            self.text_changed.emit(text)
        self.label.show()
        self.line_edit.hide()

    def text(self) -> str:
        return self.label.text()

    def setText(self, text: str):
        self.label.setText(text)


# ---------------------------------------------------------------------------
# Shortcut card
# ---------------------------------------------------------------------------
class ShortcutCard(QFrame):
    data_changed = pyqtSignal()

    def __init__(self, index: int = 0, on_delete=None, parent=None):
        super().__init__(parent)
        self.index = index
        self._on_delete = on_delete
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName(f"card_{self.index}")
        self.setStyleSheet("""
            ShortcutCard {
                background-color: #16213e;
                border-radius: 10px;
                border: 1px solid #0f3460;
            }
            ShortcutCard:hover {
                border: 1px solid #e94560;
            }
        """)
        self.setMinimumHeight(195)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 12, 14, 12)

        # --- Header ---
        header = QHBoxLayout()
        header.setSpacing(8)
        self.name_editor = EditableLabel(f"Shortcut {self.index + 1}")
        self.name_editor.text_changed.connect(lambda _: self.data_changed.emit())
        header.addWidget(self.name_editor)
        header.addStretch()

        self.enabled_check = QCheckBox("Active")
        self.enabled_check.setChecked(True)
        self.enabled_check.setToolTip("Enable / disable this shortcut")
        self.enabled_check.stateChanged.connect(lambda _: self.data_changed.emit())
        header.addWidget(self.enabled_check)

        del_btn = QPushButton("\u2715")
        del_btn.setToolTip("Delete shortcut")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet("""
            QPushButton { background-color: #e94560; border-radius: 14px; font-size: 14px; padding: 0; }
            QPushButton:hover { background-color: #ff6b81; }
        """)
        del_btn.clicked.connect(lambda: self._on_delete(self.index) if self._on_delete else None)
        header.addWidget(del_btn)
        layout.addLayout(header)

        # --- Trigger key (captures combo or single key) ---
        trig_lbl = QLabel("Trigger:")
        trig_lbl.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(trig_lbl)

        self.trigger_input = TriggerKeyInput("Press a key or combo...")
        self.trigger_input.changed.connect(lambda: self.data_changed.emit())
        layout.addWidget(self.trigger_input)

        # --- Keys to send (sequence with combos) ---
        keys_lbl = QLabel("Keys to send:")
        keys_lbl.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(keys_lbl)

        self.keys_input = KeySequenceInput("Type keys or press combos...")
        self.keys_input.changed.connect(lambda: self.data_changed.emit())
        layout.addWidget(self.keys_input)

        # --- Delays ---
        delay_row = QHBoxLayout()
        delay_row.setSpacing(6)

        delay_lbl = QLabel("Delay (ms):")
        delay_lbl.setStyleSheet("font-size: 11px; color: #888;")
        delay_row.addWidget(delay_lbl)

        int_val = QIntValidator(0, 99999)

        self.min_delay_input = QLineEdit(str(MIN_DELAY_DEFAULT))
        self.min_delay_input.setValidator(int_val)
        self.min_delay_input.setPlaceholderText("Min")
        self.min_delay_input.setToolTip("Min random delay (ms)")
        self.min_delay_input.setMaximumWidth(70)
        self.min_delay_input.setStyleSheet("font-size: 11px; padding: 4px 6px;")
        self.min_delay_input.textChanged.connect(lambda _: self.data_changed.emit())
        delay_row.addWidget(self.min_delay_input)

        arrow = QLabel("\u2194")
        arrow.setStyleSheet("font-size: 14px; color: #555;")
        delay_row.addWidget(arrow)

        self.max_delay_input = QLineEdit(str(MAX_DELAY_DEFAULT))
        self.max_delay_input.setValidator(int_val)
        self.max_delay_input.setPlaceholderText("Max")
        self.max_delay_input.setToolTip("Max random delay (ms)")
        self.max_delay_input.setMaximumWidth(70)
        self.max_delay_input.setStyleSheet("font-size: 11px; padding: 4px 6px;")
        self.max_delay_input.textChanged.connect(lambda _: self.data_changed.emit())
        delay_row.addWidget(self.max_delay_input)

        delay_row.addStretch()
        layout.addLayout(delay_row)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def get_data(self) -> Dict:
        try:
            mn = int(self.min_delay_input.text() or 0)
        except ValueError:
            mn = MIN_DELAY_DEFAULT
        try:
            mx = int(self.max_delay_input.text() or 0)
        except ValueError:
            mx = MAX_DELAY_DEFAULT
        return {
            "name": self.name_editor.text(),
            "shortcut": self.trigger_input.get_value(),
            "keys": self.keys_input.get_serialized(),
            "enabled": self.enabled_check.isChecked(),
            "min_delay": mn,
            "max_delay": mx,
        }

    def set_data(self, data: Dict):
        self.name_editor.setText(data.get("name", f"Shortcut {self.index + 1}"))
        self.trigger_input.set_value(data.get("shortcut", ""))
        self.keys_input.set_from_string(data.get("keys", ""))
        self.enabled_check.setChecked(data.get("enabled", True))
        self.min_delay_input.setText(str(data.get("min_delay", MIN_DELAY_DEFAULT)))
        self.max_delay_input.setText(str(data.get("max_delay", MAX_DELAY_DEFAULT)))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class POEasyWindow(QMainWindow):
    _status_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(860, 660)

        self._icon_off, self._icon_on = generate_icons()
        self.setWindowIcon(self._icon_off)

        if not os.path.exists(ICON_PATH):
            save_icon_to_ico(self._icon_off, ICON_PATH)

        self._running = False
        self._stop_event = threading.Event()
        self._hotkey_ids: List = []
        self._cards: List[ShortcutCard] = []

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._do_save)

        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(HOTKEY_RELOAD_MS)
        self._reload_timer.timeout.connect(self._live_reload_hotkeys)

        self._status_signal.connect(self._on_status_message)

        self._setup_ui()
        self._setup_tray()
        self._setup_global_hotkeys()
        self._load_settings()

        log.info("POEasy started.")

    def _setup_ui(self):
        self.setStyleSheet(DARK_STYLE)

        central = QWidget()
        central.setStyleSheet("background-color: #1a1a2e;")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(16)
        root.setContentsMargins(22, 18, 22, 18)

        # --- Header ---
        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 26px; font-weight: bold; color: #e94560;")
        header.addWidget(title)

        self._status_dot = QLabel("\u25cf")
        self._status_dot.setStyleSheet("font-size: 28px; color: #e94560;")
        self._status_dot.setToolTip("Stopped")
        header.addWidget(self._status_dot)

        self._status_label = QLabel("Stopped")
        self._status_label.setStyleSheet("font-size: 12px; color: #888;")
        header.addWidget(self._status_label)

        header.addStretch()
        root.addLayout(header)

        # --- Shortcuts grid (scrollable) ---
        scroll_container = QWidget()
        scroll_container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(scroll_container)
        self._grid.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidget(scroll_container)
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)

        # --- Add button ---
        add_btn = QPushButton("\u2795  Add Shortcut")
        add_btn.setStyleSheet("""
            QPushButton { background-color: #0f3460; padding: 12px; font-size: 14px; }
            QPushButton:hover { background-color: #e94560; }
        """)
        add_btn.setToolTip(f"Add a new shortcut (max {MAX_SHORTCUTS})")
        add_btn.clicked.connect(self._add_card)
        root.addWidget(add_btn)

        # --- Start / Stop ---
        ctrl = QHBoxLayout()

        self._start_btn = QPushButton("\u25b6  Start  (F10)")
        self._start_btn.setStyleSheet("""
            QPushButton { background-color: #2ea043; padding: 12px; font-size: 15px; }
            QPushButton:hover { background-color: #3fb950; }
        """)
        self._start_btn.clicked.connect(self.start)
        ctrl.addWidget(self._start_btn)

        self._stop_btn = QPushButton("\u25a0  Stop  (F11)")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet("""
            QPushButton { background-color: #da3633; padding: 12px; font-size: 15px; }
            QPushButton:hover { background-color: #f85149; }
        """)
        self._stop_btn.clicked.connect(self.stop)
        ctrl.addWidget(self._stop_btn)

        root.addLayout(ctrl)

    # --------------------------------------------------------- System tray
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return

        self._tray = QSystemTrayIcon(self._icon_off, self)
        self._tray.setToolTip(APP_NAME + " \u2014 Stopped")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #16213e; color: #e0e0e0; border: 1px solid #0f3460; }
            QMenu::item:selected { background-color: #e94560; }
        """)

        show_action = QAction("Show / Restore", self)
        show_action.triggered.connect(self._restore_from_tray)
        menu.addAction(show_action)
        menu.addSeparator()

        start_action = QAction("Start macros", self)
        start_action.triggered.connect(self.start)
        menu.addAction(start_action)

        stop_action = QAction("Stop macros", self)
        stop_action.triggered.connect(self.stop)
        menu.addAction(stop_action)
        menu.addSeparator()

        self._startup_action = QAction("Start with Windows", self)
        self._startup_action.setCheckable(True)
        self._startup_action.setChecked(is_startup_enabled())
        self._startup_action.triggered.connect(self._toggle_startup)
        menu.addAction(self._startup_action)
        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _toggle_startup(self, checked: bool):
        set_startup_enabled(checked)
        self._startup_action.setChecked(is_startup_enabled())

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized() and self._tray and self._tray.isVisible():
                QTimer.singleShot(0, self.hide)
                self._tray.showMessage(APP_NAME, "Minimized to tray.", QSystemTrayIcon.MessageIcon.Information, 1500)
                event.ignore()
                return
        super().changeEvent(event)

    def closeEvent(self, event):
        if self._tray and self._tray.isVisible():
            self.hide()
            self._tray.showMessage(APP_NAME, "Right-click \u2192 Quit to exit.", QSystemTrayIcon.MessageIcon.Information, 2000)
            event.ignore()
        else:
            self._shutdown()
            event.accept()

    def _quit_app(self):
        self._shutdown()
        QApplication.instance().quit()

    def _shutdown(self):
        log.info("Shutting down...")
        self.stop()
        self._do_save()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if self._tray:
            self._tray.hide()
        release_single_instance()

    def _setup_global_hotkeys(self):
        try:
            keyboard.add_hotkey("F10", self.start, suppress=True)
            keyboard.add_hotkey("F11", self.stop, suppress=True)
        except Exception as e:
            log.error("Failed to register global hotkeys: %s", e)

    # --------------------------------------------------- Card management
    def _add_card(self, data: Optional[Dict] = None):
        if len(self._cards) >= MAX_SHORTCUTS:
            QMessageBox.information(self, APP_NAME, f"Maximum {MAX_SHORTCUTS} shortcuts reached.")
            return
        idx = len(self._cards)
        card = ShortcutCard(index=idx, on_delete=self._delete_card)
        if data:
            card.set_data(data)
        card.data_changed.connect(self._on_card_changed)
        row, col = divmod(idx, 2)
        self._grid.addWidget(card, row, col)
        self._cards.append(card)
        self._schedule_save()

    def _delete_card(self, index: int):
        if not (0 <= index < len(self._cards)):
            return
        card = self._cards.pop(index)
        self._grid.removeWidget(card)
        card.setParent(None)
        card.deleteLater()
        for i, c in enumerate(self._cards):
            c.index = i
            self._grid.removeWidget(c)
            row, col = divmod(i, 2)
            self._grid.addWidget(c, row, col)
        self._on_card_changed()

    def _on_card_changed(self):
        self._schedule_save()
        if self._running:
            self._reload_timer.start()

    # --------------------------------------------------- Settings I/O
    def _schedule_save(self):
        self._save_timer.start()

    def _do_save(self):
        settings = {"shortcuts": [c.get_data() for c in self._cards]}
        try:
            tmp = SETTINGS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            os.replace(tmp, SETTINGS_FILE)
        except Exception as e:
            log.error("Save failed: %s", e)

    def _load_settings(self):
        if not os.path.isfile(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
            global_min = settings.get("min_delay", MIN_DELAY_DEFAULT)
            global_max = settings.get("max_delay", MAX_DELAY_DEFAULT)
            for sd in settings.get("shortcuts", []):
                if "min_delay" not in sd:
                    sd["min_delay"] = global_min
                if "max_delay" not in sd:
                    sd["max_delay"] = global_max
                self._add_card(sd)
            log.info("Settings loaded (%d shortcuts).", len(self._cards))
        except Exception as e:
            log.error("Failed to load settings: %s", e)

    # --------------------------------------------------- Validation
    def _validate(self) -> bool:
        for card in self._cards:
            d = card.get_data()
            if d["enabled"] and d["shortcut"] and d["keys"]:
                if d["min_delay"] < 0 or d["max_delay"] < 0:
                    QMessageBox.warning(self, APP_NAME, f"'{d['name']}': delays cannot be negative.")
                    return False
                if d["min_delay"] > d["max_delay"]:
                    QMessageBox.warning(self, APP_NAME, f"'{d['name']}': min > max delay.")
                    return False
        active = [c for c in self._cards if c.get_data()["enabled"] and c.get_data()["shortcut"] and c.get_data()["keys"]]
        if not active:
            QMessageBox.warning(self, APP_NAME, "At least one active shortcut needed.")
            return False
        return True

    # --------------------------------------------------- Start / Stop
    def start(self):
        if self._running:
            return
        if not self._validate():
            return
        self._do_save()
        self._stop_event.clear()
        self._running = True
        self._register_hotkeys()
        self._update_ui_state()
        log.info("Macros started (%d hotkeys).", len(self._hotkey_ids))
        if self._tray:
            self._tray.showMessage(APP_NAME, "Macros activated!", QSystemTrayIcon.MessageIcon.Information, 1500)

    def stop(self):
        if not self._running:
            return
        self._stop_event.set()
        self._unregister_hotkeys()
        self._running = False
        self._update_ui_state()
        log.info("Macros stopped.")
        if self._tray:
            self._tray.showMessage(APP_NAME, "Macros deactivated.", QSystemTrayIcon.MessageIcon.Warning, 1500)

    def _register_hotkeys(self):
        for card in self._cards:
            d = card.get_data()
            if d["enabled"] and d["shortcut"] and d["keys"]:
                try:
                    mn = max(0, d["min_delay"])
                    mx = max(mn, d["max_delay"])
                    keys_str = d["keys"]
                    hk = keyboard.add_hotkey(
                        d["shortcut"],
                        lambda ks=keys_str, lo=mn, hi=mx: self._fire_keys(ks, lo, hi),
                        suppress=True,
                        trigger_on_release=False,
                    )
                    self._hotkey_ids.append(hk)
                except Exception as e:
                    log.error("Failed to bind '%s': %s", d["shortcut"], e)

    def _unregister_hotkeys(self):
        for hk in self._hotkey_ids:
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        self._hotkey_ids.clear()

    def _live_reload_hotkeys(self):
        if not self._running:
            return
        self._unregister_hotkeys()
        self._register_hotkeys()
        log.info("Hotkeys reloaded (%d active).", len(self._hotkey_ids))

    def _update_ui_state(self):
        if self._running:
            self._status_dot.setStyleSheet("font-size: 28px; color: #2ea043;")
            self._status_dot.setToolTip("Running")
            self._status_label.setText("Running")
            self._status_label.setStyleSheet("font-size: 12px; color: #2ea043;")
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
            self.setWindowIcon(self._icon_on)
            if self._tray:
                self._tray.setIcon(self._icon_on)
                self._tray.setToolTip(APP_NAME + " \u2014 Running")
        else:
            self._status_dot.setStyleSheet("font-size: 28px; color: #e94560;")
            self._status_dot.setToolTip("Stopped")
            self._status_label.setText("Stopped")
            self._status_label.setStyleSheet("font-size: 12px; color: #888;")
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
            self.setWindowIcon(self._icon_off)
            if self._tray:
                self._tray.setIcon(self._icon_off)
                self._tray.setToolTip(APP_NAME + " \u2014 Stopped")

    # --------------------------------------------------- Key firing
    def _fire_keys(self, keys_serialized: str, min_delay: int, max_delay: int):
        if not self._running or self._stop_event.is_set():
            return
        tokens = parse_key_tokens(keys_serialized)
        t = threading.Thread(
            target=self._fire_keys_worker,
            args=(tokens, min_delay, max_delay),
            daemon=True,
        )
        t.start()

    def _fire_keys_worker(self, tokens: list, min_delay: int, max_delay: int):
        try:
            for token in tokens:
                if self._stop_event.is_set():
                    return
                # token is either a single char 'a' or a combo 'ctrl+g'
                keyboard.press_and_release(token)
                if max_delay > 0:
                    delay_ms = random.randint(min_delay, max_delay)
                    time.sleep(delay_ms / 1000.0)
        except Exception as e:
            log.error("Key fire error: %s", e)

    def _on_status_message(self, msg: str):
        self._status_label.setText(msg)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    if not acquire_single_instance():
        app = QApplication(sys.argv)
        QMessageBox.information(None, APP_NAME, "POEasy is already running.\nCheck your system tray.")
        sys.exit(0)

    try:
        app = QApplication(sys.argv)
        app.setFont(QFont("Segoe UI", 10))
        app.setQuitOnLastWindowClosed(False)
        window = POEasyWindow()
        window.show()
        exit_code = app.exec()
    except Exception as e:
        log.critical("Fatal error: %s", e, exc_info=True)
        exit_code = 1
    finally:
        release_single_instance()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
