"""Parquet bronze layer: a raw, append-only copy of every SA source table (LF-1b,
todo/sa/todo_lf1b_bronze.md).

MySQL stays the operational store (730-day EVENT retention, LF-0). This module copies it into a
columnar lake on the `sa_lake` volume so the learners can scan years of history in seconds with
DuckDB, outside the OLTP database. Silver and gold (LF-2) are rebuilt from bronze whenever their
cleaning logic changes, so bronze is deliberately raw: no cleaning, no joins, no dropped rows.

Layout (Hive-style, zstd):
    <lake>/bronze/<table>/date=YYYY-MM-DD/part-0.parquet        event tables, one file per UTC day
    <lake>/bronze/_snapshots/<table>/date=YYYY-MM-DD/part-0.parquet   daily snapshot of a
                                                                 current-state table

Incremental export needs no state table: the resume point is derived from the partitions already
on disk. Each run rewrites every day from (last exported day - LOOKBACK_DAYS) onward, which makes
a run idempotent (re-running adds nothing) and picks up rows that landed in the last partition
after it was written. The same code is the backfill: with no partitions on disk it starts from the
beginning of the table.

Assumptions, stated so a violation is easy to spot:
- The MySQL session clock is UTC (true on the NUC: NOW() == UTC_TIMESTAMP()), so naive DATETIMEs
  are UTC and day partitions are UTC days.
- Rows are not inserted more than LOOKBACK_DAYS behind the newest partition. device_history's
  timestamp is NOW() at insert, so that holds there. household_events.occurred_at comes from the
  producer's event time and could in principle lag; a late row older than the lookback would be
  missed until the next full backfill.

Secrets and PII never enter the lake: see EXCLUDED_COLUMNS and _assert_no_secret_columns().
"""

import fcntl
import logging
import os
import re
import shutil
import sys
from datetime import date, datetime, time as dtime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import orjson
import pyarrow as pa
import pyarrow.parquet as pq
import pymysql

logger = logging.getLogger("SALake")

LAKE_DIR = os.environ.get("SA_LAKE_DIR", "/lake")

# Re-export this many days before the newest partition on every run.
LOOKBACK_DAYS = 1

# (source table, the timestamp column its rows are partitioned by). Every one of these is
# append-only history except calendar_events, whose forward window is deleted and re-inserted on
# each sync: partitioning it by start_time and rewriting from the lookback point onward captures
# each event once its day arrives, with its final form.
EVENT_TABLES = (
    ("device_history", "timestamp"),
    ("household_events", "occurred_at"),
    ("card_interactions", "occurred_at"),
    ("attention_telemetry_history", "reported_at"),
    ("device_location_history", "captured_at"),
    ("smarthome_sensor_history", "recorded_at"),
    ("calendar_events", "start_time"),
    ("environment_history", "recorded_at"),
    ("device_command_history", "issued_at"),
    ("listening_history", "played_at"),
    ("deck_context_history", "observed_at"),
)

# Current-state tables: no history of their own, so a daily snapshot is how user types (resident
# vs. guest), device ownership and HA device churn are known for a past date.
SNAPSHOT_TABLES = (
    "user",
    "user_types",
    "states",
    "device",
    "smarthome_devices",
    "routines",
    "environment",
)

# Columns that are secrets or contact PII, or can carry a credential, and so never leave MySQL.
# Reasons: password_hash/email/about_me (credential / PII), device.stream_url (camera URLs embed
# credentials), smarthome_devices.last_state (HA entity attributes include signed
# entity_picture tokens; sensor values are already in smarthome_sensor_history),
# routines.actions (email actions carry recipients and bodies).
EXCLUDED_COLUMNS = {
    "user": {"password_hash", "email", "about_me"},
    "device": {"stream_url"},
    "smarthome_devices": {"last_state"},
    "routines": {"actions"},
}

# Backstop for the explicit list above: a column that looks like a secret is refused outright, so
# a future migration adding e.g. `api_token` to a snapshot table fails loudly instead of leaking.
_SECRET_COLUMN = re.compile(r"password|passwd|token|secret|psk|credential|api_?key", re.IGNORECASE)

_INT_TYPES = {"tinyint", "smallint", "mediumint", "int", "integer", "bigint", "year"}
_FLOAT_TYPES = {"float", "double", "decimal", "numeric"}


def arrow_type(data_type):
    """Arrow type for a MySQL DATA_TYPE. DECIMAL becomes float64 (every DECIMAL here is a
    coordinate that fits a double); DATETIME/TIMESTAMP stay naive microsecond timestamps (UTC by
    convention); TIME, JSON, ENUM and all text become strings."""
    dt = data_type.lower()
    if dt in _INT_TYPES:
        return pa.int64()
    if dt in _FLOAT_TYPES:
        return pa.float64()
    if dt in ("datetime", "timestamp"):
        return pa.timestamp("us")
    if dt == "date":
        return pa.date32()
    if dt in ("char", "varchar", "text", "tinytext", "mediumtext", "longtext", "json", "enum",
              "set", "time"):  # fmt: skip
        return pa.string()
    raise ValueError(f"No Arrow mapping for MySQL type '{data_type}'")


def _convert(value):
    """Python value -> something pyarrow accepts for the column types above."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, timedelta):  # MySQL TIME
        return str(value)
    if isinstance(value, (dict, list)):
        return orjson.dumps(value).decode()
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


def _assert_no_secret_columns(table, columns):
    bad = [c for c in columns if _SECRET_COLUMN.search(c)]
    if bad:
        raise ValueError(
            f"Refusing to export {table}: column(s) {bad} look like secrets. Add them to "
            "EXCLUDED_COLUMNS in sa/lake.py (or rename them) after deciding they are safe."
        )


def _connect():
    return pymysql.connect(
        host=os.environ.get("MYSQL_DATABASE"),
        user=os.environ.get("MYSQL_USER"),
        passwd=os.environ.get("MYSQL_PSWD"),
        db=os.environ.get("MYSQL_NAME"),
    )


def _table_columns(conn, table):
    """[(column name, MySQL DATA_TYPE)] in table order."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
        (table,),
    )
    return [(name, data_type) for name, data_type in cursor.fetchall()]


def _stream_rows(conn, table, columns, ts_col, since):
    """Rows with ts >= since, oldest first, streamed (server-side cursor) so a multi-million-row
    backfill never sits in memory. Identifiers come from information_schema / the constants above,
    never from user input; the value is parameterized."""
    cursor = conn.cursor(pymysql.cursors.SSCursor)
    cols = ", ".join(f"`{c}`" for c in columns)
    cursor.execute(
        f"SELECT {cols} FROM `{table}` WHERE `{ts_col}` >= %s ORDER BY `{ts_col}`", (since,)
    )
    try:
        yield from cursor
    finally:
        cursor.close()


def _parse_day(name):
    match = re.fullmatch(r"date=(\d{4}-\d{2}-\d{2})", name)
    return date.fromisoformat(match.group(1)) if match else None


def _utc_today():
    return datetime.now(timezone.utc).date()


def _resume_since(table_dir, today):
    """Where to start reading: LOOKBACK_DAYS before the newest partition on disk, or None for a
    full backfill. Capped at today so a future-dated partition (an upcoming calendar event) can't
    push the resume point past days that haven't been exported yet."""
    days = sorted(d for d in (_parse_day(p.name) for p in table_dir.glob("date=*")) if d)
    if not days:
        return None
    return datetime.combine(min(days[-1], today) - timedelta(days=LOOKBACK_DAYS), dtime.min)


def _write_partition(table_dir, label, schema, rows):
    """Write one day's rows as table_dir/date=<label>/part-0.parquet, replacing any previous
    version of that day. Built in a temp dir and swapped in, so a crash mid-write can never leave
    a half-written partition under a real name."""
    final = table_dir / f"date={label}"
    tmp = table_dir / f".tmp-date={label}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    columns = list(zip(*rows))
    arrays = [pa.array(list(col), type=field.type) for col, field in zip(columns, schema)]
    pq.write_table(
        pa.Table.from_arrays(arrays, schema=schema), tmp / "part-0.parquet", compression="zstd"
    )
    shutil.rmtree(final, ignore_errors=True)
    os.replace(tmp, final)


HORIZON_FILE = "_exported_through.txt"


def write_horizon(table_dir, moment):
    """Record when an external source was last exported successfully (naive UTC). A state that
    hasn't changed since Tuesday is still held *now*; without this the silver layer couldn't tell
    "unchanged" from "we stopped looking", and would have to guess where each interval ends."""
    Path(table_dir).mkdir(parents=True, exist_ok=True)
    (Path(table_dir) / HORIZON_FILE).write_text(moment.replace(microsecond=0).isoformat())


def read_horizon(table_dir):
    """The datetime written by write_horizon(), or None if the source was never exported."""
    try:
        return datetime.fromisoformat((Path(table_dir) / HORIZON_FILE).read_text().strip())
    except (OSError, ValueError):
        return None


def merge_partition(table_dir, label, schema, rows, key_indexes):
    """Merge `rows` into date=<label>: union with whatever the partition already holds, deduped by
    the key columns (a newer row replaces an older one with the same key), written atomically.

    The MySQL exports rewrite a whole day because MySQL is the source of truth for that day. The
    external sources (Home Assistant, Gmail) re-deliver overlapping windows and, for Home Assistant,
    start-of-window anchor states that belong to an older day, so those partitions are merged, not
    replaced. Idempotent: merging the same rows twice leaves the partition unchanged."""
    final = Path(table_dir) / f"date={label}" / "part-0.parquet"
    names = schema.names
    merged = {}
    if final.exists():
        for record in pq.read_table(final).to_pylist():
            row = [record.get(n) for n in names]
            merged[tuple(row[i] for i in key_indexes)] = row
    for row in rows:
        merged[tuple(row[i] for i in key_indexes)] = row
    _write_partition(Path(table_dir), label, schema, list(merged.values()))
    return len(merged)


def _schema_for(columns):
    return pa.schema([pa.field(name, arrow_type(data_type)) for name, data_type in columns])


def export_table(conn, table, ts_col, lake_dir=None, progress=None, today=None):
    """Export one event table. Returns {"table", "since", "days", "rows"} for this run's writes."""
    lake = Path(lake_dir or LAKE_DIR)
    table_dir = lake / "bronze" / table
    table_dir.mkdir(parents=True, exist_ok=True)
    for stale in table_dir.glob(".tmp-date=*"):
        shutil.rmtree(stale, ignore_errors=True)

    columns = _table_columns(conn, table)
    names = [name for name, _ in columns]
    _assert_no_secret_columns(table, names)
    schema = _schema_for(columns)
    ts_index = names.index(ts_col)
    since = _resume_since(table_dir, today or _utc_today())

    days_written = rows_written = 0
    current_day, buffer = None, []

    def flush():
        nonlocal days_written, rows_written
        if buffer:
            _write_partition(table_dir, current_day.isoformat(), schema, buffer)
            days_written += 1
            rows_written += len(buffer)
            if progress:
                progress()

    stream_from = since or datetime(1970, 1, 1)
    for row in _stream_rows(conn, table, names, ts_col, stream_from):
        row = [_convert(v) for v in row]
        day = row[ts_index].date()
        if day != current_day:
            flush()
            current_day, buffer = day, []
        buffer.append(row)
    flush()
    logger.info(
        f"bronze {table}: {rows_written} rows in {days_written} day(s) "
        f"since {since.date() if since else 'the beginning'}"
    )
    return {"table": table, "since": since, "days": days_written, "rows": rows_written}


def export_snapshot(conn, table, lake_dir=None, today=None):
    """Write today's full snapshot of a current-state table (secrets excluded), replacing an
    earlier snapshot from the same day."""
    lake = Path(lake_dir or LAKE_DIR)
    table_dir = lake / "bronze" / "_snapshots" / table
    table_dir.mkdir(parents=True, exist_ok=True)
    excluded = EXCLUDED_COLUMNS.get(table, set())
    columns = [(n, t) for n, t in _table_columns(conn, table) if n not in excluded]
    names = [n for n, _ in columns]
    _assert_no_secret_columns(table, names)
    cursor = conn.cursor()
    cursor.execute("SELECT " + ", ".join(f"`{c}`" for c in names) + f" FROM `{table}`")
    rows = [[_convert(v) for v in row] for row in cursor.fetchall()]
    if rows:
        _write_partition(table_dir, (today or _utc_today()).isoformat(), _schema_for(columns), rows)
    logger.info(f"bronze snapshot {table}: {len(rows)} rows")
    return {"table": table, "rows": len(rows)}


class _ExportLock:
    """One exporter at a time (the nightly job and a manual backfill must not interleave their
    partition rewrites). Non-blocking: a second caller gets a clear error instead of waiting."""

    def __init__(self, lake_dir):
        Path(lake_dir).mkdir(parents=True, exist_ok=True)
        self._path = Path(lake_dir) / ".export.lock"
        self._handle = None

    def __enter__(self):
        self._handle = open(self._path, "w")
        try:
            fcntl.flock(self._handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._handle.close()
            raise RuntimeError("Another bronze export is already running") from None
        return self

    def __exit__(self, *exc):
        fcntl.flock(self._handle, fcntl.LOCK_UN)
        self._handle.close()


def partition_stats(lake_dir=None):
    """{table: {"rows": n, "bytes": n, "days": n}} read from Parquet footers (no data scan)."""
    lake = Path(lake_dir or LAKE_DIR) / "bronze"
    stats = {}
    for table_dir in sorted(p for p in lake.glob("*") if p.is_dir()):
        targets = (
            [(f"snapshot.{p.name}", p) for p in sorted((table_dir).glob("*")) if p.is_dir()]
            if table_dir.name == "_snapshots"
            else [(table_dir.name, table_dir)]
        )
        for name, directory in targets:
            files = list(directory.glob("date=*/part-*.parquet"))
            stats[name] = {
                "rows": sum(pq.ParquetFile(f).metadata.num_rows for f in files),
                "bytes": sum(f.stat().st_size for f in files),
                "days": len(files),
            }
    return stats


def record_lake_sizes(conn, lake_dir=None):
    """Insert the lake's per-table size into sa_storage_metrics (no new table: table_name carries
    a `lake.` prefix, row_count/data_bytes the Parquet rows/bytes, index_bytes 0) so lake growth is
    tracked alongside the MySQL tables it copies."""
    stats = partition_stats(lake_dir)
    cursor = conn.cursor()
    for name, s in stats.items():
        cursor.execute(
            "INSERT INTO sa_storage_metrics (table_name, row_count, data_bytes, index_bytes, "
            "recorded_at) VALUES (%s, %s, %s, 0, NOW())",
            (f"lake.{name}"[:64], s["rows"], s["bytes"]),
        )
    conn.commit()
    return stats


def run_export(lake_dir=None, progress=None, tables=None):
    """Nightly job (and the backfill): every event table, then today's snapshots, then lake sizes.
    One failing table is logged and skipped so it can't block the rest."""
    lake_dir = lake_dir or LAKE_DIR
    results, failures = [], []
    with _ExportLock(lake_dir):
        conn = _connect()
        try:
            for table, ts_col in EVENT_TABLES:
                if tables and table not in tables:
                    continue
                try:
                    results.append(export_table(conn, table, ts_col, lake_dir, progress))
                except Exception as e:  # noqa: BLE001 -- keep exporting the other tables
                    logger.error(f"bronze export of {table} failed: {e}")
                    failures.append(table)
            for table in SNAPSHOT_TABLES:
                if tables and table not in tables:
                    continue
                try:
                    export_snapshot(conn, table, lake_dir)
                    if progress:
                        progress()
                except Exception as e:  # noqa: BLE001
                    logger.error(f"bronze snapshot of {table} failed: {e}")
                    failures.append(f"snapshot:{table}")
            try:
                record_lake_sizes(conn, lake_dir)
            except Exception as e:  # noqa: BLE001 -- size tracking is best-effort
                logger.error(f"recording lake sizes failed: {e}")
        finally:
            conn.close()
    return {"exported": results, "failures": failures}


def verify(lake_dir=None, today=None):
    """Compare per-day row counts, MySQL vs. the lake, for every event table. Returns a list of
    mismatch strings, empty when they agree. Today's partition is excluded: rows keep arriving
    between the export and this count."""
    lake = Path(lake_dir or LAKE_DIR) / "bronze"
    today = today or _utc_today()
    problems = []
    conn = _connect()
    try:
        for table, ts_col in EVENT_TABLES:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT DATE(`{ts_col}`), COUNT(*) FROM `{table}` GROUP BY DATE(`{ts_col}`)"
            )
            mysql_counts = {d: n for d, n in cursor.fetchall() if d < today}
            lake_counts = {}
            for part in (lake / table).glob("date=*/part-*.parquet"):
                day = _parse_day(part.parent.name)
                if day and day < today:
                    lake_counts[day] = (
                        lake_counts.get(day, 0) + pq.ParquetFile(part).metadata.num_rows
                    )
            for day in sorted(set(mysql_counts) | set(lake_counts)):
                if mysql_counts.get(day, 0) != lake_counts.get(day, 0):
                    problems.append(
                        f"{table} {day}: mysql={mysql_counts.get(day, 0)} "
                        f"lake={lake_counts.get(day, 0)}"
                    )
    finally:
        conn.close()
    return problems


if __name__ == "__main__":
    logging.basicConfig(
        stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(name)s - %(message)s"
    )
    command = sys.argv[1] if len(sys.argv) > 1 else "export"
    if command in ("export", "backfill"):  # same code: with an empty lake it IS the backfill
        outcome = run_export(tables=set(sys.argv[2:]) or None)
        print(f"failures: {outcome['failures'] or 'none'}")
        sys.exit(1 if outcome["failures"] else 0)
    elif command == "verify":
        mismatches = verify()
        print("\n".join(mismatches) if mismatches else "OK: lake matches MySQL for every past day")
        sys.exit(1 if mismatches else 0)
    elif command == "stats":
        for name, s in partition_stats().items():
            size_mb = s["bytes"] / 1048576
            print(f"{name:40s} {s['rows']:>10,} rows {size_mb:>8.1f} MB {s['days']:>4} days")
    else:
        print("usage: python -m sa.lake export|backfill [table ...] | verify | stats")
        sys.exit(2)
