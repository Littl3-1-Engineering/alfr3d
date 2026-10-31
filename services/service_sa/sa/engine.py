"""Situational-awareness engine: context frame, display rules, card suppression, publishing,
and the entity-baseline computation those rules read.

LF-1a (todo/sa/todo_lf1a_sa_service_split.md): moved verbatim out of
service_daemon/alfr3ddaemon.py -- the SA constants, the SA methods of MyDaemon (now SAEngine)
and compute_entity_baselines() -- so the daemon stays a fast loop engine and SA has one owner.
No behaviour change: same rules, same priorities, same queries, same Kafka topic.
`awareness.py` runs SAEngine.check_situational_awareness() every 60s; `learner.py` runs
compute_entity_baselines() every 6h.
"""

# Standard library imports
import logging
import math
import statistics
import time
import os
import sys
import bisect
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
import orjson

# Third party imports
import pymysql
from sa import context_frame, focus_utils, inference_store, mood_utils, routing_utils, shadow
from sa import disk, layer2
from sa.learners import household_day
from sa.learners import presence as presence_learner
from sa.learners import scalar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import calendar_utils, gmail_utils, spotify_utils  # noqa: E402
from common import get_producer  # noqa: E402
from common import db_utils  # noqa: E402
from common import day_context  # noqa: E402
from common import timeofday  # noqa: E402

logger = logging.getLogger("SALog")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

# get main DB credentials
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")

# How far ahead of a call-like event's start time check_focus_needed() will fire.
FOCUS_LEAD_MINUTES = 15

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

# Spotify's own 0.0-1.0 "energy" audio feature above which check_party_advisory()
# considers what's actually playing to be genuinely high-energy, independent
# of ALFR3D's own (capped, on weeknights) recommendation.
PARTY_ADVISORY_ENERGY_THRESHOLD = 0.75

# Minimum time between check_party_advisory() spoken nudges, so a rowdy
# weeknight track doesn't get "it's a school night" repeated every polling
# cycle -- the card itself still refreshes every cycle, only the TTS nudge
# is rate-limited.
PARTY_ADVISORY_COOLDOWN_MINUTES = 60

# Last time check_party_advisory() spoke a nudge; 0.0 so the very first
# detection always speaks rather than waiting out a cooldown against an
# undefined "last time".
PARTY_ADVISORY_LAST_NUDGE_TIME = 0.0

# check_system_health(): how often an integration (Home Assistant / SmartThings) is probed, and
# how many probes in a row must fail before the card fires. A probe is a network call with a
# 10s timeout, so it must not run every ~60s cycle; two consecutive failures (~10 min) keeps a
# single blip or an HA restart from raising an urgent card.
SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS = 300
SYSTEM_HEALTH_FAILURES_BEFORE_ALERT = 2

# (key, display name, common module, is-configured fn, probe fn) -- an unconfigured integration
# is never probed or alerted on.
SYSTEM_HEALTH_INTEGRATIONS = (
    ("home_assistant", "Home Assistant", "ha_utils", "is_ha_configured", "test_ha_connection"),
    ("smartthings", "SmartThings", "st_utils", "is_st_configured", "test_st_connection"),
)

# check_disk_health(): sa-learner samples the disk every few hours, so the rule re-reads the
# history at most this often; the critical tier speaks at most once per cooldown.
DISK_HEALTH_CHECK_INTERVAL_SECONDS = 900
DISK_HEALTH_SPEAK_COOLDOWN_SECONDS = 24 * 3600
DISK_HEALTH_STATE = {"checked": 0.0, "result": None, "spoke": 0.0}

# Per-integration probe state: {key: {"failures": int, "last_probe": float}}. In-memory only --
# a restart just re-probes, and the alert needs fresh consecutive failures anyway.
SYSTEM_HEALTH_STATE = {}

# `config` table key check_now_playing() persists the last-seen track under,
# so the value survives daemon restarts and is queryable by other services.
NOW_PLAYING_CONFIG_KEY = "music_now_playing"

# `config` table key POST /api/context/surface-state (service_api/routes/context.py)
# writes the launcher's last-reported active surface/terminal-session state
# under; read by check_cross_surface_continuity() via _read_config_json().
SURFACE_STATE_CONFIG_KEY = "launcher_surface_state"

# check_cross_surface_continuity() only offers a resume for state reported/
# updated within this many minutes -- a paused track or edited routine from
# hours ago isn't "picking up where you left off" anymore.
CROSS_SURFACE_STALENESS_MINUTES = 45

# `config` table key POST /api/context/attention-telemetry writes the
# launcher's most recent rolling-window snapshot under; read by
# check_attention_focus() and check_wind_down_signal().
ATTENTION_TELEMETRY_CONFIG_KEY = "launcher_attention_telemetry"

# The launcher reports a fresh attention-telemetry snapshot every ~15
# minutes -- a snapshot older than this is treated as stale (device likely
# offline/asleep) rather than fed into either check below.
ATTENTION_TELEMETRY_STALENESS_MINUTES = 30

# `config` table key POST /api/context/device-snapshot writes each Deck's own
# current device context under (todo/sa/todo_context_exchange_protocol.md Phase 2)
# -- battery/charging, DND/headset, network, orientation, foreground activity.
# These are facets the *launcher* owns: nothing else in this system can observe
# them, so before this the daemon had no way to know the phone was silenced.
# Mirrors routes/context.py's DEVICE_CONTEXT_CONFIG_KEY, kept in sync manually
# for the same reason SURFACE_STATE_CONFIG_KEY above is.
DEVICE_CONTEXT_CONFIG_KEY = "launcher_device_context"

# A Deck reports its device context on its own ~60s foreground tick, so
# anything older than this means that device is backgrounded, asleep, or gone
# -- and a stale DND reading is worse than none, since it would keep claiming
# the user is silenced long after they stopped being.
DEVICE_CONTEXT_STALENESS_MINUTES = 15

# check_attention_focus() fires when the reported window-switch count is at
# least this high -- a conservative starting point (roughly one switch per
# minute sustained over a ~15-minute report window) with no real telemetry
# yet to tune it against.
ATTENTION_FOCUS_MIN_SWITCHES = 15

# ...and only when media-category dwell is under this fraction of total
# dwell time -- high switching concentrated in media (e.g. flipping between
# a few apps while half-watching something) isn't "focus", it's the
# wind-down check's pattern instead.
ATTENTION_FOCUS_MAX_MEDIA_DWELL_FRACTION = 0.3

# check_wind_down_signal() fires when the reported unlock count is at least
# this high within the report window -- another conservative starting point.
WIND_DOWN_MIN_UNLOCKS = 5

# ...and only when media-category dwell is over this fraction of total dwell
# time -- the milestone's own "late-hour high unlock rate + social-app
# dwell" pattern.
WIND_DOWN_MIN_MEDIA_DWELL_FRACTION = 0.5

# check_attention_focus()/check_wind_down_signal() compare the current snapshot against this
# household's own rolling switch_count/unlock_count median (see _attention_telemetry_trend())
# once at least this many attention_telemetry_history rows exist -- "is this unusual for this
# household" rather than only "is this a big number in general". ~2 days at the launcher's
# 15-minute report cadence; a conservative starting point with no real telemetry yet to tune it
# against, same caveat as ENTITY_BASELINE_MIN_SAMPLES. Below this floor, both checks fall back
# to the fixed thresholds above unchanged.
ATTENTION_TREND_MIN_SAMPLES = 200

# How far back _attention_telemetry_trend() looks when computing the household's median
# switch_count/unlock_count.
ATTENTION_TREND_LOOKBACK_DAYS = 14

# Grace added on top of the household's own median switch_count/unlock_count before either
# check fires on the trend path -- same "small grace window so a marginally-above-typical value
# doesn't trigger every cycle" reasoning as RHYTHM_BREAK_GRACE_MINUTES.
ATTENTION_FOCUS_TREND_GRACE_SWITCHES = 5
WIND_DOWN_TREND_GRACE_UNLOCKS = 2


# decide_displays()'s suppression pass (SA-1) identifies a card as (rule_id, subject_key) --
# DISPLAY_RULES' own id, not the card's own "mode" field (which collides: check_gatherings,
# rule id "music", and check_now_playing, rule id "now_playing", both stamp "mode": "music" on
# their card). Most rules are singleton -- there's only one slot to suppress regardless of what
# the content currently says (dismissing "now playing" should mean "stop telling me what's
# playing for a while", not "I've seen this exact track before"), so subject_key defaults to "".
# Only rules that can legitimately recur for different underlying entities get a real one, via
# CARD_SUBJECT_KEY_EXTRACTORS below -- dismissing one device's rhythm-break card must not
# suppress a different device's.
def _cross_surface_continuity_subject_key(card):
    return f"{card.get('resume_type')}:{card.get('resume_target')}"


CARD_SUBJECT_KEY_EXTRACTORS = {
    "rhythm_break_anomaly": lambda card: card.get("entity_name") or "",
    # LF-3: one presence_deviation card per person, so dismissing one doesn't hide another's.
    "presence_deviation": lambda card: card.get("entity_name") or "",
    "cross_surface_continuity": _cross_surface_continuity_subject_key,
    # SA-3: departure_anomaly is rhythm_break_anomaly's human analogue -- dismissing one
    # resident's "still home" card must not suppress a different resident's.
    "departure_anomaly": lambda card: card.get("entity_name") or "",
    # Continuous-stay guest decay: dismissing one overstaying guest's advisory must not
    # suppress a different guest's.
    "guest_overstay_advisory": lambda card: card.get("entity_name") or "",
}

# Cards whose `urgent` field is true are never suppressed regardless of interaction history --
# household_composition's elevated variant (an unrecognized device on the network) is the only
# one today, but this is a generic field check so any future rule can opt in the same way.
CARD_SUPPRESSION_NEVER_OVERRIDE_FIELD = "urgent"

# decide_displays()'s suppression pass looks at up to this many of a card identity's most recent
# card_interactions rows -- must cover both the cooldown check (just the latest row) and the
# repetition-damping run-length count below.
CARD_SUPPRESSION_HISTORY_LIMIT = 10

# A card identity whose most recent interaction is "dismissed" is suppressed for this many
# minutes before it's allowed to show again -- a conservative starting point, no real
# interaction data yet to tune it against (same caveat as every other threshold in this file).
# Per-mode override via CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE.
CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES = 60
CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE = {
    # Continuous-stay guest decay: the underlying signal (days-of-stay) only changes once a
    # day, so re-showing this more than daily is pure noise on a signal that hasn't moved.
    "guest_overstay_advisory": 1440,
}

# A card identity shown this many cycles in a row with no interaction at all (no dismiss, no
# tap) gets suppressed until its underlying state changes (i.e. until something -- a different
# device, a content change on a singleton rule -- gives it a new identity, or a real interaction
# resets the run). Per-mode override via CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE.
CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES = 20
CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE = {}

# How far back compute_entity_baselines() looks when reconstructing on/off
# sessions from device_history to build each device's rhythm baseline.
ENTITY_BASELINE_LOOKBACK_DAYS = 30

# Minimum complete on/off sessions before a device gets a baseline row at all --
# below this, a "typical" pattern isn't meaningfully established yet, and
# publishing one would produce noisy false-positive anomalies.
ENTITY_BASELINE_MIN_SAMPLES = 5

# device_history is written about once a minute while the scanner runs. A silence longer than this
# inside an "online" session means the offline transition was never observed (scanner/daemon
# outage), so the session is closed at the last row seen online instead of being stretched across
# the gap -- otherwise one lost transition becomes a phantom multi-day session that poisons
# typical_daily_max and the still-on-past-typical rule.
ENTITY_BASELINE_MAX_HISTORY_GAP_MINUTES = 180

# An hour of the (UTC) day is part of a device's usual window when the device was online during it
# on at least this share of the days it was seen at all. Stored as a 24-bit mask in
# entity_baselines.active_hours_mask and read by check_rhythm_break_anomaly()'s unusual-hour branch.
ENTITY_BASELINE_ACTIVE_HOUR_MIN_SHARE = 0.15

# SA-9 Phase 2: how far back compute_entity_baselines() looks in smarthome_sensor_history when
# building each ESPHome sensor's per-time-of-day-bucket climate baseline.
CLIMATE_BASELINE_LOOKBACK_DAYS = 30

# Minimum readings in a given time-of-day bucket before check_climate_deviation() trusts that
# bucket's baseline -- same "degrade to silence below a reliability floor" precedent as
# ENTITY_BASELINE_MIN_SAMPLES.
CLIMATE_BASELINE_MIN_SAMPLES = 10

# 2026-09-26 fix: typical_daily_min/typical_daily_max for a 'room' (climate) baseline used to be
# the *raw* min/max of the lookback window -- checked against real production data and found to
# be self-defeating: a "typical" band built from the full observed range already covers ~all
# future readings, so check_climate_deviation() could never fire (confirmed: zero firings in 10
# days against 314k+ real readings). Now typical_daily_min/max are computed as
# median +/- CLIMATE_BASELINE_STDEV_MULTIPLIER standard deviations -- a band that reflects
# genuinely "typical" values instead of self-widening to the noise floor. Verified against the
# real household's actual sensor history before picking 2.0 (see todo_esphome_situational_
# awareness.md's 2026-09-26 entry): tight enough that real recorded extremes fall outside it,
# loose enough not to flap on ordinary variation.
CLIMATE_BASELINE_STDEV_MULTIPLIER = 2.0

# check_climate_deviation() fires only when the current reading is this far outside the
# baseline's [typical_daily_min, typical_daily_max] band (now a median +/- stdev band, not a raw
# min/max range -- see CLIMATE_BASELINE_STDEV_MULTIPLIER) for the current time-of-day bucket --
# a margin, not a hard edge, so a reading right at the historical boundary doesn't flap in and
# out of firing. Sized much smaller than before the 2026-09-26 fix: the band itself is now tight,
# so the margin only needs to add hysteresis, not compensate for an overly wide band.
CLIMATE_DEVIATION_MARGIN_C = 0.5
CLIMATE_DEVIATION_MARGIN_HUMIDITY_PCT = 3

# household_events/attention_telemetry_history/card_interactions retention, and the daily SA
# storage-metrics snapshot, all moved from Python `schedule` jobs to DB-native scheduled EVENTs
# in migration 039 (2026-09-13) -- see that migration's own comment for why. No Python constant
# for their retention window lives here any more; it's in the EVENT bodies themselves, same as
# device_location_history's own event already was.

# check_rhythm_break_anomaly() only fires this many minutes past a device's
# typical_daily_max on-duration -- a small grace window so a session that's
# only marginally longer than usual doesn't trigger every cycle.
RHYTHM_BREAK_GRACE_MINUTES = 15

# check_departure_anomaly() (SA-3): how far back device_history is scanned when computing a
# resident's per-weekday/weekend departure-hour baseline. Longer than ENTITY_BASELINE_LOOKBACK_DAYS
# (30d) deliberately -- splitting into weekday/weekend buckets roughly quarters the sample size a
# device baseline gets from the same window, and the confirmed-home-overnight anchor
# (_departure_hours_by_bucket()) rejects many days outright. Verified against this household's
# real history (todo/sa/todo_departure_anomaly.md): 60 days left every resident under the sample
# floor; 120 days was the first window where multiple residents actually cleared it. 180 would
# match device_history's own retention ceiling exactly, leaving no margin before rows this
# window depends on get pruned daily -- 120 leaves a 60-day cushion.
DEPARTURE_BASELINE_LOOKBACK_DAYS = 120

# A gap this long between consecutive device_history writes for a claimed device is treated as a
# genuine absence, not scan noise -- service_device's own check_offline_devices() only flips a
# device to 'offline' once its last_online is stale by 30 minutes, so any gap at or above that
# (+1 minute buffer) reflects an already-confirmed offline transition, not scan jitter.
DEPARTURE_GAP_MINUTES = 31

# A resident's per-day-bucket (weekday/weekend) departure baseline needs at least this many
# observed first-departure days before check_departure_anomaly() trusts it -- same "degrade to
# silence below a reliability floor" precedent as ENTITY_BASELINE_MIN_SAMPLES/
# ATTENTION_TREND_MIN_SAMPLES elsewhere in this file.
DEPARTURE_BASELINE_MIN_SAMPLES = 8

# check_departure_anomaly() also requires the baseline's observed hour range
# (typical_daily_max - typical_daily_min) to be at or under this many hours. The Phase 0 spike
# found some residents' real departure-hour history is too scattered (multi-hour spread, no
# real "typical" time) to be worth alerting on at all -- above this floor that household member
# simply gets no departure-anomaly baseline, rather than firing on noise dressed up as a pattern.
DEPARTURE_BASELINE_MAX_SPREAD_HOURS = 4

# How many hours past a resident's typical departure hour check_departure_anomaly() waits before
# firing -- a grace window so running a bit late on an otherwise-normal day doesn't trigger a
# card, mirroring RHYTHM_BREAK_GRACE_MINUTES's reasoning at the coarser (hour, not minute)
# granularity appropriate for a once-a-day event.
DEPARTURE_ANOMALY_GRACE_HOURS = 1.5

# Continuous-stay guest decay: max how far check_gatherings() can nudge its own priority-3 slot
# as its guests' decayed energy (spotify_utils.aggregate_guest_energy()) drops toward
# spotify_utils.GUEST_STAY_ENERGY_FLOOR. 0.08 leaves a 0.02 cushion below now_playing's 3.1, so
# a fully-decayed guest population never crosses into the next rule's priority band.
GUEST_CARD_PRIORITY_MAX_DEMOTION = 0.08

# check_travel() (SA-6): once the computed leave-by time is more than this many minutes in the
# past, stop publishing the card -- a stale leave-by time is worse than no card. Deliberately
# one-sided: this used to also cap how far *ahead* of leave-by the card could appear (a symmetric
# +/- window), which meant a distant event's leave-by simply didn't exist on the wire yet no
# matter how much advance notice a consumer wanted. self-hosted OSRM has no live-traffic layer
# (see check_travel()'s own doc comment), so the drive-time estimate doesn't get more accurate by
# waiting -- there's no reason to withhold it. How far in advance to actually *show* the card is
# alfr3d_deck's call (EventLeaveByLifecycle.LEAD_TIME_MINUTES), not this service's.
TRAVEL_STALE_AFTER_MINUTES = 30

# SA-10: household-level baselines (entity_type='household'). Household is a singleton -- there's
# only one row per day_bucket regardless of household size -- so entity_id is a fixed sentinel,
# not a real foreign key into any table.
HOUSEHOLD_BASELINE_ENTITY_ID = 0

# How far back the household-level aggregate query scans device_history. Reuses
# DEPARTURE_BASELINE_LOOKBACK_DAYS's own reasoning (weekday/weekend bucketing roughly halves the
# sample size a straight daily count would get, and 120 days leaves a cushion under
# device_history's 180-day retention) rather than re-deriving a separate number for a
# conceptually-similar "how much history does a day-bucketed household baseline need" question.
HOUSEHOLD_BASELINE_LOOKBACK_DAYS = DEPARTURE_BASELINE_LOOKBACK_DAYS

# A household-level per-day-bucket baseline needs at least this many observed days before
# the household baseline's consumers trust it -- same "degrade to silence below a reliability floor"
# precedent as every other baseline-gated check in this file. Set a bit higher than
# DEPARTURE_BASELINE_MIN_SAMPLES (8): a household-wide "is today unusual" call is a broader,
# higher-consequence claim than one resident's departure time, and deserves more evidence first.
HOUSEHOLD_BASELINE_MIN_SAMPLES = 14

# check_rhythm_break_anomaly()'s "expected absent" branch: an offline device with a reliable
# baseline is flagged only within this many hours *after* its typical_active_hour -- catches "it
# should be on by now" without nagging forever about a device that's simply been off for days.
EXPECTED_ABSENT_WINDOW_HOURS = 3

# ...and only if it was online this recently. A longer-offline device is retired, moved, or a stale
# duplicate record (e.g. the same machine's second network adapter, which has its own device row
# keyed by MAC) -- not "late". Four days spans a long weekend for a work machine.
EXPECTED_ABSENT_MAX_OFFLINE_DAYS = 4


class SAEngine:
    def check_situational_awareness(self):
        """Poll data and publish array of situational awareness cards."""
        results = self.decide_displays()
        if results:
            self.publish_sa(results)

    # Registry of situational-awareness display rules: (id, priority, check method name).
    # Each check_* method still stamps its own "priority" onto the card it returns;
    # the id/priority here just drive iteration order and logging.
    #
    # SA-5: every card is {mode, content, priority, ...}. `content` is prose and stays
    # authoritative for display -- it's what the `speak`/TTS path and the LLM personality
    # layer consume, and it's the human-readable fallback. `data` (optional -- a rule with
    # nothing worth exposing beyond content and its existing top-level fields just omits it)
    # is the structured facts a consumer would otherwise have to regex out of that prose.
    # Rule of thumb: if a number appears in the prose, it belongs in `data`. Pre-existing
    # top-level extras (entity_name, resume_type/resume_target, playlist_*, switch_count,
    # unlock_count, known_count/unknown_count/urgent, device_count, confidence,
    # conference_uri, track_title/track_artist/is_playing) are unchanged -- SA-5 does not
    # move anything a consumer might already read into `data` retroactively.
    # `data.because` (optional, SA-5 Phase 3): a short list of the signals that caused the
    # rule to fire -- interpretable evidence, not a full audit log.
    #
    # Per-mode `data` schemas (all keys optional/nullable unless noted):
    #   event:                 title, start_time (ISO), minutes_until, because
    #   focus_needed:           title, start_time (ISO), minutes_until, because
    #   music (check_gatherings): mood, genre, energy, tempo_hint, guest_count, total_count,
    #                           time_of_day, because
    #   party_advisory:        track_name, energy, day_of_week, because
    #   weather:                city, subjective_feel, description, low, high
    #   weather_advisory:      forecast_rain_probability, hours_ahead, because
    #   mood:                   day_of_week, time_of_day, energy, energy_label
    #   household_composition: known_names
    #   system_health:         unreachable (integration keys), because
    #   rhythm_break_anomaly:  varies by deviation_type -- still_on_past_typical:
    #                           over_by_minutes/typical_daily_max_minutes; unusual_hour:
    #                           current_hour/typical_active_hour; expected_absent:
    #                           typical_active_hour; all three also carry because
    #   cross_surface_continuity (music candidate only): minutes_ago
    #   attention_focus:       because
    #   wind_down_signal:      because
    #   empty_house_still_on:  smarthome_device_names, because
    #   departure_anomaly:      typical_departure_hour, sample_count, because
    #   presence_deviation:     expected_p_home, away_minutes, surprise_bits, confidence, because
    #   travel:                 duration_minutes, distance_km, traffic_aware, leave_by, because
    #   household_unusual_day:  today_device_count, typical_device_count_range,
    #                           today_first_activity_hour, typical_first_activity_hour, because
    #   time, music (check_now_playing), email, cross_surface_continuity
    #   (terminal/routine candidates): no `data` -- nothing beyond content and existing
    #   top-level fields is currently hidden in the prose for these.
    DISPLAY_RULES = (
        ("time", 1, "check_time"),
        ("event", 2, "check_events"),
        # SA-6: restores what commit 08509ce removed, on self-hosted infrastructure. Between
        # event (2) and empty_house_still_on (2.4)/rhythm_break_anomaly (2.6) -- an orchestrating,
        # time-boxed card, matching its original placement before removal.
        ("travel", 2.5, "check_travel"),
        ("music", 3, "check_gatherings"),
        # What's actually playing right now, independent of whether a
        # gathering triggered a recommendation -- priority 3.1 keeps it
        # right after the recommendation card it complements, ahead of the
        # party advisory (3.2) that reacts to this same playback state.
        ("now_playing", 3.1, "check_now_playing"),
        # Follows directly on from music (3): checks whether what's actually
        # playing is genuinely high-energy despite a capped weeknight
        # recommendation. Priority 3.2 keeps it right after the card it's
        # reacting to, ahead of focus_needed (3.5).
        ("party_advisory", 3.2, "check_party_advisory"),
        # Continuous-stay guest decay: fires once a guest's decayed energy contribution has
        # gone negative (day ~14+), suggesting the household resolve the situation -- promote
        # to resident, or address the overstay -- before it drags energy down further. Priority
        # 3.15 sits it between now_playing (3.1) and party_advisory (3.2): it reacts to the same
        # guest-presence signal as music (3), but is a slower-moving, less time-sensitive
        # observation than either neighbor.
        ("guest_overstay_advisory", 3.15, "check_guest_overstay_advisory"),
        # A call starting soon is more actionable/time-boxed than the ambient
        # "should I play music" gathering check, but not as centrally
        # orchestrating as an event departure — priority 3.5 sits it directly
        # between music (3) and email (4) without renumbering existing rules.
        ("focus_needed", 3.5, "check_focus_needed"),
        # Evidence-based sibling to focus_needed, not a replacement -- see
        # check_attention_focus()'s own doc comment.
        ("attention_focus", 3.6, "check_attention_focus"),
        ("email", 4, "check_emails"),
        # Forward-looking and actionable ("bring an umbrella"), unlike the
        # passive weather status readout below it -- sits between email (4)
        # and weather (5) the same way focus_needed sits between music and
        # email.
        ("weather_advisory", 4.5, "check_weather_advisory"),
        ("weather", 5, "check_weather"),
        # SA-9 Phase 1: ambient, low-urgency observation, same tier as weather but
        # device-sourced from a single intermittent ESPHome sensor -- lower confidence than the
        # forecast-backed weather cards, so it sits just below them rather than competing.
        ("climate_advisory", 5.3, "check_climate_advisory"),
        # SA-9 Phase 2: baseline-learned deviation-from-typical sibling to climate_advisory
        # (5.3) -- same tier, same "absolute readout vs. deviation alert" split as
        # weather (5) / weather_advisory (4.5).
        ("climate_deviation", 5.4, "check_climate_deviation"),
        # mood is lower-urgency ambient context, not an actionable alert —
        # slotted just below weather rather than competing with priorities 1-5.
        ("mood", 6, "check_mood"),
        # Priority isn't fixed here -- check_household_composition() computes it per-call:
        # ambient (6.2, next to mood) when every online device is claimed, elevated (2.3,
        # next to event/gathering) when an unclaimed/unknown device is on the network.
        ("household_composition", 6.2, "check_household_composition"),
        # Urgent (never suppressible, no dismiss button): a configured integration that has been
        # unreachable for several probes means every device it syncs reads offline. Priority 2.2
        # sits just above household_composition's elevated variant (2.3) -- the system itself
        # being blind outranks any single card it would have produced.
        ("system_health", 2.2, "check_system_health"),
        # Disk running out is the same kind of "the system is about to go blind" as system_health:
        # critical is urgent (2.1, just above it), warn is an ambient heads-up near mood.
        ("disk_health", 5.9, "check_disk_health"),
        # Actionable, near event/gathering: a genuine deviation from a device's
        # established on/off rhythm is worth surfacing promptly.
        ("rhythm_break_anomaly", 2.6, "check_rhythm_break_anomaly"),
        # SA-3: the human analogue of rhythm_break_anomaly, one priority tier below it --
        # "usually gone by now, still home" is a genuine routine deviation, not an alert.
        ("departure_anomaly", 2.7, "check_departure_anomaly"),
        # LF-3: the learned sibling of departure_anomaly. Not "still home when usually gone" but
        # "away when usually home" -- the case SA-3 cannot see -- scored against a per-person,
        # per-weekday, per-hour model of P(home) with a stated probability and confidence
        # (sa/learners/presence.py). Just below departure_anomaly: same kind of observation.
        ("presence_deviation", 2.75, "check_presence_deviation"),
        # Helpful, not urgent -- below weather (5), above mood (6.2/2.3): a
        # convenience "resume" offer, not something demanding attention.
        ("cross_surface_continuity", 5.5, "check_cross_surface_continuity"),
        # Just below cross_surface_continuity -- a low-urgency suggestion,
        # not something demanding attention either.
        ("wind_down_signal", 5.8, "check_wind_down_signal"),
        # SA-4 Phase 3 proof case: needs three frame fields at once
        # (online_devices, smarthome_online, day_mood) and couldn't have been
        # written before the context frame existed. Near rhythm_break_anomaly
        # (2.6) and household_composition's elevated variant (2.3) -- worth
        # attention, not an emergency.
        ("empty_house_still_on", 2.4, "check_empty_house_still_on"),
        # SA-10 Phase 3: household-level analogue of departure_anomaly/rhythm_break_anomaly --
        # just below mood (6)/household_composition's ambient variant (6.2), an observation, not
        # an alert. At most one card per day by construction (gated on being past the day's
        # typical_last_activity_hour).
        ("household_unusual_day", 6.5, "check_household_unusual_day"),
    )

    # Cap on cards published per cycle. Tied to the number of registered rules so
    # that every currently-registered category can coexist — previously a hardcoded
    # [:4] slice silently dropped weather (priority 5) whenever all five checks
    # fired. Grows automatically if DISPLAY_RULES grows, so adding a rule doesn't
    # silently reintroduce the same drop.
    MAX_DISPLAYS = len(DISPLAY_RULES)

    def build_context_frame(self):
        """Assemble one context_frame.ContextFrame for this decide_displays() cycle (SA-4).

        Each field is fetched in its own try/except -- one integration failing (Spotify
        unreachable, a query erroring) must not prevent unrelated fields, or the cards that
        depend on them, from being built. See context_frame.py's module docstring for the
        exact duplicate DB/API calls this eliminates.
        """
        frame = context_frame.ContextFrame()
        frame.now = datetime.now(timezone.utc)

        try:
            frame.tz_offset = db_utils.get_env_timezone(ENV_NAME)
            frame.local_dt = db_utils.get_env_local_time(ENV_NAME)
            frame.day_mood = mood_utils.get_day_mood(frame.local_dt)
            frame.day_ctx = day_context.get_day_context(ENV_NAME, now=frame.local_dt)
        except Exception as e:
            logger.error(f"Context frame: day_mood build failed: {e}")

        try:
            frame.upcoming_events = calendar_utils.get_upcoming_events()
        except Exception as e:
            logger.error(f"Context frame: upcoming_events build failed: {e}")

        try:
            frame.online_devices = context_frame.fetch_online_devices()
        except Exception as e:
            logger.error(f"Context frame: online_devices build failed: {e}")

        try:
            frame.person_presence = context_frame.fetch_person_presence()
        except Exception as e:
            logger.error(f"Context frame: person_presence build failed: {e}")

        try:
            frame.smarthome_online = context_frame.fetch_smarthome_online()
        except Exception as e:
            logger.error(f"Context frame: smarthome_online build failed: {e}")

        try:
            frame.esphome_climate = context_frame.fetch_esphome_climate_snapshot()
        except Exception as e:
            logger.error(f"Context frame: esphome_climate build failed: {e}")

        try:
            if frame.local_dt:
                bucket = timeofday.coarse_bucket(frame.local_dt.hour)
                frame.esphome_climate_baselines = context_frame.fetch_esphome_climate_baselines(
                    bucket
                )
        except Exception as e:
            logger.error(f"Context frame: esphome_climate_baselines build failed: {e}")

        try:
            frame.environment = context_frame.fetch_environment_snapshot(ENV_NAME)
        except Exception as e:
            logger.error(f"Context frame: environment build failed: {e}")

        try:
            from common import spotify_utils as spotify_api

            frame.playback = spotify_api.get_playback_state()
        except Exception as e:
            logger.error(f"Context frame: playback build failed: {e}")

        try:
            frame.persisted_now_playing = self._read_config_json(NOW_PLAYING_CONFIG_KEY)
        except Exception as e:
            logger.error(f"Context frame: persisted_now_playing build failed: {e}")

        try:
            launcher = context_frame.LauncherContext()
            launcher.surface_state = self._read_config_json(SURFACE_STATE_CONFIG_KEY)
            launcher.attention_snapshot = self._read_fresh_attention_telemetry()
            launcher.attention_trend = self._attention_telemetry_trend()
            launcher.device_contexts = self._read_fresh_device_contexts()
            frame.launcher_context = launcher
        except Exception as e:
            logger.error(f"Context frame: launcher_context build failed: {e}")

        return frame

    def decide_displays(self):
        """Run every registered display rule and return non-None cards, sorted by priority.

        Builds one context_frame.ContextFrame (SA-4) at the top of the cycle and passes it to
        every check -- see build_context_frame()'s docstring. A card whose rule doesn't use any
        frame field still receives it, for consistency and so it shares `frame.now` with every
        other card this cycle.

        A suppression pass (SA-1) runs after collection, before the sort: a card whose
        identity was recently dismissed, or has repeated too many cycles running with no
        interaction at all, is dropped -- unless its `urgent` field opts it out entirely
        (see CARD_SUPPRESSION_NEVER_OVERRIDE_FIELD; household_composition's elevated
        variant is the only rule using this today).
        """
        frame = self.build_context_frame()
        collected = []
        legacy_cards = {}
        for rule_id, _priority, check_name in self.DISPLAY_RULES:
            logger.info(f"Collecting displays: checking {rule_id}")
            card = getattr(self, check_name)(frame)
            legacy_cards[rule_id] = card
            if card:
                collected.append((rule_id, card))
        self._run_shadow(frame, legacy_cards)

        displays = []
        for rule_id, card in collected:
            # Stamp the card's own identity onto it so consumers (React dashboard, Nexus
            # Launcher) can report shown/tapped/dismissed against the same (rule_id,
            # subject_key) this suppression pass uses -- without this, a consumer would
            # have no reliable way to identify a card (the card's own "mode" field
            # collides across rules; see CARD_SUBJECT_KEY_EXTRACTORS' own comment).
            subject_key = self._card_subject_key(rule_id, card)
            card["rule_id"] = rule_id
            card["subject_key"] = subject_key
            if card.get(CARD_SUPPRESSION_NEVER_OVERRIDE_FIELD):
                displays.append(card)
                continue
            reason = self._card_suppression_reason(rule_id, subject_key)
            if reason:
                logger.info(f"Suppressing {rule_id} card (subject={subject_key!r}): {reason}")
                continue
            displays.append(card)

        if not displays:
            logger.info("No priority displays, defaulting to time and weather")

        logger.debug("Displays before sorting: " + str(displays))
        # sort by priority
        displays.sort(key=lambda x: x["priority"])

        logger.debug("Final displays selected: " + str(displays))
        return displays[: self.MAX_DISPLAYS]

    def _run_shadow(self, frame, legacy_cards):
        """LF-4: score the learners that will replace the legacy rules beside them and log the
        comparison (sa/shadow.py). Never raises and never changes a card."""
        try:
            if getattr(self, "_shadow", None) is None:
                self._shadow = shadow.ShadowRunner(
                    lambda: pymysql.connect(
                        host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
                    ),
                    self._persist_inferences,
                )
            self._shadow.run(frame, legacy_cards)
        except Exception as e:
            logger.error(f"Shadow run failed: {e}")

    @staticmethod
    def _card_subject_key(rule_id, card):
        """Subject-key half of a card's (rule_id, subject_key) identity (SA-1) -- ""
        for the (majority of) rules with no per-entity extractor registered in
        CARD_SUBJECT_KEY_EXTRACTORS, meaning the whole rule is one suppressible slot."""
        extractor = CARD_SUBJECT_KEY_EXTRACTORS.get(rule_id)
        return extractor(card) if extractor else ""

    def _card_suppression_reason(self, rule_id, subject_key):
        """Return a short reason string to suppress this (rule_id, subject_key) card
        identity, or None to show it as normal. Reads card_interactions only -- the
        daemon never writes to it, only consumers report shown/tapped/dismissed/expired
        (see routes/context.py's POST /api/context/card-interaction); a published card
        that never made it past a client's own display cap was never actually "shown",
        and the daemon has no way to know that, so it must not assume otherwise."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT action, occurred_at FROM card_interactions "
                "WHERE rule_id = %s AND subject_key = %s ORDER BY occurred_at DESC LIMIT %s",
                (rule_id, subject_key, CARD_SUPPRESSION_HISTORY_LIMIT),
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            latest_action, latest_at = rows[0]
            if latest_action == "dismissed":
                cooldown = CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE.get(
                    rule_id, CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES
                )
                since = datetime.now(timezone.utc) - latest_at.replace(tzinfo=timezone.utc)
                if since < timedelta(minutes=cooldown):
                    return "cooldown"
                return None

            run_length = 0
            for action, _ in rows:
                if action != "shown":
                    break
                run_length += 1
            threshold = CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE.get(
                rule_id, CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES
            )
            if run_length >= threshold:
                return "repetition"
            return None
        except pymysql.Error as e:
            logger.error(f"Card suppression check error: {e}")
            return None
        finally:
            if db:
                db.close()

    def check_system_health(self, frame=None):
        """Urgent card when a configured integration (Home Assistant, SmartThings) has failed
        SYSTEM_HEALTH_FAILURES_BEFORE_ALERT consecutive probes. SA had no way to say "I'm blind"
        -- an HA outage just made every synced device read offline with nothing on the dashboard
        explaining why.

        Probes are rate-limited to SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS per integration (each is
        a network call with a 10s timeout); between probes the last result stands. An
        unconfigured integration is skipped entirely, never alerted on. Sets `urgent`, so
        decide_displays() never suppresses it. Not a frame field (SA-4) -- it probes external
        services rather than reading shared state.
        """
        from common import ha_utils, st_utils

        modules = {"ha_utils": ha_utils, "st_utils": st_utils}
        now = time.time()
        down = []
        for key, name, module_name, configured_fn, probe_fn in SYSTEM_HEALTH_INTEGRATIONS:
            state = SYSTEM_HEALTH_STATE.setdefault(key, {"failures": 0, "last_probe": 0.0})
            try:
                if now - state["last_probe"] >= SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS:
                    state["last_probe"] = now
                    module = modules[module_name]
                    if not getattr(module, configured_fn)():
                        state["failures"] = 0
                    elif getattr(module, probe_fn)()[0]:
                        state["failures"] = 0
                    else:
                        state["failures"] += 1
            except Exception as e:
                # A broken probe must not take the whole SA cycle down, and must not count as
                # the integration being down either -- that would be a false urgent alert.
                logger.error(f"System health probe for {key} failed: {e}")
            if state["failures"] >= SYSTEM_HEALTH_FAILURES_BEFORE_ALERT:
                down.append((key, name, state["failures"]))

        if not down:
            return None
        names = ", ".join(name for _key, name, _n in down)
        minutes = SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS // 60
        return {
            "mode": "system_health",
            "content": f"{names} unreachable — synced devices will read offline",
            "priority": 2.2,
            "urgent": True,
            "data": {
                "unreachable": [key for key, _name, _n in down],
                "because": [
                    f"{name}: {n} consecutive failed checks (every {minutes} min)"
                    for _key, name, n in down
                ],
            },
        }

    def check_disk_health(self, frame=None):
        """Card when host disk, the Parquet lake or MySQL growth is running out of room, from the
        `disk.root` and `lake.*` rows sa-learner writes to sa_storage_metrics (sa/disk.py).

        warn is an ambient card; critical sets `urgent` (never suppressed) and speaks once a day.
        Debounced by sa.disk.assess() -- two consecutive samples must agree -- and the history
        read is cached for DISK_HEALTH_CHECK_INTERVAL_SECONDS. Never deletes anything: the card
        only says what the numbers are.
        """
        del frame
        now = time.time()
        state = DISK_HEALTH_STATE
        if now - state["checked"] >= DISK_HEALTH_CHECK_INTERVAL_SECONDS:
            state["checked"] = now
            db = None
            try:
                db = pymysql.connect(
                    host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
                )
                utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
                state["result"] = disk.assess(
                    disk.load_samples(db, utc_now),
                    disk.load_lake_totals(db, utc_now),
                    disk.load_host_usage(db, utc_now),
                )
            except Exception as e:
                # Keep the last result: a DB blip must not clear or raise a disk alert.
                logger.error(f"Disk health check error: {e}")
            finally:
                if db:
                    db.close()
        result = state["result"]
        if not result or result["level"] == "ok":
            return None

        critical = result["level"] == "critical"
        free_gb = result["free"] / 1024**3
        if critical and now - state["spoke"] >= DISK_HEALTH_SPEAK_COOLDOWN_SECONDS:
            p = get_producer()
            if p:
                p.send(
                    "speak",
                    (
                        f"Heads up, the server is down to {free_gb:.0f} gigabytes of free disk."
                        " It needs some cleaning soon."
                    ).encode("utf-8"),
                )
                state["spoke"] = now
        return {
            "mode": "disk_health",
            "content": (
                f"Disk space {'critically ' if critical else ''}low: {free_gb:.1f} GB free"
                + (
                    f", full in about {result['days_left']:.0f} days"
                    if result["days_left"] is not None and result["days_left"] < 365
                    else ""
                )
            ),
            "priority": 2.1 if critical else 5.9,
            **({"urgent": True} if critical else {}),
            "data": {
                "level": result["level"],
                "free_bytes": result["free"],
                "total_bytes": result["total"],
                "days_left": result["days_left"],
                "lake_bytes": result["lake_bytes"],
                "because": result["because"],
            },
        }

    def check_emails(self, frame=None):
        """Check for unread emails using Gmail utils. Not a frame field (SA-4) -- not
        duplicated by any other rule, so its own direct Gmail call stays as-is.
        `frame` defaults to None (unused) because perform_waking_hours_tasks() also
        calls this directly, outside decide_displays()'s per-cycle frame, for its own
        separate "check Gmail" waking-hours routine."""
        del frame
        emails = gmail_utils.check_unread_emails()
        if emails:
            email = emails[0]  # Take first
            content_lines = f"From: {email['sender']}, Subject: {email['subject']}"
            content = f"Unread Email - {content_lines} | Total Unread: {len(emails)}"
            return {"mode": "email", "content": content, "priority": 4}

    def check_events(self, frame):
        """Check for upcoming events, showing plain title/time info.

        `frame.upcoming_events` (SA-4) replaces this rule's own
        calendar_utils.get_upcoming_events() call -- check_focus_needed() reads the exact same
        query, so both now share the one fetch build_context_frame() makes per cycle.
        """
        events = frame.upcoming_events
        if not events:
            return None
        event = events[0]  # Take first
        if event["start_time"] - frame.now > timedelta(hours=3):
            return None  # Only care about events within next hour
        title = event["title"]
        start_time = event["start_time"]
        minutes_until = int((start_time - frame.now).total_seconds() / 60)
        content = f"Upcoming event: {title} at {frame.to_local(start_time).strftime('%I:%M %p')}"
        return {
            "mode": "event",
            "content": content,
            "priority": 2,
            "data": {
                "title": title,
                "start_time": start_time.isoformat(),
                "minutes_until": minutes_until,
                "because": [f"{title} starts in {minutes_until} min"],
            },
        }

    def check_travel(self, frame):
        """SA-6: restores what commit 08509ce removed (Google Maps Directions-based
        check_travel()), on self-hosted infrastructure -- see
        todo/sa/todo_self_hosted_routing.md for the Phase 0 spike that justified self-hosted OSRM
        for routing (measured live against real production hardware) plus the public Nominatim
        API for the much rarer geocoding need, over any paid/hosted alternative.

        Fires for any upcoming event (see UPCOMING_EVENTS_LOOKAHEAD_HOURS) that has a resolvable
        physical destination -- a non-empty `address` and no `conference_uri` (a video call has
        nowhere to drive to; that case is check_focus_needed()'s job, not this one's) -- as long
        as its computed leave-by time hasn't meaningfully passed yet (TRAVEL_STALE_AFTER_MINUTES).
        No upper bound on how far in advance: how soon to actually surface this to the household
        is a display decision, made downstream (see TRAVEL_STALE_AFTER_MINUTES's own doc comment).

        Fails closed and silent at every step: an ungeocodable address, a household location
        that hasn't been geocoded yet, or an unreachable routing container all mean no card,
        never a fabricated estimate -- the exact anti-pattern the original implementation was
        criticized for. `data.traffic_aware` is always `false`: none of the self-hosted routing
        engines evaluated match Google's live-traffic layer, so no consumer should present this
        as anything but a free-flow/typical-conditions estimate.
        """
        events = frame.upcoming_events
        if not events:
            return None
        event = events[0]
        address = (event.get("address") or "").strip()
        if not address or event.get("conference_uri"):
            return None
        start_time = event.get("start_time")
        if start_time is None or frame.now is None:
            return None

        dest = routing_utils.geocode_address(address)
        if dest is None:
            return None
        origin = routing_utils.fetch_home_coordinates(ENV_NAME)
        if origin is None:
            return None
        route = routing_utils.get_route(origin, dest)
        if route is None:
            return None

        leave_by = start_time - timedelta(minutes=route["duration_minutes"])
        minutes_until_leave = (leave_by - frame.now).total_seconds() / 60
        if minutes_until_leave < -TRAVEL_STALE_AFTER_MINUTES:
            return None

        title = event["title"]
        duration_minutes = round(route["duration_minutes"])
        distance_km = round(route["distance_km"], 1)
        content = f"Leave by {frame.to_local(leave_by).strftime('%I:%M %p')} for {title}"
        return {
            "mode": "travel",
            "content": content,
            "priority": 2.5,
            "data": {
                "duration_minutes": duration_minutes,
                "distance_km": distance_km,
                "traffic_aware": False,
                "leave_by": leave_by.isoformat(),
                "because": [f"{duration_minutes} min drive to {title}"],
            },
        }

    def check_focus_needed(self, frame):
        """Check whether the next upcoming event looks like a call starting soon.

        Reuses `frame.upcoming_events` (SA-4; same source check_events() reads) and applies
        focus_utils.looks_like_call() (SA-7) -- tiered by confidence: `focus_utils.CONFIRMED`
        when the event carries real synced conferencing data (`conference_uri`),
        `focus_utils.PROBABLE` when only the text heuristic over address/notes matches. See
        focus_utils' module docstring for the full tier breakdown and known false-positive
        shape of the probable tier. Only fires within FOCUS_LEAD_MINUTES of the event's start.

        DND correlation (todo/sa/todo_context_exchange_protocol.md Phase 2, and the deferred
        follow-up todo_attention_telemetry.md asked for): when a Deck reports Do Not Disturb
        already on, "Find a quiet spot." is advice the user has visibly already taken, so the
        card drops it and says so instead. It deliberately still *fires* -- the useful part of
        this card is "your call starts in N minutes," and silencing that because the phone is
        silenced would throw away the alert to preserve the footnote.

        Note the tri-state: only an explicit `True` changes the wording. A household with no
        Deck reporting (None) gets exactly the pre-Phase-2 card, rather than being treated as
        "DND off" and told something subtly wrong about a device nobody asked about.
        """
        events = frame.upcoming_events
        if not events:
            return None
        event = events[0]
        confidence = focus_utils.looks_like_call(
            event["address"], event["notes"], event.get("conference_uri")
        )
        if not confidence:
            return None
        start_time = event["start_time"]
        if start_time - frame.now > timedelta(minutes=FOCUS_LEAD_MINUTES):
            return None
        title = event["title"]
        start_label = frame.to_local(start_time).strftime("%I:%M %p")
        if confidence == focus_utils.CONFIRMED:
            solution = event.get("conference_solution") or "Call"
            lead = f"{solution} starting soon"
        else:
            lead = "Looks like a call starting soon"
        device_contexts = (frame.launcher_context and frame.launcher_context.device_contexts) or {}
        in_dnd = self._any_device_in_dnd(device_contexts)
        advice = "Do Not Disturb is already on." if in_dnd else "Find a quiet spot."
        content = f"{lead}: {title} at {start_label}. {advice}"
        minutes_until = int((start_time - frame.now).total_seconds() / 60)
        because = [
            f"{title} starts in {minutes_until} min",
            (
                "confirmed conferencing data"
                if confidence == focus_utils.CONFIRMED
                else "text looks like a call"
            ),
        ]
        if in_dnd:
            because.append("a Deck reports Do Not Disturb on")
        return {
            "mode": "focus_needed",
            "content": content,
            "priority": 3.5,
            "confidence": confidence,
            "conference_uri": event.get("conference_uri"),
            "dnd_active": in_dnd,
            "data": {
                "title": title,
                "start_time": start_time.isoformat(),
                "minutes_until": minutes_until,
                "because": because,
            },
        }

    def _online_guest_stay_days(self, cursor, now):
        """Continuous-stay guest decay: days-of-continuous-stay for every currently-online
        guest, shared by check_gatherings() (energy/priority) and
        check_guest_overstay_advisory() (the resolve-this nudge) so both read the same
        underlying signal. NULL continuous_stay_since (not yet backfilled, or a stay that
        hasn't started per service_user.app.update_user_state()) is treated as a fresh
        arrival (0 days) rather than fabricating an overstay from missing data.
        """
        cursor.execute("""
            SELECT username, continuous_stay_since
            FROM user u
            JOIN states s ON u.state = s.id
            JOIN user_types ut ON u.type = ut.id
            WHERE s.state = 'online' AND ut.type = 'guest' AND u.username != 'unknown'
            """)
        results = []
        for username, continuous_stay_since in cursor.fetchall():
            if continuous_stay_since:
                since = (
                    continuous_stay_since.replace(tzinfo=timezone.utc)
                    if continuous_stay_since.tzinfo is None
                    else continuous_stay_since
                )
                days = max(0.0, (now - since).total_seconds() / 86400)
            else:
                days = 0.0
            results.append((username, days))
        return results

    def check_gatherings(self, frame):
        """Check for gatherings (>3 guests/residents online).

        `frame.local_dt`/`frame.day_mood` (SA-4) replace this rule's own
        db_utils.get_env_local_time()/mood_utils.get_day_mood() calls -- check_party_advisory(),
        check_wind_down_signal(), and check_mood() all needed the exact same pair. `frame.
        environment`'s description/subjective_feel replace this rule's own separate read of the
        same `environment` row check_weather()/check_weather_advisory() also read.
        """
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN ut.type IN ('guest') THEN 1 ELSE 0 END) as guest_count,
                    COUNT(*) as total_count
                FROM user u
                JOIN states s ON u.state = s.id
                JOIN user_types ut ON u.type = ut.id
                WHERE s.state = 'online' AND u.username != 'unknown'
                """)
            row = cursor.fetchone()
            # SUM() returns decimal.Decimal via pymysql (unlike COUNT()'s plain int) -- cast
            # so guest_count is safe to embed directly in the "data" dict's JSON payload (SA-5),
            # not just interpolated into f-string content like before.
            guest_count = int(row[0]) if row and row[0] else 0
            total_count = int(row[1]) if row and row[1] else 0

            if guest_count > 0:
                logger.info(
                    "Gathering detected with total people: "
                    + str(total_count)
                    + " (guests: "
                    + str(guest_count)
                    + ")"
                )
                if frame.local_dt is None or frame.day_mood is None:
                    return None
                local_dt = frame.local_dt
                time_of_day = frame.day_mood["time_of_day"]
                environment = frame.environment or {}
                weather_info = {
                    "description": environment.get("description"),
                    "subjective_feel": environment.get("subjective_feel"),
                }

                guest_stays = self._online_guest_stay_days(
                    cursor, frame.now or datetime.now(timezone.utc)
                )
                guest_energy_bonus = spotify_utils.aggregate_guest_energy(
                    [days for _, days in guest_stays]
                )

                reco = spotify_utils.recommend(
                    total_people=total_count,
                    guest_count=guest_count,
                    time_of_day=time_of_day,
                    weather=weather_info,
                    is_party_night=spotify_utils.is_party_night(local_dt),
                    guest_energy_bonus=guest_energy_bonus,
                )
                logger.info(f"Recommendation: {reco}")

                p = get_producer()
                if p:
                    event = {
                        "id": f"gathering_detected_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "type": "info",
                        "message": (
                            f"Gathering detected with {total_count} people "
                            f"({guest_count} guests). Suggesting {reco['mood']} music "
                            f"({reco['genre']})."
                        ),
                        "time": datetime.now(timezone.utc).isoformat(),
                    }
                    p.send("event-stream", orjson.dumps(event))

                hint = reco.get("playlist_hint", reco.get("mood", ""))
                playlist = None
                try:
                    playlist = spotify_utils.resolve_playlist(hint, reco.get("genre", ""))
                except Exception as e:
                    logger.warning(f"Playlist resolution failed, using text hint only: {e}")

                display_name = playlist.get("name") if playlist else hint
                content = f"Play {display_name} ({reco['genre']}, energy={reco['energy']})"

                # Continuous-stay guest decay: demote this card's own priority as its guests'
                # decayed energy drops toward the floor -- a houseful of long-staying guests
                # shouldn't keep surfacing as prominently as a fresh gathering does.
                span = spotify_utils.GUEST_STAY_ENERGY_PEAK - spotify_utils.GUEST_STAY_ENERGY_FLOOR
                penalty = (
                    GUEST_CARD_PRIORITY_MAX_DEMOTION
                    * (spotify_utils.GUEST_STAY_ENERGY_PEAK - guest_energy_bonus)
                    / span
                )
                because = [f"{guest_count} guest(s) online", f"{time_of_day} time of day"]
                because.extend(
                    f"{username}: {days:.0f}d continuous, contribution "
                    f"{spotify_utils.guest_stay_energy_contribution(days):+.2f}"
                    for username, days in guest_stays
                )

                card = {
                    "mode": "music",
                    "content": content,
                    "priority": round(3.0 + penalty, 3),
                    "data": {
                        "mood": reco.get("mood"),
                        "genre": reco.get("genre"),
                        "energy": reco.get("energy"),
                        "tempo_hint": reco.get("tempo_hint"),
                        "guest_count": guest_count,
                        "total_count": total_count,
                        "time_of_day": time_of_day,
                        "guest_energy_contribution": round(guest_energy_bonus, 3),
                        "because": because,
                    },
                }
                if playlist:
                    card.update(
                        {
                            "playlist_id": playlist.get("id"),
                            "playlist_name": playlist.get("name"),
                            "playlist_uri": playlist.get("uri"),
                            "playlist_url": playlist.get("url"),
                            "playlist_image": playlist.get("image"),
                            "playlist_source": playlist.get("source"),
                        }
                    )
                return card
            return None
        except pymysql.Error as e:
            logger.error("Gathering check error: " + str(e))
            if db:
                db.rollback()
            return None
        finally:
            if db:
                db.close()

    def check_guest_overstay_advisory(self, frame):
        """Continuous-stay guest decay: once a guest's decayed energy contribution
        (spotify_utils.guest_stay_energy_contribution(), see check_gatherings()/
        _online_guest_stay_days()) has gone negative -- day ~14+ of an unbroken stay -- nudge
        the household to actually resolve the situation before their continued presence drags
        the household energy down further: promote them to resident, or address the overstay.

        Only one card per cycle, same "single most-overdue" precedent as
        check_departure_anomaly()/check_rhythm_break_anomaly() -- picks the guest whose
        contribution has decayed furthest negative. CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE
        keeps this from re-firing more than once a day, since the underlying signal (days of
        stay) only moves that slowly.
        """
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            guest_stays = self._online_guest_stay_days(
                cursor, frame.now or datetime.now(timezone.utc)
            )
            overstaying = [
                (spotify_utils.guest_stay_energy_contribution(days), username, days)
                for username, days in guest_stays
            ]
            overstaying = [row for row in overstaying if row[0] < 0]
            if not overstaying:
                return None

            overstaying.sort()
            contribution, username, days = overstaying[0]
            return {
                "mode": "guest_overstay_advisory",
                "content": (
                    f"{username} has been staying continuously for {int(days)} day(s) — "
                    "consider promoting them to resident, or addressing the overstay"
                ),
                "priority": 3.15,
                "entity_name": username,
                "data": {
                    "days_continuous": round(days, 1),
                    "energy_contribution": round(contribution, 3),
                    "because": [
                        f"{int(days)} days of continuous stay",
                        f"energy contribution {contribution:+.2f} (negative past day 14)",
                    ],
                },
            }
        except pymysql.Error as e:
            logger.error("Guest overstay advisory check error: " + str(e))
            if db:
                db.rollback()
            return None
        finally:
            if db:
                db.close()

    def check_household_composition(self, frame):
        """Report which household members' claimed devices are online right now, vs. how
        many unclaimed/unknown MACs are also on the network.

        `device.user_id` is already exactly "this MAC is claimed by a household member" --
        the arp-scan sync (service_device.app.check_lan/update_or_create_device) never sets
        it on discovery, only the device-management UI does -- so no new table is needed to
        tell known from unknown. Priority is computed here rather than fixed in DISPLAY_RULES:
        ambient (6.2) when everything online is claimed, elevated (2.3, security-relevant)
        when at least one unclaimed device is online.

        `frame.online_devices` (SA-4) replaces this rule's own device/state/user query --
        the same fetch check_empty_house_still_on() also reads.
        """
        online = frame.online_devices
        if not online or not online["rows"]:
            return None

        known_names = online["known_names"]
        known_count = online["known_count"]
        unknown_count = online["unknown_count"]

        if unknown_count > 0:
            content = f"{unknown_count} unrecognized device(s) on the network" + (
                f" alongside {', '.join(known_names)}" if known_names else ""
            )
            return {
                "mode": "household_composition",
                "content": content,
                "priority": 2.3,
                "known_count": known_count,
                "unknown_count": unknown_count,
                "urgent": True,
                "data": {"known_names": known_names},
            }

        content = f"Home: {', '.join(known_names)}" if known_names else "No known devices online"
        return {
            "mode": "household_composition",
            "content": content,
            "priority": 6.2,
            "known_count": known_count,
            "unknown_count": unknown_count,
            "urgent": False,
            "data": {"known_names": known_names},
        }

    def check_empty_house_still_on(self, frame):
        """No claimed household member's device is online, but at least one smart-home
        device still is -- the SA-4 Phase 3 proof case: a rule that genuinely could not have
        been written before the context frame existed, since it needs `frame.online_devices`
        (is anyone actually home), `frame.smarthome_online` (what's still running), and
        `frame.day_mood` (only worth a nudge once it's evening/night -- during the day
        "everyone's out, the office lamp is on" is unremarkable, not everyone being home all
        day is normal) all at once. Observation only, like every other card in this file --
        it names what's still on, it does not turn anything off.
        """
        online = frame.online_devices
        smarthome_online = frame.smarthome_online
        if online is None or online["known_count"] > 0:
            return None
        if not smarthome_online:
            return None
        if frame.day_mood is None or frame.day_mood["time_of_day"] not in ("evening", "night"):
            return None
        content = f"House appears empty, but {', '.join(smarthome_online)} still on"
        return {
            "mode": "empty_house_still_on",
            "content": content,
            "priority": 2.4,
            "device_count": len(smarthome_online),
            "data": {
                "smarthome_device_names": smarthome_online,
                "because": [
                    "no claimed household device online",
                    f"{frame.day_mood['time_of_day']}",
                ],
            },
        }

    def check_rhythm_break_anomaly(self, frame):
        """Compare devices against their `entity_baselines` row and surface a card only on a
        genuine deviation from routine. Three deviation types, checked in this order (the first
        one that fires wins -- still one card per cycle, same "one card per check" shape as every
        other DISPLAY_RULES method):

        1. `still_on_past_typical` (original): a currently-online device has been on
           RHYTHM_BREAK_GRACE_MINUTES+ past its typical_daily_max for this session.
        2. `unusual_hour` (SA-10): a currently-online device's *current* hour (and the hours either
           side of it) are all outside its active_hours_mask -- the hours it was actually online
           on a meaningful share of days. (This used to measure distance from typical_active_hour,
           the modal session *start* hour, which flagged any session running longer than the
           tolerance -- i.e. every ordinary workday afternoon.)
        3. `expected_absent` (SA-10): a currently-*offline* device is still absent within
           EXPECTED_ABSENT_WINDOW_HOURS of its typical_active_hour -- "it should be on by now."
           Known limitation: doesn't handle a typical_active_hour that wraps past midnight (e.g.
           23 + a 3-hour window) -- narrow edge case, not worth the extra query complexity this
           pass; documented here rather than silently wrong.

        All three require `eb.sample_count >= eb.min_sample_count` explicitly (SA-10's
        min_sample_count column) rather than trusting every row in the table implicitly --
        today every row already cleared its floor at write time, but this is the same "do I
        trust this yet" check every consumer should make, not just the ones that happen to need
        it right now.

        Not a frame field (SA-4) -- this device/entity_baselines join isn't duplicated by any
        other rule, so it stays its own query; only `frame.now` (SA-4's single
        shared-per-cycle timestamp) replaces this rule's own datetime.now(timezone.utc) call.
        """
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            now = frame.now

            cursor.execute(
                """
                SELECT d.name, TIMESTAMPDIFF(MINUTE, d.last_online, %s) AS minutes_on,
                       eb.typical_daily_max
                FROM device d
                JOIN states s ON d.state = s.id
                JOIN entity_baselines eb ON eb.entity_type = 'device' AND eb.entity_id = d.id
                WHERE s.state = 'online'
                  AND d.last_online IS NOT NULL
                  AND eb.typical_daily_max IS NOT NULL
                  AND eb.sample_count >= eb.min_sample_count
                  AND TIMESTAMPDIFF(MINUTE, d.last_online, %s) > eb.typical_daily_max + %s
                ORDER BY (TIMESTAMPDIFF(MINUTE, d.last_online, %s) - eb.typical_daily_max) DESC
                LIMIT 1
                """,
                (now, now, RHYTHM_BREAK_GRACE_MINUTES, now),
            )
            row = cursor.fetchone()
            if row:
                name, minutes_on, typical_max = row
                over_by = int(minutes_on - typical_max)
                return {
                    "mode": "rhythm_break_anomaly",
                    "content": f"{name} has been on for {over_by} min longer than usual",
                    "priority": 2.6,
                    "entity_name": name,
                    "deviation_type": "still_on_past_typical",
                    "data": {
                        "over_by_minutes": over_by,
                        "typical_daily_max_minutes": int(typical_max),
                        "because": [
                            f"on {over_by} min past its typical max ({int(typical_max)} min)"
                        ],
                    },
                }

            current_hour = now.hour
            nearby_hours_mask = sum(1 << ((current_hour + offset) % 24) for offset in (-1, 0, 1))
            cursor.execute(
                """
                SELECT d.name, eb.typical_active_hour, eb.active_hours_mask
                FROM device d
                JOIN states s ON d.state = s.id
                JOIN entity_baselines eb ON eb.entity_type = 'device' AND eb.entity_id = d.id
                WHERE s.state = 'online'
                  AND eb.active_hours_mask IS NOT NULL
                  AND eb.active_hours_mask <> 0
                  AND eb.sample_count >= eb.min_sample_count
                  AND (eb.active_hours_mask & %s) = 0
                ORDER BY d.id
                LIMIT 1
                """,
                (nearby_hours_mask,),
            )
            row = cursor.fetchone()
            if row:
                name, typical_hour, active_mask = row
                active_hours = [h for h in range(24) if active_mask >> h & 1]
                return {
                    "mode": "rhythm_break_anomaly",
                    "content": f"{name} is on at an unusual hour",
                    "priority": 2.6,
                    "entity_name": name,
                    "deviation_type": "unusual_hour",
                    "data": {
                        "current_hour": current_hour,
                        "typical_active_hour": int(typical_hour),
                        "because": [
                            f"on at {current_hour:02d}:00, but usually only on between "
                            f"{active_hours[0]:02d}:00 and {active_hours[-1]:02d}:59"
                        ],
                    },
                }

            cursor.execute(
                """
                SELECT d.name, HOUR(%s) AS current_hour, eb.typical_active_hour
                FROM device d
                JOIN states s ON d.state = s.id
                JOIN entity_baselines eb ON eb.entity_type = 'device' AND eb.entity_id = d.id
                WHERE s.state = 'offline'
                  AND d.last_online >= %s - INTERVAL %s DAY
                  AND eb.typical_active_hour IS NOT NULL
                  AND eb.sample_count >= eb.min_sample_count
                  AND HOUR(%s) >= eb.typical_active_hour
                  AND HOUR(%s) < eb.typical_active_hour + %s
                ORDER BY (HOUR(%s) - eb.typical_active_hour) DESC
                LIMIT 1
                """,
                (
                    now,
                    now,
                    EXPECTED_ABSENT_MAX_OFFLINE_DAYS,
                    now,
                    now,
                    EXPECTED_ABSENT_WINDOW_HOURS,
                    now,
                ),
            )
            row = cursor.fetchone()
            if row:
                name, current_hour, typical_hour = row
                return {
                    "mode": "rhythm_break_anomaly",
                    "content": f"{name} hasn't come online yet",
                    "priority": 2.6,
                    "entity_name": name,
                    "deviation_type": "expected_absent",
                    "data": {
                        "typical_active_hour": int(typical_hour),
                        "because": [
                            f"usually active by {int(typical_hour):02d}:00, "
                            f"still offline at {int(current_hour):02d}:00"
                        ],
                    },
                }

            return None
        except pymysql.Error as e:
            logger.error("Rhythm break anomaly check error: " + str(e))
            return None
        finally:
            if db:
                db.close()

    def check_departure_anomaly(self, frame):
        """SA-3: "usually gone by now, still home" -- the human analogue of
        check_rhythm_break_anomaly(), reading compute_entity_baselines()'s `entity_type='user'`
        rows instead of `'device'`. See todo/sa/todo_departure_anomaly.md for the Phase 0 spike that
        justified deriving this from the existing device_history/entity_baselines pattern rather
        than a new table.

        Fires only when every one of these holds, for at least one resident:
        - a reliable baseline exists for today's weekday/weekend bucket (sample-count floor
          *and* a tight-enough observed hour spread -- DEPARTURE_BASELINE_MIN_SAMPLES/
          DEPARTURE_BASELINE_MAX_SPREAD_HOURS; a resident whose real departure times are just
          scattered gets no baseline at all rather than a noisy one),
        - the local hour is past that baseline's typical departure hour, plus a grace window
          (DEPARTURE_ANOMALY_GRACE_HOURS) so running a bit late isn't an anomaly,
        - at least one of that resident's claimed devices is online right now,
        - and no household calendar event covers this exact moment (a booked morning at home,
          e.g. WFH, is not a deviation -- checked directly against calendar_events, not
          frame.upcoming_events, which only looks a couple hours *forward* and would miss an
          event already in progress).

        Only one card per cycle, same "single most-overdue" precedent as
        check_rhythm_break_anomaly() -- picks the resident furthest past their typical hour.

        Tone constraint (from the task doc): this is an ambient observation, never a welfare
        check. "Still home -- unusual for a Tuesday," never "is everything okay?"
        """
        if frame.local_dt is None or frame.day_mood is None:
            return None
        local_dt = frame.local_dt
        day_bucket = "weekend" if local_dt.weekday() >= 5 else "weekday"
        current_hour = local_dt.hour + local_dt.minute / 60

        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                """
                SELECT eb.entity_id, u.username, eb.typical_active_hour, eb.sample_count
                FROM entity_baselines eb
                JOIN user u ON u.id = eb.entity_id
                JOIN user_types ut ON u.type = ut.id
                WHERE eb.entity_type = 'user' AND eb.day_bucket = %s
                  AND eb.sample_count >= %s
                  AND (eb.typical_daily_max - eb.typical_daily_min) <= %s
                  AND ut.type IN ('owner', 'technoking', 'resident')
                """,
                (day_bucket, DEPARTURE_BASELINE_MIN_SAMPLES, DEPARTURE_BASELINE_MAX_SPREAD_HOURS),
            )
            candidates = cursor.fetchall()
            if not candidates:
                return None

            overdue = []
            for user_id, username, typical_hour, sample_count in candidates:
                if current_hour < typical_hour + DEPARTURE_ANOMALY_GRACE_HOURS:
                    continue
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM device d
                    JOIN states s ON d.state = s.id
                    WHERE d.user_id = %s AND s.state = 'online'
                    """,
                    (user_id,),
                )
                (online_count,) = cursor.fetchone()
                if online_count == 0:
                    continue
                overdue.append((current_hour - typical_hour, username, typical_hour, sample_count))

            if not overdue:
                return None

            cursor.execute(
                "SELECT 1 FROM calendar_events WHERE start_time <= %s AND end_time >= %s LIMIT 1",
                (frame.now, frame.now),
            )
            if cursor.fetchone():
                return None

            overdue.sort(reverse=True)
            _over_by, username, typical_hour, sample_count = overdue[0]
            day_of_week = frame.day_mood["day_of_week"]
            return {
                "mode": "departure_anomaly",
                "content": f"{username} still home — unusual for a {day_of_week}",
                "priority": 2.7,
                "entity_name": username,
                "data": {
                    "typical_departure_hour": int(typical_hour),
                    "sample_count": sample_count,
                    "because": [
                        f"usually gone by {int(typical_hour):02d}:00 on a {day_bucket}",
                        f"{sample_count} samples in the last "
                        f"{DEPARTURE_BASELINE_LOOKBACK_DAYS} days",
                    ],
                },
            }
        except pymysql.Error as e:
            logger.error("Departure anomaly check error: " + str(e))
            return None
        finally:
            if db:
                db.close()

    # --- LF-3: presence deviation ---------------------------------------------------------

    # Only these people get a CARD for being away (a guest being out is just a guest leaving).
    # Every deviation, for anyone, is still recorded in sa_inferences.
    PRESENCE_CARD_USER_TYPES = ("owner", "technoking", "resident")

    def _presence_profiles(self):
        """Presence profiles by user id, reloaded only when sa-learner has written a newer fit:
        one MAX() query per cycle, a full reload (a handful of rows) only when it changed."""
        cache = getattr(self, "_presence_cache", {})
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            stamp = inference_store.profiles_stamp(db, presence_learner.NAME)
            if stamp is None:
                self._presence_cache, self._presence_stamp = {}, None
            elif stamp != getattr(self, "_presence_stamp", None):
                loaded = inference_store.load_profiles(db, presence_learner.NAME)
                self._presence_cache = {str(p.subject_id): p for p in loaded}
                self._presence_stamp = stamp
                logger.info(f"Loaded {len(loaded)} presence profile(s) fitted {stamp}")
            return getattr(self, "_presence_cache", {})
        except pymysql.Error as e:
            logger.error("Presence profile load error: " + str(e))
            return cache
        finally:
            if db:
                db.close()

    def _persist_inferences(self, inferences):
        """Record scored inferences (best effort: a write failure must never cost the card)."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            for inference in inferences:
                inference_store.upsert_inference(db, inference)
        except pymysql.Error as e:
            logger.error("Inference persist error: " + str(e))
        finally:
            if db:
                db.close()

    def _calendar_busy_at(self, moment):
        """Whether any household calendar event covers `moment` (naive UTC). A booked absence is
        not a deviation -- checked directly, like check_departure_anomaly(), since
        frame.upcoming_events only looks forward."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT 1 FROM calendar_events WHERE start_time <= %s AND end_time >= %s LIMIT 1",
                (moment, moment),
            )
            return cursor.fetchone() is not None
        except pymysql.Error as e:
            logger.error("Presence calendar check error: " + str(e))
            return False
        finally:
            if db:
                db.close()

    def check_presence_deviation(self, frame):
        """LF-3: "out, but usually home at this hour". Scores each person's current state
        (home/away, from the phone) against their learned P(home | weekday, hour) and records any
        improbable one in sa_inferences with a probability and a confidence. Fires a card only for
        an owner/resident who has been away at least MIN_AWAY_MINUTES (phones nap ~30 minutes
        without leaving), whose confidence clears MIN_CARD_CONFIDENCE, with no household calendar
        event covering now. One card per cycle: the most surprising, weighted by confidence.

        Tone constraint, inherited from SA-3: an ambient observation, never a welfare check.
        """
        if frame.person_presence is None or frame.local_dt is None or frame.now is None:
            return None
        profiles = self._presence_profiles()
        if not profiles:
            return None
        learner = presence_learner.PresenceLearner()
        now_utc = frame.now.replace(tzinfo=None)
        scored = []
        for person in frame.person_presence:
            profile = profiles.get(str(person["user_id"]))
            if profile is None:
                continue
            away_minutes = None
            if not person["home"] and person["last_online"] is not None:
                away_minutes = (now_utc - person["last_online"]).total_seconds() / 60.0
            inference = learner.score(
                profile,
                {"home": person["home"], "away_minutes": away_minutes, "local_dt": frame.local_dt},
                now_utc,
            )
            if inference is not None:
                scored.append((person, inference))
        if not scored:
            return None
        self._persist_inferences([inference for _person, inference in scored])

        candidates = [
            (person, inference)
            for person, inference in scored
            if not person["home"]
            and person["user_type"] in self.PRESENCE_CARD_USER_TYPES
            and inference.confidence >= presence_learner.MIN_CARD_CONFIDENCE
        ]
        if not candidates:
            return None
        if self._calendar_busy_at(now_utc):
            return None
        person, inference = max(candidates, key=lambda c: c[1].surprise * c[1].confidence)
        day_name = (frame.day_mood or {}).get("day_of_week") or frame.local_dt.strftime("%A")
        hour = inference.context["hour_local"]
        away = int(inference.observed["away_minutes"])
        p_home = inference.expected["p_home"]
        return {
            "mode": "presence_deviation",
            "content": (
                f"{person['username']} is out — usually home {day_name}s around {hour:02d}:00"
            ),
            "priority": 2.75,
            "entity_name": person["username"],
            "data": {
                "expected_p_home": p_home,
                "away_minutes": away,
                "surprise_bits": inference.surprise,
                "confidence": inference.confidence,
                "because": [
                    f"home {round(p_home * 100)}% of {day_name}s at {hour:02d}:00",
                    f"away {away // 60}h {away % 60:02d}m",
                    f"confidence {inference.confidence:.2f}",
                ],
            },
        }

    def check_household_unusual_day(self, frame):
        """SA-10: "is today unusual for this household". Since the LF-4 cutover (2026-10-12) this
        reads the layer-2 inference `household_unusual_day` (sa/learners/household_day.py) instead
        of computing a verdict from entity_baselines: the shadow pass scores the day once it is
        past CUTOFF_HOUR local, combines the day's features (devices active, first device online,
        resident-minutes at home) weighted by confidence, and stores the result in sa_inferences.
        This card is that row, shown while it stays fresh (the shadow pass refreshes it every
        cycle, so it lags the inference by at most one).

        Tone constraint, inherited from SA-10: an observation, never a concern.
        """
        if frame.day_mood is None or frame.now is None:
            return None
        now_utc = frame.now.replace(tzinfo=None)
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            found = [
                i
                for i in inference_store.load_recent(
                    db, 2, now_utc - timedelta(minutes=layer2.FRESH_MINUTES), kinds=("deviation",)
                )
                if i.learner == household_day.NAME
            ]
        except pymysql.Error as e:
            logger.error("Household unusual day check error: " + str(e))
            return None
        finally:
            if db:
                db.close()
        if not found:
            return None
        inference = found[0]
        day_of_week = frame.day_mood["day_of_week"]
        return {
            "mode": "household_unusual_day",
            "content": f"{day_of_week} is running differently than usual",
            "priority": 6.5,
            "data": {
                "surprise_bits": inference.surprise,
                "confidence": inference.confidence,
                "observed": inference.observed,
                "expected": inference.expected,
                "because": household_day.explain(inference),
            },
        }

    def _read_config_json(self, key):
        """Return the JSON value stored under `config.name = key` as a dict,
        or {} if there is none yet or the read fails. Generalized from what
        was originally `_read_now_playing_config()` -- now also used by
        check_cross_surface_continuity() to read SURFACE_STATE_CONFIG_KEY,
        the launcher-reported surface state written by
        `POST /api/context/surface-state` (service_api/routes/context.py)."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute("SELECT value FROM config WHERE name = %s", (key,))
            row = cursor.fetchone()
            return orjson.loads(row[0]) if row and row[0] else {}
        except Exception as e:
            logger.error(f"Config JSON read error ({key}): {e}")
            return {}
        finally:
            if db:
                db.close()

    def _write_now_playing_config(self, state):
        """Upsert the now-playing state into `config`, following the same
        UPDATE-then-INSERT-if-0-rows pattern used elsewhere for this table
        (e.g. spotify_utils.save_spotify_credentials())."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            value = orjson.dumps(state).decode("utf-8")
            cursor.execute(
                "UPDATE config SET value = %s WHERE name = %s",
                (value, NOW_PLAYING_CONFIG_KEY),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO config (name, value) VALUES (%s, %s)",
                    (NOW_PLAYING_CONFIG_KEY, value),
                )
            db.commit()
        except Exception as e:
            logger.error(f"Now playing config write error: {e}")
        finally:
            if db:
                db.close()

    def check_now_playing(self, frame):
        """Surface a situational-awareness card for whatever's actually
        playing on Spotify right now, independent of check_gatherings()'s
        recommendation card.

        Runs every ~60s cycle like every other DISPLAY_RULES check (no
        separate poll loop -- the daemon's outer loop only ticks that often
        anyway). Only persists to `config` and publishes an event-stream
        message when the track or play state actually changed, so it
        doesn't repeat the same "now playing" line every cycle.

        Persists on a play->pause transition too (not just track changes),
        even though no card is returned for the paused state itself --
        check_cross_surface_continuity() needs that persisted "paused N
        minutes ago" state to offer a resume. Before that feature existed,
        pausing never got persisted at all here.

        `frame.playback` (SA-4) replaces this rule's own
        spotify_api.get_playback_state() call -- check_party_advisory() reads the exact same
        fetch. `frame.persisted_now_playing` replaces reading NOW_PLAYING_CONFIG_KEY here --
        check_cross_surface_continuity() reads that same config row too.
        """
        try:
            state = frame.playback or {}
            item = state.get("item") or {}
            track_id = item.get("id")
            is_playing = state.get("is_playing", False)
            if not track_id:
                return None

            # config.value is VARCHAR(512) -- cap title/artist defensively
            # (no album art is stored here; that's re-fetched live from
            # GET /api/music/spotify/status when needed).
            title = (item.get("name") or "")[:150]
            artist = ", ".join(item.get("artists") or [])[:150]

            last = frame.persisted_now_playing or {}
            if last.get("track_id") != track_id or last.get("is_playing") != is_playing:
                self._write_now_playing_config(
                    {
                        "track_id": track_id,
                        "title": title,
                        "artist": artist,
                        "is_playing": is_playing,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                if is_playing:
                    p = get_producer()
                    if p:
                        message = (
                            f"Now playing: {title} by {artist}"
                            if artist
                            else f"Now playing: {title}"
                        )
                        event = {
                            "id": f"now_playing_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            "type": "audio",
                            "message": message,
                            "time": datetime.now(timezone.utc).isoformat(),
                            "subject_type": "track",
                            "subject_id": track_id,
                            "verb": "play_start",
                        }
                        p.send("event-stream", orjson.dumps(event))

            if not is_playing:
                return None

            content = f"{title} — {artist}" if artist else title
            return {
                "mode": "music",
                "content": f"Now playing: {content}",
                "priority": 3.1,
                "track_title": title,
                "track_artist": artist,
                "is_playing": is_playing,
            }
        except Exception as e:
            logger.error(f"Now playing check error: {e}")
            return None

    def check_cross_surface_continuity(self, frame):
        """Offer a "pick up where you left off" resume for whichever surface
        was most recently left active: paused Spotify playback, an edited
        Matrix routine, or a reported launcher (terminal) session. Reads
        three existing signals rather than tracking anything new -- see
        todo/sa/todo_cross_surface_continuity.md.

        Each candidate is discarded if older than
        CROSS_SURFACE_STALENESS_MINUTES -- a paused track from hours ago
        isn't "picking up where you left off" anymore. Returns whichever
        surviving candidate is most recent.

        `frame.persisted_now_playing`/`frame.launcher_context.surface_state` (SA-4) replace
        this rule's own NOW_PLAYING_CONFIG_KEY/SURFACE_STATE_CONFIG_KEY reads --
        check_now_playing() reads the same now-playing config row, and the surface-state row
        isn't duplicated elsewhere but moved into the frame for consistency. The routines
        query below isn't duplicated by anything else, so it stays its own query.
        """
        now = frame.now
        staleness = timedelta(minutes=CROSS_SURFACE_STALENESS_MINUTES)
        candidates = []

        now_playing = frame.persisted_now_playing or {}
        if now_playing.get("is_playing") is False and now_playing.get("updated_at"):
            try:
                paused_at = datetime.fromisoformat(now_playing["updated_at"])
            except ValueError:
                paused_at = None
            if paused_at and now - paused_at <= staleness:
                title = now_playing.get("title") or "your last track"
                minutes_ago = int((now - paused_at).total_seconds() / 60)
                candidates.append(
                    (
                        paused_at,
                        {
                            "mode": "cross_surface_continuity",
                            "content": f"{title} paused {minutes_ago} min ago — resume?",
                            "priority": 5.5,
                            "resume_type": "music",
                            "resume_target": now_playing.get("track_id"),
                            "data": {"minutes_ago": minutes_ago},
                        },
                    )
                )

        surface_state = (frame.launcher_context and frame.launcher_context.surface_state) or {}
        if surface_state.get("terminal_session_active") and surface_state.get("updated_at"):
            try:
                reported_at = datetime.fromisoformat(surface_state["updated_at"])
            except ValueError:
                reported_at = None
            if reported_at and now - reported_at <= staleness:
                candidates.append(
                    (
                        reported_at,
                        {
                            "mode": "cross_surface_continuity",
                            "content": "Terminal session still open — resume on the Deck?",
                            "priority": 5.5,
                            "resume_type": "terminal",
                            "resume_target": None,
                        },
                    )
                )

        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT name, updated_at FROM routines WHERE updated_at IS NOT NULL "
                "ORDER BY updated_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                name, updated_at = row
                edited_at = updated_at.replace(tzinfo=timezone.utc)
                if now - edited_at <= staleness:
                    candidates.append(
                        (
                            edited_at,
                            {
                                "mode": "cross_surface_continuity",
                                "content": f'"{name}" routine edited recently — reopen it?',
                                "priority": 5.5,
                                "resume_type": "routine",
                                "resume_target": name,
                            },
                        )
                    )
        except pymysql.Error as e:
            logger.error("Cross-surface continuity routine check error: " + str(e))
        finally:
            if db:
                db.close()

        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1]

    def _read_fresh_attention_telemetry(self):
        """Return the most recent attention-telemetry snapshot (see
        POST /api/context/attention-telemetry, routes/context.py) as a dict,
        or None if there isn't one yet or it's older than
        ATTENTION_TELEMETRY_STALENESS_MINUTES -- shared staleness gate for
        both check_attention_focus() and check_wind_down_signal()."""
        snapshot = self._read_config_json(ATTENTION_TELEMETRY_CONFIG_KEY)
        reported_at = snapshot.get("reported_at")
        if not reported_at:
            return None
        try:
            reported_dt = datetime.fromisoformat(reported_at)
        except ValueError:
            return None
        age = datetime.now(timezone.utc) - reported_dt
        if age > timedelta(minutes=ATTENTION_TELEMETRY_STALENESS_MINUTES):
            return None
        return snapshot

    def _read_fresh_device_contexts(self):
        """Every Deck-reported device context that's still fresh, as
        {device_id: facets}. Stale entries are dropped rather than returned --
        see DEVICE_CONTEXT_STALENESS_MINUTES.

        Returns {} when nothing has ever been reported, which is deliberately
        indistinguishable from "every reporting device is stale": both mean the
        household has no current device evidence, and no rule should branch
        differently between those two cases.
        """
        stored = self._read_config_json(DEVICE_CONTEXT_CONFIG_KEY)
        devices = stored.get("devices")
        if not isinstance(devices, dict):
            return {}
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=DEVICE_CONTEXT_STALENESS_MINUTES)
        fresh = {}
        for device_id, entry in devices.items():
            if not isinstance(entry, dict):
                continue
            observed_at = entry.get("observed_at")
            if not observed_at:
                continue
            try:
                observed_dt = datetime.fromisoformat(observed_at)
            except ValueError:
                continue
            if observed_dt < cutoff:
                continue
            facets = entry.get("facets")
            if isinstance(facets, dict) and facets:
                fresh[device_id] = facets
        return fresh

    @staticmethod
    def _any_device_in_dnd(device_contexts):
        """The household roll-up for the DND facet: True if any fresh device
        reports Do Not Disturb on, False if at least one reports it off, None
        if no fresh device reported the facet at all.

        **The reduce is "any", stated explicitly** because multi-device
        disagreement is real and last-writer-wins would hide it: with a wall
        tablet and a phone, the question a consumer actually asks is "has the
        user silenced interruptions anywhere," not "what did the most recent
        device to check in happen to say." Tri-state rather than a bare bool so
        "nobody told us" stays distinguishable from "somebody told us it's off"
        -- a rule that wants to *soften* its advice on DND must not soften it
        just because no Deck is reporting.
        """
        seen = False
        for facets in device_contexts.values():
            dnd = (facets.get("interruption") or {}).get("dnd_active")
            if dnd is None:
                continue
            seen = True
            if dnd:
                return True
        return False if seen else None

    @staticmethod
    def _media_dwell_fraction(dwell_by_category_ms):
        """Fraction of total reported dwell time spent in the "media"
        category -- shared by check_attention_focus() (wants this low) and
        check_wind_down_signal() (wants this high). 0.0 if there's no dwell
        data at all (rather than dividing by zero)."""
        if not dwell_by_category_ms:
            return 0.0
        total = sum(dwell_by_category_ms.values())
        if total <= 0:
            return 0.0
        return dwell_by_category_ms.get("media", 0) / total

    def _attention_telemetry_trend(self):
        """Household's own rolling switch_count/unlock_count median from
        attention_telemetry_history (SA-2), over the last
        ATTENTION_TREND_LOOKBACK_DAYS. Returns None below
        ATTENTION_TREND_MIN_SAMPLES (not enough history for a meaningful
        "typical" yet) or on a DB error -- callers fall back to the fixed
        thresholds in that case, same "degrade to silence" precedent as
        compute_entity_baselines()/check_rhythm_break_anomaly()."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT switch_count, unlock_count FROM attention_telemetry_history "
                "WHERE reported_at >= %s",
                (datetime.now(timezone.utc) - timedelta(days=ATTENTION_TREND_LOOKBACK_DAYS),),
            )
            rows = cursor.fetchall()
            if len(rows) < ATTENTION_TREND_MIN_SAMPLES:
                return None
            return {
                "sample_count": len(rows),
                "median_switch_count": statistics.median(row[0] for row in rows),
                "median_unlock_count": statistics.median(row[1] for row in rows),
            }
        except pymysql.Error as e:
            logger.error(f"Attention telemetry trend query error: {e}")
            return None
        finally:
            if db:
                db.close()

    def check_attention_focus(self, frame):
        """A measured, evidence-based focus signal from the launcher's own window-switching
        behavior -- additive alongside (not a replacement for) check_focus_needed()'s calendar
        heuristic; see todo/sa/todo_attention_telemetry.md for why the two coexist.

        Since the LF-4 cutover this shows the scalar learner's inference (sa/learners/scalar.py)
        instead of a fixed 15-switch threshold or a rolling median plus grace: the shadow pass
        scores the reported switch count against this household's own count for the hour
        (modelled as log(1 + n)) and stores a deviation in sa_inferences, so the card lags it by at
        most one cycle. Only a HIGH deviation counts (a quiet hour is not "deep in it") and it
        needs confidence >= MIN_CARD_CONFIDENCE. As before, switching concentrated in media is the
        wind-down pattern instead (see check_wind_down_signal()), so it does not fire.

        `frame.launcher_context.attention_snapshot` (SA-4) supplies the displayed count and the
        media-dwell guard; check_wind_down_signal() reads the same snapshot.
        """
        launcher = frame.launcher_context
        snapshot = launcher and launcher.attention_snapshot
        if not snapshot or frame.now is None:
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
            logger.error("Attention focus check error: " + str(e))
            return None
        finally:
            if db:
                db.close()
        found = [
            i
            for i in recent
            if i.learner == scalar.NAME
            and (i.evidence or {}).get("series") == "attention:switch_count"
            and i.observed.get("direction") == "high"
            and i.confidence >= presence_learner.MIN_CARD_CONFIDENCE
        ]
        if not found:
            return None
        inference = max(found, key=lambda i: i.surprise)
        media_fraction = self._media_dwell_fraction(snapshot.get("dwell_by_category_ms") or {})
        if media_fraction >= ATTENTION_FOCUS_MAX_MEDIA_DWELL_FRACTION:
            return None
        switch_count = snapshot.get("switch_count", 0)
        usual = round(math.expm1(inference.expected["mu"]))  # modelled as log(1 + n)
        return {
            "mode": "attention_focus",
            "content": f"Deep in it — {switch_count} window switches recently",
            "priority": 3.6,
            "switch_count": switch_count,
            "data": {
                "typical_switch_count": usual,
                "surprise_bits": inference.surprise,
                "confidence": inference.confidence,
                "because": [
                    f"{switch_count} switches against about {usual} usual at this hour",
                    f"media dwell {media_fraction:.0%} < "
                    f"{ATTENTION_FOCUS_MAX_MEDIA_DWELL_FRACTION:.0%}",
                ],
            },
        }

    def check_wind_down_signal(self, frame):
        """The milestone's own "inverse case": late-hour high unlock rate +
        media-heavy dwell suggests winding down. Suggestion card only --
        does not auto-actuate lights/Spotify itself, matching every other
        card in this file (informational, never autonomous device control).

        Fires above this household's own rolling median unlock_count plus a
        grace margin once enough history exists
        (`frame.launcher_context.attention_trend`), falling back to the fixed
        WIND_DOWN_MIN_UNLOCKS threshold below that sample floor -- same
        trend-vs-fallback shape as check_attention_focus().

        `frame.day_mood`/`frame.launcher_context.attention_snapshot`/`.attention_trend`
        (SA-4) replace this rule's own get_env_local_time()/get_day_mood()/
        _read_fresh_attention_telemetry()/_attention_telemetry_trend() calls.
        """
        launcher = frame.launcher_context
        snapshot = launcher and launcher.attention_snapshot
        if not snapshot:
            return None
        if frame.day_mood is None or frame.day_mood["time_of_day"] != "night":
            return None
        unlock_count = snapshot.get("unlock_count", 0)
        trend = launcher and launcher.attention_trend
        threshold = WIND_DOWN_MIN_UNLOCKS
        if trend:
            threshold = max(threshold, trend["median_unlock_count"] + WIND_DOWN_TREND_GRACE_UNLOCKS)
        if unlock_count < threshold:
            return None
        media_fraction = self._media_dwell_fraction(snapshot.get("dwell_by_category_ms") or {})
        if media_fraction < WIND_DOWN_MIN_MEDIA_DWELL_FRACTION:
            return None
        return {
            "mode": "wind_down_signal",
            "content": f"Lots of screen time tonight ({unlock_count} unlocks) — wind down?",
            "priority": 5.8,
            "unlock_count": unlock_count,
            "data": {
                "because": [
                    f"{unlock_count} unlocks >= threshold {threshold}",
                    f"media dwell {media_fraction:.0%} >= {WIND_DOWN_MIN_MEDIA_DWELL_FRACTION:.0%}",
                    "night",
                ]
            },
        }

    def check_party_advisory(self, frame):
        """Catch a real, high-energy gathering happening despite the capped
        weeknight recommendation -- e.g. someone manually queues something
        rowdy on a Tuesday -- and nudge toward winding down.

        `common.spotify_utils.recommend()` only ever *suggests* capped
        energy on non-party nights (see its `is_party_night` param); nothing
        stops residents/guests from playing something high-energy anyway.
        This checks what's actually playing via Spotify's own 0.0-1.0
        'energy' audio feature for the current track, independent of
        ALFR3D's own estimate. Only evaluated outside the household's
        declared Friday/Saturday party-night window and once it's genuinely
        late (time_of_day == "night"), not just any weeknight evening.

        The returned card refreshes every cycle like any other display, but
        the spoken nudge over the `speak` topic is cooldown-gated
        (PARTY_ADVISORY_COOLDOWN_MINUTES) so it doesn't repeat the same
        "school night" line every polling cycle.

        `frame.local_dt`/`frame.day_mood`/`frame.playback` (SA-4) replace this rule's own
        get_env_local_time()/get_day_mood()/get_playback_state() calls --
        check_gatherings()/check_wind_down_signal()/check_mood() share the first two,
        check_now_playing() shares the third. get_track_energy() below stays its own call --
        a different Spotify endpoint (audio features, not playback state) that depends on
        the track id this same fetch already resolved, so there's nothing to share it with.
        """
        global PARTY_ADVISORY_LAST_NUDGE_TIME
        try:
            if frame.local_dt is None or frame.day_mood is None:
                return None
            local_dt = frame.local_dt
            if spotify_utils.is_party_night(local_dt):
                return None

            day_mood = frame.day_mood
            if day_mood["time_of_day"] != "night":
                return None

            from common import spotify_utils as spotify_api

            state = frame.playback or {}
            item = state.get("item") or {}
            track_id = item.get("id")
            if not state.get("is_playing") or not track_id:
                return None

            energy = spotify_api.get_track_energy(track_id)
            if energy is None or energy < PARTY_ADVISORY_ENERGY_THRESHOLD:
                return None

            track_name = item.get("name") or "the music"
            content = (
                f'"{track_name}" is still high-energy for a {day_mood["day_of_week"]} '
                "night -- work tomorrow, might be worth winding down."
            )

            if time.time() - PARTY_ADVISORY_LAST_NUDGE_TIME > PARTY_ADVISORY_COOLDOWN_MINUTES * 60:
                p = get_producer()
                if p:
                    p.send(
                        "speak",
                        (
                            f'Hey, it\'s a {day_mood["day_of_week"]} night and the music is '
                            "still pretty high energy. Just a heads up, it's a work night."
                        ).encode("utf-8"),
                    )
                PARTY_ADVISORY_LAST_NUDGE_TIME = time.time()

            return {
                "mode": "party_advisory",
                "content": content,
                "priority": 3.2,
                "data": {
                    "track_name": track_name,
                    "energy": energy,
                    "day_of_week": day_mood["day_of_week"],
                    "because": [
                        f"track energy {energy:.2f} >= {PARTY_ADVISORY_ENERGY_THRESHOLD}",
                        f"{day_mood['day_of_week']} night",
                    ],
                },
            }
        except Exception as e:
            logger.error("Party advisory check error: " + str(e))
            return None

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

        if climate["temperature_online"] and climate["temperature_c"] is not None:
            temp = climate["temperature_c"]
            if temp < CLIMATE_ADVISORY_COLD_THRESHOLD_C:
                return {
                    "mode": "climate_advisory",
                    "content": f"It's cooler than usual indoors ({temp}°C)",
                    "priority": 5.3,
                    "data": {
                        "temperature_c": temp,
                        "because": [f"{temp}°C < {CLIMATE_ADVISORY_COLD_THRESHOLD_C}°C"],
                    },
                }
            if temp > CLIMATE_ADVISORY_HOT_THRESHOLD_C:
                return {
                    "mode": "climate_advisory",
                    "content": f"It's warmer than usual indoors ({temp}°C)",
                    "priority": 5.3,
                    "data": {
                        "temperature_c": temp,
                        "because": [f"{temp}°C > {CLIMATE_ADVISORY_HOT_THRESHOLD_C}°C"],
                    },
                }

        if climate["humidity_online"] and climate["humidity_pct"] is not None:
            humidity = climate["humidity_pct"]
            if humidity > CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT:
                return {
                    "mode": "climate_advisory",
                    "content": f"Humidity is higher than usual indoors ({humidity}%)",
                    "priority": 5.3,
                    "data": {
                        "humidity_pct": humidity,
                        "because": [f"{humidity}% > {CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT}%"],
                    },
                }
            if humidity < CLIMATE_ADVISORY_HUMIDITY_LOW_PCT:
                return {
                    "mode": "climate_advisory",
                    "content": f"Humidity is lower than usual indoors ({humidity}%)",
                    "priority": 5.3,
                    "data": {
                        "humidity_pct": humidity,
                        "because": [f"{humidity}% < {CLIMATE_ADVISORY_HUMIDITY_LOW_PCT}%"],
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
                else "humidity"
                if series.endswith(":Humidity")
                else None
            )
            if kind and inference.confidence >= presence_learner.MIN_CARD_CONFIDENCE:
                found.append((kind, inference))
        if not found:
            return None
        # Most surprising first; temperature wins a tie, as it did when this compared bands.
        kind, inference = max(found, key=lambda f: (f[1].surprise, f[0] == "temperature"))
        value = inference.observed["value"]
        high = inference.observed["direction"] == "high"
        mu = inference.expected["mu"]
        if kind == "temperature":
            direction = "Warmer" if high else "Cooler"
            content = f"{direction} than typical for this time of day ({value}°C)"
            data = {"temperature_c": value}
            because = f"{value}°C against about {mu:.1f}°C expected at this hour"
        else:
            content = (
                f"{'Higher' if high else 'Lower'} humidity than typical for this time of day "
                f"({value}%)"
            )
            data = {"humidity_pct": value}
            because = f"{value}% against about {mu:.0f}% expected at this hour"
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

    def publish_sa(self, data):
        """Publish array of SA cards to Kafka topic."""
        p = get_producer()
        if p:
            p.send("situational-awareness", orjson.dumps(data))
            logger.info("Published situational awareness: " + str(data))


def _departure_hours_by_bucket(timestamps):
    """Reduce one resident's raw device_history timestamps (union of every claimed device,
    already sorted ascending) into {"weekday": [hour, ...], "weekend": [hour, ...]} -- one entry
    per day this resident's first real departure could be confirmed.

    `device_history.state` is not used here (SA-3's Phase 0 spike found it unreliable for this --
    see todo/sa/todo_departure_anomaly.md: the `before_device_update` trigger logs each row's state
    from *before* that write, so a per-cycle "still online" ping and the offline-flip event both
    log the same value, and only a reconnect-after-absence row logs the other one). The real
    signal is in the *gaps* between consecutive writes: `device.update()` fires on every arp-scan
    sighting (~60-90s while a device is actually seen), so a gap of DEPARTURE_GAP_MINUTES+ can
    only mean the device (and everything that shares this list) went undetected for that long.

    A day only counts if this resident was confirmed home overnight (some row before 05:00) --
    without that anchor, a day's first-seen row could just be a late-morning reappearance of an
    absence that started the night before, which would misattribute a multi-day trip's single
    real departure to every day it spans.
    """
    buckets = {"weekday": [], "weekend": []}
    if len(timestamps) < 2:
        return buckets

    days_seen = set()
    for ts in timestamps:
        day = ts.date()
        if day in days_seen:
            continue
        days_seen.add(day)

        day_start_idx = bisect.bisect_left(timestamps, datetime.combine(day, dtime.min))
        if timestamps[day_start_idx].time() >= dtime(5, 0):
            continue  # no overnight confirmation -- likely spillover from a prior absence

        anchor_idx = bisect.bisect_left(timestamps, datetime.combine(day, dtime(4, 0)))
        if anchor_idx >= len(timestamps) or timestamps[anchor_idx].date() != day:
            continue

        departure = None
        for i in range(anchor_idx, len(timestamps) - 1):
            gap_minutes = (timestamps[i + 1] - timestamps[i]).total_seconds() / 60
            if gap_minutes >= DEPARTURE_GAP_MINUTES:
                departure = timestamps[i]
                break
        if departure is None:
            continue

        bucket = "weekend" if departure.weekday() >= 5 else "weekday"
        buckets[bucket].append(departure.hour)

    return buckets


def _device_sessions(rows):
    """Reconstruct complete online sessions from a device's ordered (timestamp, state) history
    rows, as a list of (start, end) datetimes. A session ends at the next 'offline' row, or --
    when the history goes silent for more than ENTITY_BASELINE_MAX_HISTORY_GAP_MINUTES while the
    device is 'online' -- at the last row seen online. Sessions still open at the end of the rows
    and zero-length sessions are dropped."""
    max_gap = timedelta(minutes=ENTITY_BASELINE_MAX_HISTORY_GAP_MINUTES)
    sessions = []
    start = last_online = prev_ts = None
    for ts, state in rows:
        if start is not None and prev_ts is not None and ts - prev_ts > max_gap:
            if last_online > start:
                sessions.append((start, last_online))
            start = None
        if state == "online":
            if start is None:
                start = ts
            last_online = ts
        elif state == "offline" and start is not None:
            if ts > start:
                sessions.append((start, ts))
            start = None
        prev_ts = ts
    return sessions


def _active_hours_mask(sessions):
    """24-bit mask (bit h = UTC hour h) of the hours a device is usually online: hours covered by
    a session on at least ENTITY_BASELINE_ACTIVE_HOUR_MIN_SHARE of the days it had any session.
    Unlike a session's start hour, this describes the whole window the device is normally on."""
    days_seen = set()
    days_by_hour = {}
    for start, end in sessions:
        cursor_ts = start.replace(minute=0, second=0, microsecond=0)
        while cursor_ts <= end:
            days_seen.add(cursor_ts.date())
            days_by_hour.setdefault(cursor_ts.hour, set()).add(cursor_ts.date())
            cursor_ts += timedelta(hours=1)
    mask = 0
    for hour, days in days_by_hour.items():
        if len(days) / len(days_seen) >= ENTITY_BASELINE_ACTIVE_HOUR_MIN_SHARE:
            mask |= 1 << hour
    return mask


def compute_entity_baselines():
    """Recompute per-entity rhythm/routine baselines into `entity_baselines`.

    Three independent baseline types share this table and this 6-hourly compute cadence, all
    derived from `device_history`, none needing a new table (SA-10 generalised the mechanism
    rather than letting each new subject bolt on its own):
    - `device` rows (original, see todo/sa/todo_rhythm_break_anomaly.md): on/off session
      baselines used by MyDaemon.check_rhythm_break_anomaly(). `smarthome_devices` has no
      equivalent state-history table yet -- `device_command_history` logs issued commands, not
      observed state over time -- so smarthome-device baselines aren't computed;
      `entity_baselines.entity_type` keeps room for that once such a history exists (as does
      `'room'`, gated on SA-9 sensor coverage -- stopped at Phase 0 this session, no real
      ESPHome node to validate against, see todo/sa/todo_esphome_situational_awareness.md).
    - `user` rows (SA-3, see todo/sa/todo_departure_anomaly.md): per-resident weekday/weekend
      departure-hour baselines used by MyDaemon.check_departure_anomaly(). Guests excluded.
    - `household` rows (SA-10, see todo/sa/todo_generalize_entity_baselines.md): weekday/weekend
      typical first/last-activity hour and device-count range for the household as a whole,
      used by MyDaemon.check_household_unusual_day(). A singleton -- one row per day_bucket,
      `entity_id` is a fixed sentinel (HOUSEHOLD_BASELINE_ENTITY_ID), not a real foreign key.
      Computed as a single SQL aggregate, not a per-entity Python loop -- see the "household
      baselines" block below for why that distinction mattered in practice, not just in theory.
    """
    logger.info("Computing entity rhythm baselines")
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute(
            "SELECT DISTINCT device_id FROM device_history WHERE timestamp >= %s",
            (datetime.now(timezone.utc) - timedelta(days=ENTITY_BASELINE_LOOKBACK_DAYS),),
        )
        device_ids = [row[0] for row in cursor.fetchall()]

        for device_id in device_ids:
            cursor.execute(
                """
                SELECT dh.timestamp, s.state
                FROM device_history dh
                JOIN states s ON dh.state = s.id
                WHERE dh.device_id = %s
                  AND dh.timestamp >= %s
                  AND s.state IN ('online', 'offline')
                ORDER BY dh.timestamp ASC
                """,
                (
                    device_id,
                    datetime.now(timezone.utc) - timedelta(days=ENTITY_BASELINE_LOOKBACK_DAYS),
                ),
            )
            rows = cursor.fetchall()

            sessions = _device_sessions(rows)
            durations_minutes = [(end - start).total_seconds() / 60 for start, end in sessions]
            start_hours = [start.hour for start, _ in sessions]

            if len(durations_minutes) < ENTITY_BASELINE_MIN_SAMPLES:
                continue

            cursor.execute(
                """
                INSERT INTO entity_baselines
                    (entity_type, entity_id, median_on_minutes, typical_active_hour,
                     active_hours_mask, typical_daily_min, typical_daily_max, sample_count,
                     min_sample_count, computed_at)
                VALUES ('device', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    median_on_minutes = VALUES(median_on_minutes),
                    typical_active_hour = VALUES(typical_active_hour),
                    active_hours_mask = VALUES(active_hours_mask),
                    typical_daily_min = VALUES(typical_daily_min),
                    typical_daily_max = VALUES(typical_daily_max),
                    sample_count = VALUES(sample_count),
                    min_sample_count = VALUES(min_sample_count),
                    computed_at = VALUES(computed_at)
                """,
                (
                    device_id,
                    statistics.median(durations_minutes),
                    statistics.mode(start_hours),
                    _active_hours_mask(sessions),
                    min(durations_minutes),
                    max(durations_minutes),
                    len(durations_minutes),
                    ENTITY_BASELINE_MIN_SAMPLES,
                    datetime.now(timezone.utc),
                ),
            )

        # SA-3: per-resident departure-hour baselines, entity_type='user'. Same table, same
        # compute cadence -- see _departure_hours_by_bucket()'s own doc comment for why this
        # doesn't reuse the online/offline state-column reconstruction above. Guests excluded via
        # the same ut.type convention services.common.db_utils's "worthy listeners" check already
        # uses (owner/technoking/resident only).
        tz_offset = timedelta(seconds=db_utils.get_env_timezone(ENV_NAME))
        departure_lookback_start = datetime.now(timezone.utc) - timedelta(
            days=DEPARTURE_BASELINE_LOOKBACK_DAYS
        )
        cursor.execute("""
            SELECT DISTINCT u.id, u.username
            FROM user u
            JOIN user_types ut ON u.type = ut.id
            JOIN device d ON d.user_id = u.id
            WHERE ut.type IN ('owner', 'technoking', 'resident')
            """)
        eligible_users = cursor.fetchall()

        for user_id, username in eligible_users:
            cursor.execute("SELECT id FROM device WHERE user_id = %s", (user_id,))
            device_ids = [row[0] for row in cursor.fetchall()]
            if not device_ids:
                continue

            placeholders = ",".join(["%s"] * len(device_ids))
            cursor.execute(
                f"""
                SELECT timestamp FROM device_history
                WHERE device_id IN ({placeholders}) AND timestamp >= %s
                ORDER BY timestamp ASC
                """,
                (*device_ids, departure_lookback_start),
            )
            local_timestamps = sorted(row[0] + tz_offset for row in cursor.fetchall())
            buckets = _departure_hours_by_bucket(local_timestamps)

            for day_bucket, hours in buckets.items():
                if len(hours) < DEPARTURE_BASELINE_MIN_SAMPLES:
                    continue
                cursor.execute(
                    """
                    INSERT INTO entity_baselines
                        (entity_type, entity_id, day_bucket, typical_active_hour,
                         typical_daily_min, typical_daily_max, sample_count, min_sample_count,
                         computed_at)
                    VALUES ('user', %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        typical_active_hour = VALUES(typical_active_hour),
                        typical_daily_min = VALUES(typical_daily_min),
                        typical_daily_max = VALUES(typical_daily_max),
                        sample_count = VALUES(sample_count),
                        min_sample_count = VALUES(min_sample_count),
                        computed_at = VALUES(computed_at)
                    """,
                    (
                        user_id,
                        day_bucket,
                        statistics.mode(hours),
                        min(hours),
                        max(hours),
                        len(hours),
                        DEPARTURE_BASELINE_MIN_SAMPLES,
                        datetime.now(timezone.utc),
                    ),
                )
            logger.info(f"Departure baseline for {username}: {buckets}")

        # SA-10: household-level baselines, entity_type='household'. Unlike the device/user
        # loops above, this is a single SQL aggregate (GROUP BY local calendar day), not a
        # per-entity Python session-reconstruction loop -- deliberately, since Phase 0 measured
        # the existing device loop alone taking ~175s on the production NUC (see
        # todo/sa/todo_generalize_entity_baselines.md); adding another loop of that shape for a new
        # subject type would multiply that cost, an aggregate query doesn't.
        household_lookback_start = datetime.now(timezone.utc) - timedelta(
            days=HOUSEHOLD_BASELINE_LOOKBACK_DAYS
        )
        # A derived table computing local_date once, grouped by that bare column, rather than
        # GROUP BY on an inline expression with the raw `timestamp` column also referenced in
        # the SELECT list -- MySQL's ONLY_FULL_GROUP_BY mode (the production default) rejects
        # the latter even though DAYOFWEEK(local_date) is functionally dependent on it; caught
        # live against the real database, not something the mocked unit tests could catch.
        cursor.execute(
            """
            SELECT
                DAYOFWEEK(local_date) AS local_dow,
                HOUR(first_ts) AS first_hour,
                HOUR(last_ts) AS last_hour,
                device_count
            FROM (
                SELECT
                    DATE(timestamp + INTERVAL %s SECOND) AS local_date,
                    MIN(timestamp + INTERVAL %s SECOND) AS first_ts,
                    MAX(timestamp + INTERVAL %s SECOND) AS last_ts,
                    COUNT(DISTINCT device_id) AS device_count
                FROM device_history
                WHERE timestamp >= %s
                GROUP BY local_date
            ) AS daily
            """,
            (
                tz_offset.total_seconds(),
                tz_offset.total_seconds(),
                tz_offset.total_seconds(),
                household_lookback_start,
            ),
        )
        household_buckets = {"weekday": [], "weekend": []}
        for local_dow, first_hour, last_hour, device_count in cursor.fetchall():
            # MySQL DAYOFWEEK: 1=Sunday ... 7=Saturday.
            bucket = "weekend" if local_dow in (1, 7) else "weekday"
            household_buckets[bucket].append((first_hour, last_hour, device_count))

        for day_bucket, samples in household_buckets.items():
            if len(samples) < HOUSEHOLD_BASELINE_MIN_SAMPLES:
                continue
            first_hours = [s[0] for s in samples]
            last_hours = [s[1] for s in samples]
            device_counts = [s[2] for s in samples]
            cursor.execute(
                """
                INSERT INTO entity_baselines
                    (entity_type, entity_id, day_bucket, typical_active_hour,
                     typical_last_activity_hour, typical_daily_min, typical_daily_max,
                     sample_count, min_sample_count, computed_at)
                VALUES ('household', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    typical_active_hour = VALUES(typical_active_hour),
                    typical_last_activity_hour = VALUES(typical_last_activity_hour),
                    typical_daily_min = VALUES(typical_daily_min),
                    typical_daily_max = VALUES(typical_daily_max),
                    sample_count = VALUES(sample_count),
                    min_sample_count = VALUES(min_sample_count),
                    computed_at = VALUES(computed_at)
                """,
                (
                    HOUSEHOLD_BASELINE_ENTITY_ID,
                    day_bucket,
                    statistics.mode(first_hours),
                    statistics.mode(last_hours),
                    min(device_counts),
                    max(device_counts),
                    len(samples),
                    HOUSEHOLD_BASELINE_MIN_SAMPLES,
                    datetime.now(timezone.utc),
                ),
            )
        sample_counts = {bucket: len(samples) for bucket, samples in household_buckets.items()}
        logger.info(f"Household baseline sample counts: {sample_counts}")

        # SA-9 Phase 2: per-ESPHome-sensor-entity, per-time-of-day-bucket climate baselines,
        # entity_type='room' (reserved since SA-10/migration 033 for exactly this -- see
        # migration 041's own comment on why entity_id keys on the sensor's own
        # smarthome_devices.id rather than an actual room, which isn't populated anywhere yet).
        # Bucketed by time-of-day (common.timeofday.coarse_bucket()), not day_bucket
        # (weekday/weekend) -- indoor temperature varies by hour far more than by day of week.
        climate_lookback_start = datetime.now(timezone.utc) - timedelta(
            days=CLIMATE_BASELINE_LOOKBACK_DAYS
        )
        cursor.execute(
            "SELECT smarthome_device_id, value, recorded_at FROM smarthome_sensor_history "
            "WHERE recorded_at >= %s",
            (climate_lookback_start,),
        )
        climate_readings = defaultdict(list)
        for device_id, value, recorded_at in cursor.fetchall():
            local_hour = (recorded_at + tz_offset).hour
            climate_readings[(device_id, timeofday.coarse_bucket(local_hour))].append(value)

        for (device_id, bucket), values in climate_readings.items():
            if len(values) < CLIMATE_BASELINE_MIN_SAMPLES:
                continue
            # 2026-09-26 fix: typical_daily_min/max used to be raw min(values)/max(values) --
            # a "typical" band built from the literal observed range self-widens to cover
            # nearly every future reading too, so check_climate_deviation() could never fire
            # (confirmed against real production data: zero firings in 10 days). A
            # median +/- N-stdev band reflects what's actually typical instead.
            median_value = statistics.median(values)
            # len(values) >= CLIMATE_BASELINE_MIN_SAMPLES (10) >= 2, so stdev() is always safe.
            stdev_value = statistics.stdev(values)
            typical_min = median_value - CLIMATE_BASELINE_STDEV_MULTIPLIER * stdev_value
            typical_max = median_value + CLIMATE_BASELINE_STDEV_MULTIPLIER * stdev_value
            cursor.execute(
                """
                INSERT INTO entity_baselines
                    (entity_type, entity_id, day_bucket, time_of_day_bucket,
                     typical_median_value, typical_daily_min, typical_daily_max,
                     sample_count, min_sample_count, computed_at)
                VALUES ('room', %s, 'all', %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    typical_median_value = VALUES(typical_median_value),
                    typical_daily_min = VALUES(typical_daily_min),
                    typical_daily_max = VALUES(typical_daily_max),
                    sample_count = VALUES(sample_count),
                    min_sample_count = VALUES(min_sample_count),
                    computed_at = VALUES(computed_at)
                """,
                (
                    device_id,
                    bucket,
                    median_value,
                    typical_min,
                    typical_max,
                    len(values),
                    CLIMATE_BASELINE_MIN_SAMPLES,
                    datetime.now(timezone.utc),
                ),
            )
        climate_sample_counts = {k: len(v) for k, v in climate_readings.items()}
        logger.info(f"Climate baseline sample counts: {climate_sample_counts}")

        db.commit()
    except pymysql.Error as e:
        logger.error(f"Entity baseline computation error: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()
