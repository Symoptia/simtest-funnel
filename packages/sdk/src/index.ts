import * as wasm from './wasm/simtest_funnel_wasm.js';

/**
 * Tolerances passed to {@link compare} / {@link summarize}. A field that is
 * omitted, `undefined` or `null` is "not given"; any number (including `0`)
 * is given.
 *
 * Coefficients are resolved per axis by the Rust core, identically in every
 * simtest-funnel API (x axis: `atolx`/`ltolx`/`rtolx`; y axis:
 * `atoly`/`ltoly`/`rtoly`):
 *
 * - an axis with no coefficient given gets the default `rtol = 2e-3`
 *   (other coefficients `0`);
 * - an axis with at least one coefficient given uses the given values and
 *   `0` for its other coefficients;
 * - an explicit `0` counts as given.
 *
 * So `{ atoly: 0.05 }` means `atoly = 0.05`, `rtoly = 0` and
 * `rtolx = 2e-3`; use `{ atolx: 0, atoly: 0.05 }` for zero x tolerance.
 */
export interface Tolerances {
  atolx?: number | null;
  atoly?: number | null;
  ltolx?: number | null;
  ltoly?: number | null;
  rtolx?: number | null;
  rtoly?: number | null;
}

/** The six effective tolerance coefficients after resolution. */
export type ResolvedTolerances = { [K in keyof Tolerances]-?: number };

/** X-range filter. */
export interface XRange {
  lo: number;
  hi: number;
}

/**
 * Options for {@link compare}. Omitting `options`, or omitting
 * `tolerances`, means the default tolerances (`rtolx = rtoly = 2e-3`).
 */
export interface Options {
  tolerances?: Tolerances;
  xRange?: XRange;
}

/** Fully explicit options, as returned by {@link defaultOptions}. */
export interface ResolvedOptions {
  tolerances: ResolvedTolerances;
  xRange: XRange;
}

/** Status codes (mirror `simtest_funnel_core::Status`). */
export const Status = {
  Pass: 0,
  Fail: -1,
  MissingReference: 1,
  MissingTest: 2,
  NonMonotonic: 10,
  LengthMismatch: 11,
  EmptyRange: 12,
  BufferTooSmall: 13,
  InsufficientData: 14,
} as const;
export type StatusCode = (typeof Status)[keyof typeof Status];

/** Result of {@link compare}. Errors are signed. */
export interface CompareResult {
  status: StatusCode;
  lowerX: Float64Array;
  lowerY: Float64Array;
  upperX: Float64Array;
  upperY: Float64Array;
  errorsX: Float64Array;
  errorsY: Float64Array;
}

function toF64(v: ArrayLike<number> | Float64Array): Float64Array {
  return v instanceof Float64Array
    ? v
    : Float64Array.from(v as ArrayLike<number>);
}

/**
 * Compare a test trajectory against a reference. Errors are signed
 * (positive above upper, negative below lower). Partially specified
 * tolerances are resolved per axis (see {@link Tolerances}); `options`
 * omitted means the defaults reported by {@link defaultOptions}.
 */
export function compare(
  referenceX: ArrayLike<number> | Float64Array,
  referenceY: ArrayLike<number> | Float64Array,
  testX: ArrayLike<number> | Float64Array,
  testY: ArrayLike<number> | Float64Array,
  options?: Options,
): CompareResult {
  const raw = wasm.compare(
    toF64(referenceX),
    toF64(referenceY),
    toF64(testX),
    toF64(testY),
    // biome-ignore lint/suspicious/noExplicitAny: WASM glue returns `any`
    (options ?? null) as any,
  );
  const r = raw as {
    status: number;
    lowerX: number[];
    lowerY: number[];
    upperX: number[];
    upperY: number[];
    errorsX: number[];
    errorsY: number[];
  };
  return {
    status: r.status as StatusCode,
    lowerX: Float64Array.from(r.lowerX),
    lowerY: Float64Array.from(r.lowerY),
    upperX: Float64Array.from(r.upperX),
    upperY: Float64Array.from(r.upperY),
    errorsX: Float64Array.from(r.errorsX),
    errorsY: Float64Array.from(r.errorsY),
  };
}

/** Side of the tube on which a violation lies. */
export type ViolationDirection = 'above' | 'below';

/**
 * A maximal run of consecutive judged test points outside the tube on the
 * same side. `startX` / `endX` are the x of the first / last test point of
 * the run (equal for a single-point violation).
 */
export interface ViolationInterval {
  startX: number;
  endX: number;
  direction: ViolationDirection;
  pointCount: number;
  /** Signed deviation with the largest magnitude in the run. */
  worstDeviation: number;
  worstX: number;
}

/** Overall worst deviation of a comparison. */
export interface WorstDeviation {
  x: number;
  /** Signed deviation with the largest magnitude (first on ties). */
  deviation: number;
  /** Half the distance between upper and lower bound at `x`. */
  tubeHalfWidthY: number;
}

/**
 * How much a comparison violated the tolerances it was run with. Only
 * judged test points (x inside `xRange` intersected with the reference
 * x-extent) contribute. For validation statuses, or when no point is
 * judged, `comparedRange`, `worst` and both fractions are `null`.
 */
export interface ViolationSummary {
  status: StatusCode;
  /** The six resolved tolerance values used. */
  tolerances: ResolvedTolerances;
  xRange: XRange;
  /** First to last judged test point. */
  comparedRange: XRange | null;
  intervals: ViolationInterval[];
  worst: WorstDeviation | null;
  pointsCompared: number;
  pointsOutside: number;
  fractionOfPointsOutside: number | null;
  /**
   * Each judged point represents the x-length halfway to its neighbours;
   * share of that length lying outside the tube.
   */
  fractionOfSpanOutside: number | null;
}

/**
 * Summarize how much `result` violated its tolerances. `referenceX` and
 * `options` must be the reference x-values and options passed to
 * {@link compare} for `result` (`undefined` means the same defaults
 * `compare` uses). Computed by the Rust core, so numbers are identical to
 * the Rust and Python APIs.
 */
export function summarize(
  result: CompareResult,
  referenceX: ArrayLike<number> | Float64Array,
  options?: Options,
): ViolationSummary {
  return wasm.summarize(
    toF64(referenceX),
    result.status,
    result.lowerX,
    result.lowerY,
    result.upperX,
    result.upperY,
    result.errorsX,
    result.errorsY,
    options ?? null,
  ) as ViolationSummary;
}

/**
 * Returns the default options with all six tolerances explicit
 * (`rtolx = rtoly = 2e-3`, others `0`). Passing them to {@link compare}
 * is identical to omitting `options`.
 */
export function defaultOptions(): ResolvedOptions {
  return wasm.defaultOptions() as ResolvedOptions;
}

/** Returns the core crate version. */
export function version(): string {
  return wasm.version();
}

/**
 * Plot interface shared with Plotly.js. We declare only the minimal
 * surface we need so that users can bring their own Plotly build
 * (peer dependency).
 */
export interface PlotlyLike {
  newPlot(
    el: HTMLElement,
    data: unknown[],
    layout?: unknown,
    config?: unknown,
  ): Promise<unknown>;
}

/** Trace inputs to {@link createFunnelPlot}. */
export interface CreateFunnelPlotInputs {
  reference: { x: ArrayLike<number>; y: ArrayLike<number>; name?: string };
  test: { x: ArrayLike<number>; y: ArrayLike<number>; name?: string };
  result: CompareResult;
}

/** Render a funnel plot into `el`. */
export async function createFunnelPlot(
  plotly: PlotlyLike,
  el: HTMLElement,
  inputs: CreateFunnelPlotInputs,
  layout?: Record<string, unknown>,
): Promise<unknown> {
  const traces = [
    {
      x: Array.from(inputs.reference.x),
      y: Array.from(inputs.reference.y),
      name: inputs.reference.name ?? 'reference',
      mode: 'lines',
      type: 'scatter',
    },
    {
      x: Array.from(inputs.test.x),
      y: Array.from(inputs.test.y),
      name: inputs.test.name ?? 'test',
      mode: 'lines',
      type: 'scatter',
    },
    {
      x: Array.from(inputs.result.lowerX),
      y: Array.from(inputs.result.lowerY),
      name: 'lower bound',
      mode: 'lines',
      line: { dash: 'dot' },
      type: 'scatter',
    },
    {
      x: Array.from(inputs.result.upperX),
      y: Array.from(inputs.result.upperY),
      name: 'upper bound',
      mode: 'lines',
      line: { dash: 'dot' },
      type: 'scatter',
    },
    {
      x: Array.from(inputs.result.errorsX),
      y: Array.from(inputs.result.errorsY).map((v) => Math.abs(v)),
      name: 'error',
      mode: 'lines',
      type: 'scatter',
      yaxis: 'y2',
    },
  ];
  const finalLayout = {
    title: 'Funnel comparison',
    yaxis: { title: 'value' },
    yaxis2: { title: '|error|', overlaying: 'y', side: 'right' },
    ...(layout ?? {}),
  };
  return plotly.newPlot(el, traces, finalLayout);
}
