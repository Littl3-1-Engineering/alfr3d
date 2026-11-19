"""Context registry (Timeline "Context learning 2/5", todo/sa/todo_lf8_context_registry.md).

Every context feature the lake offers a learner is declared once, here, and everything downstream
is generated from the declaration:

    registration  ->  gold `context_features` (long form: one row per feature per hour)
                  ->  gold `context_hourly`   (the wide table every learner joins to, a pivot of it)
                  ->  `sa.ledger`             (what is captured, since when, how well, who reads it)
                  ->  `learner_candidates()`  (what a learner is allowed to see, by privacy scope)

Adding a signal is one `Feature(...)` in `REGISTRY` (or, for a new source table, one entry in
`JOINS` as well): no SQL elsewhere and no learner code changes. A feature is `value`, an SQL
expression over the aliases of the joins it names, evaluated per hourly bucket:

    s  the hour spine (bucket_utc)        d  s_day_context (calendar, season, sun)
    w  s_weather_hourly (outdoor)         c  calendar_hourly (busy minutes)
    p  people at home (from the presence grid)

`context_hourly` keeps exactly the columns it always had (names, order, values); only the way it
is built changed. Series families (ESPHome sensors, Home Assistant entities, Deck battery,
attention) already live long-form in `scalar_hourly`; they are registered as `SeriesFamily` so the
ledger and the privacy rules cover them too.

Privacy scope is enforced here, not trusted to callers: a feature scoped beyond what the owner has
opened (`restricted`, e.g. precise location) is registered and shows in the ledger, but
`learner_candidates()` never returns it and nothing builds it into `context_features`.

Stable identity: a series is named by what it IS (an ESPHome sensor is `host:name`, never a
`smarthome_devices` row id), so a power-cycled sensor is the same feature. See `sa/identity.py`.
"""

from dataclasses import dataclass

# --- Privacy scopes ----------------------------------------------------------------------------

HOUSEHOLD = "household"  # derived from sources the household already shares with itself
OWNER_OPENED = "owner_opened"  # only once the owner has opened it to learning
RESTRICTED = "restricted"  # registered and visible in the ledger, never exposed to a learner
SCOPES = (HOUSEHOLD, OWNER_OPENED, RESTRICTED)

KINDS = ("bool", "int", "float", "text")
# How each kind is cast back when `context_hourly` pivots the long form.
_PIVOT_CAST = {"bool": "BOOLEAN", "int": "BIGINT", "float": "DOUBLE", "text": None}
_NULL_OF = {
    "bool": "NULL::BOOLEAN",
    "int": "NULL::BIGINT",
    "float": "NULL::DOUBLE",
    "text": "NULL::VARCHAR",
}


@dataclass(frozen=True)
class Join:
    """A relation a feature's `value` may read. `requires` is the table that must exist for the
    join to be usable (None: always available)."""

    requires: str
    sql: str


JOINS = {
    "day": Join(
        "s_day_context",
        "LEFT JOIN s_day_context d ON d.date = CAST(to_local(s.bucket_utc) AS DATE)",
    ),
    "weather": Join(
        "s_weather_hourly", "LEFT JOIN s_weather_hourly w ON w.bucket_utc = s.bucket_utc"
    ),
    "calendar": Join(
        "calendar_hourly", "LEFT JOIN calendar_hourly c ON c.bucket_utc = s.bucket_utc"
    ),
    "people": Join(None, "LEFT JOIN people p ON p.bucket_utc = s.bucket_utc"),
}


@dataclass(frozen=True)
class Feature:
    """One context feature, declared once.

    key              the feature's stable name (also its `context_hourly` column when
                     `in_context_hourly`)
    kind             bool | int | float | text
    value            SQL expression over the aliases of `joins`; None registers a feature that is
                     known but not captured (the ledger says so)
    joins            names from JOINS the expression reads
    grain            what one value covers: "hour"
    lags             hours a covariate search may look back (a hint for the shared engine)
    coverage_floor   the least share of an hour that must be observed for it to count (None: a
                     derived feature with no notion of partial coverage)
    provenance       where the value comes from, in words, for the ledger
    retention_days   how long the SOURCE keeps it (None: unbounded or derived)
    privacy          one of SCOPES
    readers          learners / cards that read it today, verified by a test
    in_context_hourly  becomes a column of the wide table
    """

    key: str
    kind: str
    value: str = None
    joins: tuple = ()
    grain: str = "hour"
    lags: tuple = ()
    coverage_floor: float = None
    provenance: str = ""
    retention_days: int = None
    privacy: str = HOUSEHOLD
    readers: tuple = ()
    in_context_hourly: bool = True
    description: str = ""


@dataclass(frozen=True)
class SeriesFamily:
    """A family of numeric series that already live long-form in `scalar_hourly`, named by
    `prefix`. Registered for the ledger and the privacy rules."""

    prefix: str
    provenance: str
    identity: str
    retention_days: int = None
    privacy: str = HOUSEHOLD
    readers: tuple = ()
    coverage_floor: float = 0.5


# Order is the column order of `context_hourly`: it matches the table as it was before the
# registry, so the wide table's columns do not move.
REGISTRY = (
    Feature(
        "is_weekend",
        "bool",
        "d.is_weekend",
        ("day",),
        provenance="silver day_context (local calendar)",
        description="Saturday or Sunday, household-local",
    ),
    Feature(
        "is_holiday",
        "bool",
        "d.is_holiday",
        ("day",),
        provenance="silver day_context (Ontario statutory holidays)",
    ),
    Feature(
        "holiday_name",
        "text",
        "d.holiday_name",
        ("day",),
        provenance="silver day_context (Ontario statutory holidays)",
    ),
    Feature(
        "month",
        "int",
        "d.month",
        ("day",),
        provenance="silver day_context (local calendar)",
        description="Stays off every learner until about a year of history exists",
    ),
    Feature(
        "season",
        "text",
        "d.season",
        ("day",),
        provenance="silver day_context (local calendar)",
        description="Stays off every learner until about a year of history exists",
    ),
    Feature(
        "is_daylight",
        "bool",
        "CASE WHEN d.sunrise_utc IS NOT NULL "
        "THEN (s.bucket_utc + INTERVAL 30 MINUTE) BETWEEN d.sunrise_utc AND d.sunset_utc END",
        ("day",),
        provenance="NOAA solar equations at the household's coordinates (silver day_context)",
    ),
    Feature(
        "outdoor_temp_c",
        "float",
        "w.temperature_c",
        ("weather",),
        lags=(1, 3, 24),
        coverage_floor=0.5,
        provenance="environment_history (ALFR3D get_weather), household location, not Home "
        "Assistant",
        retention_days=730,
        readers=("scalar_baseline",),
        description="Read by scalar_baseline as its optional covariate, from silver weather_hourly "
        "directly; no learner reads this context_hourly column yet",
    ),
    Feature(
        "outdoor_humidity_pct",
        "float",
        "w.humidity_pct",
        ("weather",),
        lags=(1, 3, 24),
        provenance="environment_history (ALFR3D get_weather)",
        retention_days=730,
    ),
    Feature(
        "outdoor_pressure_hpa",
        "float",
        "w.pressure_hpa",
        ("weather",),
        lags=(1, 3, 24),
        provenance="environment_history (ALFR3D get_weather)",
        retention_days=730,
    ),
    Feature(
        "outdoor_condition",
        "text",
        "w.description",
        ("weather",),
        provenance="environment_history (ALFR3D get_weather)",
        retention_days=730,
    ),
    Feature(
        "calendar_busy_minutes",
        "float",
        "COALESCE(c.busy_minutes, 0)",
        ("calendar",),
        provenance="calendar_events (household calendar), kept 730 days since LF-0 "
        "(2026-10-09) and exported nightly; the lake's copy starts 2026-10-09",
        retention_days=730,
        readers=("calendar_observer",),
        description="ZERO-FILLED: an hour with no event reads 0, including every hour before the "
        "calendar was first captured (2026-10-09), so 0 does not mean 'free' there. "
        "Kept as is so context_hourly is unchanged; a fix (NULL before capture) is proposed in "
        "todo_lf8_context_registry.md",
    ),
    Feature(
        "people_home",
        "float",  # DOUBLE, as the wide table always typed it
        "CASE WHEN p.observed THEN p.people_home END",
        ("people",),
        provenance="silver presence_intervals via the gold presence grid (phones only)",
        readers=("presence_profile", "daytime_profile", "household_day"),
    ),
    # Registered, not captured: the ledger lists it, no learner can ever see it.
    Feature(
        "precise_location",
        "text",
        None,
        privacy=RESTRICTED,
        in_context_hourly=False,
        provenance="not captured: the Deck reports coarse (~2 km) location only; a precise "
        "opt-in needs the owner's decision (todo_precise_location.md)",
    ),
)

SERIES_FAMILIES = (
    SeriesFamily(
        "esphome:",
        "ESPHome sensors via smarthome_sensor_history, one reading about every 15 minutes",
        "host:name from the latest smarthome_devices snapshot, plus sa_sensor_aliases for retired "
        "row ids (never a row id)",
        retention_days=730,
        readers=("scalar_baseline", "drift"),
    ),
    SeriesFamily(
        "ha:",
        "Home Assistant entity history, exported by the sa-learner because HA keeps ~10 days",
        "the Home Assistant entity id",
        readers=("scalar_baseline", "drift"),
    ),
    SeriesFamily(
        "deck:",
        "alfr3d_deck device context (battery) via deck_context_history",
        "first 8 characters of the install id; one per Deck",
        readers=("scalar_baseline", "drift", "deck_observer"),
    ),
    SeriesFamily(
        "attention:",
        "alfr3d_deck attention telemetry: one window summary per report, averaged by hour here",
        "the telemetry column (switch_count, unlock_count)",
        readers=("scalar_baseline", "drift"),
    ),
)


# --- Validation -------------------------------------------------------------------------------


def validate(features=REGISTRY, families=SERIES_FAMILIES, joins=JOINS):
    """Problems with a registry, as strings (empty when it is sound)."""
    problems, seen = [], set()
    for f in features:
        if f.key in seen:
            problems.append(f"duplicate feature key {f.key!r}")
        seen.add(f.key)
        if f.kind not in KINDS:
            problems.append(f"{f.key}: unknown kind {f.kind!r}")
        if f.privacy not in SCOPES:
            problems.append(f"{f.key}: unknown privacy scope {f.privacy!r}")
        for name in f.joins:
            if name not in joins:
                problems.append(f"{f.key}: unknown join {name!r}")
        if f.value is not None and not f.joins:
            problems.append(f"{f.key}: has an expression but names no join")
        if f.privacy == RESTRICTED and (f.value is not None or f.in_context_hourly):
            problems.append(f"{f.key}: a restricted feature must not be built or exposed")
        if f.in_context_hourly and f.value is None:
            problems.append(f"{f.key}: a context_hourly column needs an expression")
    prefixes = set()
    for fam in families:
        if fam.prefix in prefixes:
            problems.append(f"duplicate series prefix {fam.prefix!r}")
        prefixes.add(fam.prefix)
        if fam.privacy not in SCOPES:
            problems.append(f"{fam.prefix}: unknown privacy scope {fam.privacy!r}")
    return problems


# --- What a learner may see ------------------------------------------------------------------


def learner_candidates(opened=frozenset(), features=REGISTRY, families=SERIES_FAMILIES):
    """Keys and prefixes a learner may be offered. Household-scoped ones always; owner-opened ones
    only when named in `opened`; restricted ones never, whatever the caller passes."""

    def ok(scope, name):
        return scope == HOUSEHOLD or (scope == OWNER_OPENED and name in opened)

    return {
        "features": [f.key for f in features if f.value is not None and ok(f.privacy, f.key)],
        "series": [s.prefix for s in families if ok(s.privacy, s.prefix)],
    }


# --- SQL generation ---------------------------------------------------------------------------

_SPINE = """
    people AS (
      SELECT bucket_utc, BOOL_OR(observed) AS observed,
             SUM((minutes_home >= 30)::INT) AS people_home
      FROM g_presence_grid GROUP BY bucket_utc),
    spine AS (
      SELECT UNNEST(generate_series(MIN(bucket_utc), MAX(bucket_utc), INTERVAL 1 HOUR))
               AS bucket_utc
      FROM people)"""


def buildable(feature, available, joins=JOINS):
    """True when the feature has an expression, is not restricted, and every relation it reads
    exists in this build."""
    if feature.value is None or feature.privacy == RESTRICTED:
        return False
    return all(joins[j].requires is None or joins[j].requires in available for j in feature.joins)


def features_query(available, features=REGISTRY, joins=JOINS):
    """The long-form gold `context_features`: (feature_key, bucket_utc, value_num, value_text),
    one row per feature per hour that has a value. Booleans are stored as 1/0 in value_num."""
    parts = []
    for f in features:
        if not buildable(f, available, joins):
            continue
        on = " ".join(joins[j].sql for j in f.joins)
        if f.kind == "text":
            num, text = "NULL::DOUBLE", f"CAST(({f.value}) AS VARCHAR)"
            present = f"({f.value}) IS NOT NULL"
        else:
            num, text = f"CAST(({f.value}) AS DOUBLE)", "NULL::VARCHAR"
            present = f"({f.value}) IS NOT NULL"
        parts.append(
            f"SELECT '{f.key}' AS feature_key, s.bucket_utc, {num} AS value_num, "
            f"{text} AS value_text FROM spine s {on} WHERE {present}"
        )
    if not parts:
        return None
    return (
        f"WITH {_SPINE.strip()} SELECT * FROM ({' UNION ALL '.join(parts)}) "
        "ORDER BY feature_key, bucket_utc"
    )


def context_hourly_query(available, features=REGISTRY, joins=JOINS):
    """The wide `context_hourly`, a pivot of `context_features` (view `g_context_features`) over
    the hour spine. Columns and their order are the registry's `in_context_hourly` features, after
    the fixed time columns; a feature that cannot be built this run is a typed NULL, so the
    columns never depend on which sources happen to exist."""
    pivot, columns = [], []
    for f in features:
        if not f.in_context_hourly:
            continue
        if buildable(f, available, joins):
            col = "text" if f.kind == "text" else "num"
            agg = f"MAX(value_{col}) FILTER (WHERE feature_key = '{f.key}')"
            pivot.append(f"{agg} AS {f.key}")
            cast = _PIVOT_CAST[f.kind]
            columns.append(f"CAST(x.{f.key} AS {cast}) AS {f.key}" if cast else f"x.{f.key}")
        else:
            columns.append(f"{_NULL_OF[f.kind]} AS {f.key}")
    pivot_cte = (
        f"x AS (SELECT bucket_utc, {', '.join(pivot)} FROM g_context_features GROUP BY bucket_utc)"
        if pivot
        else "x AS (SELECT NULL::TIMESTAMP AS bucket_utc WHERE false)"
    )
    return f"""
        WITH {_SPINE.strip()},
        {pivot_cte}
        SELECT s.bucket_utc, to_local(s.bucket_utc) AS bucket_local,
               CAST(to_local(s.bucket_utc) AS DATE) AS date_local,
               hour(to_local(s.bucket_utc)) AS hour_local, d.dow AS dow_local,
               {", ".join(columns)}
        FROM spine s
        LEFT JOIN s_day_context d ON d.date = CAST(to_local(s.bucket_utc) AS DATE)
        LEFT JOIN x ON x.bucket_utc = s.bucket_utc
        ORDER BY s.bucket_utc"""
