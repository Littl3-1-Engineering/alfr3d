# Situational-Awareness Data Retention — 3-Year Horizon & Disk Sizing

## Status: 🟢 Implemented and deployed 2026-09-13. All SA event-log tables now retain 2 years; correction below to a claim in the original version of this doc.

**The ask:** the current 180-day retention doesn't span a full year of seasons (winter through
summer), across which household dynamics shift drastically — arrival/departure times move with
daylight, presence patterns change with school/work calendars, energy use shifts. Explore what a
3-year retention horizon would actually cost in disk, based on today's real growth rate.

**Correction to this doc's original version:** it claimed `device_location_history` had "grown
unbounded since it shipped" with no cleanup mechanism. That was wrong, and the error was mine —
found by grepping only Python source for `DELETE`/cleanup, which missed a MySQL-native scheduled
`EVENT` created directly in the table's own migration SQL. Checked against the live production
DB before writing this correction: `cleanup_device_location_history_event` exists, is `ENABLED`,
and has actually executed (`SHOW EVENTS`/`information_schema.EVENTS` confirmed it). The table
already had real 180-day retention. The table that was **genuinely** unbounded — no mechanism of
any kind, in Python or SQL — turned out to be `card_interactions`. See the corrected table below.

## First finding: "180 days" is not one policy — it's three different things, one of them fictional

Checked every retention mechanism in the codebase and the live production DB rather than trusting
comments. The real state, per table:

| Table | Stated policy | Actual mechanism (as of 2026-09-12) | Now (2026-09-13) |
|---|---|---|---|
| `device_history` | 180 days | Real — monthly RANGE partitions, `DROP PARTITION` via a daily scheduled event (`maintain_device_history_partitions_event`, migration 025) | **Unchanged** — out of scope, see "What was deliberately not touched" below |
| `household_events` | 90 days | Real — row-by-row `DELETE ... WHERE occurred_at < cutoff` in the daemon's daily maintenance pass | **730 days** |
| `attention_telemetry_history` | 90 days | Real — same row-by-row `DELETE` pattern | **730 days** |
| `device_location_history` | 180 days | Real — a MySQL-native scheduled `EVENT` (`cleanup_device_location_history_event`, migration 036), confirmed `ENABLED` and actually executing on the live NUC | **730 days** (migration 038/041) |
| `card_interactions` | (none stated) | **None — genuinely unbounded**, the one table this label actually fit | **730 days**, new `prune_card_interactions()` (migration-free, pure Python + schedule) |
| `entity_baselines` | (none stated) | None | **Deliberately still none — see below, this table doesn't need it** |

`entity_baselines` is an **upsert** table (`UNIQUE KEY (entity_type, entity_id)`, recomputed in
place every 6 hours by `compute_entity_baselines()`) — one row per tracked entity, not one row
per event. Its size is bounded by how many entities the household has, not by time, so it was
never actually part of the "unbounded growth" problem and gets no retention added.

## Real growth rate, pulled from the live NUC database (2026-09-13)

Not modeled — queried directly (`information_schema.tables`, `MIN`/`MAX` on each table's own
timestamp column, current partition sizes for `device_history`).

| Table | Rows now | Size now | Date range sampled | Rate | Bytes/row |
|---|---|---|---|---|---|
| `device_history` | 2,454,066 | 502.5 MB | 2026-03-16 → now (~181 days, not yet steady-state) | ~30,400 rows/day (Aug+Sep partitions) | ~214 B |
| `household_events` | 22,170 | 5.03 MB | 2026-08-30 → now (14.0 days) | 1,584 rows/day | 243 B |
| `card_interactions` | 8,210 | 0.89 MB | 2026-08-31 → now (12.3 days) | 668 rows/day | 115 B |
| `attention_telemetry_history` | 512 | 0.09 MB | 2026-08-30 → now (14.0 days) | 36.6 rows/day | 208 B |
| `device_location_history` | 61 | 0.06 MB | 2026-09-11 → now (2.0 days) | ~30/day | **unreliable, see caveat** |

**Caveats on this data, stated plainly rather than smoothed over:**
- `device_history`'s June partition (1.08M rows/30d ≈ 36k/day) and July partition (38k rows/31d ≈
  1.2k/day) disagree by 30x — a real outage or bug sometime in July, not a rate change. Aug+Sep
  (44 days, no visible discontinuity) is the rate used above as the more trustworthy baseline.
- `device_location_history` has only 2 days of real data (it shipped 2026-09-10/11) from what is
  so far a single reporting device. Its per-row size estimate is dominated by InnoDB's fixed
  page/extent overhead at this row count, not a real steady-state figure — re-measure this table
  specifically once it has a few weeks of multi-device data before trusting a projection from it.
- All rates assume today's usage pattern holds for 3 years, which a household growing (more
  residents, more Deck devices, more IoT entities) will not do. Treat every number below as a
  floor, not a ceiling.

## What 3 years actually costs

Extrapolating the rates above linearly to 1,095 days, **with no retention cap** (today's actual
state for two of these tables already):

| Table | 3-year rows | 3-year size |
|---|---|---|
| `device_history` | ~33.3M | **~7.1 GB** |
| `household_events` | ~1.73M | ~421 MB |
| `card_interactions` | ~731k | ~84 MB |
| `attention_telemetry_history` | ~40k | ~8 MB |
| `device_location_history` | too little data to trust a 3-year figure yet | likely tens of MB, re-measure |
| **Combined SA-specific tables (excludes `device_history`)** | | **~510 MB** |

**The real finding here:** extending retention on the tables that are actually "situational
awareness" in the narrow sense — gatherings, card interactions, attention telemetry, location —
costs on the order of **half a gigabyte for a full 3 years**, combined. That is cheap enough that
disk size is not the reason to cap it at 180 days; if 180 days is kept, it should be a deliberate
privacy/relevance decision, not a storage-driven one.

**`device_history` is the actual disk cost**, by two orders of magnitude, and it is not narrowly
"situational awareness" — it is raw device online/offline presence polling, which several SA
rules read but which was never scoped to this todo's original question. It already has the right
mechanism (partition + `DROP PARTITION`) for exactly the reason migration 025 states: the
row-by-row `DELETE` pattern the other two enforced tables still use "never shrinks the InnoDB
tablespace and gets more expensive as the table grows." If this household's own multi-year
context needs the *presence history* to go back further too (not just the SA tables above), that
is where the real multi-GB decision lives, separate from the SA tables the original question
named.

## Headroom this has to fit into

The NUC currently running this deployment: **37 GB free of 109 GB (65% used)**. A 3-year SA
extension (~510 MB) is noise against that. Even the full `device_history` 3-year figure (~7.1 GB,
unbounded) would fit comfortably today — but 67 GB is already used by something other than these
tables (container images, Kafka/Zookeeper logs, MySQL's own overhead), worth a separate look if
that 65% keeps climbing on its own.

**This also has a hardware angle worth connecting**: `todo_alfr3d_kit_pi5_bom.md` recommends an
NVMe SSD via M.2 HAT+ for the sellable Kit but does not fix a capacity — it was scoped around RAM
and CPU, not disk growth. This todo's numbers are the input that BOM decision was missing.

## Why the seasonal argument is sound independent of disk cost

180 days is chosen for a reason unrelated to bytes — it is roughly six months, so a fixed calendar
window drawn today is guaranteed to miss one of winter or summer entirely, and a household's
actual rhythm-break/rhythm-baseline detection (`entity_baselines`, `check_rhythm_break_anomaly`)
is exactly the kind of signal that should be comparing "this winter evening" against "last winter
evening," not against a rolling half-year that never contains both. The disk-cost finding above
means there is no longer a resource reason not to fix this — the only remaining question is which
of the options below.

## Options, given the numbers above

1. **Extend the SA-specific tables to 1 year (or 3), leave `device_history` at 180 days.** Cheap
   (~510 MB at 3yr), and gets the seasonal comparison the household dynamics actually need without
   touching the one table where cost is real. Simplest change: raise
   `HOUSEHOLD_EVENTS_RETENTION_DAYS`/`ATTENTION_TELEMETRY_HISTORY_RETENTION_DAYS`, add a real
   cleanup for `device_location_history` and `card_interactions` at the same horizon rather than
   leaving them uncapped by accident.
2. **Downsample past a shorter full-fidelity window.** Keep 180 days of raw rows, collapse older
   data into daily/weekly aggregates for the specific baselines that need multi-season comparison
   (a much smaller table than raw history). More engineering, smallest disk footprint, and the
   right shape if `device_history` itself is ever pulled into a longer horizon.
3. **Extend `device_history` too**, if presence history specifically (not just the four SA tables)
   needs to span seasons. This is the ~7 GB decision, and should follow the same partition +
   `DROP PARTITION` pattern already proven there rather than inventing a new mechanism.

## Open questions for the user

- Is the 3-year ask about the four SA-specific tables only, or does `device_history` (presence)
  need the same horizon? That's the difference between ~500 MB and ~7 GB.
- Full-fidelity retention, or full-fidelity for a shorter window (say 180 days) with aggregated
  seasonal baselines kept longer? Option 2 above is more work but scales better if the household
  or the Kit's future customers run this for years, not one season.
- Should the currently-uncapped tables (`card_interactions`, `device_location_history`,
  `entity_baselines`) get *any* ceiling, even a generous one, purely so "uncapped" never becomes
  "unbounded and forgotten" the way `device_location_history`'s stale migration comment already
  did once?

## Implemented 2026-09-13

**`prune_card_interactions()`** — new function in `alfr3ddaemon.py`, identical shape to
`prune_household_events`/`prune_attention_telemetry_history`, scheduled on the same 6-hourly
cadence. `decide_displays()`'s suppression pass only ever reads the most recent
`CARD_SUPPRESSION_HISTORY_LIMIT` rows per card identity, so pruning older rows changes nothing
about suppression behavior — this exists purely to bound disk, same as its two siblings.

**Retention raised to 730 days (2 years)** for `household_events`,
`attention_telemetry_history`, and `card_interactions`, all off one new shared constant
(`SA_EVENT_LOG_RETENTION_DAYS_DEFAULT = 730`) so the three don't drift independently. Each
remains individually overridable via its own existing env var
(`HOUSEHOLD_EVENTS_RETENTION_DAYS`, etc.).

**`device_location_history` raised to 730 days** via migrations 037/038 (raw SQL) wrapped by
alembic 0040/0041 — `DROP EVENT` + `CREATE EVENT` with `INTERVAL 730 DAY` replacing `180 DAY`.
This table's retention lives in a MySQL-native scheduled event, not a Python constant like its
three siblings; that asymmetry is real and this fix didn't try to unify it, since doing so would
mean moving the mechanism itself, a bigger change than the number this todo was asked to change.
Confirmed the event is owned by this deployment's own migration user (not `root`/`SYSTEM_USER`,
unlike `device_history`'s original event), so `DROP`+`CREATE` from a normal migration is safe.

**`sa_storage_metrics`** (migration 040) — a new table, and `record_sa_storage_metrics()`
scheduled once daily, snapshotting row count + data/index bytes for
`household_events`/`card_interactions`/`attention_telemetry_history`/`device_location_history`/
`entity_baselines`/`device_history` (the last two included for context — the actual growth
driver and the deliberately-excluded upsert table, respectively). This is the "track disk usage
growth" ask: rather than re-deriving a projection from a short window again later, the real
numbers are now a running time series —

```sql
SELECT table_name, recorded_at, row_count,
       ROUND((data_bytes+index_bytes)/1024/1024, 2) AS size_mb
FROM sa_storage_metrics ORDER BY table_name, recorded_at;
```

— which is exactly what will let ALFR3D's own future SA rules eventually reason about
multi-season baselines using data that was actually retained long enough to compare against,
which is the stated point of doing any of this.

**Verified before deploying**, not just unit-mocked: applied migrations 040/041 against a real
local MySQL 8.0 (via this repo's own `docker-compose.yml`), confirmed `sa_storage_metrics`'s
schema and the recreated event's `SHOW CREATE EVENT` text directly, tested the downgrade path
(correctly restores `180 DAY` and drops the table), seeded real stale/fresh rows in
`card_interactions` and ran `prune_card_interactions()`/`record_sa_storage_metrics()` against
them directly (not mocked) to confirm the cutoff logic and the metrics insert both do what their
tests assert. 568 tests pass (6 new), ruff/black clean.

## What was deliberately not touched

**`device_history` stays at 180 days.** It is presence/online-status polling, not narrowly
"situational awareness," and it is the one table where extending retention is a real multi-GB
decision (~7.1 GB at 3 years unbounded, per the projection above) rather than the ~500 MB the
four SA tables cost combined. The user's instruction was scoped to "SA tables"; this one wasn't
named, and changing it needs a separate, explicit decision given the cost difference.

## Moved fully DB-native, 2026-09-13

User instruction after the above shipped: keep retention enforcement at the database level, not
the service level — "what can be done in db should be solved in [db]," not left depending on a
long-running application process. Concretely: the three Python `schedule`-job prune functions
this todo added a few hours earlier (`prune_household_events`, `prune_attention_telemetry_history`,
`prune_card_interactions`) and the daily `record_sa_storage_metrics()` were all deleted from
`alfr3ddaemon.py` entirely, along with their scheduling and their four Python retention
constants — no dead code, no leftover configuration knob for something the database now owns.

In their place, migration 039 (alembic 0042) creates four scheduled `EVENT`s living inside MySQL
itself — `cleanup_household_events_event`, `cleanup_attention_telemetry_history_event`,
`cleanup_card_interactions_event`, and `record_sa_storage_metrics_event` (which calls a new
`record_sa_storage_metrics_proc()` stored procedure, since the metrics recording loops over a
fixed table list — the same cursor-over-a-derived-table shape
`maintain_device_history_partitions()` already uses for its own partition list). This brings all
four in line with what `device_location_history`'s own retention already was from the start: a
MySQL-native EVENT, not application code.

**The real win, not just a style preference**: these now run inside the database engine's own
scheduler, so retention and growth-tracking both keep working through a `service-daemon`
redeploy, crash, or extended downtime — previously, every one of the four silently stopped the
moment that one container was unhealthy, with nothing else in the stack aware it had happened.

**The accepted tradeoff, stated plainly**: the 730-day windows are now literals in each EVENT
body, the same way `device_location_history`'s always was. There is no more env-var override —
changing any of these four numbers is a migration from here on, not a config change. Given the
choice was explicitly "push it to the layer that can enforce it without depending on a service
being alive," this is the correct trade, but it is a real one and worth remembering next time a
retention window needs tuning.

**Verified against real local MySQL 8.0, not just the SQL text**: applied migration 042, called
`record_sa_storage_metrics_proc()` directly and confirmed real rows landed in
`sa_storage_metrics`, seeded a genuinely stale `card_interactions` row and confirmed the exact
`DELETE` each event body runs removes it while leaving a fresh row untouched, tested the
downgrade path removes all four events and the procedure, then re-upgraded to head. Also directly
observed (not assumed) that `CREATE EVENT ... ON SCHEDULE EVERY 1 DAY` with no explicit `STARTS`
fires once immediately at creation before its first real 24-hour interval — useful to know before
reading a "why did this table already have a row right after I ran the migration" question later.
558 tests pass (10 removed with the deleted Python functions), ruff/black clean.
