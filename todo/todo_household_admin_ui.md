# Todo: Owner-Administers-Household, Fully Surfaced in the Web UI

## Status: ✅ Shipped 2026-08-24 -- password-reset UI + role-gating both done and on-device verified. Only item 4 (Launcher parity, explicitly v2/out-of-scope) remains, tracked as a separate open decision below.

## Shipped 2026-08-24: Reset Password UI + role-gating

Both remaining design-sketch items (#1 and #2) are done:

- **`UserModal.jsx`** now has a "Reset Password" (key icon) action next to Edit/Delete, visible
  only when `isAdmin` is true. Clicking it opens an inline confirm panel (no native `confirm()` --
  deliberately avoided so the flow stays fully in-page) warning that the target's sessions will be
  signed out. Confirming generates a 16-character password client-side (unambiguous charset --
  no `0/O/1/l/I`, via `crypto.getRandomValues`), calls `POST /api/auth/admin-reset-password`, and
  on success displays the password once in a copyable box with the "share this directly, can't be
  emailed yet" messaging the design sketch called for. Failure shows an inline error and re-offers
  the confirm panel rather than losing the attempt.
- **Role-gating**: `PersonnelRoster.jsx` computes `isAdmin` from `useAuth()`'s `user.role` (`owner`
  or `technoking`) and hides "Add User" entirely for anyone else, including signed-out visitors.
  `UserModal.jsx` takes `isAdmin` as a prop and hides Edit/Reset Password/Delete (and the `type`
  selector, since it's only reachable via Edit) the same way. Resolved the "hidden vs read-only"
  open question as **read-only**: non-admins still see the roster cards, just none of the mutating
  controls -- consistent with `GET /api/users` already being open.
- **Verified two ways**: 9 new unit tests (`PersonnelRoster.test.jsx`, `UserModal.test.jsx`) cover
  Add User visibility across owner/technoking/resident/signed-out, and the full reset-password
  flow (confirm -> generate -> call -> display, plus the failure and cancel paths) with a mocked
  API. Separately, live-verified against the real deployed stack: rebuilt and redeployed
  `service-frontend` (`docker compose build/up service-frontend`), signed in as a real `owner`
  account, created a throwaway `ZZ-Claude-Test-Delete-Me` guest user, reset its password end-to-end
  (real backend call, real generated password displayed and copied), then deleted it -- no real
  household account was touched. Note for next time: the app's real entry point is nginx on `:80`
  (proxies `/api` to the backend); `service-frontend`'s own `:8000` is a bare static file server
  with no `/api` proxy and will 200 with the SPA's `index.html` for any API path, which looks like
  a working page but silently breaks every fetch (`Unexpected token '<'` JSON-parse errors) --
  cost real time mid-session before catching it.

## Overview

## Overview

`todo_user_management.md` shipped the *self-service* half of user management (a resident editing
their own profile) on 2026-08-24. This todo covers the other half: making sure an **owner** (or the
`technoking` backdoor) can actually administer every other household member's account entirely
through the UI, with no drop to `curl`/direct API calls, and with no dead-end controls shown to
users who aren't allowed to use them.

Most of the backend for this already exists and is confirmed working. This is primarily a frontend
gap-filling + correctness pass, not new backend design, except for one missing endpoint call site
(password reset).

## Current State (confirmed 2026-08-24)

- **Create/edit/delete other users — done, works today.** `PersonnelRoster.jsx` (rendered on
  `pages/Domain.jsx:106`) has an "Add User" button (`POST /api/users`) and, via `UserModal.jsx`,
  edit (`PUT /api/users/{id}`, including changing `name`/`email`/`about_me`/`type`) and delete
  (`DELETE /api/users/{id}`) for any other user. Backend gates all three on
  `require_permission("users")` → `_TECHNOKING_ONLY` in the matrix, and `owner` aliases to
  `technoking` (`auth/permissions.py:27`), so an owner passes today's checks.
- **Password reset for another user — backend exists, zero UI.** `POST
  /api/auth/admin-reset-password` (`services/service_api/auth/routes.py:275`) takes `{user_id,
  new_password}`, is gated the same way as the CRUD routes above, overwrites the target's
  `password_hash`, and revokes all of that user's existing refresh tokens. Grepped the entire
  frontend (`services/service_frontend/src`) — no call site anywhere. Today an owner can only do
  this via a direct API call (curl/Postman), not through the app.
- **No email delivery** for the new password — `todo_email_service.md` (not started) is the
  eventual fix; until then this stays an "admin sets it and tells the person out-of-band" flow,
  same trust model the backend route's own docstring describes.
- **No role-gating in the UI itself — real gap.** Grepped `PersonnelRoster.jsx` and
  `pages/Domain.jsx`: neither checks the caller's role before rendering. A resident or guest who
  navigates to the Domain page today sees the full admin roster — Add User, Edit, the `type`
  dropdown, Delete — and every one of those actions will 403 from the backend when clicked. The
  backend enforcement is correct; the UI just shows controls that always fail for non-admins
  instead of hiding them. `todo_user_management.md`'s design sketch item 3 flagged this exact gap
  ("likely just needs a role-gate double-check ... matching the backend's real enforcement") and
  it's still open.
- **Launcher (alfr3d_deck): no admin UI at all**, confirmed by grep in the prior session — only
  login/auth screens exist. Out of scope question below (this todo's own self-service counterpart,
  the Settings profile screen, is tracked separately in `todo_user_management.md`'s "Explicitly
  deferred" section and is about editing *your own* row, not administering others').

## Fixed 2026-08-24: `owner` is now a selectable type

Confirmed the backend never hardcoded the three known role names -- both `create_user` and
`update_user` (`services/service_api/routes/users.py`) resolve `type` by looking it up in the
`user_types` table (`SELECT id FROM user_types WHERE type = %s`), so once a row exists there,
assigning it via the API needs no other backend change. Two real gaps, both fixed:

- **Existing databases were missing the `owner` row.** `createTables.sql` already seeds it (id 4,
  added alongside `permissions.py`'s `owner`→`technoking` alias), but `0001_baseline`'s Alembic
  migration only runs `createTables.sql` when the `user` table doesn't exist yet -- any database
  migrated *before* that seed row was added never got it and had no other path to it. Added
  `setup/migrations/versions/0024_owner_user_type.py`, which backfills the `owner` row only if
  missing (checks by name, not by hardcoded id, so it's safe regardless of what id the fresh-install
  path happened to assign). Not yet run against a live database in this environment -- no DB
  container is up here; verify with `alembic upgrade head` before/at next deploy. **Run 2026-08-25
  against the live production DB** (`docker compose --profile test run --rm migrate alembic upgrade
  head`, after rebuilding the `migrate` image since it was stale and didn't have 0024 in its build
  context yet) -- confirmed `alembic current` now reports `0024 (head)`. The migration itself
  no-opped (`user_types.owner already present; skipping`) since the row was already backfilled
  manually during the 2026-08-24 live-verification pass; this run just formally records 0024 in the
  migration chain so future `alembic upgrade head` runs don't skip it on a fresh install.
- **Frontend never offered `owner` as an option.** Added it to both role `<select>` dropdowns:
  `PersonnelRoster.jsx`'s "Add User" form and `UserModal.jsx`'s edit view. `eslint`/`flake8`/`black`
  clean on all three changed files.

## Design sketch

1. ~~Add a "Reset Password" action to `UserModal.jsx`~~ — done, see "Shipped 2026-08-24" above.
2. ~~Role-gate `PersonnelRoster.jsx`/`UserModal.jsx` end to end~~ — done, see "Shipped 2026-08-24"
   above. Resolved as read-only for non-admins, not hidden.
3. ~~Verify the `owner` role is actually reachable end to end~~ — done, see "Fixed 2026-08-24" above.
4. **Launcher parity — explicitly a v2 decision, not v1 scope.** Confirm with the user whether
   owner-administers-household needs to exist on `alfr3d_deck` at all, or whether the web app is
   the sole admin surface (phones/tablets can just open the web app) and the launcher only ever
   needs the self-service profile screen already tracked in `todo_user_management.md`.

## Open Questions

- ~~New-password UX~~ — resolved: generate-and-display, per the user's explicit choice 2026-08-24.
- ~~Roster visibility for non-admins~~ — resolved: read-only, per the user's explicit choice
  2026-08-24. `todo_user_management.md`'s copy of the same open question should point here now.
- Item 4 above (Launcher parity) remains the only genuinely open question in this doc.

## Related

- `todo_user_management.md` (this directory) — shipped the self-service half this todo's admin
  half complements; also the origin of the role-gating gap and the `owner`-role open question.
- `todo_auth_rbac.md` (this directory) — owns `admin-reset-password`, the permission matrix, and
  the `user_types` seed data referenced in design item 3.
- `todo_email_service.md` (this directory) — the eventual replacement for "admin tells the user
  their new password out-of-band" once transactional email exists.
- [[alfr3d-role-model]] — `owner`/`technoking`/`resident`/`guest` role semantics this todo assumes.
