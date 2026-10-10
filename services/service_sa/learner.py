#!/usr/bin/python
"""sa-learner: the slow path of service_sa.

Runs compute_entity_baselines() every 6 hours (the job service_daemon used to run on its own
schedule, LF-1a) and the nightly lake job: Parquet bronze export (LF-1b, sa/lake.py) followed by
the silver/gold rebuild (LF-2, sa/silver.py). Both take minutes on
the NUC, which is exactly why they don't share a loop with anything time-sensitive. Later phases
add silver/gold and the layer-1 learners.
"""

import os
import sys
import time

import schedule

from sa import engine, external, inference_store, lake, silver
from sa.learners import presence, scalar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "common"))
from common import heartbeat  # noqa: E402

logger = engine.logger

# compute_entity_baselines() alone measured ~175s on the NUC and blocks this loop while it runs,
# so the stale window must comfortably exceed one run plus a loop tick.
HEARTBEAT_PATH = "/tmp/sa_learner_heartbeat"
HEARTBEAT_STALE_SECONDS = 900
BASELINE_INTERVAL_HOURS = 6
# Container time is UTC. 03:30 UTC = 23:30 local, after the day's partitions have mostly settled.
BRONZE_EXPORT_AT = "03:30"


def run_bronze_export():
    """Nightly lake job: export MySQL to bronze (LF-1b), pull the external sources that keep their
    own history -- Home Assistant and Gmail (LF-0b) -- then rebuild silver and gold from it (LF-2).
    Touches the heartbeat as each piece is written: a first run on an empty lake is a full backfill
    that outlasts the watchdog's stale window, and the watchdog exits the process when the
    heartbeat goes stale. The stages fail independently: a bronze table that couldn't be exported
    still leaves yesterday's copy, and silver is rebuilt from whatever bronze holds."""
    touch = lambda: heartbeat.touch(HEARTBEAT_PATH)  # noqa: E731
    try:
        outcome = lake.run_export(progress=touch)
        logger.info(f"bronze export done, failures: {outcome['failures'] or 'none'}")
    except Exception as e:
        logger.error(f"bronze export failed: {e}")
    try:
        outcomes = external.run_all(progress=touch)
        logger.info(f"external exports done: {outcomes}")
    except Exception as e:
        logger.error(f"external exports failed: {e}")
    try:
        counts = silver.run_build(progress=touch)
        logger.info(f"silver/gold build done: {counts}")
    except Exception as e:
        logger.error(f"silver/gold build failed: {e}")
    run_learners()


def run_learners():
    """Fit the layer-1 learners on the gold layer and store their profiles and outlooks (LF-3).
    Runs after every silver/gold rebuild; sa-awareness picks the new fit up on its next cycle."""
    conn = None
    try:
        conn = inference_store.connect()
        outcome = presence.run_fit(lake.LAKE_DIR, conn)
        logger.info(f"presence learner done: {outcome}")
    except Exception as e:
        logger.error(f"presence learner failed: {e}")
    try:
        if conn is None:
            conn = inference_store.connect()
        outcome = scalar.run_fit(lake.LAKE_DIR, conn)
        logger.info(f"scalar learner done: {outcome}")
    except Exception as e:
        logger.error(f"scalar learner failed: {e}")
    finally:
        if conn:
            conn.close()


def run():
    while True:
        heartbeat.touch(HEARTBEAT_PATH)
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    logger.info("sa-learner starting")
    heartbeat.touch(HEARTBEAT_PATH)
    heartbeat.start_watchdog(HEARTBEAT_PATH, HEARTBEAT_STALE_SECONDS, log=logger)
    # Same cadence as the daemon's old `schedule.every(6).hours.do(compute_entity_baselines)`:
    # first run 6h after start, not at start.
    schedule.every(BASELINE_INTERVAL_HOURS).hours.do(engine.compute_entity_baselines)
    schedule.every().day.at(BRONZE_EXPORT_AT).do(run_bronze_export)
    run()
