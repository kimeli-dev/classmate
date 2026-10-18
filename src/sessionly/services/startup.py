"""Start Sessionly with Windows (only with the user's consent).

Uses the per-user ``Run`` registry key: no administrator rights, and it's visible and
removable in Task Manager -> Startup apps.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Sessionly"
LEGACY_VALUE_NAME = "Classmate"  # the app's old name - its entry would launch a module that no longer exists


def launch_command() -> str:
    if getattr(sys, "frozen", False):  # packaged .exe
        return f'"{sys.executable}" --background'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" -m sessionly --background'


def _winreg():
    import winreg  # Windows only
    return winreg


def is_enabled(key_path: str = RUN_KEY) -> bool:
    try:
        winreg = _winreg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except (OSError, ImportError):
        return False


def set_enabled(enabled: bool, key_path: str = RUN_KEY) -> None:
    winreg = _winreg()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def migrate_legacy(key_path: str = RUN_KEY) -> bool:
    """If the user had 'start with Windows' on under the old name, keep it on under the new one."""
    try:
        winreg = _winreg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
            winreg.QueryValueEx(key, LEGACY_VALUE_NAME)
            winreg.DeleteValue(key, LEGACY_VALUE_NAME)
    except (OSError, ImportError):
        return False
    set_enabled(True, key_path)
    return True
