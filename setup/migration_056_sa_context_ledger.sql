-- Migration 056 (2026-11-19): the context capture ledger, readable by the API.
--
-- `python -m sa.ledger` answers "what do we actually have to learn from" from the Parquet lake:
-- per context feature and per series, whether it is captured, since when, how much of the last 30
-- days it covers, how long its source keeps it, who reads it. The API does not mount the lake
-- (only sa-learner does), so after each nightly silver build sa-learner writes the same answer
-- here, replacing the whole table (about 60 rows), and GET /api/context/ledger reads it.
--
-- Replace-all, not append: it is a snapshot of the lake, and the lake is the source of truth.
-- No retention event and no storage-metrics entry: the table never grows.

CREATE TABLE IF NOT EXISTS `sa_context_ledger` (
  `ledger_key` VARCHAR(255) NOT NULL,        -- feature key, or series key such as esphome:host:name
  `kind` ENUM('feature', 'series') NOT NULL,
  `status` VARCHAR(16) NOT NULL,             -- captured | not_captured | restricted
  `capture_start` DATETIME NULL,             -- first hourly bucket (UTC), NULL when nothing captured
  `last_seen` DATETIME NULL,                 -- newest hourly bucket (UTC)
  `row_count` BIGINT NOT NULL DEFAULT 0,
  `hours_with_data` INT NOT NULL DEFAULT 0,  -- distinct hours with a value in the window
  `coverage` DOUBLE NOT NULL DEFAULT 0,      -- hours_with_data / (window_days * 24)
  `window_days` INT NOT NULL,
  `retention_days` INT NULL,                 -- how long the SOURCE keeps it, NULL = unbounded/derived
  `privacy` VARCHAR(16) NOT NULL,            -- household | owner_opened | restricted
  `readers` JSON NOT NULL,                   -- learners and cards that read it
  `provenance` TEXT NOT NULL,
  `identity_rule` TEXT NULL,                 -- how a series is named (never a row id)
  `note` TEXT NULL,
  `horizon` DATETIME NULL,                   -- the lake's newest bucket when this was computed
  `computed_at` DATETIME NOT NULL,
  PRIMARY KEY (`ledger_key`, `kind`)
);
