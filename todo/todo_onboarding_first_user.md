# First-Run Onboarding: Detect No Password-Set User, Generate or Claim the First Account

## Status: ✅ Complete -- backend + webapp + launcher UI shipped 2026-08-24. The planned email-OTP
follow-up (item 3 below) was decided against 2026-08-26 -- see `todo_email_service.md`'s Decision
section: `claim`/`bootstrap` already require physical-device or local-network access, so an
emailed code adds no real security at that step. Nothing else in this doc is blocked by that.

## Overview

[[project-alfr3d-launch-critical-security]] shipped password auth + RBAC (`todo_auth_rbac.md`), but
there is still no guided path from "fresh install, nobody has ever set a password" to "a household
member is signed in." Today the only entry point is `POST /api/auth/claim`, which requires already
knowing a username to claim — there's no detection of "no resident has a password set yet" and no
UI that surfaces the claim step, whether that's generating a brand-new first user or letting an
existing seeded resident claim their row.

## Current State (confirmed 2026-08-23, updated 2026-08-24)

- Backend: `POST /api/auth/claim` (`services/service_api/auth/routes.py`, scoped in
  `todo_auth_rbac.md` Phase 0) already exists and only succeeds against a user whose
  `password_hash` is still NULL/empty — the core safety property this onboarding flow needs is
  already there. It's rate-limited (10 attempts/15min per IP, added in Phase 5) and returns a
  generic error on both "user not found" and "already claimed" (no enumeration leak).
- Backend: **shipped 2026-08-24** — `GET /api/auth/setup-status` (unauthenticated, reports
  `empty`/`unclaimed`/`claimed` plus the claimable-user list) and `POST /api/auth/bootstrap`
  (unauthenticated, rate-limited 10/15min, creates and claims a brand-new **owner** account in one
  call -- deliberately `owner`, not `technoking`, per [[alfr3d-role-model]]) both exist in
  `services/service_api/auth/routes.py` with test coverage in `tests/test_auth.py`.
- Webapp: **shipped 2026-08-24** — `OnboardingModal.jsx` shows instead of `LoginModal` whenever
  `setup-status` reports non-`claimed`, offering claim-existing or create-new (calls `bootstrap`)
  paths; wired into `App.jsx`/`AuthContext.jsx`/`authStore.js`. Test coverage in
  `OnboardingModal.test.jsx`.
- Launcher (`alfr3d_deck`): **shipped 2026-08-24** — `Alfr3dClient`/`HttpAlfr3dClient` gained
  `getSetupStatus`/`claim`/`bootstrap` (mirroring the webapp's `authStore.js`), `Alfr3d` object
  gained matching `claim`/`bootstrap`/`checkSetupStatus` wrappers that persist tokens the same way
  `login` does, and a new `OnboardingSection.kt` composable renders the claim/create card. Settings
  hoists the `setup-status` check into a new `Alfr3dAccountSection` wrapper so the onboarding card
  and the normal `AuthSection` sign-in form are mutually exclusive (never both shown at once,
  matching the webapp's `LoginModal`/`OnboardingModal` split) rather than stacked.
- Email OTP follow-up: decided against 2026-08-26 (see `todo_email_service.md`'s Decision
  section) -- not just deferred, not going to be built. Solo-owner lockout recovery (a real, if
  narrow, gap the OTP idea was partly reaching for) is instead covered by
  `setup/reset_owner_password.py`, a direct-DB script gated on host access rather than email.

## Design (sketch — needs scoping pass before implementation)

1. **Detection endpoint**: something like `GET /api/auth/setup-status` (unauthenticated, read-only)
   returning whether *any* `user` row has a non-NULL `password_hash` yet. If none do, both clients
   know to route into onboarding instead of (or in addition to) the normal login screen.
2. **Onboarding flow** when no user is claimed:
   - Offer to claim one of the existing seeded residents (list `user_types` = resident/technoking
     rows by name, same data `claim` already keys off of), **or**
   - Generate a brand-new first user (owner role, since someone must hold full admin -- deliberately
     `owner`, not `technoking`: per [[alfr3d-role-model]], technoking is an Athos-only backdoor
     never assignable via any UI) if the household prefers not to reuse a pre-seeded row.
3. **Follow-up: email OTP — decided against, 2026-08-26.** Originally scoped as blocked on
   `todo_email_service.md`'s SMTP/email capability; once that capability actually got built and
   examined against this exact use case, it turned out to add no real security here — `claim`/
   `bootstrap` already require physical-device or local-network access, the same trust boundary an
   emailed code would be trying to add on top of. See `todo_email_service.md`'s Decision section
   for the full reasoning and what was built instead (`setup/reset_owner_password.py`, for the one
   real gap: solo-owner lockout with no other admin to help).
4. Where does the "does anyone have a password" check run? Likely both: webapp shows an onboarding
   screen instead of the normal login modal on first load if `setup-status` says nobody's claimed;
   launcher does the equivalent inside `AuthSection()`/a new onboarding surface in Settings.

## Open Questions

- Should the generate-a-new-first-user path bypass `claim` entirely (a distinct
  `POST /api/auth/bootstrap` that creates a row *and* sets its password in one call), or should it
  still create a plain unclaimed `user` row first and then reuse `claim` uniformly for both paths?
  Reusing `claim` for both keeps one code path but means "generate a new user" is really two calls.
- Should `setup-status` distinguish "zero users exist at all" (fresh DB, nothing seeded) from "users
  exist but none are claimed" (normal post-`createTables.sql` seed state)? The onboarding copy
  probably differs ("welcome, let's create your account" vs. "residents are already set up, claim
  yours").
- ~~Scope and vendor choice for the email OTP step~~ — resolved 2026-08-26: not building it. See
  `todo_email_service.md`.

## Related

- `todo_auth_rbac.md` (this directory) — the auth/RBAC system this onboarding flow sits on top of;
  `claim`'s existing safety guarantees (NULL-password-only, rate-limited, non-enumerating) are
  reused here, not rebuilt.
- `alfr3d_deck/todo/todo_auth_rbac.md` — launcher-side login already shipped; this doc's launcher
  work is net-new UI in the same area (Settings), not a rework of the existing login screen.
- `todo_email_service.md` (this directory) — the email-OTP follow-up idea originally tracked
  here was decided against there; see its Decision section for the reasoning.
- `setup/reset_owner_password.py` — what actually covers the one real gap (solo-owner lockout)
  the email-OTP idea was partly reaching for.
