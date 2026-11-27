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
import time  # noqa: F401  (re-exported: tests patch engine.time)
import os
import sys
from datetime import datetime, timezone
import orjson

# Third party imports
import pymysql
from sa import context_frame, mood_utils, shadow
from sa import inference_store  # noqa: F401  (re-exported: tests patch engine.inference_store)
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
from sa.learned_cards import (  # noqa: F401  (re-exported)
    LearnedCards,
    ATTENTION_FOCUS_MAX_MEDIA_DWELL_FRACTION,
    ATTENTION_TELEMETRY_CONFIG_KEY,
    ATTENTION_TELEMETRY_STALENESS_MINUTES,
    DEVICE_CONTEXT_CONFIG_KEY,
    DEVICE_CONTEXT_STALENESS_MINUTES,
    WIND_DOWN_MIN_MEDIA_DWELL_FRACTION,
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
    BACKUP_HEALTH_CHECK_INTERVAL_SECONDS,
    BACKUP_HEALTH_STATE,
    DISK_HEALTH_CHECK_INTERVAL_SECONDS,
    DISK_HEALTH_SPEAK_COOLDOWN_SECONDS,
    DISK_HEALTH_STATE,
    SYSTEM_HEALTH_FAILURES_BEFORE_ALERT,
    SYSTEM_HEALTH_INTEGRATIONS,
    SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS,
    SYSTEM_HEALTH_STATE,
)

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

# household_events/attention_telemetry_history/card_interactions retention, and the daily SA
# storage-metrics snapshot, all moved from Python `schedule` jobs to DB-native scheduled EVENTs
# in migration 039 (2026-09-13) -- see that migration's own comment for why. No Python constant
# for their retention window lives here any more; it's in the EVENT bodies themselves, same as
# device_location_history's own event already was.


class SAEngine(
    LearnedCards, CalendarCards, MediaCards, EnvironmentCards, HealthCards, SuppressionMixin
):
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
        # A daily DB backup that stopped landing: ambient at 36 h, urgent at 96 h (priority is
        # set per call by check_backup_health, 2.15 critical / 5.85 warn).
        ("backup_health", 5.85, "check_backup_health"),
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

    def publish_sa(self, data):
        """Publish array of SA cards to Kafka topic."""
        p = get_producer()
        if p:
            p.send("situational-awareness", orjson.dumps(data))
            logger.info("Published situational awareness: " + str(data))
