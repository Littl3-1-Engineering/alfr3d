"""Card suppression (SA-1): the cooldown and repetition checks `decide_displays` applies.

Step 2 of the engine.py split (todo/sa/todo_parallel_capture_track.md, item 4): the constants and
`_card_suppression_reason` moved verbatim out of engine.py. `SAEngine` inherits the mixin, so
`engine._card_suppression_reason` and `self._card_suppression_reason` resolve as before; engine
re-exports the constants. `pymysql` is the shared module object, so tests that patch
`engine.pymysql.connect` still reach this code.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import pymysql

logger = logging.getLogger("SALog")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")

# The explicit answers that start a card's cooldown (SA-1); see _card_suppression_reason.
CARD_FEEDBACK_ACTIONS = ("dismissed", "acked", "not_useful")

# decide_displays()'s suppression pass looks at up to this many of a card identity's most recent
# card_interactions rows -- must cover both the cooldown check (just the latest row) and the
# repetition-damping run-length count below.
CARD_SUPPRESSION_HISTORY_LIMIT = 10

# A card identity whose most recent interaction is "dismissed" is suppressed for this many
# minutes before it's allowed to show again -- a conservative starting point, no real
# interaction data yet to tune it against (same caveat as every other threshold in this file).
# Per-mode override via CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE.
CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES = 60
CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE = {
    # Continuous-stay guest decay: the underlying signal (days-of-stay) only changes once a
    # day, so re-showing this more than daily is pure noise on a signal that hasn't moved.
    "guest_overstay_advisory": 1440,
}

# "Not useful" is the one clearly negative feedback action, so it silences the card for far longer
# than a neutral swipe-away or a checkmark: a day by default. Product default, not yet tuned against
# real feedback (there is none yet); per-rule override in the _BY_RULE dict below.
CARD_SUPPRESSION_NOT_USEFUL_COOLDOWN_MINUTES = 1440
CARD_SUPPRESSION_NOT_USEFUL_COOLDOWN_MINUTES_BY_RULE = {}

# A card identity shown this many cycles in a row with no interaction at all (no dismiss, no
# tap) gets suppressed until its underlying state changes (i.e. until something -- a different
# device, a content change on a singleton rule -- gives it a new identity, or a real interaction
# resets the run). Per-mode override via CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE.
CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES = 20
CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE = {}


class SuppressionMixin:
    def _card_suppression_reason(self, rule_id, subject_key):
        """Return a short reason string to suppress this (rule_id, subject_key) card
        identity, or None to show it as normal. Reads card_interactions only -- the
        daemon never writes to it, only consumers report shown/tapped/dismissed/expired
        (see routes/context.py's POST /api/context/card-interaction); a published card
        that never made it past a client's own display cap was never actually "shown",
        and the daemon has no way to know that, so it must not assume otherwise."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            # The cooldown comes from the latest feedback or tap, found by its own query. A later
            # `shown` (a surface that has not got the news yet, or just a refresh) must not cancel
            # it, and a burst of `shown` rows from two surfaces must not push the feedback row out
            # of the history window below. Only a later tap, real re-engagement, ends it early.
            cursor.execute(
                "SELECT action, occurred_at FROM card_interactions "
                "WHERE rule_id = %s AND subject_key = %s "
                "AND action IN ('dismissed', 'acked', 'not_useful', 'tapped') "
                "ORDER BY occurred_at DESC, id DESC LIMIT 1",
                (rule_id, subject_key),
            )
            feedback = cursor.fetchall()
            if feedback and feedback[0][0] in CARD_FEEDBACK_ACTIONS:
                feedback_action, feedback_at = feedback[0]
                if feedback_action == "not_useful":
                    cooldown = CARD_SUPPRESSION_NOT_USEFUL_COOLDOWN_MINUTES_BY_RULE.get(
                        rule_id, CARD_SUPPRESSION_NOT_USEFUL_COOLDOWN_MINUTES
                    )
                else:
                    cooldown = CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE.get(
                        rule_id, CARD_SUPPRESSION_DEFAULT_COOLDOWN_MINUTES
                    )
                since = datetime.now(timezone.utc) - feedback_at.replace(tzinfo=timezone.utc)
                if since < timedelta(minutes=cooldown):
                    return "cooldown"

            cursor.execute(
                "SELECT action, occurred_at FROM card_interactions "
                "WHERE rule_id = %s AND subject_key = %s AND action <> 'impression' "
                "ORDER BY occurred_at DESC LIMIT %s",
                (rule_id, subject_key, CARD_SUPPRESSION_HISTORY_LIMIT),
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            run_length = 0
            for action, _ in rows:
                if action != "shown":
                    break
                run_length += 1
            threshold = CARD_SUPPRESSION_REPETITION_CYCLES_BY_RULE.get(
                rule_id, CARD_SUPPRESSION_DEFAULT_REPETITION_CYCLES
            )
            if run_length >= threshold:
                return "repetition"
            return None
        except pymysql.Error as e:
            logger.error(f"Card suppression check error: {e}")
            return None
        finally:
            if db:
                db.close()
