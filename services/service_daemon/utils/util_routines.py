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
import pymysql as MySQLdb
from datetime import datetime

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
        routine_trigger = routine[4]
        cur_time = datetime.now()

        # does routine need to be triggered??
        if cur_time > routine_time and not routine_trigger:
            logger.info(routine[1] + " routine is being triggered")
            # set triggered flag = True
            try:
                logger.info("Resetting 'triggered' flag for " + routine[1] + " routine")
                cursor.execute("UPDATE routines SET triggered = 1 WHERE id = %s;", (routine[0],))
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
    logger.info("Checking if Alfr3d should be mute")
    result = False

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
        "SELECT * from routines WHERE environment_id = %s and name = %s;",
        (env_id, "Morning"),
    )
    morning = cursor.fetchone()
    if not morning:
        logger.error("Morning routine not found")
        db.close()
        return False
    morning_time = morning[2]

    cursor.execute(
        "SELECT * from routines WHERE environment_id = %s and name = %s;",
        (env_id, "Bedtime"),
    )
    bed = cursor.fetchone()
    if not bed:
        logger.error("Bedtime routine not found")
        db.close()
        return False
    bed_time = bed[2]

    cur_time = datetime.now()
    mor_time = datetime.now().replace(
        hour=int(morning_time.seconds / 3600),
        minute=int((morning_time.seconds // 60) % 60),
    )
    end_time = datetime.now().replace(
        hour=int(bed_time.seconds / 3600), minute=int((bed_time.seconds // 60) % 60)
    )

    # only speak between morning alarm and bedtime alarm...
    if cur_time > mor_time and cur_time < end_time:
        logger.info("Alfr3d is free to speak during this time of day")
    else:
        logger.info("Alfr3d should be quiet while we're sleeping")
        result = True

    # get state id of status "online"
    cursor.execute('SELECT * from states WHERE state = "online";')
    data = cursor.fetchone()
    if not data:
        logger.error("Online state not found")
        db.close()
        return False
    state_id = data[0]

    # get all user types which are god or owner type
    cursor.execute(
        'SELECT * from user_types WHERE type = "owner" or type = "technoking" or type = "resident";'
    )
    data = cursor.fetchall()
    if not data:
        logger.error("No user types found")
        db.close()
        return False
    types = []
    for item in data:
        types.append(item[0])

    # see if any users worth speaking to are online
    cursor.execute(
        "SELECT * from user WHERE state = %s and type IN (%s, %s, %s);",
        (state_id, types[0], types[1], types[2]),
    )
    data = cursor.fetchall()

    if not data:
        logger.info("Alfr3d should be quiet when no worthy ears are around")
        result = True
    else:
        logger.info("Alfr3d has worthy listeners:")
        for user in data:
            logger.info("    - " + user[1])

    if result:
        logger.info("Alfr3d is to be quiet")
    else:
        logger.info("Alfr3d is free to speak")

    return result


if __name__ == "__main__":
    if sys.argv[1] == "reset":
        reset_routines()
