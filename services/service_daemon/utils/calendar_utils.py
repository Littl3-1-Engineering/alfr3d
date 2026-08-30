#!/usr/bin/python

"""
Google Calendar utilities for Alfr3d Daemon.
Integrates with Google Calendar API for fetching events.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, timezone
import orjson
import pymysql
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from common import get_producer

logger = logging.getLogger("CalendarUtils")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]

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
    db = None
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        cursor.execute(
            "SELECT access_token, refresh_token, expires_at "
            "FROM integrations_tokens WHERE integration_type = 'google'"
        )
        row = cursor.fetchone()
        if row:
            access_token, refresh_token, expires_at = row
            creds = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                scopes=SCOPES,
            )
            if expires_at and datetime.now() > expires_at:
                creds.refresh(Request())
                update_tokens("google", creds)
    except pymysql.Error as e:
        logger.error(f"Database error getting Calendar credentials: {e}")
        if db:
            db.rollback()
    except Exception as e:
        logger.error(f"Error getting Calendar credentials: {e}")
    finally:
        if db:
            db.close()
    return creds


def update_tokens(integration_type, creds):
    """Update tokens in DB."""
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        expires_at = (
            datetime.now()
            + timedelta(seconds=creds.expiry.timestamp() - datetime.now().timestamp())
            if creds.expiry
            else None
        )
        cursor.execute(
            "INSERT INTO integrations_tokens "
            "(integration_type, access_token, refresh_token, expires_at) "
            "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE access_token=%s, "
            "refresh_token=%s, expires_at=%s",
            (
                integration_type,
                creds.token,
                creds.refresh_token,
                expires_at,
                creds.token,
                creds.refresh_token,
                expires_at,
            ),
        )
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Error updating tokens: {e}")


def _extract_conference_info(event):
    """Return (conference_uri, conference_solution) from a Google Calendar API event's
    `conferenceData`/`hangoutLink` fields, or (None, None) if the event has no structured
    conferencing attached (SA-7). `conferenceData` is the modern, general field -- covers
    Google Meet, Zoom, Teams, phone/SIP entry points via `conferenceSolution.name` +
    `entryPoints[].uri` -- and is already present in events().list()'s response with no
    extra request parameter or broader OAuth scope needed to read it (conferenceDataVersion
    only gates *creating* conference data on write calls). `hangoutLink` is an older,
    simpler Google-Meet-only field, checked as a fallback for the rare response shape that
    carries it without full `conferenceData`.

    A Zoom/Teams link a human pastes into the free-text notes/address fields by hand -- not
    created through the calendar's structured conferencing integration -- has none of this,
    which is exactly why focus_utils.looks_like_call()'s text heuristic is kept as a lower
    confidence tier rather than retired.
    """
    conference_data = event.get("conferenceData") or {}
    entry_points = conference_data.get("entryPoints") or []
    entry = next((e for e in entry_points if e.get("entryPointType") == "video"), None) or (
        entry_points[0] if entry_points else None
    )
    if entry and entry.get("uri"):
        solution = (conference_data.get("conferenceSolution") or {}).get("name")
        return entry["uri"], solution
    hangout_link = event.get("hangoutLink")
    if hangout_link:
        return hangout_link, "Google Meet"
    return None, None


def get_upcoming_events():
    """
    Fetch upcoming events from DB.
    TODO: Populate DB via Google Calendar API.
    Returns: List of event dicts, or None.
    """
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        now = datetime.now()
        future = now + timedelta(hours=2)
        cursor.execute(
            "SELECT title, start_time, address, notes, conference_uri, conference_solution "
            "FROM calendar_events WHERE start_time BETWEEN %s AND %s "
            "ORDER BY start_time ASC LIMIT 1",
            (now, future),
        )
        row = cursor.fetchone()
        db.close()
        if row:
            return [
                {
                    "title": row[0],
                    "start_time": row[1].replace(tzinfo=timezone.utc),
                    "address": row[2],
                    "notes": row[3],
                    "conference_uri": row[4],
                    "conference_solution": row[5],
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
        service = build("calendar", "v3", credentials=creds)

        # List calendars to find IDs by name
        calendar_list = service.calendarList().list().execute()
        calendars = {cal["summary"]: cal["id"] for cal in calendar_list.get("items", [])}
        logger.debug(f"Available calendars: {calendars}")

        # Desired calendars by name (whitespace-trimmed to tolerate stray spaces in Google's naming)
        desired_calendars = ["Armageddion Littl3.1", "Family", "Cassiopeia"]
        trimmed_calendars = {name.strip(): cal_id for name, cal_id in calendars.items()}
        calendar_ids = []
        for name in desired_calendars:
            if name in trimmed_calendars:
                calendar_ids.append(trimmed_calendars[name])
            else:
                logger.warning(f"Calendar '{name}' not found")

        now_dt = datetime.utcnow()
        future_dt = now_dt + timedelta(days=7)
        now = now_dt.isoformat() + "Z"
        future = future_dt.isoformat() + "Z"

        all_events = []
        for cal_id in calendar_ids:
            events_result = (
                service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=now,
                    timeMax=future,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            all_events.extend(events_result.get("items", []))

        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()

        # The Google Calendar API's timeMin/timeMax filter by *end* time and *start* time
        # respectively (an event is returned if it hasn't ended yet and starts before the
        # horizon) -- not by start_time on both ends. A window filtered on start_time >=
        # now_dt would miss any event still in progress (started before now, not yet
        # ended), leaving its old row undeleted *and* invisible to the diff below, so a
        # still-ongoing event would get re-inserted as a duplicate and misreported as
        # "created" on every sync while it runs.
        window_clause = "end_time >= %s AND start_time <= %s"

        # sync_calendar() wipes and re-inserts the whole sync window every run (no Google
        # event id is stored to upsert against), so a diff against what was there *before*
        # the delete is the only way to tell a genuinely new/changed event from one that's
        # just being re-synced unchanged -- see todo/todo_household_event_log.md.
        cursor.execute(
            f"SELECT title, start_time, end_time, address, notes FROM calendar_events "
            f"WHERE {window_clause}",
            (now_dt, future_dt),
        )
        events_before_sync = set(cursor.fetchall())

        # Delete existing events in the sync range to avoid duplicates
        cursor.execute(f"DELETE FROM calendar_events WHERE {window_clause}", (now_dt, future_dt))

        synced_keys = set()
        new_events = []
        for event in all_events:
            start_str = event["start"].get("dateTime", event["start"].get("date"))
            end_str = event["end"].get("dateTime", event["end"].get("date"))
            # Parse datetime strings, handle 'Z' suffix
            if start_str:
                if "T" in start_str:
                    start = (
                        datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        .astimezone(timezone.utc)
                        .replace(microsecond=0, tzinfo=None)
                    )
                else:
                    # all-day event, start at beginning of day
                    start = datetime.fromisoformat(start_str + "T00:00:00+00:00").replace(
                        tzinfo=None
                    )
            else:
                start = None
            if end_str:
                if "T" in end_str:
                    end = (
                        datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                        .astimezone(timezone.utc)
                        .replace(microsecond=0, tzinfo=None)
                    )
                else:
                    # all-day event, end at beginning of next day
                    end = datetime.fromisoformat(end_str + "T00:00:00+00:00").replace(tzinfo=None)
            else:
                end = None
            title = event.get("summary", "No Title")
            location = event.get("location", "")
            description = event.get("description", "")
            conference_uri, conference_solution = _extract_conference_info(event)

            # Comparison key uses the same (naive, second-precision) datetime objects
            # `events_before_sync` was read back as -- not the formatted strings passed
            # to INSERT -- so a previously-synced, unchanged event round-trips to an
            # identical key and isn't mistaken for new. Deliberately excludes
            # conference_uri/conference_solution (SA-7) -- a conference link appearing on
            # an otherwise-unchanged event isn't a new event worth a household_event.
            row_key = (title, start, end, location, description)
            synced_keys.add(row_key)
            if row_key not in events_before_sync:
                new_events.append(row_key)

            cursor.execute(
                "INSERT INTO calendar_events "
                "(title, start_time, end_time, address, notes, conference_uri, "
                "conference_solution) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    title,
                    start.strftime("%Y-%m-%d %H:%M:%S") if start else None,
                    end.strftime("%Y-%m-%d %H:%M:%S") if end else None,
                    location,
                    description,
                    conference_uri,
                    conference_solution,
                ),
            )
        removed_events = events_before_sync - synced_keys
        db.commit()
        db.close()
        logger.info(f"Synced {len(all_events)} calendar events from {len(calendar_ids)} calendars")
        _publish_calendar_diff(new_events, removed_events)
    except Exception as e:
        logger.error(f"Error syncing calendar: {e}")


def _publish_calendar_diff(new_events, removed_events):
    """Publish one event-stream message per calendar event that appeared or
    disappeared since the last sync (SA-11 Phase 2) -- not for events that
    were merely re-synced unchanged."""
    if not new_events and not removed_events:
        return
    p = get_producer()
    if not p:
        logger.warning("No Kafka producer available; dropping calendar-event changes")
        return
    for title, start, _end, _location, _description in new_events:
        event = {
            "id": f"calendar_event_created_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "type": "info",
            "message": f"New calendar event: {title}",
            "time": datetime.now(timezone.utc).isoformat(),
            "subject_type": "calendar_event",
            "subject_id": title,
            "verb": "created",
        }
        p.send("event-stream", orjson.dumps(event))
    for title, start, _end, _location, _description in removed_events:
        event = {
            "id": f"calendar_event_removed_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "type": "info",
            "message": f"Calendar event removed: {title}",
            "time": datetime.now(timezone.utc).isoformat(),
            "subject_type": "calendar_event",
            "subject_id": title,
            "verb": "removed",
        }
        p.send("event-stream", orjson.dumps(event))
