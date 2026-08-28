-- Migration 024: Cross-surface continuity card -- routines.updated_at
--
-- Gives "last-edited routine" for free: MySQL bumps this on any UPDATE routines ... with no
-- application-code changes to the existing routine-editing routes. Read by
-- alfr3ddaemon.check_cross_surface_continuity(). See todo/todo_cross_surface_continuity.md.

ALTER TABLE `routines`
  ADD COLUMN `updated_at` TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP;
