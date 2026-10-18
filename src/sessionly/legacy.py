"""One-time move from the app's previous name (Classmate) to Sessionly.

Moves the data folder (database, logs, config) and renames the database file,
so nothing the user saved is lost. Leftover speech-recognition models from an abandoned
feature are removed. Safe to call on every start: it does nothing once Sessionly has data.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

LEGACY_NAME = "Classmate"
LEGACY_DB = "classmate.db"
NEW_DB = "sessionly.db"


class LegacyAppRunning(RuntimeError):
    pass


def legacy_data_dir(new_dir: Path) -> Path:
    return new_dir.with_name(LEGACY_NAME)


def migrate_data_dir(new_dir: Path, legacy_dir: Path) -> bool:
    """Returns True if data was moved. Raises LegacyAppRunning if the old app holds the files."""
    if (new_dir / NEW_DB).exists() or not (legacy_dir / LEGACY_DB).exists():
        return False
    if new_dir.exists() and any(new_dir.iterdir()):
        log.warning("Both %s and %s exist; leaving the old folder alone", legacy_dir.name, new_dir.name)
        return False
    try:
        if new_dir.exists():
            new_dir.rmdir()  # empty - created by an earlier start
        legacy_dir.rename(new_dir)
    except PermissionError as exc:
        raise LegacyAppRunning(str(exc)) from exc
    for suffix in ("", "-wal", "-shm"):  # SQLite finds the WAL by file name, so rename all three
        old = new_dir / f"{LEGACY_DB}{suffix}"
        if old.exists():
            old.rename(new_dir / f"{NEW_DB}{suffix}")
    for bak in new_dir.glob(f"{LEGACY_DB}.bak-*"):
        bak.rename(new_dir / bak.name.replace(LEGACY_DB, NEW_DB))
    shutil.rmtree(new_dir / "models", ignore_errors=True)  # unused speech models (~220 MB)
    log.info("Moved data from %s to %s", legacy_dir, new_dir)
    return True
