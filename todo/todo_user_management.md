# User Management: Owner CRUD on Other Users + Self-Service Profile Editing

## Status: 🟡 Backend + web frontend done 2026-08-24; Launcher (alfr3d_deck) profile screen still open, scoped out of this pass deliberately

## What shipped (2026-08-24)

- **Backend** (`services/service_api/routes/users.py`): `PUT /api/users/{user_id}` now accepts
  either an owner/technoking caller (any user, full field set including `type`) or the caller
  editing their own row (`caller.id == user_id`, restricted field set). `type` is excluded from
  the self-service path unconditionally -- even an owner/technoking editing their *own* row
  through this route can't change their own `type`; that always requires the explicit
  admin-on-someone-else path. Uses `require_auth` + `auth.permissions.is_allowed()` directly
  rather than `require_permission`, since the route now has two different authorization
  outcomes depending on whose row is being edited.
- The `owner`-as-distinct-admin-role prerequisite this todo originally called out as blocking
  turned out to already be shipped: `auth/permissions.py`'s `_ROLE_ALIASES = {"owner":
  "technoking"}` (added in the first-run onboarding work) already makes `owner` get every
  `technoking` grant, including `users`'s. No matrix change was needed.
- 6 new tests in `tests/test_api_service.py` covering: unauthenticated rejection, cross-user
  edit rejection for a non-admin, self-service edit success, `type` silently dropped on a
  self-edit, `type` silently dropped even for an admin editing their own row, and an admin
  successfully changing someone *else's* `type`. Full backend suite 286/286 passing.
- **Frontend**: new `pages/Profile.jsx` -- a "My Profile" page (name/email/about_me only, role
  shown read-only, `type` never sent) reachable by clicking your own name/role in the nav bar
  (`App.jsx`), routed at `/profile`. Reuses `AuthContext`'s `deriveUser()`-sourced `user.id`
  the same way `auth/change-password` does server-side -- there's no way to pass someone else's
  id from this form. `PersonnelRoster.jsx`/`UserModal.jsx` (admin CRUD on other users) were left
  as-is; the backend's existing role gate already covered admin-editing-others correctly, this
  todo only added the missing self-service path. 2 new tests in `pages/Profile.test.jsx`. Full
  frontend suite 82/82 passing, lint clean (0 errors; pre-existing unrelated warnings only),
  `npm run build` succeeds.

## Explicitly deferred (not done in this pass)

- **Launcher (`alfr3d_deck`)**: design sketch item 5 (net-new Settings profile-editing screen) --
  scoped out of this pass on purpose (different codebase/language, sized separately). Still
  needed for parity; nothing in `alfr3d_deck` consumes the new self-service endpoint yet.
- Self-service `DELETE` ("delete my own account") -- sketch item 2, explicitly out of scope,
  session/token-revocation implications not addressed here.
- The three "Open Questions" below the sketch (other-users' profile visibility, email
  re-verification on change, admin-editing-someone-else's `about_me`) -- untouched, still open.

---

## Overview

Owners (technoking) need full CRUD on other users. Individual users need to be able to edit their
own profile. Neither half of this is fully true today: CRUD exists but is purely role-gated with no
concept of "this is my own record," and there is no self-service editing surface anywhere in either
client.

## Current State (confirmed 2026-08-23)

- **Backend routes** (`services/service_api/routes/users.py`): `GET /api/users` (lines 21-30) is
  fully open, no auth at all. `POST /api/users` (79-111), `PUT /api/users/{user_id}` (114-146),
  `DELETE /api/users/{user_id}` (149-160) are each gated by `require_permission("users", <action>)`.
- **Permission matrix** (`services/service_api/auth/permissions.py:53`): `"users": {"*": _TECHNOKING_ONLY}`
  — every write action is technoking-only. Unlike `devices`/`routines` (which grant
  `_TECHNOKING_AND_RESIDENT`), there is no resident-level grant for `users` at all.
  `"owner"` aliases to `technoking` (line 24) but isn't assignable through any current UI.
- **No self-service concept exists anywhere in the stack.** `require_permission()`
  (`auth/dependencies.py:45-56`) only checks `is_allowed(resource, action, user.type)` — it never
  compares the authenticated caller's id to the `user_id` path param. `update_user`/`delete_user`
  receive the injected `CurrentUser` but never reference its `.id` (users.py:114-146, 149-160). So
  today a technoking can edit/delete any row including their own, but a resident/guest cannot edit
  even *their own* profile — there's no bypass path for "it's me."
- **Models** (`services/service_api/models.py:7-18`): `UserUpdate` exposes `name`, `email`,
  `about_me`, `type` — all freely editable together. No `password` field on either model (password
  changes go through the separate `auth/change-password` / `admin-reset-password` endpoints from
  `todo_auth_rbac.md` Phase 5, not this CRUD surface). Notably, **`type` is part of the same update
  payload as the profile fields** — a naive self-edit endpoint that just relaxes the permission
  check would let a user promote themselves to technoking by editing their own `type`.
- **Frontend**: `PersonnelRoster.jsx` (admin roster/CRUD grid) + `UserModal.jsx` (edit dialog:
  `name`, `type` select, `email`, `about_me`, plus a delete button) are the only user-editing UI
  that exists, and both are purely admin-facing — reachable as a full roster table, not scoped to
  "my own record." No `Profile`/`Account`/"my settings" component exists anywhere in
  `services/service_frontend`. `AuthContext.jsx` (lines 6-10, 40-45) already derives `user.id`/
  `user.role` client-side from the JWT via `deriveUser()`, so the data needed to build a "this is
  me" view already reaches the frontend — nothing currently consumes it for that purpose.
- **Launcher (`alfr3d_deck`)**: only auth exists (`Alfr3dAuthState.kt`, `Alfr3dAuthStore.kt`) — no
  profile-editing UI at all, confirmed by grep.

**Decided (2026-08-23):**
- `type` is excluded from the self-service update path entirely — a user can never change their
  own `type` via `PUT /api/users/{user_id}`, full stop.
- Only admin/owner can edit `type` for *other* users. "Owner" is the real assignable admin role
  for everyone except Athos — `technoking` is a backdoor role reserved for Athos (the "father of
  ALFR3D") alone, not a role any household member is ever assigned or can assign. This means the
  permission matrix's current `_TECHNOKING_ONLY` gate on `users`'s write actions
  (`permissions.py:53`) needs to become "technoking OR owner" for admin-on-other-user actions —
  today `owner` only *aliases* to `technoking` (permissions.py:24) rather than being a distinct
  grantable role in the matrix, so this needs the matrix (and `user_types` seed data, currently
  `1=technoking, 2=resident, 3=guest` per `todo_auth_rbac.md` §Current-state) to actually
  distinguish `owner` as its own assignable, non-backdoor admin role. **Full role set going
  forward: `technoking` (Athos-only backdoor, unassignable via any UI), `owner` (real household
  admin — full CRUD on other users), `resident`, `guest`.**

## Design (sketch — needs scoping pass before implementation)

1. **Backend**: add a self-service path alongside the existing owner/technoking-only path on
   `PUT /api/users/{user_id}` — e.g. allow the request through if either
   `is_allowed("users", "update", caller.type)` (today's check, to be widened to cover `owner`)
   **or** `caller.id == user_id`, and in the self-service case **exclude `type` from what's
   writable** (and probably `email` if it's ever used for verification/OTP per
   `todo_onboarding_first_user.md` — decide whether email changes need re-verification). Likely
   cleanest as two effective code paths sharing one route: full-field update (including `type`)
   for owner/technoking-on-anyone, restricted-field update (never `type`) for self.
2. **Backend**: decide whether `DELETE` ever gets a self-service path ("delete my own account") —
   probably out of scope initially; deleting your own account while signed in has UX/session
   implications (revoke tokens, etc.) worth scoping separately if wanted at all.
3. ~~Frontend — admin side: role-gate double-check~~ — done 2026-08-24 in
   `todo_household_admin_ui.md` (`PersonnelRoster.jsx`/`UserModal.jsx` now hide Add/Edit/Delete/
   Reset Password/`type` from non-owner/technoking viewers; roster stays visible read-only).
4. **Frontend — self-service side**: net-new "My Profile" surface (nav entry or a section under
   the existing user menu) that reuses `UserModal.jsx`'s field set minus `type`, calling the same
   `PUT /api/users/{user_id}` with the caller's own id from `AuthContext`'s `deriveUser()`.
5. **Launcher**: net-new profile-editing UI in Settings (alongside the existing `AuthSection()`)
   calling the same restricted self-service update — currently nothing there to build on besides
   the login screen.

## Open Questions

- ~~Should residents/guests get any visibility into *other* users' profiles (read-only)~~ —
  resolved 2026-08-24 in `todo_household_admin_ui.md`: read-only. Non-admins see the roster cards,
  just none of the write controls.
- Whether email changes on your own profile should require re-verification once
  `todo_onboarding_first_user.md`'s email OTP capability exists, or whether that's overkill for a
  household-trust-model app.
- Whether `about_me` should be excludable from technoking's edit-someone-else's-profile path (an
  admin overwriting another resident's own bio text feels different from an admin managing
  role/account state) — low priority, worth a glance during implementation.

## Related

- `todo_auth_rbac.md` (this directory) — the permission matrix and `require_permission` dependency
  this todo extends with a per-resource-instance ownership check; also owns password
  change/reset, which this todo's profile editing does not touch.
- `todo_onboarding_first_user.md` (this directory) — the claimed-account/OTP flow this todo's
  self-service editing sits downstream of (a user must exist and be claimed before they have a
  profile to edit).
