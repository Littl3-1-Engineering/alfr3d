import { describe, it, expect } from 'vitest';
import { roundReading } from './formatReading';

describe('roundReading', () => {
  it('rounds numeric strings and numbers to whole numbers', () => {
    expect(roundReading('22.456789')).toBe('22');
    expect(roundReading('22.5')).toBe('23');
    expect(roundReading(47.9999)).toBe('48');
  });
  it('passes through non-numeric and empty values', () => {
    expect(roundReading('unavailable')).toBe('unavailable');
    expect(roundReading('on')).toBe('on');
    expect(roundReading(null)).toBe(null);
    expect(roundReading(undefined)).toBe(undefined);
  });
});
