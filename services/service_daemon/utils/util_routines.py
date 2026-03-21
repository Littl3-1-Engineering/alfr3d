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
import json
import pymysql as MySQLdb
from datetime import datetime
from kafka import KafkaProducer
from kafka.errors import KafkaError
from utils.db_utils import check_mute_optimized

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
KAFKA_URL = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")

try:
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_URL,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
except KafkaError:
    logger.warning("Failed to create Kafka producer, actions will not be sent")
    producer = None


def execute_actions(actions_json):
    """Execute actions from JSON array via Kafka."""
    if not actions_json:
        return 0

    try:
        actions = json.loads(actions_json) if isinstance(actions_json, str) else actions_json
    except (json.JSONDecodeError, TypeError):
        logger.error("Invalid actions JSON")
        return 0

    if not producer:
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

            executed += 1
        except Exception as e:
            logger.error(f"Failed to execute action {action_type}: {str(e)}")

    return executed


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

    # get environemnt id of current environment
    cursor.execute("SELECT * from environment WHERE name = %s;", (ENV_NAME,))
    data = cursor.fetchone()
    if not data:
        logger.error("Environment not found")
        db.close()
        return False
    env_id = data[0]

    cursor.execute("SELECT * from routines WHERE environment_id = %s and enabled = 1;", (env_id,))
    routines = cursor.fetchall()

    for routine in routines:
        logger.info(
            "Checking "
            + routine[1]
            + " routine with time "
            + str(routine[2])
            + " and flag "
            + str(routine[4])
        )
        # get routine trigger time and flag
        routine_time = routine[2]
        routine_time = datetime.now().replace(
            hour=int(routine_time.seconds / 3600),
            minute=int((routine_time.seconds // 60) % 60),
        )
        routine_trigger = routine[6]
        recurrence = routine[4] if len(routine) > 4 else "daily"
        actions = routine[5] if len(routine) > 5 else None
        cur_time = datetime.now()
        cur_weekday = cur_time.weekday()

        should_trigger = False
        if cur_time > routine_time and not routine_trigger:
            if recurrence == "once":
                should_trigger = True
            elif recurrence == "daily":
                should_trigger = True
            elif recurrence == "weekdays" and cur_weekday < 5:
                should_trigger = True
            elif recurrence == "weekly":
                should_trigger = True

        if should_trigger:
            logger.info(routine[1] + " routine is being triggered")
            if actions:
                executed = execute_actions(actions)
                logger.info(f"Executed {executed} actions for routine {routine[1]}")
            try:
                cursor.execute(
                    "UPDATE routines SET triggered = 1, last_run = NOW() WHERE id = %s;",
                    (routine[0],),
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
    return check_mute_optimized(ENV_NAME)


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
