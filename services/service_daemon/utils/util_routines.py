#!/usr/bin/python

"""
This is a utility for Routines for Alfr3d:
"""
# Copyright (c) 2010-2020 LiTtl3.1 Industries (LiTtl3.1).
# All rights reserved.
# This source code and any compilation or derivative thereof is the
# proprietary information of LiTtl3.1 Industries and is
# confidential in nature.
# Use of this source code is subject to the terms of the applicable
# LiTtl3.1 Industries license agreement.
#
# Under no circumstances is this component (or portion thereof) to be in any
# way affected or brought under the terms of any Open Source License without
# the prior express written permission of LiTtl3.1 Industries.
#
# For the purpose of this clause, the term Open Source Software/Component
# includes:
#
# (i) any software/component that requires as a condition of use, modification
#     and/or distribution of such software/component, that such software/
#     component:
#     a. be disclosed or distributed in source code form;
#     b. be licensed for the purpose of making derivative works; and/or
# (ii) any software/component that contains, is derived in any manner (in whole
#      or in part) from, or statically or dynamically links against any
#      software/component specified under (i).

import os
import sys
import logging
import orjson
import pymysql as MySQLdb
from datetime import timedelta
from random import randint

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../common"))
from common import get_producer, db_utils, ha_utils, spotify_utils, audio_cast  # noqa: E402

# set up logging
logger = logging.getLogger("RoutinesLog")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

# get main DB credentials
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE") or "mysql"
MYSQL_DB = os.environ.get("MYSQL_NAME") or "alfr3d_db"
MYSQL_USER = os.environ.get("MYSQL_USER") or "user"
MYSQL_PSWD = os.environ.get("MYSQL_PSWD") or "password"
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")

# Routine names to quip types. These quips are only spoken by their matching routines.
ROUTINE_QUIP_TYPES = {"Sunrise": "sunrise", "Sunset": "sunset", "Bedtime": "bedtime"}


def _get_routine_quip(cursor, quip_type):
    """Fetch a random quip of the given routine type using the routine's DB cursor."""
    cursor.execute("SELECT MAX(id) FROM quips WHERE type = %s", (quip_type,))
    max_row = cursor.fetchone()
    if not max_row or not max_row[0]:
        return None
    random_id = randint(1, max_row[0])
    cursor.execute(
        "SELECT quips FROM quips WHERE id >= %s AND type = %s LIMIT 1",
        (random_id, quip_type),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def execute_actions(actions_json):
    """Execute actions from JSON array via Kafka."""
    if not actions_json:
        return 0

    try:
        actions = orjson.loads(actions_json) if isinstance(actions_json, str) else actions_json
    except (orjson.JSONDecodeError, TypeError):
        logger.error("Invalid actions JSON")
        return 0

    try:
        producer = get_producer()
    except Exception:
        logger.error("Kafka producer not available")
        return 0

    executed = 0
    for action in actions:
        action_type = action.get("type")
        action_params = action.get("params", {})

        try:
            if action_type == "speak":
                message = {"text": action_params.get("text", ""), "engine": "Coqui"}
                producer.send("speak", message)
                producer.flush()
                logger.info(f"Executed speak action: {action_params.get('text', '')[:50]}")

            elif action_type == "device":
                message = {
                    "device_id": action_params.get("device_id"),
                    "action": action_params.get("action", "on"),
                }
                producer.send("device", message)
                producer.flush()
                logger.info(f"Executed device action: {action_params.get('device_id')}")

            elif action_type == "email":
                message = {
                    "type": "email",
                    "to": action_params.get("to", ""),
                    "subject": action_params.get("subject", ""),
                    "body": action_params.get("body", ""),
                }
                producer.send("user", message)
                producer.flush()
                logger.info(f"Executed email action to: {action_params.get('to', '')}")

            elif action_type == "scene":
                message = {"scene": action_params.get("scene_id", "")}
                producer.send("device", message)
                producer.flush()
                logger.info(f"Executed scene action: {action_params.get('scene_id', '')}")

            elif action_type in ("thermostat_set", "lock", "unlock", "cover_open", "cover_close"):
                success, message = control_iot_device(
                    action_params.get("device_id"), action_type, action_params
                )
                if success:
                    logger.info(f"Executed {action_type} action")
                else:
                    logger.error(f"Failed to execute {action_type} action: {message}")

            elif action_type in ("music", "spotify"):
                ok, message = _execute_music_action(action_params)
                if ok:
                    logger.info(f"Executed music action: {message}")
                else:
                    logger.error(f"Failed to execute music action: {message}")

            executed += 1
        except Exception as e:
            logger.error(f"Failed to execute action {action_type}: {str(e)}")

    return executed


def _execute_music_action(params):
    """Execute a music/Spotify action (play, pause, next, previous, search+play, cast)."""
    action = (params.get("action") or "play").lower()
    query = params.get("query") or params.get("text") or ""
    try:
        if action == "pause":
            return spotify_utils.pause()
        if action == "next":
            return spotify_utils.next_track()
        if action == "previous":
            return spotify_utils.previous_track()
        if action == "volume":
            percent = params.get("volume_percent", 50)
            return spotify_utils.set_volume(percent)
        if action == "cast":
            entity_id = params.get("entity_id")
            group_name = params.get("group_name")
            volume = params.get("volume_percent")
            if entity_id:
                ok, err = audio_cast.cast_to_speaker(entity_id, volume=volume)
            elif group_name:
                ok, err = audio_cast.cast_to_group(group_name, volume=volume)
            else:
                return False, "entity_id or group_name is required for cast"
            return ok, err or "Cast completed"
        if action == "stop_cast":
            return audio_cast.stop_cast()
        if query:
            data, err = spotify_utils.search(query, "track", 1)
            if err:
                return False, f"Search failed: {err}"
            tracks = (data.get("tracks") or {}).get("items") or []
            if not tracks:
                return False, f"No results for '{query}'"
            uri = tracks[0].get("uri")
            ok, err = spotify_utils.play(context_uri=uri)
            if not ok:
                return False, err or "Play failed"
            return True, f"Playing '{tracks[0].get('name')}'"
        return spotify_utils.play()
    except Exception as e:
        return False, str(e)


def control_iot_device(device_id, action_type, params):
    """Control an IoT device (smarthome_devices) for routine actions."""
    if not device_id:
        return False, "No device_id provided"
    try:
        db = MySQLdb.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute(
            "SELECT source, ha_entity_id FROM smarthome_devices WHERE id = %s",
            (device_id,),
        )
        row = cursor.fetchone()
        db.close()
    except Exception as e:
        logger.error(f"Failed to look up IoT device {device_id}: {str(e)}")
        return False, str(e)

    if not row:
        return False, "IoT device not found"
    source, ha_entity_id = row[0], row[1]

    if source != "homeassistant" or not ha_entity_id:
        return False, "Unsupported source or unlinked entity"

    if action_type == "thermostat_set":
        temperature = params.get("temperature")
        success, message = ha_utils.ha_control_device(
            ha_entity_id, "set_temperature", {"temperature": temperature}
        )
        if not success:
            return success, message
        mode = params.get("mode")
        if mode:
            return ha_utils.ha_control_device(ha_entity_id, "set_mode", {"mode": mode})
        return success, message
    elif action_type == "lock":
        return ha_utils.ha_control_device(ha_entity_id, "lock", None)
    elif action_type == "unlock":
        return ha_utils.ha_control_device(ha_entity_id, "unlock", None)
    elif action_type == "cover_open":
        return ha_utils.ha_control_device(ha_entity_id, "set_cover_position", {"position": 100})
    elif action_type == "cover_close":
        return ha_utils.ha_control_device(ha_entity_id, "set_cover_position", {"position": 0})
    return False, "Unknown action type"


# In-memory state caches for event trigger detection
_PREV_USER_STATES = {}
_PREV_DEVICE_STATES = {}
_SUN_FIRED = {}


def _fetch_user_states(cursor, env_id):
    """Return {user_id: bool} where bool is True when user is online."""
    cursor.execute(
        "SELECT id, state FROM user WHERE environment_id = %s", (env_id,)
    )
    return {row[0]: (row[1] == 2) for row in cursor.fetchall()}


def _fetch_device_states(cursor, env_id):
    """Return {device_id: bool} where bool is True when device is online."""
    cursor.execute(
        "SELECT id, state FROM device WHERE environment_id = %s", (env_id,)
    )
    return {row[0]: (row[1] == 2) for row in cursor.fetchall()}


def _eval_sun_trigger(routine_id, kind, sunrise, sunset, cur_time, today):
    """Fire once per day when the current time passes the sun event."""
    if kind == "sunrise":
        sun_time = sunrise
    else:
        sun_time = sunset
    if not sun_time:
        return False
    key = (routine_id, kind)
    if _SUN_FIRED.get(key) == today:
        return False
    sun_dt = cur_time.replace(
        hour=sun_time.hour, minute=sun_time.minute, second=0, microsecond=0
    )
    if sun_dt <= cur_time <= sun_dt + timedelta(minutes=15):
        _SUN_FIRED[key] = today
        return True
    return False


def _eval_event_trigger(kind, params, user_states, device_states, sunrise, sunset, cur_time, today, routine_id):
    """Evaluate a single non-time trigger; returns (fired, all_handled)."""
    if kind in ("sunrise", "sunset"):
        return _eval_sun_trigger(routine_id, kind, sunrise, sunset, cur_time, today), True
    if kind in ("person_arrives", "person_leaves"):
        user_id = params.get("user_id")
        if not user_id:
            return False, True
        prev_state = _PREV_USER_STATES.get(user_id)
        cur_state = user_states.get(user_id, False)
        fired = False
        if prev_state is False and cur_state is True and kind == "person_arrives":
            fired = True
        elif prev_state is True and cur_state is False and kind == "person_leaves":
            fired = True
        _PREV_USER_STATES[user_id] = cur_state
        return fired, True
    if kind in ("device_turns_on", "device_turns_off"):
        device_id = params.get("device_id")
        if not device_id:
            return False, True
        prev_state = _PREV_DEVICE_STATES.get(device_id)
        cur_state = device_states.get(device_id, False)
        fired = False
        if prev_state is False and cur_state is True and kind == "device_turns_on":
            fired = True
        elif prev_state is True and cur_state is False and kind == "device_turns_off":
            fired = True
        _PREV_DEVICE_STATES[device_id] = cur_state
        return fired, True
    return False, False


def _eval_conditions(conditions, ctx):
    """All conditions must evaluate True."""
    if not conditions:
        return True
    for cond in conditions:
        ctype = cond.get("type")
        params = cond.get("params", {})
        if ctype == "person_is_home":
            if not ctx["user_states"].get(params.get("user_id"), False):
                return False
        elif ctype == "person_is_away":
            if ctx["user_states"].get(params.get("user_id"), False):
                return False
        elif ctype == "anyone_home":
            if not any(ctx["user_states"].values()):
                return False
        elif ctype == "no_one_home":
            if any(ctx["user_states"].values()):
                return False
        elif ctype == "device_is_on":
            if not ctx["device_states"].get(params.get("device_id"), False):
                return False
        elif ctype == "device_is_off":
            if ctx["device_states"].get(params.get("device_id"), False):
                return False
        elif ctype == "temperature_above":
            if ctx["temperature"] is None or ctx["temperature"] <= params.get("value"):
                return False
        elif ctype == "temperature_below":
            if ctx["temperature"] is None or ctx["temperature"] >= params.get("value"):
                return False
        elif ctype == "mode":
            mode = params.get("mode")
            if mode == "day" and ctx["is_night"]:
                return False
            if mode == "night" and not ctx["is_night"]:
                return False
            if mode == "home" and not any(ctx["user_states"].values()):
                return False
            if mode == "away" and any(ctx["user_states"].values()):
                return False
    return True


def check_routines() -> bool:
    """
    Description:
            Check if it is time to execute any routines and take action
            if needed...
    """
    logger.info("Checking routines")

    if not ENV_NAME:
        logger.error("ALFR3D_ENV_NAME environment variable not set")
        return False

    # fetch available Routines
    try:
        db = MySQLdb.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
    except Exception as e:
        logger.error("Failed to connect to database")
        logger.error("Traceback: " + str(e))
        return False

    # get environment row for current environment (explicit columns keep indexes stable)
    cursor.execute(
        "SELECT id, latitude, longitude, city, state, country, IP, low, high, "
        "temperature, wind, wind_dir, description, sunrise, sunset, pressure, "
        "pressure_trend, humidity, manual_override, manual_location_override, "
        "subjective_feel, timezone FROM environment WHERE name = %s;",
        (ENV_NAME,),
    )
    data = cursor.fetchone()
    if not data:
        logger.error("Environment not found")
        db.close()
        return False
    env_id = data[0]
    env_sunrise = data[13]
    env_sunset = data[14]
    env_temperature = data[9]

    user_states = _fetch_user_states(cursor, env_id)
    device_states = _fetch_device_states(cursor, env_id)

    cur_time = db_utils.get_env_local_time(ENV_NAME)
    cur_weekday = cur_time.weekday()
    today = cur_time.strftime("%Y-%m-%d")
    is_night = not (env_sunrise and env_sunset and env_sunrise <= cur_time <= env_sunset)

    cursor.execute(
        "SELECT id, name, time, enabled, recurrence, actions, triggered, triggers, conditions "
        "FROM routines WHERE environment_id = %s and enabled = 1;",
        (env_id,),
    )
    routines = cursor.fetchall()

    for routine in routines:
        routine_id, routine_name, routine_time, _, recurrence, actions, triggered = routine[:7]
        triggers_json = routine[7] if len(routine) > 7 else None
        conditions_json = routine[8] if len(routine) > 8 else None

        try:
            triggers = (
                orjson.loads(triggers_json)
                if isinstance(triggers_json, str)
                else (triggers_json or [])
            )
        except (orjson.JSONDecodeError, TypeError):
            triggers = []

        try:
            conditions = (
                orjson.loads(conditions_json)
                if isinstance(conditions_json, str)
                else (conditions_json or [])
            )
        except (orjson.JSONDecodeError, TypeError):
            conditions = []

        logger.info(
            f"Checking {routine_name} routine with time {routine_time} and flag {triggered}"
        )

        # evaluate WHEN (triggers, OR-combined)
        should_trigger = False
        handled = False

        if routine_time is not None:
            handled = True
            trigger_time = cur_time.replace(
                hour=int(routine_time.seconds / 3600),
                minute=int((routine_time.seconds // 60) % 60),
            )
            if cur_time > trigger_time and not triggered:
                if recurrence == "once":
                    should_trigger = True
                elif recurrence == "daily":
                    should_trigger = True
                elif recurrence == "weekdays" and cur_weekday < 5:
                    should_trigger = True
                elif recurrence == "weekly":
                    should_trigger = True

        for trigger in triggers or []:
            fired, trig_handled = _eval_event_trigger(
                trigger.get("type"),
                trigger.get("params", {}),
                user_states,
                device_states,
                env_sunrise,
                env_sunset,
                cur_time,
                today,
                routine_id,
            )
            if trig_handled:
                handled = True
            if fired:
                should_trigger = True
                logger.info(f"{routine_name} event trigger fired: {trigger.get('type')}")

        if not handled:
            logger.warning(f"Routine {routine_name} has no valid triggers, skipping")
            continue

        # evaluate IF (conditions, all must pass)
        ctx = {
            "user_states": user_states,
            "device_states": device_states,
            "temperature": env_temperature,
            "is_night": is_night,
        }
        if not _eval_conditions(conditions, ctx):
            continue

        if should_trigger:
            logger.info(routine_name + " routine is being triggered")
            quip_type = ROUTINE_QUIP_TYPES.get(routine_name)
            if quip_type:
                quip = _get_routine_quip(cursor, quip_type)
                if quip:
                    producer = get_producer()
                    if producer:
                        producer.send(
                            "speak",
                            orjson.dumps({"text": quip}),
                        )
                        producer.flush()
                        logger.info(f"Spoke routine quip for {routine_name}: {quip[:50]}")
            if actions:
                executed = execute_actions(actions)
                logger.info(f"Executed {executed} actions for routine {routine_name}")
            try:
                cursor.execute(
                    "UPDATE routines SET triggered = 1, last_run = NOW() WHERE id = %s;",
                    (routine_id,),
                )
                db.commit()
            except Exception as e:
                logger.error("Failed to update the database")
                logger.error("Traceback: " + str(e))
                db.rollback()
                db.close()
                return False

    db.close()
    return True


def reset_routines() -> bool:
    """
    Description:
            refresh some things at midnight
    """
    logger.info("Resetting routine flags")

    if not ENV_NAME:
        logger.error("ALFR3D_ENV_NAME environment variable not set")
        return False

    try:
        db = MySQLdb.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
    except Exception as e:
        logger.error("Failed to connect to database")
        logger.error("Traceback: " + str(e))
        return False

    # get environemnt id of current environment
    cursor.execute("SELECT * from environment WHERE name = %s;", (ENV_NAME,))
    data = cursor.fetchone()
    if not data:
        logger.error("Environment not found")
        db.close()
        return False
    env_id = data[0]

    cursor.execute(
        "SELECT * from routines WHERE environment_id = %s and enabled = True;",
        (env_id,),
    )
    routines = cursor.fetchall()

    for routine in routines:
        # set Triggered flag to false
        try:
            logger.info("Resetting 'triggered' flag for " + routine[1] + " routine")
            cursor.execute("UPDATE routines SET triggered = 0 WHERE id = %s;", (routine[0],))
            db.commit()
        except Exception as e:
            logger.error("Failed to update the database")
            logger.error("Traceback: " + str(e))
            db.rollback()
            db.close()
            return False

    return True


def check_mute() -> bool:
    """
    Description:
            checks what time it is and decides if Alfr3d should be quiet
            - between wake-up time and bedtime
            - only when Athos is at home
            - only when 'owner' is at home
    """
    return db_utils.check_mute_optimized(ENV_NAME)


def sunrise_routine():
    """
    Description:
            sunset routine - perform this routine 30 minutes before sunrise
            giving the users time to go see sunrise
    """
    logger.info("Pre-sunrise routine")


def morning_routine():
    """
    Description:
            perform morning routine - ring alarm, speak weather, check email, etc..
    """
    logger.info("Time for morning routine")


def sunset_routine():
    """
    Description:
            routine to perform at sunset - turn on ambient lights
    """
    logger.info("Time for sunset routine")


def bedtime_routine():
    """
    Description:
            routine to perform at bedtime - turn on ambient lights
    """
    logger.info("Bedtime")


if __name__ == "__main__":
    if sys.argv[1] == "reset":
        reset_routines()
