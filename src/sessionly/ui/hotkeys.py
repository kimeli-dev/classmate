"""System-wide hotkeys (Windows ``RegisterHotKey``), so a reply can be played while Zoom or
Meet has the keyboard focus. Elsewhere (or under the offscreen test platform) this is a no-op."""

from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication
from PySide6.QtGui import QGuiApplication

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
_BASE_ID = 0x5E50  # arbitrary, app-private id range

# Keys offered for the single "Reply key". Plain function keys are taken from every app while
# Sessionly runs, so the list favours keys meetings and browsers don't use.
REPLY_KEYS: dict[str, tuple[int, int]] = {
    "F9": (0, 0x78),
    "F8": (0, 0x77),
    "F10": (0, 0x79),
    "Pause": (0, 0x13),
    "Scroll Lock": (0, 0x91),
    "Ctrl+Alt+Space": (MOD_CONTROL | MOD_ALT, 0x20),
    "Ctrl+Shift+Space": (MOD_CONTROL | MOD_SHIFT, 0x20),
}
DEFAULT_REPLY_KEY = "F9"


def numbered_key(n: int) -> tuple[int, int]:
    """Ctrl+Alt+<n> for reply number n (1-9)."""
    return MOD_CONTROL | MOD_ALT, 0x30 + n


def supported() -> bool:
    return sys.platform == "win32" and QGuiApplication.platformName() == "windows"


class GlobalHotkeys(QAbstractNativeEventFilter):
    """Registers ``{key_id: (name, (modifiers, virtual_key))}``; ``on_press(key_id)`` runs on the UI thread."""

    def __init__(self, on_press: Callable[[int], None]) -> None:
        super().__init__()
        self.on_press = on_press
        self.registered: list[int] = []
        self.failed: list[str] = []   # names of keys another app already uses
        self._installed = False

    def set_keys(self, keys: dict[int, tuple[str, tuple[int, int]]]) -> None:
        self.clear()
        if not supported():
            return
        if not self._installed:
            QCoreApplication.instance().installNativeEventFilter(self)
            self._installed = True
        user32 = ctypes.windll.user32
        for key_id, (name, (mods, vk)) in keys.items():
            if user32.RegisterHotKey(None, _BASE_ID + key_id, mods | MOD_NOREPEAT, vk):
                self.registered.append(key_id)
            else:
                self.failed.append(name)
        if self.failed:
            log.warning("Hotkeys already used by another app: %s", ", ".join(self.failed))

    def clear(self) -> None:
        if supported():
            for key_id in self.registered:
                ctypes.windll.user32.UnregisterHotKey(None, _BASE_ID + key_id)
        self.registered, self.failed = [], []

    def nativeEventFilter(self, event_type, message):
        # Hotkeys registered without a window arrive as thread messages ("dispatcher" MSGs).
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                key_id = int(msg.wParam) - _BASE_ID
                if key_id in self.registered:
                    self.on_press(key_id)
                    return True, 0
        return False, 0
