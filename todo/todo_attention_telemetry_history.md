# SA-2: Retain launcher attention telemetry history

## Status: 🟢 Built and live-verified 2026-08-29; deployed to production 2026-08-30

**Deployed to the household's real NUC 2026-08-30** via PR #156 (squash-merged to `main`). A real
`mysqldump` backup was taken first; migrations applied cleanly through 0035; affected services
rebuilt and redeployed; verified live with a clean cycle and a real authenticated API response.

Wave 1 of the situational-awareness expansion (see the Notion "Situational & Context Awareness
— Capability Audit" page), following [[todo_household_event_log]] (SA-11). Revised in scope on
2026-08-29: `surface-state` history moved to SA-11's `household_events` (it's a discrete
state-change, not a rollup); this item only covers `attention-telemetry`'s pre-aggregated
rolling-window reports.

## Phase 0 findings

- Report cadence confirmed by reading `AttentionTelemetryReporter.kt` in `alfr3d_deck`: every
  15 minutes (`REPORT_INTERVAL_MS`), flushing `AttentionTelemetryStore.snapshotAndReset()`.
  ~96 reports/day/household — trivial row volume next to `household_events`.
- `dwell_by_category_ms` keys are `WindowManager` layout keys (`"terminal"`, `"media"`, etc.),
  not per-app/per-URL — confirmed no PII by reading `AttentionTelemetryStore.kt`'s own doc
  comment and `recordWindowFocus()`'s call sites.
- Next-free migration number confirmed as **0030** at write time (chain was at 0029 after
  SA-11 landed this session).

## Phase 1 — History table

`attention_telemetry_history` (migration 0030): `unlock_count`, `switch_count`,
`dwell_by_category_ms` (JSON), `window_start_ms`, `window_end_ms`, `reported_at`. Index on
`reported_at`. Write-through added to `POST /api/context/attention-telemetry`
(`routes/context.py`) inside the same `db_connection()` block as the existing `config` upsert —
one commit, both destinations, `config` snapshot behavior unchanged.

Retention: `prune_attention_telemetry_history()` in `alfr3ddaemon.py`, scheduled every 6h
alongside `compute_entity_baselines()`/`prune_household_events()`. Default 90 days
(`ATTENTION_TELEMETRY_HISTORY_RETENTION_DAYS`), same default as SA-11 though actual volume here
is far lower (one row per 15-min report vs. one per `event-stream` message).

## Phase 2 — Trend-aware checks

`_attention_telemetry_trend()`: queries `attention_telemetry_history` over the last
`ATTENTION_TREND_LOOKBACK_DAYS` (14), returns the household's median `switch_count`/
`unlock_count` plus a sample count, or `None` below `ATTENTION_TREND_MIN_SAMPLES` (200, ~2 days
of reports) or on a DB error.

`check_attention_focus()`/`check_wind_down_signal()` now compare against
`max(fixed_threshold, household_median + grace)` when trend is available
(`ATTENTION_FOCUS_TREND_GRACE_SWITCHES=5`, `WIND_DOWN_TREND_GRACE_UNLOCKS=2` — same "small grace
window" reasoning as `RHYTHM_BREAK_GRACE_MINUTES`), falling back to the original fixed
`ATTENTION_FOCUS_MIN_SWITCHES`/`WIND_DOWN_MIN_UNLOCKS` thresholds unchanged below the sample
floor. The `media_fraction` checks are untouched — they're already a normalized ratio, not a raw
count prone to household-scale variance the same way.

## Live verification (2026-08-29, real docker-compose stack)

- Ran `alembic upgrade head` (0029 → 0030) against the live dev MySQL; confirmed schema.
- Minted a real JWT inside the running `service-api` container and POSTed a real
  `attention-telemetry` report over HTTP — confirmed it landed in both `config` (unchanged
  shape) and `attention_telemetry_history` (new row, correct values).
- Confirmed `check_attention_focus()` fired an `attention_focus` card for that report
  (`switch_count=22 >= 15` fixed threshold, trend not yet active with only 1 history row) —
  visible in a real published `situational-awareness` cycle.
- Seeded 200 synthetic history rows (`switch_count=30, unlock_count=3`) directly into the live
  table, confirmed the *next* cycle's `attention_focus` card was correctly **suppressed**
  (`22 < max(15, 30+5=35)`) — proves the trend-vs-fallback switch works against the real
  database and the real `DISPLAY_RULES` pipeline, not just mocked unit tests. Cleaned up the
  seed rows afterward.
- `prune_attention_telemetry_history()` ran cleanly against the real table (0 rows pruned,
  correct 90-day cutoff).

## Not yet done

- **Row-growth measurement over real time.** Verified the mechanism works; the ~96/day
  estimate from the report cadence hasn't been confirmed against an actual multi-day run.
- **Android on-device verification** of the launcher side (`AttentionTelemetryReporter`/
  `AttentionTelemetryStore`) — still outstanding per `todo_attention_telemetry.md`; this doc
  only verified the backend's receiving/storing/trend-computing side.
- Tuning `ATTENTION_TREND_MIN_SAMPLES`/grace constants against real telemetry once enough
  accumulates — currently conservative starting points, same caveat as every other threshold in
  this file.

## Out of scope (per the task doc, unchanged)

- `surface-state` history — SA-11's job.
- Any change to `alfr3d_deck`'s own collection logic or permission surface.
- Exposing this history through the API or dashboard.
- Cross-user attention correlation (SA-10).
