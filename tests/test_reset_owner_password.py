"""Unit tests for setup/reset_owner_password.py.

Only covers the two pure-logic pieces worth guarding against regression: the hand-duplicated
password hashing (must stay verifiable by werkzeug.security.check_password_hash, the function the
real API uses) and the host-resolution fallback (bare host vs. container). DB interaction
(list_users/reset_password) was exercised manually against a real MySQL container rather than
mocked here -- see the session that added this script for that verification; a maintenance
script's DB glue isn't part of this repo's existing test convention (no other setup/*.py script
has test coverage either).
"""

import os
import sys
from unittest.mock import patch

from werkzeug.security import check_password_hash

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "setup"))
import reset_owner_password as script  # noqa: E402


def test_hash_password_is_accepted_by_werkzeug_check_password_hash():
    hashed = script._hash_password("correct horse battery staple")
    assert check_password_hash(hashed, "correct horse battery staple") is True


def test_hash_password_rejects_wrong_password():
    hashed = script._hash_password("correct horse battery staple")
    assert check_password_hash(hashed, "wrong password") is False


def test_hash_password_produces_distinct_salts():
    a = script._hash_password("same-password")
    b = script._hash_password("same-password")
    assert a != b  # random salt per call, matching generate_password_hash's own behavior


def test_resolve_mysql_host_falls_back_to_localhost_on_bare_host():
    with patch.object(os.path, "exists", return_value=False):
        with patch.dict(os.environ, {"MYSQL_DATABASE": "mysql"}, clear=False):
            assert script._resolve_mysql_host() == "127.0.0.1"


def test_resolve_mysql_host_trusts_container_env():
    with patch.object(os.path, "exists", return_value=True):
        with patch.dict(os.environ, {"MYSQL_DATABASE": "mysql"}, clear=False):
            assert script._resolve_mysql_host() == "mysql"


def test_resolve_mysql_host_respects_explicit_override():
    with patch.object(os.path, "exists", return_value=False):
        with patch.dict(os.environ, {"MYSQL_DATABASE": "10.0.0.5"}, clear=False):
            assert script._resolve_mysql_host() == "10.0.0.5"
