import os
import logging
import random
from datetime import datetime

import pymysql

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")

logger = logging.getLogger(__name__)


def get_db_connection():
    return pymysql.connect(
        host=MYSQL_DATABASE,
        user=MYSQL_USER,
        passwd=MYSQL_PSWD,
        db=MYSQL_DB,
    )


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
        if result:
            return {
                "id": result["id"],
                "name": result["name"],
                "sarcasm": float(result["sarcasm"]),
                "formality": float(result["formality"]),
                "warmth": float(result["warmth"]),
                "patience": float(result["patience"]),
                "linguistic_style": result["linguistic_style"] or "",
                "forbidden_words": result["forbidden_words"] or "",
                "verbal_tics": result["verbal_tics"] or "",
            }
        return get_default_personality()
    except pymysql.Error as e:
        logger.error(f"Database error getting personality: {e}")
        db.rollback()
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
            "WHERE type = 'current'",
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
        if result:
            return {
                "repeat_count": result["repeat_count"],
                "hour": result["hour"],
                "weather": result["weather"] or "clear",
                "mood": result["mood"],
                "last_error_count": result["last_error_count"],
                "llm_calls_today": result["llm_calls_today"],
                "last_text": result["last_text"] or "",
                "last_spoke_time": result["last_spoke_time"],
            }
        return get_default_context()
    except pymysql.Error as e:
        logger.error(f"Database error getting context: {e}")
        db.rollback()
        return get_default_context()
    finally:
        db.close()


def get_default_context():
    return {
        "repeat_count": 0,
        "hour": datetime.now().hour,
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
            set_clause = "repeat_count = GREATEST(0, repeat_count + %s), "
        else:
            set_clause = ""

        cursor.execute(
            f"UPDATE context SET {set_clause}"
            f"last_text = %s, last_spoke_time = NOW() WHERE environment_id = %s",
            (
                (repeat_increment, text[:512], env_id)
                if repeat_increment != 0
                else (text[:512], env_id)
            ),
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


def get_blended_personality(env_id=None):
    personality = get_personality_by_environment(env_id)
    context = get_context_by_environment(env_id)

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


def build_llm_system_prompt(personality):
    blended = personality.get("blended", {})
    linguistic_style = personality.get("linguistic_style", "default assistant")

    forbidden = personality.get("forbidden_words", "")
    tics = personality.get("verbal_tics", "")

    tics_instruction = f"Use these verbal tics occasionally: {tics}" if tics else ""
    forbidden_instruction = f"Never use these words: {forbidden}" if forbidden else ""

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

    return f"""You are ALFR3D, a home assistant.

Current Personality State:
- Style: {linguistic_style}
- Sarcasm: {blended.get("sarcasm", 0.5):.1f}/1.0
- Formality: {blended.get("formality", 0.5):.1f}/1.0
- Warmth: {blended.get("warmth", 0.5):.1f}/1.0
- Patience: {blended.get("patience", 1.0):.1f}/1.0
- Mood: {personality.get("mood", "neutral")}

Voice Constraints:
{tics_instruction}
{forbidden_instruction}

Instructions:
- Respond to the user's request
- Keep it under 20 words for TTS efficiency
- Stay in character based on the personality traits above
{formality_instruction}
{warmth_instruction}
{sarcasm_instruction}

User request: """


def select_quip_by_traits(quips, traits):
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
        random.shuffle(results)
        return [{"type": r["type"], "quips": r["quips"]} for r in results]
    except pymysql.Error as e:
        logger.error(f"Database error getting quips: {e}")
        db.rollback()
        return []
    finally:
        db.close()
