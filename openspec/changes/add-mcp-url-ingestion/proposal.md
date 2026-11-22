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
  preamble, date-time time, column mapping) behaves as for a local file.
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
- **On-disk cache**: a fetched URL is stored in the user's cache
  directory; repeated calls with the same URL do not fetch again, and
  within one server session a URL always gives the same content, so
  results are reproducible across calls. Results name the URL, when it
  was fetched, its size and a content hash, so a verdict states exactly
  what was compared. The cache has a size limit.
- **Network can be switched off**: a start-up option and environment
  variable disable fetching entirely; a URL argument then fails with a
  clear message (whether cached copies are still served is settled in
  design). The tool annotations state the server may reach the network
  when fetching is enabled.
- **Open-Meteo forecast-vs-actual example**:
  - a small sample CSV bundled in the repository (one location, about
    15 days hourly, `temperature_2m` and its day-1/3/5 previous-run
    columns, a few kB, fixed past date range) with CC BY 4.0
    attribution ("Weather data by Open-Meteo.com", link to the
    licence, note of any changes), so tests and docs work offline;
  - documented live URLs with fixed `start_date` / `end_date`, so the
    same comparison can be run against the API;
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
- An example gallery beyond the Open-Meteo example.

## Capabilities

### New Capabilities

- `mcp-url-sources`: reading signal files from public URLs — which URLs
  are accepted, safety limits, what is (not) sent, the cache and its
  reproducibility guarantee, how network access is switched off, and
  what results report about a fetched file.
- `example-datasets`: example data shipped with the repository — the
  bundled Open-Meteo sample, its attribution, the documented live URLs,
  and the walkthrough that must keep working offline.

### Modified Capabilities

- `mcp-server`: "Stateless file access" today forbids network
  connections and any file write except plot files; it changes to allow
  fetching (when enabled) and writing the URL cache. Tool annotations
  change from closed-world when fetching is enabled. Workspace roots
  keep applying to local paths only. The snippet's handling of URL
  inputs is added.
- `mcp-plots`: `plot_signals` accepts URLs for its input files;
  output-path rules unchanged.

## Impact

- `python/simtest-funnel-mcp`: a new fetch/cache module, `csvio.py`
  (input from a fetched file), `server.py` (arguments, start-up options,
  annotations, descriptions), `snippet.py`, README; a new HTTP client
  dependency unless the standard library suffices (decided in design).
- Repository: the bundled sample CSV and its attribution (location to be
  chosen, e.g. an `examples/` folder), included in the package or only
  in the repository.
- **Depends on `add-mcp-column-mapping-and-formats`**: the Open-Meteo CSV
  has a metadata preamble, ISO 8601 times and reference/test as
  differently named columns in one file.
- **Relation to `add-cancellation`**: that change gives `compare_signals`
  and `plot_signals` a per-call time limit (60 s by default) but leaves
  CSV reading uncancellable. Fetch time counts toward the call, so the
  fetch timeout must stay well below the per-call limit, and a
  cancelled or timed-out call must not leave a partial file in the
  cache.
- Security posture of the server changes: it becomes able to send GET
  requests chosen by the model. The README documents this, the
  switch to turn it off and the address restrictions.
- Open points for design:
  - **Default on or off.** Fetching enabled by default with an opt-out
    switch, or disabled until the user opts in; and whether a host
    allow-list option is offered (a model-chosen URL can carry data in
    its query string).
  - **Cache lifetime.** Session-pinned only (fetch once per server
    session), or persistent across sessions with a maximum age and/or
    conditional revalidation (`ETag` / `Last-Modified`); whether a call
    can force a refresh; cache location and size limit.
  - **Offline mode and the cache.** When network access is off, serve
    URLs already in the cache or refuse every URL.
  - **Limits.** Default size cap (for example 20 MB) and timeouts
    (connect and total, below the 60 s call limit); redirect hop count;
    accepted content types (`text/csv`, `text/plain`,
    `application/csv`, `application/octet-stream`?).
  - **Proxies.** Honour `HTTPS_PROXY` (needed behind corporate proxies,
    but then the address check applies to the proxy, not the target) or
    ignore proxy settings.
  - **Snippets for URL inputs.** Embed the URL (CI needs network and the
    content may change), embed the URL plus the content hash and fail
    clearly on a mismatch, or advise vendoring the file.
  - **Sample details.** Which Open-Meteo weather model to pin (one
    whose upstream source is CC BY 4.0, rather than the default
    best-match blend, keeps attribution simple), `timeformat` ISO 8601
    (exercises the date-time support) versus `unixtime`, GMT versus a
    local time zone (Open-Meteo ignores daylight-saving changes in ISO
    local times), and whether the bundled file is kept byte-identical to
    the API response with the attribution in an adjacent file.
  - **HTTP client.** Standard library versus a dependency such as
    `httpx`, given the need to pin the connection to the checked
    address.
