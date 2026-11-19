-- Migration 058 (2026-11-19): the layer-3 autonomy policy and its audit log.
--
-- Layer 3 (todo/sa/todo_l3_proposal_policy_contract.md) may propose an action and, only where the
-- owner has granted it, perform it, per action type, scope and context, on a ladder: 0 predict only,
-- 1 suggest, 2 standing permission, 3 act then tell. **Every level defaults to 0**: a row that does
-- not exist means level 0, so these tables start EMPTY and nothing reads them to execute anything in
-- this release (there is no executor yet). Promotion is an owner decision made with the evidence
-- shown; demotion is automatic; both are recorded in the append-only log.
--
-- `scope`/`scope_key` name person and presence-conditioned scopes so they can be added later; only
-- household scope is built and the application refuses the others until the owner asks.
-- Proposals are NOT a table: they are layer-3 rows in `sa_inferences` (kind 'proposal').
-- The kill switch is a row in the existing `config` table (name 'autonomy_kill'), not a new table.

CREATE TABLE IF NOT EXISTS `sa_autonomy_policy` (
  `action_type` VARCHAR(64) NOT NULL,
  `scope` ENUM('household', 'person', 'presence') NOT NULL DEFAULT 'household',
  `scope_key` VARCHAR(64) NOT NULL DEFAULT '',   -- a person id, or a presence-condition key
  `context` VARCHAR(64) NOT NULL DEFAULT '*',    -- '*' = any context
  `level` TINYINT NOT NULL DEFAULT 0,            -- 0..3
  `evidence` JSON NOT NULL,                      -- the counts the owner was shown at promotion
  `granted_by` VARCHAR(64) NULL,                 -- the owner's user id
  `granted_at` DATETIME NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`action_type`, `scope`, `scope_key`, `context`)
);

CREATE TABLE IF NOT EXISTS `sa_autonomy_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `action_type` VARCHAR(64) NOT NULL,
  `scope` VARCHAR(16) NOT NULL,
  `scope_key` VARCHAR(64) NOT NULL,
  `context` VARCHAR(64) NOT NULL,
  `from_level` VARCHAR(16) NOT NULL,             -- a number, or 'any' for the kill switch
  `to_level` VARCHAR(16) NOT NULL,               -- a number, or 'restored' for a reset
  `actor` VARCHAR(64) NOT NULL,                  -- a user id, or 'system' for automatic demotion
  `reason` VARCHAR(255) NOT NULL,
  `evidence` JSON NOT NULL,
  `at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_autonomy_log_type_at` (`action_type`, `at`)
);
