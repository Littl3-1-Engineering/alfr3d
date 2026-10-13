-- Migration 049 (2026-10-12): per-user UI theme, shared by the web frontend and alfr3d_deck.
--
-- The theme a person picks on one surface should carry to the other (todo/todo_theme_sync_deck.md).
-- `ui_theme` holds a shared theme id ('dark', 'amber', 'light', 'matrix', 'graphite'); NULL means
-- the person never chose one, so each surface keeps its own default. Validation lives in
-- routes/users.py (UI_THEMES), not in the schema, so a new theme needs no migration.
ALTER TABLE `user` ADD COLUMN `ui_theme` VARCHAR(32) NULL DEFAULT NULL AFTER `title`;
