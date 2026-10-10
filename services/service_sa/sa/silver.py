"""Silver and gold layers: bronze cleaned once, then shaped for learners (LF-2,
todo/sa/todo_lf2_silver_gold.md).

Bronze (sa/lake.py) is a raw copy of MySQL. Every rule that read MySQL directly used to re-derive
the same things its own way (who is home, when a device was on, which sensor is which). Silver
does that cleaning once. Gold reshapes silver into the grids the layer-1 learners train on.

Both layers are rebuilt whole from bronze every night: the data is small (the whole lake is tens
of MB), a rebuild takes seconds, and a bug fix is then just a re-run, never a migration.

    <lake>/silver/<table>/part-0.parquet
    <lake>/gold/<table>/part-0.parquet
    <lake>/silver/_build.json        parameters + row counts of the last build

What the data taught us (Phase 0, 2026-10-10, on the household's real device_history):

- A device's `last_online` is a real sighting; the logged `state` is NOT (the before-update
  trigger records OLD.state, and two rows can share a second, so LEAD() ordering is unstable).
  Presence is therefore built from distinct `last_online` values, never from `state`.
- A person is represented by their PHONE. The household tags devices `resident`/`guest`
  (device_type 5/3) when they stand for a person and `HW` (2) for laptops, tablets, Kindles,
  speakers. Hardware stays home when its owner leaves (on 2026-10-09 the owner's phone was away
  08:34-14:42 local while his laptop stayed on at home all day), so it is NOT presence evidence.
  It still feeds device_sessions.
- The same physical phone appears under several device ids (private-MAC rotation), so presence
  is computed per user across all of a user's phone ids, never per device.
- Phones go quiet for ~30 minutes without leaving, and the observed gaps decay smoothly through
  30-60 minutes with no clean separation. PRESENCE_GAP_MINUTES sits just above the ~31 minute
  offline-marking bump. Absences shorter than that are merged into presence and counted in
  `short_gaps_merged` so a learner can see how much of an interval was inferred.

Assumptions, stated so a violation is easy to spot:
- Bronze timestamps are naive UTC (MySQL session clock is UTC on the NUC).
- The household lives in SA_TIMEZONE (default America/Toronto). Local time is computed with the
  IANA zone, so DST is handled; the environment row only carries a fixed offset.
- Interval ends are the last sighting, so they run ~1 minute short of true departure (a sighting
  lands roughly every 64 s while a phone is on the network).
"""

import json
import logging
import os
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pymysql

from sa import silver_contexts

logger = logging.getLogger("SASilver")

LAKE_DIR = os.environ.get("SA_LAKE_DIR", "/lake")
TIMEZONE = os.environ.get("SA_TIMEZONE", "America/Toronto")

# A gap between consecutive phone sightings longer than this starts a new presence interval.
PRESENCE_GAP_MINUTES = 45
# Gaps at least this long (and <= PRESENCE_GAP_MINUTES) that were merged into one interval are
# counted as `short_gaps_merged`: the stretch where presence was inferred, not observed.
AMBIGUOUS_GAP_MINUTES = 10
# An hour counts as "observed" when the collector wrote at least this fraction of its typical
# (median) hourly row count. device_history fell ~30x in July 2026 without ever reaching zero, so
# "any rows at all" would have called a collection outage a long absence.
OBSERVED_MIN_FRACTION = 0.1
# A day counts as observed when at least this many of its hours were.
OBSERVED_MIN_HOURS_PER_DAY = 20
# Sightings older than the collector are stale carry-over (a retired phone's last_online from
# 2023, copied into the first row logged for it) and are ignored. The tolerance is because a
# sighting is logged in a row stamped just AFTER it, so the very first real one predates the
# first row by about a minute.
# device_types.id for a person's own phone: 3 = guest, 5 = resident. 2 (HW) and everything else
# is hardware that does not travel with the person.
PERSONAL_DEVICE_TYPES = (3, 5)
# User types / names that are not people: the household system itself, and the catch-all that
# unclaimed devices are assigned to.
NON_PERSON_USER_TYPES = ("alfr3d",)
NON_PERSON_USERNAMES = ("unknown",)

SILVER_TABLES = (
    "presence_intervals",
    "device_sessions",
    "sensor_15m",
    "events_clean",
    "calendar_busy",
    "day_context",
    # LF-2b: the contexts added by LF-0b (sa/silver_contexts.py)
    "ha_states",
    "ha_intervals",
    "ha_entities",
    "weather_hourly",
    "email_events",
    "deck_intervals",
)
GOLD_TABLES = (
    "presence_grid",
    "daily_rhythm",
    "hourly_rates",
    "sensor_hourly",
    # LF-2b, built in a second gold pass because they read other gold / silver tables
    "scalar_hourly",
    "state_hourly",
    "email_hourly",
    "sender_daily",
    "context_hourly",
)


# --- Ontario statutory holidays (day_context.is_holiday) -----------------------------------


def _nth_weekday(year, month, weekday, n):
    """The n-th `weekday` (0=Mon) of a month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _easter(year):
    """Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = (h + el - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def ontario_holidays(year):
    """{date: name} for Ontario's statutory public holidays. Dates are literal: no 'observed'
    shifting when one lands on a weekend, since what matters here is when the household's routine
    changes, and that is the actual day."""
    victoria = date(year, 5, 24)
    victoria -= timedelta(days=(victoria.weekday() - 0) % 7)  # Monday on or before May 24
    return {
        date(year, 1, 1): "New Year's Day",
        _nth_weekday(year, 2, 0, 3): "Family Day",
        _easter(year) - timedelta(days=2): "Good Friday",
        victoria: "Victoria Day",
        date(year, 7, 1): "Canada Day",
        _nth_weekday(year, 9, 0, 1): "Labour Day",
        _nth_weekday(year, 10, 0, 2): "Thanksgiving",
        date(year, 12, 25): "Christmas Day",
        date(year, 12, 26): "Boxing Day",
    }


def _season(month):
    """Meteorological season (northern hemisphere)."""
    return {12: "winter", 1: "winter", 2: "winter"}.get(
        month,
        "spring" if month in (3, 4, 5) else "summer" if month in (6, 7, 8) else "autumn",
    )


DAY_CONTEXT_SCHEMA = pa.schema(
    [
        pa.field("date", pa.date32()),
        pa.field("dow", pa.int64()),
        pa.field("is_weekend", pa.bool_()),
        pa.field("month", pa.int64()),
        pa.field("season", pa.string()),
        pa.field("is_holiday", pa.bool_()),
        pa.field("holiday_name", pa.string()),
        pa.field("sunrise_utc", pa.timestamp("us")),
        pa.field("sunset_utc", pa.timestamp("us")),
        pa.field("daylight_minutes", pa.float64()),
    ]
)


def day_context_rows(start, end, location=None):
    """One row per calendar day in [start, end]: dow (0=Mon), weekend, month, season, holiday, and,
    given a (latitude, longitude), sunrise / sunset (UTC) and the length of daylight."""
    rows = []
    holidays = {}
    day = start
    while day <= end:
        if day.year not in holidays:
            holidays[day.year] = ontario_holidays(day.year)
        name = holidays[day.year].get(day)
        sunrise = sunset = daylight = None
        if location is not None:
            sunrise, sunset = silver_contexts.sun_times(day, location[0], location[1])
            if sunrise is not None:
                daylight = (sunset - sunrise).total_seconds() / 60.0
        rows.append(
            {
                "date": day,
                "dow": day.weekday(),
                "is_weekend": day.weekday() >= 5,
                "month": day.month,
                "season": _season(day.month),
                "is_holiday": name is not None,
                "holiday_name": name,
                "sunrise_utc": sunrise,
                "sunset_utc": sunset,
                "daylight_minutes": daylight,
            }
        )
        day += timedelta(days=1)
    return rows


# --- Overrides from MySQL -------------------------------------------------------------------


def load_overrides(conn):
    """(exclusions, aliases) from the hand-editable MySQL tables (migration 045).
    exclusions: [(source, event_type, subject_id, start_ts, end_ts)]; aliases: {id: sensor_key}."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT source, event_type, subject_id, start_ts, end_ts FROM sa_data_exclusions"
    )
    exclusions = list(cursor.fetchall())
    cursor.execute("SELECT smarthome_device_id, sensor_key FROM sa_sensor_aliases")
    aliases = {row[0]: row[1] for row in cursor.fetchall()}
    return exclusions, aliases


# --- Build ----------------------------------------------------------------------------------


def _files(lake, *parts):
    return list(Path(lake).joinpath(*parts).glob("*/part-*.parquet"))


def _view(con, name, lake, *parts, snapshot=False):
    """Create view `name` over a bronze table if it has any files. Returns whether it exists."""
    if not _files(lake, *parts):
        return False
    pattern = str(Path(lake).joinpath(*parts)) + "/*/part-*.parquet"
    # union_by_name: partitions written before a migration added a column lack it, and a column
    # that was entirely NULL on one day is typed differently from other days. Match by name, not
    # by the first file's schema.
    con.execute(
        f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{pattern}', "
        "hive_partitioning=true, union_by_name=true)"
    )
    return True


def _write(con, query, layer, table, lake):
    """Materialise `query` as <lake>/<layer>/<table>/part-0.parquet, swapped in atomically."""
    out_dir = Path(lake) / layer / table
    tmp_dir = Path(lake) / layer / f".tmp-{table}"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)
    con.execute(
        f"COPY ({query}) TO '{tmp_dir / 'part-0.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    rows = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{tmp_dir / 'part-0.parquet'}')"
    ).fetchone()[0]
    shutil.rmtree(out_dir, ignore_errors=True)
    os.replace(tmp_dir, out_dir)
    return rows


def _setup(con, lake, exclusions, aliases, tz):
    """Views over bronze, the helper macro, and the override tables. Returns the set of bronze
    sources that exist, so a table whose input is missing is skipped rather than failing."""
    con.execute(f"CREATE MACRO to_local(ts) AS timezone('{tz}', timezone('UTC', ts))")
    have = set()
    for name in (
        "device_history",
        "household_events",
        "smarthome_sensor_history",
        "calendar_events",
    ):
        if _view(con, f"b_{name}", lake, "bronze", name):
            have.add(name)
    for name in ("user", "user_types", "device", "smarthome_devices", "environment"):
        if _view(con, f"snap_{name}", lake, "bronze", "_snapshots", name):
            have.add(f"snap_{name}")

    silver_contexts.setup(con, lake, have, tz)

    con.execute(
        "CREATE TABLE exclusions (source VARCHAR, event_type VARCHAR, subject_id VARCHAR, "
        "start_ts TIMESTAMP, end_ts TIMESTAMP)"
    )
    for row in exclusions:
        con.execute("INSERT INTO exclusions VALUES (?, ?, ?, ?, ?)", list(row))
    con.execute("CREATE TABLE sensor_aliases (id BIGINT, sensor_key VARCHAR)")
    for sid, key in aliases.items():
        con.execute("INSERT INTO sensor_aliases VALUES (?, ?)", [sid, key])

    if {"snap_user", "snap_user_types"} <= have:
        # The most recent snapshot only: a person's current name and type.
        con.execute(f"""CREATE VIEW persons AS
            SELECT u.id AS user_id, u.username, t.type AS user_type
            FROM (SELECT * FROM snap_user WHERE date = (SELECT MAX(date) FROM snap_user)) u
            JOIN (SELECT * FROM snap_user_types
                  WHERE date = (SELECT MAX(date) FROM snap_user_types)) t ON u.type = t.id
            WHERE t.type NOT IN ({_sql_list(NON_PERSON_USER_TYPES)})
              AND u.username NOT IN ({_sql_list(NON_PERSON_USERNAMES)})""")
        have.add("persons")
    return have


def _sql_list(values):
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


def _build_presence(con, lake, have, gap):
    """presence_intervals (per person, phone sightings) and device_sessions (per device)."""
    results = {}
    if "device_history" in have:
        con.execute(
            "CREATE TABLE collector_start AS "
            "SELECT MIN(timestamp) - INTERVAL 1 HOUR AS t FROM b_device_history"
        )
    if {"device_history", "persons"} <= have:
        types = ", ".join(str(t) for t in PERSONAL_DEVICE_TYPES)
        snapshot_part = (
            f"""UNION
            SELECT d.user_id, d.id AS device_id, d.last_online AS ts
            FROM (SELECT * FROM snap_device WHERE date = (SELECT MAX(date) FROM snap_device)) d
            JOIN persons p ON p.user_id = d.user_id
            WHERE d.device_type IN ({types}) AND d.last_online IS NOT NULL
              AND d.last_online >= (SELECT t FROM collector_start)"""
            if "snap_device" in have
            else ""
        )
        # Distinct last_online values are the sightings. The snapshot adds each phone's newest
        # sighting, which is not in device_history until the device row is next updated.
        con.execute(f"""CREATE TABLE sightings AS
            SELECT DISTINCT h.user_id, h.device_id, h.last_online AS ts
            FROM b_device_history h JOIN persons p ON p.user_id = h.user_id
            WHERE h.device_type IN ({types}) AND h.last_online IS NOT NULL
              AND h.last_online >= (SELECT t FROM collector_start)
            {snapshot_part}""")
        con.execute(f"""CREATE TABLE phone_islands AS
            WITH g AS (
              SELECT user_id, device_id, ts,
                     date_diff('second',
                       LAG(ts) OVER (PARTITION BY user_id ORDER BY ts, device_id), ts) / 60.0
                       AS gap_min
              FROM sightings),
            i AS (
              SELECT *, SUM(CASE WHEN gap_min > {gap} THEN 1 ELSE 0 END)
                          OVER (PARTITION BY user_id ORDER BY ts, device_id
                                ROWS UNBOUNDED PRECEDING) AS island
              FROM g)
            SELECT user_id, island, MIN(ts) AS start_utc, MAX(ts) AS end_utc,
                   COUNT(*) AS sightings, COUNT(DISTINCT device_id) AS devices,
                   SUM(CASE WHEN gap_min >= {AMBIGUOUS_GAP_MINUTES} AND gap_min <= {gap}
                            THEN 1 ELSE 0 END) AS short_gaps_merged
            FROM i GROUP BY user_id, island""")
        results["presence_intervals"] = """
            SELECT p.user_id, p.username, p.user_type, 'wifi_phone' AS source,
                   i.start_utc, i.end_utc,
                   to_local(i.start_utc) AS start_local, to_local(i.end_utc) AS end_local,
                   i.sightings, i.devices, i.short_gaps_merged
            FROM phone_islands i JOIN persons p ON p.user_id = i.user_id
            ORDER BY p.user_id, i.start_utc"""
    if "device_history" in have:
        con.execute(f"""CREATE TABLE device_islands AS
            WITH s AS (SELECT DISTINCT device_id, last_online AS ts FROM b_device_history
                       WHERE last_online IS NOT NULL
                         AND last_online >= (SELECT t FROM collector_start)),
            g AS (SELECT device_id, ts,
                         date_diff('second', LAG(ts) OVER (PARTITION BY device_id ORDER BY ts), ts)
                           / 60.0 AS gap_min FROM s),
            i AS (SELECT *, SUM(CASE WHEN gap_min > {gap} THEN 1 ELSE 0 END)
                              OVER (PARTITION BY device_id ORDER BY ts
                                    ROWS UNBOUNDED PRECEDING) AS island FROM g)
            SELECT device_id, island, MIN(ts) AS start_utc, MAX(ts) AS end_utc,
                   COUNT(*) AS sightings
            FROM i GROUP BY device_id, island""")
        con.execute("""CREATE TABLE device_latest AS
            SELECT device_id, arg_max(name, timestamp) AS name,
                   arg_max(user_id, timestamp) AS user_id,
                   arg_max(device_type, timestamp) AS device_type
            FROM b_device_history GROUP BY device_id""")
        results["device_sessions"] = """
            SELECT i.device_id, l.name, l.user_id, l.device_type,
                   i.start_utc, i.end_utc,
                   to_local(i.start_utc) AS start_local, to_local(i.end_utc) AS end_local,
                   i.sightings
            FROM device_islands i JOIN device_latest l USING (device_id)
            ORDER BY i.device_id, i.start_utc"""
    return results


def _build_silver_other(con, have):
    results = {}
    if "smarthome_sensor_history" in have:
        if "snap_smarthome_devices" in have:
            con.execute("""CREATE VIEW sensor_identity AS
                WITH latest AS (
                  SELECT id, arg_max(name, date) AS name, arg_max(source, date) AS source,
                         arg_max(esp_entity_id, date) AS esp, arg_max(ha_entity_id, date) AS ha,
                         arg_max(st_device_id, date) AS st
                  FROM snap_smarthome_devices GROUP BY id)
                SELECT id, CASE source
                         WHEN 'esphome' THEN split_part(esp, ':', 1) || ':' || name
                         ELSE source || ':' || COALESCE(ha, st, name) END AS sensor_key
                FROM latest""")
        else:
            con.execute(
                "CREATE VIEW sensor_identity AS "
                "SELECT NULL::BIGINT AS id, NULL::VARCHAR AS sensor_key WHERE false"
            )
        # An alias is a human decision about a retired id, so it wins over the snapshot.
        results["sensor_15m"] = """
            SELECT COALESCE(a.sensor_key, s.sensor_key,
                            'id:' || h.smarthome_device_id) AS sensor_key,
                   time_bucket(INTERVAL 15 MINUTE, h.recorded_at) AS bucket_utc,
                   to_local(time_bucket(INTERVAL 15 MINUTE, h.recorded_at)) AS bucket_local,
                   COUNT(*) AS n, AVG(h.value) AS mean, MIN(h.value) AS min, MAX(h.value) AS max
            FROM b_smarthome_sensor_history h
            LEFT JOIN sensor_aliases a ON a.id = h.smarthome_device_id
            LEFT JOIN sensor_identity s ON s.id = h.smarthome_device_id
            WHERE h.value IS NOT NULL
            GROUP BY ALL ORDER BY 1, 2"""
    if "household_events" in have:
        results["events_clean"] = """
            SELECT e.id, e.event_type, e.subject_type, e.subject_id, e.verb, e.message,
                   e.source_service, e.occurred_at AS occurred_utc,
                   to_local(e.occurred_at) AS occurred_local
            FROM b_household_events e
            WHERE NOT EXISTS (
              SELECT 1 FROM exclusions x
              WHERE x.source = 'household_events'
                AND e.occurred_at >= x.start_ts AND e.occurred_at < x.end_ts
                AND (x.event_type IS NULL OR x.event_type = e.event_type)
                AND (x.subject_id IS NULL OR x.subject_id = e.subject_id))
            ORDER BY e.occurred_at"""
    if "calendar_events" in have:
        # Busy intervals only: titles and notes are deliberately left behind in bronze.
        results["calendar_busy"] = """
            SELECT start_time AS start_utc, end_time AS end_utc,
                   to_local(start_time) AS start_local, to_local(end_time) AS end_local,
                   date_diff('minute', start_time, end_time) >= 23 * 60 AS all_day,
                   address IS NOT NULL AND address <> '' AS has_address,
                   conference_uri IS NOT NULL AS has_conference
            FROM b_calendar_events ORDER BY start_time"""
    return results


def _build_gold(con, have, lake):
    """Gold queries. Depend on silver tables materialised as views over what was just written."""
    results = {}
    silver = {t: Path(lake) / "silver" / t / "part-0.parquet" for t in SILVER_TABLES}
    for name, path in silver.items():
        if path.exists():
            con.execute(f"CREATE OR REPLACE VIEW s_{name} AS SELECT * FROM read_parquet('{path}')")

    if silver["presence_intervals"].exists() and "device_history" in have:
        # Hourly UTC buckets from each person's first sighting to the data horizon. `observed`
        # says whether the collector wrote anything that hour at all: a zero there is an outage
        # (device_history dropped ~30x in July 2026), not an absence.
        con.execute(f"""CREATE TABLE collector_hours AS
            WITH raw AS (SELECT time_bucket(INTERVAL 1 HOUR, timestamp) AS b, COUNT(*) AS n
                         FROM b_device_history GROUP BY 1)
            SELECT b, n, n >= {OBSERVED_MIN_FRACTION} * (SELECT MEDIAN(n) FROM raw) AS ok
            FROM raw""")
        con.execute("""CREATE TABLE horizon AS
            SELECT time_bucket(INTERVAL 1 HOUR, MAX(timestamp)) AS h FROM b_device_history""")
        con.execute("""CREATE TABLE person_hours AS
            SELECT user_id, username, UNNEST(generate_series(
                     time_bucket(INTERVAL 1 HOUR, MIN(start_utc)), (SELECT h FROM horizon),
                     INTERVAL 1 HOUR)) AS b
            FROM s_presence_intervals GROUP BY user_id, username""")
        con.execute("""CREATE TABLE home_minutes AS
            WITH e AS (
              SELECT user_id, start_utc, end_utc,
                     UNNEST(generate_series(time_bucket(INTERVAL 1 HOUR, start_utc),
                                            time_bucket(INTERVAL 1 HOUR, end_utc),
                                            INTERVAL 1 HOUR)) AS b
              FROM s_presence_intervals)
            SELECT user_id, b,
                   SUM(date_diff('second', GREATEST(start_utc, b),
                                 LEAST(end_utc, b + INTERVAL 1 HOUR)) / 60.0) AS minutes_home
            FROM e GROUP BY user_id, b""")
        results["presence_grid"] = """
            SELECT p.user_id, p.username, p.b AS bucket_utc,
                   CAST(to_local(p.b) AS DATE) AS date_local,
                   hour(to_local(p.b)) AS hour_local,
                   isodow(to_local(p.b)) - 1 AS dow_local,
                   COALESCE(m.minutes_home, 0) AS minutes_home,
                   -- The hour containing the newest collector row has not finished: nobody can
                   -- have accumulated a full hour in it yet, so it is not an observation.
                   COALESCE(c.ok, false) AND p.b < (SELECT h FROM horizon) AS observed
            FROM person_hours p
            LEFT JOIN home_minutes m ON m.user_id = p.user_id AND m.b = p.b
            LEFT JOIN collector_hours c ON c.b = p.b
            ORDER BY p.user_id, p.b"""

        # One row per person per local day (zero-filled), with first/last seen and the longest
        # absence between intervals inside the day.
        con.execute("""CREATE TABLE person_days AS
            SELECT user_id, username, UNNEST(generate_series(
                     CAST(to_local(MIN(start_utc)) AS DATE),
                     CAST(to_local((SELECT h FROM horizon)) AS DATE), INTERVAL 1 DAY))::DATE AS d
            FROM s_presence_intervals GROUP BY user_id, username""")
        con.execute("""CREATE TABLE clipped AS
            WITH e AS (
              SELECT user_id, start_local, end_local,
                     UNNEST(generate_series(CAST(start_local AS DATE), CAST(end_local AS DATE),
                                            INTERVAL 1 DAY))::DATE AS d
              FROM s_presence_intervals)
            SELECT user_id, d,
                   GREATEST(start_local, CAST(d AS TIMESTAMP)) AS s,
                   LEAST(end_local, CAST(d AS TIMESTAMP) + INTERVAL 1 DAY) AS e
            FROM e""")
        con.execute("""CREATE TABLE observed_days AS
            SELECT CAST(to_local(b) AS DATE) AS d, COUNT(*) AS hours
            FROM collector_hours WHERE ok GROUP BY 1""")
        results["daily_rhythm"] = f"""
            WITH gaps AS (
              SELECT user_id, d, s, e,
                     date_diff('minute', LAG(e) OVER (PARTITION BY user_id, d ORDER BY s), s) AS gap
              FROM clipped),
            agg AS (
              SELECT user_id, d, MIN(s) AS first_seen_local, MAX(e) AS last_seen_local,
                     COUNT(*) AS n_intervals,
                     SUM(date_diff('second', s, e)) / 60.0 AS minutes_home,
                     MAX(gap) AS longest_absence_min
              FROM gaps GROUP BY user_id, d)
            SELECT p.user_id, p.username, p.d AS date_local, isodow(p.d) - 1 AS dow_local,
                   a.first_seen_local, a.last_seen_local,
                   COALESCE(a.n_intervals, 0) AS n_intervals,
                   COALESCE(a.minutes_home, 0) AS minutes_home,
                   a.longest_absence_min,
                   COALESCE(o.hours, 0) AS observed_hours,
                   COALESCE(o.hours, 0) >= {OBSERVED_MIN_HOURS_PER_DAY} AS observed
            FROM person_days p
            LEFT JOIN agg a ON a.user_id = p.user_id AND a.d = p.d
            LEFT JOIN observed_days o ON o.d = p.d
            ORDER BY p.user_id, p.d"""

    if silver["events_clean"].exists():
        # Sparse: only hours with at least one event. A learner zero-fills against the data
        # horizon (see presence_grid.observed).
        results["hourly_rates"] = """
            SELECT event_type || '/' || COALESCE(subject_type, '-') || '/' || COALESCE(verb, '-')
                     AS signal,
                   time_bucket(INTERVAL 1 HOUR, occurred_utc) AS bucket_utc,
                   CAST(to_local(time_bucket(INTERVAL 1 HOUR, occurred_utc)) AS DATE) AS date_local,
                   hour(to_local(time_bucket(INTERVAL 1 HOUR, occurred_utc))) AS hour_local,
                   COUNT(*) AS n
            FROM s_events_clean GROUP BY ALL ORDER BY 1, 2"""
    if silver["sensor_15m"].exists():
        results["sensor_hourly"] = """
            SELECT sensor_key, time_bucket(INTERVAL 1 HOUR, bucket_utc) AS bucket_utc,
                   CAST(to_local(time_bucket(INTERVAL 1 HOUR, bucket_utc)) AS DATE) AS date_local,
                   hour(to_local(time_bucket(INTERVAL 1 HOUR, bucket_utc))) AS hour_local,
                   SUM(n) AS n, SUM(mean * n) / SUM(n) AS mean, MIN(min) AS min, MAX(max) AS max
            FROM s_sensor_15m GROUP BY ALL ORDER BY 1, 2"""
    return results


def build(lake_dir=None, exclusions=(), aliases=None, tz=None, gap_minutes=None, progress=None,
          today=None):  # fmt: skip
    """Rebuild every silver then every gold table from bronze. Returns {table: rows}."""
    lake = lake_dir or LAKE_DIR
    tz = tz or TIMEZONE
    gap = gap_minutes or PRESENCE_GAP_MINUTES
    con = duckdb.connect()
    counts = {}
    try:
        have = _setup(con, lake, exclusions, aliases or {}, tz)
        queries = _build_presence(con, lake, have, gap)
        queries.update(_build_silver_other(con, have))
        queries.update(silver_contexts.build_ha(con, have))
        queries.update(silver_contexts.build_weather(con, have))
        queries.update(silver_contexts.build_email(con, have))
        queries.update(silver_contexts.build_deck(con, have))
        for table in SILVER_TABLES:
            if table in queries:
                counts[table] = _write(con, queries[table], "silver", table, lake)
                if progress:
                    progress()
        # day_context is generated, not queried: a date spine from the earliest bronze day.
        spine_start = _earliest_day(con, have)
        if spine_start:
            end = (today or datetime.now(timezone.utc).date()) + timedelta(days=1)
            rows = day_context_rows(spine_start, end, _location(con, have))
            con.register("dc", pa.Table.from_pylist(rows, schema=DAY_CONTEXT_SCHEMA))
            counts["day_context"] = _write(
                con,
                "SELECT *, to_local(sunrise_utc) AS sunrise_local, "
                "to_local(sunset_utc) AS sunset_local FROM dc",
                "silver",
                "day_context",
                lake,
            )
        gold = _build_gold(con, have, lake)
        for table in GOLD_TABLES:
            if table in gold:
                counts[table] = _write(con, gold[table], "gold", table, lake)
                if progress:
                    progress()
        # Second gold pass: tables that read other gold / silver tables, so they go through views
        # over the Parquet just written (s_* silver, g_* gold).
        _register_views(con, lake)
        more = silver_contexts.build_gold(con, have)
        for table in GOLD_TABLES:
            if table in more:
                counts[table] = _write(con, more[table], "gold", table, lake)
                if progress:
                    progress()
    finally:
        con.close()
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "timezone": tz,
        "presence_gap_minutes": gap,
        "personal_device_types": list(PERSONAL_DEVICE_TYPES),
        "rows": counts,
    }
    (Path(lake) / "silver").mkdir(parents=True, exist_ok=True)
    (Path(lake) / "silver" / "_build.json").write_text(json.dumps(meta, indent=2))
    logger.info(f"silver/gold built: {counts}")
    return counts


def _location(con, have):
    """(latitude, longitude) of the household from the newest environment snapshot, or None."""
    if "snap_environment" not in have:
        return None
    row = con.execute(
        "SELECT latitude, longitude FROM snap_environment "
        "WHERE date = (SELECT MAX(date) FROM snap_environment) LIMIT 1"
    ).fetchone()
    if not row or row[0] is None or row[1] is None:
        return None
    return float(row[0]), float(row[1])


def _register_views(con, lake):
    """Views over every silver (s_*) and gold (g_*) table already written."""
    for layer, prefix, tables in (
        ("silver", "s", SILVER_TABLES),
        ("gold", "g", GOLD_TABLES),
    ):
        for table in tables:
            path = Path(lake) / layer / table / "part-0.parquet"
            if path.exists():
                con.execute(
                    f"CREATE OR REPLACE VIEW {prefix}_{table} AS "
                    f"SELECT * FROM read_parquet('{path}')"
                )


def _earliest_day(con, have):
    days = []
    if "device_history" in have:
        days.append(
            con.execute("SELECT MIN(CAST(timestamp AS DATE)) FROM b_device_history").fetchone()[0]
        )
    if "household_events" in have:
        days.append(
            con.execute("SELECT MIN(CAST(occurred_at AS DATE)) FROM b_household_events").fetchone()[
                0
            ]
        )
    days = [d for d in days if d]
    return min(days) if days else None


def _connect():
    return pymysql.connect(
        host=os.environ.get("MYSQL_DATABASE"),
        user=os.environ.get("MYSQL_USER"),
        passwd=os.environ.get("MYSQL_PSWD"),
        db=os.environ.get("MYSQL_NAME"),
    )


def run_build(lake_dir=None, progress=None):
    """Nightly job: read the overrides from MySQL, then rebuild silver and gold."""
    conn = _connect()
    try:
        exclusions, aliases = load_overrides(conn)
    finally:
        conn.close()
    return build(lake_dir, exclusions, aliases, progress=progress)


if __name__ == "__main__":
    logging.basicConfig(
        stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(name)s - %(message)s"
    )
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    if command == "build":
        print(run_build())
    else:
        print("usage: python -m sa.silver build")
        sys.exit(2)
