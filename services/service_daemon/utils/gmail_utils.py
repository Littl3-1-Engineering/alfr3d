#!/usr/bin/python

"""
Gmail utilities for Alfr3d Daemon.
Integrates with Gmail API for fetching unread emails.
"""

from email.utils import parseaddr
import os
import sys
import logging
from datetime import datetime, timedelta
import pymysql
import urllib.request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

logger = logging.getLogger("GmailUtils")
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
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")


def check_internet():
    """Check if internet is available by testing connection to Google's OAuth endpoint."""
    try:
        urllib.request.urlopen('https://www.google.com', timeout=30)
        logger.debug("Internet connection available")
        return True
    except Exception as e:
        logger.warning("No internet connection available")
        logger.warning(str(e))
        return False


def get_credentials():
    """Get valid credentials for Gmail API."""
    logger.debug("Getting Gmail credentials")
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
            if expires_at and datetime.utcnow() > expires_at:
                if check_internet():
                    creds.refresh(Request())
                    # Update DB with new token
                    update_tokens('google', creds)
                else:
                    logger.warning("OAuth token expired and no internet available to refresh. Skipping Gmail checks.")
                    return None
    except Exception as e:
        logger.error(f"Error getting Gmail credentials: {e}")
    return creds


def update_tokens(integration_type, creds):
    """Update tokens in DB."""
    logger.debug("Updating tokens in DB")
    try:
        db = pymysql.connect(
            host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
        )
        cursor = db.cursor()
        expires_at = datetime.utcnow() + timedelta(seconds=creds.expiry.timestamp() - datetime.utcnow().timestamp()) if creds.expiry else None
        cursor.execute(
            "INSERT INTO integrations_tokens (integration_type, access_token, refresh_token, expires_at) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE access_token=%s, refresh_token=%s, expires_at=%s",
            (integration_type, creds.token, creds.refresh_token, expires_at, creds.token, creds.refresh_token, expires_at)
        )
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Error updating tokens: {e}")


def check_unread_emails():
    """
    Fetch unread emails on-demand.
    Returns: List of dicts with 'sender' and 'subject', or None.
    """
    logger.info("Checking for unread emails")
    creds = get_credentials()
    if not creds:
        logger.warning("No Gmail credentials available")
        return None

    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', q='is:unread').execute()
        messages = results.get('messages', [])

        emails = []
        for msg in messages[:5]:  # Limit to 5
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = msg_data['payload']['headers']
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            # Parse it to get only the name (returns "John Doe")
            sender_name, sender_email = parseaddr(sender)
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            emails.append({'sender': sender_name, 'subject': subject})

        logger.info(f"Fetched {len(emails)} unread emails")
        return emails if emails else None
    except Exception as e:
        logger.error(f"Error fetching unread emails: {e}")
        return None


def authorize_google():
    """Authorize Google and store tokens."""
    if not CLIENT_ID or not CLIENT_SECRET:
        logger.error("CLIENT_ID and CLIENT_SECRET not set")
        return
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES
    )
    creds = flow.run_local_server(port=0)
    update_tokens('google', creds)
    logger.info("Google authorized and tokens stored")


def sync_gmail():
    """
    Sync Gmail data.
    """
    logger.info("Syncing Gmail")
    # For now, just check unread emails
    emails = check_unread_emails()
    if emails:
        logger.info(f"Synced Gmail: {len(emails)} unread emails")
    else:
        logger.info("No unread emails to sync")
