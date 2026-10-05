import { describe, it, expect } from 'vitest';
import { formatLocalTime, parseEventTime } from './timeUtils';

describe('event time parsing', () => {
  const utc = '2026-10-05T14:30:00.000Z';

  it('reads an offset isoformat with a stray trailing Z as the offset instant', () => {
    expect(parseEventTime('2026-10-05T14:30:00.000+00:00Z').toISOString()).toBe(utc);
  });

  it('treats a plain Z string as that UTC instant', () => {
    expect(parseEventTime('2026-10-05T14:30:00Z').toISOString()).toBe('2026-10-05T14:30:00.000Z');
  });

  it('treats a naive string as UTC rather than browser-local', () => {
    expect(parseEventTime('2026-10-05T14:30:00').toISOString()).toBe('2026-10-05T14:30:00.000Z');
    expect(parseEventTime('2026-10-05 14:30:00').toISOString()).toBe('2026-10-05T14:30:00.000Z');
  });

  it('returns the raw input from formatLocalTime when unparseable, never "Invalid Date"', () => {
    expect(formatLocalTime('not a time')).toBe('not a time');
    expect(formatLocalTime('2026-10-05T14:30:00.000+00:00Z')).not.toMatch(/Invalid/);
  });
});
