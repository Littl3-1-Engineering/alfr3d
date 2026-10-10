"""Tests for LF-0b: the external-source exports (Home Assistant history, Gmail metadata) and the
merge helper they share. HA and Gmail are replaced by fakes shaped like the real responses (probed
on the NUC on 2026-10-10), so what is checked is OUR handling: what is requested, what is stored,
what is deliberately not, and that re-running changes nothing.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from services.service_sa.sa import email_log, external, ha_history, lake

NOW = datetime(2026, 10, 10, 12, 0)
CONFIG = {"ha_url": "http://ha.local:8123/", "ha_token": "tok"}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _point(entity, state, changed, updated=None):
    stamp = changed.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00")
    return {
        "entity_id": entity,
        "state": state,
        "attributes": {},
        "last_changed": stamp,
        "last_updated": (updated or changed).strftime("%Y-%m-%dT%H:%M:%S.000000+00:00"),
    }


class FakeHA:
    """Answers /api/states and /api/history/period like HA 2023.8 does: an entity list is
    required, and each requested entity returns its points inside the window plus the state in
    effect at the window's start."""

    def __init__(self, history, entities=None):
        self.history = history  # {entity_id: [(changed_datetime, state)]}
        self.entities = entities or sorted(history)
        self.calls = []

    def __call__(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        if url.endswith("/api/states"):
            return FakeResponse([{"entity_id": e, "state": "x"} for e in self.entities])
        start = datetime.fromisoformat(url.rsplit("/", 1)[1]).replace(tzinfo=None)
        end = datetime.fromisoformat(params["end_time"]).replace(tzinfo=None)
        series = []
        for entity in params["filter_entity_id"].split(","):
            points = sorted(self.history.get(entity, []))
            anchor = [p for p in points if p[0] <= start][-1:]
            inside = [p for p in points if start < p[0] <= end]
            # HA reports the state in effect at the start of the window, stamped at that start.
            rows = [_point(entity, state, start) for _changed, state in anchor]
            rows += [_point(entity, state, changed) for changed, state in inside]
            if rows:
                series.append(rows)
        return FakeResponse(series)

    def history_calls(self):
        return [c for c in self.calls if "/api/history/period/" in c[0]]


def _partitions(lake_dir, table):
    out = {}
    for part in (lake_dir / "bronze" / table).glob("date=*/part-0.parquet"):
        out[part.parent.name.split("=")[1]] = pq.read_table(part).to_pylist()
    return out


class TestMergePartition:
    SCHEMA = pa.schema([pa.field("k", pa.string()), pa.field("v", pa.int64())])

    def test_unions_with_existing_and_the_newer_row_wins(self, tmp_path):
        lake.merge_partition(tmp_path, "2026-10-10", self.SCHEMA, [["a", 1], ["b", 2]], (0,))

        merged = lake.merge_partition(
            tmp_path, "2026-10-10", self.SCHEMA, [["b", 20], ["c", 3]], (0,)
        )

        rows = pq.read_table(tmp_path / "date=2026-10-10" / "part-0.parquet").to_pylist()
        assert merged == 3
        assert {r["k"]: r["v"] for r in rows} == {"a": 1, "b": 20, "c": 3}

    def test_merging_the_same_rows_twice_changes_nothing(self, tmp_path):
        rows = [["a", 1], ["b", 2]]
        lake.merge_partition(tmp_path, "2026-10-10", self.SCHEMA, rows, (0,))
        before = pq.read_table(tmp_path / "date=2026-10-10" / "part-0.parquet").to_pylist()

        lake.merge_partition(tmp_path, "2026-10-10", self.SCHEMA, rows, (0,))

        assert pq.read_table(tmp_path / "date=2026-10-10" / "part-0.parquet").to_pylist() == before

    def test_a_composite_key_distinguishes_rows(self, tmp_path):
        schema = pa.schema(
            [pa.field("e", pa.string()), pa.field("t", pa.int64()), pa.field("s", pa.string())]
        )
        lake.merge_partition(
            tmp_path, "d", schema, [["x", 1, "on"], ["x", 2, "off"], ["y", 1, "on"]], (0, 1)
        )

        assert len(pq.read_table(tmp_path / "date=d" / "part-0.parquet")) == 3


class TestHaEntities:
    def test_lists_entities_but_never_the_legacy_pushbullet_ones(self):
        ha = FakeHA(
            {}, entities=["sensor.pushbullet_title", "sensor.pushbullet_body", "weather.home"]
        )

        ids = ha_history.list_entities("http://ha", {}, ha)

        assert ids == ["weather.home"]

    def test_a_chunk_of_entities_is_requested_without_attributes(self):
        entities = [f"sensor.s{i:02d}" for i in range(65)]
        ha = FakeHA({e: [(NOW - timedelta(hours=1), "1")] for e in entities}, entities)

        rows = ha_history.fetch_window("http://ha", {}, entities, NOW - timedelta(days=1), NOW, ha)

        calls = ha.history_calls()
        assert len(calls) == 3  # 65 entities in chunks of 30
        for _url, params in calls:
            assert "no_attributes" in params and "end_time" in params
            assert len(params["filter_entity_id"].split(",")) <= ha_history.CHUNK_ENTITIES
        assert len(rows) == 65

    def test_rows_are_naive_utc_with_a_domain_and_no_attribute_column(self):
        ha = FakeHA({"media_player.tv": [(datetime(2026, 10, 9, 20, 0), "playing")]})

        (row,) = ha_history.fetch_window(
            "http://ha", {}, ["media_player.tv"], datetime(2026, 10, 9), NOW, ha
        )

        assert row == [
            "media_player.tv",
            "media_player",
            "playing",
            datetime(2026, 10, 9, 20, 0),
            datetime(2026, 10, 9, 20, 0),
        ]
        assert ha_history.SCHEMA.names == [
            "entity_id",
            "domain",
            "state",
            "last_changed",
            "last_updated",
        ]


class TestHaExport:
    HISTORY = {
        "sensor.openweathermap_temperature": [
            (datetime(2026, 10, 9, 6, 0), "11.2"),
            (datetime(2026, 10, 9, 18, 0), "15.4"),
            (datetime(2026, 10, 10, 6, 0), "12.0"),
        ],
        "sun.sun": [
            (datetime(2026, 10, 8, 22, 0), "below_horizon"),
            (datetime(2026, 10, 10, 11, 0), "above_horizon"),
        ],
    }

    def _export(self, tmp_path, ha, now=NOW, **kw):
        return ha_history.export_ha_history(str(tmp_path), now_utc=now, get=ha, config=CONFIG, **kw)

    def test_first_run_walks_back_a_day_at_a_time_and_stops_at_the_end_of_retention(self, tmp_path):
        ha = FakeHA(self.HISTORY)

        outcome = self._export(tmp_path, ha)

        # Today and the day before have data; the next three days are empty, then it stops.
        # Three days with data (the 10th, 9th and 8th) then three empty ones, one request each.
        assert len(ha.history_calls()) == 3 + ha_history.EMPTY_DAYS_TO_STOP
        parts = _partitions(tmp_path, "ha_state_history")
        assert {"2026-10-10", "2026-10-09"} <= set(parts)
        assert outcome["entities"] == 2 and outcome["rows"] > 0

    def test_state_changes_land_in_the_partition_of_their_own_day(self, tmp_path):
        self._export(tmp_path, FakeHA(self.HISTORY))

        parts = _partitions(tmp_path, "ha_state_history")

        temps = {
            r["last_changed"]: r["state"]
            for rows in parts.values()
            for r in rows
            if r["entity_id"].endswith("temperature")
        }
        assert temps[datetime(2026, 10, 10, 6, 0)] == "12.0"
        assert {
            r["state"] for r in parts["2026-10-09"] if r["entity_id"].endswith("temperature")
        } >= {"11.2", "15.4"}

    def test_an_entity_that_did_not_change_is_anchored_by_its_start_of_window_state(self, tmp_path):
        self._export(tmp_path, FakeHA(self.HISTORY))

        sun = [
            r
            for rows in _partitions(tmp_path, "ha_state_history").values()
            for r in rows
            if r["entity_id"] == "sun.sun"
        ]

        # sun.sun changed at 22:00 on the 8th and 11:00 today. Between, its state is known from the
        # midnight anchors, so a series can be rebuilt without a point at every hour.
        anchors = {r["last_changed"]: r["state"] for r in sun}
        assert anchors[datetime(2026, 10, 10, 0, 0)] == "below_horizon"
        assert anchors[datetime(2026, 10, 10, 11, 0)] == "above_horizon"

    def test_running_twice_stores_each_point_once(self, tmp_path):
        ha = FakeHA(self.HISTORY)
        self._export(tmp_path, ha)
        first = {k: len(v) for k, v in _partitions(tmp_path, "ha_state_history").items()}

        self._export(tmp_path, ha)

        assert {k: len(v) for k, v in _partitions(tmp_path, "ha_state_history").items()} == first

    def test_later_runs_resume_from_the_newest_partition_with_a_lookback(self, tmp_path):
        ha = FakeHA(self.HISTORY)
        self._export(tmp_path, ha)
        ha.calls.clear()

        self._export(tmp_path, ha, now=NOW + timedelta(hours=6))

        calls = ha.history_calls()
        assert len(calls) == 1  # one window, not a day-by-day walk
        assert calls[0][0].endswith("2026-10-09T00:00:00+00:00")  # newest day (10th) minus a day

    def test_no_configuration_means_no_network_call(self, tmp_path):
        ha = FakeHA(self.HISTORY)

        outcome = ha_history.export_ha_history(
            str(tmp_path), now_utc=NOW, get=ha, config={"ha_url": "", "ha_token": ""}
        )

        assert outcome == {"skipped": "Home Assistant is not configured"} and ha.calls == []

    def test_legacy_pushbullet_entities_are_never_requested_or_stored(self, tmp_path):
        history = dict(self.HISTORY)
        history["sensor.pushbullet_body"] = [(datetime(2026, 10, 10, 9, 0), "my private message")]
        history["sensor.pushbullet_title"] = [(datetime(2026, 10, 10, 9, 0), "Dinner?")]
        ha = FakeHA(history)

        self._export(tmp_path, ha)

        requested = ",".join(p["filter_entity_id"] for _u, p in ha.history_calls())
        assert "pushbullet" not in requested
        stored = str(_partitions(tmp_path, "ha_state_history"))
        assert "my private message" not in stored and "Dinner?" not in stored

    def test_tightening_an_exclusion_removes_what_was_already_stored(self, tmp_path):
        """The first backfill (before Pushbullet was known to be legacy) stored its title entity."""
        table_dir = tmp_path / "bronze" / "ha_state_history"
        rows = [
            [
                "sensor.pushbullet_title",
                "sensor",
                "Dinner?",
                datetime(2026, 10, 9, 9, 0),
                datetime(2026, 10, 9, 9, 0),
            ],
            [
                "weather.home",
                "weather",
                "sunny",
                datetime(2026, 10, 9, 10, 0),
                datetime(2026, 10, 9, 10, 0),
            ],
        ]
        lake.merge_partition(table_dir, "2026-10-09", ha_history.SCHEMA, rows, ha_history.KEY)
        only_legacy = [
            ["sensor.pushbullet_body", "sensor", "x", datetime(2026, 10, 8), datetime(2026, 10, 8)]
        ]
        lake.merge_partition(
            table_dir, "2026-10-08", ha_history.SCHEMA, only_legacy, ha_history.KEY
        )

        removed = ha_history.purge_excluded(table_dir)

        assert removed == 2
        left = _partitions(tmp_path, "ha_state_history")
        assert [r["entity_id"] for r in left["2026-10-09"]] == ["weather.home"]
        assert "2026-10-08" not in left  # a partition that held only excluded rows is deleted

    def test_purge_runs_at_the_start_of_every_export(self, tmp_path):
        table_dir = tmp_path / "bronze" / "ha_state_history"
        stale = [
            [
                "sensor.pushbullet_title",
                "sensor",
                "t",
                datetime(2026, 10, 9, 9, 0),
                datetime(2026, 10, 9, 9, 0),
            ]
        ]
        lake.merge_partition(table_dir, "2026-10-09", ha_history.SCHEMA, stale, ha_history.KEY)

        self._export(tmp_path, FakeHA(self.HISTORY))

        assert "pushbullet" not in str(_partitions(tmp_path, "ha_state_history"))

    def test_progress_is_reported_so_the_watchdog_is_fed(self, tmp_path):
        progress = MagicMock()

        self._export(tmp_path, FakeHA(self.HISTORY), progress=progress)

        assert progress.call_count >= 2

    def test_an_http_error_propagates_so_the_orchestrator_can_log_it(self, tmp_path):
        def failing(url, **kw):
            return FakeResponse({"message": "Unauthorized"}, status=401)

        with pytest.raises(RuntimeError, match="401"):
            ha_history.export_ha_history(str(tmp_path), now_utc=NOW, get=failing, config=CONFIG)


# --- Gmail ------------------------------------------------------------------------------


def _gmail_message(
    mid,
    received,
    sender="Alice Example <alice@example.com>",
    subject="Hello",
    labels=("INBOX", "UNREAD"),
):
    return {
        "id": mid,
        "threadId": "t" + mid,
        "internalDate": str(int((received - datetime(1970, 1, 1)).total_seconds() * 1000)),
        "labelIds": list(labels),
        "sizeEstimate": 2048,
        "payload": {
            "headers": [{"name": "From", "value": sender}, {"name": "Subject", "value": subject}]
        },
    }


class FakeHttpError(Exception):
    """Shaped like googleapiclient.errors.HttpError: the status lives on .resp."""

    def __init__(self, status):
        super().__init__(f"<HttpError {status}>")
        self.resp = type("Resp", (), {"status": status})()


class FakeBatch:
    def __init__(self, service, callback):
        self.service, self.callback, self.items = service, callback, []

    def add(self, request, request_id=None):
        self.items.append((request_id, request))

    def execute(self):
        if self.service.fail_batches:
            self.service.fail_batches -= 1
            raise RuntimeError("backendError")
        self.service.batches.append([rid for rid, _ in self.items])
        for rid, request in self.items:
            message_id = request["id"]
            limited = self.service.rate_limited.get(message_id, 0)
            if limited:  # transient: HTTP 429 for the first N attempts, then it succeeds
                self.service.rate_limited[message_id] = limited - 1
                self.callback(rid, None, FakeHttpError(429))
            elif message_id in self.service.always_failing:
                self.callback(rid, None, FakeHttpError(503))
            elif message_id not in self.service.store:
                self.callback(rid, None, FakeHttpError(404))
            else:
                self.callback(rid, self.service.store[message_id], None)


class FakeGmail:
    def __init__(self, messages, page_size=500):
        self.store = {m["id"]: m for m in messages}
        self.page_size = page_size
        self.queries, self.batches, self.get_calls = [], [], []
        self.fail_batches = 0
        self.rate_limited = {}  # message id -> how many 429s before it is served
        self.always_failing = set()

    # service.users().messages().list/get(...) and service.new_batch_http_request(...)
    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, q, maxResults, pageToken=None):
        self.queries.append(q)
        ids = sorted(self.store)
        start = int(pageToken or 0)
        body = {"messages": [{"id": i} for i in ids[start : start + self.page_size]]}
        if start + self.page_size < len(ids):
            body["nextPageToken"] = str(start + self.page_size)
        return MagicMock(execute=lambda num_retries=0: body)

    def get(self, userId, id, format, metadataHeaders):
        self.get_calls.append({"format": format, "headers": metadataHeaders})
        return {"id": id}

    def new_batch_http_request(self, callback):
        return FakeBatch(self, callback)


class TestEmailParsing:
    def test_a_message_becomes_a_metadata_row(self):
        received = datetime(2026, 10, 9, 14, 30, 5)

        row = email_log.parse_message(
            _gmail_message("m1", received, "Alice Example <Alice@Example.COM>", "Invoice 42")
        )

        assert row == [
            "m1",
            "tm1",
            received,
            "Alice Example",
            "alice@example.com",
            "example.com",
            "Invoice 42",
            "INBOX,UNREAD",
            True,
            2048,
        ]

    def test_encoded_names_and_subjects_are_decoded(self):
        sender = "=?UTF-8?B?Qm9qYW4gVnVrb3ZpxIc=?= <bojan@example.rs>"
        subject = "=?UTF-8?Q?Caf=C3=A9_menu?="

        row = email_log.parse_message(_gmail_message("m2", datetime(2026, 10, 9), sender, subject))

        assert row[3] == "Bojan Vuković" and row[6] == "Café menu"

    def test_a_read_message_is_not_unread_and_a_missing_sender_is_tolerated(self):
        row = email_log.parse_message(
            _gmail_message("m3", datetime(2026, 10, 9), "", "", labels=("INBOX",))
        )

        assert row[8] is False and row[3:6] == ["", "", ""]

    def test_an_implausible_internal_date_falls_back_to_the_date_header(self):
        """Seen live: Gmail returned internalDate -1 ms for a real message, which landed in 1969."""
        message = _gmail_message("m5", datetime(2026, 10, 9, 14, 0))
        message["internalDate"] = "-1"
        message["payload"]["headers"].append(
            {"name": "Date", "value": "Fri, 09 Oct 2026 10:00:00 -0400"}
        )

        row = email_log.parse_message(message)

        assert row[2] == datetime(2026, 10, 9, 14, 0)  # 10:00 -0400 is 14:00 UTC

    def test_a_far_future_internal_date_is_rejected_too(self):
        """Seen live: a real message arrived dated 2611-09-25 (5 million hourly rows downstream)."""
        message = _gmail_message("m7", datetime(2026, 10, 9, 14, 0))
        message["internalDate"] = str(
            int((datetime(2611, 9, 25) - datetime(1970, 1, 1)).total_seconds() * 1000)
        )
        message["payload"]["headers"].append(
            {"name": "Date", "value": "Fri, 09 Oct 2026 10:00:00 -0400"}
        )

        row = email_log.parse_message(message, now=datetime(2026, 10, 10))

        assert row[2] == datetime(2026, 10, 9, 14, 0)

    def test_an_absurd_date_in_both_places_drops_the_message(self):
        message = _gmail_message("m8", datetime(2026, 10, 9))
        message["internalDate"] = "99999999999999999"
        message["payload"]["headers"].append(
            {"name": "Date", "value": "Mon, 01 Jan 2999 00:00:00 +0000"}
        )

        assert email_log.parse_message(message, now=datetime(2026, 10, 10)) is None

    def test_a_date_two_days_ahead_is_tolerated_for_clock_skew(self):
        row = email_log.parse_message(
            _gmail_message("m9", datetime(2026, 10, 11, 23, 0)), now=datetime(2026, 10, 10)
        )

        assert row[2] == datetime(2026, 10, 11, 23, 0)

    def test_a_message_with_no_usable_date_anywhere_is_dropped(self):
        message = _gmail_message("m6", datetime(2026, 10, 9))
        message["internalDate"] = "-1"

        assert email_log.parse_message(message) is None

    def test_a_message_without_a_date_is_dropped(self):
        message = _gmail_message("m4", datetime(2026, 10, 9))
        del message["internalDate"]

        assert email_log.parse_message(message) is None


class TestEmailExport:
    def _export(self, tmp_path, gmail, now=NOW, **kw):
        return email_log.export_email(
            str(tmp_path), now_utc=now, service=gmail, sleep=lambda s: None, **kw
        )

    def _messages(self, n, day=datetime(2026, 10, 9, 8, 0)):
        return [_gmail_message(f"m{i:03d}", day + timedelta(minutes=i)) for i in range(n)]

    def test_bodies_are_never_requested_only_metadata_headers(self, tmp_path):
        gmail = FakeGmail(self._messages(3))

        self._export(tmp_path, gmail)

        assert gmail.get_calls and all(c["format"] == "metadata" for c in gmail.get_calls)
        assert all(c["headers"] == ["From", "Subject", "Date"] for c in gmail.get_calls)

    def test_the_window_is_twelve_months(self, tmp_path):
        gmail = FakeGmail(self._messages(3))

        self._export(tmp_path, gmail)

        after = int(gmail.queries[0].split(":")[1])
        expected = (
            NOW.replace(hour=0) - timedelta(days=365) - datetime(1970, 1, 1)
        ).total_seconds()
        assert after == int(expected)

    def test_batches_are_small_enough_for_gmails_quota_and_all_messages_are_stored(self, tmp_path):
        gmail = FakeGmail(self._messages(120), page_size=50)
        sleeps = []

        outcome = email_log.export_email(
            str(tmp_path), now_utc=NOW, service=gmail, sleep=sleeps.append
        )

        assert outcome["rows"] == 120 and outcome["failed"] == 0 and outcome["days"] == 1
        # Batches of 50 drew HTTP 429 on 19 of 50 when probed live; 10 is accepted.
        assert email_log.BATCH_SIZE == 10 and all(len(b) <= 10 for b in gmail.batches)
        assert len(gmail.batches) == 12
        assert sleeps.count(email_log.BATCH_PAUSE_SECONDS) == 12
        assert len(_partitions(tmp_path, "email_messages")["2026-10-09"]) == 120

    def test_a_message_deleted_after_listing_is_counted_as_gone_not_failed(self, tmp_path):
        gmail = FakeGmail(self._messages(4))
        original = gmail.list
        gmail.list = lambda **kw: _drop_message_after_listing(gmail, original, **kw)

        outcome = self._export(tmp_path, gmail)

        assert outcome["rows"] == 3 and outcome["gone"] == 1 and outcome["failed"] == 0

    def test_a_per_message_rate_limit_is_retried_with_backoff_until_it_succeeds(self, tmp_path):
        gmail = FakeGmail(self._messages(5))
        gmail.rate_limited = {"m001": 2, "m003": 1}  # the live failure: 429 on individual messages
        sleeps = []

        outcome = email_log.export_email(
            str(tmp_path), now_utc=NOW, service=gmail, sleep=sleeps.append
        )

        assert outcome["rows"] == 5 and outcome["failed"] == 0  # none lost
        assert 1 in sleeps and 2 in sleeps  # exponential backoff between attempts

    def test_a_whole_batch_failure_is_also_retried(self, tmp_path):
        gmail = FakeGmail(self._messages(3))
        gmail.fail_batches = 2

        outcome = self._export(tmp_path, gmail)

        assert outcome["rows"] == 3 and outcome["failed"] == 0

    def test_a_message_that_keeps_failing_is_reported_not_hidden(self, tmp_path):
        gmail = FakeGmail(self._messages(5))
        gmail.always_failing = {"m002"}

        outcome = self._export(tmp_path, gmail)

        assert outcome["rows"] == 4 and outcome["failed"] == 1  # surfaced in the result and the log

    def test_the_next_run_heals_what_failed_before(self, tmp_path):
        gmail = FakeGmail(
            self._messages(5, day=datetime(2026, 9, 1, 8, 0))
        )  # old: outside lookback
        gmail.always_failing = {"m002"}
        self._export(tmp_path, gmail)
        gmail.always_failing = set()  # Gmail recovers
        gmail.get_calls.clear()

        outcome = self._export(tmp_path, gmail, now=NOW + timedelta(days=1))

        assert outcome["rows"] == 1 and len(gmail.get_calls) == 1  # fetched only the missing one
        assert len(_partitions(tmp_path, "email_messages")["2026-09-01"]) == 5

    def test_a_later_run_fetches_only_new_and_recent_mail(self, tmp_path):
        old = self._messages(3, day=datetime(2026, 9, 1, 8, 0))
        recent = [_gmail_message(f"r{i}", datetime(2026, 10, 9, 8, i)) for i in range(2)]
        gmail = FakeGmail(old + recent)
        self._export(tmp_path, gmail)
        gmail.get_calls.clear()
        gmail.store["new1"] = _gmail_message("new1", datetime(2026, 10, 11, 9, 0))

        outcome = self._export(tmp_path, gmail, now=NOW + timedelta(days=1, hours=1))

        # 2 recent (label refresh) + 1 new; the 3 old messages are not fetched again.
        assert len(gmail.get_calls) == 3 and outcome["rows"] == 3
        assert len(_partitions(tmp_path, "email_messages")["2026-09-01"]) == 3

    def test_a_label_change_since_the_last_run_refreshes_the_stored_row(self, tmp_path):
        gmail = FakeGmail(
            [_gmail_message("m1", datetime(2026, 10, 9, 9, 0), labels=("INBOX", "UNREAD"))]
        )
        self._export(tmp_path, gmail)
        gmail.store["m1"] = _gmail_message("m1", datetime(2026, 10, 9, 9, 0), labels=("INBOX",))

        self._export(tmp_path, gmail, now=NOW + timedelta(hours=2))

        (row,) = _partitions(tmp_path, "email_messages")["2026-10-09"]
        assert row["is_unread"] is False

    def test_a_bad_date_stored_earlier_is_removed_and_the_message_refiled_correctly(self, tmp_path):
        table_dir = tmp_path / "bronze" / "email_messages"
        bad = [
            ["m1", "tm1", datetime(2611, 9, 25), "A", "a@x.com", "x.com", "s", "INBOX", False, 1]
        ]
        lake.merge_partition(table_dir, "2611-09-25", email_log.SCHEMA, bad, email_log.KEY)
        gmail = FakeGmail([_gmail_message("m1", datetime(2026, 10, 9, 9, 0))])

        outcome = self._export(tmp_path, gmail)

        parts = _partitions(tmp_path, "email_messages")
        assert "2611-09-25" not in parts
        assert [r["message_id"] for r in parts["2026-10-09"]] == ["m1"]
        assert outcome["rows"] == 1

    def test_a_message_with_no_usable_date_is_counted_not_silently_lost(self, tmp_path):
        undated = _gmail_message("u1", datetime(2026, 10, 9, 9, 0))
        undated["internalDate"] = "-1"
        gmail = FakeGmail([_gmail_message("ok1", datetime(2026, 10, 9, 9, 0)), undated])

        outcome = self._export(tmp_path, gmail)

        assert outcome["rows"] == 1 and outcome["undated"] == 1 and outcome["failed"] == 0

    def test_no_credentials_means_nothing_is_fetched(self, tmp_path):
        with patch("common.gmail_utils.get_credentials", return_value=None):
            outcome = email_log.export_email(str(tmp_path), now_utc=NOW)

        assert outcome == {"skipped": "no Gmail credentials"}

    def test_the_stored_schema_has_no_body_column(self):
        assert "body" not in email_log.SCHEMA.names and "snippet" not in email_log.SCHEMA.names
        assert email_log.SCHEMA.names == [
            "message_id", "thread_id", "received_utc", "sender_name", "sender_email",
            "sender_domain", "subject", "labels", "is_unread", "size_estimate",
        ]  # fmt: skip


def _drop_message_after_listing(gmail, original, **kw):
    response = original(**kw)
    gmail.store.pop("m001", None)  # deleted between list() and get()
    return response


class TestOrchestration:
    def test_one_failing_source_does_not_stop_the_other(self, tmp_path):
        email_ok = MagicMock(return_value={"rows": 1})
        with patch.object(
            external,
            "SOURCES",
            (("ha_history", MagicMock(side_effect=RuntimeError("HA down"))), ("email", email_ok)),
        ):
            outcomes = external.run_all(str(tmp_path))

        assert outcomes["ha_history"] == "failed: HA down" and outcomes["email"] == {"rows": 1}

    def test_sources_can_be_selected(self, tmp_path):
        ha, mail = MagicMock(return_value={}), MagicMock(return_value={})
        with patch.object(external, "SOURCES", (("ha_history", ha), ("email", mail))):
            external.run_all(str(tmp_path), only={"email"})

        ha.assert_not_called()
        mail.assert_called_once()

    def test_it_holds_the_export_lock(self, tmp_path):
        with lake._ExportLock(str(tmp_path)):
            with pytest.raises(RuntimeError, match="already running"):
                external.run_all(str(tmp_path))

    def test_the_nightly_job_runs_external_exports_between_mysql_export_and_silver(self):
        from services.service_sa import learner

        order = []
        with patch.object(
            learner.lake,
            "run_export",
            side_effect=lambda **k: order.append("mysql") or {"failures": []},
        ), patch.object(
            learner.external, "run_all", side_effect=lambda **k: order.append("external") or {}
        ), patch.object(
            learner.silver, "run_build", side_effect=lambda **k: order.append("silver") or {}
        ), patch.object(
            learner, "run_learners", side_effect=lambda: order.append("learners")
        ):
            learner.run_bronze_export()

        assert order == ["mysql", "external", "silver", "learners"]

    def test_a_failing_external_stage_does_not_stop_silver_or_the_learners(self):
        from services.service_sa import learner

        order = []
        with patch.object(learner.lake, "run_export", return_value={"failures": []}), patch.object(
            learner.external, "run_all", side_effect=RuntimeError("boom")
        ), patch.object(
            learner.silver, "run_build", side_effect=lambda **k: order.append("silver") or {}
        ), patch.object(
            learner, "run_learners", side_effect=lambda: order.append("learners")
        ):
            learner.run_bronze_export()

        assert order == ["silver", "learners"]
