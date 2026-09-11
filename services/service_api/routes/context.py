"""Launcher-reported context signals: surface state, attention telemetry, and
situational-awareness card interactions.

Deliberately separate from routes/devices.py or routes/music.py: this isn't
about a specific ALFR3D-owned resource, it's consumers (the React dashboard,
the Nexus Launcher) telling the backend about their own UI state/usage so
alfr3ddaemon.py's DISPLAY_RULES checks can react to it --
check_cross_surface_continuity() (surface state),
check_attention_focus()/check_wind_down_signal() (attention telemetry), and
decide_displays()'s suppression pass (card interactions).
See todo/todo_cross_surface_continuity.md, todo/todo_attention_telemetry.md,
todo/todo_card_feedback_loop.md.
"""

import logging
import math
import uuid
from datetime import datetime, timezone

import orjson
from fastapi import APIRouter, Depends, HTTPException

from common import db_connection
from auth.dependencies import require_permission
from dependencies import ALFR3D_ENV_NAME, get_producer

logger = logging.getLogger("ApiLog")
router = APIRouter(prefix="/api", tags=["context"])

# Mirrors alfr3ddaemon.SURFACE_STATE_CONFIG_KEY / ATTENTION_TELEMETRY_CONFIG_KEY -- kept in sync
# manually since service_api and service_daemon are separate deployables with no shared
# constants module today (same as NOW_PLAYING_CONFIG_KEY's own precedent).
SURFACE_STATE_CONFIG_KEY = "launcher_surface_state"
ATTENTION_TELEMETRY_CONFIG_KEY = "launcher_attention_telemetry"


def _upsert_config_json(cursor, key, value_dict):
    """UPDATE-then-INSERT-if-0-rows upsert of a JSON blob into `config`, the same pattern
    spotify_utils.save_spotify_credentials() and alfr3ddaemon._write_now_playing_config() use.
    Factored out here now that this file has two callers."""
    value = orjson.dumps(value_dict).decode("utf-8")
    cursor.execute("UPDATE config SET value = %s WHERE name = %s", (value, key))
    if cursor.rowcount == 0:
        cursor.execute("INSERT INTO config (name, value) VALUES (%s, %s)", (key, value))


@router.post("/context/surface-state")
async def report_surface_state(
    data: dict = None, _perm=Depends(require_permission("context", "surface_state"))
):
    """Upsert the launcher's currently-active surface into `config`."""
    try:
        data = data or {}
        state = {
            "active_surface": data.get("active_surface"),
            "terminal_session_active": bool(data.get("terminal_session_active", False)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with db_connection() as db:
            cursor = db.cursor()
            _upsert_config_json(cursor, SURFACE_STATE_CONFIG_KEY, state)
            db.commit()
        return {"message": "Surface state recorded"}
    except Exception as e:
        logger.error(f"Error recording surface state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context/attention-telemetry")
async def report_attention_telemetry(
    data: dict = None, _perm=Depends(require_permission("context", "attention_telemetry"))
):
    """Upsert the launcher's most recent attention-telemetry snapshot (unlock count, window
    switch count, per-category dwell time) into `config`, and also append it to
    `attention_telemetry_history` (SA-2) so check_attention_focus()/check_wind_down_signal() can
    compare against this household's own rolling distribution instead of only a fixed threshold.
    The `config` snapshot is unchanged -- this is purely an additional destination."""
    try:
        data = data or {}
        unlock_count = int(data.get("unlock_count", 0))
        switch_count = int(data.get("switch_count", 0))
        dwell_by_category_ms = data.get("dwell_by_category_ms") or {}
        window_start_ms = data.get("window_start_ms")
        window_end_ms = data.get("window_end_ms")
        reported_at = datetime.now(timezone.utc)
        snapshot = {
            "unlock_count": unlock_count,
            "switch_count": switch_count,
            "dwell_by_category_ms": dwell_by_category_ms,
            "window_start_ms": window_start_ms,
            "window_end_ms": window_end_ms,
            "reported_at": reported_at.isoformat(),
        }
        with db_connection() as db:
            cursor = db.cursor()
            _upsert_config_json(cursor, ATTENTION_TELEMETRY_CONFIG_KEY, snapshot)
            cursor.execute(
                "INSERT INTO attention_telemetry_history "
                "(unlock_count, switch_count, dwell_by_category_ms, window_start_ms, "
                "window_end_ms, reported_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    unlock_count,
                    switch_count,
                    orjson.dumps(dwell_by_category_ms).decode("utf-8"),
                    window_start_ms,
                    window_end_ms,
                    reported_at,
                ),
            )
            db.commit()
        return {"message": "Attention telemetry recorded"}
    except Exception as e:
        logger.error(f"Error recording attention telemetry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# POST /api/context/device-location bounds (todo/todo_device_location_reporting.md).
_LOCATION_MAX_ACCURACY_M = 20_000.0  # a fix claiming worse than 20 km is a bad reading, not data
_LOCATION_MAX_FIX_AGE_DAYS = 180  # matches cleanup_device_location_history_event's retention
_LOCATION_MAX_FUTURE_SKEW_MS = 60_000.0  # tolerate a minute of device-clock skew, no more

# Geofence -> SA-12 household_events producer (todo/todo_transition_learning.md deferred
# follow-up). "Home" is a circle of this radius around the household's own `environment`
# coordinates. 3km, not a few houses' width: todo_device_location_reporting.md's Phase 0
# on-device investigation found ACCESS_COARSE_LOCATION hard-clamps every fix -- network, gps,
# fused, a fresh getCurrentLocation, all of them -- to a ~2km grid, with consecutive reads at
# the *same physical spot* landing up to ~2.2km apart. Its own conclusion: "any server-side
# geofence needs a wide band (~3km) ... or the 2km jitter will flap it." A radius smaller than
# the fixes' own accuracy (confirmed live: real production fixes came back accuracy_m=2000
# almost uniformly) makes confident "home" unreachable -- _geofence_state() can never satisfy
# `distance + accuracy_m <= radius_m` if accuracy_m alone already exceeds radius_m. First
# deploy (2026-09-11) shipped with 300m and, checked against real production data the same
# day, produced zero transitions despite a real ~13.6km trip sitting in the raw fixes -- this
# is the fix.
_HOME_GEOFENCE_RADIUS_M = 3_000.0


def _haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters between two (lat, lon) points."""
    r = 6_371_000.0  # Earth mean radius, meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _geofence_state(distance_m, accuracy_m, radius_m=_HOME_GEOFENCE_RADIUS_M):
    """Classify one fix as confidently "home", confidently "away", or `None` (ambiguous --
    `accuracy_m` isn't tight enough to place the fix on one side of the radius, so the caller
    should leave the running state alone rather than flap on a noisy reading). A fix with no
    reported accuracy falls back to a plain threshold -- less confident, but still usable, the
    same tradeoff the raw "network" fixes already make elsewhere in this pipeline (see the real
    ~3h-trip density pass in todo_device_location_reporting.md)."""
    if accuracy_m is None:
        return "home" if distance_m <= radius_m else "away"
    if distance_m + accuracy_m <= radius_m:
        return "home"
    if distance_m - accuracy_m > radius_m:
        return "away"
    return None


def _compute_geofence_transitions(home, baseline_state, fixes, radius_m=_HOME_GEOFENCE_RADIUS_M):
    """Walk `fixes` (ascending by `captured_at`, each `(lat, lon, accuracy_m, captured_at)`)
    forward from `baseline_state` ("home"/"away"/`None`) and return the ordered list of
    `(verb, captured_at)` crossings -- "left_area" on home->away, "entered_area" on away->home.

    Ambiguous fixes (see `_geofence_state`) never move the state, so a run of low-accuracy
    readings near the boundary can't cause flapping. No baseline (a brand-new install's very
    first fixes) never itself counts as a transition -- there's nothing to transition *from*,
    just an initial state being established. A batch that itself spans a full round trip
    (fixes queued while offline, then flushed together) can yield more than one crossing; each
    is returned.
    """
    home_lat, home_lon = home
    transitions = []
    state = baseline_state
    for lat, lon, accuracy_m, captured_at in fixes:
        distance_m = _haversine_m(home_lat, home_lon, lat, lon)
        new_state = _geofence_state(distance_m, accuracy_m, radius_m)
        if new_state is None or new_state == state:
            continue
        if state is not None:
            verb = "left_area" if new_state == "away" else "entered_area"
            transitions.append((verb, captured_at))
        state = new_state
    return transitions


def _fetch_home_coordinates(cursor):
    """This household's own (latitude, longitude) from the `environment` row for
    `ALFR3D_ENV_NAME`, or `None` if unset. Same source table/columns as
    `service_daemon.routing_utils.fetch_home_coordinates()` (SA-6) -- service_api can't import
    across the service boundary, so this re-reads the same two columns directly."""
    cursor.execute(
        "SELECT latitude, longitude FROM environment WHERE name = %s", (ALFR3D_ENV_NAME,)
    )
    row = cursor.fetchone()
    if not row or row[0] is None or row[1] is None:
        return None
    return (float(row[0]), float(row[1]))


_BASELINE_LOOKBACK_FIXES = 20  # how far back to search for the last *confidently* classified fix


def _emit_geofence_transition_events(cursor, user_id, install_id, fixes):
    """Detect and record SA-12 (todo_transition_learning.md) `subject_type=user` /
    `verb=left_area|entered_area` household events from one install's just-accepted batch of
    location fixes, on the same event-stream -> `service_api._persist_household_events()` path
    every other structured producer uses (SA-11 / Branch C).

    Tracked per `client_install_id`, matching `device_location_history`'s own per-device design
    (todo_device_location_reporting.md design decision #3) -- fixes are never merged across a
    user's other devices, so a phone leaving while a tablet stays home reports as that phone's
    own transition, not the household's. `fixes` must already be sorted ascending by
    `captured_at`. Best-effort: any failure here (no home coordinates set yet, a DB hiccup, no
    Kafka producer) must never affect the location-report response the caller already
    succeeded at.
    """
    if not fixes:
        return
    try:
        home = _fetch_home_coordinates(cursor)
        if home is None:
            return

        # The single most recent prior fix is very often itself ambiguous (coarse-location
        # accuracy is commonly as wide as the geofence band itself -- see
        # _HOME_GEOFENCE_RADIUS_M's comment), so walk backward through recent history for the
        # last one that actually resolves to a confident state rather than silently losing a
        # known "away"/"home" baseline to one noisy row.
        cursor.execute(
            "SELECT latitude, longitude, accuracy_m FROM device_location_history "
            "WHERE client_install_id = %s AND captured_at < %s "
            "ORDER BY captured_at DESC LIMIT %s",
            (install_id, fixes[0][3], _BASELINE_LOOKBACK_FIXES),
        )
        baseline_state = None
        for b_lat, b_lon, b_accuracy in cursor.fetchall():
            baseline_distance = _haversine_m(home[0], home[1], float(b_lat), float(b_lon))
            candidate_state = _geofence_state(
                baseline_distance, float(b_accuracy) if b_accuracy is not None else None
            )
            if candidate_state is not None:
                baseline_state = candidate_state
                break

        transitions = _compute_geofence_transitions(home, baseline_state, fixes)
        if not transitions:
            return

        producer = get_producer()
        if not producer:
            return
        for verb, captured_at in transitions:
            producer.send(
                "event-stream",
                {
                    "id": f"geofence_{verb}_{user_id}_{install_id}_"
                    f"{captured_at.strftime('%Y%m%d%H%M%S%f')}",
                    "type": "presence",
                    "message": f"user {user_id} {verb.replace('_', ' ')}",
                    "time": captured_at.isoformat(),
                    "service": "api",
                    "subject_type": "user",
                    "subject_id": str(user_id),
                    "verb": verb,
                },
            )
        producer.flush()
    except Exception as e:  # noqa: BLE001 -- must never break the location-report response
        logger.error(f"Failed to emit geofence transition event(s): {e}")


@router.post("/context/device-location")
async def report_device_location(
    data: dict = None, user=Depends(require_permission("context", "device_location"))
):
    """Ingest a batch of approximate location fixes from one ALFR3D Deck install into
    `device_location_history`.

    Per-*device*: keyed by `client_install_id` (a stable UUID the Deck generates), never
    merged across the reporting user's other devices. `user_id` is taken from the JWT, never
    the request body. `device_id` is left NULL -- a later device-linking step ties the install
    to its arp-scan `device` row.

    No DISPLAY_RULES check reads this table yet. It remains a data-collection pipeline for
    later SA work (`check_travel()` origin, location baselines) beyond the one consumer that
    now exists: each accepted batch also feeds `_emit_geofence_transition_events()`, the SA-12
    (todo_transition_learning.md) geofence enter/exit producer. Returns
    `{"accepted": n, "rejected": m}` -- individual bad fixes are dropped, not fatal.
    """
    try:
        data = data or {}
        install_id = str(data.get("client_install_id") or "").strip()
        try:
            uuid.UUID(install_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="client_install_id must be a UUID")

        fixes = data.get("fixes")
        if not isinstance(fixes, list) or not fixes:
            raise HTTPException(status_code=400, detail="fixes must be a non-empty list")

        reported_at = datetime.now(timezone.utc)
        now_ms = reported_at.timestamp() * 1000.0
        oldest_allowed_ms = now_ms - _LOCATION_MAX_FIX_AGE_DAYS * 86_400_000.0

        rows = []
        rejected = 0
        for fix in fixes:
            if not isinstance(fix, dict):
                rejected += 1
                continue
            try:
                lat = float(fix["latitude"])
                lon = float(fix["longitude"])
                captured_ms = float(fix["captured_at_ms"])
            except (KeyError, TypeError, ValueError):
                rejected += 1
                continue
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                rejected += 1
                continue
            too_new = captured_ms > now_ms + _LOCATION_MAX_FUTURE_SKEW_MS
            if too_new or captured_ms < oldest_allowed_ms:
                rejected += 1
                continue

            accuracy = fix.get("accuracy_m")
            try:
                accuracy = float(accuracy) if accuracy is not None else None
            except (TypeError, ValueError):
                accuracy = None
            if accuracy is not None and not (0.0 <= accuracy <= _LOCATION_MAX_ACCURACY_M):
                accuracy = None

            provider = fix.get("provider")
            provider = str(provider)[:16] if provider is not None else None

            captured_at = datetime.fromtimestamp(captured_ms / 1000.0, tz=timezone.utc)
            rows.append(
                (
                    install_id,
                    int(user.id),
                    lat,
                    lon,
                    accuracy,
                    provider,
                    "deck",
                    captured_at,
                    reported_at,
                )
            )

        if rows:
            with db_connection() as db:
                cursor = db.cursor()
                cursor.executemany(
                    "INSERT INTO device_location_history "
                    "(client_install_id, user_id, latitude, longitude, accuracy_m, provider, "
                    "source, captured_at, reported_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )
                db.commit()
                # (lat, lon, accuracy_m, captured_at) per row -- indices 2/3/4/7 of the tuple
                # built above. Sorted defensively: a queued-while-offline batch should already
                # arrive in capture order, but the geofence walk depends on it.
                fixes_for_geofence = sorted(
                    ((r[2], r[3], r[4], r[7]) for r in rows), key=lambda f: f[3]
                )
                _emit_geofence_transition_events(cursor, user.id, install_id, fixes_for_geofence)
        return {"accepted": len(rows), "rejected": rejected}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording device location: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_CARD_INTERACTION_ACTIONS = {"shown", "tapped", "dismissed", "expired"}


@router.post("/context/card-interaction")
async def report_card_interaction(
    data: dict = None, _perm=Depends(require_permission("context", "card_interaction"))
):
    """Record a `card_interactions` row for one situational-awareness card
    (SA-1). Card identity is `(rule_id, subject_key)` -- see
    todo/todo_card_feedback_loop.md for why that's the identity instead of
    `(mode, content_hash)`. `rule_id` is the DISPLAY_RULES id
    (`alfr3ddaemon.py`), not the card's own `mode` field -- the two aren't
    always the same (`check_gatherings`/rule id "music" and
    `check_now_playing`/rule id "now_playing" both stamp `"mode": "music"` on
    their card).

    `shown` must be reported by the consumer only after actually rendering
    the card (i.e. after any client-side truncation like
    `MAX_DISPLAY_CARDS`) -- never assumed by the daemon, which has no way to
    know what a truncated-away card's fate was.
    """
    try:
        data = data or {}
        rule_id = data.get("rule_id")
        action = data.get("action")
        if not rule_id or action not in _CARD_INTERACTION_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"rule_id and one of {sorted(_CARD_INTERACTION_ACTIONS)} are required",
            )
        subject_key = data.get("subject_key") or ""
        user_id = data.get("user_id")
        with db_connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO card_interactions "
                "(rule_id, subject_key, action, user_id, occurred_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (rule_id, subject_key, action, user_id, datetime.now(timezone.utc)),
            )
            db.commit()
        return {"message": "Card interaction recorded"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording card interaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))
