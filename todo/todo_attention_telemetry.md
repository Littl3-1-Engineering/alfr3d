# Deck: Attention Telemetry as a Focus Signal

## Status: 🔲 Scoped only, not started (deliberately — see below)

## Overview

Nexus Launcher already tracks unlock frequency, per-app-category dwell time, and window-switch
rate on the spatial canvas but doesn't publish any of it. Scoped in Notion 2026-08-28 alongside
four other Deck data-feature milestones. Goal: (1) launcher emits these as a new Kafka event
stream, (2) backend derives a measured `focus_needed` signal from it instead of today's inferred
one (currently a text heuristic over calendar event address/notes, `focus_utils.looks_like_call()`
— see `check_focus_needed()` in `alfr3ddaemon.py`), (3) inverse case: late-hour high-unlock-rate +
social-app dwell triggers a wind-down card (dim via HA, Spotify low-energy switch).

## Why this is scope-only today

Two blockers, both explicit in the Notion milestone description itself:

1. **New Kafka topic required.** Unlike the other three "build today" Deck features (household
   composition, rhythm-break anomaly, cross-surface continuity), this one doesn't fit the
   existing situational-awareness pipeline (`DISPLAY_RULES` → `situational-awareness` topic →
   Deck polls `getSituationalAwareness()`). It needs a *new* inbound stream (launcher → backend),
   which is new infrastructure, not an additive DISPLAY_RULES check.
2. **Explicit coordination requirement.** The milestone's own description says: "coordinate
   scope with [the Nexus Launcher context-source exploration page] before building to avoid
   overlapping signal definitions." That page (`3c9d732b1d3481b08b51cb5ce4a718cc` in Notion,
   "Explore: Nexus Launcher as a new context source for Alfr3d") already brainstormed a
   *different* signal list: WiFi leave/arrive events, named context zones, car Bluetooth,
   charging-pattern sleep/wake, notification-category correlation, **DND correlation with
   `focus_needed`** (direct overlap with this todo's goal #2), cross-household "everyone left,"
   ambient app-category mood input. Its recommended pilot is WiFi leave/arrive, not attention
   telemetry — the two docs currently define `focus_needed`-adjacent signals independently and
   would collide if both got built without reconciling first.

## Reconciliation needed before implementation (not done yet)

- Decide whether "attention telemetry" (unlock rate, dwell time, window-switch rate) and "DND
  correlation with focus_needed" (from the exploration page) are the same signal described two
  ways, or genuinely complementary — if the same, merge into one scoped feature instead of
  building both.
- Both pages independently propose replacing/augmenting `check_focus_needed()`'s heuristic — pick
  one signal source (or a defined combination) as the actual `focus_needed` input before writing
  any Kafka topic or consumer code, to avoid two competing writers to the same DISPLAY_RULES slot.
- New Kafka topic naming/schema needs to be decided once, covering whatever signal set comes out
  of the merge above — not designed per-feature.

## Design sketch (not finalized — do this pass before building)

- Launcher-side: new Kafka topic (name TBD post-reconciliation, e.g. `launcher-telemetry`),
  emitted from wherever unlock/dwell/window-switch is already tracked locally (needs a
  `alfr3d_deck` repo grep to confirm the current tracking location — not done in this pass).
  Opt-in-per-signal and on-device-derived-events-only, matching the exploration page's
  local-first/no-telemetry framing (this brand constraint applies to both docs equally).
- Backend-side: new consumer alongside the existing `service_device`/`service_user`/etc. Kafka
  consumers, feeding a merged `focus_needed` computation that supersedes or augments
  `check_focus_needed()`.

## Related

- Notion: "Explore: Nexus Launcher as a new context source for Alfr3d" — reconcile with this
  before building either.
- `services/service_daemon/alfr3ddaemon.py` `check_focus_needed()`, `focus_utils.py` — the
  existing heuristic this would replace/augment.
