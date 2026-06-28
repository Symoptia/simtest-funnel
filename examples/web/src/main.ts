import {
  type CompareResult,
  type PlotlyLike,
  Status,
  compare,
  createFunnelPlot,
} from '@simtest-js/funnel';

/** A single demo signal: one column of the CSV, reference vs test. */
interface Signal {
  key: 'x' | 'y' | 'z';
  label: string;
  formula: string;
}

const SIGNALS: Signal[] = [
  {
    key: 'x',
    label: 'x',
    formula: 'sin(2πt) vs sin(2πt) + 0.05·sin(30πt)',
  },
  {
    key: 'y',
    label: 'y',
    formula: 'cos(2πt)·sin(100t) vs cos(2πt)·sin(150t)',
  },
  {
    key: 'z',
    label: 'z',
    formula: 'sin(4πt) vs sin(5πt)',
  },
];

const COLUMNS = ['time', 'x', 'y', 'z'] as const;
type Column = (typeof COLUMNS)[number];

/** Parsed CSV: column name -> values. */
type Table = Record<Column, Float64Array>;

/** Tolerances used for every signal (10% in both directions). */
const TOLERANCES = { atolx: 0.1, atoly: 0.1 } as const;

async function fetchCsv(url: string): Promise<Table> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`failed to load ${url}: ${res.status}`);
  }
  return parseCsv(await res.text());
}

function parseCsv(text: string): Table {
  const lines = text.trim().split(/\r?\n/);
  const header = lines[0].split(',').map((h) => h.trim());
  for (const col of COLUMNS) {
    if (!header.includes(col)) {
      throw new Error(`CSV missing column "${col}"`);
    }
  }
  const rows = lines.slice(1);
  const cols: Record<string, number[]> = {};
  for (const col of COLUMNS) {
    cols[col] = [];
  }
  for (const line of rows) {
    const cells = line.split(',');
    header.forEach((name, i) => {
      if (COLUMNS.includes(name as Column)) {
        cols[name].push(Number(cells[i]));
      }
    });
  }
  return {
    time: Float64Array.from(cols.time),
    x: Float64Array.from(cols.x),
    y: Float64Array.from(cols.y),
    z: Float64Array.from(cols.z),
  };
}

function statusLabel(result: CompareResult): { pass: boolean; text: string } {
  const pass = result.status === Status.Pass;
  return { pass, text: pass ? 'PASS' : 'FAIL' };
}

/** Wait briefly for the async Plotly CDN script; resolve null if it never loads. */
async function waitForPlotly(timeoutMs = 5000): Promise<PlotlyLike | null> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (window.Plotly) {
      return window.Plotly;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return window.Plotly ?? null;
}

function renderSignalCard(signal: Signal, result: CompareResult): HTMLElement {
  const { pass, text } = statusLabel(result);
  const card = document.createElement('section');
  card.className = 'signal';
  card.innerHTML = `
    <h2>Signal ${signal.label}
      <span class="status ${pass ? 'pass' : 'fail'}">${text}</span>
    </h2>
    <p class="formula">${signal.formula}</p>
    <div class="plot" id="plot-${signal.key}"></div>
  `;
  return card;
}

async function main(): Promise<void> {
  const container = document.getElementById('signals');
  if (!container) {
    return;
  }

  let reference: Table;
  let test: Table;
  try {
    [reference, test] = await Promise.all([
      fetchCsv('./reference.csv'),
      fetchCsv('./test.csv'),
    ]);
  } catch (err) {
    container.innerHTML = `<p class="status fail">Failed to load demo data: ${
      (err as Error).message
    }</p>`;
    return;
  }

  const plotly = await waitForPlotly();

  for (const signal of SIGNALS) {
    const result = compare(
      reference.time,
      reference[signal.key],
      test.time,
      test[signal.key],
      { tolerances: { ...TOLERANCES } },
    );
    container.appendChild(renderSignalCard(signal, result));

    // Render the plot independently so one failure does not block the rest.
    const el = document.getElementById(`plot-${signal.key}`);
    if (!el) {
      continue;
    }
    if (!plotly) {
      el.innerHTML =
        '<p class="formula">Plotly failed to load — status shown above.</p>';
      continue;
    }
    try {
      await createFunnelPlot(
        plotly,
        el,
        {
          reference: {
            x: reference.time,
            y: reference[signal.key],
            name: 'reference',
          },
          test: { x: test.time, y: test[signal.key], name: 'test' },
          result,
        },
        { title: `Signal ${signal.label}`, xaxis: { title: 'time' } },
      );
    } catch (err) {
      el.innerHTML = `<p class="formula">Plot failed: ${
        (err as Error).message
      }</p>`;
    }
  }
}

void main();
