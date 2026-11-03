// Sensor/weather readings arrive as raw values (HA sensor states are strings like
// "22.456789"). Show numeric ones as whole numbers; leave non-numeric states
// ("on", "unavailable", ...) untouched.
export function roundReading(value) {
  if (value === null || value === undefined || value === '') return value;
  const n = typeof value === 'number' ? value : Number(String(value).trim());
  return Number.isFinite(n) ? String(Math.round(n)) : value;
}
