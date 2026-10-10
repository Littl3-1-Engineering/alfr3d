# Signal inventory: every SA context, what is captured, and what the engine learns from it

> **Layer:** data + learners · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) → LF-0b (new), LF-4, LF-5

## Status: 🔲 Inventory written 2026-10-10 from the live lake. Capture work (LF-0b) not started.

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
| **ESPHome binary sensors (2), light (1)** | state | only the current `last_state` | **none**: sensor history records the numeric `sensor` domain only | ❌ gap |
| **Home Assistant: 48 sensors, 13 media players** (24 OpenWeatherMap incl. forecasts, phone battery / charger, speedtest, Pushbullet title and body, version) | scalar / state / event | only the current value in `smarthome_devices.last_state` | **none on our side.** HA keeps ~10 days (probed: data back to ~09-30, nothing older) | ❌ gap, **urgent: loses a day every day** |
| **Weather / meteorological** | scalar + categorical | `environment_history` | 13 rows since 10-09 | ❌ gap (HA's OpenWeatherMap entities hold the last ~10 days) |
| **IoT commands** | event | `device_command_history` | since 10-10 (1 row so far) | ✅ captured |
| **Date, day, time of year, holidays** | context | silver `day_context` | built for the whole span | ✅ (daylight not yet: sunrise and sunset accumulate in `environment_history` from 10-09) |
| **Calendar events** | interval | `calendar_events` | 2 events kept since 10-09; earlier events were deleted 24 h after ending. `household_events` has 33 created / removed notices since 09-08 | ⚠️ mostly lost |
| **Email** (frequency, sender, subject) | event stream | Gmail API, but only the top-5 unread are read for a card, and **nothing is stored** | none stored. Deck notifications of Gmail messages give sender and app only (see next row) | ❌ gap, **backfillable** from the Gmail API |
| **Notifications and calls from the Deck** | event stream | `household_events` notification events | 1,050 messaged + 66 called since 09-13; **sender name and app only, no subject** | ⚠️ partial |
| **Geofencing / location** | state + scalar | `device_location_history`, enter / leave events | 797 fixes since 09-11, one device, 2 km accuracy; 13 enter / leave events | ⚠️ thin |
| **Phone / attention** (unlocks, switches, dwell) | scalar | `attention_telemetry_history` | 1,491 rows since 08-30 | ✅ captured. DND and battery on the Deck are current-only |
| **Card interactions** | event | `card_interactions` | 49,558 since 08-31 | ✅ |
| **Music** | event | track `play_start` / `play_stop` events | 5,558 starts + 227 stops since 08-30 (+ 78 `listening_history`) | ✅ |
| **Routines** | event | `routine/executed` events | 145 since 09-08 | ✅ |
| **Network health** (speedtest) | scalar | HA entities | none (inside the HA gap) | ❌ gap |

## Capture gaps, ranked by how fast they are being lost

1. **Home Assistant entity history: ~1 day lost per day.** HA's recorder keeps ~10 days. Fix: a
   nightly export of every entity's state changes from HA's history API straight into bronze
   Parquet, plus a **one-time backfill of the ~10 days still available**. No new MySQL table; HA is
   the source of truth and a 10-day window leaves plenty of margin for a missed night.
2. **Weather.** `environment_history` has accumulated since 10-09. HA's OpenWeatherMap entities
   cover the last ~10 days. Years of past weather exist in free historical archives but would
   require sending the household's coordinates to a third party: **a decision, not a default.**
3. **Email.** Not stored at all. The Gmail API holds years: a metadata-only capture (received time,
   sender, sender domain, subject, labels, read state; never the body) can be incrementally synced
   and **backfilled** deep into the past, so email learners could start with real history. Needs a
   decision on subject retention and on how far to backfill.
4. **ESPHome state domains** other than numeric sensors (binary sensors, lights): extend the
   existing recorder.
5. **Calendar.** Retention is fixed since 10-09; earlier history is gone except the created /
   removed notices.
6. **Deck context** (DND, battery, activity) is current-only; attention telemetry already has
   history.

## Proposed order

- **LF-0b: capture the missing contexts (do first, before more learners).** Items 1, 3 and 4 above
  (and 2 if approved). Pure capture: bronze exports, one Gmail metadata sync, extended recorders.
  Each is small and independent; the first has a clock on it.
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
