# Sync themes between Alfr3d (web frontend) and Alfr3d Deck

## Status: not started (added 2026-10-03); cross-repo, mirrored in `alfr3d_deck/todo/`

Ask: the theme chosen on one surface should carry to the other.

## Notes / decisions to make

- Inventory both theme definitions (web frontend CSS/Tailwind tokens vs Deck Compose themes) and map
  them to one shared theme id + token set; decide the source of truth (backend-stored per-user preference is the natural one).
- Sync direction/conflicts: last-write-wins per user, or per-device override with a "sync themes" toggle?
- Needs a backend preference endpoint (RBAC-gated write, see `todo_auth_rbac.md`) and live propagation
  (event stream/WebSocket) so an open surface updates without reload.
- Themes with no counterpart on the other surface need a fallback.
- Interacts with cyan-over-magenta work in `alfr3d_deck/todo/todo_device_controls_visual_refresh.md`.
