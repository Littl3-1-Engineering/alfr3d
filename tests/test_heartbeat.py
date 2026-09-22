"""Unit tests for common.heartbeat -- the liveness file the consumer services touch and
their container HEALTHCHECKs read.

The point of this module is that a wedged consumer keeps its process alive, so these cover
the states a healthcheck actually has to tell apart: never started, making progress, and
stopped making progress.
"""

import os
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
