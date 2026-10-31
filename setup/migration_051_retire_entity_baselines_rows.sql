-- Migration 051: clear the entity_baselines rows nothing reads or writes any more
--
-- The `device` rows (check_rhythm_break_anomaly now reads the device rhythm learner), the
-- `household` rows (the household-day learner) and the `room` climate rows (the scalar learner)
-- are no longer computed by compute_entity_baselines() or read by any card. Only the `user`
-- departure rows remain, for check_departure_anomaly(), until it moves to the stay learner and
-- the table is dropped. Not restorable by a downgrade (the learners hold their own profiles).
DELETE FROM `entity_baselines` WHERE `entity_type` IN ('device', 'household', 'room');
