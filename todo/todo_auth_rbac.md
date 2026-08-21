# Plan: Authentication + RBAC for ALFR3D backend

## Status: 🔲 TODO (not started — planning only)

## Goal
Unauthenticated clients (webapp and Nexus Launcher alike) get **read-only** access. Authenticated users get **write access gated by an ACL/role check** per resource/action. This is a prerequisite for launching ALFR3D as a multi-user/hosted product (see the monetization plan's Path C — ALFR3D Cloud — which currently just says "accounts/auth" as an unscoped Phase 3 line item; this doc is that design).

## Current state (verified in code, 2026-08-20)
There is currently **no authentication or authorization at all** — every API route is fully open.

- **`user` table** — `setup/createTables.sql:17-29`. Columns: `id`, `username`, `email`, `password_hash` (column exists but nothing in the codebase reads or writes it), `about_me`, `state` (FK), `last_online`, `created_at`, `environment_id` (FK), `type` (FK → `user_types`).
- **`user_types`** — `setup/createTables.sql:82-86`. Seeded values `1=technoking, 2=resident, 3=guest`. Purely descriptive today — nothing branches on it for permissions.
- **API models** — `services/service_api/models.py:7-18` (`UserCreate`/`UserUpdate`) only expose `name`, `type`, `email`, `about_me`. Password is not part of the API surface at all yet.
- **User routes/queries** — `services/service_api/routes/users.py`, `_fetch_users()` in `services/service_api/dependencies.py:268-296`.
- **No login endpoint, no session/JWT/cookie handling, no auth middleware.** `services/service_api/app.py` only registers `CORSMiddleware` (line 190) and routers (lines 199-214) — no `Depends()`-based auth anywhere.
- **No roles/permissions/ACL logic anywhere** — `user_types` is the only role-shaped thing and it's unenforced.
- **DB access is raw `pymysql`**, no ORM — matters for how any auth middleware fetches user rows.
- Migrations: Alembic under `setup/migrations/versions/` (0001–0019) plus parallel raw SQL in `setup/migration_*.sql`; schema-of-record is `setup/createTables.sql`.

## Design

### 1. Auth mechanism: JWT, not server sessions
Both clients (React SPA webapp *and* the Nexus Launcher Android app) talk to the same REST API, so a stateless bearer-token scheme is simpler than cookie sessions (which the launcher can't use naturally as a native client).

- `POST /api/auth/login` — username/email + password → short-lived **access token** (JWT, ~15 min) + longer-lived **refresh token** (opaque, stored server-side so it's revocable).
- New table `refresh_tokens` (user_id FK, token hash, issued_at, expires_at, revoked_at) — needed because pure stateless JWTs can't be revoked (e.g. on logout, password change, or a stolen launcher device).
- `POST /api/auth/refresh` — trade a valid refresh token for a new access token.
- `POST /api/auth/logout` — revoke the refresh token.
- Passwords hashed with bcrypt or argon2 into the **existing but currently-unused** `password_hash` column — no schema change needed there, just wiring it up.
- Since every existing `user` row has no password set today, rollout needs a **"set your password" / invite flow** for existing users rather than assuming password_hash is already populated (see Rollout, Phase 0 below).

### 2. Read vs. write split (the "unauthenticated = view-only" rule)
- All `GET` routes stay open — anonymous callers (or any authenticated user with no explicit grant) can view.
- All `POST`/`PUT`/`PATCH`/`DELETE` routes require both authentication **and** a permission check for that resource+action. Enforced via a FastAPI dependency, not per-route ad hoc code, so it can't be forgotten on a new route:
  - `get_current_user_optional` — parses the bearer token if present, returns `None` on missing/invalid token (used on read routes if any read ever needs to vary by identity, e.g. a user's own profile).
  - `require_auth` — 401s if no valid token.
  - `require_permission(resource: str, action: str)` — 401 if unauthenticated, 403 if authenticated but lacking the grant; wraps `require_auth`.

### 3. ACL model — start simple, leave room to grow
Given this is currently a solo-household system (not yet a hosted multi-tenant product), recommend starting with a **code-defined permission matrix** keyed off role, rather than a fully dynamic DB-driven permissions engine — less to build, still correct, and it's a natural stepping stone to a DB-driven version later if ALFR3D Cloud needs per-device sharing grants.

- Promote `user_types` from decorative to enforced: `technoking` (full admin — user management, integrations, system config), `resident` (read/write on household resources: devices, routines, calendar, music — not user management or integrations), `guest` (read-only, same as unauthenticated, or a narrow allowlist like "can trigger routines but not edit them" — worth confirming with the user before assuming).
- Define the matrix once, e.g. `services/service_api/auth/permissions.py`: `{resource: {action: {allowed_roles}}}` for resources `devices`, `routines`, `integrations`, `users`, `calendar`, `music`, etc.
- **Escape hatch for later**: if/when per-resource sharing is needed (e.g. "guest can control only the living room lights"), migrate to real `roles`/`permissions`/`role_permissions`/`user_roles` tables — the `require_permission` dependency's *interface* shouldn't need to change, only its implementation, so this isn't a rewrite later.

### 4. Client integration
- **Webapp (React SPA)**: add a login page/form; store the access token in memory (not localStorage, to reduce XSS token-theft surface) and use the refresh token via an httpOnly cookie or silent-refresh flow; hide/disable write UI (edit buttons, forms, delete actions) when unauthenticated, matching the backend's enforcement so the UI isn't lying about what it can do.
- **Nexus Launcher (Android, `alfr3d_deck`)**: add a login screen; store tokens in Android Keystore-backed encrypted storage (same pattern the launcher already uses for Play Billing entitlement state, per [[project-alfr3d-monetization-plan]]); attach `Authorization: Bearer <token>` to all mutating calls; when logged out, the launcher's ALFR3D cards/controls should render in a view-only state rather than erroring — this needs a companion todo in `alfr3d_deck/todo/` once this plan is accepted, per [[project-alfr3d-deck-companion]]'s cross-repo convention.

### 5. Rollout phasing
- **Phase 0 — migration prep**: since no `user` row has a password today, ship a one-time "claim your account" flow (e.g. a CLI script or an admin-only unauthenticated-but-locked-down bootstrap endpoint) so existing household members can set a password before write routes start requiring auth. Decide the default role for existing rows (likely `resident`, with the household owner promoted to `technoking` manually).
- **Phase 1 — auth infra**: `user` password wiring, JWT issuance, `refresh_tokens` table, login/refresh/logout endpoints.
- **Phase 2 — permission middleware**: `require_permission` dependency + the code-defined matrix; apply to all write routes across `services/service_api/routes/*`. This is the biggest-surface-area phase — every existing write route needs the dependency added and its resource/action classified.
- **Phase 3 — webapp**: login UI, token handling, view-only mode for anonymous/under-permissioned users.
- **Phase 4 — launcher**: login screen, token storage, view-only mode (tracked as a companion `alfr3d_deck` todo).
- **Phase 5 — hardening**: login rate-limiting, no username-enumeration on failed login, password reset flow, audit that no write route was missed (grep for all `@router.post|put|patch|delete` and confirm each has `require_permission`).

### 6. Open question: user model — add `gender`?
No `gender` column exists today, and nothing in the codebase (personality engine, TTS, etc.) currently references gender or pronouns. Worth deciding *why* before adding it — the likely use case here is personalization (e.g. TTS voice selection per user, or the personality/LLM layer addressing a user correctly), not demographic data collection. If pursued: make it optional/nullable, free-text or a small open enum rather than a fixed binary set, and treat it as a per-user preference the user sets for themselves (not something an admin sets for other household members). This is independent of the RBAC work above but touches the same `user` table/API models, so it's a natural companion change to bundle into the Phase 1 migration if the user decides to move forward — flagged here rather than actioned.

## Related
- [[project-alfr3d-monetization-plan]] — ALFR3D Cloud (Path C) Phase 3 currently just lists "accounts/auth" unscoped; this doc is the scoping.
- See `todo_multiuser_integrations.md` in this same directory — multi-user calendar/email support depends on this auth/user-identity work landing first (need a real logged-in user to attribute an integration to).
- `todo_cloud_relay.md` (this directory, added 2026-08-21) — Cloud subscriber/billing identity, a deliberately separate system from the household RBAC users here; that doc's Design §2 discusses whether the two logins should ever converge.
