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
 * - an axis with no coefficient given gets its default: the x axis all `0`
 *   (no time tolerance), the y axis `rtoly = 2e-3` (other coefficients `0`);
 * - an axis with at least one coefficient given uses the given values and
 *   `0` for its other coefficients;
 * - an explicit `0` counts as given.
 *
 * So `{ atoly: 0.05 }` means `atoly = 0.05` and every other coefficient
 * `0`. Give an x coefficient, e.g. `{ atolx: 0.5, atoly: 0.05 }`, to allow
 * the test to be shifted in time: with zero x tolerance the x half-width is
 * the `1e-10` floor, so each test point is checked only against the y band
 * around the reference at the same x and a slightly delayed steep edge
 * fails.
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

/**
 * X-range window passed in {@link Options}: only test points with x in
 * `[lo, hi]` are judged. A bound that is omitted, `undefined` or `null` is
 * unbounded on that side, so `{ lo: 0.5 }` means `[0.5, Infinity]` (same as
 * the Python `Range`).
 *
 * The tube for the window is built from the reference extended beyond it
 * by the x tolerance (two x half-widths plus three samples per side), so a
 * test point near a window edge that is shifted by less than the x
 * tolerance is judged as in a full-range comparison; without `rtolx` /
 * `rtoly` every point in the window gets the same verdict as in the
 * full-range comparison. At the first and last reference sample there is
 * nothing to extend with. `rtolx` / `rtoly` are relative to the reference
 * inside the window, and coverage (`MissingReference` / `MissingTest`) is
 * judged inside the window.
 */
export interface XRange {
  lo?: number | null;
  hi?: number | null;
}

/**
 * A range as returned by the library: both bounds present, unbounded
 * sides are `-Infinity` / `Infinity`.
 */
export interface ResolvedXRange {
  lo: number;
  hi: number;
}

/**
 * Options for {@link compare}. Omitting `options`, or omitting
 * `tolerances`, means the default tolerances (`rtoly = 2e-3`, no tolerance
 * in x).
 */
export interface Options {
  tolerances?: Tolerances;
  xRange?: XRange;
}

/** Fully explicit options, as returned by {@link defaultOptions}. */
export interface ResolvedOptions {
  tolerances: ResolvedTolerances;
  xRange: ResolvedXRange;
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

/**
 * Result of {@link compare}. `errorsX` is the test x-grid and `errorsY` the
 * signed deviation there (positive above the upper bound, negative below the
 * lower bound, `0` inside the tube and for test points outside `xRange`).
 * With an `xRange`, `lowerX` / `upperX` reach beyond the window by the
 * extension the tube is built from.
 */
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
  xRange: ResolvedXRange;
  /** First to last judged test point. */
  comparedRange: ResolvedXRange | null;
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
 * Samples kept by {@link downsampleMinMax}, in input order:
 * `x[k] === inputX[indices[k]]` and `y[k] === inputY[indices[k]]`. Use
 * `indices` to select the same samples from further arrays on the same
 * x-grid (e.g. `result.errorsY` of a comparison).
 */
export interface Downsampled {
  indices: Uint32Array;
  x: Float64Array;
  y: Float64Array;
}

/**
 * Reduce a signal to the extremes of `buckets` equal-width x-buckets, for
 * output only (plots, reports); never feed the result back into
 * {@link compare}.
 *
 * The lowest and highest sample of each bucket are kept (first occurrence
 * on ties, `NaN` y never selected), plus the first and last sample. Each
 * finite value of `pinnedX` keeps the sample with the nearest x (ties go to
 * the lower x) and every sample sharing that x; `NaN` pins are ignored. Pin
 * the `worstX` of every interval of {@link summarize} so a plot never hides
 * a violation.
 *
 * At most `min(n, 2 * buckets + 2 + M)` samples are returned (`M` = samples
 * selected by pins); if `n <= 2 * buckets` every sample is returned.
 * Computed by the Rust core, so results are identical to the Rust and
 * Python APIs.
 *
 * @throws Error for a length mismatch, a non-finite or decreasing x, a
 * non-integer `buckets` or `buckets < 1`.
 */
export function downsampleMinMax(
  x: ArrayLike<number> | Float64Array,
  y: ArrayLike<number> | Float64Array,
  buckets: number,
  pinnedX?: ArrayLike<number> | Float64Array,
): Downsampled {
  try {
    return wasm.downsampleMinMax(
      toF64(x),
      toF64(y),
      buckets,
      toF64(pinnedX ?? []),
    ) as Downsampled;
  } catch (e) {
    // The WASM glue throws the core's message as a plain string.
    throw e instanceof Error ? e : new Error(String(e));
  }
}

/**
 * Returns the default options with all six tolerances explicit
 * (`rtoly = 2e-3`, others `0`: no tolerance in x). Passing them to {@link compare}
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

/** Layout keys whose objects {@link createFunnelPlot} merges with its defaults. */
const MERGED_LAYOUT_KEYS = [
  'title',
  'xaxis',
  'yaxis',
  'yaxis2',
  'legend',
  'margin',
] as const;

/** Layout keys whose `title` may be given as a plain string. */
const AXIS_KEYS = ['xaxis', 'yaxis', 'yaxis2'] as const;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Plotly 3 ignores string titles: turn `'t'` into `{ text: 't' }`. */
function titleObject(title: unknown): unknown {
  return typeof title === 'string' ? { text: title } : title;
}

/**
 * The layout {@link createFunnelPlot} passes to Plotly: its defaults with
 * `layout` merged in. Exported for tests and for callers who render the
 * traces themselves.
 *
 * - Titles (`title`, `xaxis.title`, `yaxis.title`, `yaxis2.title`) may be
 *   given as strings; they are turned into the `{ text }` objects Plotly 3
 *   requires (Plotly 3 does not display string titles).
 * - `title`, `xaxis`, `yaxis`, `yaxis2`, `legend` and `margin` are merged
 *   one level deep, so e.g. `{ yaxis2: { range: [0, 1] } }` keeps the
 *   error axis on the right; `{ text: ... }` replaces the default title
 *   text but keeps its position. Every other key replaces the default.
 * - Defaults: title "Funnel comparison" at the top left (clear of
 *   Plotly's toolbar at the top right), axes `value` and
 *   `|error|` (right, from zero, no grid) with automatic margins for tick
 *   labels and axis titles, and a horizontal legend across the bottom of
 *   the figure, so the plot keeps its full width on narrow screens.
 */
export function funnelPlotLayout(
  layout?: Record<string, unknown>,
): Record<string, unknown> {
  const defaults: Record<string, Record<string, unknown>> = {
    title: {
      text: 'Funnel comparison',
      x: 0,
      xref: 'container',
      xanchor: 'left',
      y: 1,
      yref: 'container',
      yanchor: 'top',
      pad: { t: 12 },
    },
    xaxis: { automargin: true },
    yaxis: { title: { text: 'value' }, automargin: true },
    yaxis2: {
      title: { text: '|error|' },
      overlaying: 'y',
      side: 'right',
      rangemode: 'tozero',
      showgrid: false,
      automargin: true,
    },
    legend: {
      orientation: 'h',
      x: 0,
      xref: 'container',
      xanchor: 'left',
      y: 0,
      yref: 'container',
      yanchor: 'bottom',
      // Plotly wraps a horizontal legend within the plot-area width; at 11 px
      // two entries share a row even on a phone.
      font: { size: 11 },
    },
    margin: { t: 48, r: 8, b: 8, l: 8 },
  };
  const given: Record<string, unknown> = { ...(layout ?? {}) };
  if ('title' in given) {
    given.title = titleObject(given.title);
  }
  for (const key of AXIS_KEYS) {
    const axis = given[key];
    if (isPlainObject(axis) && 'title' in axis) {
      given[key] = { ...axis, title: titleObject(axis.title) };
    }
  }
  const merged: Record<string, unknown> = { ...defaults, ...given };
  for (const key of MERGED_LAYOUT_KEYS) {
    const value = given[key];
    if (isPlainObject(value)) {
      merged[key] = { ...defaults[key], ...value };
    }
  }
  return merged;
}

/**
 * Render a funnel plot into `el`: reference, test, both tube bounds and the
 * absolute deviations (on a second y axis on the right). For a comparison
 * with an `xRange` the bounds cover the window plus the extension the tube
 * was built from and the deviations are `0` outside the window; pass e.g.
 * `{ xaxis: { range: [lo, hi] } }` as `layout` to show only the window.
 *
 * `layout` is merged with the defaults as described in
 * {@link funnelPlotLayout}; titles may be plain strings, e.g.
 * `{ title: 'Signal x', xaxis: { title: 'time' } }`.
 */
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
  return plotly.newPlot(el, traces, funnelPlotLayout(layout));
}
