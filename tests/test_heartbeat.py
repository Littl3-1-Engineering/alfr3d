"""Unit tests for common.heartbeat -- the liveness file the consumer services touch and
their container HEALTHCHECKs read.

The point of this module is that a wedged consumer keeps its process alive, so these cover
the states a healthcheck actually has to tell apart: never started, making progress, and
stopped making progress.
"""

import os
import threading
import time

from services.common import heartbeat


def test_missing_file_is_not_fresh(tmp_path):
    # A service that has not reached its loop yet must not read as healthy.
    assert heartbeat.is_fresh(str(tmp_path / "never_written")) is False


def test_touch_then_fresh(tmp_path):
    p = str(tmp_path / "hb")
    heartbeat.touch(p)
    assert os.path.exists(p)
    assert heartbeat.is_fresh(p) is True


def test_stale_file_is_not_fresh(tmp_path):
    p = str(tmp_path / "hb")
    heartbeat.touch(p)
    # Backdate well past the window rather than sleeping through it.
    old = time.time() - 600
    os.utime(p, (old, old))
    assert heartbeat.is_fresh(p, 90) is False


def test_touch_refreshes_a_stale_file(tmp_path):
    p = str(tmp_path / "hb")
    heartbeat.touch(p)
    old = time.time() - 600
    os.utime(p, (old, old))
    assert heartbeat.is_fresh(p, 90) is False
    heartbeat.touch(p)
    assert heartbeat.is_fresh(p, 90) is True


def test_touch_survives_an_unwritable_path(tmp_path, caplog):
    # A heartbeat that cannot be written must not raise into the service's main loop.
    unwritable = str(tmp_path / "no_such_dir" / "hb")
    heartbeat.touch(unwritable)
    assert heartbeat.is_fresh(unwritable) is False


def test_cli_exit_codes(tmp_path):
    p = str(tmp_path / "hb")
    heartbeat.touch(p)
    assert heartbeat.main([p, "90"]) == 0

    old = time.time() - 600
    os.utime(p, (old, old))
    assert heartbeat.main([p, "90"]) == 1

    assert heartbeat.main([str(tmp_path / "absent"), "90"]) == 1
    # Usage errors are distinct from "unhealthy" so a broken compose entry is visible.
    assert heartbeat.main([]) == 2
    assert heartbeat.main([p, "not-a-number"]) == 2


def test_cli_defaults_to_the_module_window(tmp_path):
    p = str(tmp_path / "hb")
    heartbeat.touch(p)
    assert heartbeat.main([p]) == 0

    old = time.time() - (heartbeat.DEFAULT_STALE_SECONDS + 10)
    os.utime(p, (old, old))
    assert heartbeat.main([p]) == 1


def test_watchdog_exits_the_process_when_the_heartbeat_goes_stale(tmp_path, monkeypatch):
    """The whole point: a wedged loop must take the process down so the container restarts."""
    p = str(tmp_path / "hb")
    exits = []
    monkeypatch.setattr(heartbeat.os, "_exit", lambda code: exits.append(code))
    stop = threading.Event()

    try:
        heartbeat.start_watchdog(p, stale_seconds=0.05, check_interval=0.01, stop_event=stop)
        # start_watchdog touches up front, so it is fresh; let it go stale on its own.
        deadline = time.time() + 3
        while not exits and time.time() < deadline:
            time.sleep(0.02)
    finally:
        stop.set()

    assert exits == [1], "watchdog should have exited with status 1"


def test_watchdog_stays_quiet_while_the_loop_keeps_beating(tmp_path, monkeypatch):
    p = str(tmp_path / "hb")
    exits = []
    monkeypatch.setattr(heartbeat.os, "_exit", lambda code: exits.append(code))
    stop = threading.Event()

    try:
        heartbeat.start_watchdog(p, stale_seconds=1.0, check_interval=0.01, stop_event=stop)
        # A loop making progress keeps touching; the watchdog must not fire.
        for _ in range(30):
            heartbeat.touch(p)
            time.sleep(0.02)
    finally:
        stop.set()

    assert exits == [], "watchdog fired despite a live heartbeat"


def test_watchdog_touches_up_front_so_a_slow_start_does_not_trip_it(tmp_path):
    p = str(tmp_path / "hb")
    stop = threading.Event()
    try:
        assert heartbeat.is_fresh(p) is False
        heartbeat.start_watchdog(p, stale_seconds=60, check_interval=60, stop_event=stop)
        assert heartbeat.is_fresh(p) is True
    finally:
        stop.set()


def test_watchdog_can_be_retired_so_it_cannot_outlive_its_owner(tmp_path, monkeypatch):
    """A leaked watchdog would os._exit whatever process is still running. Guards the guard."""
    p = str(tmp_path / "hb")
    exits = []
    monkeypatch.setattr(heartbeat.os, "_exit", lambda code: exits.append(code))
    stop = threading.Event()

    thread = heartbeat.start_watchdog(p, stale_seconds=0.05, check_interval=0.01, stop_event=stop)
    stop.set()
    thread.join(timeout=2)

    assert not thread.is_alive(), "watchdog thread should retire once stopped"
    time.sleep(0.2)  # well past the stale window it would otherwise have fired on
    assert exits == [], "a stopped watchdog must never fire"
