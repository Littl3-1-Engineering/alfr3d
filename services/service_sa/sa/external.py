"""The nightly external-source exports: Home Assistant history and Gmail metadata (LF-0b).

Both sources keep their own history (Home Assistant ~10 days, Gmail indefinitely), so unlike the
MySQL tables they go straight into the Parquet lake with no operational copy in MySQL. They run
under the same export lock as the MySQL export so a manual backfill and the nightly job never
interleave, and each fails on its own: Home Assistant being down must not stop the mail sync, or
the silver rebuild after it.
"""

import logging

from sa import email_log, ha_history, lake

logger = logging.getLogger("SAExternal")

SOURCES = (
    ("ha_history", ha_history.export_ha_history),
    ("email", email_log.export_email),
)


def run_all(lake_dir=None, progress=None, only=None):
    """Export every external source. Returns {source: outcome-or-error-string}."""
    lake_dir = lake_dir or lake.LAKE_DIR
    outcomes = {}
    with lake._ExportLock(lake_dir):
        for name, export in SOURCES:
            if only and name not in only:
                continue
            try:
                outcomes[name] = export(lake_dir, progress=progress)
            except Exception as e:  # noqa: BLE001 -- one source failing must not stop the others
                logger.error(f"external export '{name}' failed: {e}")
                outcomes[name] = f"failed: {e}"
    return outcomes
