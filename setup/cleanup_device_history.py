#!/usr/bin/env python3
"""
Script to cleanup old device history entries.
Run this periodically, e.g., via cron.
"""
import os
import pymysql
from datetime import datetime, timedelta

MYSQL_DATABASE = os.environ["MYSQL_DATABASE"]
MYSQL_DB = os.environ["MYSQL_NAME"]
MYSQL_USER = os.environ["MYSQL_USER"]
MYSQL_PSWD = os.environ["MYSQL_PSWD"]


def cleanup_device_history():
    db = pymysql.connect(
        host=MYSQL_DATABASE,
        user=MYSQL_USER,
        password=MYSQL_PSWD,
        database=MYSQL_DB,
    )
    cursor = db.cursor()
    cutoff = datetime.now() - timedelta(days=180)
    cursor.execute("DELETE FROM device_history WHERE timestamp < %s", (cutoff,))
    deleted = cursor.rowcount
    db.commit()
    # Optionally optimize
    # cursor.execute("OPTIMIZE TABLE device_history")
    db.close()
    print(f"Deleted {deleted} old device history entries.")


if __name__ == "__main__":
    cleanup_device_history()
