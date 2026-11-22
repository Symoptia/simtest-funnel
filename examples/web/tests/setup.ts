// No demo test may reach the network: the global fetch is replaced by one
// that records the call and throws, and any call fails the test afterwards
// even if the code under test swallowed the error.

import { afterEach, beforeEach } from 'vitest';

const calls: string[] = [];

function blockedFetch(input: unknown): Promise<Response> {
  calls.push(String(input));
  throw new Error(`network access in tests: ${String(input)}`);
}

beforeEach(() => {
  calls.length = 0;
  globalThis.fetch = blockedFetch as typeof fetch;
});

afterEach(() => {
  if (calls.length > 0) {
    const urls = calls.splice(0).join(', ');
    throw new Error(`network access in tests: global fetch called for ${urls}`);
  }
});

/** Calls to the global fetch in the current test (for the guard's own test). */
export function takeBlockedCalls(): string[] {
  return calls.splice(0);
}
