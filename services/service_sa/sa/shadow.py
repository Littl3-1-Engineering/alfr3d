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

from sa import inference_store, layer2
from sa import silver
from sa.learners.base import Inference, utcnow
from sa.learners import (
    away_unusual,
    day_off,
    daytime,
    device_rhythm,
    household_day,
    rates,
    scalar,
    stay,
)

logger = logging.getLogger("SALog")

# Every layer-2 inference the awareness loop computes. A new one is a Rule in sa/learners/ and a
# line here (sa/layer2.py).
RULES = (away_unusual.RULE, day_off.RULE, household_day.RULE)

HOURS_BACK = 24
COME_ONLINE_GAP_MINUTES = 45  # a device unseen this long is 'coming online' (silver's gap)


class ShadowRunner:
    def __init__(self, connect, persist):
        """connect() -> a new pymysql connection; persist(list_of_inferences) -> None."""
        self._connect = connect
        self._persist = persist
        self._profiles = {}  # learner name -> (stamp, [Profile])
        self._last = {}  # rule -> signature last logged
        self._daytime = (None, {})  # ((local day, checkpoint), {user id: Inference or None})
        self._stay_starts = {}  # user id -> start of the stay in progress (see departure)
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

    def record(self, rule, legacy, findings, persist=True):
        """Persist the learner's findings and log when (legacy, learner) differs from last time."""
        if findings and persist:
            self._persist(findings)
        learner_desc = "; ".join(self.describe(f) for f in findings) or "quiet"
        signature = (legacy, learner_desc)
        if self._last.get(rule) != signature:
            self._last[rule] = signature
            agree = "AGREE" if (legacy == "quiet") == (not findings) else "DIFFER"
            logger.info(f"SHADOW {rule} {agree}: legacy={legacy} learner={learner_desc}")
            self._save_comparison(rule, agree, legacy, learner_desc, len(findings))

    def _save_comparison(self, rule, verdict, legacy, learner_desc, learner_count):
        """Keep the comparison past a restart (sa_shadow_comparison). Best effort: the shadow
        must never fail a cycle."""
        try:
            db = self._connect()
            try:
                inference_store.save_comparison(
                    db, rule, utcnow(), verdict, legacy, learner_desc, learner_count
                )
            finally:
                db.close()
        except Exception as e:
            logger.error(f"SHADOW {rule} comparison not saved: {e}")

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
        try:
            self.calendar_state(frame)
        except Exception as e:
            logger.error(f"Calendar state failed: {e}")
        try:
            self.household_features(frame)
        except Exception as e:
            logger.error(f"Household features failed: {e}")
        try:
            self.daytime_rows(frame)
        except Exception as e:
            logger.error(f"Daytime failed: {e}")
        try:
            self.layer2(frame, cards)
        except Exception as e:
            logger.error(f"Layer 2 failed: {e}")

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
        """`departure_anomaly` as an overstay: a resident whose stay so far is improbably long
        for them (sa/learners/stay.py). The presence learner's marginal p(home) cannot answer this
        (a part-time resident is rarely home at any hour), so this reads the stay profile."""
        if not frame.person_presence or frame.local_dt is None or frame.now is None:
            return []
        profiles = {str(p.subject_id): p for p in self.profiles(stay.NAME)}
        learner = stay.StayLearner()
        now_utc = frame.now.replace(tzinfo=None)
        findings = []
        for person in frame.person_presence:
            uid = str(person["user_id"])
            if not person["home"]:
                self._stay_starts.pop(uid, None)  # the next arrival starts a new stay
                continue
            profile = profiles.get(uid)
            if profile is None or person["user_type"] not in stay.OVERSTAY_USER_TYPES:
                continue
            start = self._stay_start(person["user_id"], now_utc)
            if start is None:
                continue
            inference = learner.score(profile, {"stay_start": start}, now_utc)
            if inference is not None:
                findings.append(inference)
        return findings

    def _stay_start(self, user_id, now_utc):
        """When this person's current stay began, from their phones' sightings in device_history,
        cached for as long as they stay home (the query takes ~1.5 s for a busy phone)."""
        key = str(user_id)
        cached = self._stay_starts.get(key)
        if cached is not None:
            return cached
        db = self._connect()
        try:
            cursor = db.cursor()
            cursor.execute(
                "SELECT DISTINCT last_online FROM device_history WHERE timestamp >= %s "
                "AND user_id = %s AND device_type IN %s AND last_online IS NOT NULL",
                (
                    now_utc - timedelta(days=stay.LOOKBACK_DAYS),
                    user_id,
                    silver.PERSONAL_DEVICE_TYPES,
                ),
            )
            start = stay.stay_start_from_sightings([row[0] for row in cursor.fetchall()])
        finally:
            db.close()
        if start is not None:
            self._stay_starts[key] = start
        return start

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

    def calendar_state(self, frame):
        """Layer-1 observation for layer 2: an event on the household calendar covers now. A state
        row, not a deviation (no probability): rules use it to EXPLAIN an absence. Refreshed each
        cycle while the event lasts, so it drops out of layer 2 within minutes of ending. The title
        is deliberately not stored."""
        if frame.now is None:
            return []
        now = frame.now.replace(tzinfo=None)
        db = self._connect()
        try:
            cursor = db.cursor()
            cursor.execute(
                "SELECT id, start_time, end_time FROM calendar_events "
                "WHERE start_time <= %s AND end_time >= %s",
                (now, now),
            )
            rows = cursor.fetchall()
        finally:
            db.close()
        found = [
            Inference(
                kind="state",
                subject_type="household",
                subject_id="calendar",
                signal=layer2.SIGNAL_CALENDAR_BUSY,
                learner="calendar_observer",
                learner_version="1",
                window_start=start,
                window_end=end,
                observed={"state": "busy"},
                confidence=1.0,
                evidence={"family": "calendar", "event_id": event_id},
                expires_at=end,
            )
            for event_id, start, end in rows
        ]
        if found:
            self._persist(found)
        return found

    def layer2(self, frame, cards=None):
        """Layer 2: combine the fresh layer-1 rows in sa_inferences (sa/layer2.py), one pass for
        every registered rule. Persisted to sa_inferences and logged when the set of results
        changes; never a card. Rows are only read after the layer-1 passes above have refreshed
        them this cycle."""
        if frame.now is None:
            return []
        now_utc = frame.now.replace(tzinfo=None)
        db = self._connect()
        try:
            parents = inference_store.load_recent(
                db, 1, now_utc - timedelta(minutes=layer2.FRESH_MINUTES)
            )
            ctx = self._layer2_context(db, parents, frame)
        finally:
            db.close()
        findings = layer2.run_rules(RULES, parents, ctx, now_utc) if parents else []
        if findings:
            self._persist(findings)
        for rule in RULES:
            legacy_rule = getattr(rule, "legacy_rule", None)
            if legacy_rule and cards and legacy_rule in cards:
                self.record(
                    legacy_rule,
                    self.legacy_desc(cards[legacy_rule]),
                    [f for f in findings if f.learner == rule.name],
                    persist=False,
                )
        signature = tuple(sorted((f.learner, f.subject_id) for f in findings))
        if self._last.get("layer2") != signature:
            self._last["layer2"] = signature
            if findings:
                logger.info(
                    "LIVE layer2: "
                    + "; ".join(
                        f"{f.learner} {f.evidence.get('username') or f.subject_id} "
                        f"{f.surprise:.1f} bits conf={f.confidence:.2f} "
                        f"families={','.join(f.evidence['families'])}"
                        for f in findings
                    )
                )
            else:
                logger.info("LIVE layer2: quiet")
        return findings

    def _layer2_context(self, db, parents, frame):
        """What the rules need beyond the parents themselves: who owns each device, and how many
        of each person's devices have a rhythm profile (the corroboration base). Queried only when a
        rule needs it: owners when a device deviation is among the parents, today's calendar when
        a home deviation is."""
        ctx = {"owners": {}, "owned_with_profile": {}}
        if frame.local_dt is not None and any(
            p.signal == daytime.SIGNAL and (p.observed or {}).get("state") == "home"
            for p in parents
        ):
            day_start = frame.now.replace(tzinfo=None) - (
                frame.local_dt - frame.local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM calendar_events WHERE start_time < %s AND end_time >= %s",
                (day_start + timedelta(days=1), day_start),
            )
            ctx["day_start_utc"] = day_start.replace(microsecond=0)
            ctx["calendar_events_today"] = cursor.fetchone()[0]
        if not any(p.signal == device_rhythm.SIGNAL_AVAILABILITY for p in parents):
            return ctx
        cursor = db.cursor()
        cursor.execute("SELECT id, user_id FROM device WHERE user_id IS NOT NULL")
        owners = {str(device_id): str(user_id) for device_id, user_id in cursor.fetchall()}
        ctx["owners"] = owners
        for profile in self.profiles(device_rhythm.NAME):
            user = owners.get(str(profile.subject_id))
            if user is not None:
                ctx["owned_with_profile"][user] = ctx["owned_with_profile"].get(user, 0) + 1
        return ctx

    def daytime_rows(self, frame):
        """Layer-1 `presence.daytime` rows (sa/learners/daytime.py): residents who have been home
        unusually long in today's 09:00-17:00 window so far. Scored once per local hour for
        everyone with one device_history pass, cached, and re-persisted each cycle so layer 2
        (`day_off`) keeps seeing them as fresh."""
        if frame.local_dt is None or frame.now is None or not frame.person_presence:
            return []
        checkpoint = daytime.eval_hour(frame.local_dt.hour)
        if checkpoint is None:
            return []
        day = frame.local_dt.date()
        if self._daytime[0] != (day, checkpoint):
            self._daytime = ((day, checkpoint), self._score_daytime(frame, day, checkpoint))
        rows = [r for r in self._daytime[1].values() if r is not None]
        now = utcnow()
        for row in rows:
            row.computed_at = now
        if rows:
            self._persist(rows)
        return rows

    def _score_daytime(self, frame, day, checkpoint):
        profiles = {str(p.subject_id): p for p in self.profiles(daytime.NAME)}
        residents = [
            p["user_id"]
            for p in frame.person_presence
            if p["user_type"] in household_day.HOME_USER_TYPES and str(p["user_id"]) in profiles
        ]
        if not residents:
            return {}
        now_utc = frame.now.replace(tzinfo=None)
        midnight = now_utc - (frame.local_dt - datetime.combine(day, datetime.min.time()))
        window_start = midnight + timedelta(hours=daytime.WINDOW_START_HOUR)
        window_end = midnight + timedelta(hours=checkpoint)
        db = self._connect()
        try:
            cursor = db.cursor()
            # Same filter as household(): the indexed `timestamp`, phones only, one gap of lookback
            # for a stay already in progress at the window's start.
            lookback = window_start - timedelta(minutes=household_day.PRESENCE_GAP_MINUTES)
            cursor.execute(
                "SELECT DISTINCT user_id, last_online FROM device_history WHERE user_id IN "
                f"({','.join(['%s'] * len(residents))}) AND device_type IN %s "
                "AND timestamp >= %s AND timestamp < %s AND last_online >= %s "
                "AND last_online < %s",
                (
                    *residents,
                    silver.PERSONAL_DEVICE_TYPES,
                    lookback,
                    window_end + timedelta(minutes=5),
                    lookback,
                    window_end,
                ),
            )
            seen = {}
            for user_id, last_online in cursor.fetchall():
                seen.setdefault(user_id, []).append(last_online)
        finally:
            db.close()
        learner = daytime.DaytimeLearner()
        scored = {}
        for user_id in residents:
            minutes = household_day.home_minutes(
                {user_id: seen.get(user_id, [])}, window_start, window_end
            )
            scored[user_id] = learner.score(
                profiles[str(user_id)],
                {"hours_home": minutes / 60.0, "local_dt": frame.local_dt, "day_start": midnight},
                now_utc,
            )
        return scored

    def household(self, frame):
        """The household's day so far as layer-1 feature rows (household_day.score_features),
        computed once per day at the first cycle at or after the cutoff hour; the layer-2 rule
        household_unusual_day combines them. The rows are cached for the day and re-persisted by
        household_features() each cycle so layer 2 keeps seeing them as fresh."""
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
            # The day's devices and the first to COME online, measured the way silver measures the
            # fitted days (sa/silver.py device_islands): by SIGHTINGS (`last_online`), not by
            # history rows (every state change writes a row, which inflated the count 2-3x), with
            # rows of one named device owned by one person merged into one identity, and a device
            # "comes online" when its previous sighting is more than a gap earlier. One window pass
            # (a correlated NOT EXISTS took minutes on device_history and wedged the loop). Filtered
            # on the indexed `timestamp`, which trails the sighting by about a minute.
            person_ids = [p["user_id"] for p in (frame.person_presence or [])] or [-1]
            ident = (
                "CASE WHEN user_id IN ("
                + ",".join(["%s"] * len(person_ids))
                + ") AND name IS NOT NULL AND name <> 'unknown' "
                "THEN CONCAT('p', user_id, ':', name) ELSE CONCAT('d', device_id) END"
            )
            cursor.execute(
                "SELECT COUNT(DISTINCT ident), "
                "MIN(CASE WHEN prev IS NULL OR prev < ts - INTERVAL %s MINUTE THEN ts END) FROM ("
                f"SELECT ident, ts, LAG(ts) OVER (PARTITION BY ident ORDER BY ts) AS prev FROM ("
                f"SELECT DISTINCT {ident} AS ident, last_online AS ts FROM device_history "
                "WHERE timestamp >= %s - INTERVAL %s MINUTE AND timestamp < %s + INTERVAL 5 MINUTE "
                "AND last_online IS NOT NULL AND last_online >= %s - INTERVAL %s MINUTE "
                "AND last_online < %s) s) x WHERE ts >= %s",
                (
                    COME_ONLINE_GAP_MINUTES,
                    *person_ids,
                    midnight,
                    COME_ONLINE_GAP_MINUTES,
                    cutoff,
                    midnight,
                    COME_ONLINE_GAP_MINUTES,
                    cutoff,
                    midnight,
                ),
            )
            devices, first = cursor.fetchone()
            # The devices seen in the INVENTORY_DAYS before today: what "all the devices" is now.
            # A device deleted from the system leaves it after two weeks, so retiring hardware
            # does not read as a quiet house (silver measures the fitted days the same way).
            since = midnight - timedelta(days=household_day.INVENTORY_DAYS)
            cursor.execute(
                f"SELECT COUNT(DISTINCT {ident}) FROM device_history "
                "WHERE timestamp >= %s AND timestamp < %s + INTERVAL 5 MINUTE "
                "AND last_online IS NOT NULL AND last_online >= %s AND last_online < %s",
                (*person_ids, since, midnight, since, midnight),
            )
            (inventory,) = cursor.fetchone()
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
        rows = household_day.HouseholdDayLearner().score_features(
            profiles[0],
            {
                "devices": devices,
                "device_share": (
                    devices / inventory if inventory >= household_day.MIN_INVENTORY else None
                ),
                "first_minute": first_minute,
                "home_minutes": home,
                "local_dt": frame.local_dt,
            },
            frame.now.replace(tzinfo=None),
        )
        self._household[day] = rows
        return rows

    def household_features(self, frame):
        """Refresh this day's household feature rows in sa_inferences (a handful of upserts)."""
        rows = self.household(frame)
        if rows:
            now = utcnow()
            for row in rows:
                row.computed_at = now  # layer 2 only reads rows refreshed in the last few minutes
            self._persist(rows)
        return rows
