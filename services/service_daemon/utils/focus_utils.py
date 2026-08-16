#!/usr/bin/python

"""
Heuristic "is this calendar event a call?" detector for Alfr3d Daemon.

Kept separate from calendar_utils.py (which owns Google Calendar sync/fetch)
so sync/fetch logic doesn't get cluttered with unrelated text-heuristic code.

This is a v1 heuristic over the free-text `address`/`notes` fields already
stored in `calendar_events` (see calendar_utils.get_upcoming_events()).
Google Calendar's `conferenceData`/`hangoutLink` fields are not requested or
stored anywhere in this schema today — a real v2 would sync those fields and
match on them directly instead of pattern-matching text. Expect false
negatives for calls that don't paste a recognizable URL/label into address
or notes, and false positives for unrelated text that happens to mention a
marker word in passing (e.g. "re-zoom the picture before the meeting").
"""

import re

# Known conferencing URL hosts, plus a few bare friendly-label fallbacks for
# organizers who paste "Zoom" / "Google Meet" / "Teams meeting" instead of a
# raw link. Module-level so new markers can be added without touching
# looks_like_call().
CALL_MARKERS = (
    "zoom.us",
    "meet.google.com",
    "teams.microsoft.com",
    "webex.com",
    "zoom",
    "google meet",
    "teams meeting",
)

_CALL_MARKERS_RE = re.compile("|".join(re.escape(marker) for marker in CALL_MARKERS), re.IGNORECASE)


def looks_like_call(address, notes):
    """Heuristically decide whether a calendar event looks like a video/voice call.

    Case-insensitive substring match against `address` and `notes` for known
    conferencing markers (see CALL_MARKERS). This is a heuristic, not a
    reliable signal: it will miss calls that don't mention a recognizable
    URL/label, and can false-positive on unrelated text that happens to
    contain a marker word.
    """
    combined = " ".join(text for text in (address, notes) if text)
    if not combined:
        return False
    return bool(_CALL_MARKERS_RE.search(combined))
