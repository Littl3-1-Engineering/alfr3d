#!/usr/bin/env python3
"""
Self-service password reset for solo-owner lockout recovery.

Bypasses ALFR3D's own auth API entirely -- talks straight to MySQL, so it works even when
nobody can log in (the whole point). The script's own invocation IS the trust boundary: running
it requires either shell access to the Kit's host or `docker compose exec` access into a running
container -- the same physical/local-network access boundary `claim`/`bootstrap` already rely on
for onboarding, not a new one. Works against any username, not just an 'owner' row: whoever can
run this already has the DB credentials to do the same update by hand, so restricting it to one
role would be security theater, not a real boundary.

This exists instead of an emailed password-reset flow -- see todo/todo_email_service.md for why
household units don't send email at all (no real security benefit at onboarding time, and every
multi-resident household already has admin-assisted reset via the API; this script is the
missing piece for the one gap that leaves: a solo-owner household where the owner locks
themselves out with nobody else to help).

Usage (run from the repo root):
    python3 setup/reset_owner_password.py --list
    python3 setup/reset_owner_password.py --username athos
    python3 setup/reset_owner_password.py --username athos --password "a specific new password"

Also works via `docker compose exec service-api python3 - --username athos
< setup/reset_owner_password.py` -- the container's own environment already has the right
MYSQL_* values.
"""

import argparse
import hashlib
import os
import secrets
import sys

import pymysql

# Password hashing is duplicated from services/service_api/auth/password_utils.py rather than
# imported -- this script must run standalone (bare host or an ad hoc container exec) without
# depending on service_api's package layout being importable from wherever it's invoked. The
# output format is self-describing (`pbkdf2:sha256:<iterations>$<salt>$<hex digest>`): werkzeug's
# check_password_hash() re-derives the iteration count from the stored string itself rather than
# assuming its own current default, so this only needs to produce a correctly-shaped string, not
# track werkzeug's default forever.
_PBKDF2_ITERATIONS = 1_000_000
_SALT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _hash_password(plain_password):
    salt = "".join(secrets.choice(_SALT_CHARS) for _ in range(16))
    digest = hashlib.pbkdf2_hmac(
        "sha256", plain_password.encode(), salt.encode(), _PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2:sha256:{_PBKDF2_ITERATIONS}${salt}${digest}"


def _load_env_file():
    """Mirrors authorize_google.py's own .env loading -- only fills in vars not already set, so
    a real container environment (docker compose exec) always wins over the file."""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _resolve_mysql_host():
    configured = os.environ.get("MYSQL_DATABASE")
    if os.path.exists("/.dockerenv"):
        # Inside a container on the compose network -- "mysql" (or whatever's configured)
        # resolves fine here via Docker's embedded DNS.
        return configured or "mysql"
    if not configured or configured == "mysql":
        # Bare host shell: "mysql" is docker-compose's internal network hostname, unreachable
        # outside it. mysql's 3306 is published to the host (docker-compose.yml), so reach it
        # there instead.
        return "127.0.0.1"
    return configured


def _connect():
    _load_env_file()
    return pymysql.connect(
        host=_resolve_mysql_host(),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "user"),
        password=os.environ.get("MYSQL_PSWD", ""),
        database=os.environ.get("MYSQL_NAME", "alfr3d_db"),
    )


def list_users(db):
    cursor = db.cursor()
    cursor.execute(
        "SELECT u.username, ut.type, "
        "CASE WHEN u.password_hash IS NULL OR u.password_hash = '' THEN 'unclaimed' "
        "ELSE 'claimed' END AS status "
        "FROM user u JOIN user_types ut ON u.type = ut.id "
        "WHERE u.username IS NOT NULL ORDER BY u.username"
    )
    rows = cursor.fetchall()
    if not rows:
        print("No users found.")
        return
    print(f"{'username':<20} {'type':<12} status")
    for username, user_type, status in rows:
        print(f"{username:<20} {user_type:<12} {status}")


def reset_password(db, username, new_password):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM user WHERE username = %s", (username,))
    row = cursor.fetchone()
    if not row:
        print(
            f"No user named {username!r} found. Run --list to see valid usernames.", file=sys.stderr
        )
        sys.exit(1)
    user_id = row[0]

    cursor.execute(
        "UPDATE user SET password_hash = %s WHERE id = %s",
        (_hash_password(new_password), user_id),
    )
    # Mirrors admin_reset_password's behavior in auth/routes.py: force every existing session
    # (if any survived whatever locked this account out) to re-login on the new password.
    cursor.execute(
        "UPDATE refresh_tokens SET revoked_at = UTC_TIMESTAMP() "
        "WHERE user_id = %s AND revoked_at IS NULL",
        (user_id,),
    )
    db.commit()
    print(f"Password reset for {username!r}. Every existing session was signed out.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List usernames and claim status")
    parser.add_argument("--username", help="Username to reset")
    parser.add_argument(
        "--password",
        help="New password (min 8 chars). If omitted, a random one is generated and printed once.",
    )
    args = parser.parse_args()

    if not args.list and not args.username:
        parser.error("pass --username <name> (or --list to see available usernames)")
    if args.password is not None and len(args.password) < 8:
        parser.error("--password must be at least 8 characters")

    db = _connect()
    try:
        if args.list:
            list_users(db)
            return
        new_password = args.password or secrets.token_urlsafe(12)
        reset_password(db, args.username, new_password)
        if not args.password:
            print(f"Generated password: {new_password}")
            print("Log in with this once, then change it from your profile.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
