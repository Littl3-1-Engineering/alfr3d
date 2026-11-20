"""Hostname discovery for LAN devices found by the ARP scan.

Why not just ``socket.gethostbyaddr``: that goes through the container's resolver, which
Docker points at public DNS (``/etc/docker/daemon.json``). Public resolvers have no records for
RFC1918 addresses, so every lookup failed. The names we want live on the LAN itself, so ask the
LAN directly, in order of reliability:

1. Reverse (PTR) lookup against the default gateway. The router is the DHCP server and
   registers the hostname each client announced when it leased its address.
2. Unicast mDNS reverse lookup sent straight to the device (port 5353). Catches devices
   (Macs, phones, Linux boxes running avahi) that never announce a DHCP hostname.
3. The system resolver, as a last resort for setups whose resolver does know the LAN.
"""

import logging
import socket
import subprocess
from typing import Optional

import dns.exception
import dns.message
import dns.name
import dns.query
import dns.rcode
import dns.rdataclass
import dns.rdatatype
import dns.reversename

logger = logging.getLogger("DevicesLog")

DNS_TIMEOUT = 1.5
MDNS_PORT = 5353
# Names that carry no information about the device itself.
_IGNORED_NAMES = {"_gateway", "localhost", "unknown", ""}
# mDNS "QU" bit: ask the responder to answer by unicast to our source port.
_MDNS_UNICAST_RESPONSE = 0x8000


def default_gateway() -> Optional[str]:
    """Return the default route's gateway IPv4 address, or None."""
    try:
        out = subprocess.run(
            ["ip", "-4", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    parts = out.split()
    if "via" in parts:
        idx = parts.index("via") + 1
        if idx < len(parts):
            return parts[idx]
    return None


def clean_name(raw: Optional[str], ip: str = "") -> Optional[str]:
    """Normalise a DNS name into a display hostname; None if it's uninformative."""
    if not raw:
        return None
    name = raw.strip().rstrip(".")
    if name.lower() in _IGNORED_NAMES or name == ip:
        return None
    return name


def _first_ptr(response: dns.message.Message) -> Optional[str]:
    if response.rcode() != dns.rcode.NOERROR:
        return None
    for rrset in response.answer:
        if rrset.rdtype == dns.rdatatype.PTR:
            for rdata in rrset:
                return rdata.target.to_text()
    return None


def ptr_via_server(ip: str, server: str, port: int = 53, rdclass: int = dns.rdataclass.IN):
    """Send one reverse lookup for ``ip`` to ``server``; return the PTR target text or None."""
    query = dns.message.make_query(
        dns.reversename.from_address(ip), dns.rdatatype.PTR, rdclass=rdclass
    )
    try:
        response = dns.query.udp(
            query, server, port=port, timeout=DNS_TIMEOUT, ignore_unexpected=True
        )
    except (dns.exception.DNSException, OSError):
        return None
    return _first_ptr(response)


def resolve_via_gateway(ip: str, gateway: Optional[str]) -> Optional[str]:
    if not gateway or gateway == ip:
        return None
    return clean_name(ptr_via_server(ip, gateway), ip)


def resolve_via_mdns(ip: str) -> Optional[str]:
    return clean_name(
        ptr_via_server(ip, ip, port=MDNS_PORT, rdclass=dns.rdataclass.IN | _MDNS_UNICAST_RESPONSE),
        ip,
    )


def resolve_via_system(ip: str) -> Optional[str]:
    try:
        return clean_name(socket.gethostbyaddr(ip)[0], ip)
    except (socket.herror, socket.gaierror, OSError):
        return None


def discover_hostname(ip: str, gateway: Optional[str] = None) -> Optional[str]:
    """Best-effort hostname for ``ip``; None when every method comes up empty."""
    gateway = gateway if gateway is not None else default_gateway()
    for method, lookup in (
        ("gateway-ptr", lambda: resolve_via_gateway(ip, gateway)),
        ("mdns", lambda: resolve_via_mdns(ip)),
        ("system", lambda: resolve_via_system(ip)),
    ):
        name = lookup()
        if name:
            logger.debug("Hostname for %s via %s: %s", ip, method, name)
            return name
    logger.debug("No hostname found for %s", ip)
    return None
