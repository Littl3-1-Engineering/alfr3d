"""Tests for the daily kanji wisdom quote endpoint."""

import os
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "service_api"))

os.environ.setdefault("MYSQL_DATABASE", "localhost")
os.environ.setdefault("MYSQL_USER", "root")
os.environ.setdefault("MYSQL_PSWD", "testrootpassword")
os.environ.setdefault("MYSQL_NAME", "test_alfr3d_db")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("ALFR3D_ENV_NAME", "test")
os.environ.setdefault(
    "ALFR3D_SECRETS_KEY",
    "8pS1sOe6r8kM2v3z1Q5X0jz3n5aQ6l1V9j0k3m0zQeM=",  # pragma: allowlist secret
)  # fixed test-only Fernet key, not a real credential
os.environ.setdefault("HOST_REPO_PATH", "/tmp/alfr3d-test-repo")
os.environ.setdefault("COMPOSE_PROJECT_NAME", "alfr3d")

QUOTES = [
    {
        "id": 1,
        "kanji": "一期一会",
        "reading": "ichigo ichie",
        "meaning": "one meeting",
        "enabled": True,
    },
    {
        "id": 2,
        "kanji": "七転八起",
        "reading": "nanakorobi yaoki",
        "meaning": "rise",
        "enabled": True,
    },
    {"id": 3, "kanji": "守破離", "reading": "shu-ha-ri", "meaning": "mastery", "enabled": True},
]


@pytest.fixture(scope="module")
def client():
    from app import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_cache():
    import dependencies as deps

    deps._cache.clear()
    yield


def test_pick_for_day_is_deterministic_and_wraps():
    from routes.kanji import pick_for_day

    day = date(2026, 10, 6)
    assert pick_for_day(QUOTES, day) == pick_for_day(QUOTES, day)
    assert pick_for_day(QUOTES, date.fromordinal(day.toordinal() + 3)) == pick_for_day(QUOTES, day)
    seen = {pick_for_day(QUOTES, date.fromordinal(day.toordinal() + i))["id"] for i in range(3)}
    assert seen == {1, 2, 3}


def test_pick_for_day_empty_is_none():
    from routes.kanji import pick_for_day

    assert pick_for_day([], date(2026, 10, 6)) is None


@patch("routes.kanji._household_today", return_value=date(2026, 10, 6))
@patch("routes.kanji._fetch_enabled", return_value=QUOTES)
def test_today_returns_the_days_quote(_fetch, _today, client):
    resp = client.get("/api/kanji/today")
    assert resp.status_code == 200
    body = resp.json()
    expected = QUOTES[date(2026, 10, 6).toordinal() % 3]
    assert body["date"] == "2026-10-06"
    assert body["kanji"] == expected["kanji"]
    assert set(body) == {"date", "id", "kanji", "reading", "meaning"}


@patch("routes.kanji._household_today", return_value=date(2026, 10, 6))
@patch("routes.kanji._fetch_enabled", return_value=[])
def test_today_404_when_nothing_enabled(_fetch, _today, client):
    assert client.get("/api/kanji/today").status_code == 404


def test_household_today_falls_back_to_server_date_on_failure():
    from routes.kanji import _household_today

    with patch("routes.kanji.get_day_context", side_effect=RuntimeError("tz lookup failed")):
        assert _household_today() == date.today()


def test_writes_require_authentication(client):
    body = {"kanji": "x", "reading": "x", "meaning": "x"}
    assert client.post("/api/kanji", json=body).status_code == 401
    assert client.put("/api/kanji/1", json=body).status_code == 401
    assert client.delete("/api/kanji/1").status_code == 401
    assert client.get("/api/kanji").status_code == 401


def test_fetch_enabled_maps_rows():
    from routes.kanji import _fetch_enabled

    with patch("routes.kanji.db_connection") as conn:
        cursor = MagicMock()
        conn.return_value.__enter__.return_value.cursor.return_value = cursor
        cursor.fetchall.return_value = [(1, "守破離", "shu-ha-ri", "mastery", 1)]
        assert _fetch_enabled() == [
            {
                "id": 1,
                "kanji": "守破離",
                "reading": "shu-ha-ri",
                "meaning": "mastery",
                "enabled": True,
            }
        ]
