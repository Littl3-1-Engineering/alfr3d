"""Liveness heartbeat for services whose main loop has no HTTP surface.

A wedged Kafka consumer -- blocked inside a connect at boot while it races the broker, or
stuck mid-poll -- leaves its process running and its PID alive, so Docker's default "did the
process exit?" liveness reports nothing useful. Each such service touches a heartbeat file
every time its loop makes progress, and the container HEALTHCHECK marks the container
unhealthy once that file goes stale.

Used as a healthcheck from compose:

    test: ["CMD", "python", "-m", "common.heartbeat", "/tmp/user_heartbeat", "90"]

`service_speak` grew the first hand-rolled version of this; it now delegates here so every
consumer service reports liveness the same way.
"""

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

# Long enough that an ordinary slow iteration never trips it, short enough that a genuinely
# stuck consumer is caught within a couple of healthcheck intervals. Services whose loop is
# inherently slower (the daemon's 60s cycle) pass their own value.
DEFAULT_STALE_SECONDS = 90


def touch(path: str) -> None:
    """Record that the caller's main loop is making progress."""
    try:
        with open(path, "w") as f:
            f.write(str(time.time()))
    except OSError as e:
        # A heartbeat that can't be written must not take the service down with it -- the
        # healthcheck notices the staleness by itself, which is the outcome we want anyway.
        logger.warning(f"Failed to write heartbeat to {path}: {e}")


def is_fresh(path: str, stale_seconds: float = DEFAULT_STALE_SECONDS) -> bool:
    """True if `path` exists and was touched within `stale_seconds`."""
    try:
        return (time.time() - os.path.getmtime(path)) < stale_seconds
    except OSError:
        # Missing file: the service has not reached its loop yet, or never will.
        return False


def main(argv) -> int:
    if not argv:
        print("usage: python -m common.heartbeat <path> [stale_seconds]", file=sys.stderr)
        return 2
    path = argv[0]
    try:
        stale = float(argv[1]) if len(argv) > 1 else DEFAULT_STALE_SECONDS
    except ValueError:
        print(f"invalid stale_seconds: {argv[1]}", file=sys.stderr)
        return 2
    return 0 if is_fresh(path, stale) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
