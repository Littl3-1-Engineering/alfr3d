"""Silver and gold for the contexts LF-0b added to the lake (LF-2b,
todo/sa/todo_signal_inventory.md): Home Assistant states, outdoor weather, email, daylight, and the
hourly "context" table every learner joins to.

silver.py builds people, devices, sensors, events and the calendar. This module covers what arrived
afterwards, and reuses its connection, its `to_local()` macro and its atomic writer.

Silver (new)
    ha_states        every Home Assistant state change, parsed (numeric value, unavailable flag,
                     midnight-anchor flag), local time
    ha_intervals     the same as "state held from t1 to t2", consecutive identical states merged.
                     The shape most learners want: an entity that has not changed since Tuesday is
                     still held now, which a list of changes cannot say
    ha_entities      a dictionary: kind (numeric / categorical / metadata / unavailable), how many
                     points, first and last seen, friendly name
    weather_hourly   outdoor conditions by hour at the household's location, from ALFR3D's own
                     get_weather() record (environment_history). NOT from Home Assistant: see below
    email_events     email metadata with local time and Gmail's category

Gold (new)
    scalar_hourly    one shape for every numeric series (ESPHome sensors and Home Assistant
                     entities): time-weighted hourly mean / min / max and the fraction of the hour
                     actually covered
    state_hourly     minutes spent in each state per hour, for every categorical entity
    email_hourly     messages per hour, zero-filled, with category and sender counts
    sender_daily     messages per sender per local day (email and phone notifications)
    context_hourly   one row per hour: time of day, weekday, season, holiday, daylight, outdoor
                     weather, calendar busy minutes, how many people were home. The covariates for
                     every learner ("unusual for a Tuesday evening in October with this weather")

Why intervals and not just changes: sensors report on change. A series cannot be averaged by hour,
or conditioned on, without knowing the value *between* reports. So every entity becomes intervals
bounded by the source's last successful export (`lake.write_horizon`), and hourly values are
time-weighted.

Home Assistant describes the old house. HA's configured home is still Novi Sad, Serbia
(45.24 N, 19.81 E, Europe/Belgrade); ALFR3D has the household in Etobicoke, Canada. HA's
OpenWeatherMap entities, its `sun` entities, `zone.home` and its device trackers are therefore all
for the wrong place (checked 2026-10-10: 15.9 C and 62 % humidity in HA while ALFR3D recorded 19.9 C
and 40 % in Etobicoke at the same moment). They stay in the lake and in ha_states, flagged
`describes_ha_home` in ha_entities, but are never used as the household's context. The fix is in
Home Assistant (set its home location); `_ha_config.json` in the bronze table records the location
HA reports and any later change, so the two regimes can be told apart.

Assumptions, stated so a violation is easy to spot:
- Midnight-stamped points are Home Assistant's start-of-window anchors, not real changes (HA stamps
  the state in effect at the start of a requested window at that start). A real change at exactly
  00:00:00.000000 is vanishingly unlikely; anchors are flagged, not dropped, because they carry the
  state of entities that never change.
- Daylight comes from the NOAA solar equations at the household's coordinates (environment
  snapshot), accurate to a couple of minutes, which is ample for "is it light outside".
"""

import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from sa import lake

# --- Daylight --------------------------------------------------------------------------------


def sun_times(day, lat, lon):
    """(sunrise_utc, sunset_utc) as naive UTC datetimes for a date at a latitude / longitude (east
    positive), by the NOAA solar-position equations. (None, None) in polar day or night. The sunset
    of a western-hemisphere date falls on the next UTC day, which is correct."""
    jd = day.toordinal() - date(2000, 1, 1).toordinal() + 2451544.5 + 0.5  # noon UTC
    t = (jd - 2451545.0) / 36525.0
    rad = math.radians
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = (
        math.sin(rad(m)) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(rad(2 * m)) * (0.019993 - 0.000101 * t)
        + math.sin(rad(3 * m)) * 0.000289
    )
    omega = 125.04 - 1934.136 * t
    app_long = l0 + c - 0.00569 - 0.00478 * math.sin(rad(omega))
    seconds = 21.448 - t * (46.8150 + t * (0.00059 - t * 0.001813))
    obliq = 23 + (26 + seconds / 60) / 60 + 0.00256 * math.cos(rad(omega))
    decl = math.degrees(math.asin(math.sin(rad(obliq)) * math.sin(rad(app_long))))
    y = math.tan(rad(obliq / 2)) ** 2
    eq_time = 4 * math.degrees(
        y * math.sin(2 * rad(l0))
        - 2 * e * math.sin(rad(m))
        + 4 * e * y * math.sin(rad(m)) * math.cos(2 * rad(l0))
        - 0.5 * y * y * math.sin(4 * rad(l0))
        - 1.25 * e * e * math.sin(2 * rad(m))
    )
    cos_ha = math.cos(rad(90.833)) / (math.cos(rad(lat)) * math.cos(rad(decl))) - math.tan(
        rad(lat)
    ) * math.tan(rad(decl))
    if abs(cos_ha) > 1:
        return None, None
    hour_angle = math.degrees(math.acos(cos_ha))
    noon_minutes = 720 - 4 * lon - eq_time
    midnight = datetime.combine(day, datetime.min.time())
    return (
        midnight + timedelta(minutes=noon_minutes - 4 * hour_angle),
        midnight + timedelta(minutes=noon_minutes + 4 * hour_angle),
    )


# --- Classification of Home Assistant entities -------------------------------------------------

# Entities that are neither a usable number nor a usable state: ISO timestamps (the sun's "next
# dawn"), version strings, uptime, enumerated codes. Kept in ha_states, left out of the hourly
# series.
METADATA_ENTITIES = re.compile(
    r"weather_code|forecast_time|sun_next_|current_version|sensor\.uptime|precipitation_kind",
    re.IGNORECASE,
)
# An entity unavailable more than this share of the time carries no state worth learning.
UNAVAILABLE_SHARE_LIMIT = 0.9
# How long a weather reading is carried forward before the hour is left empty.
MAX_WEATHER_AGE_HOURS = 6
# Share of its available intervals that must parse as numbers for an entity to count as numeric.
NUMERIC_SHARE_MIN = 0.8

# Entities computed for Home Assistant's configured home, which is not where the household is.
HA_HOME_ENTITIES = re.compile(
    r"openweathermap|^sun\.|sensor\.sun_|^weather\.|^zone\.|^device_tracker\.|^person\.",
    re.IGNORECASE,
)


def _sql_str(value):
    return "'" + str(value).replace("'", "''") + "'"


def setup(con, lake_dir, have, tz):
    """Views over the new bronze tables and the data horizons. Adds what exists to `have`."""
    bronze = Path(lake_dir) / "bronze"
    for name in ("ha_state_history", "email_messages", "environment_history"):
        if list((bronze / name).glob("*/part-*.parquet")):
            pattern = f"{bronze / name}/*/part-*.parquet"
            con.execute(
                f"CREATE VIEW b_{name} AS SELECT * FROM read_parquet('{pattern}', "
                "hive_partitioning=true, union_by_name=true)"
            )
            have.add(name)
    _ha_home_check(con, bronze, have)
    # The moment each external source was last exported (fallback: its newest data point).
    for name, column in (("ha_state_history", "last_updated"), ("email_messages", "received_utc")):
        if name not in have:
            continue
        horizon = lake.read_horizon(bronze / name)
        if horizon is None:
            horizon = con.execute(f"SELECT MAX({column}) FROM b_{name}").fetchone()[0]
        con.execute(f"CREATE TABLE horizon_{name} AS SELECT TIMESTAMP '{horizon}' AS h")


# --- Silver ----------------------------------------------------------------------------------


def _haversine_km(lat1, lon1, lat2, lon2):
    rad = math.radians
    a = (
        math.sin(rad(lat2 - lat1) / 2) ** 2
        + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(rad(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _ha_home_check(con, bronze, have):
    """ha_home_check: where Home Assistant thinks home is, and how far that is from where ALFR3D
    puts the household. One row; NULLs when either is unknown."""
    ha = None
    try:
        ha = json.loads((bronze / "ha_state_history" / "_ha_config.json").read_text())["current"]
    except (OSError, ValueError, KeyError):
        pass
    household = None
    if "snap_environment" in have:
        household = con.execute(
            "SELECT latitude, longitude FROM snap_environment "
            "WHERE date = (SELECT MAX(date) FROM snap_environment) LIMIT 1"
        ).fetchone()
    distance = None
    if ha and household and None not in (ha.get("latitude"), ha.get("longitude"), *household):
        distance = _haversine_km(
            float(ha["latitude"]), float(ha["longitude"]), float(household[0]), float(household[1])
        )
    con.execute("CREATE TABLE ha_home_check (distance_km DOUBLE, ha_name VARCHAR, ha_tz VARCHAR)")
    con.execute(
        "INSERT INTO ha_home_check VALUES (?, ?, ?)",
        [distance, (ha or {}).get("location_name"), (ha or {}).get("time_zone")],
    )


def build_ha(con, have):
    """Home Assistant tables. Materialises ha_events, ha_intervals, ha_entities (plus the hourly
    series gold reuses) and returns the silver queries to write."""
    if "ha_state_history" not in have:
        return {}
    con.execute("""CREATE TABLE ha_events AS
        SELECT entity_id, domain, state, last_changed AS changed_utc,
               strftime(last_changed, '%H:%M:%S.%f') = '00:00:00.000000' AS is_anchor
        FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY entity_id, last_changed
                                           ORDER BY last_updated DESC) AS rn
              FROM b_ha_state_history)
        WHERE rn = 1""")
    # Consecutive identical states merge into one held interval. Each interval ends where the next
    # one begins, and the last ends at the source's export horizon.
    con.execute("""CREATE TABLE ha_intervals AS
        WITH ordered AS (
          SELECT *, LAG(state) OVER w AS prev_state,
                 COALESCE(LEAD(changed_utc) OVER w, (SELECT h FROM horizon_ha_state_history))
                   AS next_change
          FROM ha_events WINDOW w AS (PARTITION BY entity_id ORDER BY changed_utc)),
        marked AS (
          SELECT *, SUM(CASE WHEN prev_state IS NULL OR prev_state <> state THEN 1 ELSE 0 END)
                      OVER (PARTITION BY entity_id ORDER BY changed_utc
                            ROWS UNBOUNDED PRECEDING) AS island
          FROM ordered)
        SELECT entity_id, ANY_VALUE(domain) AS domain, state,
               CASE WHEN isfinite(TRY_CAST(state AS DOUBLE)) THEN TRY_CAST(state AS DOUBLE) END
                 AS value,
               state IN ('unavailable', 'unknown') AS is_unavailable,
               MIN(changed_utc) AS start_utc,
               GREATEST(MAX(next_change), MIN(changed_utc)) AS end_utc,
               COUNT(*) AS n_points, BOOL_OR(NOT is_anchor) AS has_real_change
        FROM marked GROUP BY entity_id, island, state""")
    con.execute(f"""CREATE TABLE ha_entities AS
        WITH per AS (
          SELECT entity_id, ANY_VALUE(domain) AS domain, COUNT(*) AS n_intervals,
                 SUM(n_points) AS n_points, COUNT(DISTINCT state) AS n_distinct_states,
                 MIN(start_utc) AS first_seen, MAX(end_utc) AS last_seen,
                 SUM(CASE WHEN is_unavailable THEN epoch(end_utc) - epoch(start_utc) ELSE 0 END)
                   / NULLIF(SUM(epoch(end_utc) - epoch(start_utc)), 0) AS unavailable_share,
                 SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END) AS n_numeric,
                 SUM(CASE WHEN NOT is_unavailable THEN 1 ELSE 0 END) AS n_available
          FROM ha_intervals GROUP BY entity_id)
        SELECT p.entity_id, p.domain,
               CASE WHEN regexp_matches(p.entity_id, '{METADATA_ENTITIES.pattern}', 'i')
                         THEN 'metadata'
                    WHEN COALESCE(p.unavailable_share, 0) > {UNAVAILABLE_SHARE_LIMIT}
                         THEN 'unavailable'
                    WHEN p.n_available > 0 AND p.n_numeric >= {NUMERIC_SHARE_MIN} * p.n_available
                         THEN 'numeric'
                    ELSE 'categorical' END AS kind,
               p.n_intervals, p.n_points, p.n_distinct_states, p.first_seen, p.last_seen,
               p.unavailable_share, p.entity_id LIKE '%forecast%' AS is_forecast
        FROM per p ORDER BY p.entity_id""")

    # Hourly, time-weighted. A held value covers the hours it spans in proportion to the time held.
    con.execute("""CREATE TABLE ha_hour_overlaps AS
        WITH spans AS (
          SELECT i.entity_id, e.kind, i.state, i.value, i.is_unavailable, i.start_utc, i.end_utc,
                 UNNEST(generate_series(
                   time_bucket(INTERVAL 1 HOUR, i.start_utc),
                   time_bucket(INTERVAL 1 HOUR,
                               GREATEST(i.end_utc - INTERVAL 1 MICROSECOND, i.start_utc)),
                   INTERVAL 1 HOUR)) AS bucket_utc
          FROM ha_intervals i JOIN ha_entities e USING (entity_id)
          WHERE e.kind IN ('numeric', 'categorical'))
        SELECT entity_id, kind, state, value, is_unavailable, bucket_utc,
               epoch(LEAST(end_utc, bucket_utc + INTERVAL 1 HOUR))
                 - epoch(GREATEST(start_utc, bucket_utc)) AS seconds
        FROM spans""")
    con.execute("""CREATE TABLE ha_hourly_numeric AS
        SELECT entity_id, bucket_utc,
               SUM(value * seconds) / SUM(seconds) AS mean, MIN(value) AS min, MAX(value) AS max,
               LEAST(1.0, SUM(seconds) / 3600.0) AS coverage
        FROM ha_hour_overlaps
        WHERE kind = 'numeric' AND NOT is_unavailable AND value IS NOT NULL AND seconds > 0
        GROUP BY entity_id, bucket_utc""")
    con.execute("""CREATE TABLE ha_hourly_state AS
        SELECT entity_id, bucket_utc, state, SUM(seconds) / 60.0 AS minutes
        FROM ha_hour_overlaps WHERE kind = 'categorical' AND seconds > 0
        GROUP BY entity_id, bucket_utc, state""")

    names_join = (
        "LEFT JOIN (SELECT ha_entity_id, arg_max(name, date) AS name "
        "FROM snap_smarthome_devices GROUP BY ha_entity_id) d ON d.ha_entity_id = e.entity_id"
        if "snap_smarthome_devices" in have
        else ""
    )
    queries = {
        "ha_states": """
            SELECT entity_id, domain, state,
                   CASE WHEN isfinite(TRY_CAST(state AS DOUBLE)) THEN TRY_CAST(state AS DOUBLE)
                   END AS value,
                   state IN ('unavailable', 'unknown') AS is_unavailable, is_anchor, changed_utc,
                   to_local(changed_utc) AS changed_local
            FROM ha_events ORDER BY entity_id, changed_utc""",
        "ha_intervals": """
            SELECT entity_id, domain, state, value, is_unavailable, start_utc, end_utc,
                   to_local(start_utc) AS start_local, to_local(end_utc) AS end_local,
                   n_points, has_real_change
            FROM ha_intervals ORDER BY entity_id, start_utc""",
        "ha_entities": f"""
            SELECT e.*,
                   regexp_matches(e.entity_id, '{HA_HOME_ENTITIES.pattern}', 'i')
                     AS describes_ha_home,
                   c.distance_km AS ha_home_distance_km, c.ha_name AS ha_home_name,
                   {"d.name" if "snap_smarthome_devices" in have else "NULL::VARCHAR"}
                     AS friendly_name
            FROM ha_entities e CROSS JOIN ha_home_check c
            {names_join}
            ORDER BY e.entity_id""",
    }
    return queries


def build_weather(con, have):
    """weather_hourly from ALFR3D's own get_weather() record (environment_history), forward-filled
    to the hour for up to MAX_WEATHER_AGE_HOURS. Not Home Assistant's: see the module docstring."""
    if "environment_history" not in have:
        return {}
    # The last reading is carried forward for up to MAX_WEATHER_AGE_HOURS, but never past the lake's
    # data horizon (the newest device_history row, when there is one): hours that have not happened
    # yet must not get an "observation".
    horizon = (
        "(SELECT MAX(timestamp) FROM b_device_history)"
        if "device_history" in have
        else f"MAX(recorded_at) + INTERVAL {MAX_WEATHER_AGE_HOURS} HOUR"
    )
    con.execute(f"""CREATE TABLE weather_hours AS
        SELECT b AS bucket_utc, b + INTERVAL 1 HOUR AS hour_end
        FROM (SELECT UNNEST(generate_series(
                       time_bucket(INTERVAL 1 HOUR, MIN(recorded_at)),
                       time_bucket(INTERVAL 1 HOUR,
                                   LEAST(MAX(recorded_at) + INTERVAL {MAX_WEATHER_AGE_HOURS} HOUR,
                                         {horizon})),
                       INTERVAL 1 HOUR)) AS b
              FROM b_environment_history WHERE kind = 'weather')""")
    return {"weather_hourly": f"""
            SELECT h.bucket_utc, to_local(h.bucket_utc) AS bucket_local,
                   e.temperature AS temperature_c, e.humidity AS humidity_pct,
                   e.pressure AS pressure_hpa, e.wind AS wind_kmh, e.wind_dir,
                   e.description, e.low AS low_c, e.high AS high_c,
                   epoch(h.hour_end - e.recorded_at) / 60.0 AS age_minutes,
                   'environment_history' AS source
            FROM weather_hours h
            ASOF LEFT JOIN (SELECT * FROM b_environment_history WHERE kind = 'weather') e
              ON h.hour_end >= e.recorded_at
            WHERE (h.hour_end - e.recorded_at) <= INTERVAL {MAX_WEATHER_AGE_HOURS} HOUR
            ORDER BY h.bucket_utc"""}


def build_email(con, have):
    if "email_messages" not in have:
        return {}
    return {"email_events": """
            SELECT message_id, thread_id, received_utc, to_local(received_utc) AS received_local,
                   sender_name, sender_email, sender_domain, subject, labels, is_unread,
                   labels LIKE '%INBOX%' AS in_inbox,
                   CASE WHEN labels LIKE '%CATEGORY_PROMOTIONS%' THEN 'promotions'
                        WHEN labels LIKE '%CATEGORY_UPDATES%' THEN 'updates'
                        WHEN labels LIKE '%CATEGORY_SOCIAL%' THEN 'social'
                        WHEN labels LIKE '%CATEGORY_FORUMS%' THEN 'forums'
                        WHEN labels LIKE '%CATEGORY_PERSONAL%' THEN 'personal'
                        ELSE 'uncategorised' END AS category,
                   size_estimate
            FROM b_email_messages ORDER BY received_utc"""}


# --- Gold ------------------------------------------------------------------------------------


def build_gold(con, have):
    """The second gold pass: tables that read other gold / silver tables (views `s_*` and `g_*`
    over the Parquet already written) plus the hourly series built during silver."""
    queries = {}
    if "ha_state_history" in have:
        queries["state_hourly"] = """
            SELECT 'ha:' || entity_id AS series_key, bucket_utc,
                   CAST(to_local(bucket_utc) AS DATE) AS date_local,
                   hour(to_local(bucket_utc)) AS hour_local, state, minutes
            FROM ha_hourly_state ORDER BY series_key, bucket_utc, state"""
    parts = []
    if "ha_state_history" in have:
        parts.append("""
            SELECT 'ha:' || entity_id AS series_key, 'homeassistant' AS source, bucket_utc,
                   mean, min, max, coverage FROM ha_hourly_numeric""")
    if con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'g_sensor_hourly'"
    ).fetchone()[0]:
        # ESPHome sensors report about every 15 minutes: four readings cover an hour.
        parts.append("""
            SELECT 'esphome:' || sensor_key AS series_key, 'esphome' AS source, bucket_utc,
                   mean, min, max, LEAST(1.0, n / 4.0) AS coverage FROM g_sensor_hourly""")
    if parts:
        queries["scalar_hourly"] = f"""
            SELECT series_key, source, bucket_utc,
                   CAST(to_local(bucket_utc) AS DATE) AS date_local,
                   hour(to_local(bucket_utc)) AS hour_local,
                   isodow(to_local(bucket_utc)) - 1 AS dow_local,
                   mean, min, max, coverage
            FROM ({" UNION ALL ".join(parts)}) ORDER BY series_key, bucket_utc"""

    if "email_messages" in have:
        queries["email_hourly"] = """
            WITH spine AS (
              SELECT UNNEST(generate_series(time_bucket(INTERVAL 1 HOUR, MIN(received_utc)),
                       time_bucket(INTERVAL 1 HOUR,
                                   GREATEST(MAX(received_utc),
                                            (SELECT h FROM horizon_email_messages))),
                       INTERVAL 1 HOUR)) AS bucket_utc
              FROM s_email_events),
            hourly AS (
              SELECT time_bucket(INTERVAL 1 HOUR, received_utc) AS bucket_utc, COUNT(*) AS n,
                     SUM(is_unread::INT) AS n_unread,
                     SUM((category = 'promotions')::INT) AS n_promotions,
                     SUM((category = 'updates')::INT) AS n_updates,
                     SUM((category = 'social')::INT) AS n_social,
                     SUM(in_inbox::INT) AS n_inbox, COUNT(DISTINCT sender_email) AS distinct_senders
              FROM s_email_events GROUP BY 1)
            SELECT s.bucket_utc, CAST(to_local(s.bucket_utc) AS DATE) AS date_local,
                   hour(to_local(s.bucket_utc)) AS hour_local,
                   isodow(to_local(s.bucket_utc)) - 1 AS dow_local,
                   COALESCE(h.n, 0) AS n, COALESCE(h.n_unread, 0) AS n_unread,
                   COALESCE(h.n_promotions, 0) AS n_promotions,
                   COALESCE(h.n_updates, 0) AS n_updates, COALESCE(h.n_social, 0) AS n_social,
                   COALESCE(h.n_inbox, 0) AS n_inbox,
                   COALESCE(h.distinct_senders, 0) AS distinct_senders
            FROM spine s LEFT JOIN hourly h USING (bucket_utc) ORDER BY s.bucket_utc"""

    sender_parts = []
    if "email_messages" in have:
        sender_parts.append("""
            SELECT 'gmail' AS source, sender_email AS sender, sender_domain AS domain,
                   CAST(received_local AS DATE) AS date_local, COUNT(*) AS n
            FROM s_email_events GROUP BY ALL""")
    if con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 's_events_clean'"
    ).fetchone()[0]:
        sender_parts.append("""
            SELECT 'notification:' || verb AS source, subject_id AS sender, NULL::VARCHAR AS domain,
                   CAST(occurred_local AS DATE) AS date_local, COUNT(*) AS n
            FROM s_events_clean
            WHERE event_type = 'notification' AND subject_type = 'sender' GROUP BY ALL""")
    if sender_parts:
        queries["sender_daily"] = (
            f"SELECT * FROM ({' UNION ALL '.join(sender_parts)}) "
            "ORDER BY source, sender, date_local"
        )

    has_grid = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'g_presence_grid'"
    ).fetchone()[0]
    has_day = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 's_day_context'"
    ).fetchone()[0]
    if has_grid and has_day:
        has_weather = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 's_weather_hourly'"
        ).fetchone()[0]
        has_calendar = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 's_calendar_busy'"
        ).fetchone()[0]
        if has_calendar:
            con.execute("""CREATE TABLE calendar_hourly AS
                WITH e AS (
                  SELECT start_utc, end_utc,
                         UNNEST(generate_series(time_bucket(INTERVAL 1 HOUR, start_utc),
                                time_bucket(INTERVAL 1 HOUR, end_utc), INTERVAL 1 HOUR)) AS b
                  FROM s_calendar_busy WHERE NOT all_day)
                SELECT b AS bucket_utc,
                       SUM(GREATEST(0, epoch(LEAST(end_utc, b + INTERVAL 1 HOUR))
                                       - epoch(GREATEST(start_utc, b)))) / 60.0 AS busy_minutes
                FROM e GROUP BY b""")
        weather_cols = (
            "w.temperature_c AS outdoor_temp_c, w.humidity_pct AS outdoor_humidity_pct, "
            "w.pressure_hpa AS outdoor_pressure_hpa, w.description AS outdoor_condition"
            if has_weather
            else "NULL::DOUBLE AS outdoor_temp_c, NULL::DOUBLE AS outdoor_humidity_pct, "
            "NULL::DOUBLE AS outdoor_pressure_hpa, NULL::VARCHAR AS outdoor_condition"
        )
        queries["context_hourly"] = f"""
            WITH people AS (
              SELECT bucket_utc, BOOL_OR(observed) AS observed,
                     SUM((minutes_home >= 30)::INT) AS people_home
              FROM g_presence_grid GROUP BY bucket_utc),
            spine AS (
              SELECT UNNEST(generate_series(MIN(bucket_utc), MAX(bucket_utc), INTERVAL 1 HOUR))
                       AS bucket_utc
              FROM people)
            SELECT s.bucket_utc, to_local(s.bucket_utc) AS bucket_local,
                   CAST(to_local(s.bucket_utc) AS DATE) AS date_local,
                   hour(to_local(s.bucket_utc)) AS hour_local, d.dow AS dow_local,
                   d.is_weekend, d.is_holiday, d.holiday_name, d.month, d.season,
                   CASE WHEN d.sunrise_utc IS NOT NULL
                        THEN (s.bucket_utc + INTERVAL 30 MINUTE)
                             BETWEEN d.sunrise_utc AND d.sunset_utc
                   END AS is_daylight,
                   {weather_cols},
                   {"COALESCE(c.busy_minutes, 0)" if has_calendar else "NULL::DOUBLE"}
                     AS calendar_busy_minutes,
                   CASE WHEN p.observed THEN p.people_home END AS people_home
            FROM spine s
            LEFT JOIN s_day_context d ON d.date = CAST(to_local(s.bucket_utc) AS DATE)
            {"LEFT JOIN s_weather_hourly w ON w.bucket_utc = s.bucket_utc" if has_weather else ""}
            {"LEFT JOIN calendar_hourly c ON c.bucket_utc = s.bucket_utc" if has_calendar else ""}
            LEFT JOIN people p ON p.bucket_utc = s.bucket_utc
            ORDER BY s.bucket_utc"""
    return queries
