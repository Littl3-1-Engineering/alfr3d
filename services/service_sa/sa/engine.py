"""Situational-awareness engine: context frame, display rules, card suppression, publishing,
and publishing. (The entity-baseline computation that used to live here is gone; see
migration 0062.)

LF-1a (todo/sa/todo_lf1a_sa_service_split.md): moved verbatim out of
service_daemon/alfr3ddaemon.py -- the SA constants, the SA methods of MyDaemon (now SAEngine)
and compute_entity_baselines() -- so the daemon stays a fast loop engine and SA has one owner.
No behaviour change: same rules, same priorities, same queries, same Kafka topic.
`awareness.py` runs SAEngine.check_situational_awareness() every 60s; `learner.py` runs the
nightly lake and learner jobs.
"""

# Standard library imports
import logging
import math
import time  # noqa: F401  (re-exported: tests patch engine.time)
import os
import sys
from datetime import datetime, timedelta, timezone
import orjson

# Third party imports
import pymysql
from sa import context_frame, inference_store, mood_utils, shadow
from sa import routing_utils  # noqa: F401  (re-exported: tests patch engine.routing_utils)
from sa import disk, layer2  # noqa: F401  (disk re-exported: tests patch engine.disk)
from sa.card_utils import (  # noqa: F401  (re-exported: tests patch these on `engine`)
    CARD_SUBJECT_KEY_EXTRACTORS,
    _cross_surface_continuity_subject_key,
    _span_text,
)
from sa.suppression import (  # noqa: F401  (re-exported)
    CARD_FEEDBACK_ACTIONS,
    CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE,
    CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES,
    CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES,
    CARD_SUPPRESSION_HISTORY_LIMIT,
    CARD_SUPPRESSION_NOT_USEFUL_COOLDOWN_MINUTES,
    CARD_SUPPRESSION_NOT_USEFUL_COOLDOWN_MINUTES_BY_RULE,
    CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE,
    SuppressionMixin,
)
from sa.calendar_cards import (  # noqa: F401  (re-exported)
    CalendarCards,
    FOCUS_LEAD_MINUTES,
    GUEST_CARD_PRIORITY_MAX_DEMOTION,
    PARTY_ADVISORY_COOLDOWN_MINUTES,
    PARTY_ADVISORY_ENERGY_THRESHOLD,
    TRAVEL_STALE_AFTER_MINUTES,
)
from sa.environment_cards import (  # noqa: F401  (re-exported)
    EnvironmentCards,
    CLIMATE_ADVISORY_COLD_THRESHOLD_C,
    CLIMATE_ADVISORY_HOT_THRESHOLD_C,
    CLIMATE_ADVISORY_HUMIDITY_HIGH_PCT,
    CLIMATE_ADVISORY_HUMIDITY_LOW_PCT,
    FORECAST_HOURS_AHEAD,
    RAIN_ADVISORY_THRESHOLD,
)
from sa.media_cards import (  # noqa: F401  (re-exported)
    CROSS_SURFACE_STALENESS_MINUTES,
    NOW_PLAYING_CONFIG_KEY,
    MediaCards,
)
from sa.health_cards import (  # noqa: F401  (re-exported)
    HealthCards,
    DISK_HEALTH_CHECK_INTERVAL_SECONDS,
    DISK_HEALTH_SPEAK_COOLDOWN_SECONDS,
    DISK_HEALTH_STATE,
    SYSTEM_HEALTH_FAILURES_BEFORE_ALERT,
    SYSTEM_HEALTH_INTEGRATIONS,
    SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS,
    SYSTEM_HEALTH_STATE,
)
from sa.learners import device_rhythm, household_day, stay
from sa.learners import presence as presence_learner
from sa.learners import scalar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import calendar_utils, gmail_utils, spotify_utils  # noqa: E402,F401
from common import get_producer  # noqa: E402
from common import db_utils  # noqa: E402
from common import day_context  # noqa: E402

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

# `config` table key POST /api/context/surface-state (service_api/routes/context.py)
# writes the launcher's last-reported active surface/terminal-session state
# under; read by check_cross_surface_continuity() via _read_config_json().
SURFACE_STATE_CONFIG_KEY = "launcher_surface_state"

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

# ...and only when media-category dwell is under this fraction of total
# dwell time -- high switching concentrated in media (e.g. flipping between
# a few apps while half-watching something) isn't "focus", it's the
# wind-down check's pattern instead.
ATTENTION_FOCUS_MAX_MEDIA_DWELL_FRACTION = 0.3

# check_wind_down_signal() only fires when media-category dwell is over this fraction of total
# dwell time -- the milestone's own "late-hour high unlock rate + social-app dwell" pattern. How
# many unlocks count as "high" is the scalar learner's call (this household's own count for the
# hour), not a constant here.
WIND_DOWN_MIN_MEDIA_DWELL_FRACTION = 0.5


# decide_displays()'s suppression pass (SA-1) identifies a card as (rule_id, subject_key) --
# DISPLAY_RULES' own id, not the card's own "mode" field (which collides: check_gatherings,
# rule id "music", and check_now_playing, rule id "now_playing", both stamp "mode": "music" on
# their card). Most rules are singleton -- there's only one slot to suppress regardless of what
# the content currently says (dismissing "now playing" should mean "stop telling me what's
# playing for a while", not "I've seen this exact track before"), so subject_key defaults to "".
# Only rules that can legitimately recur for different underlying entities get a real one, via
# CARD_SUBJECT_KEY_EXTRACTORS below -- dismissing one device's rhythm-break card must not
# suppress a different device's.
# Cards whose `urgent` field is true are never suppressed regardless of interaction history --
# household_composition's elevated variant (an unrecognized device on the network) is the only
# one today, but this is a generic field check so any future rule can opt in the same way.
CARD_SUPPRESSION_NEVER_OVERRIDE_FIELD = "urgent"

# device_history is written about once a minute while the scanner runs. A silence longer than this
# inside an "online" session means the offline transition was never observed (scanner/daemon
# outage), so the session is closed at the last row seen online instead of being stretched across
# the gap -- otherwise one lost transition becomes a phantom multi-day session that poisons
# typical_daily_max and the still-on-past-typical rule.
ENTITY_BASELINE_MAX_HISTORY_GAP_MINUTES = 180

# An hour of the (UTC) day is part of a device's usual window when the device was online during it
# on at least this share of the days it was seen at all. Stored as a 24-bit mask in
# the device-rhythm learner's active-hours mask (formerly entity_baselines.active_hours_mask).
ENTITY_BASELINE_ACTIVE_HOUR_MIN_SHARE = 0.15

# household_events/attention_telemetry_history/card_interactions retention, and the daily SA
# storage-metrics snapshot, all moved from Python `schedule` jobs to DB-native scheduled EVENTs
# in migration 039 (2026-09-13) -- see that migration's own comment for why. No Python constant
# for their retention window lives here any more; it's in the EVENT bodies themselves, same as
# device_location_history's own event already was.


class SAEngine(CalendarCards, MediaCards, EnvironmentCards, HealthCards, SuppressionMixin):
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
    #   device_health:         offline_minutes/usual_longest_offline_minutes/threshold_minutes,
    #                           because
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
        # Household hardware (camera, sensor) offline far longer than it ever ordinarily is: the
        # same "something's off" tier, just below the routine-break card.
        ("device_health", 2.65, "check_device_health"),
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
        """A device behaving out of its own routine. Since the LF-4 cutover this shows the device
        rhythm learner's inference (sa/learners/device_rhythm.py) instead of comparing against an
        `entity_baselines` row: the shadow pass scores every device each cycle and stores any
        deviation in sa_inferences, so the card lags it by at most one cycle. Three deviation
        types, as before:

        - `expected_absent`: offline at an hour it is almost always on (and long enough, per
          device: see the learner's offline_flicker_minutes),
        - `unusual_hour`: on at an hour it almost never is,
        - `still_on_past_typical`: this session has outlasted nearly every past one.

        One card per cycle, the most surprising deviation whose confidence clears
        MIN_CARD_CONFIDENCE (the card's identity is the device, so SA-1's cooldown quiets a device
        that is dismissed). Not a frame field: it reads the stored inferences directly.
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
            logger.error("Rhythm break anomaly check error: " + str(e))
            return None
        finally:
            if db:
                db.close()
        found = [
            i
            for i in recent
            if i.learner == device_rhythm.NAME
            and i.signal in (device_rhythm.SIGNAL_AVAILABILITY, device_rhythm.SIGNAL_DURATION)
            and (i.evidence or {}).get("device")
            and i.confidence >= presence_learner.MIN_CARD_CONFIDENCE
        ]
        if not found:
            return None
        inference = max(found, key=lambda i: i.surprise)
        name = inference.evidence["device"]
        card = {
            "mode": "rhythm_break_anomaly",
            "priority": 2.6,
            "entity_name": name,
            "data": {"surprise_bits": inference.surprise, "confidence": inference.confidence},
        }
        if inference.signal == device_rhythm.SIGNAL_DURATION:
            over_by = round(inference.observed["minutes_on"] - inference.expected["p95_minutes"])
            typical = round(inference.expected["p95_minutes"])
            card.update(
                content=f"{name} has been on for {over_by} min longer than usual",
                deviation_type="still_on_past_typical",
            )
            card["data"].update(
                over_by_minutes=over_by,
                typical_daily_max_minutes=typical,
                because=[f"on {over_by} min past the longest ordinary session ({typical} min)"],
            )
        elif inference.observed["state"] == "offline":
            usual = round(inference.expected["p_online"] * 100)
            minutes = round(inference.observed["offline_minutes"])
            hour = inference.context["hour_local"]
            card.update(content=f"{name} hasn't come online yet", deviation_type="expected_absent")
            card["data"].update(
                offline_minutes=minutes,
                p_online=inference.expected["p_online"],
                because=[
                    f"usually online {usual}% of the time at {hour:02d}:00, "
                    f"offline for {minutes} min"
                ],
            )
        else:
            usual = round(inference.expected["p_online"] * 100)
            hour = inference.context["hour_local"]
            card.update(content=f"{name} is on at an unusual hour", deviation_type="unusual_hour")
            card["data"].update(
                current_hour=hour,
                p_online=inference.expected["p_online"],
                because=[f"on at {hour:02d}:00, when it is usually on only {usual}% of the time"],
            )
        return card

    def check_device_health(self, frame):
        """Household hardware (a camera, a sensor: devices owned by the infrastructure user) that
        has been offline much longer than it ever ordinarily is. The trigger is the device's own
        history, not a device type or a person's schedule: max(floor, 1.5 x the longest offline
        stretch it ordinarily shows), so a PC that sleeps eight hours a night is not flagged by one
        (see DeviceRhythmLearner.score_health). Reads the stored inferences like
        check_rhythm_break_anomaly. Stays quiet while an integration is unreachable
        (check_system_health owns that), since every device it syncs then reads offline.

        One card per cycle, the device that has been off longest; its identity is the device, so
        SA-1's cooldown quiets one that is dismissed."""
        if frame.now is None:
            return None
        if any(
            state["failures"] >= SYSTEM_HEALTH_FAILURES_BEFORE_ALERT
            for state in SYSTEM_HEALTH_STATE.values()
        ):
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
            logger.error("Device health check error: " + str(e))
            return None
        finally:
            if db:
                db.close()
        found = [
            i
            for i in recent
            if i.learner == device_rhythm.NAME
            and i.signal == device_rhythm.SIGNAL_HEALTH
            and (i.evidence or {}).get("device")
        ]
        if not found:
            return None
        inference = max(found, key=lambda i: i.observed["offline_minutes"])
        name = inference.evidence["device"]
        minutes = round(inference.observed["offline_minutes"])
        usual = inference.expected.get("usual_longest_offline_minutes")
        span = _span_text(minutes)
        because = (
            [f"offline {span}; it is ordinarily off for at most {_span_text(round(usual))}"]
            if usual
            else [f"offline {span}, and it has no history of being off for long"]
        )
        return {
            "mode": "device_health",
            "content": f"{name} has been offline for {span}",
            "priority": 2.65,
            "entity_name": name,
            "data": {
                "offline_minutes": minutes,
                "usual_longest_offline_minutes": usual,
                "threshold_minutes": inference.expected["threshold_minutes"],
                "because": because,
            },
        }

    def check_departure_anomaly(self, frame):
        """SA-3: a resident who has been home an unusually long stretch for them. Since the LF-4
        cutover this shows the stay learner's inference (sa/learners/stay.py) instead of an
        `entity_baselines` "usually gone by now" hour: the shadow pass scores every resident's stay
        so far each cycle and stores any deviation in sa_inferences, so the card lags it by at most
        one cycle.

        What it means, deliberately: no outing longer than the person's own bridge (see
        sa/presence_bridge.py, 15-60 minutes) in a stay far longer than their comparable past
        stays. A short walk does not end a stay, so the wording says "hasn't been out" and never
        "home the whole time". Calendar suppression (a booked stretch at home) and the audience
        (owner, technoking, resident) are applied where the inference is produced.

        One card per cycle, the most surprising stay whose confidence clears MIN_CARD_CONFIDENCE.
        Tone constraint (from the task doc): an ambient observation, never a welfare check.
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
            logger.error("Departure anomaly check error: " + str(e))
            return None
        finally:
            if db:
                db.close()
        found = [
            i
            for i in recent
            if i.learner == stay.NAME
            and i.signal == stay.SIGNAL
            and (i.evidence or {}).get("username")
            and i.confidence >= presence_learner.MIN_CARD_CONFIDENCE
        ]
        if not found:
            return None
        inference = max(found, key=lambda i: i.surprise)
        username = inference.evidence["username"]
        minutes = inference.observed["stay_minutes"]
        hours = round(minutes / 60.0)
        span = f"{hours} h" if minutes < 48 * 60 else f"{round(minutes / 1440.0)} days"
        daytype = (frame.day_mood or {}).get("day_of_week") or inference.context.get("daytype")
        usual = round(inference.expected["p_stay_at_least"] * 100)
        return {
            "mode": "departure_anomaly",
            "content": f"{username} hasn't been out in {span} — unusual for a {daytype}",
            "priority": 2.7,
            "entity_name": username,
            "data": {
                "stay_minutes": round(minutes),
                "surprise_bits": inference.surprise,
                "confidence": inference.confidence,
                "p_stay_at_least": inference.expected["p_stay_at_least"],
                "because": [
                    f"{span} without a longer outing, which only {usual}% of comparable "
                    f"past stays reached",
                ],
            },
        }

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

    def _fresh_attention_deviation(self, frame, series):
        """The scalar learner's freshest HIGH deviation for an attention series (e.g.
        "attention:switch_count"), or None: nothing fresh, not high, below MIN_CARD_CONFIDENCE, or
        the read failed. Shared by check_attention_focus() and check_wind_down_signal().
        """
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
            logger.error("Attention deviation read error: " + str(e))
            return None
        finally:
            if db:
                db.close()
        found = [
            i
            for i in recent
            if i.learner == scalar.NAME
            and (i.evidence or {}).get("series") == series
            and i.observed.get("direction") == "high"
            and i.confidence >= presence_learner.MIN_CARD_CONFIDENCE
        ]
        return max(found, key=lambda i: i.surprise) if found else None

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
        inference = self._fresh_attention_deviation(frame, "attention:switch_count")
        if inference is None:
            return None
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

        Since the LF-4 cutover this shows the scalar learner's inference
        (sa/learners/scalar.py) instead of a fixed 5-unlock threshold or a rolling median plus
        grace: the shadow pass scores the reported unlock count against this household's own
        count for the hour (modelled as log(1 + n)) and stores a deviation in sa_inferences, so
        the card lags it by at most one cycle. Only a HIGH deviation counts and it needs
        confidence >= MIN_CARD_CONFIDENCE. What the learner cannot know stays here: it must be
        night, and the dwell must be media-heavy (the pattern that separates winding down from
        check_attention_focus()'s focused work).

        `frame.day_mood`/`frame.launcher_context.attention_snapshot` (SA-4) supply the night
        gate, the displayed count and the media-dwell guard.
        """
        launcher = frame.launcher_context
        snapshot = launcher and launcher.attention_snapshot
        if not snapshot or frame.now is None:
            return None
        if frame.day_mood is None or frame.day_mood["time_of_day"] != "night":
            return None
        media_fraction = self._media_dwell_fraction(snapshot.get("dwell_by_category_ms") or {})
        if media_fraction < WIND_DOWN_MIN_MEDIA_DWELL_FRACTION:
            return None
        inference = self._fresh_attention_deviation(frame, "attention:unlock_count")
        if inference is None:
            return None
        unlock_count = snapshot.get("unlock_count", 0)
        usual = round(math.expm1(inference.expected["mu"]))  # modelled as log(1 + n)
        return {
            "mode": "wind_down_signal",
            "content": f"Lots of screen time tonight ({unlock_count} unlocks) — wind down?",
            "priority": 5.8,
            "unlock_count": unlock_count,
            "data": {
                "typical_unlock_count": usual,
                "surprise_bits": inference.surprise,
                "confidence": inference.confidence,
                "because": [
                    f"{unlock_count} unlocks against about {usual} usual at this hour",
                    f"media dwell {media_fraction:.0%} >= {WIND_DOWN_MIN_MEDIA_DWELL_FRACTION:.0%}",
                    "night",
                ],
            },
        }

    def publish_sa(self, data):
        """Publish array of SA cards to Kafka topic."""
        p = get_producer()
        if p:
            p.send("situational-awareness", orjson.dumps(data))
            logger.info("Published situational awareness: " + str(data))


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
