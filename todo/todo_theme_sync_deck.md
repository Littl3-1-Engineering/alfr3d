# Sync themes between Alfr3d (web frontend) and Alfr3d Deck

## Status: built 2026-10-12, committed (`55ab354e`); web-to-Deck and Deck-to-web both verified working by Athos 2026-10-13 (added 2026-10-03); cross-repo, mirrored in `alfr3d_deck/todo/`

## What was built (2026-10-12)

- **Source of truth:** `user.ui_theme` (migration 049 / alembic 0054), a shared id: `dark`, `amber`,
  `light`, `matrix`, `graphite` (the web `themes.js` keys). `GET/PUT /api/users/me/theme`, any
  signed-in user for their own row (no role gate, like profile edits); unknown ids give 422. A PUT
  broadcasts `theme` on the websocket with the user id. Tests: `tests/test_user_theme.py`.
- **Sync rule:** last write wins per user. No per-device override on the web; the Deck has a
  "Sync theme with ALFR3D" toggle (default on).
- **Web:** `components/ThemeSync.jsx` (mounted in `App.jsx`): on sign-in a saved server theme
  replaces the local one, otherwise the local one seeds the server; local changes are PUT; a
  `theme` broadcast for this user applies live. Signed out stays local. 5 vitest tests.
- **Deck:** `settings/ThemeSync.kt` maps Deep Cyan/`dark`, Tactical Amber/`amber`, Light/`light`.
  Wallpaper and Custom stay device-local; `matrix`/`graphite` are ignored; a Pro-locked `amber`
  is not applied for a non-Pro user. Pull runs in the 30-min background sync; a user change pushes
  immediately. `decide()` is unit-tested (`ThemeSyncTest`).

## Known gaps

- The Deck has no live channel: web changes arrive on the next sync, not instantly.
- The "last synced" id is in memory only, so a push that failed offline is dropped after a restart.
- Not run on a device or against the live backend; the interaction with
  `todo_device_controls_visual_refresh.md` is untouched.
- Notion Timeline and README not yet updated (do it when this ships).

Ask: the theme chosen on one surface should carry to the other.

## Notes / decisions to make

- Inventory both theme definitions (web frontend CSS/Tailwind tokens vs Deck Compose themes) and map
  them to one shared theme id + token set; decide the source of truth (backend-stored per-user preference is the natural one).
- Sync direction/conflicts: last-write-wins per user, or per-device override with a "sync themes" toggle?
- Needs a backend preference endpoint (RBAC-gated write, see `todo_auth_rbac.md`) and live propagation
  (event stream/WebSocket) so an open surface updates without reload.
- Themes with no counterpart on the other surface need a fallback.
- Interacts with cyan-over-magenta work in `alfr3d_deck/todo/todo_device_controls_visual_refresh.md`.
