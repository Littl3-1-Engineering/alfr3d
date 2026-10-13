"""Disk, lake and MySQL growth monitoring (todo/sa/todo_disk_and_lake_monitoring.md).

sa-learner samples the host disk into `sa_storage_metrics` as `disk.root` (no new table, like the
`lake.<table>` rows): `row_count` = total bytes, `data_bytes` = bytes available to a non-root
process, `index_bytes` = 0. sa-awareness reads those rows back through `assess()` and
`SAEngine.check_disk_health` turns the result into a card. Nothing here deletes anything.
"""

import os
import shutil
from datetime import timedelta

DISK_TABLE = "disk.root"
LAKE_PREFIX = "lake."
# Docker named volumes live on the host root filesystem, so statvfs on the lake mount reports the
# real disk (verified 2026-10-09: matched `df /`).
DISK_PATH = os.environ.get("SA_LAKE_DIR", "/lake")

HISTORY_DAYS = 30
# A fresh install must not alert on a growth rate fitted to two points.
MIN_SAMPLES_FOR_TREND = 6
MIN_SPAN_DAYS_FOR_TREND = 5.0

WARN_FREE_FRACTION, WARN_FREE_BYTES, WARN_DAYS_LEFT = 0.20, 15 * 1024**3, 60
CRIT_FREE_FRACTION, CRIT_FREE_BYTES, CRIT_DAYS_LEFT = 0.10, 7 * 1024**3, 14
# Lake: this many times its own trailing weekly growth in the last week is a runaway exporter; the
# floor keeps a quiet lake (a few MB a week) from tripping on noise.
LAKE_RUNAWAY_FACTOR = 5.0
LAKE_RUNAWAY_MIN_BYTES = 200 * 1024**2
LAKE_SHARE_OF_FREE = 0.25

LEVELS = {"ok": 0, "warn": 1, "critical": 2}


def record_disk_sample(conn, path=None):
    """Insert one `disk.root` row. Returns (total_bytes, free_bytes)."""
    usage = shutil.disk_usage(path or DISK_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sa_storage_metrics (table_name, row_count, data_bytes, index_bytes, "
        "recorded_at) VALUES (%s, %s, %s, 0, NOW())",
        (DISK_TABLE, usage.total, usage.free),
    )
    conn.commit()
    return usage.total, usage.free


def load_samples(conn, now, days=HISTORY_DAYS):
    """[(recorded_at, total, free)] oldest first, `disk.root` rows from the last `days`."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT recorded_at, row_count, data_bytes FROM sa_storage_metrics "
        "WHERE table_name = %s AND recorded_at >= %s ORDER BY recorded_at",
        (DISK_TABLE, now - timedelta(days=days)),
    )
    return [(t, int(total), int(free)) for t, total, free in cursor.fetchall()]


def load_lake_totals(conn, now, days=HISTORY_DAYS):
    """[(recorded_at, total_lake_bytes)] oldest first. Each nightly run writes every table with
    the same second-resolution timestamp window, so rows are grouped by calendar day."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DATE(recorded_at), SUM(data_bytes) FROM sa_storage_metrics "
        "WHERE table_name LIKE %s AND recorded_at >= %s GROUP BY DATE(recorded_at) "
        "ORDER BY DATE(recorded_at)",
        (LAKE_PREFIX + "%", now - timedelta(days=days)),
    )
    return [(d, int(total)) for d, total in cursor.fetchall()]


def days_until_full(samples):
    """Days until free space runs out at the least-squares growth of used space over `samples`,
    or None with thin history or a flat/shrinking disk."""
    if len(samples) < MIN_SAMPLES_FOR_TREND:
        return None
    t0 = samples[0][0]
    xs = [(t - t0).total_seconds() / 86400.0 for t, _total, _free in samples]
    if xs[-1] < MIN_SPAN_DAYS_FOR_TREND:
        return None
    ys = [total - free for _t, total, free in samples]
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var_x
    if slope <= 0:
        return None
    return samples[-1][2] / slope


def _free_level(total, free, days_left):
    if (
        free < CRIT_FREE_FRACTION * total
        or free < CRIT_FREE_BYTES
        or (days_left is not None and days_left < CRIT_DAYS_LEFT)
    ):
        return "critical"
    if (
        free < WARN_FREE_FRACTION * total
        or free < WARN_FREE_BYTES
        or (days_left is not None and days_left < WARN_DAYS_LEFT)
    ):
        return "warn"
    return "ok"


def lake_runaway(lake_totals):
    """True when the lake grew LAKE_RUNAWAY_FACTOR x its trailing weekly rate in the last week."""
    if len(lake_totals) < 14:
        return False
    last_day, last_total = lake_totals[-1]
    week_ago = next((tot for d, tot in reversed(lake_totals) if (last_day - d).days >= 7), None)
    first_day, first_total = lake_totals[0]
    span_days = (last_day - first_day).days
    if week_ago is None or span_days < 14:
        return False
    recent = last_total - week_ago
    trailing_per_week = (week_ago - first_total) / ((span_days - 7) / 7.0)
    if recent < LAKE_RUNAWAY_MIN_BYTES:
        return False
    return trailing_per_week <= 0 or recent > LAKE_RUNAWAY_FACTOR * trailing_per_week


def _gb(n):
    return f"{n / 1024**3:.1f} GB"


def assess(samples, lake_totals):
    """None when there is no usable data, else {"level", "free", "total", "days_left",
    "lake_bytes", "because"}. Debounced: the card level is the *lower* of the latest sample's
    level and the previous one's, so a single odd reading can't raise it (samples arrive every
    few hours, so this is a real second reading, not the same one twice)."""
    if not samples:
        return None
    _t, total, free = samples[-1]
    if total <= 0:
        return None
    days_left = days_until_full(samples)
    level = _free_level(total, free, days_left)
    if len(samples) >= 2:
        prev = samples[:-1]
        _pt, ptotal, pfree = prev[-1]
        prev_level = _free_level(ptotal, pfree, days_until_full(prev)) if ptotal > 0 else "ok"
        level = min(level, prev_level, key=LEVELS.get)
    else:
        level = "ok"

    lake_bytes = lake_totals[-1][1] if lake_totals else 0
    because = [f"{_gb(free)} free of {_gb(total)} ({100.0 * free / total:.0f}%)"]
    if days_left is not None and days_left < 365:
        because.append(
            f"at the last {HISTORY_DAYS} days' growth, full in about {days_left:.0f} days"
        )
    lake_flag = None
    if lake_runaway(lake_totals):
        lake_flag = "runaway"
        because.append("lake grew over 5x its usual weekly rate this week")
    elif lake_bytes and lake_bytes > LAKE_SHARE_OF_FREE * free:
        lake_flag = "large"
        because.append(f"lake is {_gb(lake_bytes)}, over a quarter of the free space")
    if lake_flag and level == "ok":
        level = "warn"
    return {
        "level": level,
        "free": free,
        "total": total,
        "days_left": days_left,
        "lake_bytes": lake_bytes,
        "lake_flag": lake_flag,
        "because": because,
    }
