# Roadmap, packaging and cost estimate

## Phases

| Phase | Scope | Status |
|---|---|---|
| 1 Core | Meetings, weekly schedule, schedule changes, overlaps, meeting links, dashboard, setup wizard, logging | **Done (0.1.0)** |
| 2 Background | Tray icon, start at log-on (per-user Run key), Windows notifications, `sessions` table with unique (meeting, start), missed-event report, pause-all switch, opt-in link opening, join indicator | **Done (0.2.0)** |
| 3 Meeting workflow | Zoom app launch with passcode, Meet with the allowed Google account, join-with-mic-off guide | **Done (0.3.0)** |
| Rename | Classmate → Sessionly, general vocabulary, any-day scheduling, automatic data move | **Done (0.4.0)** |
| Simplify | Learn page (AI companion, notes, slide snapshots) removed; glass sidebar | **Done (0.5.0)** |
| 4 Summaries | Import slides (PDF/PPTX), notes and transcripts; a provider interface (cloud API or local); one-page summaries that separate session content from AI explanation; search and export | Planned |
| 7 Integrations | E-mail or calendar link discovery (OAuth), shared announcements, optional cloud sync | Planned |

### Technical uncertainties to resolve before each phase
- **Phase 2:** Windows toast notifications from Python need an extra package (e.g. `windows-toasts`). Its licence and Windows 11 behaviour must be checked.
- **Phase 3:** Detecting "joined" or "waiting room" through a normal browser isn't reliable. Zoom and Meet APIs need app registration and may need institutional approval.

## Packaging as a Windows executable (not yet tested)

PyInstaller is the planned tool. These steps haven't been run yet. Verify them before the first release:

```powershell
python -m pip install pyinstaller
pyinstaller --name Sessionly --windowed --noconfirm --paths src src\sessionly\__main__.py
# Output: dist\Sessionly\Sessionly.exe. Ship the whole dist\Sessionly folder, or wrap it with Inno Setup.
```
Build in a short path (see the long-path note in the README). Add `--icon assets\sessionly.ico` for the app icon.

## Recurring cost estimate

| Item | Phase | Estimate |
|---|---|---|
| Scheduling, reminders, joining (local only) | 1–3 | **$0** |
| Cloud AI summaries | 4 | About 10 sessions/week × ~15k input tokens + ~1.5k output tokens. That's typically **under US$2–5/month** on a mid-tier model. Check current provider pricing, and set a monthly cap. |
| Local summarization | 4 | $0, but needs a capable laptop (8–16 GB RAM) and gives lower quality |
| Cloud hosting (optional) | 7 | $0–10/month (free tiers, then a small VM or serverless) |

## Cloud migration path

The services layer already separates storage, scheduling and integrations from the UI:
1. Swap `Database` for a repository backed by a hosted Postgres or Firestore. The service interfaces stay the same.
2. Move the Phase 2 scheduler logic into a cloud function that sends push notifications, so reminders arrive even when the laptop is off.
3. Keep meeting launching on the laptop. Those can't run in the cloud without the user's device.
