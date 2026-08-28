"""Code-defined permission matrix: {resource: {action: {allowed_roles}}}.

Deliberately a code-defined matrix, not a DB-driven permissions engine -- ALFR3D is a
solo-household system today, not a hosted multi-tenant product yet. If/when per-resource
sharing is needed later (e.g. "guest can control only the living room lights"), migrate to real
roles/permissions/role_permissions/user_roles tables; require_permission()'s *interface* in
dependencies.py shouldn't need to change, only PERMISSIONS' lookup implementation.

Role model: "guest" gets no write grants anywhere -- identical to an unauthenticated caller, by
design (see todo/todo_auth_rbac.md's locked decision), so it's simply never listed in any
allowed-roles set below rather than special-cased.

`user_types` has two more legacy rows beyond technoking/resident/guest: "owner" (id=4) and
"alfr3d" (id=5). "owner" is the real assignable admin role going forward -- not yet offered by
PersonnelRoster.jsx/UserModal.jsx (todo/todo_user_management.md), but reachable today via
POST /api/auth/bootstrap's first-run onboarding flow (todo/todo_onboarding_first_user.md), which
deliberately creates "owner" accounts rather than "technoking" ones since technoking is an
Athos-only backdoor never assignable via any UI -- treated as a technoking-equivalent alias below
so an owner account gets full admin grants without literally being the backdoor role. "alfr3d" is
the system's own identity, not a login-capable human account, and gets no grants -- it fails
closed to the same place an unrecognized role would.

A missing resource or action key resolves to an empty allowed-roles set (fail closed): nobody
gets write access to something this matrix doesn't explicitly grant.
"""

_ROLE_ALIASES = {"owner": "technoking"}
_NO_GRANT_TYPES = {"alfr3d"}

_TECHNOKING_ONLY = {"technoking"}
_TECHNOKING_AND_RESIDENT = {"technoking", "resident"}

# Resources where every write action shares the same allowed roles use "*" as a wildcard action
# key. Resources that mix everyday household actions with admin/setup actions override specific
# action names on top of "*".
PERMISSIONS = {
    "context": {"*": _TECHNOKING_AND_RESIDENT},  # launcher-reported surface state
    "devices": {"*": _TECHNOKING_AND_RESIDENT},
    "environment": {"*": _TECHNOKING_ONLY},
    "integrations": {"*": _TECHNOKING_ONLY},
    "iot": {
        "*": _TECHNOKING_ONLY,  # config/sync/discover/accept/remove/link/set_provider
        "control": _TECHNOKING_AND_RESIDENT,
    },
    "music": {
        "*": _TECHNOKING_AND_RESIDENT,  # playback/cast/history/speaker-groups
        "auth": _TECHNOKING_ONLY,  # stores the Spotify integration's client credentials
    },
    "personality": {
        "*": _TECHNOKING_ONLY,
        "update_context": _TECHNOKING_AND_RESIDENT,
    },
    "quips": {"*": _TECHNOKING_AND_RESIDENT},
    "routines": {"*": _TECHNOKING_AND_RESIDENT},
    "stream": {"*": _TECHNOKING_AND_RESIDENT},
    "system": {"*": _TECHNOKING_ONLY},
    "users": {"*": _TECHNOKING_ONLY},
}


def effective_role(user_type):
    """Resolve a raw user_types value to the role this matrix understands. Returns None for
    types that should never get a write grant (fails closed, same as an unrecognized role)."""
    if user_type in _NO_GRANT_TYPES:
        return None
    return _ROLE_ALIASES.get(user_type, user_type)


def is_allowed(resource, action, user_type):
    role = effective_role(user_type)
    if role is None:
        return False
    resource_actions = PERMISSIONS.get(resource, {})
    allowed_roles = resource_actions.get(action, resource_actions.get("*", set()))
    return role in allowed_roles
