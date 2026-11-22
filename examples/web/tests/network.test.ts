import { describe, expect, it } from 'vitest';
import { takeBlockedCalls } from './setup';

describe('network guard', () => {
  it('makes the global fetch throw', () => {
    expect(() => fetch('https://example.org/')).toThrow(
      /network access in tests/,
    );
    // The guard would fail this test in afterEach; we take the call so this
    // test passes and checks that the call was recorded.
    expect(takeBlockedCalls()).toEqual(['https://example.org/']);
  });
});
