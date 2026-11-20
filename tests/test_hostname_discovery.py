"""Unit tests for LAN hostname discovery (no network, no DB)."""

import os
import sys

import dns.message
import dns.rdatatype
import dns.rrset

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "service_device"))

import hostname_discovery as hd  # noqa: E402


def _ptr_response(ip, target, rcode=0):
    q = dns.message.make_query(hd.dns.reversename.from_address(ip), dns.rdatatype.PTR)
    r = dns.message.make_response(q)
    r.set_rcode(rcode)
    if target:
        r.answer.append(dns.rrset.from_text(q.question[0].name, 60, "IN", "PTR", target))
    return r


def test_clean_name_strips_dot_and_ignores_noise():
    assert hd.clean_name("leonardo.", "10.0.0.20") == "leonardo"
    assert hd.clean_name("_gateway", "10.0.0.1") is None
    assert hd.clean_name("10.0.0.5", "10.0.0.5") is None
    assert hd.clean_name(None) is None


def test_first_ptr_parses_answer_and_nxdomain():
    assert hd._first_ptr(_ptr_response("10.0.0.20", "leonardo.")) == "leonardo."
    assert hd._first_ptr(_ptr_response("10.0.0.78", None, rcode=3)) is None


def test_discover_prefers_gateway_then_mdns_then_system(monkeypatch):
    monkeypatch.setattr(hd, "resolve_via_gateway", lambda ip, gw: None)
    monkeypatch.setattr(hd, "resolve_via_mdns", lambda ip: "mac-mini")
    monkeypatch.setattr(hd, "resolve_via_system", lambda ip: "sys")
    assert hd.discover_hostname("10.0.0.9", gateway="10.0.0.1") == "mac-mini"

    monkeypatch.setattr(hd, "resolve_via_gateway", lambda ip, gw: "from-router")
    assert hd.discover_hostname("10.0.0.9", gateway="10.0.0.1") == "from-router"


def test_discover_returns_none_when_all_fail(monkeypatch):
    for fn in ("resolve_via_gateway", "resolve_via_mdns", "resolve_via_system"):
        monkeypatch.setattr(hd, fn, lambda *a, **k: None)
    assert hd.discover_hostname("10.0.0.9", gateway="10.0.0.1") is None


def test_gateway_never_queried_about_itself():
    assert hd.resolve_via_gateway("10.0.0.1", "10.0.0.1") is None
    assert hd.resolve_via_gateway("10.0.0.5", None) is None
