#!/usr/bin/python

"""
Tiered "is this calendar event a call?" detector for Alfr3d Daemon (SA-7).

Kept separate from calendar_utils.py (which owns Google Calendar sync/fetch)
so sync/fetch logic doesn't get cluttered with unrelated detection code.

Two tiers, in order:
1. `conference_uri` present (calendar_utils._extract_conference_info(), synced from
   Google's `conferenceData`/`hangoutLink`) -> "confirmed". The calendar's own
   structured conferencing data, not a guess.
2. No conference data, but the free-text `address`/`notes` fields match a known
   conferencing marker -> "probable". The original v1 heuristic, kept rather than
   retired: a Zoom/Teams link a human pastes into notes by hand -- not created
   through the calendar's structured conferencing integration -- has no
   `conference_uri` either, and losing that case would be a real regression.
   Still has the same known false-positive shape as before (e.g. "re-zoom the
   picture before the meeting" mentions "zoom" in passing) -- that's an accepted
   limitation of tier 2, not something tier 2 tries to fix; it just never gets
   promoted to "confirmed" on text content alone.
3. Neither -> `None`, no call detected.

Callers should treat the tiers as calibrated confidence, not just a bool -- see
alfr3ddaemon.check_focus_needed()'s card content, which speaks with more certainty
for "confirmed" than "probable".
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

CONFIRMED = "confirmed"
PROBABLE = "probable"


def looks_like_call(address, notes, conference_uri=None):
    """Decide whether a calendar event looks like a video/voice call, tiered by confidence.

    Returns `CONFIRMED` ("confirmed") if `conference_uri` is present -- the
    calendar's own structured conferencing data. Otherwise falls back to a
    case-insensitive substring match against `address`/`notes` for known
    conferencing markers (see CALL_MARKERS), returning `PROBABLE` ("probable")
    on a match. Returns `None` if neither signal fires.
    """
    if conference_uri:
        return CONFIRMED
    combined = " ".join(text for text in (address, notes) if text)
    if combined and _CALL_MARKERS_RE.search(combined):
        return PROBABLE
    return None
