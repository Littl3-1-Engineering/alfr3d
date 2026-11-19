#!/usr/bin/python
"""sa-learner: the slow path of service_sa.

Runs the nightly lake job: Parquet bronze export (LF-1b, sa/lake.py) followed by the silver/gold
rebuild (LF-2, sa/silver.py) and the layer-1 learner fits. It takes minutes on the NUC, which is
exactly why it doesn't share a loop with anything time-sensitive. (compute_entity_baselines(), the
6-hourly job this process used to run, was retired with the LF-4 departure_anomaly cutover.)
"""

import os
import sys
import time

import schedule

from sa import disk, engine, external, inference_store, lake, ledger, screen, silver
from sa.learners import (
    bridge,
    daytime,
    device_rhythm,
    drift,
    household_day,
    presence,
    rates,
    scalar,
    stay,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "common"))
from common import get_producer, heartbeat, learner_health  # noqa: E402

logger = engine.logger

# A long export or silver build blocks this loop while it runs, so the stale window must
# comfortably exceed one run plus a loop tick.
HEARTBEAT_PATH = "/tmp/sa_learner_heartbeat"
HEARTBEAT_STALE_SECONDS = 900
# Container time is UTC. 03:30 UTC = 23:30 local, after the day's partitions have mostly settled.
BRONZE_EXPORT_AT = "03:30"
DISK_SAMPLE_INTERVAL_HOURS = 4


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
    run_ledger()
    run_learners()
    run_discovery_screen()


def record_disk_sample():
    """Sample host disk free/total into sa_storage_metrics (sa/disk.py) for check_disk_health."""
    conn = None
    try:
        conn = inference_store.connect()
        total, free = disk.record_disk_sample(conn)
        logger.info(f"disk sample: {free / 1024**3:.1f} GB free of {total / 1024**3:.1f} GB")
        host_rows = disk.record_host_usage(conn)
        if not host_rows:
            logger.warning("host usage snapshot missing or stale; card will omit Docker/backups")
    except Exception as e:
        logger.error(f"disk sample failed: {e}")
    finally:
        if conn:
            conn.close()


def run_ledger():
    """Write the context capture ledger (sa/ledger.py) for the API. Best effort and independent of
    the learners: a missing table (migration 0063 not applied) or any error is logged, and the
    nightly job carries on."""
    conn = None
    try:
        conn = inference_store.connect()
        outcome = ledger.run(lake.LAKE_DIR, conn)
        logger.info(f"context ledger written: {outcome}")
        if outcome["unregistered"]:
            logger.warning(f"series with no registered family: {outcome['unregistered']}")
    except Exception as e:
        logger.error(f"context ledger failed: {e}")
    finally:
        if conn:
            conn.close()


def run_discovery_screen():
    """Screen the declared targets against the context features and store the findings
    (sa/screen.py, `sa_covariate_findings`). Best effort and independent of the learners, like the
    ledger: a missing table (migration 0064 not applied), an unsound target registry or any error is
    logged and the nightly job carries on. Findings drive no card and no actuation."""
    conn = None
    try:
        conn = inference_store.connect()
        outcome = screen.run(lake.LAKE_DIR, conn)
        logger.info(f"discovery screen stored: {outcome}")
    except Exception as e:
        logger.error(f"discovery screen failed: {e}")
    finally:
        if conn:
            conn.close()


# (learner name as stored in sa_profiles, label for the log, module with run_fit). The order is the
# order they run in: the presence bridge first (the others read it), drift last (the learners above
# rewrite their own stability, and drift caps it afterwards).
LEARNER_STAGES = (
    ("presence_bridge", "presence bridge", bridge),
    ("presence_profile", "presence learner", presence),
    ("scalar_baseline", "scalar learner", scalar),
    ("event_rate", "rate learner", rates),
    ("device_rhythm", "device rhythm learner", device_rhythm),
    ("household_day", "household day learner", household_day),
    ("stay_profile", "stay learner", stay),
    ("daytime_profile", "daytime learner", daytime),
    ("drift", "drift detector", drift),
)


def publish_fit_events(outcomes):
    """Send the night's fit outcomes to the event stream so a failing learner is in the household
    event log (and `/api/health`), not only in a container log. Best effort: it never raises, the
    nightly job must finish whether or not Kafka answers."""
    try:
        import orjson

        producer = get_producer()
        for event in learner_health.fit_events(outcomes):
            producer.send("event-stream", orjson.dumps(event))
        producer.flush(5)
    except Exception as e:
        logger.error(f"fit events not published: {e}")


def run_learners():
    """Fit the layer-1 learners on the gold layer and store their profiles and outlooks (LF-3).
    Runs after every silver/gold rebuild; sa-awareness picks the new fit up on its next cycle. Each
    learner fails independently: one that raises is logged, recorded as `fit_failed`, and the rest
    still run. The outcomes are published (`publish_fit_events`) and `learner_health.stale_fits`
    reads the result back from the stored profiles."""
    conn = None
    outcomes = {}
    try:
        for name, label, module in LEARNER_STAGES:
            try:
                if conn is None:
                    conn = inference_store.connect()
                outcome = module.run_fit(lake.LAKE_DIR, conn)
                logger.info(f"{label} done: {outcome}")
                outcomes[name] = ("fit_ok", outcome)
            except Exception as e:
                logger.error(f"{label} failed: {e}")
                outcomes[name] = ("fit_failed", str(e))
    finally:
        if conn:
            conn.close()
    publish_fit_events(outcomes)
    return outcomes


def run():
    while True:
        heartbeat.touch(HEARTBEAT_PATH)
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    logger.info("sa-learner starting")
    heartbeat.touch(HEARTBEAT_PATH)
    heartbeat.start_watchdog(HEARTBEAT_PATH, HEARTBEAT_STALE_SECONDS, log=logger)
    schedule.every().day.at(BRONZE_EXPORT_AT).do(run_bronze_export)
    # Sampled on its own, short job so a long export can't delay it, and a sample at start so the
    # trend has a fresh point after every deploy.
    schedule.every(DISK_SAMPLE_INTERVAL_HOURS).hours.do(record_disk_sample)
    record_disk_sample()
    run()
