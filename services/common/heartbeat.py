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
import threading
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


# How often the watchdog re-checks. Small next to any sane stale window, so the delay between
# a loop wedging and the process exiting is dominated by `stale_seconds`, not by this.
WATCHDOG_CHECK_INTERVAL_SECONDS = 10


def start_watchdog(
    path: str,
    stale_seconds: float = DEFAULT_STALE_SECONDS,
    log: logging.Logger = logger,
    check_interval: float = WATCHDOG_CHECK_INTERVAL_SECONDS,
    stop_event: threading.Event = None,
) -> threading.Thread:
    """Exit the process once `path` goes stale, so the container's restart policy revives it.

    A Docker HEALTHCHECK on the same file makes a wedged loop *visible*; this makes it
    *recover*. Docker does not restart a container merely for being unhealthy, so without
    this a stuck consumer sits red until a human notices.

    The callers that need this touch their heartbeat from inside the very loop that can
    wedge, so nothing in-process would otherwise be running to notice. Hence a separate
    daemon thread, and `os._exit` rather than `sys.exit`: raising SystemExit here would
    only unwind this watchdog thread, which is the one thread still working.

    Touches `path` once up front so a slow start can't trip the watchdog before the loop
    has written its first beat; a loop that never starts still goes stale on schedule.

    Setting `stop_event` retires the thread. Services never need it -- the watchdog should
    outlive everything else in the process -- but anything that starts a watchdog it does
    not intend to keep, tests above all, must be able to stop it: a leaked watchdog will
    happily call os._exit on whatever process is still running when its file goes stale.
    """
    touch(path)

    stop = stop_event if stop_event is not None else threading.Event()

    def _watch() -> None:
        # wait() doubles as the sleep and the stop check, so a retired watchdog goes away
        # within one interval instead of lingering for a full stale window.
        while not stop.wait(check_interval):
            if is_fresh(path, stale_seconds):
                continue
            try:
                age = time.time() - os.path.getmtime(path)
                age_text = f"{age:.0f}s"
            except OSError:
                age_text = "missing"
            log.critical(
                f"Heartbeat {path} stale ({age_text} > {stale_seconds:.0f}s); "
                "the main loop is wedged -- exiting for container restart"
            )
            os._exit(1)

    thread = threading.Thread(target=_watch, name="heartbeat-watchdog", daemon=True)
    thread.start()
    return thread


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
