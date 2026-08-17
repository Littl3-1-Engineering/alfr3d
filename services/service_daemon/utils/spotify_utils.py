#!/usr/bin/python

"""
Spotify utilities for Alfr3d Daemon.

`recommend()` / `_normalize_time_of_day()` / `is_party_night()` live in
`common.spotify_utils` now (shared with the API service's on-demand
recommendation endpoint) and are re-exported here so existing call sites
(`alfr3ddaemon.py`, tests) keep working unchanged. `resolve_playlist()` turns
a recommendation's playlist hint into one specific, real Spotify playlist via
the household's own authorized Spotify account (see
`common.spotify_utils.find_playlist_for_hint`) — library match first, then a
global Spotify search, gracefully returning None if Spotify isn't connected.
"""

import logging
from typing import Dict, Any, Optional

from common.spotify_utils import recommend, _normalize_time_of_day, is_party_night  # noqa: F401

logger = logging.getLogger("SpotifyUtils")


def resolve_playlist(playlist_hint: str, genre: str = "") -> Optional[Dict[str, Any]]:
    """Resolve a playlist hint into a real Spotify playlist (id/name/uri/url/image/source).

    Returns None when Spotify isn't connected or nothing matched — callers must
    treat that as "no specific playlist available right now", not an error.
    """
    try:
        from common import spotify_utils as spotify_api

        playlist, err = spotify_api.find_playlist_for_hint(playlist_hint, genre)
        if err or not playlist:
            if err:
                logger.info(f"resolve_playlist: no playlist resolved for '{playlist_hint}': {err}")
            return None
        return playlist
    except Exception as e:
        logger.error(f"resolve_playlist error: {e}")
        return None


if __name__ == "__main__":
    # Quick demonstration
    examples = [
        (1, 0, "evening", {"subjective_feel": "Perfect / Great day", "temp": 22}, False),
        (4, 2, "day", {"subjective_feel": "Bad weather: rain", "temp": 10}, False),
        (8, 6, "night", {"subjective_feel": "Cold", "temp": -5}, True),  # Friday/Saturday night
    ]
    for t in examples:
        print(t, "=>", recommend(*t[:4], is_party_night=t[4]))
