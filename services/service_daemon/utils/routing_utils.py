#!/usr/bin/python

"""
Self-hosted routing + geocoding client for MyDaemon.check_travel() (SA-6).

Phase 0 investigation (see todo/todo_self_hosted_routing.md) measured a real, self-hosted OSRM
deployment live on this household's own production hardware: a metro-sized OpenStreetMap extract
(98MB source -> 262MB processed) preprocesses in under 2 minutes, serves routes from ~170MB idle
RAM, and returns real driving directions with zero external network calls per route. That's what
`get_route()` below talks to.

Geocoding a calendar event's free-text address is a different, much rarer need -- self-hosting
Nominatim needs meaningfully more RAM/disk than OSRM does even for one region, which wasn't
justified for how infrequently a genuinely new address shows up. `geocode_address()` instead uses
the public Nominatim API, which its own usage policy caps at "no heavy uses (an absolute maximum
of 1 request per second)" -- comfortably satisfied by caching every result in `geocode_cache`
(migration 032) so a given address is only ever looked up once, ever, not once per cycle. A
module-level rate limiter is a defensive floor under that cache, not the thing making this
policy-compliant on its own.

Every public function here fails closed and silent: an unreachable routing container, an
ungeocodable address, or a malformed response all return None. check_travel() must never turn
that into a fabricated estimate -- the exact anti-pattern the original Google-backed
implementation (removed in 08509ce) was criticized for.
"""

import logging
import os
import time
from datetime import datetime, timezone

import pymysql
import requests

logger = logging.getLogger("DaemonLog")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")

# service-daemon runs with network_mode: host (see docker-compose.yml), so the routing
# container is reached the same way MySQL/Kafka are -- a host port mapping, not a
# Docker Compose service-name hostname.
ROUTING_SERVICE_URL = os.environ.get("ROUTING_SERVICE_URL", "http://localhost:5005")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "Alfr3d-HomeButler/1.0 (self-hosted household assistant; see repo README)"
NOMINATIM_MIN_INTERVAL_SECONDS = 1.0
_last_nominatim_call = 0.0


def geocode_address(address):
    """Resolve a free-text address to a (latitude, longitude) tuple, or None if it can't be
    resolved. Checks `geocode_cache` first -- an address is sent to the public Nominatim API at
    most once, ever, including a cached "not found" outcome, so a bad address doesn't get
    re-queried every cycle it appears on a calendar event."""
    address = (address or "").strip()
    if not address:
        return None

    cached = _read_geocode_cache(address)
    if cached is not None:
        lat, lon = cached
        return (lat, lon) if lat is not None else None

    coords = _geocode_via_nominatim(address)
    _write_geocode_cache(address, coords)
    return coords


def fetch_home_coordinates(env_name):
    """This household's own (latitude, longitude) -- the routing origin for check_travel().
    Reuses the same `environment` row check_weather()/context_frame's environment snapshot
    already read, just the two columns that snapshot doesn't select (SA-4's frame only shares
    fields duplicated across 2+ rules; only this rule needs coordinates). Returns None if the
    environment has no location set yet, or on a DB error."""
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute("SELECT latitude, longitude FROM environment WHERE name = %s", (env_name,))
        row = cursor.fetchone()
        if not row or row[0] is None or row[1] is None:
            return None
        return (row[0], row[1])
    except pymysql.Error as e:
        logger.error(f"Routing: fetch_home_coordinates error: {e}")
        return None
    finally:
        if db:
            db.close()


def get_route(origin, dest):
    """origin/dest: (latitude, longitude) tuples. Returns {"duration_minutes", "distance_km"}
    from the self-hosted OSRM service, or None on any failure -- container unreachable, no
    route found, malformed response. Driving profile only (v1 scope)."""
    try:
        origin_lat, origin_lon = origin
        dest_lat, dest_lon = dest
        url = (
            f"{ROUTING_SERVICE_URL}/route/v1/driving/"
            f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        )
        response = requests.get(url, params={"overview": "false"}, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = data["routes"][0]
        return {
            "duration_minutes": route["duration"] / 60,
            "distance_km": route["distance"] / 1000,
        }
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        logger.error(f"Routing: get_route error: {e}")
        return None


def _read_geocode_cache(address):
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute(
            "SELECT latitude, longitude FROM geocode_cache WHERE address = %s", (address,)
        )
        return cursor.fetchone()
    except pymysql.Error as e:
        logger.error(f"Routing: geocode_cache read error: {e}")
        return None
    finally:
        if db:
            db.close()


def _write_geocode_cache(address, coords):
    lat, lon = coords if coords else (None, None)
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO geocode_cache (address, latitude, longitude, cached_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                latitude = VALUES(latitude), longitude = VALUES(longitude),
                cached_at = VALUES(cached_at)
            """,
            (address, lat, lon, datetime.now(timezone.utc)),
        )
        db.commit()
    except pymysql.Error as e:
        logger.error(f"Routing: geocode_cache write error: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


def _geocode_via_nominatim(address):
    global _last_nominatim_call
    elapsed = time.monotonic() - _last_nominatim_call
    if elapsed < NOMINATIM_MIN_INTERVAL_SECONDS:
        time.sleep(NOMINATIM_MIN_INTERVAL_SECONDS - elapsed)
    _last_nominatim_call = time.monotonic()
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            return None
        return (float(results[0]["lat"]), float(results[0]["lon"]))
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as e:
        # Deliberately not logging the address itself -- it's the one place in this module
        # handling free-text personal data (a calendar event's address), unlike a device MAC
        # or a lat/lon pair elsewhere in this file.
        logger.error(f"Routing: Nominatim geocode error: {e}")
        return None
