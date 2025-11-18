#!/usr/bin/python

"""
Google Calendar utilities for Alfr3d Daemon.
TODO: Integrate Google Calendar API for fetching events.
"""

import os
import logging
from datetime import datetime, timedelta
import pymysql

logger = logging.getLogger("CalendarUtils")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")
MYSQL_DB = os.environ.get("MYSQL_NAME")
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")


def get_upcoming_events():
    """
    Fetch upcoming events from DB.
    TODO: Populate DB via Google Calendar API.
    Returns: List of event dicts, or None.
    """
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
        )
        cursor = db.cursor()
        now = datetime.now()
        future = now + timedelta(hours=2)
        cursor.execute(
            "SELECT title, start_time, address, notes FROM events WHERE start_time BETWEEN %s AND %s AND address IS NOT NULL AND address != '' ORDER BY start_time ASC LIMIT 1",
            (now, future),
        )
        row = cursor.fetchone()
        db.close()
        if row:
            return [
                {
                    "title": row[0],
                    "start_time": row[1],
                    "address": row[2],
                    "notes": row[3],
                }
            ]
    except Exception as e:
        logger.error("Calendar DB error: " + str(e))
    return None
