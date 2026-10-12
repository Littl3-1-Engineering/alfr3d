"""Shadow mode (LF-4): run the learners beside the legacy rules and compare, change nothing.

The legacy `check_*` rules keep deciding what the household sees. After they have run, the
engine hands their cards to ShadowRunner.run(), which scores the same moment with the layer-1 /
layer-2 learners that replace them and logs one line whenever the pair (legacy outcome, learner
outcome) changes for a rule:

    SHADOW climate_deviation: legacy=quiet learner=esphome:...:Temperature low z=-4.6 p=4e-06

Learner findings are also written to sa_inferences (upserted, so a lasting deviation is one row).
Once a week of these lines agrees with what the household would have wanted, the rule can read
the learner's inference instead and its baseline code can go (todo/sa/todo_lf4b_baseline_ports.md).

Everything here is best-effort and isolated: an exception in any comparison is logged and
swallowed, and no result of this module reaches a card.
"""

import logging
from datetime import datetime, timedelta

from sa import inference_store
from sa import silver
from sa.learners import device_rhythm, household_day, presence, rates, scalar

logger = logging.getLogger("SALog")

HOURS_BACK = 24
COME_ONLINE_GAP_MINUTES = 45  # a device unseen this long is 'coming online' (silver's gap)


class ShadowRunner:
    def __init__(self, connect, persist):
        """connect() -> a new pymysql connection; persist(list_of_inferences) -> None."""
        self._connect = connect
        self._persist = persist
        self._profiles = {}  # learner name -> (stamp, [Profile])
        self._last = {}  # rule -> signature last logged
        self._household = {}  # local date -> learner finding (or None)
        self._rates_window = None  # UTC start of the hour whose event rates were last scored

    # --- plumbing -------------------------------------------------------------------------

    def profiles(self, learner_name):
        """Profiles for a learner, reloaded only when sa-learner has written a newer fit."""
        db = self._connect()
        try:
            stamp = inference_store.profiles_stamp(db, learner_name)
            cached = self._profiles.get(learner_name)
            if cached is None or cached[0] != stamp:
                loaded = inference_store.load_profiles(db, learner_name) if stamp else []
                self._profiles[learner_name] = (stamp, loaded)
            return self._profiles[learner_name][1]
        finally:
            db.close()

    def record(self, rule, legacy, findings):
        """Persist the learner's findings and log when (legacy, learner) differs from last time."""
        if findings:
            self._persist(findings)
        learner_desc = "; ".join(self.describe(f) for f in findings) or "quiet"
        signature = (legacy, learner_desc)
        if self._last.get(rule) != signature:
            self._last[rule] = signature
            agree = "AGREE" if (legacy == "quiet") == (not findings) else "DIFFER"
            logger.info(f"SHADOW {rule} {agree}: legacy={legacy} learner={learner_desc}")

    @staticmethod
    def describe(inference):
        e, o = inference.expected or {}, inference.observed or {}
        what = inference.evidence.get("series") or inference.evidence.get("device") or ""
        what = what or inference.evidence.get("stream") or inference.subject_id
        return (
            f"{what} {o.get('direction') or o.get('state') or ''} "
            f"p={inference.probability:.2g} conf={inference.confidence:.2f} {e}".replace("  ", " ")
        ).strip()

    @staticmethod
    def legacy_desc(card):
        if not card:
            return "quiet"
        return f"{card.get('deviation_type') or card.get('mode')}:{card.get('entity_name') or ''}"

    # --- the comparisons ---------------------------------------------------------------------

    def run(self, frame, cards):
        """cards: {rule_id: legacy card or None} for this cycle."""
        for name, fn in (
            ("climate_deviation", self.climate),
            ("attention_focus", self.attention),
            ("departure_anomaly", self.departure),
            ("rhythm_break_anomaly", self.rhythm),
            ("household_unusual_day", self.household),
        ):
            if name not in cards:
                continue
            try:
                self.record(name, self.legacy_desc(cards.get(name)), fn(frame))
            except Exception as e:  # shadow must never reach a card
                logger.error(f"SHADOW {name} failed: {e}")
        try:
            self.live_rates(frame)
        except Exception as e:
            logger.error(f"Live rates failed: {e}")

    def live_rates(self, frame):
        """Score the hour that just ended against the event-stream rate profiles (LF-5a left this
        to the nightly fit, which only looks back at the last 48 h of the lake). Once per
        completed local hour, two minutes in so late events have landed. Event streams only: email
        volume comes from a polled API and has no live counter. Counts come from household_events
        with no sa_data_exclusions applied (the lake applies them), so a test burst can flag here
        and be gone from the next nightly run. Findings go to sa_inferences, never to a card."""
        if frame.local_dt is None or frame.now is None or frame.local_dt.minute < 2:
            return []
        end = frame.now.replace(tzinfo=None, minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=1)
        if self._rates_window == start:
            return []
        profiles = [
            p
            for p in self.profiles(rates.NAME)
            if p.params.get("window") == "hour" and p.params["stream"].startswith("event:")
        ]
        self._rates_window = start
        if not profiles:
            return []
        db = self._connect()
        try:
            cursor = db.cursor()
            cursor.execute(
                "SELECT event_type, COALESCE(subject_type, '-'), COALESCE(verb, '-'), COUNT(*) "
                "FROM household_events WHERE occurred_at >= %s AND occurred_at < %s "
                "GROUP BY 1, 2, 3",
                (start, end),
            )
            counts = {f"event:{a}/{b}/{c}": n for a, b, c, n in cursor.fetchall()}
        finally:
            db.close()
        local_start = frame.local_dt.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        day = local_start.date()
        off = day.weekday() >= 5 or day in silver.ontario_holidays(day.year)
        learner = rates.RateLearner()
        now = frame.now.replace(tzinfo=None)
        findings = []
        for profile in profiles:
            found = learner.score(
                profile,
                {
                    "count": counts.get(profile.params["stream"], 0),
                    "hour": local_start.hour,
                    "daytype": "off" if off else "work",
                    "window_start": start,
                },
                now,
            )
            if found is not None:
                findings.append(found)
        if findings:
            self._persist(findings)
            logger.info(
                "LIVE rates: " + "; ".join(self.describe(f) for f in findings) + f" at {start}"
            )
        return findings

    def _scalar_state(self, db, query, params, frame, key, value):
        """A scalar learner state: hourly means from `query` (rows of (hour_start, mean))."""
        cursor = db.cursor()
        cursor.execute(query, params)
        now_hour = frame.now.replace(tzinfo=None, minute=0, second=0, microsecond=0)
        recent = []
        for hour_start, mean in cursor.fetchall():
            lag = int((now_hour - hour_start).total_seconds() // 3600)
            if 1 <= lag <= HOURS_BACK and mean is not None:
                local_hour = (frame.local_dt - timedelta(hours=lag)).hour
                recent.append((lag, local_hour, scalar.to_model(key, float(mean))))
        return {
            "value": scalar.to_model(key, float(value)),
            "recent": recent,
            "local_dt": frame.local_dt,
        }

    def _scalar_findings(self, frame, db, series_filter, value, query, params):
        findings = []
        learner = scalar.ScalarLearner()
        now_utc = frame.now.replace(tzinfo=None)
        for profile in self.profiles(scalar.NAME):
            key = profile.params["series_key"]
            if not series_filter(key) or value is None:
                continue
            state = self._scalar_state(db, query, params(profile), frame, key, value)
            inference = learner.score(profile, state, now_utc)
            if inference is not None:
                findings.append(inference)
        return findings

    def climate(self, frame):
        climate = frame.esphome_climate
        if not climate or frame.local_dt is None:
            return []
        db = self._connect()
        try:
            cursor = db.cursor()
            cursor.execute(
                "SELECT id, name FROM smarthome_devices WHERE source = 'esphome' AND "
                "device_type = 'sensor' AND (LOWER(name) LIKE '%%temperature%%' "
                "OR LOWER(name) LIKE '%%humidity%%')"
            )
            ids = {
                ("temperature" if "temperature" in n.lower() else "humidity"): i
                for i, n in cursor.fetchall()
            }
            since = frame.now.replace(tzinfo=None, minute=0, second=0, microsecond=0) - timedelta(
                hours=HOURS_BACK
            )
            query = (
                "SELECT STR_TO_DATE(DATE_FORMAT(recorded_at, '%%Y-%%m-%%d %%H:00:00'), "
                "'%%Y-%%m-%%d %%H:%%i:%%s') AS h, AVG(value) FROM smarthome_sensor_history "
                "WHERE smarthome_device_id = %s AND recorded_at >= %s GROUP BY h"
            )
            findings = []
            for kind, suffix, value in (
                ("temperature", ":Temperature", climate.get("temperature_c")),
                ("humidity", ":Humidity", climate.get("humidity_pct")),
            ):
                if kind not in ids or value is None or not climate.get(f"{kind}_online"):
                    continue
                findings += self._scalar_findings(
                    frame, db, lambda k, s=suffix: k.startswith("esphome:") and k.endswith(s),
                    value, query, lambda _p, i=ids[kind]: (i, since),
                )  # fmt: skip
            return findings
        finally:
            db.close()

    def attention(self, frame):
        launcher = frame.launcher_context
        snapshot = launcher and launcher.attention_snapshot
        if not snapshot or frame.local_dt is None:
            return []
        db = self._connect()
        try:
            since = frame.now.replace(tzinfo=None, minute=0, second=0, microsecond=0) - timedelta(
                hours=HOURS_BACK
            )
            findings = []
            for column in ("switch_count", "unlock_count"):
                query = (
                    "SELECT STR_TO_DATE(DATE_FORMAT(reported_at, '%%Y-%%m-%%d %%H:00:00'), "
                    f"'%%Y-%%m-%%d %%H:%%i:%%s') AS h, AVG({column}) "
                    "FROM attention_telemetry_history "
                    "WHERE reported_at >= %s GROUP BY h"
                )
                findings += self._scalar_findings(
                    frame, db, lambda k, c=column: k == f"attention:{c}",
                    snapshot.get(column, 0), query, lambda _p: (since,),
                )  # fmt: skip
            return findings
        finally:
            db.close()

    def departure(self, frame):
        if not frame.person_presence or frame.local_dt is None:
            return []
        profiles = {str(p.subject_id): p for p in self.profiles(presence.NAME)}
        learner = presence.PresenceLearner()
        now_utc = frame.now.replace(tzinfo=None)
        findings = []
        for person in frame.person_presence:
            profile = profiles.get(str(person["user_id"]))
            if profile is None or not person["home"]:
                continue  # departure_anomaly is about people who are STILL home
            inference = learner.score(
                profile, {"home": True, "away_minutes": None, "local_dt": frame.local_dt}, now_utc
            )
            if inference is not None:
                findings.append(inference)
        return findings

    def rhythm(self, frame):
        profiles = {str(p.subject_id): p for p in self.profiles(device_rhythm.NAME)}
        if not profiles or frame.local_dt is None:
            return []
        db = self._connect()
        try:
            cursor = db.cursor()
            cursor.execute(
                "SELECT d.id, s.state, d.last_online, d.name FROM device d "
                "JOIN states s ON d.state = s.id WHERE d.last_online IS NOT NULL"
            )
            rows = cursor.fetchall()
        finally:
            db.close()
        learner = device_rhythm.DeviceRhythmLearner()
        now_utc = frame.now.replace(tzinfo=None)
        findings = []
        # A device whose row was replaced (MAC rotation, re-adoption) leaves an old row offline for
        # good while the same name is online under a new id: not an absence.
        online_names = {name for _id, state, _seen, name in rows if state == "online"}
        for device_id, state, last_online, name in rows:
            profile = profiles.get(str(device_id))
            if profile is None:
                continue
            if state != "online" and name in online_names and name != "unknown":
                continue
            minutes = (now_utc - last_online).total_seconds() / 60.0
            online = state == "online"
            found = learner.score(
                profile,
                {"online": online, "offline_minutes": None if online else minutes,
                 "local_dt": frame.local_dt},
                now_utc,
            )  # fmt: skip
            if found is not None:
                findings.append(found)
            if online:
                found = learner.score_duration(
                    profile, {"minutes_on": minutes, "local_dt": frame.local_dt}, now_utc
                )
                if found is not None:
                    findings.append(found)
        return findings

    def household(self, frame):
        """Once per day, the first cycle at or after the cutoff hour: the household's day so far."""
        if frame.local_dt is None or frame.local_dt.hour < household_day.CUTOFF_HOUR:
            return []
        day = frame.local_dt.date()
        if day in self._household:
            return self._household[day]
        profiles = self.profiles(household_day.NAME)
        self._household = {}
        if not profiles:
            return []
        midnight = frame.now.replace(tzinfo=None) - (
            frame.local_dt - datetime.combine(day, datetime.min.time())
        )
        cutoff = midnight + timedelta(hours=household_day.CUTOFF_HOUR)
        db = self._connect()
        try:
            cursor = db.cursor()
            cursor.execute(
                "SELECT COUNT(DISTINCT device_id), MIN(timestamp) FROM device_history "
                "WHERE timestamp >= %s AND timestamp < %s",
                (midnight, cutoff),
            )
            devices, _first = cursor.fetchone()
            cursor.execute(
                "SELECT MIN(h.timestamp) FROM device_history h WHERE h.timestamp >= %s "
                "AND h.timestamp < %s AND NOT EXISTS (SELECT 1 FROM device_history p WHERE "
                "p.device_id = h.device_id AND p.timestamp < h.timestamp AND "
                "p.timestamp >= h.timestamp - INTERVAL %s MINUTE)",
                (midnight, cutoff, COME_ONLINE_GAP_MINUTES),
            )
            first = cursor.fetchone()[0]
            # Person-minutes at home: owners' and residents' phones (device types 3 and 5), the
            # same stay rule as silver. Filtered on the indexed `timestamp` (a history row is
            # stamped about a minute after the sighting it logs): `last_online` has no index and
            # device_history is huge. Looks back one gap before midnight for a stay in progress.
            resident_ids = [
                p["user_id"]
                for p in (frame.person_presence or [])
                if p["user_type"] in household_day.HOME_USER_TYPES
            ]
            home = None
            lookback = midnight - timedelta(minutes=household_day.PRESENCE_GAP_MINUTES)
            if resident_ids:
                cursor.execute(
                    "SELECT DISTINCT user_id, last_online FROM device_history WHERE user_id IN "
                    f"({','.join(['%s'] * len(resident_ids))}) AND device_type IN (3, 5) "
                    "AND timestamp >= %s AND timestamp < %s "
                    "AND last_online >= %s AND last_online < %s",
                    (
                        *resident_ids,
                        lookback,
                        cutoff + timedelta(minutes=5),
                        lookback,
                        cutoff,
                    ),
                )
                seen = {}
                for user_id, last_online in cursor.fetchall():
                    seen.setdefault(user_id, []).append(last_online)
                home = household_day.home_minutes(seen, midnight, cutoff)
        finally:
            db.close()
        first_minute = (
            (first - midnight).total_seconds() / 60.0 if first else household_day.CUTOFF_HOUR * 60.0
        )
        inference = household_day.HouseholdDayLearner().score(
            profiles[0],
            {
                "devices": devices,
                "first_minute": first_minute,
                "home_minutes": home,
                "local_dt": frame.local_dt,
            },
            frame.now.replace(tzinfo=None),
        )
        self._household[day] = [inference] if inference else []
        return self._household[day]
