# Proposal

## Why

The MCP server reads only local files. The owner's data sources, in
order of priority, are (1) local and CI result files, (2) public URLs,
(3) files uploaded to claude.ai. Priority 1 works today; this change
adds priority 2.

It also delivers the example that motivated it: a fun, real, public
comparison of a weather forecast against what happened, from
Open-Meteo, answering "was the forecast made N days ahead close enough?"
with a funnel tube (for example ±2 °C and ±3 h). A trial done by hand
(Stockholm, 15 days hourly; share of points outside the tube for the
day-1/3/5 forecasts: ±2 °C without time tolerance 2.2 / 25.3 / 32.0 %,
±2 °C ±3 h 0.6 / 9.7 / 19.5 %, ±1 °C ±3 h 5.3 / 46.8 / 47.4 %) shows the
story the tube tells: a time tolerance forgives forecasts that are right
but a few hours early or late, and skill drops clearly with lead time.
Today an agent has to download the CSV itself and pass a local path,
which defeats "the server reads the files, samples never enter the
model's context" when the agent has no file system of its own.

Open-Meteo's Previous Runs API
(`https://previous-runs-api.open-meteo.com/v1/forecast`) suits the
example: no API key, CSV output (`format=csv`), and for each variable
the forecasts made 1 to 7 days before the valid time
(`temperature_2m_previous_day1` ... `_previous_day7`) next to the
latest run. Its data is licensed CC BY 4.0; the free tier is for
non-commercial use only and is limited to fewer than 10,000 calls a day
(and 5,000 an hour, 600 a minute).

## What Changes

- **URLs wherever a path is accepted**: `describe_signals`,
  `compare_signals` and `plot_signals` accept a public `https://` URL
  in place of an input file path. Output paths (`plot_signals`
  `output_path`) stay local. Everything after fetching (dialect,
  `header_line`, date-time time, column pairs) behaves as for a local
  file.
- **Safety limits on every fetch**:
  - `https` only; redirects followed only to `https` and only a few
    hops, each hop checked again;
  - the host must resolve to public addresses only: loopback, private,
    link-local (including cloud metadata addresses), unique-local,
    multicast and unspecified addresses are refused, and the connection
    goes to the address that was checked;
  - a size cap (also after decompression) and a fetch timeout, both
    adjustable at server start-up;
  - content-type sanity: CSV and plain text are accepted, HTML pages are
    refused with a hint (typically a "view" page instead of the raw
    file);
  - no credentials are sent: no cookies, no `Authorization` header, no
    `.netrc`; URLs with a user name or password are refused; a generic
    `User-Agent` naming the server and its version.
- **Cache for the life of the server process only**: the first call
  that uses a URL fetches it; later calls in the same server process
  reuse that copy, so within one process a URL always gives the same
  content and results are reproducible across calls. The copies live in
  a private temporary directory that is removed when the server stops
  (also on abnormal exit as far as practical). There is no cache across
  sessions, no revalidation and no offline mode serving cached copies.
  Results name the URL, when it was fetched, its size and its SHA-256,
  so a verdict states exactly what was compared.
- **Fetching counts against the per-call time limit** of
  `add-cancellation` (60 s by default); a cancelled or timed-out call
  leaves no partial cache entry.
- **Network access is off by default**: a plain install keeps the
  existing "local files only" guarantee. The user enables fetching when
  starting the server with `--allow-network` or the environment variable
  `SIMTEST_FUNNEL_MCP_ALLOW_NETWORK=1`, optionally restricted to given
  hosts with a repeatable `--allow-host HOST` (also
  `SIMTEST_FUNNEL_MCP_ALLOW_HOSTS`, comma-separated); `--allow-host`
  implies `--allow-network`. With network access off, a URL argument is
  refused with a message naming the option and the environment variable.
  The tool annotations state the server may reach the network only when
  fetching is enabled.
- **Direct connections only**: the first version connects directly to
  the target host. Proxy environment variables (`HTTPS_PROXY`,
  `HTTP_PROXY`, `ALL_PROXY`, `NO_PROXY`) are ignored, so the public
  address check always applies to the real target. When a fetch fails to
  connect, the message says proxies are not supported yet and suggests
  downloading the file and passing the local path.
- **Open-Meteo forecast-vs-actual example**:
  - a small sample CSV bundled in the repository (one location, about
    15 days hourly, `temperature_2m` and its day-1/3/5 previous-run
    columns, a few kB, fixed past date range) with CC BY 4.0
    attribution ("Weather data by Open-Meteo.com", link to the
    licence, note of any changes), so tests and docs work offline;
  - documented live URLs with fixed `start_date` / `end_date`, so the
    same comparison can be run against the API (with the server started
    with `--allow-network`, or `--allow-host
    previous-runs-api.open-meteo.com`);
  - a README walkthrough: describe, compare the day-1/3/5 forecasts
    against the latest run with a few tolerance tubes, plot one;
  - the walkthrough says plainly that the "actual" column is the latest
    model run / analysis, not station measurements, that dates in the
    future hold forecasts in both columns, and that Open-Meteo's free
    tier is for non-commercial use only.
- Tests run offline: fetching is tested against a local test server or
  a mocked transport; no test calls Open-Meteo in CI (an optional live
  check may exist behind an explicit switch).

Explicitly out of scope:

- Authenticated sources (tokens, cookies, signed URLs needing headers,
  private repositories).
- Formats other than CSV (JSON, XLSX, Parquet, NetCDF), even where the
  source offers them.
- Files uploaded to claude.ai (priority 3; a later change,
  `add-claude-skill`).
- A remote-hosted server (`add-mcp-remote-deploy`); this change is for
  the local stdio server only.
- Plain `http://` and `file://` URLs.
- Proxy support (`HTTPS_PROXY` and similar); a later change may add it
  with the address check applied appropriately.
- A persistent cache (across server processes), revalidation and an
  offline mode serving cached copies.
- An example gallery beyond the Open-Meteo example.

## Capabilities

### New Capabilities

- `mcp-url-sources`: reading signal files from public URLs — which URLs
  are accepted, safety limits, what is (not) sent, the cache and its
  reproducibility guarantee, how network access is enabled at start-up
  (off by default, optional host allow-list), direct connections only,
  and what results report about a fetched file.
- `example-datasets`: example data shipped with the repository — the
  bundled Open-Meteo sample, its attribution, the documented live URLs,
  and the walkthrough that must keep working offline.

### Modified Capabilities

- `mcp-server`: "Stateless file access" today forbids network
  connections, any state between calls and any file write except plot
  files; it changes to allow fetching (only when enabled at start-up)
  and the process-lifetime URL cache. The tool annotations become
  open-world when fetching is enabled. Workspace roots keep applying to
  local paths only. The time limit covers fetching, and fetching is
  stopped at the deadline. The snippet's handling of URL inputs is
  added.
- `mcp-plots`: `plot_signals` accepts URLs for its input files;
  output-path rules unchanged (local only, checked before any fetch);
  annotations as for the other tools.

## Impact

- `python/simtest-funnel-mcp`: a new fetch/cache module, `csvio.py` and
  `server.py` path handling (a URL is fetched to the cache and then read
  like a local file), `server.py` (start-up options, annotations,
  descriptions, `describe_signals` run off the event loop), `models.py`
  (source information), `snippet.py`, README. No new installed package:
  the standard library does the fetching (design.md, decision 2).
- Repository: the bundled sample in `examples/open-meteo/` with its
  attribution, in the repository only, not in the published wheel or
  sdist (design.md, decision 12).
- **Depends on `add-mcp-column-mapping-and-formats`**: the Open-Meteo CSV
  has a metadata preamble, ISO 8601 times and reference/test as
  differently named columns in one file.
- **Relation to `add-cancellation`**: that change gives `compare_signals`
  and `plot_signals` a per-call time limit (60 s by default) but leaves
  CSV reading uncancellable. Fetch time counts toward the call and the
  fetch is stopped at the deadline; the fetch timeout stays below the
  default call limit; a cancelled or timed-out call leaves no partial
  file and no entry in the cache.
- Security posture of the server changes only when the user opts in:
  with `--allow-network` it can send GET requests chosen by the model.
  The README documents this, the option, the host allow-list (a
  model-chosen URL can carry data in its query string) and the address
  restrictions.
- The remaining details (limits, address check and HTTP client,
  concurrency, snippets, interactions with `header_line` / `pairs` /
  `output_path`, annotations, what `describe_signals` shows, sample
  details) are worked out in design.md, each marked as a design choice
  not yet confirmed by the owner.

## Decisions

Decided by the owner (binding for design and specs):

1. **Network access off by default.** Enabled at start-up with
   `--allow-network` / `SIMTEST_FUNNEL_MCP_ALLOW_NETWORK`, optionally
   restricted with a repeatable `--allow-host`. With network off, URL
   arguments are refused with a message naming the option. A plain
   install keeps the "local files only" guarantee.
2. **No proxies in the first version.** Direct connections only; proxy
   environment variables are ignored; on failure the message says
   proxies are not supported yet and suggests downloading the file and
   passing the local path.
3. **Cache for the life of the server process only.** The first use of
   a URL fetches it; later calls in the same process reuse that copy;
   the cache is removed when the server stops (and cleaned up on
   abnormal exit as far as practical; design.md says what happens to
   leftovers). No cross-session cache, no revalidation, no offline mode
   serving cached copies. Results report the URL, fetch time, size and
   SHA-256.
4. **Fetching counts against the per-call `time_limit`** (60 s default)
   of `add-cancellation`; a cancelled or timed-out call leaves no
   partial cache entry.
