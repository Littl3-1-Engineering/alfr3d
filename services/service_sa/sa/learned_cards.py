"""Learned and presence cards: household composition and unusual day, empty house, rhythm break,
device health, departure, presence deviation, attention focus and wind-down.

Step 4e of the engine.py split (todo/sa/todo_parallel_capture_track.md, item 4): the constants and
the seventeen methods moved verbatim out of engine.py as `LearnedCards`, which `SAEngine` inherits;
engine re-exports the constants. `_read_config_json` stays on engine (the frame builder uses it).
Everything called here is a shared module object (`pymysql`, `inference_store`, `layer2`, the
learners) patched by attribute, or an instance method patched with `patch.object(engine, ...)`, so
existing tests are unaffected. `SYSTEM_HEALTH_STATE` is the same dict object health_cards owns.
"""

import logging
import math
import os
from datetime import datetime, timedelta, timezone

import pymysql
from sa import inference_store, layer2
from sa.card_utils import _span_text
from sa.health_cards import SYSTEM_HEALTH_FAILURES_BEFORE_ALERT, SYSTEM_HEALTH_STATE
from sa.learners import device_rhythm, household_day, stay
from sa.learners import presence as presence_learner
from sa.learners import scalar

logger = logging.getLogger("SALog")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")

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


class LearnedCards:
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
