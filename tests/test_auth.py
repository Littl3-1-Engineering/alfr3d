"""Unit tests for services/service_api/auth/*.

Mock-DB style, mirrors test_esphome_utils.py / test_secrets_wiring.py: no real MySQL, no
TestClient/full app import (that pulls in Kafka consumer threads and docker.sock access) --
these exercise the auth module functions directly, including the async route handlers via
asyncio.run(), the same pattern test_esphome_utils.py already uses for its async coverage.
"""

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "service_api"))
os.environ.setdefault("MYSQL_DATABASE", "localhost")
os.environ.setdefault("MYSQL_USER", "root")
os.environ.setdefault("MYSQL_PSWD", "testrootpassword")
os.environ.setdefault("MYSQL_NAME", "test_alfr3d_db")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("ALFR3D_ENV_NAME", "test")
os.environ.setdefault(
    "ALFR3D_SECRETS_KEY",
    "8pS1sOe6r8kM2v3z1Q5X0jz3n5aQ6l1V9j0k3m0zQeM=",  # pragma: allowlist secret
)  # fixed test-only Fernet key, not a real credential

from auth import (
    dependencies,
    jwt_utils,
    password_utils,
    permissions,
    rate_limit,
    routes,
    tokens,
)  # noqa: E402
from models import (  # noqa: E402
    AdminResetPasswordRequest,
    ChangePasswordRequest,
    ClaimAccountRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
)


def _mock_request(ip="127.0.0.1"):
    req = MagicMock()
    req.client.host = ip
    return req


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """Every test gets an un-throttled login/claim by default -- the dedicated rate-limit tests
    below override this within their own `with patch.object(...)` block."""
    monkeypatch.setattr(routes, "check_rate_limit", lambda *a, **k: True)


# --- password_utils --------------------------------------------------------------------------


def test_password_hash_verify_roundtrip():
    hashed = password_utils.hash_password("correct horse battery staple")
    assert password_utils.verify_password("correct horse battery staple", hashed) is True


def test_password_verify_rejects_wrong_password():
    hashed = password_utils.hash_password("correct horse battery staple")
    assert password_utils.verify_password("wrong password", hashed) is False


def test_password_verify_rejects_empty_or_none_hash():
    assert password_utils.verify_password("anything", "") is False
    assert password_utils.verify_password("anything", None) is False


def test_password_hash_fits_the_password_hash_column_and_uses_pbkdf2():
    """Regression test: werkzeug 3.1.6 (the version actually pinned in requirements.txt)
    defaults generate_password_hash() to `scrypt`, whose output doesn't fit `user.password_hash`
    (VARCHAR(128)) and would fail the UPDATE/INSERT outright -- found by exercising the real
    claim/change-password/admin-reset-password paths against a live deployment. hash_password
    must keep pinning `method="pbkdf2:sha256"` explicitly, not rely on werkzeug's default."""
    hashed = password_utils.hash_password("some-reasonable-password")
    assert hashed.startswith("pbkdf2:sha256:")
    assert len(hashed) <= 128


def test_password_verify_accepts_pre_existing_werkzeug_hash():
    """user id=1's seeded hash format -- confirms we didn't silently pick an incompatible
    hashing scheme (see setup/createTables.sql's seed row and migration_022's data fix)."""
    # seeded hash from createTables.sql, not a live credential
    prefix = "pbkdf2:sha256:260000$EVLamhqzR2ib572V$"
    digest = "29ecaf8e9ef809496eebf2cc1dafc1c865e0efa0184a89dcca63492ced5290bf"  # pragma: allowlist secret  # noqa: E501
    seeded_hash = prefix + digest
    # We don't know the real plaintext password, but a wrong guess must cleanly return False,
    # not raise -- that's the actual risk with a hand-seeded hash of unknown provenance.
    assert password_utils.verify_password("definitely-not-it", seeded_hash) is False


# --- jwt_utils ---------------------------------------------------------------------------------


def test_access_token_roundtrip_preserves_user_id_and_type():
    token = jwt_utils.create_access_token(42, "resident")
    payload = jwt_utils.decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "resident"


def test_decode_access_token_returns_none_for_garbage():
    assert jwt_utils.decode_access_token("not-a-real-token") is None


def test_decode_access_token_returns_none_for_expired_token():
    token = jwt_utils.create_access_token(1, "technoking", ttl_minutes=-1)
    assert jwt_utils.decode_access_token(token) is None


# --- permissions ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resource,action,role,expected",
    [
        ("devices", "*", "technoking", True),
        ("devices", "*", "resident", True),
        ("devices", "*", "guest", False),
        ("users", "*", "technoking", True),
        ("users", "*", "resident", False),
        ("iot", "control", "resident", True),
        ("iot", "config", "resident", False),
        ("iot", "config", "technoking", True),
        ("music", "auth", "resident", False),
        ("music", "auth", "technoking", True),
        ("music", "play", "resident", True),
        ("personality", "update_context", "resident", True),
        ("personality", "update", "resident", False),
        ("environment", "*", "resident", False),
        ("nonexistent_resource", "*", "technoking", False),  # fails closed
    ],
)
def test_permission_matrix(resource, action, role, expected):
    assert permissions.is_allowed(resource, action, role) is expected


def test_owner_aliases_to_technoking():
    assert permissions.is_allowed("users", "*", "owner") is True


def test_alfr3d_system_identity_gets_no_grants():
    assert permissions.is_allowed("devices", "*", "alfr3d") is False


def test_guest_is_never_listed_in_any_grant():
    """Locked design decision: guest == unauthenticated, no special-cased write allowlist."""
    for resource, actions in permissions.PERMISSIONS.items():
        for action, roles in actions.items():
            assert "guest" not in roles, f"{resource}.{action} must not grant guest"


# --- tokens (refresh tokens) --------------------------------------------------------------------


def test_issue_and_redeem_refresh_token():
    mock_db = MagicMock()
    with patch.object(tokens, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        raw = tokens.issue_refresh_token(7)
    assert raw

    mock_db2 = MagicMock()
    mock_db2.cursor.return_value.fetchone.return_value = (7,)
    with patch.object(tokens, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db2
        user_id = tokens.redeem_refresh_token(raw)
    assert user_id == 7


def test_redeem_unknown_token_returns_none():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = None
    with patch.object(tokens, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        assert tokens.redeem_refresh_token("not-a-real-token") is None


def test_revoke_refresh_token_updates_row():
    mock_db = MagicMock()
    with patch.object(tokens, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        tokens.revoke_refresh_token("some-token")
    mock_db.cursor.return_value.execute.assert_called_once()
    assert "UPDATE refresh_tokens" in mock_db.cursor.return_value.execute.call_args.args[0]


# --- dependencies ----------------------------------------------------------------------------


def test_get_current_user_optional_returns_none_without_credentials():
    assert dependencies.get_current_user_optional(credentials=None) is None


def test_get_current_user_optional_returns_none_for_invalid_token():
    creds = MagicMock(credentials="garbage")
    assert dependencies.get_current_user_optional(credentials=creds) is None


def test_get_current_user_optional_returns_user_for_valid_token():
    token = jwt_utils.create_access_token(5, "technoking")
    creds = MagicMock(credentials=token)
    user = dependencies.get_current_user_optional(credentials=creds)
    assert user.id == 5
    assert user.type == "technoking"


def test_require_auth_raises_401_when_unauthenticated():
    with pytest.raises(HTTPException) as exc_info:
        dependencies.require_auth(user=None)
    assert exc_info.value.status_code == 401


def test_require_permission_raises_401_when_unauthenticated():
    dep = dependencies.require_permission("devices", "*")
    with pytest.raises(HTTPException) as exc_info:
        dep(user=None)
    assert exc_info.value.status_code == 401


def test_require_permission_raises_403_when_role_lacks_grant():
    dep = dependencies.require_permission("users", "*")
    guest = dependencies.CurrentUser(id=3, type="resident")
    with pytest.raises(HTTPException) as exc_info:
        dep(user=guest)
    assert exc_info.value.status_code == 403


def test_require_permission_passes_through_when_allowed():
    dep = dependencies.require_permission("devices", "*")
    resident = dependencies.CurrentUser(id=2, type="resident")
    assert dep(user=resident) is resident


# --- routes: /auth/claim guard -----------------------------------------------------------------


def test_claim_account_rejects_already_claimed_user():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = (1, "existing-hash", "technoking")
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                routes.claim_account(
                    ClaimAccountRequest(
                        username="athos", password="newpassword"  # pragma: allowlist secret
                    ),
                    _mock_request(),
                )
            )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unable to claim this account"


def test_claim_account_rejects_unknown_user_with_same_generic_error():
    """Same status/detail as the already-claimed case above -- proves the two aren't
    distinguishable from the response, i.e. no username-enumeration channel on this endpoint."""
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = None
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                routes.claim_account(
                    ClaimAccountRequest(
                        username="ghost", password="newpassword123"  # pragma: allowlist secret
                    ),
                    _mock_request(),
                )
            )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unable to claim this account"


def test_claim_account_rejects_short_password():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            routes.claim_account(
                ClaimAccountRequest(username="athos", password="short"),  # pragma: allowlist secret
                _mock_request(),
            )
        )
    assert exc_info.value.status_code == 400


def test_claim_account_rejects_when_rate_limited():
    with patch.object(routes, "check_rate_limit", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                routes.claim_account(
                    ClaimAccountRequest(
                        username="athos", password="newpassword123"  # pragma: allowlist secret
                    ),
                    _mock_request(),
                )
            )
    assert exc_info.value.status_code == 429


def test_claim_account_sets_password_and_issues_tokens_for_unclaimed_user():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = (2, None, "resident")
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with patch.object(tokens, "issue_refresh_token", return_value="refresh-token-value"):
            result = asyncio.run(
                routes.claim_account(
                    ClaimAccountRequest(
                        username="unknown", password="newpassword123"  # pragma: allowlist secret
                    ),
                    _mock_request(),
                )
            )
    assert result["refresh_token"] == "refresh-token-value"
    assert result["token_type"] == "bearer"
    update_call = [
        c for c in mock_db.cursor.return_value.execute.call_args_list if "UPDATE user" in c.args[0]
    ][0]
    assert update_call.args[1][1] == 2  # user_id


def test_login_rejects_wrong_password():
    mock_db = MagicMock()
    seeded_hash = password_utils.hash_password("the-real-password")
    mock_db.cursor.return_value.fetchone.return_value = (1, seeded_hash, "technoking")
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                routes.login(
                    LoginRequest(
                        username="athos", password="wrong-guess"  # pragma: allowlist secret
                    ),
                    _mock_request(),
                )
            )
    assert exc_info.value.status_code == 401


def test_login_rejects_unknown_user():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = None
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                routes.login(
                    LoginRequest(username="ghost", password="anything"),  # pragma: allowlist secret
                    _mock_request(),
                )
            )
    assert exc_info.value.status_code == 401


def test_login_rejects_when_rate_limited():
    with patch.object(routes, "check_rate_limit", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                routes.login(
                    LoginRequest(username="athos", password="anything"),  # pragma: allowlist secret
                    _mock_request(),
                )
            )
    assert exc_info.value.status_code == 429


def test_login_succeeds_and_issues_tokens_for_correct_password():
    mock_db = MagicMock()
    seeded_hash = password_utils.hash_password("the-real-password")
    mock_db.cursor.return_value.fetchone.return_value = (1, seeded_hash, "technoking")
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with patch.object(tokens, "issue_refresh_token", return_value="refresh-token-value"):
            result = asyncio.run(
                routes.login(
                    LoginRequest(
                        username="athos", password="the-real-password"  # pragma: allowlist secret
                    ),
                    _mock_request(),
                )
            )
    assert result["refresh_token"] == "refresh-token-value"
    payload = jwt_utils.decode_access_token(result["access_token"])
    assert payload["sub"] == "1"
    assert payload["type"] == "technoking"


def test_logout_revokes_the_given_refresh_token():
    with patch.object(routes.tokens, "revoke_refresh_token") as mock_revoke:
        result = asyncio.run(routes.logout(LogoutRequest(refresh_token="some-token")))
    mock_revoke.assert_called_once_with("some-token")
    assert result == {"success": True}


def test_refresh_rejects_invalid_token():
    with patch.object(routes.tokens, "redeem_refresh_token", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(routes.refresh(RefreshRequest(refresh_token="bad-token")))
    assert exc_info.value.status_code == 401


def test_refresh_rotates_token_and_issues_new_access_token():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = ("resident",)
    with patch.object(routes.tokens, "redeem_refresh_token", return_value=9):
        with patch.object(routes.tokens, "revoke_refresh_token") as mock_revoke:
            with patch.object(routes.tokens, "issue_refresh_token", return_value="new-refresh"):
                with patch.object(routes, "db_connection") as mock_conn:
                    mock_conn.return_value.__enter__.return_value = mock_db
                    result = asyncio.run(routes.refresh(RefreshRequest(refresh_token="old-token")))
    mock_revoke.assert_called_once_with("old-token")
    assert result["refresh_token"] == "new-refresh"
    payload = jwt_utils.decode_access_token(result["access_token"])
    assert payload["sub"] == "9"
    assert payload["type"] == "resident"


# --- rate_limit --------------------------------------------------------------------------------


def test_check_rate_limit_allows_within_budget():
    with patch.object(rate_limit, "redis_incr_with_ttl", return_value=3):
        assert rate_limit.check_rate_limit("k", max_attempts=5, window_seconds=60) is True


def test_check_rate_limit_blocks_after_max_attempts():
    with patch.object(rate_limit, "redis_incr_with_ttl", return_value=6):
        assert rate_limit.check_rate_limit("k", max_attempts=5, window_seconds=60) is False


def test_check_rate_limit_fails_open_when_redis_unavailable():
    with patch.object(rate_limit, "redis_incr_with_ttl", return_value=None):
        assert rate_limit.check_rate_limit("k", max_attempts=5, window_seconds=60) is True


# --- routes: /auth/change-password --------------------------------------------------------------


def test_change_password_rejects_short_new_password():
    user = dependencies.CurrentUser(id=1, type="resident")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            routes.change_password(
                ChangePasswordRequest(
                    current_password="whatever", new_password="short"  # pragma: allowlist secret
                ),
                user=user,
            )
        )
    assert exc_info.value.status_code == 400


def test_change_password_rejects_wrong_current_password():
    mock_db = MagicMock()
    seeded_hash = password_utils.hash_password("the-real-password")
    mock_db.cursor.return_value.fetchone.return_value = (seeded_hash,)
    user = dependencies.CurrentUser(id=1, type="resident")
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                routes.change_password(
                    ChangePasswordRequest(
                        current_password="wrong-guess",  # pragma: allowlist secret
                        new_password="brand-new-password",  # pragma: allowlist secret
                    ),
                    user=user,
                )
            )
    assert exc_info.value.status_code == 401


def test_change_password_succeeds_and_revokes_other_sessions():
    mock_db = MagicMock()
    seeded_hash = password_utils.hash_password("the-real-password")
    mock_db.cursor.return_value.fetchone.return_value = (seeded_hash,)
    user = dependencies.CurrentUser(id=1, type="technoking")
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with patch.object(tokens, "revoke_all_refresh_tokens") as mock_revoke_all:
            with patch.object(tokens, "issue_refresh_token", return_value="fresh-refresh"):
                result = asyncio.run(
                    routes.change_password(
                        ChangePasswordRequest(
                            current_password="the-real-password",  # pragma: allowlist secret
                            new_password="brand-new-password",  # pragma: allowlist secret
                        ),
                        user=user,
                    )
                )
    mock_revoke_all.assert_called_once_with(1)
    assert result["refresh_token"] == "fresh-refresh"
    payload = jwt_utils.decode_access_token(result["access_token"])
    assert payload["sub"] == "1"
    assert payload["type"] == "technoking"
    update_call = [
        c for c in mock_db.cursor.return_value.execute.call_args_list if "UPDATE user" in c.args[0]
    ][0]
    assert update_call.args[1][1] == 1  # user_id


# --- routes: /auth/admin-reset-password ----------------------------------------------------------


def test_admin_reset_password_rejects_short_password():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            routes.admin_reset_password(
                AdminResetPasswordRequest(
                    user_id=2, new_password="short"
                ),  # pragma: allowlist secret
                _perm=dependencies.CurrentUser(id=1, type="technoking"),
            )
        )
    assert exc_info.value.status_code == 400


def test_admin_reset_password_rejects_unknown_user():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = None
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                routes.admin_reset_password(
                    AdminResetPasswordRequest(
                        user_id=999, new_password="brand-new-password"  # pragma: allowlist secret
                    ),
                    _perm=dependencies.CurrentUser(id=1, type="technoking"),
                )
            )
    assert exc_info.value.status_code == 404


def test_admin_reset_password_sets_new_hash_and_revokes_target_sessions():
    mock_db = MagicMock()
    mock_db.cursor.return_value.fetchone.return_value = (2,)
    with patch.object(routes, "db_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_db
        with patch.object(tokens, "revoke_all_refresh_tokens") as mock_revoke_all:
            result = asyncio.run(
                routes.admin_reset_password(
                    AdminResetPasswordRequest(
                        user_id=2, new_password="brand-new-password"  # pragma: allowlist secret
                    ),
                    _perm=dependencies.CurrentUser(id=1, type="technoking"),
                )
            )
    mock_revoke_all.assert_called_once_with(2)
    assert result == {"success": True}
    update_call = [
        c for c in mock_db.cursor.return_value.execute.call_args_list if "UPDATE user" in c.args[0]
    ][0]
    assert update_call.args[1][1] == 2  # user_id
