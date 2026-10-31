"""service_tls/app.py run-once mode (TLS_ONESHOT=1), the way docker-compose.yml runs it."""

import importlib.util
import os
import sys
import types

import pytest

import local_tls

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "services", "service_tls", "app.py")


@pytest.fixture
def tls_app(tmp_path, monkeypatch):
    """app.py loaded by path (several services have an app.py) with docker stubbed out."""
    reloads = []

    class FakeContainer:
        name = "alfr3d-nginx-1"

        def kill(self, signal):
            reloads.append(signal)

    class FakeContainers:
        def list(self, filters):
            reloads.append(filters)
            return [FakeContainer()]

    fake_docker = types.SimpleNamespace(
        from_env=lambda: types.SimpleNamespace(containers=FakeContainers())
    )
    monkeypatch.setitem(sys.modules, "docker", fake_docker)
    spec = importlib.util.spec_from_file_location("service_tls_app", APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "CA_DIR", str(tmp_path / "ca"))
    monkeypatch.setattr(mod, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(mod, "EXTRA_SANS", [])
    monkeypatch.setattr(local_tls, "host_sans", lambda extra=(): {"10.0.0.1", "localhost"})
    mod.reloads = reloads
    return mod


def run_main(mod):
    with pytest.raises(SystemExit) as exc:
        mod.main()
    return exc.value.code


def test_oneshot_issues_leaf_hups_nginx_and_exits_zero(tls_app, monkeypatch):
    monkeypatch.setattr(tls_app, "ONESHOT", True)
    assert run_main(tls_app) == 0
    assert os.path.exists(os.path.join(tls_app.OUT_DIR, "server.crt"))
    assert os.path.exists(os.path.join(tls_app.OUT_DIR, "ca.crt"))
    assert tls_app.reloads == [{"label": "com.docker.compose.service=nginx"}, "HUP"]


def test_oneshot_is_a_noop_when_nothing_changed(tls_app, monkeypatch):
    monkeypatch.setattr(tls_app, "ONESHOT", True)
    run_main(tls_app)
    leaf = open(os.path.join(tls_app.OUT_DIR, "server.crt"), "rb").read()
    tls_app.reloads.clear()
    assert run_main(tls_app) == 0
    assert open(os.path.join(tls_app.OUT_DIR, "server.crt"), "rb").read() == leaf
    assert tls_app.reloads == []  # no re-issue, no HUP


def test_oneshot_never_regenerates_the_ca(tls_app, monkeypatch):
    monkeypatch.setattr(tls_app, "ONESHOT", True)
    run_main(tls_app)
    first = local_tls.cert_fingerprint(local_tls.load_cert(f"{tls_app.CA_DIR}/ca.crt"))
    monkeypatch.setattr(local_tls, "host_sans", lambda extra=(): {"10.0.0.2", "localhost"})
    run_main(tls_app)  # IP moved: leaf re-issued, CA untouched
    second = local_tls.cert_fingerprint(local_tls.load_cert(f"{tls_app.CA_DIR}/ca.crt"))
    assert first == second


def test_failed_reissue_keeps_a_usable_leaf_and_exits_zero(tls_app, monkeypatch):
    monkeypatch.setattr(tls_app, "ONESHOT", True)
    run_main(tls_app)

    def boom(*a, **k):
        raise RuntimeError("issue failed")

    monkeypatch.setattr(local_tls, "host_sans", lambda extra=(): {"10.0.0.9", "localhost"})
    monkeypatch.setattr(local_tls, "issue_leaf", boom)
    assert run_main(tls_app) == 0  # drifted SANs, but the old leaf still serves


def test_failed_issue_with_no_leaf_exits_nonzero(tls_app, monkeypatch):
    monkeypatch.setattr(tls_app, "ONESHOT", True)

    def boom(*a, **k):
        raise RuntimeError("issue failed")

    monkeypatch.setattr(local_tls, "issue_leaf", boom)
    assert run_main(tls_app) == 1


def test_default_mode_still_loops(tls_app, monkeypatch):
    assert tls_app.ONESHOT is False
    sleeps = []

    class Stop(Exception):
        pass

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise Stop

    monkeypatch.setattr(tls_app.time, "sleep", fake_sleep)
    with pytest.raises(Stop):
        tls_app.main()
    assert sleeps == [tls_app.CHECK_INTERVAL] * 2


def test_reload_targets_the_configured_service(tls_app, monkeypatch):
    monkeypatch.setattr(tls_app, "NGINX_SERVICE", "service-frontend")
    tls_app.reload_nginx()
    assert tls_app.reloads[0] == {"label": "com.docker.compose.service=service-frontend"}
