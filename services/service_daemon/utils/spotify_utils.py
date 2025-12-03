#!/usr/bin/python

"""
Spotify utilities for Alfr3d Daemon.
TODO: Integrate Spotify Web API for playlist suggestions.

This module provides a lightweight, deterministic recommendation engine
that maps situational inputs (occupants, guests, time of day, weather)
to a small set of music attributes: mood, genre, energy and a playlist hint.

The implementation is intentionally simple and explainable so it can be
extended later with ML models or third-party API lookups.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("SpotifyUtils")


def get_playlist_suggestion(playlist_hint: str) -> str:
    """
    Suggest a playlist based on time and weather.
    TODO: Implement Spotify API integration for dynamic suggestions.
    Returns: Playlist name string.
    """
    # Placeholder: Hardcoded for now
    return playlist_hint


def _normalize_time_of_day(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def recommend(
    total_people: int, guest_count: int, time_of_day: str, weather: Any = None
) -> Dict[str, Any]:
    """
    Produce a recommendation dictionary.

    Args:
        total_people: total number of people present (residents + guests)
        guest_count: number of guests (may be 0)
        time_of_day: one of 'morning','day','evening','night' (or 'day'/'evening' used elsewhere)
        weather: either a string (e.g. 'rainy', 'sunny') or a dict containing keys
                 like 'subjective_feel', 'description', 'main', 'temp'.

    Returns:
        dict with keys: 'mood','genre','energy'(0-1),'tempo_hint','playlist_hint'
    """
    # Basic sanity for time_of_day
    if time_of_day is None:
        time_of_day = "day"
    if isinstance(time_of_day, int):
        time_of_day = _normalize_time_of_day(time_of_day)

    # Extract simple weather indicators
    subj = None
    if isinstance(weather, dict):
        subj = weather.get("subjective_feel") or weather.get("description")
    elif isinstance(weather, str):
        subj = weather

    # Base energy from people count
    if total_people <= 1:
        energy = 0.2
    elif total_people <= 3:
        energy = 0.4
    elif total_people <= 6:
        energy = 0.7
    else:
        energy = 0.9

    # Guests tend to increase energy slightly
    if guest_count and guest_count > 0:
        energy += 0.08

    # Time of day adjustments
    if time_of_day in ("evening", "night"):
        energy += 0.05
    if time_of_day == "morning":
        energy -= 0.05

    # Weather adjustments
    if subj:
        low_energy_keywords = ["rain", "drizzle", "snow", "cold", "bad weather"]
        high_energy_keywords = ["sunny", "perfect", "pleasant", "warm"]
        s = subj.lower()
        if any(k in s for k in low_energy_keywords):
            energy -= 0.12
        if any(k in s for k in high_energy_keywords):
            energy += 0.06

    # Clamp energy
    energy = max(0.0, min(1.0, energy))

    # Map energy to genre/mood/tempo
    if energy < 0.3:
        genre = "acoustic / ambient / lofi"
        mood = "relaxed"
        tempo = "slow"
        playlist_hint = (
            "chill, acoustic, lo-fi" if subj and "rain" in str(subj).lower() else "acoustic, mellow"
        )
    elif energy < 0.6:
        genre = "indie / soft pop / jazz"
        mood = "warm"
        tempo = "medium"
        playlist_hint = "indie / soft pop / mellow jazz"
    elif energy < 0.8:
        genre = "alt-rock / upbeat pop / nu-disco"
        mood = "upbeat"
        tempo = "medium-fast"
        playlist_hint = "upbeat pop, alt-rock, nu-disco"
    else:
        genre = "dance / house / party hits"
        mood = "energetic"
        tempo = "fast"
        playlist_hint = "party, dance, high-energy"

    # Compose a short friendly descriptor
    descriptor = f"{mood} {genre.split('/')[0].strip()}"

    return {
        "mood": descriptor,
        "genre": genre,
        "energy": round(energy, 2),
        "tempo_hint": tempo,
        "playlist_hint": playlist_hint,
    }


if __name__ == "__main__":
    # Quick demonstration
    examples = [
        (1, 0, "evening", {"subjective_feel": "Perfect / Great day", "temp": 22}),
        (4, 2, "day", {"subjective_feel": "Bad weather: rain", "temp": 10}),
        (8, 6, "night", {"subjective_feel": "Cold", "temp": -5}),
    ]
    for t in examples:
        print(t, "=>", recommend(*t))
