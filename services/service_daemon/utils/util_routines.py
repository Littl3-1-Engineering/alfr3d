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
