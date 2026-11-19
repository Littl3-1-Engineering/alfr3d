# Layer 3 1/4: outcome evidence inventory (Phase 6, Phase 0 for this phase)

Prompt: Notion "Claude Code prompt: context-agnostic learning and layer 3", Phase 6; design page
"Layer 3: anticipation with earned autonomy (design, 2026-11-18)". Phase 6 is **design and outcome
capture only: nothing here executes a device command.** This note is the read-only inventory the
prompt asks for before anything is designed. Taken 2026-11-19 from the production MySQL (SELECTs
only) and the lake (bronze `ha_state_history`, `device_command_history`), no writes anywhere.

## Verdict in one paragraph

For **lights and switches** the evidence is real and the capture gap the prompt feared is mostly
closed: Home Assistant is connected, device commands and device events arrive, and **state changes
not caused by Alfr3d's API are captured** (49 of 168 switch transitions in 18 days had no matching
command). For **card feedback** the evidence is far too thin to learn from: 20 explicit
interactions ever, 6 of 112 impressions with an outcome, and no card currently proposes an action,
so there is nothing for a card to be "acted on" against. The acted-on linkage for cards is therefore
**not feasible today and I am not inventing one** (the prompt's stop rule); what the data does
support is conditional-frequency learning on switch behaviour, and outcome labels can only start to
exist once proposals exist (6a/6c).

## Card feedback (`card_interactions`, 111k rows)

| action | n | first | last |
|---|---|---|---|
| shown | 112,631 | 2026-08-31 | 2026-11-19 |
| impression | 112 | 2026-11-02 | 2026-11-19 |
| dismissed | 8 | 2026-08-31 | 2026-11-15 |
| tapped | 7 | 2026-10-12 | 2026-10-20 |
| acked | 4 | 2026-11-15 | 2026-11-18 |
| not_useful | 1 | 2026-11-16 | 2026-11-16 |

- 110,346 of the `shown` rows have no surface (the awareness loop logging its own cycles, not a
  client seeing a card); only 2,285 come from a client (Deck 2,224, web 61).
- **Explicit outcomes per rule (all time):** `household_composition` 10 (7 tapped, 2 acked, 1
  dismissed), `rhythm_break_anomaly` 5 (4 dismissed, 1 acked), `time` 4 (2 dismissed, 1 acked, 1
  not_useful), `music` 1. Three of four rules are under "a handful".
- Only **6 of the 112 impressions** have a later explicit outcome with the same `impression_id`.
- `detail` is used once (`already_knew`, on the one `not_useful`).
- The design page's "46 impressions" figure is stale (112 now); its "acted-on linkage re-check
  about 2026-12-28" stands.

## Device commands and events

- `device_command_history`: **155 rows, all successful, all since 2026-11-02**: Home Assistant 141
  (135 `user` origin, 6 `system`), ESPHome 14 (`turn_on`, user). Mostly `switch.*` lamps and shelf
  lights; the most active days have 16 commands (Nov 14, 15).
- The lake holds 2 more Home Assistant commands (2026-10-10 and 2026-10-13) that the MySQL table
  does not show. Unexplained, immaterial to the verdict, recorded.
- `household_events` device rows: `turned_on` 106, `turned_off` 92 (2026-09-16 to now; **76 off and
  71 on in November alone**), `set` 59 (last on 2026-10-09: no brightness events since). The
  prompt's worry that these were zero while every HA device was offline is resolved: **they arrive**.
- `household_events` also holds `routine:executed` 331, `track:play_start` 13,694, `user:came_online`
  870 / `went_offline` 852, `sender:messaged` 2,482, `sender:called` 139.

## Is a state change not caused by an API command captured? Yes, for HA switches

Bronze `ha_state_history` (34,250 rows from 2026-09-30) includes the `switch` domain: 6 entities,
246 rows, **168 on/off transitions between 2026-11-02 and 2026-11-19**. Matching each transition to a
Home Assistant command for the same entity within 3 minutes (same direction):

- **119 explained** by an API command; **49 not**: a wall switch, a physical button, or a Home
  Assistant automation or schedule. By entity: `office_armoire_lights` 22 (rapid on/off bursts, e.g.
  Nov 5 00:28 to 00:30: hand toggling), `living_room_little_lamp_socket` 10 (a regular rhythm: off
  about 04:30 and on about 22:00 UTC on consecutive days, which looks like a schedule or automation),
  `living_room_polica_lights` 6, `computer_lamp_socket_1` 5, `little_lamp_socket` 5, `teckin4_socket_1`
  1.
- 27 commands have no matching transition (the command did not change the state, or the change was
  not captured).
- So "learning when lights usually go on needs the state change, whoever caused it" is **already
  satisfiable** for the 6 HA switches. Gaps that remain: only switches are present (no `light`
  domain entity has a history row, so no brightness), and only 6 entities of 53 smarthome devices;
  ESPHome devices are controlled (14 commands) but their own state changes are not in this history.
  Whether `last_changed` is the true change time (it carries sub-second stamps) is assumed from the
  data, not proven.

## What this means for the rest of Phase 6

1. **6a outcome labels** can define acted-on / ignored / undone / rejected, but there is **no card
   or proposal for them to label yet**; the first real labels will come from the first proposals
   (6c) at level 0. Today's 20 explicit card outcomes can seed a replay count per rule and no more.
2. **6b predictors:** switch behaviour is the one place with enough data for conditional frequency
   counts (168 transitions in 18 days: too few for anything but a coarse "this lamp is usually on at
   this hour" within one household). A proof predictor is plausible but small-n; it must carry the
   same sample floors and "insufficient evidence" outcome as the screen.
3. **Phase 4's screen is the right tool** to test whether weather, calendar or presence relate to
   those transitions, as a declared target (not built here).

## Not done / open

- Nothing designed yet: 6a to 6d wait for the owner's review of this inventory.
- The owner-approved replacement wording for the "nothing actuates" rule is NOT applied anywhere; the
  diff is shown first (6d).
