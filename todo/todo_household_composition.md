# Deck: Household Composition Awareness

## Status: ✅ Built 2026-08-28 (not yet on-device/live verified)

Backend: `MyDaemon.check_household_composition()` + DISPLAY_RULES registration in
`alfr3ddaemon.py`, reusing `device.user_id` as the known/unknown signal (no new table -- see
"Deviation" section below, which was written before implementation and held up). 4 new tests in
`tests/test_daemon_service.py::TestCheckHouseholdComposition`, plus the `DISPLAY_RULES`
enumeration tests updated for the 11th (now 13th, after the other two Deck features) rule. Deck:
new `HouseholdCompositionInsight` in `SituationalInsights.kt` + `household_composition`
`ContextRule` in `ContextRules.kt` (Presence tier, priority -2, branches urgent/ambient styling
on `profile.urgent`). Compiles clean, ktlint/detekt clean (no Android emulator available this
session, so on-device behavior is unverified).

Not built: quip-tone/cast-volume/camera-notification-aggression modulation (see "Explicitly not
built today" below -- still accurate).

---

## Status: 🔲 Not started (historical, see above)

## Overview

Extend today's boolean occupancy (someone's home / nobody's home) to a relational state: which
household members' claimed devices are on the network right now, vs. how many unclaimed/unknown
MACs are also present. Scoped in Notion 2026-08-28 alongside four other Deck data-feature
milestones; this is the cheapest of the five to ship.

## Deviation from the original Notion scope

The Notion milestone description called for "a new known-device registry table." Reading the
actual schema first: `device.user_id` (FK → `user`) already means exactly "this MAC is claimed by
a household member" — `update_or_create_device()` in `service_device/app.py` (the existing
15-minute `arp-scan` sync, see `check_lan()`) never sets `user_id` on discovery, so every
auto-created device starts unclaimed, and only the existing device-management UI sets it. That's
already the known/unknown signal this feature needs. No new table, no schema change at all —
purely new query + DISPLAY_RULES logic. The Notion milestone description will be updated to match
once this ships.

## Design

- New `MyDaemon.check_household_composition()` in `services/service_daemon/alfr3ddaemon.py`,
  same shape as the existing `check_gatherings()` (raw `pymysql`, no ORM, matching every other
  DISPLAY_RULES check in this file):
  - Query: online devices (`device.state = 'online'`) LEFT JOIN `user` on `device.user_id =
    user.id`. Known = `user_id IS NOT NULL` (and not the `unknown`/`alfr3d` placeholder rows, per
    the exclusion precedent in `devices.py:49`). Unknown = `user_id IS NULL`.
  - Card content: known-member names/count, unknown-MAC count.
  - Priority is computed, not fixed: `6.2` (ambient — same tier as `mood`) when every online
    device is claimed; `2.3` (elevated — same tier as `event`) when ≥1 unclaimed device is
    online. This is the "unknown-device branch doubles as a lightweight security card" behavior
    from the original scope note.
  - Card shape: `{"mode": "household_composition", "content": str, "priority": float,
    "known_count": int, "unknown_count": int, "urgent": bool}`.
- Register `("household_composition", <dynamic>, "check_household_composition")` in the
  `DISPLAY_RULES` tuple. (The tuple's stated priority is just for iteration/logging order per its
  own comment — the card's real priority is whatever the method returns, same as every other
  entry with a comment explaining its slot.)
- Deck (`alfr3d_deck`): new insight type for `mode == "household_composition"` in
  `contextawareness/SituationalInsights.kt`, registered in `contextawareness/ContextRules.kt`'s
  `DEDICATED_SITUATIONAL_MODES` set with a dedicated icon (calm icon for the normal case, a
  distinct "alert" icon when `urgent == true`).

## Explicitly not built today

Quip-tone, cast-volume, and camera-notification-aggression modulation from this signal (mentioned
in the original Notion scope) — `get_random_quip(quip_type)` takes no context parameter today,
and every call site would need threading a tone/urgency argument through. Real scope, not a
one-line addition. This todo only builds the detection + card; wiring it into personality/audio
output is a distinct future pass.

## Related

- `todo_user_management.md` — owns the device-claiming UI this feature's "known" signal depends
  on.
- `todo_smartthings_generic_control.md` / device-registry work generally — same `device` table.
