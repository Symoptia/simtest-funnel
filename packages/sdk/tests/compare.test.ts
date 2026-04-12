import { describe, it, expect } from 'vitest';
import { compare } from '../src/index.js';

describe('compare', () => {
  it('should return true', () => {
    expect(compare()).toBe(true);
  });
});
