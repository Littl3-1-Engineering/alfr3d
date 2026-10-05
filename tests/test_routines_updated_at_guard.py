"""`routines.updated_at` feeds the cross-surface-continuity "routine edited recently" card
(`check_cross_surface_continuity`). MySQL bumps it on *any* UPDATE, so every system write
(daemon firing/re-arming a routine, the sunrise/sunset sync, run-now) must pin it with
`updated_at = updated_at`, or the card fires whenever a routine merely runs.

Only the user-edit path (the PATCH route's dynamically built UPDATE) may bump it.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYSTEM_WRITERS = [
    "services/service_environment/weather_util.py",
    "services/service_daemon/utils/util_routines.py",
    "services/service_api/routes/routines.py",
]


def _static_updates(path):
    src = (ROOT / path).read_text()
    # Adjacent string literals are concatenated, so join them before matching.
    joined = re.sub(r'"\s*\n\s*"', "", src)
    stmts = re.findall(r'"(UPDATE routines SET [^"]*)"', joined)
    # The PATCH route's f-string builds its SET list dynamically -- that is the user-edit path.
    return [s for s in stmts if "{" not in s]


def test_system_writers_do_not_bump_updated_at():
    found = 0
    for path in SYSTEM_WRITERS:
        for stmt in _static_updates(path):
            found += 1
            assert "updated_at = updated_at" in stmt, f"{path}: {stmt}"
    assert found == 4
