"""MySQL reads and writes for the inference contract (migration 046): sa_profiles and
sa_inferences. Nothing else in service_sa touches these tables, so the SQL lives in one place.

Profiles are written by sa-learner after each fit and read by sa-awareness, which polls
`profiles_stamp()` once per cycle (one cheap MAX() query) and reloads only when a fit has landed.
That replaces the Kafka `sa-profiles-updated` message the plan sketched: polling needs no new topic
or consumer thread and can't miss a message across a restart.

All timestamps are naive UTC, like every SA table.
"""

import logging
import os

import orjson
import pymysql

from sa.learners.base import Inference, Profile

logger = logging.getLogger("SAStore")

# NOTE: `signal` is a reserved word in MySQL (the SIGNAL statement). It must be backtick-quoted in
# every statement that names the column -- the migration does, and so must any new query here.


def connect():
    """A MySQL connection from the service's environment."""
    return pymysql.connect(
        host=os.environ.get("MYSQL_DATABASE"),
        user=os.environ.get("MYSQL_USER"),
        passwd=os.environ.get("MYSQL_PSWD"),
        db=os.environ.get("MYSQL_NAME"),
    )


def _json(value):
    return None if value is None else orjson.dumps(value).decode()


def _load(value):
    return None if value is None else orjson.loads(value)


def save_profiles(conn, profiles):
    """Insert or replace each profile (one row per learner/subject/signal)."""
    cursor = conn.cursor()
    for p in profiles:
        cursor.execute(
            "INSERT INTO sa_profiles (learner, learner_version, subject_type, subject_id, "
            "`signal`, params, n_eff, coverage, source_quality, stability, fitted_from, "
            "fitted_to, computed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE learner_version = VALUES(learner_version), "
            "params = VALUES(params), n_eff = VALUES(n_eff), coverage = VALUES(coverage), "
            "source_quality = VALUES(source_quality), stability = VALUES(stability), "
            "fitted_from = VALUES(fitted_from), fitted_to = VALUES(fitted_to), "
            "computed_at = VALUES(computed_at)",
            (
                p.learner,
                p.learner_version,
                p.subject_type,
                p.subject_id,
                p.signal,
                _json(p.params),
                p.n_eff,
                p.coverage,
                p.source_quality,
                p.stability,
                p.fitted_from,
                p.fitted_to,
                p.computed_at,
            ),
        )
    conn.commit()
    return len(profiles)


def delete_profiles_except(conn, learner, keep_subject_ids):
    """Drop a learner's profiles for anyone not in `keep_subject_ids` (a person who no longer has
    enough history must not keep scoring against a stale fit). Returns how many were removed."""
    keep = {str(k) for k in keep_subject_ids}
    cursor = conn.cursor()
    cursor.execute("SELECT subject_id FROM sa_profiles WHERE learner = %s", (learner,))
    stale = [row[0] for row in cursor.fetchall() if row[0] not in keep]
    for subject_id in stale:
        cursor.execute(
            "DELETE FROM sa_profiles WHERE learner = %s AND subject_id = %s", (learner, subject_id)
        )
    conn.commit()
    return len(stale)


def profiles_stamp(conn, learner):
    """When this learner's profiles were last written, or None. The cheap staleness probe."""
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(computed_at) FROM sa_profiles WHERE learner = %s", (learner,))
    row = cursor.fetchone()
    return row[0] if row else None


def load_profiles(conn, learner):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT learner, learner_version, subject_type, subject_id, `signal`, params, n_eff, "
        "coverage, source_quality, stability, fitted_from, fitted_to, computed_at "
        "FROM sa_profiles WHERE learner = %s",
        (learner,),
    )
    profiles = []
    for row in cursor.fetchall():
        profiles.append(
            Profile(
                learner=row[0],
                learner_version=row[1],
                subject_type=row[2],
                subject_id=row[3],
                signal=row[4],
                params=_load(row[5]),
                n_eff=row[6],
                coverage=row[7],
                source_quality=row[8],
                stability=row[9],
                fitted_from=row[10],
                fitted_to=row[11],
                computed_at=row[12],
            )
        )
    return profiles


_INFERENCE_COLUMNS = (
    "layer, kind, subject_type, subject_id, `signal`, context, window_start, window_end, observed, "
    "expected, probability, surprise, confidence, n_eff, evidence, learner, learner_version, "
    "computed_at, expires_at"
)


def upsert_inference(conn, inf):
    """Insert an inference, or refresh it if the same (learner, kind, subject, signal,
    window_start) is already stored. An ongoing deviation keeps its window_start (the last
    sighting) from cycle to cycle, so it updates one row instead of adding one per minute."""
    cursor = conn.cursor()
    cursor.execute(
        f"INSERT INTO sa_inferences ({_INFERENCE_COLUMNS}) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE window_end = VALUES(window_end), observed = VALUES(observed), "
        "expected = VALUES(expected), probability = VALUES(probability), "
        "surprise = VALUES(surprise), confidence = VALUES(confidence), n_eff = VALUES(n_eff), "
        "evidence = VALUES(evidence), computed_at = VALUES(computed_at), "
        "expires_at = VALUES(expires_at)",
        (
            inf.layer,
            inf.kind,
            inf.subject_type,
            inf.subject_id,
            inf.signal,
            _json(inf.context),
            inf.window_start,
            inf.window_end,
            _json(inf.observed),
            _json(inf.expected),
            inf.probability,
            inf.surprise,
            inf.confidence,
            inf.n_eff,
            _json(inf.evidence),
            inf.learner,
            inf.learner_version,
            inf.computed_at,
            inf.expires_at,
        ),
    )
    conn.commit()


def replace_predictions(conn, learner, inferences):
    """A prediction is a rolling 24 h outlook, so each fit replaces the previous outlook for the
    learner instead of accumulating one per run."""
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM sa_inferences WHERE learner = %s AND kind = 'prediction'", (learner,)
    )
    conn.commit()
    for inf in inferences:
        upsert_inference(conn, inf)
    return len(inferences)


def _inference_from_row(row):
    """An Inference from a row selected with _INFERENCE_COLUMNS."""
    return Inference(
        layer=row[0],
        kind=row[1],
        subject_type=row[2],
        subject_id=row[3],
        signal=row[4],
        context=_load(row[5]),
        window_start=row[6],
        window_end=row[7],
        observed=_load(row[8]),
        expected=_load(row[9]),
        probability=row[10],
        surprise=row[11],
        confidence=row[12],
        n_eff=row[13],
        evidence=_load(row[14]),
        learner=row[15],
        learner_version=row[16],
        computed_at=row[17],
        expires_at=row[18],
    )


def latest_prediction(conn, learner, subject_id):
    """The stored 24 h outlook for a subject, as an Inference, or None."""
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {_INFERENCE_COLUMNS} FROM sa_inferences WHERE learner = %s AND kind = "
        "'prediction' AND subject_id = %s ORDER BY computed_at DESC LIMIT 1",
        (learner, str(subject_id)),
    )
    row = cursor.fetchone()
    return _inference_from_row(row) if row else None


def load_recent(conn, layer, since, kinds=("deviation", "state")):
    """Deviations and observed states of one layer refreshed since `since` (naive UTC), each
    carrying its row id as `row_id`. An ongoing deviation is re-upserted every cycle, so
    `computed_at` is when it was last seen; one that has ended stops refreshing and drops out. This
    is layer 2's only input.
    """
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {_INFERENCE_COLUMNS}, id FROM sa_inferences "
        f"WHERE layer = %s AND kind IN ({','.join(['%s'] * len(kinds))}) AND computed_at >= %s",
        (layer, *kinds, since),
    )
    found = []
    for row in cursor.fetchall():
        inference = _inference_from_row(row)
        inference.row_id = row[19]
        found.append(inference)
    return found
