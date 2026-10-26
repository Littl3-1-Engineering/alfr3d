"""Public half of the local CA, for Deck pairing.

service_tls (the sidecar) owns the CA key and publishes only ca.crt into the shared certs dir,
which service_api sees read-only under /project/certs. The CA cert is public by design; the
Deck pins it after the user confirms the fingerprint, then trusts any leaf this CA signs.
"""

import hashlib
import logging
import os

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, HTTPException, Response

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api/tls", tags=["tls"])

CA_PATH = os.getenv("TLS_CA_CERT_PATH", "/project/certs/ca.crt")


def _load_ca():
    try:
        with open(CA_PATH, "rb") as fh:
            pem = fh.read()
        return pem, x509.load_pem_x509_certificate(pem)
    except (OSError, ValueError) as e:
        logger.warning(f"Local CA unavailable at {CA_PATH}: {e}")
        raise HTTPException(status_code=503, detail="Local CA not available")


def _fingerprint(cert):
    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


@router.get("/ca")
def get_ca():
    """The CA cert (PEM) plus its SHA-256 fingerprint, for the Deck's pairing/confirm step."""
    pem, cert = _load_ca()
    return {
        "pem": pem.decode(),
        "sha256": _fingerprint(cert),
        "subject": cert.subject.rfc4514_string(),
        "not_after": cert.not_valid_after_utc.isoformat(),
    }


@router.get("/ca.crt")
def download_ca():
    """Raw PEM download, for installing the CA in a browser or OS trust store."""
    pem, _ = _load_ca()
    return Response(
        content=pem,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": 'attachment; filename="alfr3d-ca.crt"'},
    )
