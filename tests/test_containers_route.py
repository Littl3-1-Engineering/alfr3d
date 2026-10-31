"""/api/containers and /api/system/services: on-demand containers read as idle, not down."""

import os
import sys

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

from routes import containers, system  # noqa: E402


def fake_docker(inspect_lines):
    """run_docker_command stand-in keyed on the docker subcommand."""

    def run(cmd, env):
        if cmd[1] == "ps":
            names = [ln.split(",")[0] for ln in inspect_lines]
            return "\n".join('{"Names": "%s"}' % n for n in names)
        if cmd[1] == "stats":
            return "\n".join(f"{ln.split(',')[0]},0.0%,1.0%" for ln in inspect_lines)
        if cmd[1] == "info":
            return "4"
        if cmd[1] == "inspect":
            return "\n".join(inspect_lines)
        raise AssertionError(cmd)

    return run


def metrics(monkeypatch, lines):
    monkeypatch.setattr(containers, "is_docker_available", lambda: True)
    monkeypatch.setattr(containers, "run_docker_command", fake_docker(lines))
    monkeypatch.setattr(
        containers, "parse_docker_json", __import__("dependencies").parse_docker_json
    )
    return {c["name"]: c for c in containers.fetch_container_metrics()}


def test_ondemand_exited_zero_is_idle(monkeypatch):
    got = metrics(
        monkeypatch,
        [
            "alfr3d-service-tls-1,exited,none,0,true,0",
            "alfr3d-kafka-1,running,healthy,0,,0",
        ],
    )
    assert got["alfr3d-service-tls-1"]["idle"] is True
    assert got["alfr3d-service-tls-1"]["ondemand"] is True
    assert got["alfr3d-service-tls-1"]["state"] == "exited"  # raw docker state is kept
    assert got["alfr3d-kafka-1"]["idle"] is False
    assert got["alfr3d-kafka-1"]["ondemand"] is False


def test_ondemand_failure_is_not_idle(monkeypatch):
    got = metrics(monkeypatch, ["alfr3d-service-tls-1,exited,none,0,true,1"])
    assert got["alfr3d-service-tls-1"]["idle"] is False


def test_ordinary_exited_container_is_not_idle(monkeypatch):
    # Not labelled on-demand: an exited service-device is an outage even with exit code 0.
    got = metrics(monkeypatch, ["alfr3d-service-device-1,exited,none,0,,0"])
    assert got["alfr3d-service-device-1"]["idle"] is False


def test_running_ondemand_container_is_not_idle(monkeypatch):
    got = metrics(monkeypatch, ["alfr3d-service-tls-1,running,none,0,true,0"])
    assert got["alfr3d-service-tls-1"]["idle"] is False


def test_system_services_marks_clean_ondemand_exit_idle(monkeypatch):
    import asyncio

    out = (
        "alfr3d-kafka-1\tUp 3 days (healthy)\t\n"
        "alfr3d-service-tls-1\tExited (0) 4 hours ago\ttrue\n"
        "alfr3d-service-device-1\tExited (0) 4 hours ago\t\n"
        "alfr3d-service-tls-2\tExited (1) 4 hours ago\ttrue\n"
    )
    monkeypatch.setattr(system, "is_docker_available", lambda: True)
    monkeypatch.setattr(system, "run_docker_command", lambda cmd, env: out)
    got = {s["name"]: s["status"] for s in asyncio.run(system.get_services())}
    assert got == {
        "alfr3d-kafka-1": "running",
        "alfr3d-service-tls-1": "idle",
        "alfr3d-service-device-1": "stopped",
        "alfr3d-service-tls-2": "stopped",
    }
