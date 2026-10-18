# Sessionly

A Windows desktop app for anything you attend online every week: classes, team meetings,
trainings, webinars, study groups. It keeps each meeting's schedule and link in one place,
reminds you before it starts and opens it for you if you want.

**Current version: 0.4.0.** Sessionly was previously called *Classmate*; existing data is moved over
automatically the first time Sessionly starts.

## What it does

- **Meetings:** name, optional short code (e.g. `SWE 320` or `TEAM`), host, the display name you use
  there, notes.
- **Weekly schedule:** tick any days (Mo–Su) or use a quick pick (Weekdays, Mon & Wed, Tue & Thu,
  Mon/Wed/Fri, Every day). Each day gets the same start time, length and preparation time. Single
  sessions can be cancelled, moved or added.
- **Overlap warnings:** shown when you save, and on the dashboard. Sessionly never picks one for you.
- **Meeting links:** format check (Zoom, Google Meet, Teams), history, replacement, and problem reports
  that tell a broken link apart from "the host hasn't started yet". Zoom opens in the Zoom app with the
  saved passcode; Meet can open with the Google account you allow.
- **Dashboard:** a month calendar, a **Live session** card, your week at a glance, and a "needs your
  attention" list.
- **Runs in the background** from the hidden-icons tray, and can start with Windows (opt-in). You get
  reminders at preparation time, and links can open automatically (opt-in). The tray badge separates
  *link opened* from *joined (you confirmed)*.
- **Join with your mic off:** a one-time guide to the Zoom settings that make it skip the preview.

See [docs/CAPABILITIES.md](docs/CAPABILITIES.md) for limits.

## Requirements

- Windows 10 or 11, 64-bit (developed and tested on Windows 11 Pro build 26200)
- Python 3.11 or newer (tested with 3.13.14)

## Installation

> **Important — long paths.** PySide6 contains very deeply nested files. If the project lives
> in a long folder path, installing it into a `.venv` inside the project fails with
> `No such file or directory` unless Windows long-path support is turned on. The simplest fix is to
> put the virtual environment at a short path, as shown below.

```powershell
# 1. Create a virtual environment at a short path
python -m venv C:\Users\<you>\.venvs\sessionly

# 2. From the project folder, install Sessionly and the test tools
C:\Users\<you>\.venvs\sessionly\Scripts\python.exe -m pip install -r requirements-dev.txt
C:\Users\<you>\.venvs\sessionly\Scripts\python.exe -m pip install -e .

# 3. Run it
C:\Users\<you>\.venvs\sessionly\Scripts\python.exe -m sessionly
```

Step 2 also creates a `sessionly.exe` launcher in the venv's `Scripts` folder.

Alternatively, enable long paths (needs administrator rights) and use a normal `.venv`:
`Set-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem LongPathsEnabled 1`

## Running the tests

```powershell
C:\Users\<you>\.venvs\sessionly\Scripts\python.exe -m pytest
```

The UI tests run offscreen, so no windows appear. The manual checks are in
[docs/MANUAL_TEST_CHECKLIST.md](docs/MANUAL_TEST_CHECKLIST.md).

## Using Sessionly

1. On first launch, the setup wizard asks for your display name, an optional first meeting with its
   days and time, and an optional meeting link.
2. **Meetings** page: select a meeting to see its link, weekly schedule and schedule changes.
   - *Paste / Replace link* checks the link as you type. If another meeting already uses the same
     link, you're asked to confirm.
   - *It worked* confirms a link took you to the meeting.
   - *Report a problem* records what happened. Only "invalid link" or "not sure" mark the link as
     needing replacement. Waiting rooms, sign-in prompts, no internet, or a host who hasn't started
     yet keep the link.
3. **Dashboard**: the calendar, the session that's on now, and anything that needs attention. Press
   Enter on a day or a row to jump to the meeting.

Keyboard: `Ctrl+1…3` switch pages, `Ctrl+N` new meeting, `F5` refresh. Underlined letters are `Alt` shortcuts.

## Where data is stored

`%LOCALAPPDATA%\Sessionly\` holds `sessionly.db` (SQLite), `logs\` and an optional
`config.toml` (see [config.example.toml](config.example.toml)). Before any schema upgrade the database
is copied to `sessionly.db.bak-v<N>`.

## Project layout

```
src/sessionly/
  app.py              entry point: data move from Classmate, logging, database, window, tray
  legacy.py           one-time move of the old Classmate data folder
  config.py           data folder and optional config.toml
  db.py               SQLite connection, transactions, versioned migrations, integrity check
  models.py           dataclasses and enums shared by services and UI
  logging_setup.py    rotating log file with URL/e-mail/secret redaction
  context.py          wires the services together for the UI
  services/           business logic; the only place with SQL
    meetings.py  schedules.py  sessions.py  links.py  link_validation.py  meeting_launch.py
    automation.py  settings.py  startup.py
  ui/                 PySide6 widgets: main_window, sidebar (glass navigation), dashboard,
                      meetings_page, dialogs, settings_page, setup_wizard, tray, theme, icon
tests/                pytest unit, integration and offscreen UI tests
docs/                 capabilities, security & privacy, troubleshooting, manual tests, roadmap
```

## Documentation

- [Capabilities and limitations](docs/CAPABILITIES.md)
- [Security and privacy](docs/SECURITY_PRIVACY.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Manual test checklist](docs/MANUAL_TEST_CHECKLIST.md)
- [Roadmap, packaging and cost estimate](docs/ROADMAP.md)
# classmate
