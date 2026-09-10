# Leave-by demo: capture the `travel` card firing on a real event

## Status: 🟢 `check_travel()` fired live on the household NUC for the first time
2026-09-10 (`Leave by 10:18 AM for test`, real synced test event). Deployed and verified.
Just needs someone to record ~20–30 s of it. No code/infra blocker left.

This is the `alfr3d`-side half of the site's **Dial-In Plan Workstream A3** (the hero
"anticipation moment" clip on `littl31.com`). The site slot is already built and dormant:
`index.pug` renders `#anticipation` (a `<video autoplay loop muted playsinline>` in an amber
window-frame) only once `home.demo.clip` is set in `content.yml`. Until a real clip exists the
home page just flows pitch → pillars with no placeholder. See `littl31/todo/todo_site_dial_in.md`
and the Notion "🎯 Dial-In Plan" page.

The clip has to show the real `travel` card appearing on a real dashboard/Deck — no staging, no
mockup (the plan's acceptance bar). So `check_travel()` has to actually fire once, which it never
has.

## What was verified on the household NUC (`alfr3d@192.168.2.200`, 2026-09-10)

The whole `check_travel()` dependency chain was exercised live, end to end:

- **Routing container**: `alfr3d-routing-1` up 11 days (`ghcr.io/project-osrm/osrm-backend`),
  OSRM answering on `localhost:5005`.
- **Home coordinates** (todo concern #1): `environment` row `Alfr3d-Cassiopeia` →
  `Etobicoke, 43.643972, -79.588917`. Correct for the current address (confirmed by Athos).
  `check_weather()` / `context_frame` read the same row, so this is also what the rest of SA uses.
- **Extract coverage** (todo concern #2): called `routing_utils.get_route()` from *inside* the
  running `alfr3d-service-daemon-1` container for six spread-out GTA destinations —
  downtown Toronto, Pearson, Mississauga (Square One), Vaughan Mills, Scarborough Town Centre,
  Oakville — **all returned real routes** (13–32 min). The `Toronto` BBBike box comfortably
  covers anywhere a plausible household event would be. No rebuild needed.
- **Geocoding path**: `routing_utils.geocode_address("Nathan Phillips Square, Toronto")` →
  real coords via public Nominatim (reachable from the NUC), then `get_route()` from home → a
  real route. The full `address → coords → route → leave_by` chain works.
- **Timezone**: the daemon container runs UTC; `calendar_events.start_time` is stored UTC;
  `get_upcoming_events()`'s `datetime.now()` and `check_travel()`'s `frame.now` are both UTC.
  The path is timezone-consistent — no offset bug.

The NUC checkout lives at **`~/alfr3d`** (not `~/Projects/Alfr3d/alfr3d` as an earlier draft of
this file said).

## Fixed this session: calendar card times were shown in UTC, not household-local

`check_events()`, `check_travel()` and `check_focus_needed()` formatted the event / leave-by
time with a bare `strftime('%I:%M %p')` on a UTC datetime — so a 5 pm CEST event authored in a
CEST Google Calendar (correctly synced to 15:00 UTC) rendered as `at 03:00 PM` / `Leave by
02:18 PM` on the EDT household dashboard instead of `11:00 AM` / `10:18 AM`. The scheduling math
was always right (all UTC arithmetic against `frame.now`); only the display strings were wrong.

Added `ContextFrame.to_local(dt)` (uses `environment.timezone`, the DST-aware offset
`db_utils.get_env_local_time()` already trusts; passes through unchanged if the offset isn't
known that cycle) and `frame.tz_offset`, populated in `build_context_frame()`. The three rules
now format `frame.to_local(...)`. Tests: `TestContextFrameToLocal` + one local-time assertion
in each of `TestCheckEvents` / `TestCheckTravel` / `TestCheckFocusNeeded`.
**Deployed to the NUC 2026-09-10** (same rebuild as the sync routine below); verified live —
the card now reads `Upcoming event: test at 11:00 AM` / `Leave by 10:18 AM for test`.

## Fixed this session: no scheduled calendar sync

`sync_calendar()` used to run **only** at daemon startup or on a manual *Sync* click on the
Integrations → Google card (`POST /api/integrations/calendar/sync`) — every other integration
has a `schedule.every(...)` job, calendar didn't. A test event created in Google Calendar could
sit unsynced for hours.

Added `sync_calendar_routine()` in `alfr3ddaemon.py` (publishes `{type: calendar, action: sync}`
to the `integrations` topic, same message the API endpoint sends) on a
`schedule.every(15).minutes` cadence, plus `TestSyncCalendarRoutine` in `test_daemon_service.py`.
**Deployed to the NUC 2026-09-10** (`docker compose up -d --build service-daemon`, no migration).

## How the card fires (from the code, not assumptions)

| Requirement | Where |
|---|---|
| Event on Google calendar **`Armageddion Littl3.1`**, **`Family`**, or **`Cassiopeia`** | `calendar_utils.py:196` |
| Non-empty `address`, **no** Google-native conferencing (`conference_uri` empty — a Meet/Zoom link attached through the calendar's conferencing integration disqualifies it; a link pasted into notes by hand does not) | `alfr3ddaemon.py:884` |
| Event **starts within 2 h** of now | `get_upcoming_events()` horizon, `calendar_utils.py:152` |
| `leave_by = start − drive_minutes` is within **±30 min** (`TRAVEL_LEAD_MINUTES`) of now | `alfr3ddaemon.py:296`, `:902` |
| Event has **synced into `calendar_events`** | daemon startup, the 15-min job once deployed, or a manual *Sync* click |

Fails closed and silent at every step (ungeocodable address, unset home location, unreachable
routing container → no card, never a fabricated estimate). Card renders as
`Leave by H:MM PM for <title>` + `<N> min drive to <title>` on the frontend
(`SituationalAwareness.jsx:111`) and Deck (`ContextAwareness.kt` / `ContextRules.kt`).
Published once per ~60 s daemon cycle to the `situational-awareness` Kafka topic.

## Steps to capture the clip

**Option A — piggyback on a real event that's already on the calendar.**
As of 2026-09-10 there's a qualifying event synced:
`Upis dece na folklor`, **2026-09-12 14:00 UTC** (start), `2520 Dixie Rd, Mississauga` (~13 min
drive), no conference link. Its card will be live roughly **09:17–10:00 EDT on Sat Sep 12**
(from `leave_by ≈ 13:47 UTC` and the 2 h horizon capping the top of the window). If that time
works, just have the dashboard/Deck up and record.

**Option B — make a dedicated test event at a convenient time.**
1. In Google Calendar, on `Family` / `Cassiopeia` / `Armageddion Littl3.1`, create an event:
   - a real physical `address` in the GTA (any of the six probed destinations works), no Meet link;
   - start time ≈ *now + the drive time to that address* — e.g. a Mississauga address (~13 min)
     → start ~13 min out; you have ±30 min of slack so exact timing isn't critical;
   - keep it inside the next ~90 min so it clears the 2 h horizon with margin.
2. Trigger a sync: *Sync* on the Integrations → Google card, or
   `curl -X POST http://<host>/api/integrations/calendar/sync` (needs the `integrations`/
   `calendar_sync` permission). Once the 15-min job is deployed this is automatic within 15 min.
3. Within ~60 s of the sync + the leave-by window opening, the `travel` card appears on the
   dashboard and Deck.
4. **Record** ~20–30 s on a real device — the card appearing, with enough surrounding UI that it
   reads as a real dashboard, not a crop.

## Deploy / git state

Both source changes were `scp`'d onto the NUC checkout (`~/alfr3d`) and the container rebuilt
(`docker compose up -d --build service-daemon`, no migration) on 2026-09-10, then committed to
`main` from the dev checkout and pushed:

- `feat(daemon): scheduled 15-minute Google Calendar sync`
- `fix(daemon): render calendar card times in the household's timezone, not UTC`

**The NUC working tree still holds these as uncommitted local edits** and is behind `origin/main`
(it was 13 commits behind before this session). The scp'd files are byte-identical to what
landed on `main`, so the reconciliation is safe: on the NUC, `git checkout -- services/` (or
`git stash`) then `git pull` — no rebuild needed afterwards, the running image already has them.
Until that's done a NUC `git pull` will report a conflict on these two files.

## Hand the clip to the site (`littl31` repo)

```
cp <clip>.mp4 src/assets/vid/leave-by-demo.mp4       # + an optional poster frame
```
set `home.demo.clip: assets/vid/leave-by-demo.mp4` (+ `.poster`) in `src/content.yml`,
`npm run build:prod`. Same clip is reused for the Play Store listing video and waitlist
replies (Dial-In Plan A3).

## Un-hedge the copy

Once `check_travel()` has verifiably fired, restore `alfr3d.html` `intro.lines[0]` in
`littl31/src/content.yml` to unqualified present tense and delete the hedge comment on
`intro.bullets` (it currently says "already does" without ", today," because SA-6 has never run
in a live household).

## Related

- `todo/todo_self_hosted_routing.md` — SA-6 build + the 2026-08-30 NUC deploy this re-checks
- `littl31/todo/todo_site_dial_in.md` — the site A1/A2/A3 workstream this feeds
- Notion "🎯 Dial-In Plan — Positioning, Product & Launch Execution (Sep 2026)"
- Update the Notion Alfr3d Timeline per `AGENTS.md` Documentation Sync Protocol once the card
  fires for real (SA-6 Future → Present).
