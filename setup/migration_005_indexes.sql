-- Migration 005: Database Index Optimizations
-- Adds indexes for frequently queried columns to improve query performance

-- Index for device_history table - accessed frequently via device_id
CREATE INDEX idx_device_history_device_id ON device_history(device_id);

-- Index for device_history cleanup queries (timestamp-based cleanup)
CREATE INDEX idx_device_history_timestamp ON device_history(timestamp);

-- Index for config table lookups by name
CREATE INDEX idx_config_name ON config(name);

-- Index for personality table lookups by type
CREATE INDEX idx_personality_type ON personality(type);

-- Index for quips table lookups by type
CREATE INDEX idx_quips_type ON quips(type);

-- Index for environment table lookups by name
CREATE INDEX idx_environment_name ON environment(name);

-- Index for calendar_events cleanup queries
CREATE INDEX idx_calendar_events_end_time ON calendar_events(end_time);
