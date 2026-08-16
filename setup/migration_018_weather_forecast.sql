-- Migration 018: Weather forecast columns
-- Adds a persisted forecast snapshot (rain probability, forecast temp,
-- conditions) to the environment table, populated periodically by
-- weather_util.get_forecast() via service_environment's "check forecast"
-- Kafka message -- mirroring how current-conditions columns (temperature,
-- wind, etc.) are populated by check_weather(). service_daemon reads this
-- snapshot directly, the same way it already reads current weather, rather
-- than calling out to service_environment synchronously.

ALTER TABLE environment
  ADD COLUMN forecast_rain_probability FLOAT NULL DEFAULT NULL AFTER subjective_feel,
  ADD COLUMN forecast_temp FLOAT NULL DEFAULT NULL AFTER forecast_rain_probability,
  ADD COLUMN forecast_conditions VARCHAR(64) NULL DEFAULT NULL AFTER forecast_temp,
  ADD COLUMN forecast_updated_at DATETIME NULL DEFAULT NULL AFTER forecast_conditions;
