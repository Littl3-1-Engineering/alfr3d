#!/usr/bin/python

"""Re-export of `common.day_mood` -- the implementation moved there so service_api can serve the
same day-mood facet (todo/todo_context_exchange_protocol.md Phase 3). Kept so existing daemon
imports (`mood_utils.get_day_mood`) don't change."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../common"))
from common.day_mood import (  # noqa: E402,F401
    _BASE_ENERGY_BY_TIME_OF_DAY,
    _WEEKEND_DAYS,
    _WEEKEND_ENERGY_BONUS,
    _bucket_time_of_day,
    get_day_mood,
)
