"""Local CA + leaf issuing (services/service_tls/local_tls.py)."""

import datetime
import ipaddress

import pytest
from cryptography import x509

import local_tls


@pytest.fixture
def ca(tmp_path):
    return local_tls.ensure_ca(str(tmp_path / "ca"))


def test_ensure_ca_is_idempotent(tmp_path):
    d = str(tmp_path / "ca")
    first, _ = local_tls.ensure_ca(d)
    second, _ = local_tls.ensure_ca(d)
    assert local_tls.cert_fingerprint(first) == local_tls.cert_fingerprint(second)


def test_ca_key_not_world_readable(tmp_path):
    local_tls.ensure_ca(str(tmp_path / "ca"))
    assert (tmp_path / "ca" / "ca.key").stat().st_mode & 0o077 == 0


def test_leaf_chains_to_ca_and_covers_sans(tmp_path, ca):
    ca_cert, ca_key = ca
    out = str(tmp_path / "out")
    leaf = local_tls.issue_leaf(ca_cert, ca_key, ["192.168.9.9", "alfr3d.local"], out)
    leaf.verify_directly_issued_by(ca_cert)
    ext = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert ipaddress.ip_address("192.168.9.9") in ext.get_values_for_type(x509.IPAddress)
    assert "alfr3d.local" in ext.get_values_for_type(x509.DNSName)
    assert not leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca


def test_reissue_only_when_sans_change(tmp_path, ca):
    ca_cert, ca_key = ca
    out = str(tmp_path / "out")
    leaf_path = f"{out}/server.crt"
    assert local_tls.leaf_needs_reissue(leaf_path, ca_cert, {"10.0.0.1"})  # missing
    local_tls.issue_leaf(ca_cert, ca_key, ["10.0.0.1", "localhost"], out)
    assert not local_tls.leaf_needs_reissue(leaf_path, ca_cert, {"10.0.0.1", "localhost"})
    assert local_tls.leaf_needs_reissue(leaf_path, ca_cert, {"10.0.0.2", "localhost"})  # IP moved


def test_leaf_from_other_ca_is_reissued(tmp_path, ca):
    ca_cert, ca_key = ca
    other_cert, other_key = local_tls.ensure_ca(str(tmp_path / "other"))
    out = str(tmp_path / "out")
    local_tls.issue_leaf(other_cert, other_key, ["10.0.0.1"], out)
    assert local_tls.leaf_needs_reissue(f"{out}/server.crt", ca_cert, {"10.0.0.1"})


def test_expiring_leaf_is_reissued(tmp_path, ca, monkeypatch):
    ca_cert, ca_key = ca
    out = str(tmp_path / "out")
    local_tls.issue_leaf(ca_cert, ca_key, ["10.0.0.1"], out)
    future = local_tls._now() + datetime.timedelta(days=local_tls.LEAF_VALID_DAYS - 10)
    monkeypatch.setattr(local_tls, "_now", lambda: future)
    assert local_tls.leaf_needs_reissue(f"{out}/server.crt", ca_cert, {"10.0.0.1"})


def test_host_sans_has_loopback_and_static_names():
    sans = local_tls.host_sans(["my.ts.net"])
    assert {"127.0.0.1", "localhost", "alfr3d.local", "my.ts.net"} <= sans
