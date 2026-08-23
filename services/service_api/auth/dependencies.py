"""FastAPI auth dependencies: get_current_user_optional / require_auth / require_permission.

Design (todo/todo_auth_rbac.md): unauthenticated callers get read-only access everywhere (GET
routes stay undecorated, never call these). Every write route (POST/PUT/DELETE) is wrapped with
`Depends(require_permission(resource, action))` -- 401 if no/invalid token, 403 if authenticated
but the role lacks the grant for that resource+action.
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth import jwt_utils, permissions

# auto_error=False: a missing Authorization header must fall through to
# get_current_user_optional() returning None (anonymous/read-only), not an automatic 403 from
# HTTPBearer itself.
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: int
    type: str


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
):
    if credentials is None:
        return None
    payload = jwt_utils.decode_access_token(credentials.credentials)
    if payload is None:
        return None
    return CurrentUser(id=int(payload["sub"]), type=payload["type"])


def require_auth(user: CurrentUser = Depends(get_current_user_optional)):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_permission(resource, action="*"):
    """Returns a FastAPI dependency: 401 if unauthenticated, 403 if the authenticated user's
    role lacks this resource+action grant per auth/permissions.py's matrix."""

    def _dependency(user: CurrentUser = Depends(get_current_user_optional)):
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if not permissions.is_allowed(resource, action, user.type):
            raise HTTPException(status_code=403, detail="Not permitted")
        return user

    return _dependency
