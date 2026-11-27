"""Health cards: integration probes, disk, unread email.

Step 4a of the engine.py split (todo/sa/todo_parallel_capture_track.md, item 4): the constants and
the three `check_*` methods moved verbatim out of engine.py as `HealthCards`, which `SAEngine`
inherits. engine re-exports the constants and the two state dicts (the same objects, so
`patch.dict(engine.SYSTEM_HEALTH_STATE, ...)` still reaches this code). Shared module objects
(`disk`, `time`, `gmail_utils`, `pymysql`) are patched by attribute and are unaffected by the move;
`get_producer` is looked up in THIS module, so tests patch `sa.health_cards.get_producer`
(the `sa.` import path engine uses, not `services.service_sa.sa.`).
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone

import pymysql
from sa import disk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_producer, gmail_utils  # noqa: E402

logger = logging.getLogger("SALog")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")

# check_system_health(): how often an integration (Home Assistant / SmartThings) is probed, and
# how many probes in a row must fail before the card fires. A probe is a network call with a
# 10s timeout, so it must not run every ~60s cycle; two consecutive failures (~10 min) keeps a
# single blip or an HA restart from raising an urgent card.
SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS = 300
SYSTEM_HEALTH_FAILURES_BEFORE_ALERT = 2

# (key, display name, common module, is-configured fn, probe fn, what an outage means) -- an
# unconfigured integration is never probed or alerted on. The last field is the card's
# consequence clause, so it says what actually breaks (devices read offline, the map goes blank).
SYSTEM_HEALTH_INTEGRATIONS = (
    (
        "home_assistant",
        "Home Assistant",
        "ha_utils",
        "is_ha_configured",
        "test_ha_connection",
        "synced devices will read offline",
    ),
    (
        "smartthings",
        "SmartThings",
        "st_utils",
        "is_st_configured",
        "test_st_connection",
        "synced devices will read offline",
    ),
    (
        "map_tiles",
        "Map tiles",
        "map_tiles_utils",
        "is_map_tiles_configured",
        "test_map_tiles",
        "the dashboard map will show a blank or watermarked basemap",
    ),
)

# check_disk_health(): sa-learner samples the disk every few hours, so the rule re-reads the
# history at most this often; the critical tier speaks at most once per cooldown.
DISK_HEALTH_CHECK_INTERVAL_SECONDS = 900
DISK_HEALTH_SPEAK_COOLDOWN_SECONDS = 24 * 3600
DISK_HEALTH_STATE = {"checked": 0.0, "result": None, "spoke": 0.0}

# check_backup_health(): same cadence as the disk rule; never speaks (a stale backup is a
# heads-up, not an emergency, and the card stays up until a fresh dump lands).
BACKUP_HEALTH_CHECK_INTERVAL_SECONDS = 900
BACKUP_HEALTH_STATE = {"checked": 0.0, "newest": None}

# Per-integration probe state: {key: {"failures": int, "last_probe": float}}. In-memory only --
# a restart just re-probes, and the alert needs fresh consecutive failures anyway.
SYSTEM_HEALTH_STATE = {}


class HealthCards:
    def check_system_health(self, frame=None):
        """Urgent card when a configured integration (Home Assistant, SmartThings) has failed
        SYSTEM_HEALTH_FAILURES_BEFORE_ALERT consecutive probes. SA had no way to say "I'm blind"
        -- an HA outage just made every synced device read offline with nothing on the dashboard
        explaining why.

        Probes are rate-limited to SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS per integration (each is
        a network call with a 10s timeout); between probes the last result stands. An
        unconfigured integration is skipped entirely, never alerted on. Sets `urgent`, so
        decide_displays() never suppresses it. Not a frame field (SA-4) -- it probes external
        services rather than reading shared state.
        """
        from common import ha_utils, map_tiles_utils, st_utils

        modules = {
            "ha_utils": ha_utils,
            "st_utils": st_utils,
            "map_tiles_utils": map_tiles_utils,
        }
        now = time.time()
        down = []
        for (
            key,
            name,
            module_name,
            configured_fn,
            probe_fn,
            impact,
        ) in SYSTEM_HEALTH_INTEGRATIONS:
            state = SYSTEM_HEALTH_STATE.setdefault(key, {"failures": 0, "last_probe": 0.0})
            try:
                if now - state["last_probe"] >= SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS:
                    state["last_probe"] = now
                    module = modules[module_name]
                    if not getattr(module, configured_fn)():
                        state["failures"] = 0
                    elif getattr(module, probe_fn)()[0]:
                        state["failures"] = 0
                    else:
                        state["failures"] += 1
            except Exception as e:
                # A broken probe must not take the whole SA cycle down, and must not count as
                # the integration being down either -- that would be a false urgent alert.
                logger.error(f"System health probe for {key} failed: {e}")
            if state["failures"] >= SYSTEM_HEALTH_FAILURES_BEFORE_ALERT:
                down.append((key, name, state["failures"], impact))

        if not down:
            return None
        names = ", ".join(name for _key, name, _n, _impact in down)
        impacts = "; ".join(dict.fromkeys(impact for _key, _name, _n, impact in down))
        minutes = SYSTEM_HEALTH_PROBE_INTERVAL_SECONDS // 60
        return {
            "mode": "system_health",
            "content": f"{names} unreachable — {impacts}",
            "priority": 2.2,
            "urgent": True,
            "data": {
                "unreachable": [key for key, _name, _n, _impact in down],
                "because": [
                    f"{name}: {n} consecutive failed checks (every {minutes} min)"
                    for _key, name, n, _impact in down
                ],
            },
        }

    def check_disk_health(self, frame=None):
        """Card when host disk, the Parquet lake or MySQL growth is running out of room, from the
        `disk.root` and `lake.*` rows sa-learner writes to sa_storage_metrics (sa/disk.py).

        warn is an ambient card; critical sets `urgent` (never suppressed) and speaks once a day.
        Debounced by sa.disk.assess() -- two consecutive samples must agree -- and the history
        read is cached for DISK_HEALTH_CHECK_INTERVAL_SECONDS. Never deletes anything: the card
        only says what the numbers are.
        """
        del frame
        now = time.time()
        state = DISK_HEALTH_STATE
        if now - state["checked"] >= DISK_HEALTH_CHECK_INTERVAL_SECONDS:
            state["checked"] = now
            db = None
            try:
                db = pymysql.connect(
                    host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
                )
                utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
                state["result"] = disk.assess(
                    disk.load_samples(db, utc_now),
                    disk.load_lake_totals(db, utc_now),
                    disk.load_host_usage(db, utc_now),
                )
            except Exception as e:
                # Keep the last result: a DB blip must not clear or raise a disk alert.
                logger.error(f"Disk health check error: {e}")
            finally:
                if db:
                    db.close()
        result = state["result"]
        if not result or result["level"] == "ok":
            return None

        critical = result["level"] == "critical"
        free_gb = result["free"] / 1024**3
        if critical and now - state["spoke"] >= DISK_HEALTH_SPEAK_COOLDOWN_SECONDS:
            p = get_producer()
            if p:
                p.send(
                    "speak",
                    (
                        f"Heads up, the server is down to {free_gb:.0f} gigabytes of free disk."
                        " It needs some cleaning soon."
                    ).encode("utf-8"),
                )
                state["spoke"] = now
        return {
            "mode": "disk_health",
            "content": (
                f"Disk space {'critically ' if critical else ''}low: {free_gb:.1f} GB free"
                + (
                    f", full in about {result['days_left']:.0f} days"
                    if result["days_left"] is not None and result["days_left"] < 365
                    else ""
                )
            ),
            "priority": 2.1 if critical else 5.9,
            **({"urgent": True} if critical else {}),
            "data": {
                "level": result["level"],
                "free_bytes": result["free"],
                "total_bytes": result["total"],
                "days_left": result["days_left"],
                "lake_bytes": result["lake_bytes"],
                "because": result["because"],
            },
        }

    def check_backup_health(self, frame=None):
        """Card when the newest daily DB backup is over 36 h old (ambient) or 96 h (urgent).

        Failures of setup/db_backup_daily.sh are otherwise visible only in ~/db_backups/backup.log
        (cron has no mail here). The host snapshot (setup/host_usage.sh) records the newest
        dump's mtime into sa_storage_metrics; the age is computed here from that fixed mtime, so
        it keeps growing even if the snapshot cron itself stops. No card when no daily backup
        has ever been seen. Read-only; never speaks.
        """
        del frame
        now = time.time()
        state = BACKUP_HEALTH_STATE
        if now - state["checked"] >= BACKUP_HEALTH_CHECK_INTERVAL_SECONDS:
            state["checked"] = now
            db = None
            try:
                db = pymysql.connect(
                    host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
                )
                utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
                state["newest"] = disk.load_backup_newest(db, utc_now)
            except Exception as e:
                # Keep the last reading: a DB blip must not clear or raise a backup alert.
                logger.error(f"Backup health check error: {e}")
            finally:
                if db:
                    db.close()
        result = disk.assess_backups(state["newest"], now)
        if not result or result["level"] == "ok":
            return None
        critical = result["level"] == "critical"
        return {
            "mode": "backup_health",
            "content": (
                f"Database backup {'badly ' if critical else ''}overdue: "
                f"last good one is {result['age_hours']:.0f} hours old"
            ),
            "priority": 2.15 if critical else 5.85,
            **({"urgent": True} if critical else {}),
            "data": {
                "level": result["level"],
                "age_hours": round(result["age_hours"], 1),
                "newest_epoch": result["newest"],
                "because": result["because"],
            },
        }

    def check_emails(self, frame=None):
        """Check for unread emails using Gmail utils. Not a frame field (SA-4) -- not
        duplicated by any other rule, so its own direct Gmail call stays as-is.
        `frame` defaults to None (unused) because perform_waking_hours_tasks() also
        calls this directly, outside decide_displays()'s per-cycle frame, for its own
        separate "check Gmail" waking-hours routine."""
        del frame
        emails = gmail_utils.check_unread_emails()
        if emails:
            email = emails[0]  # Take first
            content_lines = f"From: {email['sender']}, Subject: {email['subject']}"
            content = f"Unread Email - {content_lines} | Total Unread: {len(emails)}"
            return {"mode": "email", "content": content, "priority": 4}
