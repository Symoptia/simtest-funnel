import { describe, expect, it } from 'vitest';
import { compare, version } from '../src/index.js';

describe('compare', () => {
  it('should return true', () => {
    expect(compare()).toBe(true);
  });
});

describe('version', () => {
  it('should return a non-empty string', () => {
    const v = version();
    expect(typeof v).toBe('string');
    expect(v.length).toBeGreaterThan(0);
  });
});
