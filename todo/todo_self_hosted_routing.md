# SA-6: Self-hosted routing & leave-by guidance

## Status: 🟡 Phase 0 live-verified against the real production NUC; Phase 1/2 code built and
fully unit-tested (444 passed); end-to-end verification against the *local* dev stack in
progress (slow background extract download — see "Not yet done"); NOT yet deployed to the
household's real production NUC (needs an explicit go-ahead)

First item of Wave 3, following Wave 2 (SA-4, SA-5, SA-3). Restores what commit `08509ce` removed
(Google Maps Directions `check_travel()`), on self-hosted infrastructure instead of a paid API —
supersedes the exploratory `todo/todo_free_routing_alternatives.md`.

## Phase 0 — evaluate and choose (real numbers, not assumptions)

Investigated live, on the household's actual production hardware (`alfr3d@192.168.2.200`,
hostname `Alfr3d-Gorsion`, Intel Pentium Silver J5040, 7.3GiB RAM, 4 cores — **not** a Raspberry
Pi 5; that hardware target was retired mid-session, this is the real box), not a synthetic
benchmark or a spec sheet:

- **Real disk headroom today: only 18GB free** on a 109GB root filesystem (84% used). A
  significant chunk of that "used" space is reclaimable Docker build cache (28.85GB cache,
  20.83GB reclaimable per `docker system df`) — a real, separate finding worth flagging to the
  user, not something this task should silently clean up on a live box.
- **Geofabrik has no sub-country extract for Canada** — the smallest official regional file
  covering this household's own location (Etobicoke/Toronto) is the entire country
  (`canada-latest.osm.pbf`, ~6.4GB compressed as of 2026-07). A full-country extract's processed
  OSRM output would be several times the source size (see below) — almost certainly **would
  not** fit in 18GB free today. This directly resolves the task's own "if a metro-area extract
  doesn't fit, self-hosting is dead" question: it isn't the metro extract that doesn't fit, it's
  a full-country one.
- **A metro-sized extract genuinely fits, measured, not assumed.** Used BBBike.org's predefined
  `Toronto` extract (98MB `.osm.pbf`, covers this household's own real location) and ran the
  actual `osrm-backend` MLD preprocessing pipeline (`osrm-extract` → `osrm-partition` →
  `osrm-customize`) live on the production box, each step timed and RSS-measured via `/usr/bin/time -v`
  and OSRM's own internal peak-RAM reporting:

  | step | wall time | peak RAM |
  |---|---|---|
  | `osrm-extract` | 68s | 814 MiB |
  | `osrm-partition` | 19.5s | 217 MiB |
  | `osrm-customize` | 5.8s | 203 MiB |

  Processed output: **262MB total** (98MB source → 262MB routing-ready data, ~2.7x). Started
  `osrm-routed` (MLD) afterward: **173MiB idle RSS**, capped at a 500MB container limit with no
  issue. Issued a real route query (a point near Etobicoke to Bay Street, downtown Toronto):
  valid response, 17.9km / ~19.7min, zero external network calls. Full test cleaned up
  afterward (`docker rm`/`docker rmi`, extract files deleted) — confirmed disk back to the exact
  18GB-free baseline.
- **Architecture**: `ghcr.io/project-osrm/osrm-backend` publishes official `arm64` images
  (`docker manifest inspect` confirmed both `amd64` and `arm64` variants exist) — no architecture
  blocker regardless of what hardware this ends up running on.
- **Cold-start / autostart**: already solved by `todo/todo_container_autostart.md` (shipped
  2026-08-25, tested with a real reboot of this exact box) — a new `routing` service in
  `docker-compose.yml` with `restart: unless-stopped` and a healthcheck inherits the existing
  systemd-unit autostart mechanism automatically. No new work needed here.
- **Traffic awareness**: none of these engines match Google's live traffic layer. OSRM here is
  free-flow/typical-conditions only. Decision: ship it, but every card carries an explicit
  `data.traffic_aware: false` so no consumer can present a free-flow estimate as if it accounted
  for current conditions.
- **Geocoding is a separate cost, and self-hosting it is not the right call.** `calendar_events`
  has no coordinates today (confirmed: no `latitude`/`longitude` columns, no existing
  geocoding of event addresses anywhere in the codebase — only IP-based *household* geolocation
  exists, in `service_environment`). Nominatim (the standard self-hostable geocoder) needs far
  more RAM/disk than OSRM even for a single country/region — not measured directly this pass
  (didn't want to risk disk headroom on the live box twice in one session for a component this
  task doesn't need to self-host), but this is well-documented in Nominatim's own installation
  requirements, not a guess. Checked the *public* Nominatim usage policy directly instead
  (`operations.osmfoundation.org/policies/nominatim`): "No heavy uses (an absolute maximum of 1
  request per second)" plus a valid User-Agent. A household geocoding a handful of new calendar
  addresses per day, cached after the first lookup, is trivially within that policy — so the
  honest, proportionate choice is the **public Nominatim API for geocoding** (rare, cached,
  policy-compliant, small external footprint) alongside **self-hosted OSRM for routing** (the
  actual per-cycle, higher-frequency piece where "on our own hardware" is the real differentiator
  and the brand argument the task doc makes).
- **Region generality** (the Kit ships to unknown geographies): Geofabrik's country-only
  granularity for Canada wouldn't generalize well, but BBBike's extract service supports
  arbitrary custom bounding boxes via its API, not just its list of predefined cities. Combined
  with the fact that this household's `environment` table already stores `latitude`/`longitude`
  for its own location (used today for weather), the provisioning approach in Phase 1 below
  derives the extract region from that existing column rather than a hardcoded place name or a
  new onboarding question.

**Verdict: Green.** Self-host OSRM for routing (proven cheap, fast, and architecture-portable);
use the public Nominatim API for the much rarer geocoding need rather than self-hosting a second,
heavier service for it. A full-country extract is explicitly out — only a bounding-box-derived
regional extract sized to the household's own location.

## Phase 1 — routing client

New `services/service_daemon/utils/routing_utils.py`:
- `geocode_address(address)` — checks `geocode_cache` (migration 032/0034, new table keyed by
  address text, not event id, since geocoding is purely a function of the address string) before
  ever calling the public Nominatim API; caches a "not found" result (`NULL` lat/lon) too, so an
  unresolvable address doesn't get re-queried every cycle. A defensive module-level 1-request/sec
  floor sits under the cache as a safety net, not as what makes this policy-compliant on its own
  (the cache is what actually keeps real volume near zero).
- `fetch_home_coordinates(env_name)` — reads `environment.latitude`/`longitude`, the same row
  `check_weather()`/`context_frame`'s snapshot already reads, just the two columns that shared
  fetcher doesn't select. Kept as its own tiny query per SA-4's convention (only fields
  duplicated across 2+ rules join the shared frame; only `check_travel()` needs coordinates).
- `get_route(origin, dest)` — thin OSRM HTTP client (`/route/v1/driving`). Returns
  `{duration_minutes, distance_km}` or `None` on any failure (unreachable container, no route,
  malformed response) — `check_travel()` must never turn `None` into a fabricated estimate.

## Phase 2 — `check_travel` rule

New `DISPLAY_RULES` entry, priority **2.5** (between `event` (2) and `empty_house_still_on`
(2.4)/`rhythm_break_anomaly` (2.6) — matches the original pre-removal placement). Fires only
when the next calendar event has a non-empty `address` and no `conference_uri` (a video call has
nowhere to drive to — that's `check_focus_needed()`'s job), and the computed leave-by time falls
within `TRAVEL_LEAD_MINUTES` (30) of `frame.now` in either direction. `data.traffic_aware` is
always `false` — none of the self-hosted engines evaluated match Google's live-traffic layer, so
no consumer can present this as anything but a free-flow estimate.

`docker-compose.yml` gains a `routing` service under a new **opt-in `routing` profile** (not
started by default) running `ghcr.io/project-osrm/osrm-backend` in MLD mode, bound to
`localhost:5005` (service-daemon runs `network_mode: host`, so it reaches `routing` the same way
it reaches MySQL/Kafka — a host port, not a Compose service-name hostname). No healthcheck: the
`osrm-backend` image's minimal Ubuntu base isn't confirmed to carry `curl`/`wget` to probe with,
and nothing else in the file `depends_on` this service anyway — not worth shipping an unverified
assumption for a cosmetic `docker compose ps` status.

`setup/build_routing_extract.sh` provisions real regional data: `ROUTING_CITY=<name>` fetches a
BBBike predefined-city extract (the exact pipeline proven in Phase 0) and runs the real
`osrm-extract`/`osrm-partition`/`osrm-customize` sequence, dropping the output into
`./routing_data/` where the `routing` service expects it.

## Testing

`TestRoutingUtils` (12 tests): cache hit skips Nominatim entirely; a cached "not found" (a row
with `NULL` lat/lon, distinct from no row at all) also skips re-querying; a genuine cache miss
calls Nominatim (with a real `User-Agent` header) and writes the result back, including caching a
"not found"; blank/`None` addresses short-circuit before any DB call; `fetch_home_coordinates()`'s
found/not-set/DB-error paths; `get_route()`'s success, no-route, and unreachable-service paths.
`TestCheckTravel` (9 tests): fires within the lead window; no upcoming event; blank address;
conferencing event (even with an address); ungeocodable address; unset home location; unreachable
routing service; leave-by too far in the future; leave-by meaningfully in the past. Existing
DISPLAY_RULES scaffolding (`_stub_daemon`, the two "everything fires" end-to-end tests, the exact
mode-order list) updated for the 18th registered rule. Full suite: **444 passed, 9 skipped**
(MySQL-integration skips, unrelated), lint clean.

## Live verification

- **Phase 0's routing-engine numbers (see above) are themselves the primary live verification**
  — measured against the actual production hardware, not a synthetic dev-box benchmark: real
  extract, real preprocessing, a real served route query, cleaned up after with disk confirmed
  back to baseline.
- **Not yet done: an end-to-end `check_travel()` firing against a running `routing` container.**
  Ran `setup/build_routing_extract.sh` locally to reproduce that same pipeline against this dev
  environment for an in-repo functional check (not just the standalone commands already proven
  on the NUC). Two attempts: the first completed the full `osrm-extract`/`partition`/`customize`
  pipeline successfully but failed at the final copy step (`region.osrm.fileIndex` came out of
  the container root-owned and 0700, unreadable by this script's own user) -- fixed in the script
  by chmod'ing the output via a throwaway `alpine` container before copying. The second attempt,
  re-running the fixed script end to end, was killed by the environment (a background-task
  session boundary, not a script failure) before the slow BBBike download
  (~20-25KB/s from this sandbox specifically, the same symptom SA-9 hit with unrelated endpoints)
  completed. **Not retried further this pass** -- the download has proven unreliable in this
  specific sandbox across multiple attempts, and Phase 0's own real-hardware numbers (see above)
  already carry the load-bearing evidence for this task; a redundant local confirmation isn't
  worth another open-ended wait. Next session (or with more reliable network conditions): rerun
  `ROUTING_CITY=Toronto ROUTING_REGION_NAME=region bash setup/build_routing_extract.sh`, then
  `docker compose --profile routing up -d routing` and confirm `check_travel()` produces a real
  card against a live calendar event with a real address -- and only then update the README's
  now-stale "needed a paid Google Maps Directions tier" line.

## Not yet done

- End-to-end `check_travel()` firing against a live `routing` container (see above -- in
  progress, not skipped).
- **Deploying this to the household's real production NUC.** Phase 0's test there was
  deliberately bounded and fully cleaned up (`docker rm`/`rmi`, extract files deleted, disk
  confirmed back to the 18GB-free baseline) -- making the `routing` service and real regional
  data a *permanent* part of that live stack (~262MB+ disk, a new always-on ~170MB+ RAM
  container) is a bigger, standing commitment on a disk-constrained box already running the
  household's actual home automation, and needs an explicit go-ahead first, not an assumption
  that Phase 0's one-time test implied consent to a permanent install.
- The 20.83GB of reclaimable Docker build cache found on the production NUC during Phase 0 --
  flagged as a separate, real finding; not touched, not this task's job to clean up unprompted.
- README's situational-awareness feature line still describes the pre-SA-6 state ("needed a paid
  Google Maps Directions tier... Open Maps action instead") -- update once live verification
  above completes.

## Out of scope (per the task doc, unchanged)

- Multi-modal routing (transit, cycling) -- driving only for v1.
- Live traffic -- `data.traffic_aware` is always `false`, by design.
- Re-adding any Google dependency.
- The manual osmium-extract-from-a-larger-region fallback for households outside BBBike's
  predefined-city list -- scoped in Phase 0's design discussion, not built or verified this pass.
