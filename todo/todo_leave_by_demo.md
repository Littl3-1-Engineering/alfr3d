# Leave-by demo: OSRM on the (new) NUC + capture the clip

## Status: 🔴 Blocked on the household — needs the NUC re-checked after the house move,
a real calendar event, and someone to record it

This is the `alfr3d`-side half of the site's **Dial-In Plan Workstream A3** (the hero
"anticipation moment" clip on `littl31.com`). The site slot is already built and dormant:
`index.pug` renders `#anticipation` (a `<video autoplay loop muted playsinline>` in an amber
window-frame) only once `home.demo.clip` is set in `content.yml`. Until a real clip exists the
home page just flows pitch → pillars with no placeholder. See `littl31/todo/todo_site_dial_in.md`
and the Notion "🎯 Dial-In Plan" page.

The clip has to show the real `travel` card appearing on a real dashboard/Deck — no staging, no
mockup (the plan's acceptance bar). So `check_travel()` has to actually fire once, which it never
has.

## Why this isn't just "record a screen"

`todo/todo_self_hosted_routing.md` records the `routing` container going live on the NUC on
2026-08-30 (a `Toronto` BBBike extract, `restart: unless-stopped`, `get_route()` verified
end-to-end from inside `service-daemon`). **Since then the household moved** (documented
2026-09-08 — see `todo/todo_next_session.md` / `todo/todo_transition_learning.md`: ~59 HA
entities stayed at the old place). The same NUC came along (`192.168.2.200`), so the container
is probably still running, but the move invalidates two things it depends on:

1. **Household coordinates.** `check_travel()` calls `routing_utils.fetch_home_coordinates(ENV_NAME)`,
   which reads `environment.latitude`/`longitude` for the `ALFR3D_ENV_NAME` row. If those still
   point at the old address, every leave-by time is computed from the wrong origin. `None` there
   → no card at all.
2. **Extent of the OSRM extract.** The provisioned dataset is a `Toronto` BBBike bounding box. If
   the new house (or a plausible test-event destination) falls outside it, `get_route()` returns
   `None` and `check_travel()` correctly refuses to fabricate an estimate — no card.

## Steps (all user-side: own NUC, own Google account, own device to record)

1. **Re-check the routing container.** On the NUC:
   ```
   cd ~/Projects/Alfr3d/alfr3d
   ROUTING_REGION_NAME=region docker compose --profile routing ps      # is it up?
   curl -s 'http://localhost:5005/route/v1/driving/-79.5,43.6;-79.38,43.65?overview=false'
   ```
   If it's not running: `ROUTING_REGION_NAME=region docker compose --profile routing up -d routing`.

2. **Fix the home coordinates for the new address.** Check the `environment` row for
   `ALFR3D_ENV_NAME` — `latitude`/`longitude` must be non-null and match the new house. These are
   normally set from IP geolocation in `service_environment`; confirm it re-resolved after the
   move, or set them directly.

3. **Confirm the extract still covers the area.** From inside the running `service-daemon`
   container, call `utils.routing_utils.get_route((home_lat, home_lon), (dest_lat, dest_lon))`
   for a realistic destination near the new house. If it returns `None` for in-range points,
   rebuild the dataset for the new region:
   ```
   ROUTING_CITY=<BBBike city name for the new area> ./setup/build_routing_extract.sh
   #   supported names: https://download.bbbike.org/osm/bbbike/
   ROUTING_REGION_NAME=region docker compose --profile routing up -d --force-recreate routing
   ```
   (If the new city isn't in BBBike's list, that's the unbuilt osmium-extract fallback noted
   under "Not yet done" in `todo/todo_self_hosted_routing.md`.)

4. **Line up a triggering calendar event.** It needs: a physical `address`, **no** conference
   link (`conference_uri` empty — a video call has nowhere to drive to), start within ~2h, and
   positioned so `leave_by = start − drive_minutes` lands within **±30 min**
   (`TRAVEL_LEAD_MINUTES`, `alfr3ddaemon.py:296`) of the moment you record. Calendar sync is
   read-only and only pulls the calendars named `Armageddion Littl3.1`, `Family`, `Cassiopeia`
   (`calendar_utils.py`) — the test event has to be on one of those and has to have synced into
   `calendar_events`. (Athos made two test events with locations on 2026-09-09 — reuse/refresh
   their times.)

5. **Watch it fire.** On the next daemon cycle the `travel` card should render on the dashboard
   and Deck: "Leave by H:MM PM for &lt;event&gt;" plus the drive-time / distance line.

6. **Record** ~20–30s of that on a real device — the card appearing, with enough surrounding UI
   that it reads as a real dashboard, not a crop.

7. **Hand the clip to the site** (`littl31` repo):
   ```
   cp <clip>.mp4 src/assets/vid/leave-by-demo.mp4       # + an optional poster frame
   ```
   set `home.demo.clip: assets/vid/leave-by-demo.mp4` (+ `.poster`) in `src/content.yml`,
   `npm run build:prod`. Same clip is reused for the Play Store listing video and waitlist
   replies (Dial-In Plan A3).

8. **Un-hedge the copy.** Once `check_travel()` has verifiably fired, restore `alfr3d.html`
   `intro.lines[0]` in `littl31/src/content.yml` to unqualified present tense and delete the
   hedge comment on `intro.bullets` (it currently says "already does" without ", today," because
   SA-6 has never run in a live household).

## Related

- `todo/todo_self_hosted_routing.md` — SA-6 build + the 2026-08-30 NUC deploy this re-checks
- `littl31/todo/todo_site_dial_in.md` — the site A1/A2/A3 workstream this feeds
- Notion "🎯 Dial-In Plan — Positioning, Product & Launch Execution (Sep 2026)"
- Update the Notion Alfr3d Timeline per `AGENTS.md` Documentation Sync Protocol once the card
  fires for real (SA-6 Future → Present).
