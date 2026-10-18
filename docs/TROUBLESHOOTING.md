# Troubleshooting

Logs: `%LOCALAPPDATA%\Sessionly\logs\sessionly.log` (Settings → Log folder → Open).

## Installation

**`pip install` fails with `OSError: [Errno 2] No such file or directory ... PySide6\qml\...`**
The path is longer than Windows' 260-character limit. Create the virtual environment at a short
path, e.g. `C:\Users\<you>\.venvs\sessionly` (see the README), or turn on long-path support as administrator.

**`ModuleNotFoundError: No module named 'sessionly'`**
Run `python -m pip install -e .` from the project folder, using the venv's `python.exe`.

## Startup

**"Sessionly cannot start — the database could not be opened"**
The database file is damaged or isn't a Sessionly database.
1. Close Sessionly.
2. In `%LOCALAPPDATA%\Sessionly`, rename `sessionly.db` to `sessionly.db.broken`.
3. If a `sessionly.db.bak-v*` file exists, copy it to `sessionly.db`. Otherwise Sessionly starts empty.

**"This database was created by a newer version of Sessionly"**
Update Sessionly. Don't downgrade with an existing database.

**The setup wizard appears again**
It appears until you finish it once. If you cancel, it shows again on the next start. That's harmless.

## Schedule

**"… is a Tuesday, but this session is on Mondays"**
A cancellation or move must use a date when that weekly time actually happens.

**"That session already has a change recorded"**
Remove the existing change (Meetings → Schedule changes → Remove change), then add the new one.

**A session doesn't appear on the dashboard**
Check that its weekly entry is *Active*, that it isn't cancelled for that date, and that it
falls in the month you're looking at.

## Meeting links

**The Save button is greyed out**
The link failed a check. The red message says why: http instead of https, spaces, a missing address, or similar.

**Orange warning "not a standard join link"**
The link may still work, for example a registration page. Save it if it came from your host.

**The meeting wouldn't open**
Use **Report a problem**. If the host hadn't started, you were in a waiting room, or it asked you
to sign in, the link is kept. Only "invalid link" or "not sure" mark it as needing replacement.

**Sessionly didn't remind me / didn't open the session**
Check that Sessionly is running (hidden icons ^), automation isn't paused, the meeting allows automatic actions,
and - for opening - "Open meeting links automatically" is on in Settings. Nothing runs while the laptop sleeps.

## Moving from Classmate

**"Classmate is still running"** when starting Sessionly
Quit Classmate from the hidden icons, then start Sessionly. Your data folder is moved from
`%LOCALAPPDATA%\Classmate` to `%LOCALAPPDATA%\Sessionly` once, automatically.
