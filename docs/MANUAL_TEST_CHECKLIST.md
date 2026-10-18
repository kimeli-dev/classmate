# Manual test checklist

Run on the target laptop with a fresh data folder:
`$env:SESSIONLY_DATA_DIR="$env:TEMP\sessionly-test"; python -m sessionly`

Record: date, Windows build, Python version, tester. Tick each item only after doing it.

## Installation
- [ ] Clean install using the README steps works without errors
- [ ] `python -m pytest` passes (record the count)
- [ ] `sessionly.exe` from the venv's `Scripts` folder starts the app

## First run
- [ ] The setup wizard appears. Entering a name, a meeting, a weekly time and a Meet link creates them all.
- [ ] Ticking *Skip* on the meeting page finishes the wizard with no meeting
- [ ] An invalid link in the wizard blocks *Finish* until it's fixed or cleared
- [ ] The wizard doesn't appear on the second launch

## Meetings
- [ ] Add a meeting with only a name. Then add one with a duplicate code: you get a clear message, and your input stays in the dialog.
- [ ] Edit a meeting. The changes show in the list and the header.
- [ ] Delete a meeting after confirming. Its links and schedule are gone.
- [ ] A meeting name containing `<b>` shows as literal text

## Schedule
- [ ] Add a meeting with Quick pick → Weekdays. Five weekly times appear, Monday to Friday.
- [ ] Untick every day and save. You're asked to tick at least one day.
- [ ] Add an overlapping slot for another meeting. You're warned before saving, and the dashboard lists the overlap.
- [ ] Cancel next week's session. It appears struck through on the dashboard with the note.
- [ ] Move a session. It disappears from the old time and appears at the new one.
- [ ] Add an extra session. It appears on its date.
- [ ] A cancellation on the wrong weekday is refused with an explanation

## Meeting links
- [ ] Paste `http://…` and the Save button stays disabled. Paste `https://meet.google.com/abc-defg-hij` and it's recognised as Google Meet.
- [ ] Paste the same link for a second meeting. You're asked to confirm.
- [ ] **Open in browser** opens the default browser
- [ ] **It worked** sets the status to "Worked last time" with a timestamp
- [ ] Report "host had not started". The status is unchanged and the advice says the link was kept.
- [ ] Report "invalid link". The status becomes "Needs replacement", you're offered a replacement, and the dashboard lists it.
- [ ] Replace the link. The old one shows in History, and *Make current* restores it.

## Sidebar
- [ ] Clicking each page glides the lime glass pill and accent bar to it; hovering shows a frosted highlight.
- [ ] Tabbing to a sidebar item shows a focus ring; Enter/Space opens the page.

## Dashboard and accessibility
- [ ] Today and the next 7 days show the right sessions, and the status changes to *Starting soon* or *In progress* at the right times
- [ ] Enter or double-click on a row opens the meeting
- [ ] The whole app can be used with the keyboard only (Tab, Alt+letter, Ctrl+1…3, Ctrl+N, F5)
- [ ] Readable at 150% Windows display scaling and in dark mode

## Moving from Classmate
- [ ] With Classmate data in `%LOCALAPPDATA%\Classmate` and Classmate still running, starting Sessionly asks you to quit Classmate first.
- [ ] After quitting it, Sessionly starts with all meetings, schedules and links; the old folder is gone.

## Voice replies (needs a microphone; the last three need VB-CABLE)
- [ ] Settings → Voice replies → Record new: the level bar moves while you speak, Stop shows the trimmed length, Play back sounds right, Save lists it with Ctrl+Alt+1.
- [ ] Record a very quiet and a loud reply: both play back at the same loudness.
- [ ] Record nothing (stay silent): you're told nothing was heard and Save stays disabled.
- [ ] With no cable chosen, the tray's Say… → reply plays on your speakers and you're told it isn't connected to meetings.
- [ ] With VB-CABLE installed, the window pre-selects *CABLE Input*. With Zoom's microphone set to *CABLE Output*, Zoom's *Test mic* plays the reply back.
- [ ] With Zoom in front, F9 says the reply chosen under *Reply key → It says*. Pressing F9 again while it plays stops it. Changing the key to Pause makes F9 do nothing in Sessionly again.
- [ ] With Zoom in front, Ctrl+Alt+1 plays reply 1 into the meeting; pressing Ctrl+Alt+2 straight after stops reply 1 and plays reply 2.
- [ ] Search `sessionly.log` for a reply's name: only its id and length appear.

## Reliability and privacy
- [ ] Kill the app in Task Manager while it's open, then restart. No data is lost and no errors appear.
- [ ] Turn off Wi-Fi. Everything still works (Sessionly needs no network except to open meetings).
- [ ] Search `sessionly.log` for `meet.google.com/` and `pwd=`. There are no matches.
- [ ] Replace `sessionly.db` with a text file and start. You get a clear error with recovery steps.
