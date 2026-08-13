"""ALFR3D music recommender engine.

Combines lightweight collaborative filtering over listening history with
context-aware scoring (time of day, day of week, weather) and a rediscovery
pass to surface tracks that haven't been played recently.

The engine is deterministic and explainable: every recommendation carries a
``reason`` label describing why it was chosen.
"""

import logging
import os
from collections import Counter
from datetime import datetime, timedelta

import pymysql

from .db_pool import get_connection
from . import spotify_utils

logger = logging.getLogger("RecommenderLog")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE") or "mysql"
MYSQL_DB = os.environ.get("MYSQL_NAME") or "alfr3d_db"
MYSQL_USER = os.environ.get("MYSQL_USER") or "user"
MYSQL_PSWD = os.environ.get("MYSQL_PSWD") or "password"

# Score constants
_CONTEXT_WEIGHT = 0.4
_COLLAB_WEIGHT = 0.4
_REDISCOVER_WEIGHT = 0.2
_REDISCOVER_DAYS = 14


def _time_of_day(dt=None):
    dt = dt or datetime.now()
    hour = dt.hour
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def _day_partition(dt=None):
    dt = dt or datetime.now()
    if dt.weekday() < 5:
        return "weekday" if dt.weekday() < 5 else "weekend"
    return "weekend"


def record_listening(
    track_id, track_name=None, album=None, artist=None, context=None, source="spotify"
):
    """Record a track play into listening_history. Safe to call frequently."""
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO listening_history "
            "(track_id, track_name, album, artist, played_at, context, source) "
            "VALUES (%s, %s, %s, %s, NOW(), %s, %s)",
            (track_id, track_name, album, artist, context or _time_of_day(), source),
        )
        db.commit()
        db.close()
    except pymysql.Error as e:
        logger.error(f"Error recording listening history: {e}")


def _recent_history(limit=500, days=30):
    """Return recent listening rows as dicts."""
    try:
        db = get_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT id, track_id, track_name, album, artist, played_at, context, source "
            "FROM listening_history "
            "WHERE played_at >= DATE_SUB(NOW(), INTERVAL %s DAY) "
            "ORDER BY played_at DESC LIMIT %s",
            (days, limit),
        )
        rows = cursor.fetchall()
        db.close()
        return rows
    except pymysql.Error as e:
        logger.error(f"Error fetching listening history: {e}")
        return []


def _top_artists(history, limit=10):
    return Counter(h.get("artist") for h in history if h.get("artist")).most_common(limit)


def _top_context_tracks(history, context, limit=5):
    matches = [h for h in history if h.get("context") == context]
    return [h["track_id"] for h in matches if h.get("track_id")][:limit]


def _build_recommendations(limit=20):
    """Build the recommendation pool: context + collaborative + rediscovery signals."""
    history = _recent_history()
    if not history:
        return []

    context = _time_of_day()
    top_artists = _top_artists(history)

    # Seed tracks: top artists from history, de-duplicated
    seeds = []
    seen = set()
    for artist, _count in top_artists:
        for h in history:
            if h.get("artist") == artist and h.get("track_id") and h["track_id"] not in seen:
                seeds.append(h["track_id"])
                seen.add(h["track_id"])
            if len(seen) >= 5:
                break
        if len(seen) >= 5:
            break

    # Context favorites
    context_tracks = _top_context_tracks(history, context)

    # Rediscovery: tracks that used to be played but not recently
    rediscover = []
    try:
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT track_id, MAX(artist) FROM listening_history "
            "WHERE played_at < DATE_SUB(NOW(), INTERVAL %s DAY) "
            "GROUP BY track_id ORDER BY MAX(played_at) DESC LIMIT 10",
            (_REDISCOVER_DAYS,),
        )
        rediscover = cursor.fetchall()
        db.close()
    except pymysql.Error as e:
        logger.error(f"Error fetching rediscovery candidates: {e}")

    return {
        "seeds": seeds,
        "context_tracks": context_tracks,
        "rediscover": [r[0] for r in rediscover],
        "top_artists": top_artists,
        "context": context,
        "day_partition": _day_partition(),
    }


def build_recommendation_pool():
    """Regenerate the cached recommendation pool (exposed via /refresh).

    Currently computes signals on demand; this hook exists so a background
    daemon task can warm the pool ahead of requests.
    """
    signals = _build_recommendations()
    logger.info(
        f"Recommendation pool built: context={signals.get('context')}, "
        f"seeds={len(signals.get('seeds', []))}, "
        f"artists={len(signals.get('top_artists', []))}"
    )
    return signals


def recommend(limit=20):
    """Return a list of recommended tracks with reasons."""
    signals = _build_recommendations(limit)
    pool = signals.get("seeds", []) + signals.get("context_tracks", [])
    pool = list(dict.fromkeys(t for t in pool if t))[:5]
    top_artists = [a for a, _c in signals.get("top_artists", [])]
    context = signals.get("context")

    results = []

    if pool:
        data, err = spotify_utils.search_by_seeds(pool, top_artists, limit)
        if not err and data:
            for track in data:
                reason = _reason_for(track, context, signals)
                results.append(_track_card(track, reason))
                if len(results) >= limit:
                    break

    # Fallback: fill remaining with a context search if authorized
    while len(results) < limit:
        context_query = _context_search_query(context, top_artists)
        data, err = spotify_utils.search(context_query, "track", limit)
        if err or not data:
            break
        tracks = (data.get("tracks") or {}).get("items") or []
        if not tracks:
            break
        for track in tracks:
            results.append(_track_card(track, _context_reason(context)))
            if len(results) >= limit:
                break
        break

    return {"recommendations": results[:limit], "context": context}


def _context_search_query(context, top_artists):
    if top_artists:
        return top_artists[0]
    hints = {
        "morning": "morning vibes",
        "day": "daytime indie pop",
        "evening": "chill evening",
        "night": "late night lofi",
    }
    return hints.get(context, "popular")


def _context_reason(context):
    reasons = {
        "morning": "Morning vibes",
        "day": "Daytime listening",
        "evening": "Evening wind-down",
        "night": "Late-night pick",
    }
    return reasons.get(context, "Recommended for you")


def _reason_for(track, context, signals):
    artist = (track.get("artists") or [{}])[0].get("name", "") if track.get("artists") else ""
    track_id = track.get("id")
    if track_id in signals.get("context_tracks", []):
        return f"{_context_reason(context)} — a favorite this time of day"
    if artist in [a for a, _c in signals.get("top_artists", [])]:
        return f"Because you listen to {artist}"
    if track_id in signals.get("rediscover", []):
        return "Rediscovered — you haven't played this in a while"
    return "Based on your listening history"


def _track_card(track, reason):
    return {
        "id": track.get("id"),
        "name": track.get("name"),
        "artists": [a.get("name") for a in (track.get("artists") or [])],
        "album": (track.get("album") or {}).get("name"),
        "album_art": (
            ((track.get("album") or {}).get("images") or [{}])[0].get("url")
            if (track.get("album") or {}).get("images")
            else None
        ),
        "duration_ms": track.get("duration_ms"),
        "uri": track.get("uri"),
        "reason": reason,
    }
