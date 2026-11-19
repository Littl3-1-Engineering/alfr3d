"""Pure helpers for the card rules: no database, no clock, no engine state.

Step 1 of the engine.py split (todo/sa/todo_parallel_capture_track.md, item 4): moved verbatim out
of engine.py, which re-exports every name so `engine.X` still resolves (tests patch it there).
"""


def _cross_surface_continuity_subject_key(card):
    return f"{card.get('resume_type')}:{card.get('resume_target')}"


def _span_text(minutes):
    """ "45 min", "5 h" or "3 days" for a length of time in minutes."""
    if minutes < 120:
        return f"{minutes} min"
    if minutes < 48 * 60:
        return f"{round(minutes / 60.0)} h"
    return f"{round(minutes / 1440.0)} days"


CARD_SUBJECT_KEY_EXTRACTORS = {
    "rhythm_break_anomaly": lambda card: card.get("entity_name") or "",
    # One device_health card per device, so dismissing the camera's doesn't hide the sensor's.
    "device_health": lambda card: card.get("entity_name") or "",
    # LF-3: one presence_deviation card per person, so dismissing one doesn't hide another's.
    "presence_deviation": lambda card: card.get("entity_name") or "",
    "cross_surface_continuity": _cross_surface_continuity_subject_key,
    # SA-3: departure_anomaly is rhythm_break_anomaly's human analogue -- dismissing one
    # resident's "still home" card must not suppress a different resident's.
    "departure_anomaly": lambda card: card.get("entity_name") or "",
    # Continuous-stay guest decay: dismissing one overstaying guest's advisory must not
    # suppress a different guest's.
    "guest_overstay_advisory": lambda card: card.get("entity_name") or "",
}
