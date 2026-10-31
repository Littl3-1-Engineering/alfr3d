"""Local private CA + leaf issuing for the nginx HTTPS listener.

The Deck pins the *CA*, not the leaf, so the leaf can be re-issued freely (new IP, new network,
renewal) without breaking paired clients. Only the CA public cert ever leaves the host; the CA
key stays in its own volume, mounted into the TLS sidecar only.
"""

import datetime
import hashlib
import ipaddress
import os
import socket

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_VALID_DAYS = 365 * 20
LEAF_VALID_DAYS = 365
RENEW_BEFORE_DAYS = 30

# Container/virtual interfaces whose addresses are meaningless to a LAN client.
_SKIP_IFACE_PREFIXES = ("lo", "docker", "br-", "veth", "virbr", "cni", "flannel")


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _write(path, data, mode):
    """Write atomically with the final mode already set, so a key is never world-readable."""
    tmp = f"{path}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _pem_cert(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def _pem_key(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def cert_fingerprint(cert):
    """SHA-256 of the DER cert, colon-separated upper-case hex (what the Deck shows to confirm)."""
    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def load_cert(path):
    with open(path, "rb") as fh:
        return x509.load_pem_x509_certificate(fh.read())


def ensure_ca(ca_dir):
    """Return (ca_cert, ca_key), creating the CA on first run. Never regenerates an existing one."""
    cert_path = os.path.join(ca_dir, "ca.crt")
    key_path = os.path.join(ca_dir, "ca.key")
    if os.path.exists(cert_path) and os.path.exists(key_path):
        with open(key_path, "rb") as fh:
            return load_cert(cert_path), serialization.load_pem_private_key(fh.read(), None)

    os.makedirs(ca_dir, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ALFR3D"),
            x509.NameAttribute(NameOID.COMMON_NAME, "ALFR3D Local CA"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - datetime.timedelta(minutes=5))
        .not_valid_after(_now() + datetime.timedelta(days=CA_VALID_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    # Key first: a crash between the two writes must not leave a cert whose key is missing.
    _write(key_path, _pem_key(key), 0o600)
    _write(cert_path, _pem_cert(cert), 0o644)
    return cert, key


def _split_sans(sans):
    ips, dns = [], []
    for san in sans:
        try:
            ips.append(ipaddress.ip_address(san))
        except ValueError:
            dns.append(san)
    return ips, dns


def issue_leaf(ca_cert, ca_key, sans, out_dir):
    """Issue a fresh leaf for `sans` (IPs and hostnames); write server.crt/.key to out_dir."""
    ips, dns = _split_sans(sans)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "alfr3d")])
    san_ext = x509.SubjectAlternativeName(
        [x509.DNSName(d) for d in dns] + [x509.IPAddress(i) for i in ips]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - datetime.timedelta(minutes=5))
        .not_valid_after(_now() + datetime.timedelta(days=LEAF_VALID_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=False,
                crl_sign=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(san_ext, critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    os.makedirs(out_dir, exist_ok=True)
    _write(os.path.join(out_dir, "server.key"), _pem_key(key), 0o600)
    _write(os.path.join(out_dir, "server.crt"), _pem_cert(cert), 0o644)
    return cert


def leaf_sans(cert):
    """The set of IP/hostname strings a leaf currently covers."""
    ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return {str(i) for i in ext.get_values_for_type(x509.IPAddress)} | set(
        ext.get_values_for_type(x509.DNSName)
    )


def leaf_needs_reissue(leaf_path, ca_cert, wanted_sans):
    """True if the leaf is missing, unreadable, from another CA, expiring, or its SANs drifted."""
    try:
        leaf = load_cert(leaf_path)
        # Signature check, not a name compare: a regenerated CA reuses the same subject name.
        leaf.verify_directly_issued_by(ca_cert)
        if leaf.not_valid_after_utc - _now() < datetime.timedelta(days=RENEW_BEFORE_DAYS):
            return True
        return leaf_sans(leaf) != set(wanted_sans)
    except (OSError, ValueError, TypeError, InvalidSignature, x509.ExtensionNotFound):
        return True


def leaf_usable(leaf_path, key_path, ca_cert):
    """True if nginx can serve the leaf as-is: both files present, issued by this CA, unexpired.

    Deliberately weaker than `not leaf_needs_reissue`: SAN drift or being inside the renewal window
    leaves a leaf that still works, so a failed re-issue must not take the stack down over it."""
    try:
        if os.path.getsize(key_path) == 0:
            return False
        leaf = load_cert(leaf_path)
        leaf.verify_directly_issued_by(ca_cert)
        return leaf.not_valid_after_utc > _now()
    except (OSError, ValueError, TypeError, InvalidSignature):
        return False


def host_sans(extra=()):
    """Every address and name a client might use to reach this host right now."""
    import ifaddr

    sans = {"localhost", "127.0.0.1", "alfr3d.local"}
    hostname = socket.gethostname()
    if hostname:
        sans.update({hostname, f"{hostname}.local"})
    for adapter in ifaddr.get_adapters():
        if adapter.name.startswith(_SKIP_IFACE_PREFIXES):
            continue
        for ip in adapter.ips:
            if not ip.is_IPv4:
                continue
            addr = ipaddress.ip_address(ip.ip)
            if addr.is_loopback or addr.is_link_local:
                continue
            sans.add(str(addr))
    sans.update(s.strip() for s in extra if s and s.strip())
    return sans
