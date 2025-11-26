#!/usr/bin/python

"""
Google Calendar utilities for Alfr3d Daemon.
Integrates with Google Calendar API for fetching events.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
import pymysql
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

logger = logging.getLogger("CalendarUtils")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/calendar.readonly', 'https://www.googleapis.com/auth/calendar.events.readonly']

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")
MYSQL_DB = os.environ.get("MYSQL_NAME")
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")


def get_credentials():
    """Get valid credentials for Calendar API."""
    creds = None
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
        )
        cursor = db.cursor()
        cursor.execute(
            "SELECT access_token, refresh_token, expires_at FROM integrations_tokens WHERE integration_type = 'google'"
        )
        row = cursor.fetchone()
        db.close()
        if row:
            access_token, refresh_token, expires_at = row
            creds = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                scopes=SCOPES
            )
            if expires_at and datetime.now() > expires_at:
                creds.refresh(Request())
                # Update DB with new token
                update_tokens('google', creds)
    except Exception as e:
        logger.error(f"Error getting Calendar credentials: {e}")
    return creds


def update_tokens(integration_type, creds):
    """Update tokens in DB."""
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
        )
        cursor = db.cursor()
        expires_at = datetime.now() + timedelta(seconds=creds.expiry.timestamp() - datetime.now().timestamp()) if creds.expiry else None
        cursor.execute(
            "INSERT INTO integrations_tokens (integration_type, access_token, refresh_token, expires_at) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE access_token=%s, refresh_token=%s, expires_at=%s",
            (integration_type, creds.token, creds.refresh_token, expires_at, creds.token, creds.refresh_token, expires_at)
        )
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Error updating tokens: {e}")


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
            "SELECT title, start_time, address, notes FROM calendar_events WHERE start_time BETWEEN %s AND %s AND address IS NOT NULL AND address != '' ORDER BY start_time ASC LIMIT 1",
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


def sync_calendar():
    """
    Sync calendar events from Google Calendar API.
    """
    logger.info("Syncing calendar events")
    creds = get_credentials()
    if not creds:
        logger.warning("No Calendar credentials available")
        return

    try:
        service = build('calendar', 'v3', credentials=creds)

        # List calendars to find IDs by name
        calendar_list = service.calendarList().list().execute()
        calendars = {cal['summary']: cal['id'] for cal in calendar_list.get('items', [])}
        logger.debug(f"Available calendars: {calendars}")

        # Desired calendars: primary is special, others by name
        desired_calendars = ['primary', 'Family', 'Cassiopeia ']
        calendar_ids = []
        for name in desired_calendars:
            if name == 'primary':
                calendar_ids.append('primary')
            elif name in calendars:
                calendar_ids.append(calendars[name])
            else:
                logger.warning(f"Calendar '{name}' not found")

        now = datetime.utcnow().isoformat() + 'Z'
        future = (datetime.utcnow() + timedelta(days=7)).isoformat() + 'Z'

        all_events = []
        for cal_id in calendar_ids:
            events_result = service.events().list(calendarId=cal_id, timeMin=now, timeMax=future, singleEvents=True, orderBy='startTime').execute()
            all_events.extend(events_result.get('items', []))

        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
        )
        cursor = db.cursor()
        for event in all_events:
            start_str = event['start'].get('dateTime', event['start'].get('date'))
            end_str = event['end'].get('dateTime', event['end'].get('date'))
            # Parse datetime strings, handle 'Z' suffix
            if start_str and 'T' in start_str:
                start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            else:
                start = start_str
            if end_str and 'T' in end_str:
                end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            else:
                end = end_str
            title = event.get('summary', 'No Title')
            location = event.get('location', '')
            description = event.get('description', '')

            cursor.execute(
                "INSERT INTO calendar_events (title, start_time, end_time, address, notes) VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE title=%s, end_time=%s, address=%s, notes=%s",
                (title, start, end, location, description, title, end, location, description)
            )
        db.commit()
        db.close()
        logger.info(f"Synced {len(all_events)} calendar events from {len(calendar_ids)} calendars")
    except Exception as e:
        logger.error(f"Error syncing calendar: {e}")
