"""Moving a user's data over from the app's old name (Classmate)."""

import pytest

from sessionly.db import LATEST_VERSION, open_database
from sessionly.legacy import LegacyAppRunning, migrate_data_dir
from sessionly.services import startup


def make_legacy(tmp_path):
    old = tmp_path / "Classmate"
    (old / "models" / "whisper").mkdir(parents=True)
    (old / "models" / "whisper" / "model.bin").write_bytes(b"x" * 100)
    (old / "slides" / "1").mkdir(parents=True)
    (old / "slides" / "1" / "a.jpg").write_bytes(b"jpg")
    (old / "classmate.db").write_bytes(b"")
    (old / "classmate.db.bak-v4").write_bytes(b"")
    return old


def test_moves_data_renames_db_and_drops_models(tmp_path):
    old = make_legacy(tmp_path)
    new = tmp_path / "Sessionly"
    new.mkdir()  # an empty folder from an earlier start must not block the move
    assert migrate_data_dir(new, old)
    assert not old.exists()
    assert (new / "sessionly.db").exists() and (new / "sessionly.db.bak-v4").exists()
    assert (new / "slides" / "1" / "a.jpg").read_bytes() == b"jpg"
    assert not (new / "models").exists()


def test_does_nothing_when_already_moved(tmp_path):
    old = make_legacy(tmp_path)
    new = tmp_path / "Sessionly"
    new.mkdir()
    (new / "sessionly.db").write_bytes(b"")
    assert not migrate_data_dir(new, old)
    assert old.exists()


def test_does_nothing_without_legacy_data(tmp_path):
    assert not migrate_data_dir(tmp_path / "Sessionly", tmp_path / "Classmate")


def test_never_merges_into_a_folder_with_data(tmp_path):
    old = make_legacy(tmp_path)
    new = tmp_path / "Sessionly"
    new.mkdir()
    (new / "notes.txt").write_text("mine")
    assert not migrate_data_dir(new, old)
    assert (old / "classmate.db").exists() and (new / "notes.txt").exists()


def test_reports_locked_folder(tmp_path, monkeypatch):
    old = make_legacy(tmp_path)

    def locked(self, target):
        raise PermissionError("in use")
    monkeypatch.setattr(type(old), "rename", locked)
    with pytest.raises(LegacyAppRunning):
        migrate_data_dir(tmp_path / "Sessionly", old)


def test_old_schema_database_upgrades_after_move(tmp_path):
    """A real v5 (Classmate) database keeps its data through the move and the v6 rename."""
    import sqlite3
    from sessionly.db import MIGRATIONS
    old = tmp_path / "Classmate"
    old.mkdir()
    conn = sqlite3.connect(old / "classmate.db")
    for version, sql in MIGRATIONS[:5]:
        conn.executescript(sql)
    conn.execute("PRAGMA user_version = 5")
    conn.execute("INSERT INTO courses (name, course_code, lecturer_name, created_at, updated_at) "
                 "VALUES ('Software Testing', 'SWE 320', 'Dr. A', 'x', 'x')")
    conn.execute("INSERT INTO schedules (course_id, day_of_week, start_time, duration_minutes, created_at, updated_at) "
                 "VALUES (1, 0, '10:00', 60, 'x', 'x')")
    conn.commit()
    conn.close()

    new = tmp_path / "Sessionly"
    assert migrate_data_dir(new, old)
    db = open_database(new / "sessionly.db")
    assert db.schema_version == LATEST_VERSION
    row = db.conn.execute("SELECT name, short_code, host_name FROM meetings").fetchone()
    assert tuple(row) == ("Software Testing", "SWE 320", "Dr. A")
    assert db.conn.execute("SELECT meeting_id FROM schedules").fetchone()[0] == 1
    assert list((new).glob("sessionly.db.bak-v5"))  # backed up before the rename
    db.close()


def test_start_with_windows_moves_to_new_name():
    winreg = pytest.importorskip("winreg")
    key_path = r"Software\SessionlyTest\Run"
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, startup.LEGACY_VALUE_NAME, 0, winreg.REG_SZ, "old command")
        assert startup.migrate_legacy(key_path)
        assert startup.is_enabled(key_path)
        assert not startup.migrate_legacy(key_path)  # only once
    finally:
        for sub in (key_path, r"Software\SessionlyTest"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass
