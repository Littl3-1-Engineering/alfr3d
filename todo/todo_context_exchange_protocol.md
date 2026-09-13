# Backend↔Deck Context Exchange Protocol

## Status: 🟢 Phases 1 and 2 built, deployed to the NUC, and live-verified 2026-09-12; Phases 3-5 designed

Prompted by a real bug (Deck showed a "Wind down" card on a Saturday at 18:18) that turned out to
be one symptom of a structural gap: **both sides run a situational-awareness engine, and neither
tells the other what it knows.** The Deck-local patch for that specific card
(`ContextRules.kt`, uncommitted, pending review) fixes the symptom only. This doc designs the
exchange.

Supersedes the narrower `todo_day_context_handshake.md` draft (deleted — its scope is Phase 1
here).

## The actual problem

Two independent SA engines, each with a partial view, each re-deriving what the other already
knows better:

- **Backend**: `MyDaemon.decide_displays()` runs 19 `DISPLAY_RULES` (`time`, `event`, `travel`,
  `music`, `now_playing`, `party_advisory`, `focus_needed`, `attention_focus`, `email`,
  `weather_advisory`, `weather`, `mood`, `household_composition`, `rhythm_break_anomaly`,
  `departure_anomaly`, `cross_surface_continuity`, `wind_down_signal`, `empty_house_still_on`,
  `household_unusual_day`) over a per-cycle `ContextFrame` (~60s).
- **Deck**: `RuleBasedContextAwarenessEngine` runs 42 `ContextRule`s over a `ContextSnapshot`
  (device tier 15s, ALFR3D tier 60s, background sync 30min).

Of the Deck's 42 rules, only 9 are pass-throughs of a backend card
(`DEDICATED_SITUATIONAL_MODES`). The other 33 are locally derived — and a large share of them are
re-deriving facts the backend already holds authoritatively.

### Three classes of overlap

**Class A — the same fact computed twice, differently.** The expensive one.

| Fact | Backend | Deck | Result |
|---|---|---|---|
| part of day | `day_context.part_of_day`, 7 parts, driven by the real **Bedtime/Morning routine rows** + sun | `timeOfDayFor()`, 6 buckets, **fixed hours 5/8/11/14/17/21** | The 18:18 Saturday bug |
| coarse time-of-day | `mood_utils.get_day_mood()["time_of_day"]`, 4 buckets via `timeofday.coarse_bucket` | (same 6-bucket `TimeOfDay`) | Backend disagrees *with itself* too: `day_context` says `wind_down` where `mood_utils` says `night` |
| weekend/social mood | `get_day_mood()`: `is_weekend`, Friday-wind-up, `base_energy` + `_WEEKEND_ENERGY_BONUS` | `dayMoodFor()`: `WeekendNight`/`SundayTransition`/`WeekendMorning` + `MusicEnergy.localEnergyFor()` | Two different rule sets for one idea, **kept in sync by hand via a code comment** |
| weather interpretation | `check_weather`, `check_weather_advisory` | `raining_info`, `cozy_weekend_rain`, `rainy_weekday_focus_mode`, `rainy_weekday_lights_routine`, `rainy_weekday_focus_music` | Same upstream row, two independent readings |
| who's home | `fetch_online_devices()` — every device on the network | `PeopleContext`/`isUserHome` from `getResidents` | Deck mirrors a summary, then re-reasons over it |
| routine about to fire | owns the table, fires them | `routineAboutToFire()` re-derives from synced `RoutineInfo.time` against **device** clock | Drifts with device clock skew |

The hand-sync is not hypothetical. `MusicEnergy.localEnergyFor()` carries this comment today:

> *"No bump: the real backend's own `mood_utils.get_day_mood()` only applies its weekend energy
> bonus to evening/night, never to a weekend morning — matched here so a locally-estimated morning
> playlist never contradicts what ALFR3D's own mood card would say."*

That is a protocol, implemented as a comment. It will rot.

**Class B — Deck-only signals the backend cannot see at all.** Verified: the backend has **zero**
references to battery, charging, DND, headset, network type/quality, orientation, or foreground
app. The only three uplinks that exist are `reportSurfaceState`, `reportAttentionTelemetry`,
`reportDeviceLocation`. So `DeviceContext` — `batteryPercent`, `isCharging`, `networkType`,
`networkQuality`, `dndActive`, `headsetConnected`, `orientation` — plus `topUsedAppLabel` never
leave the device. `check_focus_needed()` has no idea the phone is in Do Not Disturb right now;
`todo_attention_telemetry.md` already flagged "DND correlation with `focus_needed`" as desirable
and unbuilt. This protocol is how it gets built.

**Class C — backend-only signals the Deck cannot see.** Mostly already flowing down as cards, but
three notable gaps: `day_context` (Phase 1), the `day_mood` dict, and `frame.smarthome_online`.

## Design principles

1. **Ownership follows evidence, not hierarchy.** The owner of a facet is whichever side has the
   better evidence for it — not "the backend is the server so it decides." The Deck is the *only*
   authority on this device's power, DND, headset and foreground state; the backend is the only
   authority on the household's routines, cross-device presence, integrations and history.
2. **Subscribe, don't re-derive.** A non-owner consumes the owner's value. It does not implement a
   parallel algorithm for the same fact. (This is exactly why `common/day_context.py` exists — it
   killed six disagreeing implementations *inside* the backend. The principle just needs to cross
   the network boundary.)
3. **Provenance on every facet.** Each carries `source` (`backend` | `deck:<device_id>`) and
   `observed_at`. `MusicEnergy`'s existing `EnergySource.Alfr3d`/`.Local` split is the proven
   in-repo precedent — generalize it rather than invent something new.
4. **Tri-state, never boolean-collapse.** `null` means "unknown," not "false." The codebase already
   holds this line (`isUserHome: Boolean?` — *"treat `null` as don't assume either way"*;
   `_geofence_state()` returning `None` when accuracy can't place a fix). Every exchanged facet
   inherits it.
5. **Degrade, never block.** Both `ContextFrame` and `ContextSnapshot` already guarantee every
   field is independently nullable so one failed integration never suppresses unrelated cards.
   The exchange must not become a new single point of failure — an unreachable peer means "fall
   back to local estimate," never "no context."

## Ownership map

The core deliverable. Once agreed, most rule-level conflicts resolve mechanically.

| Facet | Owner | Non-owner behavior |
|---|---|---|
| `part_of_day`, `in_wind_down`, `is_waking_hours`, wake/bed times | **Backend** (`day_context.py`) | Deck subscribes; local clock-bucket only as offline fallback |
| Coarse time-of-day + `base_energy` | **Backend** (`mood_utils`) | Deck drops `localEnergyFor`'s hand-mirrored table to fallback-only |
| Calendar facts: `is_weekend`, day-of-week, Friday/Saturday-night, Sunday-transition | **Backend** | Deck subscribes (see "the contested facet" below) |
| Weather / atmosphere | **Backend** (`environment` row) | Deck subscribes (already does) |
| Sun times | **Backend** | Deck subscribes |
| Moon phase | **Deck** (pure math, no authority needed) | — |
| Household presence, guests, unknown devices | **Backend** (`fetch_online_devices`) | Deck subscribes |
| Routine definitions + firing | **Backend** | Deck subscribes; countdowns computed against **server** time, not device clock |
| IoT/smarthome state, playback, calendar, email, travel | **Backend** | Deck subscribes |
| Historical baselines (rhythm, departure, attention trend, unusual day) | **Backend** (needs cross-device history + DB) | Deck subscribes |
| Battery, charging, network type/quality, DND, headset, orientation | **Deck**, per device | Backend subscribes — **new capability** |
| Foreground app / top-used app / active surface | **Deck**, per device | Backend subscribes (partially exists as `surface_state`) |
| Attention telemetry (unlocks, switches, dwell) | **Deck**, per device | Backend subscribes (already exists) |
| This device's location / geofence | **Deck**, per device | Backend subscribes (already exists) |
| **"Is the user home"** | **Jointly evidenced — merge, don't own** | See below |

### The contested facet: weekend/social mood

This is where the 18:18 bug actually came from, and it deserves an explicit ruling rather than a
default. Two different questions are currently collapsed into one enum on each side:

- *"Is it, as a calendar fact, a Friday/Saturday night?"* → **backend-owned.** It already computes
  `is_weekend` and the Friday-wind-up case.
- *"Should this device's suggestion right now read as high-energy or wind-down?"* → **Deck-owned
  presentation choice**, informed by the backend's fact plus device state the backend can't see.

Conflating them is what let `DayMood.WeekendNight` (a presentation rule, hour ≥ 21) act as the
guard for an ownership question (is it the weekend), leaving 17:00–20:59 on Fri/Sat unguarded.
Splitting them makes that whole bug class unrepresentable.

### The jointly-evidenced facet: "is the user home"

Neither side owns this. The backend sees network-device presence across the household; the Deck
sees a coarse geofence (`accuracy_m` ≈ 2000 uniformly, per
`todo_device_location_reporting.md`'s real production findings) plus on-device activity. Needs a
stated merge rule, not an owner:

1. A confident Deck geofence state (`_geofence_state()` returning non-`None`) for *this* user
   outranks network inference — it's direct evidence about the person, not their laptop.
2. Otherwise backend network presence wins.
3. Disagreement with neither confident → `null` (unknown), and rules that branch on presence
   simply don't fire. **Never** silently pick a side.

## Protocol shape

### Downlink: `GET /api/context/snapshot`

The backend's authoritative view, assembled from the `ContextFrame` it already builds every cycle
— including the facets it currently keeps private (`day_context`, `day_mood`, `smarthome_online`,
playback). Not a replacement for the existing granular endpoints (`getWeather`, `getRoutines`, …),
which stay; this is the *derived-context* document those endpoints can't express.

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-09-12T18:18:04Z",
  "server_now_local": "2026-09-12T18:18:04",   // household-local, for clock-skew correction
  "facets": {
    "day_context": { "value": { "part_of_day": "evening", "in_wind_down": false,
                                "is_waking_hours": true, "minutes_to_bedtime": 222,
                                "wake_time": "06:30", "bed_time": "22:00" },
                     "source": "backend", "observed_at": "..." },
    "day_mood":    { "value": { "time_of_day": "evening", "day_of_week": "Saturday",
                                "is_weekend": true, "base_energy": 0.7 }, ... },
    "presence":    { "value": { "known_names": [...], "unknown_count": 0 }, ... },
    "atmosphere":  { ... },
    "playback":    { ... }
  }
}
```

Every facet independently nullable; a facet the backend couldn't build this cycle is simply
absent, which the Deck reads as "fall back to local."

### Uplink: `POST /api/context/device-snapshot`

Generalizes the three existing one-off POSTs into one device-context report, and carries the
Class-B signals that reach the backend today. `device_id` mandatory — several Decks can report,
and the backend merges N device contexts into one household view (same per-device grain
`device_location_history` already uses).

```jsonc
{
  "schema_version": 1,
  "device_id": "...",
  "observed_at": "...",
  "facets": {
    "power":       { "battery_percent": 63, "is_charging": false },
    "interruption":{ "dnd_active": true, "headset_connected": false },
    "network":     { "type": "cellular", "quality": "good" },
    "form":        { "orientation": "portrait" },
    "activity":    { "active_surface": "ambient_brief", "top_app": "...",
                     "terminal_session_active": false }
  }
}
```

Existing `surface-state` / `attention-telemetry` / `device-location` routes stay as-is (deployed,
live-verified, referenced from three todo docs). This is additive; folding them in is optional
future cleanup, explicitly **not** part of this work.

### Transport and cadence

REST both directions — every Deck↔backend integration in this codebase goes through
`HttpAlfr3dClient` → `service_api`; the Deck never touches Kafka
(`todo_attention_telemetry.md`'s own stated precedent). No websocket, no push.

Cadence already lines up: the Deck's foreground ALFR3D refresh is 60s and the daemon cycle is
~60s. Downlink rides the existing 60s fetch + 30min background sync; uplink piggybacks the same
60s tick. Backend cost is near zero — the `ContextFrame` is already built every cycle and
`get_day_context()` is already 20s-cached.

## Reconciliation

One shared merge step per side, replacing ad-hoc per-rule checks:

- **Deck**: `ContextSnapshotProvider` resolves each facet once — fresh owner value if present,
  else local estimate, stamping which was used. Rules read the resolved facet and never decide
  provenance themselves. `DEDICATED_SITUATIONAL_MODES` (today's card-layer dedup) becomes
  principled: if the backend owns the facet, the local rule doesn't fire, rather than firing and
  being filtered later.
- **Backend**: `build_context_frame()` merges reported device contexts into
  `frame.launcher_context` (which already exists for exactly this purpose) and exposes the
  household roll-up (any device in DND? any charging? nearest device home?) to the
  `DISPLAY_RULES`.

**Precedence ladder**, applied uniformly: fresh owner value → fresh non-owner value (degraded,
marked) → local estimate → `null`. "Fresh" = `observed_at` within a facet-specific TTL (day
context tolerates minutes; battery does not).

## Protocol hazards to design against

1. **Echo / false corroboration.** If the Deck reports up a fact it just learned *from* the
   backend, the backend treats its own inference as independent confirmation. Provenance tags
   prevent it: a facet whose `source` is `backend` is never re-reported upward. This is the
   subtlest failure mode here and the main reason facets carry provenance rather than bare values.
2. **Clock skew.** Countdowns and staleness checks must use `server_now_local` as the reference
   where the fact is server-owned, not the device clock. Same bounded-tolerance philosophy as
   `_LOCATION_MAX_FUTURE_SKEW_MS`.
3. **Version skew.** `schema_version` + additive-only fields + ignore-unknown. An old Deck against
   a new backend (or the reverse) degrades to local estimates; a 404 is indistinguishable from
   "stale," and both mean "fall back."
4. **Multi-device.** Two Decks will disagree (one charging, one not; one home, one away). The
   household roll-up must be an explicit reduce with a stated rule per facet, not last-writer-wins.
5. **Oscillation.** A facet flipping near a boundary (geofence jitter at 2km accuracy) must
   hysteresis-damp, not flap cards. The existing card suppression
   (`CARD_SUPPRESSION_*`, repetition damping) covers the symptom; the merge layer should not
   create new flapping upstream of it.

## What this unlocks (beyond de-duplication)

Worth stating, because the value isn't only "stop contradicting each other":

- `check_focus_needed()` gains real DND awareness — the explicitly-deferred item from
  `todo_attention_telemetry.md`.
- Backend rules can finally consider "the user is actively on their phone right now" vs. "the
  house is quiet" as different states.
- `check_empty_house_still_on` / `departure_anomaly` get a second, independent presence signal.
- Deck cards stop needing their own weather/mood/presence reasoning, which shrinks
  `ContextRules.kt` rather than growing it.
- Battery/network state lets either side suppress expensive suggestions on a dying or metered
  device.

## Phases

- **Phase 1 — `day_context` downlink (the bug that started this). ✅ Built.**
  `GET /api/context/day-context` (thin wrapper over the already-cached `DayContext`, ungated like
  every other read route), `Alfr3dClient.getDayContext()`, folded into the existing
  `alfr3dSnapshot` fan-out. `ContextSnapshotProvider.resolveDayContext()` applies the precedence
  ladder and stamps `ContextFacetSource`; `evening_winddown` prefers it, keeping the local
  fixed-hour estimate as the offline fallback. 6 route tests.

  Two findings while building it, both kept as regression tests:
  - At the reported bug time (18:18) the backend says **`afternoon`**, not `evening` —
    `_classify()` starts evening at *sunset*. The Deck's fixed 17:00 bucket was two parts ahead,
    not one.
  - The authoritative branch deliberately **drops** the `TimeOfDay.Evening` requirement: with a
    22:00 bedtime the real wind-down window (21:15–22:00) sits in the Deck's local *Night*
    bucket, so keeping that condition would mean the card could essentially never fire correctly.

- **Phase 2 — device-context uplink. ✅ Built.** `POST /api/context/device-snapshot` storing
  per-device facets keyed by install id (the same id `reportDeviceLocation` uses), bounded at 8
  devices with oldest-observation eviction. `DeviceContextReporter` on its own 5-minute timer —
  inside the backend's 15-minute staleness gate, so two reports can be missed before a device
  reads as silent. `MyDaemon._read_fresh_device_contexts()` owns the staleness gate and
  `._any_device_in_dnd()` owns the household reduce.

  **The reduce is "any", stated explicitly**, because multi-device disagreement is real: with a
  wall tablet and a phone, the question is "has the user silenced interruptions anywhere," not
  "what did the most recent device to check in say." It is tri-state — `None` when no fresh
  device reported the facet at all — so "nobody told us" stays distinguishable from "told us
  it's off".

  First consumer, shipped with it so the data is never write-only: `check_focus_needed()` now
  drops "Find a quiet spot." when a Deck reports DND already on, and adds a `because` line
  instead. It still **fires** — the useful part is "your call starts in N minutes," and
  suppressing that because the phone is silenced would throw away the alert to preserve the
  footnote. 7 route tests + 11 daemon tests.
- **Phase 3 — full downlink document.** `GET /api/context/snapshot` with the facet envelope;
  migrate `day_context` (Phase 1) into it; add `day_mood`, presence, playback, `smarthome_online`.
- **Phase 4 — reconciliation layer.** The single merge step on each side; retire the hand-mirrored
  tables in `MusicEnergy.localEnergyFor()` and the duplicated mood logic; split the contested
  weekend facet per the ruling above.
- **Phase 5 — verify.** On-device against the real household, both reachable and with Wi-Fi off,
  plus a deliberate backend-version-skew check. Same "verify against real production data before
  calling it done" discipline as `todo_device_location_reporting.md`.

Phases 1 and 2 are independently valuable and can ship without 3–5 ever happening. That's
intentional — 3–5 are the expensive half, and they should be justified by what 1–2 actually reveal.

## Out of scope

- **No push channel** (websocket/Kafka to the Deck). Polling at the existing 60s cadence is
  sufficient; matches this repo's stated Deck↔backend precedent.
- **No retirement of the granular endpoints.** `getWeather`/`getRoutines`/`getResidents`/etc. stay.
- **No folding the three existing uplink routes** into the new one. They're deployed and
  live-verified; churning them buys nothing.
- **No `TimeOfDay`/`DayMood` enum redesign** beyond the weekend-facet split in Phase 4.
- **No cross-household / multi-tenant concerns.** Single-environment assumption throughout, same
  as everything else in `DISPLAY_RULES` today.

See also: `alfr3d_deck/todo/todo_context_exchange_protocol.md` (stub).

## Live verification (2026-09-12, real household + real device `NAAIB7004279WZB`)

Deployed from `feat/context-exchange-protocol` with `docker compose up -d --build service-api
service-daemon` (v2 for build *and* recreate together, per the v1/v2 trap). Confirmed no
stale-image trap: each container's `.Image` matched the image id compose had just built, and no
unrelated service was taken down.

**Phase 1 downlink, against the household's own routine rows:**

```
GET /api/context/day-context
{"part_of_day":"evening","in_wind_down":false,"minutes_to_bedtime":100,
 "wake_time":"07:30","bed_time":"22:00","server_now_local":"2026-09-12T20:19:02", ...}
```

The real Bedtime routine is 22:00, so the authoritative wind-down window is 21:15-22:00.
`minutes_to_bedtime` checks out (20:19 + 100 min = 21:59). The Deck's old fixed-hour bucket
would have been claiming wind-down since 17:00 -- a 3h15m error against the household's own
configured intent, which is the whole reason this facet is backend-owned.

**Phase 2 uplink, real device state round-tripping:**

```json
"39bef6ad-…": {"facets": {
  "power": {"battery_percent": 83, "is_charging": true},
  "interruption": {"dnd_active": false, "headset_connected": false},
  "network": {"type": "wifi", "quality": "unknown"},
  "form": {"orientation": "portrait"}}}
```

Device id matches the Deck's own install id, and power/charging matched the phone's real state.
Note `form.orientation` is present: that is the tuple-vs-string bug (`("orientation")` is a
`str`) caught during implementation -- without the fix this facet would be silently absent in
production rather than failing loudly.

Toggling real DND on the phone flipped `dnd_active` to `true` on the next report, and the
daemon's own consumer path, run read-only against the live row, resolved it:

```
fresh device contexts: 1
  device 39bef6ad -> {'dnd_active': True, 'headset_connected': False}
_any_device_in_dnd -> True
```

So `check_focus_needed()` would now say "Do Not Disturb is already on." instead of "Find a quiet
spot." DND was restored to off afterwards. `service-api` logs confirm both directions are live
from the real Deck: `GET /api/context/day-context` and `POST /api/context/device-snapshot`.

**Verified earlier the same evening, before deploy -- the version-skew path.** With the route
still 404ing in production, `alfr3d context` on-device rendered 8 cards across 4 tiers including
two in ATMOSPHERE & MEDIA, with no wind-down card at Saturday 20:05 (inside the window the bug
used to fire in). The tier renders and its other rules fire, so the absence is a targeted
exclusion rather than a broken rule, and the 404 degraded to the local estimate with no crash and
no error card.

**Not yet verified:** the authoritative branch actually *firing* the wind-down card. That needs a
weekday between bedtime-45min and bedtime (21:15-22:00 here); the verification evening was a
Saturday, which the weekend guard correctly excludes regardless of what the backend says. Worth a
deliberate check on a weeknight.
