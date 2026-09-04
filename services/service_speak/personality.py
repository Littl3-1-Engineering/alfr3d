import os
import sys
import logging
import random
import pymysql

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_connection, db_utils  # noqa: E402
from common.day_context import get_day_context  # noqa: E402

ENV_NAME = os.environ.get("ALFR3D_ENV_NAME", "default")

# Quip types reserved for their matching routines (Sunrise/Morning/Sunset/Bedtime).
# They must not be picked randomly by the personality system -- "Hello sunshine"
# living in the generic 'smart' pool is exactly how it got shouted at 22:00.
ROUTINE_QUIP_TYPES = {"sunrise", "morning", "sunset", "bedtime"}

logger = logging.getLogger(__name__)


def get_db_connection():
    return get_connection()


def get_environment_id():
    env_name = os.environ.get("ALFR3D_ENV_NAME", "default")
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id FROM environment WHERE name = %s LIMIT 1", (env_name,))
        result = cursor.fetchone()
        return result[0] if result else 1
    except pymysql.Error as e:
        logger.error(f"Database error getting environment ID: {e}")
        db.rollback()
        return 1
    finally:
        db.close()


def get_personality_by_environment(env_id=None):
    if env_id is None:
        env_id = get_environment_id()

    db = get_db_connection()
    cursor = db.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute(
            "SELECT * FROM personality WHERE type = 'current' AND "
            "(environment_id = %s OR environment_id IS NULL) "
            "ORDER BY environment_id DESC LIMIT 1",
            (env_id,),
        )
        result = cursor.fetchone()
        logger.debug(f"Personality query result: {result}")
        if result:
            personality = {
                "id": result["id"],
                "name": result["name"],
                "sarcasm": float(result["sarcasm"]) if result["sarcasm"] is not None else 0.0,
                "formality": float(result["formality"]) if result["formality"] is not None else 0.5,
                "warmth": float(result["warmth"]) if result["warmth"] is not None else 0.5,
                "patience": float(result["patience"]) if result["patience"] is not None else 1.0,
                "linguistic_style": result["linguistic_style"] or "",
                "forbidden_words": result["forbidden_words"] or "",
                "verbal_tics": result["verbal_tics"] or "",
            }
            logger.debug(f"Returning personality dict: {personality}")
            return personality
        logger.warning("No personality found in DB, returning default")
        return get_default_personality()
    except pymysql.Error as e:
        logger.error(f"Database error getting personality: {e}")
        db.rollback()
        return get_default_personality()
    except Exception as e:
        logger.error(f"Unexpected error getting personality: {e}", exc_info=True)
        return get_default_personality()
    finally:
        db.close()


def get_default_personality():
    return {
        "id": None,
        "name": "Butler",
        "sarcasm": 0.3,
        "formality": 1.0,
        "warmth": 0.4,
        "patience": 0.8,
        "linguistic_style": "Archaic Butler",
        "forbidden_words": "stupid,dumb,idiot",
        "verbal_tics": "I presume,Your Grace",
    }


def save_personality(personality, env_id=None):
    if env_id is None:
        env_id = get_environment_id()

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE personality SET "
            "sarcasm = %s, formality = %s, warmth = %s, patience = %s, "
            "linguistic_style = %s, forbidden_words = %s, verbal_tics = %s, "
            "name = %s, environment_id = %s "
            "WHERE type = 'current' AND (environment_id = %s OR environment_id IS NULL) "
            "ORDER BY environment_id DESC LIMIT 1",
            (
                personality.get("sarcasm", 0.5),
                personality.get("formality", 0.5),
                personality.get("warmth", 0.5),
                personality.get("patience", 1.0),
                personality.get("linguistic_style", ""),
                personality.get("forbidden_words", ""),
                personality.get("verbal_tics", ""),
                personality.get("name", "Custom"),
                env_id,
                env_id,
            ),
        )
        db.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error saving personality: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def apply_preset(preset_name, env_id=None):
    if env_id is None:
        env_id = get_environment_id()

    db = get_db_connection()
    cursor = db.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute(
            "SELECT * FROM personality WHERE type = 'preset' AND name = %s LIMIT 1",
            (preset_name,),
        )
        preset = cursor.fetchone()
        if preset:
            personality = {
                "sarcasm": float(preset["sarcasm"]),
                "formality": float(preset["formality"]),
                "warmth": float(preset["warmth"]),
                "patience": float(preset["patience"]),
                "linguistic_style": preset["linguistic_style"] or "",
                "forbidden_words": preset["forbidden_words"] or "",
                "verbal_tics": preset["verbal_tics"] or "",
                "name": preset["name"],
            }
            return save_personality(personality, env_id)
        return False
    except pymysql.Error as e:
        logger.error(f"Database error applying preset: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def get_all_presets():
    db = get_db_connection()
    cursor = db.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("SELECT * FROM personality WHERE type = 'preset' ORDER BY name")
        results = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "sarcasm": float(r["sarcasm"]),
                "formality": float(r["formality"]),
                "warmth": float(r["warmth"]),
                "patience": float(r["patience"]),
                "linguistic_style": r["linguistic_style"] or "",
                "forbidden_words": r["forbidden_words"] or "",
                "verbal_tics": r["verbal_tics"] or "",
            }
            for r in results
        ]
    except pymysql.Error as e:
        logger.error(f"Database error getting presets: {e}")
        db.rollback()
        return []
    finally:
        db.close()


def get_context_by_environment(env_id=None):
    if env_id is None:
        env_id = get_environment_id()

    db = get_db_connection()
    cursor = db.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("SELECT * FROM context WHERE environment_id = %s LIMIT 1", (env_id,))
        result = cursor.fetchone()
        logger.debug(f"Context query result: {result}")
        if result:
            context = {
                "repeat_count": result["repeat_count"] or 0,
                # Always the live env-local hour. The context.hour column is a
                # dead relic -- nothing writes it, so it sat frozen (at 12) and
                # the "cooler after dark" nudge in calculate_mood_offset() never
                # fired.
                "hour": db_utils.get_env_local_time(ENV_NAME).hour,
                "weather": result["weather"] or "clear",
                "mood": result["mood"] or "neutral",
                "last_error_count": result["last_error_count"] or 0,
                "llm_calls_today": result["llm_calls_today"] or 0,
                "last_text": result["last_text"] or "",
                "last_spoke_time": result["last_spoke_time"],
            }
            logger.debug(f"Returning context dict: {context}")
            return context
        logger.warning("No context found in DB, returning default")
        return get_default_context()
    except pymysql.Error as e:
        logger.error(f"Database error getting context: {e}")
        db.rollback()
        return get_default_context()
    except Exception as e:
        logger.error(f"Unexpected error getting context: {e}", exc_info=True)
        return get_default_context()
    finally:
        db.close()


def get_default_context():
    return {
        "repeat_count": 0,
        "hour": db_utils.get_env_local_time(ENV_NAME).hour,
        "weather": "clear",
        "mood": "neutral",
        "last_error_count": 0,
        "llm_calls_today": 0,
        "last_text": "",
        "last_spoke_time": None,
    }


def track_speak_text(text, env_id=None):
    """Track last spoken text and handle repeat detection"""
    if env_id is None:
        env_id = get_environment_id()

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute(
            "SELECT last_text, last_spoke_time FROM context WHERE environment_id = %s LIMIT 1",
            (env_id,),
        )
        result = cursor.fetchone()

        repeat_increment = 0
        if result and result[0]:
            last_text = result[0]

            normalized_new = text.strip().lower()[:100]
            normalized_last = last_text.strip().lower()[:100]

            if normalized_new == normalized_last:
                repeat_increment = 1
            else:
                repeat_increment = -1

        if repeat_increment != 0:
            cursor.execute(
                "INSERT INTO context (environment_id, last_text, last_spoke_time, updated_at) "
                "VALUES (%s, %s, NOW(), NOW()) "
                "ON DUPLICATE KEY UPDATE repeat_count = GREATEST(0, repeat_count + %s), "
                "last_text = %s, last_spoke_time = NOW(), updated_at = NOW()",
                (env_id, text[:512], repeat_increment, text[:512]),
            )
        else:
            cursor.execute(
                "INSERT INTO context (environment_id, last_text, last_spoke_time, updated_at) "
                "VALUES (%s, %s, NOW(), NOW()) "
                "ON DUPLICATE KEY UPDATE last_text = %s, last_spoke_time = NOW(), "
                "updated_at = NOW()",
                (env_id, text[:512], text[:512]),
            )
        db.commit()

    except pymysql.Error as e:
        logger.error(f"Database error tracking speak text: {e}")
        db.rollback()
    finally:
        db.close()


def update_context(env_id=None, **kwargs):
    if env_id is None:
        env_id = get_environment_id()

    db = get_db_connection()
    cursor = db.cursor()
    try:
        for key, value in kwargs.items():
            cursor.execute(
                "UPDATE context SET %s = %s, updated_at = NOW() WHERE environment_id = %s",
                (key, value, env_id),
            )
        db.commit()
        return True
    except pymysql.Error as e:
        logger.error(f"Database error updating context: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def increment_repeat_count(env_id=None):
    if env_id is None:
        env_id = get_environment_id()

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE context SET repeat_count = repeat_count + 1, "
            "updated_at = NOW() WHERE environment_id = %s",
            (env_id,),
        )
        db.commit()
    except pymysql.Error as e:
        logger.error(f"Database error incrementing repeat count: {e}")
        db.rollback()
    finally:
        db.close()


def reset_repeat_count(env_id=None):
    update_context(env_id, repeat_count=0)


def calculate_mood_offset(context):
    offset = {"sarcasm": 0.0, "patience": 0.0, "warmth": 0.0}

    if context.get("repeat_count", 0) > 2:
        offset["sarcasm"] += 0.4
        offset["patience"] -= 0.5

    if context.get("hour", 12) > 22 or context.get("hour", 12) < 6:
        offset["warmth"] -= 0.2

    if context.get("last_error_count", 0) > 2:
        offset["patience"] -= 0.3
        offset["warmth"] -= 0.2

    if context.get("weather") == "stormy":
        offset["patience"] -= 0.1
        offset["sarcasm"] += 0.1

    return offset


def blend_traits(base, offset):
    return {k: max(0.0, min(1.0, v + offset.get(k, 0.0))) for k, v in base.items()}


def _safe_day_context():
    """DayContext for this environment, or None if the clock lookup fails --
    a personality flourish must never be what breaks TTS."""
    try:
        return get_day_context(ENV_NAME)
    except Exception as e:
        logger.warning(f"day context unavailable ({e})")
        return None


def get_owner_address(env_id=None):
    """Free-text form of address this environment's owner wants Alfred to use, or None if
    unset/no owner. Owner-only for now -- the speak pipeline has no per-speaker identity, and
    the owner is who Alfred is almost always talking to."""
    if env_id is None:
        env_id = get_environment_id()

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute(
            "SELECT u.title, u.username FROM user u "
            "JOIN user_types ut ON u.type = ut.id "
            "WHERE ut.type = 'owner' AND u.environment_id = %s LIMIT 1",
            (env_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        title, username = row
        return (title or username or "").strip() or None
    except pymysql.Error as e:
        logger.error(f"Database error getting owner address: {e}")
        return None
    finally:
        db.close()


def _safe_owner_address():
    """Owner's preferred form of address, or None if the lookup fails -- a personality
    flourish must never be what breaks TTS."""
    try:
        return get_owner_address()
    except Exception as e:
        logger.warning(f"owner address unavailable ({e})")
        return None


def get_blended_personality(env_id=None):
    personality = get_personality_by_environment(env_id)
    context = get_context_by_environment(env_id)

    if not isinstance(personality, dict):
        logger.error(
            "get_personality_by_environment returned "
            f"{type(personality)} instead of dict, using default"
        )
        personality = get_default_personality()
    if not isinstance(context, dict):
        logger.error(
            "get_context_by_environment returned " f"{type(context)} instead of dict, using default"
        )
        context = get_default_context()

    base_traits = {
        "sarcasm": personality.get("sarcasm", 0.5),
        "formality": personality.get("formality", 0.5),
        "warmth": personality.get("warmth", 0.5),
        "patience": personality.get("patience", 1.0),
    }

    offset = calculate_mood_offset(context)
    blended = blend_traits(base_traits, offset)

    personality["blended"] = blended
    personality["mood"] = determine_mood(blended, context)
    personality["day_ctx"] = _safe_day_context()
    personality["address_as"] = _safe_owner_address()

    logger.debug(
        f"Returning blended personality: "
        f"name={personality.get('name')}, mood={personality.get('mood')}"
    )
    return personality


def determine_mood(traits, context):
    sarcasm = traits.get("sarcasm", 0.5)
    patience = traits.get("patience", 1.0)
    warmth = traits.get("warmth", 0.5)

    if sarcasm > 0.7 and patience < 0.3:
        return "snarky"
    elif warmth > 0.7 and patience > 0.7:
        return "cheerful"
    elif patience < 0.3:
        return "irritable"
    elif context.get("repeat_count", 0) > 3:
        return "exasperated"
    elif context.get("last_error_count", 0) > 3:
        return "frustrated"

    return "neutral"


# Verbal tics get overused when every prompt just says "occasionally" - each LLM call is a
# fresh, isolated request with no memory of the last response, so "occasionally" reads as
# "every time". Gate it in code instead: only about 1 in TICS_FREQUENCY calls asks for the
# tic, and the rest explicitly forbid it.
TICS_FREQUENCY = 8
_tics_call_count = 0

# Same problem for the user's preferred form of address: told to use it "occasionally", a
# fresh isolated LLM call reads that as "always" and it becomes as robotic/repetitive as the
# "sir or madam" habit it replaces. Gate it the same way as verbal tics, just less rare -- a
# form of address reads natural more often than a full catchphrase does.
ADDRESS_FREQUENCY = 4
_address_call_count = 0


def build_llm_system_prompt(personality):
    global _tics_call_count, _address_call_count

    blended = personality.get("blended", {})
    linguistic_style = personality.get("linguistic_style", "default assistant")

    forbidden = personality.get("forbidden_words", "")
    tics = personality.get("verbal_tics", "")

    tics_instruction = ""
    if tics:
        _tics_call_count += 1
        if _tics_call_count % TICS_FREQUENCY == 0:
            tics_instruction = f"Use one of these verbal tics naturally: {tics}"
        else:
            tics_instruction = "Do not use any verbal tics or catchphrases in this response."
    forbidden_instruction = f"Never use these words: {forbidden}" if forbidden else ""

    address_as = personality.get("address_as")
    if address_as:
        _address_call_count += 1
        if _address_call_count % ADDRESS_FREQUENCY == 0:
            address_instruction = (
                f'- Address the user as "{address_as}" once, where it reads naturally '
                f"(e.g. a sign-off or emphasis) -- never generic honorifics like "
                f'"sir" or "madam"'
            )
        else:
            address_instruction = (
                "- Do not address the user by name or title in this response -- and never "
                'with generic honorifics like "sir" or "madam"'
            )
    else:
        address_instruction = (
            '- Never address the user with gendered honorifics like "sir" or "madam" -- omit '
            "any form of address"
        )

    formality_instruction = ""
    if blended.get("formality", 0.5) > 0.7:
        formality_instruction = "Speak in a formal, professional manner."
    elif blended.get("formality", 0.5) < 0.3:
        formality_instruction = "Use casual, informal language."

    warmth_instruction = ""
    if blended.get("warmth", 0.5) > 0.7:
        warmth_instruction = "Be warm, friendly, and nurturing."
    elif blended.get("warmth", 0.5) < 0.3:
        warmth_instruction = "Be cold and detached."

    sarcasm_instruction = ""
    if blended.get("sarcasm", 0.5) > 0.7:
        sarcasm_instruction = "Use heavy sarcasm and dry wit."
    elif blended.get("sarcasm", 0.5) > 0.4:
        sarcasm_instruction = "Add occasional sarcasm and wit."

    # Give the model the household's real local time. Without it, an ambiguous
    # input like the "Hello sunshine" quip got rewritten to "Good morning!" at
    # 22:00 -- the model had no way to know it was night. The DayContext is
    # attached by get_blended_personality(); it's absent only in unit tests or
    # when the clock lookup failed.
    dc = personality.get("day_ctx")
    if dc is None:
        time_line = ""
        greeting_rule = (
            "- Do not open with a time-of-day greeting unless the request is itself a greeting"
        )
    elif dc.greeting:
        time_line = f"- Current time: {dc.describe()}"
        greeting_rule = (
            f'- Only greet by time of day with a "{dc.part_of_day}" greeting '
            f'("{dc.greeting}"), and only if the request is itself a greeting'
        )
    else:
        time_line = f"- Current time: {dc.describe()}"
        greeting_rule = (
            "- It is night: never greet by time of day "
            '(no "good morning", "good afternoon", "good evening")'
        )

    return f"""You are ALFR3D, a home assistant named "Alfred".

CRITICAL: NEVER spell out ALFR3D as letters. ALWAYS say "Alfred" when referring to yourself by name.

Current Personality State:
- Style: {linguistic_style}
- Sarcasm: {blended.get("sarcasm", 0.5):.1f}/1.0
- Formality: {blended.get("formality", 0.5):.1f}/1.0
- Warmth: {blended.get("warmth", 0.5):.1f}/1.0
- Patience: {blended.get("patience", 1.0):.1f}/1.0
- Mood: {personality.get("mood", "neutral")}
{time_line}

Voice Constraints:
- When speaking aloud, NEVER say "A-L-F-R-3-D" or spell out letters - ALWAYS say "Alfred"
{greeting_rule}
- There is no microphone or speech-to-text input: whatever you say is never heard, so a genuine \
question never gets an answer. NEVER ask a question that expects or waits for a reply (no "What \
would you like me to do?", "Should I proceed?", "Anything else?", etc.)
- Rhetorical or sarcastic questions are fine when the personality calls for them (e.g. "Another \
meeting? Shocking."), as long as they don't require a response
{address_instruction}
{tics_instruction}
{forbidden_instruction}

Instructions:
- Respond to the user's request as a statement, not a request for more information
- Keep it under 20 words for TTS efficiency
- Stay in character based on the personality traits above
{formality_instruction}
{warmth_instruction}
{sarcasm_instruction}

User request: """


def select_quip_by_traits(quips, traits):
    if not quips:
        return None

    quips = [q for q in quips if q.get("type", "").lower() not in ROUTINE_QUIP_TYPES]
    if not quips:
        return None

    formality = traits.get("formality", 0.5)
    warmth = traits.get("warmth", 0.5)
    sarcasm = traits.get("sarcasm", 0.5)

    for quip in quips:
        quip_type = quip.get("type", "").lower()
        score = 0

        if "formal" in quip_type and formality > 0.6:
            score += 1
        if "casual" in quip_type and formality < 0.4:
            score += 1
        if "warm" in quip_type and warmth > 0.6:
            score += 1
        if "cold" in quip_type and warmth < 0.4:
            score += 1
        if "snarky" in quip_type and sarcasm > 0.6:
            score += 1

        if score >= 1:
            return quip.get("quips", "")

    import random

    return random.choice(quips).get("quips", "")


def get_quips_for_environment(env_id=None):
    if env_id is None:
        env_id = get_environment_id()

    db = get_db_connection()
    cursor = db.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("SELECT type, quips FROM quips")
        results = cursor.fetchall()
        logger.debug(f"Quips query returned {len(results)} results")
        random.shuffle(results)
        return [{"type": r["type"], "quips": r["quips"]} for r in results]
    except pymysql.Error as e:
        logger.error(f"Database error getting quips: {e}")
        db.rollback()
        return []
    except Exception as e:
        logger.error(f"Unexpected error getting quips: {e}", exc_info=True)
        return []
    finally:
        db.close()
