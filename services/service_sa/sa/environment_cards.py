"""Environment cards: weather, rain advisory, indoor climate (advisory and deviation), time, mood.

Step 4b of the engine.py split (todo/sa/todo_parallel_capture_track.md, item 4): the constants and
the six `check_*` methods moved verbatim out of engine.py as `EnvironmentCards`, which `SAEngine`
inherits; engine re-exports the constants. Everything the methods call is a shared module object
(`pymysql`, `inference_store`, `layer2`, `scalar`), patched by attribute, so
existing tests are unaffected. Patch any module-level NAME here, not on `engine`.
"""

import logging
import os
from datetime import timedelta

import pymysql
from sa import inference_store, layer2
from sa.learners import presence as presence_learner
from sa.learners import scalar

logger = logging.getLogger("SALog")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")

# Minimum forecast rain probability (%) for check_weather_advisory() to fire.
RAIN_ADVISORY_THRESHOLD = 30

# How far ahead the forecast checked by check_weather_advisory() looks.
FORECAST_HOURS_AHEAD = 6

# Indoor comfort band for check_climate_advisory() (SA-9 Phase 1). The hot/humidity-high sides
# were recalibrated 2026-09-26 against the real household's first ~11 days of
# smarthome_sensor_history (144k+ readings): the original 27.0C placeholder sat only ~0.5
# stdev above the real median (26.0C, stdev ~1.8-2.3C across buckets), so it fired on ordinary
# afternoon warmth (120 cards in its first 2 days) rather than genuine discomfort; the original
# 65% humidity placeholder sat *above* the real 11-day max (63.57%), so it had structurally
# never fired. New values sit just past each metric's real p97 (28.86C / 56.04%) and below its
# real max (29.94C / 63.57%) -- reachable by genuinely hot/humid moments, not by every warm
# afternoon. Cold/humidity-low are left at their original generic-comfort defaults: the real
# data has never come close to either (min 19.27C, min humidity 33.92%), so there's no household
# evidence yet to calibrate them against -- revisit once a real cold/dry spell happens.
CLIMATE_ADVISORY_COLD_THRESHOLD_C = 18.0
CLIMATE_ADVISORY_HOT_THRESHOLD_C = 29.0
CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT = 58
CLIMATE_ADVISORY_HUMIDITY_LOW_PCT = 30


class EnvironmentCards:
    def check_weather(self, frame):
        """Default: concise weather summary.

        `frame.environment` (SA-4) replaces this rule's own environment-table read --
        check_weather_advisory()/check_gatherings() each ran their own separate query
        against the exact same row.
        """
        environment = frame.environment
        if not environment:
            return None
        content = (
            f"{environment['city']}: {environment['subjective_feel']}, "
            f"{environment['description']}, {environment['low']}°C to {environment['high']}°C"
        )
        return {
            "mode": "weather",
            "content": content,
            "priority": 5,
            "data": {
                "city": environment["city"],
                "subjective_feel": environment["subjective_feel"],
                "description": environment["description"],
                "low": environment["low"],
                "high": environment["high"],
            },
        }

    def check_weather_advisory(self, frame):
        """Forward-looking rain advisory for the home location.

        Reads the forecast snapshot service_environment persists to the
        environment table (via its "check forecast" Kafka message and
        weather_util.get_forecast()) -- the same direct-DB-read pattern
        check_weather() uses for current conditions, rather than a
        synchronous cross-service call. Home location only; per-destination
        forecasting would need geocoding calendar_events.address and is out
        of scope here.

        `frame.environment` (SA-4) replaces this rule's own environment-table read --
        see check_weather()'s docstring for the duplicate this and check_gatherings() shared.
        """
        environment = frame.environment
        if not environment:
            return None
        rain_probability = environment.get("forecast_rain_probability")
        if rain_probability is not None and rain_probability > RAIN_ADVISORY_THRESHOLD:
            content = f"Rain likely in the next {FORECAST_HOURS_AHEAD} hours — bring an umbrella"
            return {
                "mode": "weather_advisory",
                "content": content,
                "priority": 4.5,
                "data": {
                    "forecast_rain_probability": rain_probability,
                    "hours_ahead": FORECAST_HOURS_AHEAD,
                    "because": [
                        f"{rain_probability}% rain probability > {RAIN_ADVISORY_THRESHOLD}%"
                    ],
                },
            }
        return None

    def check_climate_advisory(self, frame):
        """Fixed-threshold indoor comfort advisory from the household's one accepted ESPHome
        temp/humidity sensor (SA-9 Phase 1). Deliberately still fixed thresholds, not
        baseline-learned, even though entity_baselines gained smarthome/ESPHome support in
        Phase 2 (climate_deviation) -- this rule and that one answer different questions on
        purpose ("is it uncomfortable, period" vs. "is it unusual for this house right now") and
        collapsing them into one baseline-driven check would lose the absolute-comfort signal
        entirely. The threshold *values* themselves were recalibrated against real household data
        2026-09-26 -- see CLIMATE_ADVISORY_HOT_THRESHOLD_C's own comment. Single intermittent
        sensor, no room scoping (smarthome_devices.room is never populated for ESPHome entities)
        -- content stays generic ("indoors") rather than naming a room.
        """
        climate = frame.esphome_climate
        if not climate:
            return None

        # Readings are shown to the nearest degree / percent; the thresholds compare the raw value.
        if climate["temperature_online"] and climate["temperature_c"] is not None:
            temp = climate["temperature_c"]
            shown = round(temp)
            if temp < CLIMATE_ADVISORY_COLD_THRESHOLD_C:
                return {
                    "mode": "climate_advisory",
                    "content": f"It's cooler than usual indoors ({shown}°C)",
                    "priority": 5.3,
                    "data": {
                        "temperature_c": shown,
                        "because": [f"{shown}°C < {CLIMATE_ADVISORY_COLD_THRESHOLD_C}°C"],
                    },
                }
            if temp > CLIMATE_ADVISORY_HOT_THRESHOLD_C:
                return {
                    "mode": "climate_advisory",
                    "content": f"It's warmer than usual indoors ({shown}°C)",
                    "priority": 5.3,
                    "data": {
                        "temperature_c": shown,
                        "because": [f"{shown}°C > {CLIMATE_ADVISORY_HOT_THRESHOLD_C}°C"],
                    },
                }

        if climate["humidity_online"] and climate["humidity_pct"] is not None:
            humidity = climate["humidity_pct"]
            shown = round(humidity)
            if humidity > CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT:
                return {
                    "mode": "climate_advisory",
                    "content": f"Humidity is higher than usual indoors ({shown}%)",
                    "priority": 5.3,
                    "data": {
                        "humidity_pct": shown,
                        "because": [f"{shown}% > {CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT}%"],
                    },
                }
            if humidity < CLIMATE_ADVISORY_HUMIDITY_LOW_PCT:
                return {
                    "mode": "climate_advisory",
                    "content": f"Humidity is lower than usual indoors ({shown}%)",
                    "priority": 5.3,
                    "data": {
                        "humidity_pct": shown,
                        "because": [f"{shown}% < {CLIMATE_ADVISORY_HUMIDITY_LOW_PCT}%"],
                    },
                }

        return None

    def check_climate_deviation(self, frame):
        """Baseline-learned sibling to check_climate_advisory() (SA-9 Phase 2): fires when the
        indoor reading is unusual for this hour, not just absolutely uncomfortable. Separate
        rule_id from climate_advisory -- same absolute-reading-vs-deviation-alert split as
        weather/weather_advisory -- so dismissing one doesn't suppress the other.

        Since the LF-4 cutover this shows the scalar learner's inference (sa/learners/scalar.py)
        instead of comparing against an `entity_baselines` band: the shadow pass scores the
        ESPHome temperature and humidity series every cycle and stores any deviation in
        sa_inferences, so this card lags it by at most one cycle. The learner knows the hour of
        day and adapts to a slow drift, so ordinary daytime warmth no longer fires (the old band
        pooled a whole time-of-day bucket: 15 of 19 flagged hours in a 13-day backtest were
        ordinary at the learner's z of 1-2). An uncomfortable level that persists is
        check_climate_advisory()'s job. Needs confidence >= MIN_CARD_CONFIDENCE, so a series
        whose stability was just cut by a regime change stays quiet.
        """
        if frame.now is None:
            return None
        now_utc = frame.now.replace(tzinfo=None)
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            recent = inference_store.load_recent(
                db, 1, now_utc - timedelta(minutes=layer2.FRESH_MINUTES), kinds=("deviation",)
            )
        except pymysql.Error as e:
            logger.error("Climate deviation check error: " + str(e))
            return None
        finally:
            if db:
                db.close()

        found = []
        for inference in recent:
            series = (inference.evidence or {}).get("series") or ""
            if inference.learner != scalar.NAME or not series.startswith("esphome:"):
                continue
            kind = (
                "temperature"
                if series.endswith(":Temperature")
                else "humidity" if series.endswith(":Humidity") else None
            )
            if kind and inference.confidence >= presence_learner.MIN_CARD_CONFIDENCE:
                found.append((kind, inference))
        if not found:
            return None
        # Most surprising first; temperature wins a tie, as it did when this compared bands.
        kind, inference = max(found, key=lambda f: (f[1].surprise, f[0] == "temperature"))
        value = round(inference.observed["value"])  # shown to the nearest degree / percent
        high = inference.observed["direction"] == "high"
        mu = round(inference.expected["mu"])
        if kind == "temperature":
            direction = "Warmer" if high else "Cooler"
            content = f"{direction} than typical for this time of day ({value}°C)"
            data = {"temperature_c": value}
            because = f"{value}°C against about {mu}°C expected at this hour"
        else:
            content = (
                f"{'Higher' if high else 'Lower'} humidity than typical for this time of day "
                f"({value}%)"
            )
            data = {"humidity_pct": value}
            because = f"{value}% against about {mu}% expected at this hour"
        return {
            "mode": "climate_deviation",
            "content": content,
            "priority": 5.4,
            "data": {
                **data,
                "typical_median_value": mu,
                "surprise_bits": inference.surprise,
                "confidence": inference.confidence,
                "because": [because],
            },
        }

    def check_time(self, frame):
        """Get current time card.

        `frame.now` (SA-4) replaces this rule's own datetime.now(timezone.utc) call -- every
        card published this cycle now shares the exact same timestamp.
        """
        content = frame.now.isoformat()
        return {"mode": "time", "content": content, "priority": 1}

    def check_mood(self, frame):
        """Baseline day-mood card: weekday/time-of-day context with a qualitative energy read.

        `frame.day_mood` (SA-4) replaces this rule's own get_env_local_time()/get_day_mood()
        calls -- check_gatherings()/check_party_advisory()/check_wind_down_signal() all
        needed the exact same pair.
        """
        if frame.day_mood is None:
            return None
        day_mood = frame.day_mood
        energy = day_mood["base_energy"]
        if energy < 0.35:
            energy_label = "low energy"
        elif energy < 0.65:
            energy_label = "moderate energy"
        else:
            energy_label = "high energy"
        content = f"{day_mood['day_of_week']} {day_mood['time_of_day']} — {energy_label}"
        return {
            "mode": "mood",
            "content": content,
            "priority": 6,
            "data": {
                "day_of_week": day_mood["day_of_week"],
                "time_of_day": day_mood["time_of_day"],
                "energy": energy,
                "energy_label": energy_label,
            },
        }
