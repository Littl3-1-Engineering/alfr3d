# Todo: Explore Free/Open-Source Routing for Travel Guidance

## Status: ➡️ Superseded 2026-08-30 by SA-6 (`todo/todo_self_hosted_routing.md`), which answers the
open questions below with real, live-measured numbers rather than assumptions. Kept here for the
original candidate list and framing.

## Goal
Revisit real leave-by time / drive-time guidance for calendar events with a destination, using
a free or self-hostable routing source instead of the Google Maps Directions API — which was
removed 2026-08-27 (`todo_repo_standardization.md`-adjacent cleanup; see `alfr3ddaemon.py`'s
`check_travel()` history) because it required a paid tier the household isn't using. Today's
replacement (`alfr3d_deck`'s `next_event_soon` "Open Maps" action) is honest but dumb — it hands
off to the device's maps app with no computed leave-by time or fuel-cost estimate at all.

## Candidates to evaluate
- **OSRM** (Open Source Routing Machine) — the household's likely reference point for this todo
  ("OSMAN"). Self-hosted, MIT-licensed, runs entirely on OpenStreetMap data with no per-request
  API key or billing. Needs a local routing server (Docker image available) preloaded with an
  OSM extract for the relevant region — a real hosting/maintenance cost (disk space, extract
  updates), not a request-billing one.
- **OpenRouteService (ORS)** — built on OSM + OSRM/GraphHopper-family engines, offers a free-tier
  hosted API (no self-hosting required) with a request-volume cap, or is itself self-hostable.
  Worth comparing against a bare self-hosted OSRM instance for setup effort vs. rate limits.
- **GraphHopper** — similar shape to ORS: hosted free tier with a request cap, or self-hostable,
  OSM-based.
- **Valhalla** — another OSM-based, self-hostable routing engine (used by some OSM-adjacent
  projects); heavier to run than OSRM but has richer routing options (e.g. time-dependent
  traffic-aware routing is limited/absent across all of these compared to Google's, worth
  confirming per-candidate rather than assuming).

## Open questions
- Self-hosted (OSRM/ORS/GraphHopper/Valhalla) vs. a hosted free tier — self-hosting avoids rate
  limits and any account/key management, but adds a new always-on service (another container,
  another `docker-compose.yml` entry, an OSM extract to download/refresh) to an already
  multi-service stack. A hosted free tier is simpler operationally but reintroduces the "what
  happens when the free quota runs out" question this whole todo exists to avoid.
- None of these have Google's real-time traffic layer — `duration_in_traffic` (the traffic-aware
  estimate `maps_utils.get_travel_info()` preferred) has no free equivalent here. Worth deciding
  up front whether a traffic-blind "typical drive time" estimate is honest enough to ship, or
  whether that gap alone makes computed leave-by guidance not worth reviving at all (vs. staying
  with the current honest, dumb "Open Maps" hand-off).
- Fuel-cost estimation (`GAS_PRICE`/`MPG`) was straightforward math independent of the routing
  API — only the distance/duration source needs replacing, not that part of the old design.
- If revived, would live in the same place as before: `maps_utils.py`-equivalent in
  `service_daemon/utils/`, called from a `check_travel()`-equivalent registered in
  `alfr3ddaemon.DISPLAY_RULES`. `alfr3d_deck`'s `next_event_soon` would need to go back to
  branching on a real `travel` situational-awareness card the way `alfr3d_travel_guidance` used
  to, rather than (or possibly in addition to) its current plain "Open Maps" hand-off.

## Related
- Removed 2026-08-27: `alfr3ddaemon.check_travel()`, `maps_utils.py` (Google Maps Directions),
  `alfr3d_deck`'s `alfr3d_travel_guidance`/`TravelInsight`. See both repos' commit history same
  date for exactly what was torn out and why.
