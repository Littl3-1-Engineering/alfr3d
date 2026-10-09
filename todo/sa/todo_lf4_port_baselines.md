# LF-4: Port the existing baselines to learners

> **Layer:** L1 learner · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-4

## Status: 🔲 Not started (planned 2026-10-09). Depends on LF-3.

## Scope

Each port runs in **shadow mode** first: the learner scores alongside the old rule and both
firings are logged for comparison for about a week. Then the rule switches to the learner's
inference and the old baseline code is deleted.

| Existing | Doc | Learner |
|---|---|---|
| `climate_deviation` (SA-9) | [todo_esphome_situational_awareness.md](todo_esphome_situational_awareness.md) | scalar sensor: robust median/MAD per hour |
| attention trend (SA-2) | [todo_attention_telemetry_history.md](todo_attention_telemetry_history.md) | scalar |
| rhythm break, device | [todo_rhythm_break_anomaly.md](todo_rhythm_break_anomaly.md) | session duration + time-of-event |
| departure anomaly (SA-3) | [todo_departure_anomaly.md](todo_departure_anomaly.md) | presence profile + time-of-event (circular) |
| household first/last activity (SA-10) | [todo_generalize_entity_baselines.md](todo_generalize_entity_baselines.md) | time-of-event + rate; the "unusual day" combination moves to LF-6 |

- [ ] One shadow-compare log per port, results recorded in the owning doc.
- [ ] After all ports: delete `compute_entity_baselines()` (in `service_sa` since LF-1a) and drop
      `entity_baselines` in a migration.

## Verify

Shadow logs reviewed per port; pytest and `lint.sh` green; no rule regresses on a known past firing
(e.g. SA-3's 2026-09-12 firing, SA-9's 2026-09-16 `climate_advisory`).
