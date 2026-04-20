-- Migration: Personality Context Tracking
-- Adds columns to track last spoken text and time for repeat detection

-- Add last_text and last_spoke_time to context table
ALTER TABLE context ADD COLUMN last_text VARCHAR(512) DEFAULT NULL;
ALTER TABLE context ADD COLUMN last_spoke_time TIMESTAMP DEFAULT NULL;

-- Add index for efficient lookups
ALTER TABLE context ADD INDEX idx_last_spoke_time (last_spoke_time);
