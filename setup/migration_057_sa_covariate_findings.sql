-- Migration 057 (2026-11-19): the discovery screen's findings, readable by the API.
--
-- sa/screen.py (Context learning 4/5, todo/sa/todo_lf10_discovery_screen.md) screens every declared
-- target (sa/targets.py: guests home, empty house, time away, ...) against the context registry's
-- features and lags each night: held-out gain and effect size, or an explicit "insufficient
-- evidence" row with its reason. sa-learner writes the rows here after the learners; the API does
-- not mount the lake, so GET /api/context/findings reads them from here.
--
-- One row per target, candidate feature and lag, per nightly run, KEPT for 90 days (the stage
-- prunes older runs): a relationship that holds for weeks is worth more than one that appears once,
-- and the API reports on how many recent nights a candidate was an `effect`. A re-run of the same
-- night replaces that night's rows. A target with no data still writes one row (feature_key '*')
-- saying why, so every night provably covers every declared target.
--
-- `status` is `effect` only for a candidate that beat the shifted-feature permutation null after
-- multiple-testing correction; everything under a floor or not distinguishable from chance is
-- `insufficient_evidence`, never a result. Findings drive no card and no actuation.

CREATE TABLE IF NOT EXISTS `sa_covariate_findings` (
  `run_date` DATE NOT NULL,                  -- the nightly run this row belongs to
  `target_key` VARCHAR(64) NOT NULL,         -- sa/targets.py key, e.g. guests_home
  `feature_key` VARCHAR(64) NOT NULL,        -- context registry key, or '*' for the whole target
  `lag_hours` INT NOT NULL DEFAULT 0,        -- hours the feature leads the target
  `method` VARCHAR(8) NOT NULL,              -- slope (continuous target) | rates (count, binary)
  `status` ENUM('effect', 'insufficient_evidence', 'not_tested') NOT NULL,
  `reason` VARCHAR(255) NULL,
  `n` INT NULL,                              -- paired hours the candidate was judged on
  `effect` DOUBLE NULL,                      -- slope, or outcome-per-hour shift (see effect_unit)
  `effect_unit` VARCHAR(160) NULL,
  `improvement` DOUBLE NULL,                 -- relative cut in held-out error
  `p` DOUBLE NULL,                           -- shifted-feature permutation p
  `p_adjusted` DOUBLE NULL,                  -- Holm-corrected over the candidates looked at
  `fitted_from` DATE NULL,
  `fitted_to` DATE NULL,
  `evidence` JSON NOT NULL,                  -- transform, held-out window, permutations, floors
  `computed_at` DATETIME NOT NULL,
  PRIMARY KEY (`run_date`, `target_key`, `feature_key`, `lag_hours`),
  KEY `idx_findings_target_status` (`target_key`, `status`)
);
