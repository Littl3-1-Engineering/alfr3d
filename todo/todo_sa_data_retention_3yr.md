# Situational-Awareness Data Retention — 3-Year Horizon & Disk Sizing

## Status: 🔲 Not started — exploration requested 2026-09-12, grounded in live production data

**The ask:** the current 180-day retention doesn't span a full year of seasons (winter through
summer), across which household dynamics shift drastically — arrival/departure times move with
daylight, presence patterns change with school/work calendars, energy use shifts. Explore what a
3-year retention horizon would actually cost in disk, based on today's real growth rate.

## First finding: "180 days" is not one policy — it's three different things, one of them fictional

Checked every retention mechanism in the codebase and the live production DB rather than trusting
comments. The real state, per table:

| Table | Stated policy | Actual mechanism | Real cadence |
|---|---|---|---|
| `device_history` | 180 days | **Real** — monthly RANGE partitions, `DROP PARTITION` via a daily scheduled event (`maintain_device_history_partitions_event`, migration 025) | Enforced |
| `household_events` | 90 days | Real — row-by-row `DELETE ... WHERE occurred_at < cutoff` in the daemon's daily maintenance pass | Enforced |
| `attention_telemetry_history` | 90 days | Real — same row-by-row `DELETE` pattern | Enforced |
| `device_location_history` | **"180 days" per the migration's own comment** | **Does not exist.** `_LOCATION_MAX_FIX_AGE_DAYS = 180` in `routes/context.py` only rejects an *incoming* fix claiming to be older than 180 days at ingest time — it has never deleted a row. This table has grown unbounded since it shipped. | **None** |
| `card_interactions` | (none stated) | None | **None** |
| `entity_baselines` | (none stated) | None | **None** |

So two of the tables most relevant to "situational awareness" already have no ceiling at all —
extending retention on those costs nothing extra to implement, because there is nothing currently
capping them. The one table whose comment claims a 180-day policy that would matter here
(`device_location_history`) turns out to have never had one; worth fixing that gap regardless of
what this todo decides, since "documented but not implemented" is worse than either extreme.

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
