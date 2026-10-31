"""Device rhythm learner: is this device on (or off) when it usually isn't (is), and has this
session lasted longer than any normal one? The learner behind the legacy `rhythm_break_anomaly`
rule's three deviation types:

- `unusual_hour`   -> availability: the device is ON at an hour when it almost never is
- `expected_absent`-> availability: the device is OFF at an hour when it almost always is on
- `still_on_past_typical` -> duration: the current session is longer than almost every past one

Availability reuses the presence learner's pooled day-of-week x hour Beta-Binomial (a device is a
"person" whose hourly state is the fraction of the hour it was online); duration is the empirical
survival function of past sessions (recency-weighted), so "p" is literally "the share of past
sessions that lasted at least this long". The legacy rule used a median-ish typical maximum plus a
fixed grace, and a typical active hour with a fixed tolerance. Here every device gets a
probability and a confidence instead of two hand-set margins.
"""

import logging
import math
import os
import sys
from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo

import duckdb

from sa import confidence, inference_store
from sa.learners import presence
from sa.learners.base import Inference, Learner, Profile, utcnow

logger = logging.getLogger("SADeviceRhythm")

NAME = "device_rhythm"
VERSION = "1"
SIGNAL_AVAILABILITY = "device.online"
SIGNAL_DURATION = "device.session_minutes"

MIN_OBSERVED_HOURS = 72
MIN_SESSIONS = 10
SESSION_LOOKBACK_DAYS = 120
MAX_SESSIONS_STORED = 400
SESSION_HALF_LIFE_DAYS = 28.0
MIN_OPEN_GAP_MINUTES = 45  # a session ending this close to the horizon may still be open

MIN_SURPRISE_BITS = presence.MIN_SURPRISE_BITS  # P of the observed state <= 12.5 %
MIN_OFFLINE_MINUTES = presence.MIN_AWAY_MINUTES  # devices flicker off for a few minutes
MAX_OFFLINE_MINUTES = 3 * 24 * 60  # offline for days is gone, not late
RETIRED_AFTER_DAYS = 14  # no session this recently: the device is no longer part of the house
MIN_GAPS = 10  # unexpected offline gaps needed before a device's own flicker length is trusted
GAP_QUANTILE = 0.9  # an offline stretch must outlast this share of the device's own flickers
MAX_FLICKER_MINUTES = 24 * 60  # a longer gap is an absence, not a flicker, and stays out
USUALLY_ON = 0.5  # an hour counts as "usually on" when the device is online in at least this share
P_DURATION_FLAG = 0.02  # at most 2 % of past sessions ran this long
DURATION_GRACE_MINUTES = 30  # and it has to be genuinely longer than the longest ordinary one


def offline_flicker_minutes(sessions, cells, ref, cutoff, tz):
    """How long this device's own unexpected offline stretches last: the GAP_QUANTILE of the gaps
    between its sessions whose midpoint falls in an
    hour it is usually on, recency-weighted. A PC that sleeps
    for two hours most afternoons is only worth a card when it is off longer than that. None with
    fewer than MIN_GAPS such gaps. sessions: [(start_date, minutes, end_utc)]."""
    zone = ZoneInfo(tz)
    ordered = sorted(sessions, key=lambda s: s[2])
    gaps = []
    for prev, nxt in zip(ordered, ordered[1:]):
        minutes = (nxt[2] - timedelta(minutes=nxt[1]) - prev[2]).total_seconds() / 60.0
        if not 0 < minutes <= MAX_FLICKER_MINUTES:
            continue
        # Judged by its midpoint, so a nightly shutdown that begins while the device is still
        # usually on (and ends hours into the next morning) is not counted as a flicker.
        middle = (prev[2] + timedelta(minutes=minutes / 2)).replace(tzinfo=timezone.utc)
        middle = middle.astimezone(zone)
        if middle.date() < cutoff:
            continue
        p_on, _w = presence.cell(cells, middle.date(), middle.hour)
        if p_on >= USUALLY_ON:
            age = max(0, (ref - middle.date()).days)
            gaps.append((minutes, 0.5 ** (age / SESSION_HALF_LIFE_DAYS)))
    if len(gaps) < MIN_GAPS:
        return None
    gaps.sort()
    target, running = GAP_QUANTILE * sum(w for _, w in gaps), 0.0
    for minutes, weight in gaps:
        running += weight
        if running >= target:
            return minutes
    return gaps[-1][0]


def survival(durations, x):
    """P(session >= x) from [(minutes, weight)], smoothed so it is never exactly 0 or 1."""
    total = sum(w for _, w in durations)
    over = sum(w for d, w in durations if d >= x)
    return (over + 0.5) / (total + 1.0)


class DeviceRhythmLearner(Learner):
    name = NAME
    version = VERSION

    def fit_device(self, device_id, name, rows, sessions, ref, horizon):
        """Profile for one device, or None. rows: (date, hour, dow, minutes_online, observed);
        sessions: [(start_date, duration_minutes, end_utc)]."""
        observed = [(d, h, dw, m) for d, h, dw, m, ok in rows if ok and d <= ref]
        if len(observed) < MIN_OBSERVED_HOURS:
            return None
        cells = presence.fit_cells(observed, ref)
        stability, detail = presence.stability_of(observed, ref)
        cutoff = ref - timedelta(days=SESSION_LOOKBACK_DAYS)
        kept = [
            (dur, 0.5 ** (max(0, (ref - d).days) / SESSION_HALF_LIFE_DAYS))
            for d, dur, end in sessions
            if d >= cutoff
            and (horizon is None or end <= horizon - timedelta(minutes=MIN_OPEN_GAP_MINUTES))
        ]
        kept.sort(key=lambda t: -t[1])  # newest (heaviest) first, then cap
        kept = kept[:MAX_SESSIONS_STORED]
        if len(kept) < MIN_SESSIONS:
            return None  # gone or never really used: nothing to be unusual against
        newest_end = max((end for _d, _dur, end in sessions), default=None)
        if newest_end is None or newest_end.date() < ref - timedelta(days=RETIRED_AFTER_DAYS):
            return None
        from sa import silver

        flicker = offline_flicker_minutes(sessions, cells, ref, cutoff, silver.TIMEZONE)
        recent_cut = ref - timedelta(days=presence.COVERAGE_WINDOW_DAYS - 1)
        window = [ok for d, _h, _dw, _m, ok in rows if recent_cut <= d <= ref]
        coverage = sum(1 for ok in window if ok) / len(window) if window else 0.0
        params = {
            "device": name,
            "m0": round(cells["m0"], 4),
            "p_dow": [[round(p, 4) for p in row] for row in cells["p_dow"]],
            "w_dow": [[round(w, 3) for w in row] for row in cells["w_dow"]],
            "p_daytype": {k: [round(p, 4) for p in v] for k, v in cells["p_dt"].items()},
            "w_daytype": {k: [round(w, 3) for w in v] for k, v in cells["w_dt"].items()},
            "sessions": [[round(d, 1), round(w, 4)] for d, w in kept],
            "offline_flicker_minutes": None if flicker is None else round(flicker, 1),
            "stability_detail": {
                k: (round(v, 4) if isinstance(v, float) else v) for k, v in detail.items()
            },
        }
        return Profile(
            learner=self.name,
            learner_version=self.version,
            subject_type="device",
            subject_id=device_id,
            signal="device.rhythm",
            params=params,
            n_eff=round(sum(sum(row) for row in cells["w_dow"]), 3),
            coverage=round(coverage, 4),
            source_quality=1.0,
            stability=round(stability, 4),
            fitted_from=min(d for d, *_ in observed),
            fitted_to=ref,
        )

    def fit(self, lake_dir, ref=None):
        data = load_gold(lake_dir)
        if not data["rows"]:
            return []
        ref = ref or max(r[0] for rows in data["rows"].values() for r in rows)
        profiles = []
        for device_id, rows in sorted(data["rows"].items()):
            profile = self.fit_device(
                device_id,
                data["names"].get(device_id),
                rows,
                data["sessions"].get(device_id, []),
                ref,
                data["horizon"],
            )
            if profile is not None:
                profiles.append(profile)
        logger.info(f"device rhythm: fitted {len(profiles)} device(s) as of {ref}")
        return profiles

    def _terms(self, profile, weight):
        return confidence.Confidence(
            confidence.sufficiency(weight),
            profile.coverage,
            profile.source_quality,
            profile.stability,
        )

    def score(self, profile, state, now):
        """Availability deviation: state {"online": bool, "offline_minutes": float|None,
        "local_dt"}. None if unremarkable (or too soon to call an absence)."""
        cells = presence.cells_from_params(profile.params)
        local_dt = state["local_dt"]
        day, hour = local_dt.date(), local_dt.hour
        p_on, weight = presence.cell(cells, day, hour)
        online = bool(state["online"])
        p_observed = min(1.0, max(1e-6, p_on if online else 1.0 - p_on))
        surprise = -math.log2(p_observed)
        if surprise < MIN_SURPRISE_BITS:
            return None
        off_minutes = state.get("offline_minutes")
        # Not an absence until it outlasts both the fixed floor and this device's own flickers.
        minimum = max(MIN_OFFLINE_MINUTES, profile.params.get("offline_flicker_minutes") or 0)
        if not online and (
            off_minutes is None or not minimum <= off_minutes <= MAX_OFFLINE_MINUTES
        ):
            return None
        terms = self._terms(profile, weight)
        return Inference(
            kind="deviation",
            subject_type="device",
            subject_id=profile.subject_id,
            signal=SIGNAL_AVAILABILITY,
            learner=self.name,
            learner_version=self.version,
            window_start=(
                now.replace(minute=0, second=0, microsecond=0)
                if online
                else now - timedelta(minutes=off_minutes)
            ),
            window_end=now.replace(microsecond=0),
            context={"hour_local": hour, "dow": day.weekday()},
            observed={
                "state": "online" if online else "offline",
                "offline_minutes": off_minutes,
            },
            expected={"p_online": round(p_on, 4)},
            probability=round(p_observed, 6),
            surprise=round(surprise, 3),
            confidence=round(terms.value, 4),
            n_eff=round(weight, 3),
            evidence={"terms": terms.as_dict(), "device": profile.params.get("device")},
            expires_at=now + timedelta(hours=6),
        )

    def score_duration(self, profile, state, now):
        """Duration deviation: state {"minutes_on": float}. Fires when the share of past sessions
        that lasted this long is <= P_DURATION_FLAG and the session is also at least
        DURATION_GRACE_MINUTES past the longest ordinary (95 % weight) one."""
        sessions = [(d, w) for d, w in profile.params.get("sessions", [])]
        if len(sessions) < MIN_SESSIONS:
            return None
        x = float(state["minutes_on"])
        p = survival(sessions, x)
        ordered = sorted(sessions)
        total, running, p95 = sum(w for _, w in ordered), 0.0, ordered[-1][0]
        for d, w in ordered:
            running += w
            if running >= 0.95 * total:
                p95 = d
                break
        if p > P_DURATION_FLAG or x < p95 + DURATION_GRACE_MINUTES:
            return None
        terms = self._terms(profile, sum(w for _, w in sessions))
        return Inference(
            kind="deviation",
            subject_type="device",
            subject_id=profile.subject_id,
            signal=SIGNAL_DURATION,
            learner=self.name,
            learner_version=self.version,
            window_start=now - timedelta(minutes=x),
            window_end=now.replace(microsecond=0),
            context={"hour_local": state["local_dt"].hour},
            observed={"minutes_on": round(x, 1)},
            expected={"p95_minutes": round(p95, 1), "share_at_least": round(p, 4)},
            probability=round(p, 6),
            surprise=round(-math.log2(p), 3),
            confidence=round(terms.value, 4),
            n_eff=round(sum(w for _, w in sessions), 3),
            evidence={"terms": terms.as_dict(), "device": profile.params.get("device")},
            expires_at=now + timedelta(hours=6),
        )


_HOURLY_SQL = """
            WITH dev AS (SELECT device_id, MAX(name) AS name, MIN(start_utc) AS first_seen
                         FROM sess GROUP BY 1)
            SELECT d.device_id, d.name,
                   CAST(to_local(b.bucket_utc) AS DATE), hour(to_local(b.bucket_utc)),
                   isodow(to_local(b.bucket_utc)) - 1,
                   COALESCE(SUM(epoch(LEAST(s.end_utc, b.bucket_utc + INTERVAL 1 HOUR)
                                      - GREATEST(s.start_utc, b.bucket_utc)) / 60.0), 0),
                   b.observed
            FROM dev d
            JOIN hrs b ON b.bucket_utc >= date_trunc('hour', d.first_seen)
            LEFT JOIN sess s ON s.device_id = d.device_id
                            AND s.start_utc < b.bucket_utc + INTERVAL 1 HOUR
                            AND s.end_utc > b.bucket_utc
            GROUP BY ALL ORDER BY 1, 3, 4
            """


# --- Reading the lake --------------------------------------------------------------------------


def load_gold(lake_dir, tz=None):
    """{"rows": {device_id: [(date, hour, dow, minutes_online, observed)]}, "names", "sessions":
    {device_id: [(start_date, minutes, end_utc)]}, "horizon"}. Hours are the ones the presence grid
    counts as observed; a device's history starts at its first session."""
    from sa import silver

    tz = tz or silver.TIMEZONE
    sessions_file = os.path.join(lake_dir, "silver", "device_sessions", "part-0.parquet")
    grid_file = os.path.join(lake_dir, "gold", "presence_grid", "part-0.parquet")
    out = {"rows": {}, "names": {}, "sessions": {}, "horizon": None}
    if not (os.path.exists(sessions_file) and os.path.exists(grid_file)):
        return out
    con = duckdb.connect()
    try:
        con.execute(f"CREATE MACRO to_local(ts) AS timezone('{tz}', timezone('UTC', ts))")
        con.execute(f"CREATE VIEW sess AS SELECT * FROM read_parquet('{sessions_file}')")
        con.execute(f"""CREATE VIEW hrs AS
                SELECT bucket_utc, bool_or(observed) AS observed
                FROM read_parquet('{grid_file}') GROUP BY 1""")
        out["horizon"] = con.execute("SELECT MAX(end_utc) FROM sess").fetchone()[0]
        for device_id, name, d, h, dow, minutes, ok in con.execute(_HOURLY_SQL).fetchall():
            out["rows"].setdefault(device_id, []).append((d, h, dow, min(60.0, minutes), ok))
            out["names"][device_id] = name
        for device_id, d, minutes, end in con.execute(
            "SELECT device_id, CAST(start_local AS DATE), epoch(end_utc - start_utc) / 60.0, "
            "end_utc "
            "FROM sess ORDER BY device_id, start_utc"
        ).fetchall():
            out["sessions"].setdefault(device_id, []).append((d, minutes, end))
        return out
    finally:
        con.close()


def run_fit(lake_dir, conn, now_utc=None):
    """The nightly job: fit every device with enough history and store the profiles."""
    profiles = DeviceRhythmLearner().fit(lake_dir)
    if not profiles:
        return {"profiles": 0, "removed": 0}
    inference_store.save_profiles(conn, profiles)
    removed = inference_store.delete_profiles_except(conn, NAME, [p.subject_id for p in profiles])
    return {"profiles": len(profiles), "removed": removed}


def backtest(lake_dir, device_id, start, end, learner=None):
    """Walk-forward availability: [{"date","hour","online","p_online","flagged"}] for every
    observed hour in [start, end], each day scored on a profile fitted before it. A device counts
    as online in an hour when it was on for at least half of it."""
    learner = learner or DeviceRhythmLearner()
    data = load_gold(lake_dir)
    device_id = int(device_id)  # Profile.subject_id is a string; the lake keys are ints
    rows = data["rows"].get(device_id, [])
    out, day = [], start
    while day <= end:
        profile = learner.fit_device(
            device_id,
            data["names"].get(device_id),
            [r for r in rows if r[0] < day],
            [s for s in data["sessions"].get(device_id, []) if s[0] < day],
            day - timedelta(days=1),
            data["horizon"],
        )
        if profile is not None:
            cells = presence.cells_from_params(profile.params)
            for d, h, _dw, minutes, ok in rows:
                if d != day or not ok:
                    continue
                p_on, _w = presence.cell(cells, d, h)
                online = minutes >= 30
                p_obs = p_on if online else 1 - p_on
                out.append(
                    {
                        "date": d,
                        "hour": h,
                        "online": online,
                        "p_online": p_on,
                        "flagged": -math.log2(max(p_obs, 1e-6)) >= MIN_SURPRISE_BITS,
                    }
                )
        day += timedelta(days=1)
    return out


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    for profile in DeviceRhythmLearner().fit(os.environ.get("SA_LAKE_DIR", "/lake")):
        print(
            f"{profile.subject_id:>4} {str(profile.params['device'])[:28]:28s} "
            f"n_eff={profile.n_eff:<8} cov={profile.coverage} stab={profile.stability} "
            f"sessions={len(profile.params['sessions'])}"
        )
