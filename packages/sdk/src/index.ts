import * as wasm from './wasm/simtest_funnel_wasm.js';

/** Tolerances passed to {@link compare}. */
export interface Tolerances {
  atolx?: number;
  atoly?: number;
  ltolx?: number;
  ltoly?: number;
  rtolx?: number;
  rtoly?: number;
}

/** X-range filter. */
export interface XRange {
  lo: number;
  hi: number;
}

/** Options for {@link compare}. */
export interface Options {
  tolerances?: Tolerances;
  xRange?: XRange;
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
 * (positive above upper, negative below lower).
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

/** Returns the default options. */
export function defaultOptions(): Options {
  return wasm.defaultOptions() as Options;
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
