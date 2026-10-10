#!/usr/bin/python
"""sa-awareness: the fast path of service_sa.

Runs SAEngine.check_situational_awareness() every 60 seconds -- build the context frame, run the
display rules, apply card suppression, publish to the `situational-awareness` Kafka topic. This
is the loop that used to run at the end of every service_daemon cycle (LF-1a,
todo/sa/todo_lf1a_sa_service_split.md). Behaviour is unchanged; it just no longer shares a loop
with routines, device scans and the 6-hourly baseline computation.
"""

import os
import sys
import time

from sa import engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "common"))
from common import heartbeat  # noqa: E402

logger = engine.logger

# Same window the daemon used for its own loop: one cycle is a 60s sleep plus however long the
# SA rules take, so 300s catches a wedged loop without flapping on a slow pass.
HEARTBEAT_PATH = "/tmp/sa_awareness_heartbeat"
HEARTBEAT_STALE_SECONDS = 300
CYCLE_SECONDS = 60


def run(sa_engine):
    while True:
        heartbeat.touch(HEARTBEAT_PATH)
        try:
            sa_engine.check_situational_awareness()
        except Exception as e:
            logger.error("Situational awareness check failed: " + str(e))
        time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    sa_engine = engine.SAEngine()
    if len(sys.argv) == 2 and sys.argv[1] == "test":
        logger.info("Running one situational awareness cycle (test mode)")
        sa_engine.check_situational_awareness()
        sys.exit(0)
    logger.info("sa-awareness starting")
    heartbeat.touch(HEARTBEAT_PATH)
    heartbeat.start_watchdog(HEARTBEAT_PATH, HEARTBEAT_STALE_SECONDS, log=logger)
    run(sa_engine)
