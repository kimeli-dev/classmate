# Supported and unsupported capabilities

Status as of Sessionly 0.5.0. Nothing is listed as supported unless it is implemented and covered by
automated tests or the manual checklist.

## Meetings and schedule

| Capability | Notes |
|---|---|
| Meeting create / edit / delete | A meeting is anything recurring: a class, team sync, training, webinar series or study group. Deleting removes its schedule, changes and links (with confirmation). Short codes are optional and unique, ignoring case. |
| Weekly schedule | Tick any days (Mo–Su) or use a quick pick: Weekdays, Mon & Wed, Tue & Thu, Mon/Wed/Fri, Every day. Each ticked day is one weekly time with the same start, length (1–720 min) and preparation time (0–120 min). Editing changes one day at a time. |
| Cancelled, moved and extra sessions | One change per regular session per date. The date must fall on that weekly time's day. |
| Overlap detection | Warns while you edit and lists overlaps on the dashboard, including sessions that cross Sunday midnight. Nothing is resolved automatically. |

## Links and joining

| Capability | Notes |
|---|---|
| Meeting-link storage and history | One current link per meeting, enforced by the database. Old links are kept and can be restored. |
| Link format validation | https only. Recognises Zoom (`*.zoom.us`, `zoomgov.com`), Google Meet and Teams. Rejects look-alike domains, embedded credentials and unusual ports. **A valid format does not mean the meeting exists.** |
| Wrong-meeting protection | If the link is already the current link for another meeting, you're asked to confirm. |
| Problem classification | Waiting room, sign-in prompt, no internet, or a host who hasn't started do **not** mark the link as broken. |
| Opening meetings | Zoom opens in the Zoom app with the meeting ID, saved passcode and your display name. Meet can open with the Google account you allow. Otherwise the default browser is used. |
| Join Zoom with mic off | This comes from Zoom's own settings, not the link (Zoom has no supported link option for it). Settings walks you through the four Zoom options once. |

## Background

| Capability | Notes |
|---|---|
| Runs in the background | Closing the window keeps Sessionly in the hidden icons (^). Quit from the tray menu. Only one copy runs; launching again brings the window forward. |
| Start with Windows | Opt-in under Settings. Uses the per-user `Run` registry key, so no admin rights are needed, and you can remove it in Task Manager → Startup apps. |
| Reminders | Quiet Windows notification at preparation time, once per session. The database prevents duplicates, even across restarts. |
| Automatic link opening | Opt-in. Opens the link at preparation time, after a quick internet check. It isn't done for failed links, for meetings with automation turned off, or when it's more than 10 minutes after the start. |
| Join indicator | Tray badge plus the dashboard's Live session card: *Starts soon*, *Link opened – not confirmed*, *Joined – you confirmed*, *Couldn't join*. **"Joined" is only ever set by you.** |
| Missed-session report | Sessions that passed while the laptop slept or Sessionly was off are reported when it starts again. |
| Pause all automation | Settings or the tray menu. |

## Voice replies

| Capability | Notes |
|---|---|
| Record replies in your own voice | Up to 9 short phrases (0.3–15 s), e.g. "Present", "Yes, I'm here", "Sorry, my mic was off". Each recording has its silence trimmed, gets short fades and is levelled to the same peak, so every reply sounds alike. Re-record, rename, reorder or delete them under Settings → Voice replies. |
| Reply key | One system-wide key (**F9** by default; F8, F10, Pause, Scroll Lock, Ctrl+Alt+Space, Ctrl+Shift+Space or Off) says your chosen reply, or reply 1 if you haven't chosen. Pressing it again while the reply plays stops it. It works while Zoom or Meet is in front. |
| One-tap playback | The tray icon's **Say…** menu, the Voice replies window, or system-wide hotkeys **Ctrl+Alt+1–9** (these work while Zoom or Meet is in front). Starting a reply stops the one playing. **A reply only ever plays when you press it.** Sessionly doesn't listen to the meeting or react to your name. |
| Into the meeting | Through a virtual audio cable (e.g. VB-CABLE): Sessionly plays into *CABLE Input*, Zoom/Meet use *CABLE Output* as the microphone, and Windows' *Listen to this device* passes your live mic into the cable. A detected cable is pre-selected. You can also hear replies on your speakers. |

**Limits:** without a virtual cable, replies play on your speakers only and Sessionly says so. Hotkeys another
app already uses can't be registered and are listed in the Voice replies window. Your meeting's own mute still
applies: if you're muted in Zoom, nobody hears the reply.

## Not implemented

| Capability | What it depends on |
|---|---|
| Detecting that you were admitted to a meeting | Sessionly can't look inside Zoom or the browser. Detection would need official Zoom/Meet APIs. Until then you confirm with "I'm in". |
| Session summaries from slides, notes or transcripts | An AI provider (optional, with explicit consent) or local processing. |
| E-mail or calendar link discovery | OAuth consent for each source. |

## Will not be supported

- Answering roll calls or attendance automatically, or joining on behalf of someone who isn't taking part
- Bypassing waiting rooms, host approval, CAPTCHAs, sign-in or meeting passcodes
- Reading private group chats or any messages without authorization
- Secret recording of meetings
- Claiming a join, response or summary succeeded without evidence

## Known limitations

- Times are local wall-clock times. A session at 10:00 stays at 10:00 if you travel to another time zone.
- Nothing runs while the app is closed, or the laptop is asleep or shut down. Sessions that passed meanwhile are reported afterwards.
- The dashboard only refreshes while the window is open (every 30 seconds, or press F5).
