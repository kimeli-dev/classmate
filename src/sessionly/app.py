"""Application entry point: ``python -m sessionly [--background]`` or the ``sessionly`` launcher.

``--background`` starts straight into the tray (used when starting with Windows).
Only one copy runs per Windows user; launching again brings the existing window forward.
"""

from __future__ import annotations

import getpass
import logging
import os
import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from sessionly import APP_NAME, __version__
from sessionly.config import default_data_dir, load_config
from sessionly.legacy import LEGACY_DB, LEGACY_NAME, LegacyAppRunning, legacy_data_dir, migrate_data_dir
from sessionly.services import startup
from sessionly.context import AppContext
from sessionly.db import DatabaseError, open_database
from sessionly.logging_setup import setup_logging
from sessionly.services.settings import SETUP_COMPLETED

log = logging.getLogger(__name__)


def _server_name() -> str:
    return f"{APP_NAME}-{getpass.getuser()}"


def _running(server_name: str, message: bytes = b"") -> bool:
    """True if an app instance is listening on this name (optionally sending it a message)."""
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(500):
        if message:
            socket.write(message)
            socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return True
    return False


def _signal_running_instance() -> bool:
    """True if another copy is running (and it has been asked to show itself)."""
    return _running(_server_name(), b"show")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    background = "--background" in argv
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    if _signal_running_instance():
        return 0

    from sessionly.ui.icon import app_icon
    from sessionly.ui.theme import apply_theme
    apply_theme(app)
    app.setWindowIcon(app_icon())

    # One-time move from the old name (Classmate). The old app must not hold the files.
    moved = False
    if not os.environ.get("SESSIONLY_DATA_DIR"):
        new_dir = default_data_dir()
        if _running(f"{LEGACY_NAME}-{getpass.getuser()}") and (legacy_data_dir(new_dir) / LEGACY_DB).exists() \
                and not (new_dir / "sessionly.db").exists():
            QMessageBox.information(None, APP_NAME,
                                    f"{LEGACY_NAME} (this app's old name) is still running. Quit it from the "
                                    "hidden icons (^) next to the clock, then start Sessionly again - your "
                                    "meetings, notes and snapshots will be moved over.")
            return 0
        try:
            moved = migrate_data_dir(new_dir, legacy_data_dir(new_dir))
        except LegacyAppRunning:
            QMessageBox.warning(None, APP_NAME, f"Your {LEGACY_NAME} data is in use. Close {LEGACY_NAME} and "
                                                "start Sessionly again.")
            return 1

    config = load_config()
    setup_logging(config.log_dir, config.log_level)
    log.info("Starting %s %s%s", APP_NAME, __version__, " (background)" if background else "")
    if moved:
        log.info("Moved data over from %s", LEGACY_NAME)
    if startup.migrate_legacy():
        log.info("Moved 'start with Windows' over from %s", LEGACY_NAME)

    try:
        db = open_database(config.db_path)
    except DatabaseError as exc:
        log.error("Database unavailable: %s", exc)
        QMessageBox.critical(None, f"{APP_NAME} cannot start", str(exc))
        return 1

    ctx = AppContext.create(config, db)

    from sessionly.ui.main_window import MainWindow
    from sessionly.ui.setup_wizard import SetupWizard
    from sessionly.ui.tray import TrayController

    window = MainWindow(ctx)
    tray = TrayController(ctx, window)

    server = QLocalServer()
    QLocalServer.removeServer(_server_name())  # clear a stale name left by a crash
    if server.listen(_server_name()):
        server.newConnection.connect(lambda: (server.nextPendingConnection(), window.bring_to_front()))
    else:
        log.warning("Single-instance server unavailable: %s", server.errorString())

    first_run = not ctx.settings.get(SETUP_COMPLETED, False)
    if not background or first_run or not tray.available:
        window.show()
    if first_run:
        wizard = SetupWizard(ctx, window)
        if wizard.exec():
            window.meetings.reload(wizard.created_meeting_id)
            window.dashboard.refresh()

    tray.start()
    tray.update_state()
    # Without a tray, closing the window must still end the app.
    if not tray.available:
        app.setQuitOnLastWindowClosed(True)

    code = app.exec()
    db.close()
    log.info("Exited with code %s", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
