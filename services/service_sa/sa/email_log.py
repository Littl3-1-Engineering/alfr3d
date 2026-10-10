"""Gmail message metadata -> Parquet bronze (LF-0b, todo/sa/todo_signal_inventory.md).

Email frequency, who writes, and what about, are things SA should learn from: a usual sender gone
silent, a burst from an unfamiliar one, the normal rhythm of a weekday inbox. ALFR3D only ever read
the top five *unread* messages for a card and kept none of it.

    <lake>/bronze/email_messages/date=YYYY-MM-DD/part-0.parquet      (date = received, UTC)
    columns: message_id, thread_id, received_utc, sender_name, sender_email, sender_domain,
             subject, labels, is_unread, size_estimate

**Metadata only. The body of a message is never requested** (`format=metadata`, headers `From`,
`Subject` and `Date`), and attachments are never touched. The subject line is stored because the
household asked for it. Stays on the lake volume on the NUC; nothing leaves the machine.

Gmail itself keeps the mail indefinitely, so unlike Home Assistant's history there is no loss clock
here. Every run lists the whole EMAIL_BACKFILL_DAYS window (12 months, a couple of seconds) and
fetches what is not stored yet, so the sync is **self-healing**: a message that failed once, or that
arrived while the job was down, is picked up on the next run instead of staying a permanent hole.
Messages from the last EMAIL_LOOKBACK_DAYS are fetched again every run to refresh their labels
(read, archived); older ones are immutable enough to leave alone. Merged by message id, so a re-run
changes nothing it shouldn't.

Uses the read-only Gmail scope the integration already holds. Spam and trash are excluded (Gmail's
default for list calls).

Quota: Gmail limits a user to 250 quota units/second and a metadata `get` costs 5. A batch of 50
was tried first and **Gmail rejected 19 of 50 with HTTP 429**, silently dropping a third of the mail
when those errors were treated as "message gone"; batches of 10 are accepted. Rate-limit and server
errors are retried per message with backoff, a 404 (deleted since it was listed) is skipped, and
anything still failing after the retries is counted and reported, never hidden.
"""

import logging
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from sa import lake

logger = logging.getLogger("SAEmailLog")

TABLE = "email_messages"
EMAIL_BACKFILL_DAYS = 365
EMAIL_LOOKBACK_DAYS = 2
LIST_PAGE_SIZE = 500
BATCH_SIZE = 10
BATCH_PAUSE_SECONDS = 0.5
MAX_RETRIES = 5

SCHEMA = pa.schema(
    [
        pa.field("message_id", pa.string()),
        pa.field("thread_id", pa.string()),
        pa.field("received_utc", pa.timestamp("us")),
        pa.field("sender_name", pa.string()),
        pa.field("sender_email", pa.string()),
        pa.field("sender_domain", pa.string()),
        pa.field("subject", pa.string()),
        pa.field("labels", pa.string()),
        pa.field("is_unread", pa.bool_()),
        pa.field("size_estimate", pa.int64()),
    ]
)
KEY = (0,)  # message_id


def _decode(value):
    """RFC 2047 header ('=?UTF-8?B?...?=') -> readable text; falls back to the raw value."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001 -- a malformed header must not lose the message
        return value


# Gmail's internalDate has been seen as -1 ms on a real message. Anything before this is not a real
# arrival time.
EARLIEST_PLAUSIBLE = datetime(2000, 1, 1)


def _received(message, headers):
    """When the message arrived: Gmail's internalDate, or if that is implausible, the message's own
    Date header (converted to UTC). None if neither is usable."""
    internal = message.get("internalDate")
    if internal is not None:
        received = datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc).replace(
            tzinfo=None
        )
        if received >= EARLIEST_PLAUSIBLE:
            return received
    try:
        received = parsedate_to_datetime(headers.get("date", ""))
        received = received.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None
    return received if received >= EARLIEST_PLAUSIBLE else None


def parse_message(message):
    """One Gmail `format=metadata` response -> a bronze row (or None if it has no usable date)."""
    headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    received = _received(message, headers)
    if received is None:
        return None
    # Parse the address first, then decode the display name: an RFC 2047 name decoded up front can
    # contain commas or quotes that confuse the address parser.
    name, address = parseaddr(headers.get("from", ""))
    name, address = _decode(name), (address or "").lower()
    labels = message.get("labelIds", [])
    return [
        message["id"],
        message.get("threadId", ""),
        received,
        name,
        address,
        address.rsplit("@", 1)[-1] if "@" in address else "",
        _decode(headers.get("subject", "")),
        ",".join(labels),
        "UNREAD" in labels,
        int(message.get("sizeEstimate") or 0),
    ]


def list_message_ids(service, query):
    """Every message id matching a Gmail search, following pagination."""
    ids, token = [], None
    while True:
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=LIST_PAGE_SIZE, pageToken=token)
            .execute(num_retries=MAX_RETRIES)
        )
        ids += [m["id"] for m in response.get("messages", [])]
        token = response.get("nextPageToken")
        if not token:
            return ids


def _status(exception):
    return getattr(getattr(exception, "resp", None), "status", None)


def _retryable(exception):
    """Rate limits and server hiccups are worth another try; a 404 (deleted) or a permission error
    will not change. A failure of the whole batch (no per-message status) is treated as transient.
    """
    status = _status(exception)
    if status is None:
        return True
    return status in (429, 500, 502, 503, 504) or (
        status == 403 and "rate" in str(exception).lower()
    )


def fetch_metadata(service, ids, progress=None, pause=BATCH_PAUSE_SECONDS, sleep=time.sleep):
    """Metadata rows for message ids, in small rate-limited batches. Returns (rows, stats) where
    stats = {"gone": messages Gmail no longer has, "failed": messages still failing after the
    retries}. Neither is silent: the caller logs both."""
    rows, stats = [], {"gone": 0, "failed": 0}
    for i in range(0, len(ids), BATCH_SIZE):
        pending = list(ids[i : i + BATCH_SIZE])
        results, gone = {}, set()
        for attempt in range(MAX_RETRIES):
            errors = {}

            def collect(request_id, response, exception, errors=errors):
                if exception is None:
                    results[request_id] = response
                else:
                    errors[request_id] = exception

            batch = service.new_batch_http_request(callback=collect)
            for message_id in pending:
                batch.add(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    ),
                    request_id=message_id,
                )
            try:
                batch.execute()
            except Exception as e:  # noqa: BLE001 -- the whole request failed: retry everything
                logger.warning(f"gmail batch failed ({e})")
                errors = {m: e for m in pending if m not in results}
            gone |= {m for m, e in errors.items() if not _retryable(e)}
            pending = [m for m in pending if m not in results and m not in gone]
            if not pending:
                break
            wait = min(2**attempt, 30)
            logger.warning(f"gmail: {len(pending)} message(s) rate-limited, retrying in {wait}s")
            sleep(wait)
        stats["gone"] += len(gone)
        stats["failed"] += len(pending)
        for message_id, message in results.items():
            row = parse_message(message)
            if row is not None:
                rows.append(row)
        if progress:
            progress()
        sleep(pause)
    return rows, stats


def _stored_messages(table_dir):
    """{message_id: received date} for everything already in bronze."""
    known = {}
    for part in Path(table_dir).glob("date=*/part-0.parquet"):
        day = part.parent.name.split("=", 1)[1]
        for message_id in pq.read_table(part, columns=["message_id"]).column(0).to_pylist():
            known[message_id] = day
    return known


def export_email(lake_dir=None, now_utc=None, progress=None, service=None, sleep=time.sleep):
    """Sync Gmail metadata into bronze. Returns {"rows", "days"} or {"skipped": reason}."""
    lake_dir = lake_dir or lake.LAKE_DIR
    if service is None:
        from googleapiclient.discovery import build

        from common import gmail_utils

        creds = gmail_utils.get_credentials()
        if not creds:
            return {"skipped": "no Gmail credentials"}
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    table_dir = Path(lake_dir) / "bronze" / TABLE
    table_dir.mkdir(parents=True, exist_ok=True)
    for stale in table_dir.glob(".tmp-date=*"):
        shutil.rmtree(stale, ignore_errors=True)

    # Always list the whole window: it is what makes the sync self-healing.
    window_start = datetime.combine(now_utc.date(), datetime.min.time()) - timedelta(
        days=EMAIL_BACKFILL_DAYS
    )
    query = f"after:{int(window_start.replace(tzinfo=timezone.utc).timestamp())}"
    ids = list_message_ids(service, query)

    known = _stored_messages(table_dir)
    refresh_from = (now_utc - timedelta(days=EMAIL_LOOKBACK_DAYS)).date().isoformat()
    to_fetch = [i for i in ids if i not in known or known[i] >= refresh_from]
    logger.info(
        f"gmail: {len(ids)} in the window, {len(known)} stored, fetching {len(to_fetch)} "
        f"({query})"
    )

    rows, stats = fetch_metadata(service, to_fetch, progress=progress, sleep=sleep)
    by_day = {}
    for row in rows:
        by_day.setdefault(row[2].date().isoformat(), []).append(row)
    for label, day_rows in by_day.items():
        lake.merge_partition(table_dir, label, SCHEMA, day_rows, KEY)
    if stats["failed"]:
        logger.warning(
            f"gmail: {stats['failed']} message(s) still failing after retries; "
            "the next run will try them again"
        )
    logger.info(f"gmail: {len(rows)} message(s) merged into {len(by_day)} day(s)")
    return {
        "rows": len(rows),
        "days": len(by_day),
        "listed": len(ids),
        "gone": stats["gone"],
        "failed": stats["failed"],
    }


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(message)s")
    with lake._ExportLock(lake.LAKE_DIR):
        print(export_email())
