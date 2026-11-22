"""tls_health: classify/summarize/parse are pure; probe and check must never raise."""

from datetime import datetime, timedelta, timezone

from common import tls_health


def test_classify_thresholds():
    assert tls_health.classify(-0.1) == "expired"
    assert tls_health.classify(3) == "expiring"
    assert tls_health.classify(60) == "ok"


def test_worst_status_wins_and_unknown_does_not_mask_expiry():
    entries = [{"status": "ok"}, {"status": "unknown"}, {"status": "expired"}]
    assert tls_health.summarize(entries)["status"] == "expired"
    assert tls_health.summarize([{"status": "ok"}, {"status": "unknown"}])["status"] == "unknown"
    assert tls_health.summarize([])["status"] == "unknown"


def test_parse_targets_skips_malformed_items():
    assert tls_health.parse_targets("nginx:443:a.ts.net, bad, x:y:z") == [
        ("nginx", 443, "a.ts.net")
    ]
    assert tls_health.parse_targets(None) == [("nginx", 443, "localhost")]


def test_unreachable_probe_is_unknown_not_an_exception():
    assert tls_health.probe("127.0.0.1", 1, "x") == {"name": "x", "status": "unknown"}


def test_probe_reports_an_expired_cert(monkeypatch):
    class _Sock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Tls(_Sock):
        def getpeercert(self, binary_form=False):
            return b"der"

    class _Ctx:
        check_hostname = True
        verify_mode = None

        def wrap_socket(self, sock, server_hostname=None):
            return _Tls()

    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    monkeypatch.setattr(tls_health.socket, "create_connection", lambda *a, **k: _Sock())
    monkeypatch.setattr(tls_health.ssl, "create_default_context", lambda *_: _Ctx())
    monkeypatch.setattr(tls_health, "_not_after", lambda der: now - timedelta(hours=3))
    out = tls_health.probe("h", 443, "a.ts.net", now=now)
    assert out["status"] == "expired" and out["days_left"] < 0


def test_check_never_raises(monkeypatch):
    monkeypatch.setattr(tls_health, "probe", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert tls_health.check("nginx:443:a") == {"status": "unknown", "certs": []}
