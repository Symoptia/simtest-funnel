# simtest-funnel-mcp

A local [MCP](https://modelcontextprotocol.io) server that lets AI agents
(Claude Code, Claude Desktop, any MCP client) compare signals stored in
local CSV files with the funnel (tolerance-tube) algorithm of
[simtest-funnel](https://github.com/Symoptia/simtest-funnel), a port of
[LBNL Funnel](https://github.com/lbl-srg/funnel).

The server reads the files itself, so raw samples never enter the model's
context. It is stateless: every call names the files it reads, and by
default no network connection is opened. Started with `--allow-network`
(or `--allow-host HOST`), it also reads public `https://` URLs (see
[Reading files from URLs](#reading-files-from-urls)); a worked example is
[Was the forecast made N days ahead close enough?](#example-was-the-forecast-made-n-days-ahead-close-enough).
`describe_signals` and `compare_signals` are
read-only; `plot_signals` writes exactly the plot file it is given (and
nothing at all without `output_path`), and only inside a workspace root
declared by the client or an output directory configured at start-up (see
[Where plot files may be written](#where-plot-files-may-be-written)).
Transport: stdio.

> **Platform note:** `simtest-funnel` is currently published to PyPI only
> as a Linux x86-64 / CPython 3.12 wheel, so `uvx simtest-funnel-mcp`
> works only there until cross-platform wheels are published. From a
> checkout of this repository it works wherever the Rust extension builds.

## Tools

### `describe_signals(path, columns=None, max_columns=100, header_line=1)`

Header line used, time column (how it was chosen and its kind: `numeric`
or `datetime`, with or without time zone), row count, time start/end/span
(on a date-time axis also as ISO 8601 strings and durations), sampling
(uniform or not; min/median/max step), per-column min/max/range and data
problems (non-numeric or empty cells, time not non-decreasing, time column
without time zone, a preamble hint with the `header_line` to pass).
Use it to choose columns and tolerances. At most `max_columns` columns and
as many problems are listed; `columns_total`, `columns_selected`,
`columns_omitted` and `problems_omitted` state the rest. `columns` filters
by exact name or glob pattern (`*`, `?`, `[...]`), e.g.
`["*.port.signal"]`.

### `compare_signals(reference_path, test_path=None, ...)`

| Argument | Default | Meaning |
| --- | --- | --- |
| `test_path` | the reference file (with `pairs` only) | Test CSV file; required unless `pairs` are given |
| `columns` | all common columns | Signal columns to compare: exact names or glob patterns (`*`, `?`, `[...]`, matched against the columns of both files) |
| `pairs` | none | `[{"reference": .., "test": .., "label": ..}]`: compare a reference column with a differently named test column (exact names; not together with `columns`) |
| `header_line` | 1 | Header line of the reference file (see [CSV dialect](#csv-dialect)) |
| `test_header_line` | `header_line` | Header line of the test file |
| `tolerances` | one set, library default | List of sets: optional unique `label` plus any of the six coefficients |
| `column_tolerances` | none | `{row key: coefficients}` overrides, applied per axis (the key is the column name, or a pair's label, else its test column) |
| `x_range` | unbounded | `{"lo": .., "hi": ..}` time window; finite bounds (on a date-time axis numbers are epoch seconds, or ISO 8601 strings), omit one for unbounded |
| `max_intervals` | 5 | Violation intervals listed per failing row (largest deviation first) |
| `max_rows` | 100 | Rows returned (errors, then failures, then passes); totals always cover all rows |
| `include_snippet` | false | Add a pytest file reproducing the returned rows (for CI), in the structured field `snippet` |
| `time_limit` | 60 | Deadline in seconds for the whole call, counted from its start, fetching (URLs) and reading the files included (positive); see [Time limit and cancellation](#time-limit-and-cancellation) |

The result has one row per (column, tolerance set) with verdict
(`pass` / `fail` / `error`), the library status code, points outside the
tube, fractions of points and span outside, the worst deviation and, for
failures only, the violation intervals. Missing columns, bad data and
other per-column problems are reported in their rows instead of failing
the call. Both structured content and a short text rendering are returned.
Time values are never rounded in the structured content; the text prints
them with enough digits to tell adjacent samples apart.

**Column pairs.** Without `columns` or `pairs`, every signal column present
in both files is compared with the column of the same name. `pairs`
compares differently named columns, from two files or from one (omit
`test_path`; the file is then read once). One reference column may appear
in several pairs. Names are exact and case-sensitive, units in names such as
`(°C)` are part of the name; a name that is not found gives a row error
suggesting close names (e.g. `temperature_2m` -> `temperature_2m (°C)`). A
pair's row is keyed (`column`) by its label, else its test column; keys must
be unique, and pair rows also carry `reference_column` and `test_column`.
Without `pairs` a `test_path` is required (a file compared with itself
would pass trivially).

A column passes when every test point inside the compared time range
(`x_range` intersected with the reference time span) lies inside the tube
and, within `x_range`, both files cover the same time span. If one file
covers more time than the other within `x_range`, the row has verdict
`error` with status `MISSING_REFERENCE` (test extends beyond the
reference) or `MISSING_TEST` (the reverse), still reports
`points_compared` / `points_outside`, and its `problem` text names both
time spans and the exact `x_range` that compares the overlap.

### `plot_signals(reference_path, column, test_path=None, test_column=None, ...)`

Draws ONE comparison - one signal column (or one reference column against
a differently named test column), one tolerance set - and returns a
PNG preview (800 x 450 px) inline as MCP image content, so the model can
look at it. SVG is never returned inline (it would reach the model as text).

| Argument | Default | Meaning |
| --- | --- | --- |
| `column` | required | The one signal column to plot (exact name, no glob patterns); the reference column |
| `test_path` | the reference file | Test CSV file |
| `test_column` | `column` | Test column plotted against `column`, like one `compare_signals` pair (legend and title then name both) |
| `header_line`, `test_header_line` | 1, `header_line` | As in `compare_signals` |
| `tolerance` | library default | One tolerance set: optional `label` plus any of the six coefficients (one entry of `compare_signals` `tolerances`) |
| `x_range` | unbounded | As in `compare_signals`; also the time window shown (zoom) |
| `output_path` | none | Write the plot here: `.svg` (document) or `.png` (1600 x 900 px), inside a workspace root or a configured output directory. Omit for the preview only |
| `overwrite` | false | Replace `output_path` if it exists (refused otherwise) |
| `max_intervals` | 5 | Violation intervals listed in the result row (all are drawn) |
| `time_limit` | 60 | Deadline in seconds for the whole call (reading, comparison, rendering); when reached the call fails and nothing is written |

The plot shows the reference (dark grey, dashed), the test (blue, solid),
the tolerance tube (grey band between thin lower and upper bound lines) and
every region where the test leaves the tube (red shading, with `x` markers
on the violating test points). The title states the column, the verdict,
the points outside and the non-zero resolved tolerances; the axes are
labelled with the time column and the signal column; a legend sits below the
axes. The background is white, so plots stay readable on light and dark
pages (on a dark page they appear as a light card).

The comparison runs on the full data with exactly the semantics of
`compare_signals`; the result carries the same summary row (plus the file
written, the preview size and how many points were drawn), never sample
values. For drawing, reference, test and both tube bounds are reduced to
the min/max of 1000 time buckets (the test keeping the worst point of every
violation interval), so the SVG stays fully vector and small (a few hundred
kB at most for 200 000 samples). Where needed, the exact bound value at a
drawn test point is added to the drawn bound, so a plot never contradicts
the verdict: every drawn test point lies inside or outside the drawn tube
exactly as the comparison judged it (violating points at least as far
outside as their deviation), every violation interval is shaded (at least
~3 px wide, even for a single sample) and contains a marked test point, and
in a passing plot no drawn test point lies outside the drawn tube. A column
that cannot be compared (missing, bad data, differing time spans,
non-monotonic time) is an error and nothing is written.

Output files: the file must lie inside a workspace root or a configured
output directory (below); a relative `output_path` is taken relative to the
first workspace root, else the first output directory; the directory must
already exist (none is created); a symbolic link must point to a file with
the same extension; an existing file is refused unless `overwrite=true`.
These checks run before any CSV file is read or any URL fetched; a URL as
`output_path` is refused. The file is written only
after rendering succeeded, under a temporary name in the target directory,
and moved into place (atomically replacing an existing file with
`overwrite=true`; never replacing one without it) only if the call is
still live, so a failed, cancelled or timed-out call writes nothing and no
partial file ever appears. Because the checks run up to a minute before
the write, the write itself does not trust the checked path: on Linux and
macOS it works on a handle of the target directory, opened without
following a symbolic link and verified to lie inside a workspace root or
output directory immediately before the file is moved into place, and a
symbolic link at the file name is replaced, never followed. (On Windows
the directory is resolved and checked again immediately before the write,
which narrows but cannot close that window.) The reported `file.path` is
where the file was written. Output is deterministic: the same input gives
byte-identical SVG and PNG files (with the same matplotlib version), so
plots can be kept in a repository and diffed. SVG text is embedded as
paths (bundled DejaVu Sans), so files look the same everywhere.

On a date-time time axis the x data stay epoch seconds (so the drawing
agrees with the comparison exactly), the ticks are UTC-aligned dates and
times (`MM-DD hh:mm`, the year on the first tick and at year changes), the
x label ends in `(UTC)` or `(no time zone)`, the subtitle shows the time
tolerance as a duration (`x ±PT3H`) and the result's `view` carries
`lo_iso` / `hi_iso`.

Plots are rendered with [matplotlib](https://matplotlib.org) (headless,
imported only on the first `plot_signals` call, so server start-up is not
slowed). It adds about 24 MB of wheels (~77 MB installed). matplotlib
keeps a font cache in its cache directory (`~/.cache/matplotlib`, or
`$MPLCONFIGDIR`), created on first use in an environment; that is the only
other file touched.

### Time limit and cancellation

Comparisons run in a worker thread without holding the Python interpreter
lock, so the server keeps answering other requests while one runs.
Comparisons usually take well under a second even for a million samples;
a nearly noise-free signal with a large time tolerance (`rtolx`/`atolx`)
can take much longer.

- `time_limit` (seconds, default 60) is a deadline for the whole call,
  counted from its start: fetching URL inputs and reading the CSV files
  count against it (and, for `plot_signals`, rendering); a fetch is stopped
  at the deadline. Comparisons start only while time
  remains, and a running one stops when the limit is reached. Reading and
  rendering are not interrupted, so a call can overrun the limit by the
  time they take.
- `compare_signals` then still succeeds: `rows` hold the comparisons that
  finished (server-detected problems such as missing columns included),
  `not_completed` lists the `{column, tolerance_set}` pairs that did not
  (capped at `max_rows`, the rest counted in `not_completed_omitted`),
  `totals.not_completed` counts them, `time_limit_reached` is `true` and a
  note suggests a larger `time_limit`, fewer columns or a narrower
  `x_range`. The text shows them on a `NOT COMPLETED (time limit)` line; a
  requested snippet covers the finished rows only. When everything
  finishes, none of these fields appear.
- `plot_signals` is one comparison: when the limit is reached the call
  fails with an error naming the limit and nothing is written. The limit
  and cancellation are checked before rendering and again immediately
  before the file is moved into place.
- When the client cancels a call (MCP `notifications/cancelled`, e.g. the
  user interrupts the agent), the running comparison stops within
  milliseconds and no further comparison of that call is started. A
  cancelled `plot_signals` call never writes its file, also when the
  cancellation arrives after the comparison, while rendering.

### Pytest snippet

With `include_snippet=true` the result carries a self-contained pytest
module (structured field `snippet`, sent once; the text rendering only
points to it) that asserts the observed status of every returned row; rows
omitted by `max_rows` are listed as a comment, and the snippet is capped
at 64 kB. It embeds the server's CSV reader verbatim. Data paths under the
first workspace root (else the server's working directory) are written
relative to it and resolved at run time against
`$SIMTEST_FUNNEL_DATA_ROOT`, defaulting to the current directory, so run
pytest from the same place in a CI checkout. Files outside that base keep
their absolute path, with a comment that they will not resolve elsewhere.
The snippet reads each file with the header line the server used
(`REFERENCE_HEADER_LINE` / `TEST_HEADER_LINE`, `TEST = REFERENCE` for one
file), converts date-time time columns exactly as the server does, and
each case `(key, reference column, test column, tolerance set, tolerances,
expected status)` compares its own reference and test column; ISO x-range
bounds are written as epoch seconds with the ISO form in a comment.

## CSV dialect

Comma-separated, one header row (UTF-8, optional BOM). Lines whose first
non-blank character is `#` and blank lines are ignored; a `#` anywhere
else is data (e.g. a column `a#1`). A data row with more fields than the
header is an error naming the row and line; a trailing delimiter on every
line, header included, is accepted (the empty last column is dropped).
Short rows count as empty cells. The time column is the first column named
`time` (case-insensitive), otherwise the first column; the choice is
echoed back. Other columns whose name differs from `time` only by case are
ordinary signal columns.

**Header line.** `header_line` (1-based physical file line, default 1)
skips the lines before it unread; the header is the first non-blank,
non-comment line at or after it, so the default is the first non-comment
line, as always. Data row line numbers in errors stay physical file lines.
The header line is never detected automatically. When a read fails, or
succeeds but looks wrong (the header has a different field count than a
later header-like line, or the time column has bad cells), and the top of
the file looks like a preamble (a blank line followed by a line without
numbers whose next line looks like data with the same field count), the
error or a problem says so and suggests that line, e.g. `pass
header_line=4`. The hint never changes what is read.

**Date-time time column.** A time column whose non-empty cells are all ISO
8601 date-times (`YYYY-MM-DD`, optionally `T` or a space and `hh:mm`,
optional seconds and fraction, optional `Z` or an offset `+hh:mm`, `+hhmm`
or `+hh`) is read as seconds since 1970-01-01 UTC, so a file and its copy
with epoch-second times give identical results. Date-only cells are
midnight. Hours run 00-23, invalid dates are not date-times, and only upper
case `T` and `Z` are accepted. Other formats (`01/02/2026`, Excel serial
dates) are not recognised; such a column is non-numeric. A cell without
offset is read as UTC and `describe_signals` reports that the column has no
time zone; offsets are converted to UTC. Reference and test time columns
must be of the same kind: both numeric, both without time zone, or both
with offsets (otherwise the call fails explaining how to fix it); a column
mixing cells with and without offset is a time-column problem. Only the
time column is converted; date-times in signal columns are non-numeric.

On a date-time axis x tolerances and numeric `x_range` bounds are seconds
(`atolx = 10800` is ±3 h), `x_range` bounds may also be ISO strings (with a
time zone exactly when the time columns have one), a non-zero `ltolx` is
refused (it would scale with ~1.8e9 s), every tolerance set with a non-zero
time half-width echoes it as `time_tolerance: {"seconds": 10800,
"duration": "PT3H"}` (also from `rtolx`), and every time in the results
keeps its number and gains an ISO 8601 sibling (`time_start_iso`,
`lo_iso`, `x_iso`, `start_x_iso`, ...; UTC with `Z` for offset axes,
without suffix for zone-less ones). The text rendering prints ISO times and
durations.

Example: an Open-Meteo Previous Runs CSV starts with a metadata line, a
values line and a blank line, then the header
`time,temperature_2m (°C),temperature_2m_previous_day1 (°C),...` with times
such as `2026-11-20T00:00`. "Was the forecast made 1, 3 and 5 days ahead
within 2 °C and 3 hours?":

```json
{
  "reference_path": "/data/stockholm.csv",
  "header_line": 4,
  "pairs": [
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day1 (°C)", "label": "day1"},
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day3 (°C)", "label": "day3"},
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day5 (°C)", "label": "day5"}
  ],
  "tolerances": [{"label": "2C_3h", "atoly": 2, "atolx": 10800}],
  "x_range": {"lo": "2026-11-06T00:00"}
}
```

## Tolerances

Six coefficients, x = time axis, y = signal value. At each reference sample
the tube half-widths are

```text
half_x = max(atolx, rtolx * time_span_ref, ltolx * |t|)
half_y = max(atoly, rtoly * value_range_ref, ltoly * |y_ref|)
```

- `atol*`: absolute (time units / signal units; seconds on a date-time axis)
- `rtol*`: fraction of the reference time span / value range
- `ltol*`: fraction of the local `|t|` / `|y_ref|`

If a half-width comes out effectively zero (`< 1e-10`), e.g. `rtoly` alone
on a constant reference (value range 0), it falls back to
`rtol * max|reference value|` on that axis (when `rtol > 0`), and finally
to `1e-10`. For constant or near-constant signals give `atoly` explicitly.

Omitted coefficients are resolved by the library, per axis: an axis with no
coefficient given gets its default — on the x axis all `0` (no time
tolerance), on the y axis `rtoly = 0.002`; an axis with any coefficient
given uses `0` for its others; an explicit `0` counts as given. The six
resolved values are always echoed back.

**Tolerance in x** widens the tube along time, so a test signal shifted or
delayed by up to `half_x` still passes; steep edges and small timing
offsets then do not cause false failures. There is **no tolerance in x
unless you give one**: with x tolerance `0` the x half-width is the `1e-10`
floor, so each test point is checked only against the y band around the
reference at the same time and a slightly delayed steep edge fails. Prefer
`atolx` (time units): `rtolx` is a fraction of the whole time span and grows
with the length of the record (`rtolx = 0.002` allows 43 minutes on 15 days
of data). When a row fails and no x coefficient was given for it,
`compare_signals` and `plot_signals` add a note:

```text
1 failing row(s) had no x (time) tolerance: none was given and the default is 0.
If the test may be shifted or delayed in time against the reference (e.g. at
steep edges), consider an x tolerance such as atolx (time units)
```

"1 % in y, 0.5 s in x" is `{"rtoly": 0.01, "atolx": 0.5}` (or `ltoly` for
1 % of the local value).

## Reading files from URLs

Network access is **off by default**: a plain start reads local files only,
opens no network connection and creates no file or directory besides the
plot files it is asked for. A URL argument is then refused with a message
naming `--allow-network` and `SIMTEST_FUNNEL_MCP_ALLOW_NETWORK`.

When enabled at start-up, `describe_signals`, `compare_signals` and
`plot_signals` accept a public `https://` URL wherever they accept an input
path (`path`, `reference_path`, `test_path`); `output_path` stays a local
path. A fetched file is read exactly like a local one (`header_line`,
`pairs`, date-time time column).

| Option | Environment variable | Default |
| --- | --- | --- |
| `--allow-network` | `SIMTEST_FUNNEL_MCP_ALLOW_NETWORK` (`1`/`true`/`yes`/`on`, or `0`/`false`/`no`/`off`/empty; anything else stops the server at start-up) | off |
| `--allow-host HOST` (repeatable; implies `--allow-network`) | `SIMTEST_FUNNEL_MCP_ALLOW_HOSTS` (comma-separated; united with the options) | any public host |
| `--max-download-mb MB` | `SIMTEST_FUNNEL_MCP_MAX_DOWNLOAD_MB` | 20 (1 MB = 1,000,000 bytes) |
| `--fetch-timeout SECONDS` (at most 600) | `SIMTEST_FUNNEL_MCP_FETCH_TIMEOUT` | 30 |

For the numbers the command line wins over the environment. Prefer
`--allow-host`: the model chooses the URLs, and a URL can carry data from
the conversation in its query string to whatever host it names. Host
entries are exact host names (case-insensitive, IDNA; no wildcards,
subdomains not included, no scheme, port or path). Registration examples:

```bash
claude mcp add simtest-funnel -- uvx simtest-funnel-mcp --allow-host previous-runs-api.open-meteo.com
```

```json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uvx",
      "args": ["simtest-funnel-mcp", "--allow-host", "previous-runs-api.open-meteo.com"],
      "env": { "SIMTEST_FUNNEL_MCP_ALLOW_HOSTS": "raw.githubusercontent.com" }
    }
  }
}
```

(Claude Desktop: `claude_desktop_config.json`; Claude Code: a project's
`.mcp.json`. From a checkout, append the options after
`"simtest-funnel-mcp"` in the `uv run` arguments.)

**What is fetched, and how.**

- Only `https` URLs with a host; `http`, `file` and other schemes, and URLs
  with a user name or password, are refused (also with network access off).
- The host is resolved once and every address must be public: loopback,
  private (RFC 1918), link-local (including cloud metadata addresses such
  as `169.254.169.254`), unique-local, CGNAT, multicast, unspecified,
  reserved and documentation addresses are refused, also when embedded in
  IPv6 forms (IPv4-mapped, NAT64, 6to4; Teredo is refused). A host with any
  such address is refused as a whole. The connection goes to an address
  that was checked (no second lookup), while TLS verifies the certificate
  against the URL's host name with the operating system's trust store.
- Redirects (at most 5) are followed only to `https` URLs, and every hop
  is checked again (scheme, allowed hosts, addresses, certificate).
- Only a plain `GET` is sent: no cookies, no `Authorization`, nothing from
  `.netrc` or the environment, and a `User-Agent` naming only
  `simtest-funnel-mcp`, its version and the project link.
- Status 200 and CSV, plain text, generic binary or no content type, in
  UTF-8 or ASCII, uncompressed or gzip, are accepted. An HTML page (by type
  or first bytes) is refused with a hint to use the raw-file URL; JSON is
  refused with a hint to ask the service for CSV (e.g. `format=csv`). Other
  statuses fail with the status and up to 300 characters of a short text or
  JSON body (where services such as Open-Meteo put the reason).
- Size cap (after decompression) and fetch timeout as above; connecting
  times out after 10 s per address. For `compare_signals` and
  `plot_signals` the fetch counts against `time_limit` and is stopped at
  the deadline; cancelling a call (also `describe_signals`) stops its fetch
  at once.
- **No proxies.** The server connects directly and ignores `HTTPS_PROXY`,
  `HTTP_PROXY`, `ALL_PROXY` and `NO_PROXY`, so the address check always
  applies to the real target. Behind a proxy, download the file and pass
  its local path (a failed connection says so).

**Cache.** The first call that uses a URL fetches it; later calls in the
same server process reuse that copy without connecting, so a URL gives the
same content for the life of the process (restart the server to fetch it
again; there is no refresh argument and no cache across processes). Two
calls needing the same URL at once share one fetch. A failed, cancelled or
timed-out fetch leaves nothing behind. Copies live in a private directory
`simtest-funnel-mcp-*` in the system temporary directory, created on the
first fetch and removed when the server stops (end of input, SIGTERM on
Linux/macOS). After a crash, `SIGKILL` or a forced termination on Windows
the directory stays until the operating system cleans its temporary
directory or you delete it; it holds only public files the server fetched,
readable only by your user. The cache holds at most 10 times the size cap;
older copies are dropped and fetched again when needed, and if the content
changed meanwhile the call fails saying so.

**Results** carry, for each URL input, `path` = the URL and a `source`
object: `url`, `final_url` (when redirected), `fetched_at` (UTC),
`size`, `sha256` and `reused` (false for the call that fetched it). The
text shows the URL with fetch time, size and the first 12 hex digits of the
hash. The cache's file names are never shown.

**Snippets** never fetch. For a URL input the pytest snippet reads a local
copy, `DATA_ROOT / <name>` (the URL's last path segment, e.g.
`forecast.csv`), and before comparing checks its SHA-256 against the one
the server saw; the comment above names the URL and the fetch time. When
the copy is missing or different, every case fails with the URL, the
expected path and hash and what to do. Run the snippet once with
`SIMTEST_FUNNEL_DOWNLOAD=1` to download a missing copy (standard library,
`https` only, at most the recorded size, 60 s timeout; kept only if its
SHA-256 matches, never replacing an existing file), then commit the file:
CI then runs without network access.

## Example: was the forecast made N days ahead close enough?

[Open-Meteo](https://open-meteo.com/)'s Previous Runs API returns, for each
hour, the latest model run next to the forecasts made 1 to 7 days before.
The repository bundles one response,
[`examples/open-meteo/stockholm-2026-11-05-to-19.csv`](../../examples/open-meteo/stockholm-2026-11-05-to-19.csv):
Stockholm, 15 days hourly (360 rows), `temperature_2m` and its day-1, day-3
and day-5 forecasts from ECMWF IFS HRES (`ecmwf_ifs`), times in GMT.
[Weather data by Open-Meteo.com](https://open-meteo.com/), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), not modified;
see [ATTRIBUTION.md](../../examples/open-meteo/ATTRIBUTION.md).

Caveats: the "actual" column is the latest model run / analysis, not
measured station temperature; for dates in the future both columns hold
forecasts; times are GMT. Open-Meteo's free API is for non-commercial use
only and limited to fewer than 10,000 calls a day.

The calls below use the bundled file (use its absolute path); the server
needs no network access for them.

1. Describe it. The file starts with a three-line metadata preamble, so the
   header is on line 4:

   ```jsonc
   // describe_signals
   {"path": "examples/open-meteo/stockholm-2026-11-05-to-19.csv", "header_line": 4}
   ```

   Result: 360 rows, time column `time` read as ISO 8601 date-times without
   time zone (read as UTC), 2026-11-05T00:00 .. 2026-11-19T23:00, uniform
   hourly; columns `temperature_2m (°C)` (-0.8 .. 8.8),
   `temperature_2m_previous_day1 (°C)`, `..._previous_day3 (°C)`,
   `..._previous_day5 (°C)`.

2. Compare the latest run against each forecast, once within ±2 °C and once
   within ±2 °C and ±3 hours (`atolx` is in seconds on a date-time axis):

   ```jsonc
   // compare_signals
   {
     "reference_path": "examples/open-meteo/stockholm-2026-11-05-to-19.csv",
     "header_line": 4,
     "pairs": [
       {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day1 (°C)", "label": "day1"},
       {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day3 (°C)", "label": "day3"},
       {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day5 (°C)", "label": "day5"}
     ],
     "tolerances": [
       {"label": "2C", "atoly": 2},
       {"label": "2C_3h", "atoly": 2, "atolx": 10800}
     ]
   }
   ```

   Share of points outside the tube (of 360):

   | Forecast | ±2 °C | ±2 °C and ±3 h |
   | --- | --- | --- |
   | `day1` (made 1 day ahead) | pass, 0 of 360 (0.0 %) | pass, 0 of 360 (0.0 %) |
   | `day3` (made 3 days ahead) | fail, 38 of 360 (10.6 %) | fail, 14 of 360 (3.9 %) |
   | `day5` (made 5 days ahead) | fail, 84 of 360 (23.3 %) | fail, 47 of 360 (13.1 %) |

   The day-1 forecast stays within 2 °C all the time. Skill drops with lead
   time, and the time tolerance forgives forecasts that had the right
   temperature a few hours early or late: with ±3 h, day 3 misses only
   around a warm spell on 16 November and a cold night on 19 November.

3. Plot the day-3 pair with the ±2 °C ±3 h tube (inline preview; add
   `output_path` to save an SVG or PNG):

   ```jsonc
   // plot_signals
   {
     "reference_path": "examples/open-meteo/stockholm-2026-11-05-to-19.csv",
     "header_line": 4,
     "column": "temperature_2m (°C)",
     "test_column": "temperature_2m_previous_day3 (°C)",
     "tolerance": {"label": "2C_3h", "atoly": 2, "atolx": 10800}
   }
   ```

**The same from URLs.** With the server started with
`--allow-host raw.githubusercontent.com`, the raw repository URL of the
sample gives the same bytes (and the same numbers) once the file is on the
`main` branch:

```text
https://raw.githubusercontent.com/Symoptia/simtest-funnel/main/examples/open-meteo/stockholm-2026-11-05-to-19.csv
```

With `--allow-host previous-runs-api.open-meteo.com` (or `--allow-network`),
the live request that produced the sample can be passed as
`reference_path` instead:

```text
https://previous-runs-api.open-meteo.com/v1/forecast?latitude=59.3293&longitude=18.0686&hourly=temperature_2m,temperature_2m_previous_day1,temperature_2m_previous_day3,temperature_2m_previous_day5&models=ecmwf_ifs&start_date=2026-11-05&end_date=2026-11-19&format=csv
```

It compares the same columns; Open-Meteo may reprocess archived runs, so
the bytes (and `source.sha256`) can differ from the bundled copy. Each
call to the live URL counts against Open-Meteo's free-tier limits (once
per server process, thanks to the cache).

## Registering the server

### Claude Code

Once published to PyPI:

```bash
claude mcp add simtest-funnel -- uvx simtest-funnel-mcp
```

From a checkout of this repository (use `--scope user` to make it available
in every project):

```bash
claude mcp add simtest-funnel -- uv run --directory /path/to/simtest-funnel --quiet simtest-funnel-mcp
```

Inside this repository nothing needs to be registered: the checked-in
[`.mcp.json`](../../.mcp.json) starts the server with `uv run` from the
workspace (Claude Code asks for approval the first time).

### Claude Desktop

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uvx",
      "args": ["simtest-funnel-mcp"]
    }
  }
}
```

or, from a checkout:

```json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/simtest-funnel", "--quiet", "simtest-funnel-mcp"]
    }
  }
}
```

Use absolute paths in tool calls. When the client declares workspace roots,
the server refuses local paths outside them and resolves relative paths
against the first root (URLs are not affected by roots). Only local `file://` roots (empty host or `localhost`)
are used; other roots are ignored with a note in the result.

### Where plot files may be written

`plot_signals` writes a file only

1. inside a workspace root declared by the client (Claude Code declares the
   project directory), or
2. inside an output directory configured when the server is started:
   `--output-dir DIR` (repeatable) and/or the environment variable
   `SIMTEST_FUNNEL_MCP_OUTPUT_DIR` (several directories separated by `:`,
   `;` on Windows).

When both exist, a path inside either is allowed. With neither (e.g. a
client that declares no roots and no configured directory), every
`output_path` is refused with an error saying how to enable writing;
`plot_signals` without `output_path` still returns the inline preview. The
server's working directory is never used as a fallback. Each configured
directory must already exist (use an absolute path; `~` is expanded); the
server refuses to start otherwise, with a message naming the entry.

Claude Code needs nothing for plots inside the project. To also allow a
directory outside it, add the option to the command:

```bash
claude mcp add simtest-funnel -- uvx simtest-funnel-mcp --output-dir /home/me/plots
```

or, in a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "simtest-funnel": {
      "type": "stdio",
      "command": "uvx",
      "args": ["simtest-funnel-mcp", "--output-dir", "/home/me/plots"]
    }
  }
}
```

Clients that declare no workspace roots (Claude Desktop, at the time of
writing) need an output directory to save plots
(`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uvx",
      "args": ["simtest-funnel-mcp", "--output-dir", "/Users/me/Documents/plots"]
    }
  }
}
```

or with the environment variable:

```json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uvx",
      "args": ["simtest-funnel-mcp"],
      "env": { "SIMTEST_FUNNEL_MCP_OUTPUT_DIR": "/Users/me/Documents/plots" }
    }
  }
}
```

From a checkout, append the option after the command in the same way:
`"args": ["run", "--directory", "/path/to/simtest-funnel", "--quiet",
"simtest-funnel-mcp", "--output-dir", "/Users/me/Documents/plots"]`.

## Development

```bash
make build          # builds the native simtest-funnel module
make test-python    # includes python/simtest-funnel-mcp/tests (incl. stdio end-to-end)
make lint-python    # mypy --strict
uv run simtest-funnel-mcp   # start the server on stdio (--help for options)
```
