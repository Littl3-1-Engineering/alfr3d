#!/usr/bin/env python3

"""
Script to authorize Google integrations for ALFR3D.
Run this script to obtain and store OAuth tokens for Gmail and Calendar.
"""

import os
import sys
import logging
from google_auth_oauthlib.flow import InstalledAppFlow
from datetime import datetime, timedelta
import pymysql

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]

# Load .env file if it exists
env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                value = value.strip('"').strip("'")  # Remove quotes
                os.environ[key] = value

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "localhost")
MYSQL_USER = os.environ.get("MYSQL_USER", "user")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD", "password")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")

# If running locally, mysql host should be localhost
if MYSQL_DATABASE == "mysql":
    MYSQL_DATABASE = "localhost"


def update_tokens(integration_type, creds):
    """Update tokens in DB."""
    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
        expires_at = (
            datetime.utcnow()
            + timedelta(seconds=creds.expiry.timestamp() - datetime.utcnow().timestamp())
            if creds.expiry
            else None
        )
        cursor.execute(
            "INSERT INTO integrations_tokens (integration_type, access_token, refresh_token, "
            "expires_at) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE access_token=%s, "
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
        logger.info("Tokens updated in DB")
    except Exception as e:
        logger.error(f"Error updating tokens: {e}")


def main():
    logger.info(f"CLIENT_ID: {CLIENT_ID}")
    logger.info(f"CLIENT_SECRET: {'*' * len(CLIENT_SECRET) if CLIENT_SECRET else None}")
    if not CLIENT_ID or not CLIENT_SECRET:
        logger.error("CLIENT_ID and CLIENT_SECRET environment variables must be set")
        sys.exit(1)

    # Validate CLIENT_ID format
    if not CLIENT_ID.endswith(".apps.googleusercontent.com"):
        logger.error(
            "CLIENT_ID does not look like a valid Google OAuth client ID. It should end "
            "with '.apps.googleusercontent.com'"
        )
        sys.exit(1)

    logger.info("Starting Google OAuth flow...")

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost:8081"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
    )

    creds = flow.run_local_server(port=8081)
    update_tokens("google", creds)
    logger.info("Google authorized and tokens stored successfully!")


if __name__ == "__main__":
    main()
