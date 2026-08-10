-- Migration 012: Weather expansion columns
-- Adds current temperature, wind speed/direction, and pressure trend to the
-- environment table so the WeatherPanel can render a large current temp,
-- wind row, and pressure trend arrow.

ALTER TABLE environment
  ADD COLUMN temperature FLOAT NULL DEFAULT NULL AFTER high,
  ADD COLUMN wind FLOAT NULL DEFAULT NULL AFTER temperature,
  ADD COLUMN wind_dir VARCHAR(16) NULL DEFAULT NULL AFTER wind,
  ADD COLUMN pressure_trend VARCHAR(8) NULL DEFAULT 'steady' AFTER pressure;
