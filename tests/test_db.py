import sqlite3

import pytest

from sessionly.db import LATEST_VERSION, Database, DatabaseError, open_database


def test_fresh_database_is_migrated(tmp_path):
    db = open_database(tmp_path / "a.db")
    assert db.schema_version == LATEST_VERSION
    tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meetings", "schedules", "schedule_exceptions", "meeting_links", "settings"} <= tables
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    db.close()


def test_reopening_is_idempotent(tmp_path):
    open_database(tmp_path / "a.db").close()
    db = open_database(tmp_path / "a.db")
    assert db.schema_version == LATEST_VERSION
    assert not list(tmp_path.glob("*.bak-*"))  # nothing to migrate, so no backup
    db.close()


def test_transaction_rolls_back_on_error(db):
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            conn.execute("INSERT INTO settings VALUES ('k', '1', 'now')")
            raise RuntimeError("boom")
    assert db.conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0


def test_nested_transaction_joins_outer(db):
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            with db.transaction():
                conn.execute("INSERT INTO settings VALUES ('k', '1', 'now')")
            raise RuntimeError("outer fails")
    assert db.conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0


def test_corrupt_file_gives_clear_error(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a sqlite database" * 100)
    with pytest.raises(DatabaseError, match="could not be opened"):
        Database(bad)


def test_newer_schema_is_refused(tmp_path):
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {LATEST_VERSION + 5}")
    conn.close()
    with pytest.raises(DatabaseError, match="newer version"):
        open_database(path)
