# SA-4: Shared per-cycle context frame

## Status: 🟢 Built and live-verified 2026-08-29; deployed to production 2026-08-30

**Deployed to the household's real NUC 2026-08-30** via PR #156 (squash-merged to `main`). A real
`mysqldump` backup was taken first; migrations applied cleanly through 0035; `service-daemon`
rebuilt and redeployed; verified live with a clean cycle and a real authenticated API response.

Wave 2 of the situational-awareness expansion, following Wave 1 (SA-11, SA-2, SA-1, SA-7).
A refactor, not a new capability — turns `decide_displays()`'s 15 independent snapshot readers
into rules that share one context frame, then adds exactly one new rule (Phase 3) as proof the
frame earns its keep.

## Phase 0 — the exact duplicates found

Read every `check_*` method's body directly (not just its docstring) to build the real
inventory the task doc asked for:

- **`environment` table read 3x/cycle**, same row, different columns each time:
  `check_weather` (city/description/low/high/subjective_feel), `check_weather_advisory`
  (forecast_rain_probability), `check_gatherings` (description/subjective_feel).
- **The environment's timezone read 4x/cycle** via `db_utils.get_env_local_time()`, each call
  opening its own fresh connection: `check_gatherings`, `check_party_advisory`,
  `check_wind_down_signal`, `check_mood`.
- **`calendar_utils.get_upcoming_events()` called 2x/cycle**: `check_events`,
  `check_focus_needed` — the task doc's own named example.
- **`spotify_utils.get_playback_state()` called 2x/cycle**: `check_now_playing`,
  `check_party_advisory` — confirmed shareable (both just need current playback state);
  `get_track_energy()` stays separate, a different Spotify endpoint depending on the track id
  the shared fetch resolves.
- **The `config` table's `music_now_playing` row read 2x/cycle**: `check_now_playing` (to
  detect a change) and `check_cross_surface_continuity` (to check for a recent pause) — not
  named in the task doc but found by reading the actual code, same category of duplicate.
- **`MyDaemon._read_fresh_attention_telemetry()`/`._attention_telemetry_trend()` each called
  2x/cycle**: `check_attention_focus`, `check_wind_down_signal` — the trend query (a 14-day
  history scan) is the single most expensive duplicate found.

## Phase 1 — the frame

New `services/service_daemon/utils/context_frame.py`: `ContextFrame` (plain class, every field
defaults to `None`) and `LauncherContext` (sub-namespace: `surface_state`/`attention_snapshot`/
`attention_trend`), plus two brand-new standalone fetchers that didn't exist as reusable
functions before (`fetch_online_devices()`, `fetch_environment_snapshot()` — the latter is the
env-table dedup; a third, `fetch_smarthome_online()`, was added for Phase 3).

`MyDaemon.build_context_frame()` (kept in `alfr3ddaemon.py`, not `context_frame.py` — it needs
to call `MyDaemon`'s existing private helpers, `_read_config_json`/
`_read_fresh_attention_telemetry`/`_attention_telemetry_trend`, rather than reimplement them)
assembles one frame per cycle: `now`, `local_dt`/`day_mood`, `upcoming_events`,
`online_devices`, `smarthome_online`, `environment`, `playback`, `persisted_now_playing`,
`launcher_context`. Every field is built in its own `try`/`except`, logged and left `None` on
failure — one integration failing can't take down unrelated fields or the cards that depend on
them.

## Phase 2 — migrated rules

`decide_displays()` builds the frame once, then calls every `check_*` with it (`getattr(self,
check_name)(frame)`) — every rule's signature gained a `frame` parameter, whether or not it
uses a shared field. Rules that had no duplicate to eliminate keep their own unique query but
still read `frame.now` for the single shared timestamp:
- `check_rhythm_break_anomaly` — its device/`entity_baselines` join isn't duplicated anywhere
  else, kept as its own query.
- `check_emails`/Gmail, `check_gatherings`'s own guest-count query,
  `check_cross_surface_continuity`'s routines-edited query, `check_party_advisory`'s
  `get_track_energy()` call — all unique, all kept.

No rule's firing logic or priority changed — this phase is pure plumbing.

## Phase 3 — the proof case

`check_empty_house_still_on()` (priority 2.4, between `event` and `rhythm_break_anomaly`):
fires when no claimed household member's device is online (`frame.online_devices`), at least
one smart-home device still is (`frame.smarthome_online`, new fetcher backed by
`smarthome_devices.online` — a plain boolean column `ha_utils.sync_devices()` already
maintains, not something parsed out of the `last_state` JSON blob), and it's evening or night
(`frame.day_mood` — unremarkable during the day, when "everyone's out" is the normal state).
Three frame fields at once, genuinely impossible to write before this refactor existed.
Observation only, like every other card in this file.

## Before/after: DB operations per cycle

Counting distinct connection-acquisition events across all `check_*` methods (excludes
conditional writes that don't run every cycle, e.g. `check_now_playing`'s config write on an
actual track change):

| | Before | After |
|---|---|---|
| `environment` table reads | 3 | 1 |
| Timezone lookups (`get_env_local_time`) | 4 | 1 |
| Calendar (`get_upcoming_events`) | 2 | 1 |
| Spotify playback-state fetches | 2 | 1 |
| `music_now_playing` config reads | 2 | 1 |
| Attention snapshot config reads | 2 | 1 |
| Attention trend queries (14-day scan) | 2 | 1 |
| Unique per-rule queries (gatherings, rhythm-break, cross-surface routines) | 3 | 3 (unchanged) |
| **Total DB operations/cycle** | **~20** | **~13** (~35% fewer) |

Spotify API calls drop from up to 3 (2 duplicate playback-state fetches + 1 audio-features) to
2 (1 shared playback-state fetch + 1 audio-features) whenever both `now_playing` and
`party_advisory` fire in the same cycle.

## Testing

Every existing `TestCheckXXX` class was rewritten to pass a `_make_frame(...)` test double
instead of mocking each rule's own DB calls — a genuine simplification in several cases
(`TestCheckHouseholdComposition`, `TestCheckWeather`/`TestCheckWeatherAdvisory` no longer need
`pymysql` mocking at all; `TestCheckAttentionFocus`/`TestCheckWindDownSignal` construct plain
dicts instead of JSON-encoded mock rows). New coverage: `TestContextFrameFetchers` (the two new
standalone fetchers), `TestBuildContextFrame` (the Phase 1 acceptance criterion — a simulated
Spotify failure doesn't prevent `frame.now`/`frame.day_mood`/`frame.environment` from building,
and `check_time`/`check_weather` still produce cards), `TestCheckEmptyHouseStillOn` (the new
rule, all four gating conditions). `TestReadFreshAttentionTelemetry` was split out as its own
class to preserve the staleness-cutoff coverage that used to live inside
`TestCheckAttentionFocus`. `DISPLAY_RULES`'s own end-to-end tests
(`TestDecideDisplays`/`TestCardSuppression`) updated for the 16th rule.

**A real regression caught and fixed via cross-file test pollution**: `TestDecideDisplays`'s
autouse fixture originally mocked only `pymysql.connect`, which used to be enough (its
stub-based tests never touched real DB code). Once `decide_displays()` started calling the
real `build_context_frame()` unconditionally, that fixture let a real, unmocked
`db_utils.get_env_local_time()` call through to `services.common.db_pool`'s process-global
connection pool. That pool eagerly creates its `mincached` physical connections via whatever
`pymysql.connect` is bound to *at the moment it's first constructed* and caches them for the
rest of the pytest process — so the first `TestDecideDisplays` test to run permanently poisoned
the shared pool with mock connections, silently breaking two unrelated tests in
`test_personality.py` later in the same session (a `TypeError: unsupported type for timedelta
hours component: MagicMock`, since the poisoned pool's mock cursor's `fetchone()` returned a
`MagicMock` instead of a real timezone-offset int). Fixed by stubbing
`MyDaemon.build_context_frame()` itself in that fixture instead of mocking each of its
individual dependencies — more correct (these tests don't care how the frame gets built at
all) and immune to future frame fields needing the same treatment.

## Live verification (2026-08-29, real docker-compose stack)

- Rebuilt and recreated `service-daemon` with the new code; no migration needed (this phase
  added no schema).
- **Caught a real bug on first deploy**: `perform_waking_hours_tasks()` (a separate scheduled
  "check Gmail" routine, unrelated to `decide_displays()`) calls `self.check_emails()` directly
  — the only `check_*` method with a call site outside `decide_displays()`'s dispatch loop.
  Making `frame` a required parameter broke it immediately (`TypeError: check_emails() missing
  1 required positional argument: 'frame'`), visible in the live daemon logs within seconds of
  redeploying. Grepped every other `check_*` method for the same pattern (none found) and fixed
  by giving `check_emails(self, frame=None)` a default — it never used the frame field anyway.
  Verified clean on redeploy.
- A real cycle logged every `Collecting displays: checking <rule>` line including the new
  `checking empty_house_still_on`, with no errors, and published a card set identical in shape
  to before the refactor (same modes/priorities/content for the household's actual current
  state).
- Confirmed `frame.now` is shared: the published `time` card's timestamp and the cycle's own
  log timestamps landed within the same sub-second window, as expected from one
  `datetime.now(timezone.utc)` call instead of ~10 independent ones.

## Not yet done

- **A live "empty house, still on" firing** — the household's real smart-home devices weren't
  in a state to trigger it during this verification window (either someone was home, or nothing
  was left on). The rule's logic is covered by 5 direct unit tests
  (`TestCheckEmptyHouseStillOn`); a real end-to-end firing hasn't been observed yet.
- Async/await conversion of the daemon — explicitly out of scope per the task doc (see
  `todo/todo_flask_to_fastapi.md`).

## Out of scope (per the task doc, unchanged)

- Changing any rule's firing logic or priority (beyond the new Phase 3 rule).
- Caching across cycles — the frame is built fresh and thrown away every cycle.
