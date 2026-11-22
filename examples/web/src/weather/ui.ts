// DOM of the "Real weather" tab. All logic lives in the DOM-free modules
// next to this one; this file only builds elements and wires events.

import { createFunnelPlot, type PlotlyLike, Status } from '@simtest-js/funnel';
import { waitForPlotly } from '../synthetic';
import { type AgeComparison, compareAllAges } from './compare';
import { WeatherController, type WeatherState } from './controller';
import type { LiveClient } from './live';
import {
  type Place,
  placeLabel,
  VARIABLES,
  type Variable,
  type VariableId,
  variableById,
  type WeatherData,
  type WeatherTolerances,
} from './model';
import { loadSample } from './sample';
import { createPlaceSearch, type SearchState } from './search';
import {
  ageWords,
  answerLine,
  attributionLines,
  formatDateRange,
  formatPercent,
  formatTolerances,
  statusName,
} from './text';

/** Live search is compiled in unless the build ran with VITE_WEATHER_LIVE=false. */
const LIVE = import.meta.env.VITE_WEATHER_LIVE === 'true';

const INPUT_DEBOUNCE_MS = 150;
const MAX_TIME_TOL_HOURS = 24;

type Attrs = Record<string, string>;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Attrs = {},
  children: (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') {
      node.className = v;
    } else {
      node.setAttribute(k, v);
    }
  }
  node.append(...children);
  return node;
}

function presetOf(id: VariableId): Variable {
  return variableById(id) ?? VARIABLES[0];
}

function coords(place: Place): string {
  const lat = `${Math.abs(place.latitude).toFixed(2)}° ${place.latitude < 0 ? 'S' : 'N'}`;
  const lon = `${Math.abs(place.longitude).toFixed(2)}° ${place.longitude < 0 ? 'W' : 'E'}`;
  return `${lat}, ${lon}`;
}

/** Build the weather tab into `panel`. */
export async function mountWeather(panel: HTMLElement): Promise<void> {
  const sample = loadSample();
  let client: LiveClient | null = null;
  if (LIVE) {
    const live = await import('./live');
    client = live.createLiveClient({ fetch: live.browserFetch() });
  }
  new WeatherView(panel, sample, client);
}

class WeatherView {
  private readonly controller: WeatherController;
  private readonly client: LiveClient | null;
  private age = 1;
  private tol: WeatherTolerances;
  private shownVariable: VariableId | null = null;
  private shownData: WeatherData | null = null;
  private comparisons: AgeComparison[] = [];
  private plotly: Promise<PlotlyLike | null> | null = null;
  private plotToken = 0;
  private debounce: ReturnType<typeof setTimeout> | undefined;

  // Controls and output areas.
  private readonly variableSelect = el('select', { id: 'w-variable' });
  private readonly ageSelect = el('select', { id: 'w-age' });
  private readonly valueInput = el('input', {
    id: 'w-vtol',
    type: 'number',
    inputmode: 'decimal',
    min: '0',
  });
  private readonly valueUnit = el('span', { class: 'unit' });
  private readonly timeInput = el('input', {
    id: 'w-ttol',
    type: 'number',
    inputmode: 'decimal',
    min: '0',
    max: String(MAX_TIME_TOL_HOURS),
    step: '0.5',
  });
  private readonly presetHint = el('span', { class: 'hint' });
  private readonly current = el('p', { class: 'current' });
  private readonly message = el('p', {
    class: 'weather-message',
    role: 'status',
    'aria-live': 'polite',
  });
  private readonly results = el('div', { class: 'weather-results' });
  private readonly answer = el('p', { class: 'answer' });
  private readonly windowLine = el('p', { class: 'window' });
  private readonly table = el('table', { class: 'ages' });
  private readonly plot = el('div', { class: 'plot', id: 'w-plot' });
  private readonly attribution = el('div', { class: 'attribution' });

  constructor(
    panel: HTMLElement,
    sample: WeatherData,
    client: LiveClient | null,
  ) {
    this.client = client;
    const preset = presetOf(sample.variable);
    this.tol = { valueTol: preset.valueTol, timeTolHours: preset.timeTolHours };
    this.controller = new WeatherController(
      sample,
      client ? (place, variable) => client.loadForecast(place, variable) : null,
      (state) => this.render(state),
    );
    panel.append(
      el('p', { class: 'intro' }, [
        'Was the forecast made N days ahead close enough to what happened? ',
        'Each hour of the forecast is compared with the latest run of the same ',
        'weather model (ECMWF IFS), using a tolerance tube around the latest run.',
      ]),
      this.buildControls(),
      this.message,
      this.results,
      this.attribution,
    );
    this.results.append(this.answer, this.windowLine, this.table, this.plot);
    this.render(this.controller.state);
  }

  private buildControls(): HTMLElement {
    const box = el('div', { class: 'weather-controls' });
    if (this.client) {
      box.append(this.buildSearch(this.client));
    } else {
      box.append(
        el('p', { class: 'note' }, [
          'Live search is not available on this site; the sample shows how it works.',
        ]),
      );
    }
    box.append(this.current);

    this.variableSelect.addEventListener('change', () => {
      const id = this.variableSelect.value as VariableId;
      const { place } = this.controller.state;
      if (place) {
        void this.controller.pick(place, id);
      }
    });
    this.ageSelect.addEventListener('change', () => {
      this.age = Number(this.ageSelect.value);
      this.renderResults();
    });
    const onTolInput = (): void => {
      clearTimeout(this.debounce);
      this.debounce = setTimeout(
        () => this.readTolerances(),
        INPUT_DEBOUNCE_MS,
      );
    };
    this.valueInput.addEventListener('input', onTolInput);
    this.timeInput.addEventListener('input', onTolInput);

    const reset = el('button', { type: 'button', class: 'link' }, [
      'reset to preset',
    ]);
    reset.addEventListener('click', () => {
      this.applyPreset(this.controller.state.data.variable);
      this.renderResults();
    });

    box.append(
      el('div', { class: 'row' }, [
        el('label', { for: 'w-variable' }, ['Variable']),
        this.variableSelect,
        el('label', { for: 'w-age' }, ['Forecast made']),
        this.ageSelect,
      ]),
      el('div', { class: 'row' }, [
        el('label', { for: 'w-vtol' }, ['Value tolerance ±']),
        el('span', { class: 'nowrap' }, [this.valueInput, ' ', this.valueUnit]),
        el('label', { for: 'w-ttol' }, ['Time tolerance ±']),
        el('span', { class: 'nowrap' }, [this.timeInput, ' h']),
      ]),
      el('p', { class: 'hint-row' }, [this.presetHint, ' · ', reset]),
      el('p', { class: 'explain' }, [
        'The time tolerance lets a forecast that is right but a few hours early ',
        'or late still count as inside the tube; at 0 h every hour is checked ',
        'only against the same hour.',
      ]),
    );
    return box;
  }

  private buildSearch(client: LiveClient): HTMLElement {
    const input = el('input', {
      id: 'w-place',
      type: 'search',
      role: 'combobox',
      autocomplete: 'off',
      spellcheck: 'false',
      'aria-autocomplete': 'list',
      'aria-expanded': 'false',
      'aria-controls': 'w-places',
      placeholder: 'Type a town or city, e.g. Stockholm',
    });
    const list = el('ul', {
      id: 'w-places',
      role: 'listbox',
      'aria-label': 'Places found',
    });
    list.hidden = true;
    const status = el('p', { class: 'search-status', 'aria-live': 'polite' });
    let places: Place[] = [];
    let active = -1;

    const setActive = (i: number): void => {
      active = i;
      list.querySelectorAll('[role="option"]').forEach((li, j) => {
        li.setAttribute('aria-selected', String(j === i));
      });
      if (i >= 0) {
        input.setAttribute('aria-activedescendant', `w-place-${i}`);
        list.children[i]?.scrollIntoView({ block: 'nearest' });
      } else {
        input.removeAttribute('aria-activedescendant');
      }
    };
    const close = (): void => {
      list.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      setActive(-1);
    };
    const pick = (place: Place): void => {
      search.cancel();
      input.value = placeLabel(place);
      close();
      status.textContent = '';
      const variable = this.controller.state.place
        ? (this.variableSelect.value as VariableId)
        : this.controller.state.data.variable;
      void this.controller.pick(place, variable);
    };
    const onState = (state: SearchState): void => {
      list.replaceChildren();
      places = [];
      setActive(-1);
      if (state.kind === 'idle') {
        status.textContent = '';
        close();
        return;
      }
      if (state.kind === 'loading') {
        status.textContent = `Searching for “${state.query}”…`;
        return;
      }
      if (state.kind === 'error') {
        status.textContent = state.message;
        status.className = 'search-status error';
        close();
        return;
      }
      status.className = 'search-status';
      if (state.places.length === 0) {
        status.textContent = `No place found for “${state.query}”.`;
        close();
        return;
      }
      status.textContent = `${state.places.length} ${state.places.length === 1 ? 'place' : 'places'} found; pick one.`;
      places = state.places;
      places.forEach((place, i) => {
        const region = [place.admin1, place.country].filter(Boolean).join(', ');
        const li = el(
          'li',
          { role: 'option', id: `w-place-${i}`, 'aria-selected': 'false' },
          [
            el('strong', {}, [place.name]),
            region ? el('span', { class: 'region' }, [region]) : '',
            el('span', { class: 'coords' }, [coords(place)]),
          ],
        );
        // mousedown keeps focus in the input; click picks.
        li.addEventListener('mousedown', (e) => e.preventDefault());
        li.addEventListener('click', () => pick(place));
        list.append(li);
      });
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    };
    const search = createPlaceSearch({
      search: (q, signal) => client.searchPlaces(q, signal),
      onState: (s) => {
        if (s.kind !== 'error') {
          status.className = 'search-status';
        }
        onState(s);
      },
    });

    input.addEventListener('input', () => search.input(input.value));
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' && places.length > 0) {
        e.preventDefault();
        list.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        setActive((active + 1) % places.length);
      } else if (e.key === 'ArrowUp' && places.length > 0) {
        e.preventDefault();
        setActive((active - 1 + places.length) % places.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const place = places[active];
        if (active >= 0 && place && !list.hidden) {
          pick(place);
        } else {
          search.submit(input.value);
        }
      } else if (e.key === 'Escape') {
        close();
      }
    });
    input.addEventListener('blur', () => close());
    input.addEventListener('focus', () => {
      if (places.length > 0) {
        list.hidden = false;
        input.setAttribute('aria-expanded', 'true');
      }
    });

    return el('div', { class: 'field place' }, [
      el('label', { for: 'w-place' }, ['Place']),
      el('div', { class: 'combo' }, [input, list]),
      status,
    ]);
  }

  private applyPreset(id: VariableId): void {
    const v = presetOf(id);
    this.tol = { valueTol: v.valueTol, timeTolHours: v.timeTolHours };
    this.valueInput.value = String(v.valueTol);
    this.valueInput.step = String(v.step);
    this.timeInput.value = String(v.timeTolHours);
    this.valueUnit.textContent = v.unit;
    this.presetHint.textContent = `Preset: ${formatTolerances(
      { valueTol: v.valueTol, timeTolHours: v.timeTolHours },
      v.unit,
    ).replace(' and ', ', ')}`;
  }

  private readTolerances(): void {
    const value = this.valueInput.valueAsNumber;
    const time = this.timeInput.valueAsNumber;
    if (!(value > 0) || !Number.isFinite(value)) {
      this.showInputProblem('Enter a value tolerance above 0.');
      return;
    }
    if (!(time >= 0 && time <= MAX_TIME_TOL_HOURS)) {
      this.showInputProblem(
        `Enter a time tolerance from 0 to ${MAX_TIME_TOL_HOURS} h.`,
      );
      return;
    }
    this.tol = { valueTol: value, timeTolHours: time };
    this.renderResults();
  }

  private showInputProblem(text: string): void {
    this.message.textContent = text;
    this.message.className = 'weather-message error';
  }

  /** Re-render after a controller change. */
  private render(state: WeatherState): void {
    const { data } = state;
    const live = Boolean(this.client);

    // Variable options: all variables for a searched place, else only the
    // sample's variable.
    const options = state.place
      ? VARIABLES
      : VARIABLES.filter((v) => v.id === data.variable);
    this.variableSelect.replaceChildren(
      ...options.map((v) => el('option', { value: v.id }, [v.label])),
    );
    this.variableSelect.value = state.loading?.variable ?? data.variable;
    this.variableSelect.disabled = options.length < 2 || Boolean(state.loading);

    if (data.variable !== this.shownVariable) {
      this.applyPreset(data.variable);
      this.shownVariable = data.variable;
    }

    // Place line.
    const first = data.time[0];
    const last = data.time[data.time.length - 1];
    this.current.replaceChildren(
      'Showing ',
      el('strong', {}, [
        state.place
          ? placeLabel(state.place)
          : data.place.replace(' (sample)', ''),
      ]),
      ' ',
      el('span', { class: `badge ${data.source}` }, [
        data.source === 'sample' ? 'sample' : 'live',
      ]),
    );
    if (data.source === 'sample') {
      this.current.append(` ${formatDateRange(first, last)}`);
    } else if (state.place) {
      this.current.append(` ${coords(state.place)}`);
    }
    if (state.place && live) {
      const back = el('button', { type: 'button', class: 'link' }, [
        'Back to sample',
      ]);
      back.addEventListener('click', () => this.controller.showSample());
      this.current.append(' · ', back);
    }

    // Status line.
    if (state.loading) {
      this.message.textContent = `Loading forecasts for ${placeLabel(state.loading.place)}…`;
      this.message.className = 'weather-message';
    } else if (state.error) {
      this.message.textContent = `${state.error} The results below are for the earlier choice.`;
      this.message.className = 'weather-message error';
    } else {
      this.message.textContent = '';
      this.message.className = 'weather-message';
    }
    this.results.classList.toggle('stale', state.stale);
    this.results.setAttribute('aria-busy', String(Boolean(state.loading)));

    this.renderAttribution(data);
    if (data !== this.shownData) {
      this.shownData = data;
      this.renderResults();
    }
  }

  private renderAttribution(data: WeatherData): void {
    const lines = attributionLines({
      live: Boolean(this.client),
      sampleRetrieved: data.source === 'sample' ? data.retrieved : undefined,
    });
    this.attribution.replaceChildren(
      ...lines.map((parts) =>
        el(
          'p',
          {},
          parts.map((p) =>
            p.href
              ? el('a', { href: p.href, rel: 'noopener', target: '_blank' }, [
                  p.text,
                ])
              : p.text,
          ),
        ),
      ),
    );
  }

  /** Recompute all ages and redraw table, answer and plot. */
  private renderResults(): void {
    const data = this.controller.state.data;
    if (
      this.message.classList.contains('error') &&
      !this.controller.state.error
    ) {
      this.message.textContent = '';
      this.message.className = 'weather-message';
    }
    this.comparisons = compareAllAges(data, this.tol, Date.now() / 1000);
    const ages = this.comparisons.map((c) => c.row.age);
    if (!ages.includes(this.age)) {
      this.age = ages[0] ?? 1;
    }
    this.ageSelect.replaceChildren(
      ...ages.map((a) =>
        el('option', { value: String(a) }, [ageWords(a).replace('made ', '')]),
      ),
    );
    this.ageSelect.value = String(this.age);

    const selected = this.comparisons.find((c) => c.row.age === this.age);
    if (!selected) {
      return;
    }
    const unit = data.unit;
    const row = selected.row;
    this.answer.textContent = answerLine(row, this.tol, unit);
    this.answer.className = `answer ${row.pass ? 'pass' : 'fail'}`;

    const first = data.time[0];
    const last = data.time[data.time.length - 1];
    const parts = [`${formatDateRange(first, last)} (UTC)`];
    parts.push(`${row.total - row.missing} hours compared`);
    if (row.missing > 0) {
      parts.push(`${row.missing} of ${row.total} hours missing`);
    }
    this.windowLine.textContent = parts.join(' · ');

    this.renderTable(unit);
    void this.renderPlot(selected, data);
  }

  private renderTable(unit: string): void {
    const head = el('thead', {}, [
      el('tr', {}, [
        el('th', { scope: 'col' }, ['Forecast made']),
        el('th', { scope: 'col' }, ['Verdict']),
        el('th', { scope: 'col' }, ['Hours outside the tube']),
      ]),
    ]);
    const body = el('tbody');
    for (const { row } of this.comparisons) {
      let badge: HTMLElement;
      let share: string;
      if (row.status === null) {
        badge = el('span', { class: 'status none' }, ['no data']);
        share = 'no forecast data';
      } else {
        const text = row.pass
          ? 'PASS'
          : row.status === Status.Fail
            ? 'FAIL'
            : statusName(row.status);
        badge = el('span', { class: `status ${row.pass ? 'pass' : 'fail'}` }, [
          text,
        ]);
        share =
          row.fractionOfPointsOutside === null
            ? '–'
            : `${formatPercent(row.fractionOfPointsOutside)} (${row.pointsOutside} of ${row.pointsCompared})`;
      }
      const tr = el(
        'tr',
        {
          tabindex: '0',
          'aria-selected': String(row.age === this.age),
          class: row.age === this.age ? 'selected' : '',
        },
        [
          el('td', {}, [ageWords(row.age).replace('made ', '')]),
          el('td', {}, [badge]),
          el('td', { class: 'num' }, [share]),
        ],
      );
      const select = (): void => {
        this.age = row.age;
        this.renderResults();
      };
      tr.addEventListener('click', select);
      tr.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          select();
        }
      });
      body.append(tr);
    }
    this.table.replaceChildren(
      el('caption', {}, [
        `Within ${formatTolerances(this.tol, unit)}, for every forecast age (select a row to plot it)`,
      ]),
      head,
      body,
    );
  }

  private async renderPlot(
    comparison: AgeComparison,
    data: WeatherData,
  ): Promise<void> {
    const token = ++this.plotToken;
    const { series, result, row } = comparison;
    if (!series || !result) {
      this.plot.replaceChildren(
        el('p', { class: 'formula' }, [
          'No forecast data for this window — nothing to plot.',
        ]),
      );
      return;
    }
    this.plotly ??= waitForPlotly();
    const plotly = await this.plotly;
    if (token !== this.plotToken) {
      return;
    }
    if (!plotly) {
      this.plot.replaceChildren(
        el('p', { class: 'formula' }, [
          'Plotly failed to load, so the plot is unavailable — results shown above.',
        ]),
      );
      return;
    }
    const ms = (a: Float64Array): Float64Array => a.map((v) => v * 1000);
    const variable = presetOf(data.variable);
    const unit = data.unit;
    this.plot.replaceChildren();
    try {
      await createFunnelPlot(
        plotly,
        this.plot,
        {
          reference: {
            x: ms(series.time),
            y: series.latest,
            name: 'latest run',
          },
          test: {
            x: ms(series.time),
            y: series.forecast,
            name: `forecast ${ageWords(row.age)}`,
          },
          result: {
            ...result,
            lowerX: ms(result.lowerX),
            upperX: ms(result.upperX),
            errorsX: ms(result.errorsX),
          },
        },
        {
          // The answer line above states place, age and tolerances.
          title: { text: '' },
          xaxis: {
            type: 'date',
            title: { text: 'time (UTC)' },
            tickformat: '%-d %b',
            hoverformat: '%-d %b %Y %H:%M UTC',
          },
          yaxis: { title: { text: `${variable.label}, ${unit}` } },
          yaxis2: {
            title: { text: `|error|, ${unit}` },
            overlaying: 'y',
            side: 'right',
            rangemode: 'tozero',
            showgrid: false,
          },
          legend: { orientation: 'h', x: 0, y: 1.02, yanchor: 'bottom' },
          margin: { t: 24, r: 64, b: 48, l: 64 },
        },
      );
    } catch (err) {
      this.plot.replaceChildren(
        el('p', { class: 'formula' }, [
          `Plot failed: ${(err as Error).message}`,
        ]),
      );
    }
  }
}
