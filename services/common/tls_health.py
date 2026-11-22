"""How long until the certificates clients actually see expire? (`/api/health` `tls_certs`.)

The Tailscale HTTPS cert for the NUC (`tailscale cert`, Let's Encrypt, 90 days) is renewed by a
timer, and a timer can fail silently: when it did, the Deck's saved `https://<host>.ts.net` URL
started failing the TLS handshake and nothing in `/api/health` said why. This probes what nginx
really serves for each hostname (SNI): the cert a client would get, not a file on disk.

`TLS_PROBE_TARGETS` is a comma list of `host:port:sni` (default: the local-CA leaf on `nginx:443`).
Add the tailnet name to cover the public cert, e.g. `nginx:443:alfr3d-gorsion.tailXXXX.ts.net`.
"""

import os
import socket
import ssl
from datetime import datetime, timezone

WARN_DAYS = 14
DEFAULT_TARGETS = "nginx:443:localhost"
TIMEOUT_S = 4


def parse_targets(raw: str | None) -> list[tuple[str, int, str]]:
    targets = []
    for item in (raw or DEFAULT_TARGETS).split(","):
        parts = item.strip().split(":")
        if len(parts) == 3 and parts[1].isdigit():
            targets.append((parts[0], int(parts[1]), parts[2]))
    return targets


def classify(days_left: float) -> str:
    if days_left < 0:
        return "expired"
    if days_left < WARN_DAYS:
        return "expiring"
    return "ok"


def summarize(entries: list[dict]) -> dict:
    """Roll per-hostname entries up. Worst status wins; unreachable probes are `unknown`."""
    order = {"expired": 3, "expiring": 2, "unknown": 1, "ok": 0}
    worst = max((e["status"] for e in entries), key=order.__getitem__, default="unknown")
    return {"status": worst, "certs": entries}


def probe(host: str, port: int, sni: str, now: datetime | None = None) -> dict:
    """Handshake without verification (an expired cert must still be readable) and report expiry."""
    now = now or datetime.now(timezone.utc)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT_S) as sock:
            with ctx.wrap_socket(sock, server_hostname=sni) as tls:
                der = tls.getpeercert(binary_form=True)
        not_after = _not_after(der)
    except Exception:
        return {"name": sni, "status": "unknown"}
    days_left = (not_after - now).total_seconds() / 86400
    return {
        "name": sni,
        "status": classify(days_left),
        "not_after": not_after.isoformat(),
        "days_left": round(days_left, 1),
    }


def _not_after(der: bytes) -> datetime:
    from cryptography import x509

    return x509.load_der_x509_certificate(der).not_valid_after_utc


def check(raw_targets: str | None = None) -> dict:
    """Never raises: a broken probe must not take the health endpoint down."""
    try:
        raw = raw_targets if raw_targets is not None else os.environ.get("TLS_PROBE_TARGETS")
        return summarize([probe(*t) for t in parse_targets(raw)])
    except Exception:
        return {"status": "unknown", "certs": []}
