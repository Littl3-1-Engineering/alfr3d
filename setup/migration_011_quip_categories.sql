-- Migration 011: Quip categories
-- Adds a category column to the quips table so quips can be grouped into
-- semantic categories (greeting, weather_joke, sarcasm, wisdom, goodbye, custom).

ALTER TABLE `quips` ADD COLUMN `category` VARCHAR(32) NULL DEFAULT 'custom' AFTER `type`;
