# Signal inventory: every SA context, what is captured, and what the engine learns from it

> **Layer:** data + learners · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-0b (new), LF-4, LF-5

## Status: 🟢 LF-0b capture and LF-2b silver / gold are live (2026-10-10). The learner families are next.

Capture result, all running in production and in the nightly job:

| Context | Now captured | Size / depth |
|---|---|---|
| **Home Assistant**: every entity (80, minus the legacy Pushbullet ones), state changes | bronze `ha_state_history`, nightly + backfill | ~7,200 points, 78 entities, **11 days** (09-30 to 10-10), the whole of HA's retention |
| **Email**: sender, subject, time, labels, read state (never the body) | bronze `email_messages`, nightly, self-healing | **3,656 messages, exactly 12 months**, 533 distinct senders |
| **ESPHome binary sensors, light, switch** | `smarthome_sensor_history` as 1.0 / 0.0 | first readings 04:01 today; accrues each sync |
| **Weather** | already captured by `get_weather()` into `environment_history` (LF-0) | since 10-09; HA's OpenWeatherMap entities add the prior ~10 days at finer resolution |

## Why this exists

Raised by Athos right after LF-3: SA and learning are not only about people and devices. The
engine is for **every** context ALFR3D senses: IoT device states, weather, date / day / time of
year, indoor temperature and humidity, calendar events, email frequency and senders and subjects,
notifications, geofencing and what the Deck reports. LF-3 built the shared parts (confidence, the
profile and inference tables, the fit/score split, the walk-forward evaluation) and one learner, for
presence. This doc says what the other contexts need.

The audit's main finding: **the limiting factor is capture, not modelling.** A learner can be
written in a day; history that was never recorded cannot be recovered. Several contexts have little
or no history, and for one of them (Home Assistant) the source is discarding it daily.

## The model: four signal shapes, plus context

Every context reduces to one of four shapes, each with a learner family. The presence learner is
the "state" family; the others reuse its pooling, recency weighting, confidence terms and
walk-forward evaluation.

| Shape | What it is | Learner | Examples |
|---|---|---|---|
| **State** | binary or categorical over time | P(state \| context), Beta-Binomial profile **(built, LF-3)** | someone home, a light on, media playing, DND, weather class |
| **Scalar** | a number sampled over time | robust baseline conditioned on context (median / MAD), with covariates | indoor temp and humidity, outdoor temp, pressure, battery, speedtest, dwell time |
| **Event stream** | things that happen, with attributes | rate per context; rate **per entity** (per sender) | messages, calls, emails, notifications, track plays, card taps, routines, calendar events |
| **Transition** | A is followed by B | P(B within window \| A) | arrives home → lights, leave → thermostat |

**Context features** are shared by all of them and live in silver `day_context`: hour, weekday,
month / season, Ontario holiday (built); daylight, weather class, calendar-busy, who is home
(to build). A signal is learned *given* context, and context can include another signal: indoor
temperature depends on outdoor temperature and on whether anyone is home; "lights on while nobody is
home" is a state conditioned on presence. Cross-signal findings like that are layer 2
([todo_lf6_layer2.md](todo_lf6_layer2.md)).

## What is captured today (live lake, 2026-10-10)

| Context | Shape | Where it comes from | History in the lake | Verdict |
|---|---|---|---|---|
| **People at home** | state | phone sightings (silver) | since 2026-04-12; **no data in June, ~none in July** (collector outage) | ✅ learner built |
| **Indoor temp / humidity** (ESPHome) + wifi, uptime | scalar | `smarthome_sensor_history` | 762,739 readings since 09-16 (3.5 weeks) | ✅ captured; too short for seasons |
| **ESPHome binary sensors (2), light (1)** | state | `smarthome_sensor_history`, 1.0 / 0.0 (mean over a window = fraction of time on) | since 2026-10-10 | ✅ captured |
| **Home Assistant: 48 sensors, 13 media players, sun, weather, device trackers, scripts** (24 OpenWeatherMap incl. forecasts, phone battery / charger, speedtest, version; the leftover legacy `pushbullet` entities are excluded) | scalar / state / event | `bronze/ha_state_history` (state changes, on-change timestamps) | 11 days at capture time; HA keeps ~10, so **nothing older than 09-30 exists anywhere** | ✅ captured from 2026-10-10 |
| **Weather / meteorological** | scalar + categorical | `get_weather()` -> `environment_history` (every 4 h, forecast hourly) since 10-09, plus HA's 24 OpenWeatherMap entities (state changes, finer than 4 h) back to 09-30 | ~13 rows + 11 days of HA | ✅ captured. Only the history *before* 09-30 is missing, and accumulating is the decision |
| **IoT commands** | event | `device_command_history` | since 10-10 (1 row so far) | ✅ captured |
| **Date, day, time of year, holidays** | context | silver `day_context` | built for the whole span | ✅ (daylight not yet: sunrise and sunset accumulate in `environment_history` from 10-09) |
| **Calendar events** | interval | `calendar_events` | 2 events kept since 10-09; earlier events were deleted 24 h after ending. `household_events` has 33 created / removed notices since 09-08 | ⚠️ mostly lost |
| **Email** (frequency, sender, subject) | event stream | `bronze/email_messages`: Gmail metadata only, no body | 3,656 messages, 12 months | ✅ captured |
| **Notifications and calls from the Deck** | event stream | `household_events` notification events | 1,050 messaged + 66 called since 09-13; **sender name and app only, no subject** | ⚠️ partial |
| **Geofencing / location** | state + scalar | `device_location_history`, enter / leave events | 797 fixes since 09-11, one device, 2 km accuracy; 13 enter / leave events | ⚠️ thin |
| **Phone / attention** (unlocks, switches, dwell) | scalar | `attention_telemetry_history` | 1,491 rows since 08-30 | ✅ captured. DND and battery on the Deck are current-only |
| **Card interactions** | event | `card_interactions` | 49,558 since 08-31 | ✅ |
| **Music** | event | track `play_start` / `play_stop` events | 5,558 starts + 227 stops since 08-30 (+ 78 `listening_history`) | ✅ |
| **Routines** | event | `routine/executed` events | 145 since 09-08 | ✅ |
| **Network health** (speedtest) | scalar | HA entities | none (inside the HA gap) | ❌ gap |

## Capture gaps: what was closed and what remains

Closed by LF-0b (2026-10-10): Home Assistant history, email metadata, ESPHome binary / light /
switch states. Weather needed no new work (see the status table).

Still open:
1. **Calendar.** Retention is fixed since 10-09; earlier history is gone except the created /
   removed notices in `household_events`.
2. **Deck context** (DND, battery, charging, network, activity) is current-only: see
   [todo_deck_learning_stream.md](todo_deck_learning_stream.md).
3. **Notifications.** The Deck reports sender and app only (1,050 since 09-13). Email subjects now
   come from Gmail directly, so the only notification content missing is for apps other than Gmail
   (Viber, ...). Whether to ask the Deck for more is a privacy decision, not a default. The
   Deck's other reports, and the fact that its device context and surface state keep no history at
   all, are tracked in [todo_deck_learning_stream.md](todo_deck_learning_stream.md). (Pushbullet and
   ntfy.sh are legacy and unused: ALFR3D's notifications go over Kafka and the event stream.)
4. **Weather before 2026-09-30.** Decided: accumulate only. Seasonal context will build slowly.
5. **HA attributes** are not stored on purpose (signed picture tokens). Anything useful that lives
   only in an attribute (the sun's elevation) has to be computed instead.

## Proposed order

- **LF-0b: capture the missing contexts. Done 2026-10-10** (see the status table).
- **LF-2b: silver and gold for the new contexts** (`ha_states`, `weather_hourly`, `email_events`,
  daylight in `day_context`, calendar density) and signal-shape-generic gold grids, so each learner
  family reads one common shape.
- **LF-4 becomes the scalar and event families**, not just a port of the old baselines: scalar
  baseline conditioned on hour, weekday, season and covariates; event rates per context and per
  entity (an unusually silent or unusually loud sender, an email burst). The legacy rules (climate,
  attention, rhythm break, departure, household) are the first consumers.
- **LF-5** keeps drift and the occasional-visitor learner, and adds transitions.
- **Shared primitives:** the recency-weighted, pooled estimate and the walk-forward evaluation in
  `sa/learners/presence.py` get factored out so every family reuses them instead of copying them.

## Caveats

- Seasonal learning (indoor temperature against outdoor, heating season) needs about a year of
  data. We will have weeks. Learners must say so through `sufficiency`, not pretend.
- Indoor climate has one sensor in one room. "Indoor humidity and temperature" is a single series.
- A learner is only as good as its context: until weather and calendar history exist, "unusual for
  this weather" cannot be asked.

## What LF-0b taught (2026-10-10)

- **Home Assistant 2023.8 requires an explicit entity list** on history requests (an unfiltered
  call is HTTP 400), so each run lists `/api/states` first and fetches in chunks of 30.
- **HA stamps the state in effect at the start of a window at that start** (711 points at exactly
  00:00:00 across the backfill). These midnight anchors are what let a series be rebuilt for an
  entity that rarely changes. Partitions are therefore *merged* by (entity, time), not replaced.
- **Gmail rate-limited a batch of 50 on 19 of 50 messages (HTTP 429)**, and my first version
  treated per-message errors as "message gone" and dropped them silently: 1,230 of 3,655 messages
  were missing after the first run, with no error. Found by comparing listed against stored. Now:
  batches of 10, per-message retry with backoff, and a count of anything still failing. The sync
  also lists the whole 12-month window every run and fetches what is not stored, so a miss repairs
  itself.
- **Gmail's own estimate was wrong**: it said 201 messages in the last 12 months; the real list is
  3,655.
- **One message arrived with `internalDate` = -1 ms** and landed in 1969. The parser now falls back
  to the `Date` header and drops the message only if neither is plausible.
- **Message text stays out.** Email bodies are never requested; subject lines are kept, as the
  household asked. The `pushbullet` entities were excluded **entirely** once Athos pointed out that
  Pushbullet and ntfy.sh are legacy channels ALFR3D used before Kafka and the backend event stream
  existed, and are no longer used. The first backfill had already stored 146 of their points; the
  exporter now applies exclusions retroactively on every run, which removed them.
- A `bool` is an `int` in Python: ESPHome binary states were silently skippable only because of the
  domain check, so on/off states now map explicitly to 1.0 / 0.0.

## Known limits

- HA history older than ~10 days at the time of the first run is gone for good. If `sa-learner`
  is down for more than about nine days, the same will happen again.
- Email is only as complete as Gmail's non-spam, non-trash list for the last 12 months; mail
  deleted before capture is not recoverable.
- Subject lines are now stored in the lake on the NUC's volume. They are as sensitive as the
  mailbox itself; the lake should be treated that way (backups, access).

## Found during LF-2b (2026-10-10)

- **Home Assistant is still configured for the old house** (Novi Sad, Serbia), so its weather, sun,
  home zone and device trackers describe the wrong place. ALFR3D's own `get_weather()` record is the
  household's weather. Fixing HA's home location is a Home Assistant setting and is Athos's call;
  see [todo_lf2_silver_gold.md](todo_lf2_silver_gold.md) (LF-2b) for the evidence.
- Weather is now sampled **hourly and silently** (`record weather`), in addition to the four-hourly
  spoken one.
