# Plan: Multi-user calendar/email integrations

## Status: 🔲 TODO (not started — open design question)

## The question
If multiple household members each connect their own calendar and/or email, how does ALFR3D know whose event/email it's looking at — e.g. so a notification can correctly say "another email arrived for Sarah" instead of just "you have new mail"? Today it can't, because integrations aren't attributed to a user at all (see Current state).

## Current state (verified in code, 2026-08-20)
Both calendar and email (Gmail) integration exist, but both are **single global/owner-account only** — there is no concept of "whose" integration it is.

- `integrations_tokens` table (`setup/createTables.sql:208-217`) — one row **per `integration_type`**, enforced by a `UNIQUE (integration_type)` constraint (`unique_integration`). Stores OAuth `access_token`/`refresh_token`/`expires_at`. **No `user_id` column** — structurally cannot hold two people's Google accounts at once.
- `calendar_events` table (`setup/createTables.sql:192-201`) — synced events, also **no `user_id` column**.
- OAuth setup: `setup/authorize_google.py` — a CLI flow that writes a single row into `integrations_tokens` (type `google`, `gmail`, or `calendar`).
- Calendar sync: `services/service_daemon/utils/calendar_utils.py:49` — queries `integrations_tokens WHERE integration_type = 'google'`, no per-user filtering (there's only ever one row to find).
- Gmail sync: `services/service_daemon/utils/gmail_utils.py:65` — same single-row pattern.
- Sync trigger endpoints: `services/service_api/routes/integrations.py` (`/api/integrations/calendar/sync`, `/api/integrations/gmail/sync`, `/api/integrations/status`) — these kick off syncs, not scoped to a user.
- Daemon-side consumers: `services/service_daemon/alfr3ddaemon.py`, `services/service_daemon/utils/focus_utils.py`.

## Design sketch
This depends on `todo_auth_rbac.md` landing first — attributing an integration to "a user" requires there to actually be a real, authenticated user identity to attribute it to, not just the decorative `user` rows that exist today.

1. **Schema**: add `user_id` (FK → `user.id`) to both `integrations_tokens` and `calendar_events`. Drop or relax `integrations_tokens`' `unique_integration` constraint — it needs to become `UNIQUE (user_id, integration_type)` so each person can have their own `google`/`gmail`/`calendar` row instead of one shared row for the whole household.
2. **OAuth connect flow**: replace the CLI-only `setup/authorize_google.py` bootstrap with a per-user "Connect your Google account" flow reachable from the webapp/launcher while logged in (per the auth work), writing the resulting tokens against `user_id = current_user.id`.
3. **Sync**: `calendar_utils.py` / `gmail_utils.py` need to iterate over *all* connected accounts (one sync pass per `integrations_tokens` row) instead of assuming a single row, and tag whatever they produce (events, new-mail notices) with the owning `user_id`.
4. **Notification/attribution surface**: once events/mail are tagged with `user_id`, the personality/notification layer (routines' `speak`/`email` actions, situational-awareness cards) can render "another email arrived for Sarah" by joining through to `user.username`/`name` instead of the current implicit "it's the household's one inbox" framing. Worth checking `todo/personality.md` and `services/service_daemon/utils/focus_utils.py` for where notification text is currently composed, since that's where the per-user phrasing would need to be threaded through.
5. **Privacy/ACL interaction**: decide whether one user can see another user's calendar/email events at all, or only their own — this is itself an ACL question that should reuse the permission model from `todo_auth_rbac.md` rather than inventing a separate rule (e.g. a `calendar` resource with `action=read` scoped to "own records only" vs. household-wide, depending on role).

## Open questions (not yet decided — flag to the user before implementing)
- Should household members see each other's calendar events by default (shared-household model) or only their own (private-by-default)? This changes both the schema query patterns and the ACL matrix.
- For voice/TTS notifications spoken aloud in a shared space, is it acceptable to announce "Sarah got an email from X" out loud, or should notifications be user-scoped to that person's own device/session (harder — ALFR3D doesn't currently have a per-user "this is my device" concept, which is really the same identity question the Nexus Launcher login work in `todo_auth_rbac.md` would need to answer too).

## Related
- `todo_auth_rbac.md` — prerequisite: real user auth/identity is needed before integrations can be attributed to a user.
- [[project-alfr3d-deck-companion]] — if the launcher needs a "my notifications only" mode, that's a cross-repo feature like the pattern already used for Spotify now-playing/TTS relay.
