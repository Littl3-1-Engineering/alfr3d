#!/usr/bin/python
"""sa-learner: the slow path of service_sa.

For now runs only compute_entity_baselines() every 6 hours, the job service_daemon used to run
on its own schedule (LF-1a, todo/sa/todo_lf1a_sa_service_split.md). It takes minutes on the NUC,
which is exactly why it no longer shares a loop with anything time-sensitive. LF-1b adds the
Parquet bronze export here, and later phases the layer-1 learners.
"""

import os
import sys
import time

import schedule

from sa import engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "common"))
from common import heartbeat  # noqa: E402

logger = engine.logger

# compute_entity_baselines() alone measured ~175s on the NUC and blocks this loop while it runs,
# so the stale window must comfortably exceed one run plus a loop tick.
HEARTBEAT_PATH = "/tmp/sa_learner_heartbeat"
HEARTBEAT_STALE_SECONDS = 900
BASELINE_INTERVAL_HOURS = 6


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
    run()
