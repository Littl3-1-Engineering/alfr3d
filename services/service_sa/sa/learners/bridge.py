"""Stores each person's learned presence bridge (sa/presence_bridge.py) as a profile so the
awareness loop, which has no lake, measures stays the way silver did (stay start, daytime hours,
household day). Fitted nightly right after silver, which computes the numbers."""

import os

import duckdb

from sa.learners.base import Profile

NAME = "presence_bridge"
VERSION = "1"
SIGNAL = "presence.bridge"


def profiles_from_rows(rows, ref=None):
    """rows: (user_id, bridge_minutes, basis, nap_gaps, nights) -> [Profile]."""
    return [
        Profile(
            learner=NAME,
            learner_version=VERSION,
            subject_type="user",
            subject_id=user_id,
            signal=SIGNAL,
            params={
                "bridge_minutes": int(minutes),
                "basis": basis,
                "nap_gaps": int(naps),
                "nights": int(nights),
            },
            n_eff=float(nights),
            fitted_to=ref,
        )
        for user_id, minutes, basis, naps, nights in rows
    ]


def bridges_from_profiles(profiles):
    """{str(user_id): minutes} from stored profiles."""
    return {
        str(p.subject_id): int(p.params["bridge_minutes"])
        for p in profiles
        if p.learner == NAME and "bridge_minutes" in (p.params or {})
    }


def run_fit(lake_dir, conn):
    from sa import inference_store

    path = os.path.join(lake_dir, "silver", "person_bridge", "part-0.parquet")
    if not os.path.exists(path):
        return {"profiles": 0, "removed": 0}
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT user_id, bridge_minutes, basis, nap_gaps, nights FROM read_parquet('{path}')"
        ).fetchall()
    finally:
        con.close()
    profiles = profiles_from_rows(rows)
    if not profiles:
        return {"profiles": 0, "removed": 0}
    inference_store.save_profiles(conn, profiles)
    removed = inference_store.delete_profiles_except(conn, NAME, [p.subject_id for p in profiles])
    return {"profiles": len(profiles), "removed": removed}
