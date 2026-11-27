"""`routines.last_run` is a naive-UTC MySQL TIMESTAMP; the API must serialize it as explicit UTC
so clients (the Deck) convert it to local time instead of showing "21:17" for a 16:17 firing."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "service_api"))

from dependencies import _utc_iso  # noqa: E402


def test_naive_datetime_is_treated_as_utc():
    assert _utc_iso(datetime(2026, 11, 26, 21, 17, 0)) == "2026-11-26T21:17:00Z"


def test_aware_datetime_is_normalized_to_utc():
    est = timezone(timedelta(hours=-5))
    assert _utc_iso(datetime(2026, 11, 26, 16, 17, 0, tzinfo=est)) == "2026-11-26T21:17:00Z"


def test_non_datetime_falls_back_to_str():
    assert _utc_iso("2026-11-26 21:17:00") == "2026-11-26 21:17:00"
