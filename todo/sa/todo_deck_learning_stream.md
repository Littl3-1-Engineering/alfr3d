# Deck -> SA learning stream: capture everything alfr3d_deck reports

> **Layer:** data (input) · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-0c (new), [todo_signal_inventory.md](todo_signal_inventory.md)

## Status: 🔲 Not started (filed 2026-10-10 by request). Part of the Deck's data is already in the lake; the rest is reported and thrown away.

## Why

The Deck (alfr3d_deck, the Android launcher) is the richest sensor ALFR3D has: it is on the person,
so it knows things nothing in the house can see. Some of what it reports is already learning input.
The rest arrives, overwrites the previous value, and is gone. Same lesson as Home Assistant's 10-day
window: **history that was never written down cannot be recovered**, so capture comes before
learners.

## What the Deck reports today, and what happens to it

Every Deck-to-backend endpoint is in `services/service_api/routes/context.py`. Checked 2026-10-10:

| Deck report | Endpoint | Stored where | History kept? | In the lake? |
|---|---|---|---|---|
| Attention (unlocks, app switches, dwell by category, per 15 min) | `POST /context/attention-telemetry` | `attention_telemetry_history` (+ a config snapshot) | ✅ 1,491 rows since 08-30 | ✅ bronze |
| Location fixes (coarse, foreground-only) | `POST /context/device-location` | `device_location_history` | ✅ 797 since 09-11, one device | ✅ bronze |
| Geofence enter / leave | derived from the fixes | `household_events` (presence/user) | ✅ 13 events | ✅ via events |
| Card shown / tapped / dismissed | `POST /context/card-interaction` | `card_interactions` | ✅ 49,558 since 08-31 | ✅ bronze |
| Notification metadata (category, app, sender; **no body**) | `POST /context/notification-event` | `household_events` (notification/sender) | ✅ 1,050 messaged + 66 called since 09-13 | ✅ via events |
| **Device context**: battery %, charging, **DND**, headset, network type and quality, orientation, active surface, top app, terminal session, speech relay | `POST /context/device-snapshot` | `config` JSON `launcher_device_context`, **one row per Deck, overwritten** | ❌ **current value only** | ❌ |
| **Surface state**: active surface, terminal session | `POST /context/surface-state` | `config` JSON `launcher_surface_state`, **overwritten** | ❌ **current value only** | ❌ |

Two reports carry no history, and they are the ones about *what the person is doing right now*.

## What is lost, and what it would teach

- **DND history**: when the household silences the phone (meetings, sleep). Currently the only trace
  is `focus_needed`'s live check. Learnable: the person's quiet-hours rhythm, DND vs. calendar.
- **Battery and charging**: when the phone is on the charger (the bedside routine, the desk
  routine) is a strong, independent signal of "at home, at rest". A phone not charging overnight
  is itself unusual.
- **Network type and quality**: Wi-Fi vs. cellular is a **second, independent presence signal** that
  does not depend on arp-scan sightings: on the home Wi-Fi means home, on cellular means out. It
  would let the presence learner cross-check the phone sightings it is built on, and tell "phone
  asleep" from "person left" (the 30-minute ambiguity LF-2 had to merge).
- **Active surface / top app / terminal session**: what the person is doing on the Deck, as a time
  series, beyond the 15-minute attention aggregates.
- **Orientation, headset**: weak individually; cheap to keep.

## Proposed design

- [ ] **`deck_context_history`** (MySQL, 730-day retention EVENT like the other SA tables): one row
      per *change* in a Deck's context, not per report. Columns: `client_install_id`, `user_id`,
      `observed_at` (UTC), and the facets from `_DEVICE_CONTEXT_FACETS` flattened (nullable, so the
      tri-state "not reported" is preserved: `null` means unknown, never "no"), plus the surface
      state. Written by `report_device_snapshot` / `report_surface_state` after the upsert they
      already do, best-effort so it can never fail the report. A change-only write keeps it small:
      battery % is bucketed (5%) so a slow drain doesn't write a row a minute.
- [ ] Add it to the bronze export (`lake.EVENT_TABLES`), the storage metrics, and the retention
      doc. One migration; backup and rehearse first.
- [ ] Silver `deck_context`: per-Deck intervals (charging, DND, on-Wi-Fi) in the same shape as
      `presence_intervals`, with local time.
- [ ] Learners (after LF-4): DND rhythm (state family); charging rhythm; **network type as an
      independent presence cross-check** feeding the presence learner's `source_quality`.
- [ ] **Ask the Deck for more**, in the Deck repo (`alfr3d_deck/todo/`): app-launch counts by
      category, screen-on intervals, voice-command usage. These are Deck-side changes and a
      privacy decision for the household before anything is added; metadata only, never content.
- [ ] Notification metadata stays metadata: the existing rule (category / app / sender, never the
      body) is the contract. Gmail's own subjects now come from the Gmail API directly
      ([todo_signal_inventory.md](todo_signal_inventory.md)), so the Deck notification stream does
      not need to carry them.

## Context: legacy notification channels are gone

ntfy.sh and Pushbullet were how ALFR3D sent notifications **before Kafka and the backend event
stream existed**. Neither is used any more (the ntfy.sh relay was removed 2026-09-16). The Deck
reports through the endpoints above, over the event stream; there is nothing to capture from
ntfy.sh or Pushbullet, and the `pushbullet` entities Home Assistant still exposes are leftovers,
excluded from the lake.

## Open questions

- A Deck that is off, in a drawer, or out of battery reports nothing. The learners must treat a
  missing report as *unknown*, not as a state (the same tri-state rule). Needs a freshness window.
- Several Decks exist (a phone and a tablet). Per-Deck rows keyed by install id; mapping an install
  id to a person is the missing link for "whose phone is this", and today's `user_id` on the
  location table is the only one.
