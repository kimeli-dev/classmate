# Security and privacy

## What Sessionly stores

| Data | Where | Why |
|---|---|---|
| Meetings, schedule, schedule changes | `%LOCALAPPDATA%\Sessionly\sessionly.db` | Core feature |
| Meeting links (they may include passcodes, e.g. Zoom `pwd=`) | Same database | To open the right meeting later |
| Zoom passcode your host shared (optional, per link) | Same database, next to its link | Handed to the Zoom app when joining; copied to the clipboard as a fallback |
| Google account e-mail for Meet, and whether you allowed it | Same database (`settings` table) | Added to Meet links as `authuser=` so Meet opens as you. Sessionly never sees or stores your Google password. |
| Display name | Same database (`settings` table) | Shown on the dashboard. Passed to Zoom as your name when joining. |
| Voice replies you recorded | `%LOCALAPPDATA%\Sessionly\voice\` as WAV files; names in the database | Played into a meeting only when you press one. Never uploaded. Deleting a reply deletes its file. |
| Logs | `%LOCALAPPDATA%\Sessionly\logs\` (5 × 1 MB rotating) | Diagnosis |

**What leaves your computer:** nothing. Sessionly makes no uploads; meeting links open in your browser
or the Zoom app only when you or your automation settings open them.

## Protections

- **Logs are redacted.** Every URL becomes `<url:host>`. E-mail addresses become `<email>`.
  `pwd=`, `passcode=`, `password=`, `token=`, `api_key=` and `secret=` values become `<redacted>`.
  Tests check that a pasted Zoom passcode never reaches the log file.
- **No secrets in config files.** `config.toml` only holds the data folder and log level.
  Later API keys will go in Windows Credential Manager (via `keyring`), never in the database, config or source code.
- **Link checks reject risky patterns**: http, `user:password@host` links, unusual ports, and
  look-alike domains such as `zoom.us.example.com`. Look-alikes are labelled "Other" with a warning.
- **Per-user storage.** `%LOCALAPPDATA%` can only be read by your Windows account (and administrators).
  The database is **not encrypted**. Anyone who can sign in as you can read it. Turn on BitLocker
  or device encryption to protect a lost laptop.

## Your controls

- Delete a meeting to remove its schedule and every saved link.
- Delete individual old links under **Meeting link → History**.
- To remove everything, close Sessionly and delete `%LOCALAPPDATA%\Sessionly`.

## Commitments

- Sessionly doesn't record or listen to meetings. Nothing is recorded secretly, and platform or organisation rules always come first.
  The microphone is used only while you record a voice reply in the Voice replies window, and a recorded
  reply plays only when you press it - never in response to anything said in the meeting.
- Sessionly never bypasses waiting rooms, sign-in, passcodes or host approval, and never answers roll calls or attendance for you.
  Entering a passcode the host gave you, or opening Meet with the account you allowed, is not a bypass:
  Zoom and Google still check your account, and the host still admits you.

## Reporting a problem

Don't attach your database or unredacted screenshots of links to bug reports. The log file is safe to share.
