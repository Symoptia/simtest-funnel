// Errors of the weather part's requests. Kept apart from the Open-Meteo
// client so a sample-only build can use them without the client.

/** Kinds of failure, each with its own message (design §10). */
export type WeatherErrorKind =
  | 'offline'
  | 'timeout'
  | 'rate-limit'
  | 'bad-request'
  | 'http'
  | 'malformed'
  | 'aborted';

/** A failed Open-Meteo request, with a message for the visitor. */
export class WeatherError extends Error {
  readonly kind: WeatherErrorKind;

  constructor(kind: WeatherErrorKind, message: string) {
    super(message);
    this.name = 'WeatherError';
    this.kind = kind;
  }
}

/** Normalised search text: trimmed and lower-cased. */
export function normaliseQuery(text: string): string {
  return text.trim().toLowerCase();
}
