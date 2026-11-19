"""Derived-target registry (Context learning 4/5, todo/sa/todo_lf10_discovery_screen.md).

A target is an OUTCOME the household produces (guests home, time away, an empty house), declared
once here as a definition over silver/gold and screened nightly against the context registry's
features by `sa/screen.py`. A new outcome is one `Target(...)` in `REGISTRY` plus a validation run:
no learner changes, no new SQL anywhere else. That is the point: the owner's examples (weather
against time outdoors, calendar and weather against guests) are illustrations of a class of
question; these three targets only prove that the registry works.

A target is not a feature (a feature is something we can observe BEFORE, a target is something we
want to explain) and not a card. Nothing here acts on a finding.

    Target(key, kind, query, candidates, description)

- `kind`: `continuous` (screened by `covariates.screen` on the residual after the hour-of-week
  mean), `count` or `binary` (screened by `covariates.screen_rates`, which is not blind on a target
  that is zero most hours). Chosen by the registrant and checked against the data: `check_kind`.
- `query`: SQL over the registered lake views (`s_*` silver, `g_*` gold) returning exactly
  `(bucket_utc, value)`, one row per observed hour. `validate_queries` runs it on a small synthetic
  lake and rejects wrong columns, duplicate hours, non-numeric values, and **leakage**: the value
  at hour t must not change when only later hours are removed.
- `candidates`: which features, at which lags, may be screened against it, at most `MAX_PER_TARGET`
  in all (the engine's per-target budget). Features must exist, be numeric, and be visible to a
  learner (`context_registry.learner_candidates`): household-scoped always, owner-opened only when
  opened, restricted never, so precise location can never be screened.

Honest naming: `away_minutes` is the owner's "time outdoors" idea in the only form the data
supports, away from the HOUSE, not outdoors. "Guest" is the household's own device tag and includes
regular visitors, so `guests_home` is "guest-tagged people home", not strangers.
"""

from dataclasses import dataclass

import duckdb

from sa import context_registry, covariates

CONTINUOUS, COUNT, BINARY = "continuous", "count", "binary"
KINDS = (CONTINUOUS, COUNT, BINARY)
RAW, ANOMALY = "raw", "anomaly"  # anomaly: the feature minus its own mean for that hour of day
TRANSFORMS = (RAW, ANOMALY)

DEFAULT_LAGS = (0, 1, 3, 6, 24)  # hours a feature may lead; each target declares the ones it uses
MAX_PER_TARGET = covariates.MAX_CANDIDATES
HOME_MINUTES = (
    30  # an hour counts as "home" at this many minutes (as context_registry's people_home)
)
SPARSE_KIND_MAX_ZERO_SHARE = 0.9  # a "continuous" target this often zero is really a count/binary

NUMERIC_FEATURE_KINDS = ("bool", "int", "float")


@dataclass(frozen=True)
class Candidate:
    """A feature offered to a target, at these lags, optionally as its anomaly."""

    feature: str
    lags: tuple = (0,)
    transform: str = RAW


@dataclass(frozen=True)
class Target:
    key: str
    kind: str
    query: str
    candidates: tuple
    description: str
    min_events: int = covariates.RATE_MIN_EVENTS  # count/binary: non-zero hours needed
    privacy: str = context_registry.HOUSEHOLD


_PEOPLE = "u AS (SELECT DISTINCT user_id, user_type FROM s_presence_intervals)"
_RESIDENT = "u.user_type IN ('owner', 'resident')"

GUESTS_HOME = f"""
    WITH {_PEOPLE}
    SELECT g.bucket_utc,
           SUM(CASE WHEN u.user_type = 'guest' AND g.minutes_home >= {HOME_MINUTES}
                    THEN 1 ELSE 0 END)::DOUBLE AS value
    FROM g_presence_grid g JOIN u USING (user_id)
    WHERE g.observed GROUP BY g.bucket_utc ORDER BY g.bucket_utc"""

HOUSE_EMPTY = f"""
    WITH {_PEOPLE}
    SELECT g.bucket_utc,
           (SUM(CASE WHEN {_RESIDENT} AND g.minutes_home >= {HOME_MINUTES}
                     THEN 1 ELSE 0 END) = 0)::INT::DOUBLE AS value
    FROM g_presence_grid g JOIN u USING (user_id)
    WHERE g.observed GROUP BY g.bucket_utc ORDER BY g.bucket_utc"""

AWAY_MINUTES = f"""
    WITH {_PEOPLE}
    SELECT g.bucket_utc,
           SUM(CASE WHEN {_RESIDENT} THEN 60 - g.minutes_home ELSE 0 END)::DOUBLE AS value
    FROM g_presence_grid g JOIN u USING (user_id)
    WHERE g.observed GROUP BY g.bucket_utc ORDER BY g.bucket_utc"""

# Calendar and holiday features are used raw; the weather series as anomalies, because the target's
# hour-of-week structure is already removed and raw temperature would only re-find the daily cycle.
REGISTRY = (
    Target(
        key="guests_home",
        kind=COUNT,
        query=GUESTS_HOME,
        description="Guest-tagged people home for at least half of the hour.",
        candidates=(
            Candidate("outdoor_temp_c", (0, 3, 24), ANOMALY),
            Candidate("outdoor_humidity_pct", (0,), ANOMALY),
            Candidate("calendar_busy_minutes", (0, 24)),
            Candidate("is_holiday", (0,)),
            Candidate("forecast_rain_probability", (0,)),
        ),
    ),
    Target(
        key="house_empty",
        kind=BINARY,
        query=HOUSE_EMPTY,
        description="No resident or owner home for at least half of the hour.",
        candidates=(
            Candidate("outdoor_temp_c", (0, 3), ANOMALY),
            Candidate("outdoor_humidity_pct", (0,), ANOMALY),
            Candidate("is_daylight", (0,)),
            Candidate("calendar_busy_minutes", (0, 1)),
            Candidate("is_holiday", (0,)),
        ),
    ),
    Target(
        key="away_minutes",
        kind=CONTINUOUS,
        query=AWAY_MINUTES,
        description="Resident and owner minutes spent away from the house in the hour, summed.",
        candidates=(
            Candidate("outdoor_temp_c", (0, 3, 6), ANOMALY),
            Candidate("outdoor_humidity_pct", (0,), ANOMALY),
            Candidate("outdoor_pressure_hpa", (0,), ANOMALY),
            Candidate("calendar_busy_minutes", (0, 1)),
            Candidate("is_holiday", (0,)),
        ),
    ),
)


def expanded(target):
    """[(feature, lag, transform)] in declaration order: what the screen will be offered."""
    return [(c.feature, lag, c.transform) for c in target.candidates for lag in c.lags]


def method_for(target):
    return "slope" if target.kind == CONTINUOUS else "rates"


# --- Static validation -----------------------------------------------------------------------


def validate(targets=REGISTRY, features=context_registry.REGISTRY, opened=frozenset()):
    """Problems with the target registry, as strings (empty when it is sound)."""
    problems, seen = [], set()
    by_key = {f.key: f for f in features}
    visible = set(context_registry.learner_candidates(opened=opened, features=features)["features"])
    for t in targets:
        if t.key in seen:
            problems.append(f"duplicate target key {t.key!r}")
        seen.add(t.key)
        if t.kind not in KINDS:
            problems.append(f"{t.key}: unknown kind {t.kind!r}")
        if t.privacy != context_registry.HOUSEHOLD:
            problems.append(f"{t.key}: targets are household-scoped, not {t.privacy!r}")
        if not t.query.strip():
            problems.append(f"{t.key}: no query")
        pairs = expanded(t)
        if not pairs:
            problems.append(f"{t.key}: no candidates")
        if len(pairs) > MAX_PER_TARGET:
            problems.append(
                f"{t.key}: {len(pairs)} candidate-lags, over the budget of {MAX_PER_TARGET}"
            )
        if len(set(pairs)) != len(pairs):
            problems.append(f"{t.key}: a feature, lag and transform is offered twice")
        for c in t.candidates:
            feature = by_key.get(c.feature)
            if feature is None:
                problems.append(f"{t.key}: unknown feature {c.feature!r}")
            elif c.feature not in visible:
                problems.append(f"{t.key}: {c.feature!r} is not visible to a learner")
            elif feature.kind not in NUMERIC_FEATURE_KINDS:
                problems.append(f"{t.key}: {c.feature!r} is {feature.kind}, not numeric")
            if c.transform not in TRANSFORMS:
                problems.append(f"{t.key}: {c.feature!r} has unknown transform {c.transform!r}")
            if not c.lags or any((not isinstance(lag, int)) or lag < 0 for lag in c.lags):
                problems.append(f"{t.key}: {c.feature!r} lags must be non-negative integers")
    return problems


# --- Checks against data ---------------------------------------------------------------------


def check_kind(target, values):
    """A problem string when `values` (the target's value per observed hour) do not fit the kind
    it was declared with, else None. Run on every night's data, and on the synthetic lake."""
    values = [v for v in values if v is not None]
    if not values:
        return None  # no data is its own, separate finding
    if target.kind == BINARY and any(v not in (0, 1) for v in values):
        return "declared binary but has values other than 0 and 1"
    if target.kind == COUNT and any(v < 0 or v != int(v) for v in values):
        return "declared count but has negative or fractional values"
    if target.kind == CONTINUOUS:
        zero_share = sum(1 for v in values if v == 0) / len(values)
        if zero_share >= SPARSE_KIND_MAX_ZERO_SHARE:
            return (
                f"declared continuous but {zero_share:.0%} zero; "
                "a median slope cannot see an effect on it, declare it count or binary"
            )
    return None


def values(con, target):
    """[(bucket_utc, value)] for the target on a connection that already has the s_*/g_* views
    registered (`silver._register_views`)."""
    return con.execute(target.query).fetchall()


def synthetic_lake(hours=96):
    """An in-memory DuckDB holding the tables targets read, with a known answer: one owner, one
    resident and two guests over `hours` hours. Anyone adding a target that reads another table
    extends this so `validate_queries` can run it."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE s_presence_intervals AS SELECT * FROM (VALUES "
        "(1, 'owner'), (2, 'resident'), (3, 'guest'), (4, 'guest')) AS t(user_id, user_type)"
    )
    con.execute(
        f"""CREATE TABLE g_presence_grid AS
        SELECT u.user_id, TIMESTAMP '2026-01-05 00:00:00' + h * INTERVAL 1 HOUR AS bucket_utc,
               CASE
                 WHEN u.user_id = 1 THEN CASE WHEN h % 24 BETWEEN 9 AND 17 THEN 0 ELSE 60 END
                 WHEN u.user_id = 2 THEN CASE WHEN h % 24 BETWEEN 8 AND 12 THEN 0 ELSE 60 END
                 WHEN u.user_id = 3 THEN CASE WHEN h % 24 BETWEEN 18 AND 22 THEN 60 ELSE 0 END
                 ELSE CASE WHEN h % 24 = 20 THEN 45 ELSE 0 END
               END AS minutes_home,
               true AS observed
        FROM (SELECT * FROM (VALUES (1), (2), (3), (4)) AS t(user_id)) u,
             generate_series(0, {hours - 1}) AS g(h)"""
    )
    return con


def validate_queries(targets=REGISTRY, make_lake=synthetic_lake):
    """Problems found by running each target's query on the synthetic lake: wrong columns,
    duplicate hours, a non-numeric value, a value that does not fit its kind, and leakage (the value
    at hour t changing when only LATER hours are removed)."""
    problems = []
    for t in targets:
        try:
            con = make_lake()
            cols = [d[0] for d in con.execute(f"SELECT * FROM ({t.query}) LIMIT 0").description]
            rows = values(con, t)
        except Exception as e:  # a query that does not run is the problem, whatever it was
            problems.append(f"{t.key}: query failed: {e}")
            continue
        if cols != ["bucket_utc", "value"]:
            problems.append(f"{t.key}: query must return (bucket_utc, value), not {cols}")
            continue
        hours = [r[0] for r in rows]
        if len(set(hours)) != len(hours):
            problems.append(f"{t.key}: more than one row for an hour")
        if any(not isinstance(r[1], (int, float)) for r in rows if r[1] is not None):
            problems.append(f"{t.key}: value is not numeric")
        kind_problem = check_kind(t, [r[1] for r in rows])
        if kind_problem:
            problems.append(f"{t.key}: {kind_problem}")
        if rows:
            cutoff = hours[len(hours) // 2]
            full = dict(rows)
            truncated = make_lake()
            for table in ("g_presence_grid",):
                truncated.execute(f"DELETE FROM {table} WHERE bucket_utc > ?", [cutoff])
            early = dict(values(truncated, t))
            if any(full.get(h) != v for h, v in early.items()):
                problems.append(f"{t.key}: leaks, a value changed when later hours were removed")
    return problems
