"""Spotify now-playing monitor for the ALFR3D daemon.

Polls the Spotify Web API (via ``common.spotify_utils.get_playback_state``) on a
background thread and publishes a Kafka ``event-stream`` message whenever a new
song begins playing, so the Nexus now-playing card (and the EventStream) can
react without the frontend polling anything.

Events published:
  - ``{"type": "audio", "message": "playing song: <title> by <artist>",
      "track": {...}, "is_playing": True, "time": <iso>}`` when a new track starts
  - ``{"type": "audio", "message": "playback stopped", "track": None,
      "is_playing": False, "time": <iso>}`` when playback pauses/stops

No event is emitted while the same track keeps playing, so the stream only
carries actual song changes.
"""

import logging
import threading
import time
from datetime import datetime, timezone

import orjson

from common import get_producer
from common import spotify_utils as spotify_api

logger = logging.getLogger("DaemonLog")

POLL_INTERVAL = 10  # seconds


def _build_track_event(state, track):
    """Build the "playing song" event dict for a currently-playing track."""
    title = track.get("name") or "unknown track"
    artists = track.get("artists") or []
    artist_text = ", ".join(artists)
    message = f"playing song: {title}"
    if artist_text:
        message += f" by {artist_text}"
    return {
        "id": f"song_start_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "type": "audio",
        "message": message,
        "track": {
            "id": track.get("id"),
            "name": title,
            "artists": artists,
            "album": track.get("album"),
            "album_art": track.get("album_art"),
            "duration_ms": track.get("duration_ms"),
            "uri": track.get("uri"),
            "progress_ms": state.get("progress_ms", 0),
        },
        "is_playing": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "subject_type": "track",
        "subject_id": track.get("id"),
        "verb": "play_start",
    }


def _build_stop_event():
    """Build the "playback stopped" event dict."""
    return {
        "id": f"song_end_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "type": "audio",
        "message": "playback stopped",
        "track": None,
        "is_playing": False,
        "time": datetime.now(timezone.utc).isoformat(),
        "subject_type": "track",
        "verb": "play_stop",
    }


def evaluate(state, last_track_id, last_is_playing):
    """Decide what to publish for one playback-state sample.

    Pure function (no I/O) so it is trivially unit-testable. Returns
    ``(event_or_None, new_track_id, new_is_playing)``. Only transition points
    emit an event:
      - a new track starts (track id changed while playing), or
      - playback stops (was playing, now not).
    """
    if not state or state.get("error"):
        return None, None, False

    track = state.get("item") or {}
    track_id = track.get("id")
    is_playing = bool(state.get("is_playing"))

    if is_playing and (track_id != last_track_id or not last_is_playing):
        return _build_track_event(state, track), track_id, True
    if last_is_playing and not is_playing:
        return _build_stop_event(), None, False

    return None, track_id, is_playing


def _publish(event):
    if not event:
        return
    p = get_producer()
    if not p:
        logger.warning("No Kafka producer available; dropping now-playing event")
        return
    p.send("event-stream", orjson.dumps(event))
    logger.info(f"Published now-playing event: {event.get('message')}")


def monitor_now_playing(stop_event=None, poll_interval=POLL_INTERVAL):
    """Background loop: poll playback state and publish song-change events."""
    logger.info("Starting now-playing monitor")
    last_track_id = None
    last_is_playing = False
    while not (stop_event and stop_event.is_set()):
        try:
            state = spotify_api.get_playback_state()
        except Exception as e:
            logger.error(f"Now-playing monitor error: {e}")
            state = None
        event, last_track_id, last_is_playing = evaluate(state, last_track_id, last_is_playing)
        _publish(event)
        if stop_event is not None:
            stop_event.wait(poll_interval)
        else:
            time.sleep(poll_interval)
    logger.info("Now-playing monitor stopped")


def start_now_playing_monitor():
    """Start the monitor on a daemon thread; returns the thread."""
    thread = threading.Thread(target=monitor_now_playing, daemon=True)
    thread.start()
    return thread
