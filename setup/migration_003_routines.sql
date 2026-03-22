-- Migration 003: Routine Management System
-- Extends routines table with recurrence, actions JSON, and last_run

-- Add new columns to routines table
ALTER TABLE `routines` ADD COLUMN `recurrence` ENUM('once', 'daily', 'weekly', 'weekdays') DEFAULT 'daily' AFTER `enabled`;
ALTER TABLE `routines` ADD COLUMN `actions` JSON NULL AFTER `recurrence`;
ALTER TABLE `routines` ADD COLUMN `last_run` TIMESTAMP NULL AFTER `actions`;

-- Update existing routines to have default recurrence
UPDATE routines SET recurrence = 'daily' WHERE recurrence IS NULL;

-- Create index for faster routine lookups
CREATE INDEX idx_routines_environment_time ON routines(environment_id, time, enabled);
