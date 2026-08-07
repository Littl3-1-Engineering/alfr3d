-- Migration 015: Environment timezone column
-- Adds timezone offset (in seconds) to the environment table. The code in
-- db_utils.get_env_timezone, calendar_utils, the daemon, speak, and the API
-- has referenced environment.timezone since commit 16a89da but no migration
-- ever created the column.

ALTER TABLE environment
  ADD COLUMN timezone INT NULL DEFAULT 0 AFTER country;
