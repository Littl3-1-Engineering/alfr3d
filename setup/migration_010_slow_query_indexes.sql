-- Migration 010: Indexes for slow query optimization
-- Based on Slow Query Analysis (ticket #21)
--
-- Adds indexes for common query patterns identified during analysis:
--   - device MAC lookups (WHERE MAC = %s)
--   - device last_online range scans (offline detection)
--   - device JOINs via user_id
--   - user lookups by username, state, last_online
--   - personality type+environment compound filter
--   - calendar_events start_time range queries

ALTER TABLE device ADD INDEX idx_device_mac (MAC);
ALTER TABLE device ADD INDEX idx_device_last_online (last_online);
ALTER TABLE device ADD INDEX idx_device_user_id (user_id);

ALTER TABLE user ADD INDEX idx_user_username (username);
ALTER TABLE user ADD INDEX idx_user_state (state);
ALTER TABLE user ADD INDEX idx_user_last_online (last_online);

ALTER TABLE personality ADD INDEX idx_personality_type_env (type, environment_id);

ALTER TABLE calendar_events ADD INDEX idx_calendar_events_start_time (start_time);
