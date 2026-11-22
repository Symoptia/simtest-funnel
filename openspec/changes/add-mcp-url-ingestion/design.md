# Design

## Context

See proposal.md (Why, Decisions) for motivation and the owner's binding
decisions, and the spec deltas for the required behaviour. Relevant current
state of `python/simtest-funnel-mcp/src/simtest_funnel_mcp/`, assuming
`add-mcp-column-mapping-and-formats` has landed:

- `server.resolve_path(raw, roots)` turns every input string into a local
  `Path` (relative to the first root, else the working directory) and
  enforces the roots; `_load` then calls `csvio.load_csv(path, header_line)`.
  Reference and test resolving to the same path and header line are read
  once (column-mapping design §10).
- `compare_signals` and `plot_signals` are async and run their impl in a
  worker thread through `run_off_loop(work(token))` with
  `abandon_on_cancel=True`; the call's `funnel.CancelToken` is cancelled on
  `notifications/cancelled`. The `TimeLimit` (deadline + token) starts
  before the files are read. `describe_signals` is a plain sync tool (the
  SDK runs it in a worker thread, but cancellation does not reach it).
- `plot_signals` checks the output path before reading any input and
  publishes the file under a `PublishGate` so that a cancelled call never
  writes.
- Annotations: `READ_ONLY` (describe, compare) and `PLOT` are module
  constants with `open_world_hint=False`; tools are registered at import
  time; `INSTRUCTIONS` says "local CSV files" and "Read-only and stateless".
  `main()` parses `--output-dir` and then calls `mcp.run("stdio")`.
- `snippet.py` writes each input as `DATA_ROOT / <relative path>` or an
  absolute path with a warning comment.
- Installed dependencies: `mcp` 2.3 pulls in `httpx2` and `truststore`
  (OS trust store for `ssl`); Python ≥ 3.12.
- The open specs say the server opens no network connection, keeps no state
  between calls, writes nothing but plot files and is closed-world; the
  `mcp-server` and `mcp-plots` deltas relax exactly these points, and only
  when network access is enabled (see "Conflicts with existing specs").

Facts checked on 2026-11-22 against the live service (two one-day requests
and one 15-day request, `models=ecmwf_ifs` and `ecmwf_ifs025`): the Previous
Runs API answers `200`, `Content-Type: text/csv; charset=utf-8`,
`Content-Disposition: attachment; filename="open-meteo-59.37N18.00E24m.csv"`,
`Content-Encoding: gzip` when asked (15 days of four columns: 12 226 bytes,
3 022 compressed), the three-line preamble
(`latitude,...,timezone_abbreviation`, values with `utc_offset_seconds` 0 and
`GMT`, blank line), the header
`time,temperature_2m (°C),temperature_2m_previous_day1 (°C),...` without a
model suffix when one model is requested, and times like `2026-11-01T00:00`.
A bad request answers `400`, `application/json`,
`{"error":true,"reason":"End-date must be larger or equals than start-date"}`.

## Goals / Non-Goals

**Goals:**

- A plain install behaves exactly as today: no socket, no temporary
  directory, closed-world annotations.
- With network access enabled, a model-chosen URL can reach only public
  `https` hosts (optionally only listed ones), can make the server send
  nothing but a plain GET, and cannot exhaust memory, disk or time.
- Everything after the fetch reuses the local-file code path unchanged.
- Results and snippets say exactly which bytes were compared.

**Non-Goals:**

- No protection against what a public host serves beyond size, type and
  time limits (the content is untrusted data, parsed by the same CSV reader
  as any local file).
- No IPv6/IPv4 preference tuning, HTTP/2, keep-alive or connection reuse:
  one connection per fetch is enough for files of a few MB.
- No caching of failures, DNS results or redirects.

## Decisions

Items marked **(design choice, not yet confirmed by the owner)** are this
design's answer to something the owner's decisions leave open; each gives
the recommendation and the main alternative.

### 1. Start-up options (design choice, not yet confirmed by the owner, for the names and values)

| Option | Environment variable | Default |
| --- | --- | --- |
| `--allow-network` | `SIMTEST_FUNNEL_MCP_ALLOW_NETWORK` (`1/true/yes/on`, `0/false/no/off/empty`; anything else is a start-up error) | off |
| `--allow-host HOST` (repeatable, implies network) | `SIMTEST_FUNNEL_MCP_ALLOW_HOSTS` (comma-separated) | none (any public host) |
| `--max-download-mb N` (positive number) | `SIMTEST_FUNNEL_MCP_MAX_DOWNLOAD_MB` | 20 |
| `--fetch-timeout S` (positive, at most 600) | `SIMTEST_FUNNEL_MCP_FETCH_TIMEOUT` | 30 |

- Command line and environment combine as for `--output-dir`: hosts from
  both are united; for the numbers the command line wins.
- Host entries are lower-cased and IDNA-encoded at start-up; an entry with
  a scheme, path, port, wildcard or user info is a start-up error ("give a
  host name such as `previous-runs-api.open-meteo.com`").
- Exact host names only, no `*.example.org`: simplest to reason about, and
  a redirect to a sibling host gives an error naming that host so the user
  can add it. Alternative: a leading-dot suffix form; easy to add later.
- An IP literal in a URL is allowed when public; with an allow-list it must
  be listed literally.
- Any port is accepted: the address check, not the port, protects the
  local network. Alternative: only 443 (narrower, but would refuse
  legitimate data servers on 8443).

### 2. HTTP client: standard library `http.client` with a pinned connection (design choice, not yet confirmed by the owner)

No new installed package. A small module `fetch.py` uses:

1. `urllib.parse.urlsplit` for parsing and normalisation (scheme, user
   info, host via `.hostname`, IDNA with the `idna` codec, port, fragment
   dropped). `urllib.request` is **not** used: its opener reads proxy
   variables, `.netrc`-style handlers and follows redirects itself.
2. `socket.getaddrinfo(host, port, type=SOCK_STREAM)`, then the address
   check (decision 3) on **every** result; the first checked address that
   accepts a TCP connection within the connect timeout is used.
3. A subclass of `http.client.HTTPSConnection` whose `connect()` does
   `sock = socket.create_connection((checked_ip, port), timeout)` and
   `self.sock = self._context.wrap_socket(sock, server_hostname=self.host)`.
   `self.host` stays the URL's host name, so SNI, the `Host` header and the
   certificate's host-name check all use the original name while the TCP
   connection goes to the address that was checked (no second lookup, so
   no DNS-rebinding window). `http.client` never consults proxy variables,
   cookies or `.netrc`.
4. The TLS context is `truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`
   (OS trust store; already installed through `mcp` → `httpx2`, declared as
   a direct dependency `truststore>=0.10`) with `check_hostname=True` and
   `CERT_REQUIRED`; when `truststore` cannot be imported (an unusual
   platform), `ssl.create_default_context()`. Using the OS store avoids the
   classic "no CA certificates" failure of some Python builds on macOS and
   Windows and matches what corporate machines trust.
5. The request: `GET <path?query>` with `Host`, `User-Agent:
   simtest-funnel-mcp/<version> (+https://github.com/Symoptia/simtest-funnel)`,
   `Accept: text/csv, text/plain;q=0.9, */*;q=0.1`, `Accept-Encoding: gzip`,
   `Connection: close`; nothing else. Redirects are handled by the module
   (decision 4), not by the library.
6. The body is read with `response.read1(65536)` (or `read(65536)`) in a
   loop, decompressed incrementally with
   `zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)` using `max_length` so
   that no step can expand beyond the remaining allowance, hashed with
   `hashlib.sha256` and written to the temporary file as it arrives.

Alternative: `httpx2` (already installed). It can pin the address (request
to the IP with a `Host` header and an `sni_hostname` extension) and ignore
proxies (`trust_env=False`), but every safety property then rests on
getting several library options right and on a client whose behaviour
around redirects, environment and connection pools changes between
versions; the standard-library path is about 150 lines, fully under our
control, and uses no option that could silently re-enable proxies or
cookies.

### 3. Address check (design choice, not yet confirmed by the owner, for the exact list)

With `ipaddress`: an address is accepted only if `ip.is_global` is true and
it is not multicast. Before that, IPv6 forms that embed an IPv4 address
are unwrapped and the IPv4 address is checked instead: IPv4-mapped
(`::ffff:0:0/96`), NAT64 (`64:ff9b::/96`, `64:ff9b:1::/48`), 6to4
(`2002::/16`) and Teredo (`2001::/32`, refused outright). `is_global` is
false for loopback, RFC 1918, link-local (`169.254.0.0/16` including the
metadata address, `fe80::/10`), unique-local `fc00::/7`, CGNAT
`100.64.0.0/10`, unspecified, reserved, benchmarking and documentation
ranges. A host whose resolution returns any non-public address is refused
as a whole (a mixed answer is a misconfiguration or an attack); the error
names the host and says "resolves to a non-public address" without listing
internal addresses. Resolution failure is its own error.

### 4. Redirects, status, content (design choice, not yet confirmed by the owner)

- Up to 5 redirect hops (301, 302, 303, 307, 308); each `Location` is
  resolved against the current URL and goes through decision 2 steps 1-3
  again (scheme, user info, allow-list, address check, certificate). No
  request body is ever sent, so 303 vs 307 makes no difference.
- Final status must be 200; others fail naming status and reason. A short
  error body (`text/*` or `application/json`, at most 4 kB read) is quoted
  up to 300 characters, because Open-Meteo puts the actionable reason
  there; it is response metadata, not samples.
- Accepted media types: `text/csv`, `application/csv`,
  `text/comma-separated-values`, `text/plain`, `application/octet-stream`,
  `binary/octet-stream`, `application/vnd.ms-excel` (several servers label
  `.csv` this way) and a missing `Content-Type`. Refused with a hint:
  `text/html`, `application/xhtml+xml` ("an HTML page, probably a web view
  of the file; use the raw-file URL"), `application/json` and `*/xml`
  ("only CSV is read; if the service offers CSV, ask for it, e.g.
  `format=csv`"). Any other type is refused naming it. Additionally the
  first non-blank bytes `<!doctype html` or `<html` (case-insensitive)
  refuse the body as HTML whatever the type says.
- Charset: absent, `utf-8`, `us-ascii` accepted; anything else refused
  (the reader reads UTF-8).
- `Content-Encoding`: absent, `identity` or `gzip`; anything else (`br`,
  `zstd`, `deflate`) is refused (we only ask for gzip). Compressed files as
  content (`application/gzip`, `.csv.gz`) are out of scope (proposal).
- Size cap 20 MB after decompression: generous for CSV (15 days of hourly
  Open-Meteo data is 12 kB; 20 MB is several hundred thousand rows of a
  few columns), small enough that a handful of cached files cannot fill a
  disk. Alternative: 100 MB; the option exists for that.

### 5. Timeouts and the call's time limit (design choice, not yet confirmed by the owner, for the values)

- Connect timeout 10 s per address attempt; whole fetch (all hops, all
  reads) `fetch_timeout` (30 s), so a default call (60 s) keeps at least
  30 s for reading and comparing.
- Effective fetch deadline = `min(start + fetch_timeout, call deadline)`.
  Before every blocking operation the socket timeout is set to
  `min(remaining, 1.0)` seconds; a socket timeout with time remaining and
  no cancellation is retried only for the connect step, otherwise it ends
  the fetch (we do not resume a half-read TLS record). The 1 s slice bounds
  how long a stalled socket can delay noticing cancellation.
- Between reads the call's `CancelToken` and the deadline are checked.
  `describe_signals` has no `time_limit` argument; its fetch is bounded by
  `fetch_timeout` only (design choice; alternative: add `time_limit` to
  `describe_signals` too — more surface for little gain, since describing a
  local file is fast).
- `describe_signals` becomes async and runs through `run_off_loop` like the
  other two tools so that cancellation reaches its fetch (spec "Cancellation
  stops a fetch"). Its local-file behaviour is unchanged.

### 6. Process-lifetime cache (owner decision 3; layout is a design choice, not yet confirmed by the owner)

- `UrlCache` (one per process) holds an in-memory index
  `normalised URL → Entry(url, final_url, fetched_at, size, sha256,
  content_type, file)` and the directory. The index is the truth; a file
  without an index entry is garbage.
- Directory: `tempfile.mkdtemp(prefix="simtest-funnel-mcp-")` in the
  system temporary directory, created lazily on the first fetch (mode 0700
  on POSIX; on Windows the per-user `%TEMP%` gives the same isolation).
- Entry files are named `<sha256 of the normalised URL>.csv`; a fetch
  writes `<random>.part` in the same directory and is renamed into place
  (`os.replace`) only after the body is complete, hashed and size-checked,
  and only if the call is still live — checked under the same kind of gate
  as plot publishing, so a cancelled call's late completion is discarded
  (spec "No partial cache entry"). The `.part` file is deleted in a
  `finally`.
- The cached file is then read by `csvio.load_csv` exactly like a local
  file; the column-mapping "read once when reference and test are the same
  path and header line" applies naturally because both resolve to the same
  entry file.
- Normalisation (spec "Same URL in one cache entry"): lower-case scheme and
  host, IDNA host, default port 443 removed, fragment removed, empty path
  becomes `/`; path and query byte-exact. No reordering of query
  parameters: servers may treat order as significant.
- Size bound: total ≤ 10 × size cap (200 MB by default); least recently
  used entries are evicted. An evicted URL is fetched again, and its
  SHA-256 must equal the remembered one (the index keeps hash and fetch
  time of evicted entries), otherwise the call fails "content of <url>
  changed during this server process (sha256 A then B); restart the server
  to use the new content". This keeps the owner's guarantee (same URL,
  same content within one process) without unbounded disk use.
  Alternative: no bound (simpler; a long session with many large URLs
  could fill the temp disk) or refusing new URLs when full (surprising).
- Removal: `atexit` handler `shutil.rmtree(dir, ignore_errors=True)`; on
  POSIX a `SIGTERM` handler (installed in `main()` only when network access
  is enabled) raises `SystemExit` in the main thread so `atexit` runs;
  `SIGINT` already raises `KeyboardInterrupt`; end of stdin ends
  `mcp.run` normally. On Windows, closing the console or `TerminateProcess`
  skips `atexit`.
- Leftovers (`SIGKILL`, crash, power loss, Windows termination): the
  directory stays in the system temporary directory until the OS cleans it
  (systemd-tmpfiles, macOS periodic cleanup, Windows Storage Sense) or the
  user deletes it. It contains only public files the user's server fetched,
  readable only by that user. The README names the `simtest-funnel-mcp-*`
  pattern. Alternative: at start-up, remove `simtest-funnel-mcp-*`
  directories owned by the user whose recorded PID is no longer running —
  rejected for the first version (PID reuse and several concurrent servers
  make it error-prone, and the gain is small).

### 7. Concurrency (design choice, not yet confirmed by the owner)

Single flight per normalised URL: the cache holds a `threading.Lock` for
its index and one in-flight record (`threading.Event` + result) per URL. A
call that finds an in-flight fetch waits on the event in slices of 0.1 s,
checking its own token and deadline, and then uses the entry. If the
in-flight fetch failed, was cancelled or timed out, the waiter starts its
own fetch (it never inherits another call's failure, whose limits may have
been tighter). Different URLs fetch in parallel; no global connection
limit (the MCP client serialises most calls anyway).

### 8. Where URLs enter the tools (design choice, not yet confirmed by the owner)

- `is_url(s)`: matches `^[A-Za-z][A-Za-z0-9+.-]*://`. Only `https` is
  fetched; `http`, `file` and anything else are refused even with network
  off (the refusal is about the scheme, so the message is more useful than
  "enable network"). `https` with network off gives the network-off error.
  Windows paths (`C:\x`) and relative paths never match.
- `server._load(raw, roots, header_line)` becomes
  `_load_source(raw, ...)`: a URL goes through the cache and yields a
  `SignalFile` whose `path` is the URL as given (normalised) plus a
  `source` record; everything else goes through `resolve_path` as today.
  Roots never apply to URLs (spec "Workspace roots are honoured").
- `header_line` / `test_header_line` apply to the fetched file exactly as
  to a local file; `pairs` with `test_path` omitted reuse the reference URL
  (one fetch, one read).
- Order in `compare_signals`: start the `TimeLimit`, fetch/read the
  reference, then the test (sequential; the second often hits the cache).
  A fetch error fails the call (there is no data to give rows for), unlike
  the per-row errors of the comparison.
- `plot_signals`: `output_path` that matches `is_url` is refused with
  "output_path must be a local path"; output checks keep running before any
  input is fetched.
- Workspace-relative echo: the snippet base logic and the "resolved path"
  echo apply only to local inputs; URL inputs echo the URL.

### 9. Source information in results (design choice, not yet confirmed by the owner)

New model `SourceInfo {url, final_url?, fetched_at, size, sha256,
content_type?, reused}` attached as `source` (omitted for local files) to
`FileInfo` (compare and plot results) and `DescribeResult`. `fetched_at` is
UTC ISO 8601 with `Z` and whole seconds; `reused` is false for the call
that fetched it. The cached file's path is never exposed (it disappears
with the process and an agent with a file system should not start relying
on it). Text rendering:

```
test: https://previous-runs-api.open-meteo.com/v1/forecast?... (fetched 2026-11-22T14:39:26Z, 12226 bytes, sha256 3f2a9c1e04b7…)
```

URLs longer than 200 characters are shortened in the text (middle elided)
but never in structured content.

`describe_signals` for a URL: `path` holds the URL, `source` as above,
everything else as for a local file (header line, time column kind,
columns, problems). Preamble lines are not echoed (as in the column-mapping
design §9).

### 10. Tool annotations and descriptions (design choice, not yet confirmed by the owner)

MCP's `openWorldHint` means the tool may interact with an open set of
external entities; a GET to model-chosen hosts is exactly that, so all
three tools are open-world when network access is enabled. `readOnlyHint`
stays true for `describe_signals` / `compare_signals`: a GET does not
modify the environment, and the private cache is server-internal state.
`idempotentHint` stays true (the cache makes repeated calls return the same
result within a process). Since tools are registered at import time,
`main()` sets `open_world_hint` on the three registered tools' annotations
after parsing the options and before `mcp.run` (or registration moves into
a `build_server(config)` function; implementation detail). Instructions and
descriptions are generated from the configuration the same way: with
network on they say "local paths or https URLs" and list allowed hosts
(at most 10, then "and N more"); with network off they say URLs need
`--allow-network`. The server instructions' "local CSV files ... Read-only
and stateless" wording changes accordingly.

### 11. Snippets for URL inputs (design choice, not yet confirmed by the owner)

The snippet targets CI, where the URL may change, be rate-limited or be
unreachable, so it never fetches. For each URL input it writes

```python
# REFERENCE was fetched from
#   https://previous-runs-api.open-meteo.com/v1/forecast?...
# on 2026-11-22T14:39:26Z (12226 bytes). Save a copy next to the other data:
#   curl -fLo forecast.csv '<url>'
REFERENCE = DATA_ROOT / "forecast.csv"
REFERENCE_SHA256 = "3f2a9c1e…"
```

and a module-level check that fails (not skips) with the URL, the expected
path, the expected and actual SHA-256 and the `curl` command when the file
is missing or differs. The local name is the URL's last path segment,
sanitised to `[A-Za-z0-9._-]`, with `.csv` appended if it has no
extension, or `url-<first 8 hex of the URL hash>.csv` when empty; when the
reference and test names collide for different URLs, both get a `-<first
8 hex of the content hash>` suffix. One URL used for both sides is one file.
Alternatives: embed the URL and download in the test (needs network in CI,
breaks when the content changes, and would need its own address checks) or
an opt-in download behind an environment variable (more code in every
snippet for a rare case; the curl line covers it).

### 12. Sample and walkthrough details (design choice, not yet confirmed by the owner)

- Model: `models=ecmwf_ifs` (ECMWF IFS HRES 9 km). Open-Meteo's licence page
  lists ECMWF's forecasts under CC-BY, and its ECMWF API page says ECMWF
  moved to open data on 1 October 2025 and IFS is provided under CC-BY 4.0;
  it is hourly to 90 h (3-hourly to 144 h, which Open-Meteo interpolates
  to hourly) with a 15-day horizon, so day-1/3/5 are populated, and it
  returned data for Stockholm in a test request. Alternative:
  `ecmwf_ifs025` (0.25°, 3-hourly) or `icon_global` (DWD, also CC-BY).
- Location Stockholm, `latitude=59.3293&longitude=18.0686`.
- Date range `start_date=2026-11-05&end_date=2026-11-19` (15 full past days
  at the time of writing, 360 hourly rows).
- `hourly=temperature_2m,temperature_2m_previous_day1,temperature_2m_previous_day3,temperature_2m_previous_day5`.
- Default `timezone` (GMT) and `timeformat` (ISO 8601): exercises the
  date-time support, avoids daylight-saving ambiguity (Open-Meteo writes
  local ISO times without offsets), and `utc_offset_seconds = 0` in the
  preamble lets the walkthrough explain the "no time zone, read as UTC"
  note. Alternative: `timeformat=unixtime`.
- The file is kept byte-identical to the response (preamble included, so
  the walkthrough uses `header_line=4`); attribution lives in an adjacent
  `ATTRIBUTION.md`, not in `#` lines inside the file (which would change
  the bytes and the hash the live URL gives).
- Location in the repository: `examples/open-meteo/stockholm-2026-11-05-to-19.csv`
  and `examples/open-meteo/ATTRIBUTION.md`. Not in the wheel or the sdist:
  the package is built from `python/simtest-funnel-mcp/` only
  (`[tool.hatch.build.targets.wheel] packages = ["src/simtest_funnel_mcp"]`),
  so a repository-root folder is excluded without configuration; the
  tests read it by repository path. Rationale: a packaged data file is not
  discoverable by agents, and keeping it out of packages keeps their
  licence simple. The walkthrough uses both the local path and the raw
  repository URL
  `https://raw.githubusercontent.com/Symoptia/simtest-funnel/main/examples/open-meteo/stockholm-2026-11-05-to-19.csv`
  (a stable URL that demonstrates fetching without depending on
  Open-Meteo's availability).
- The README's numbers (shares outside the tube per pair and tube) are
  computed from the bundled file during implementation and pinned by a
  test; they will differ somewhat from the hand trial in the proposal
  (different model and dates).

### 13. Tests offline (design choice, not yet confirmed by the owner)

- A local HTTPS test server (`http.server.ThreadingHTTPServer` wrapped
  with `ssl`) on `127.0.0.1`, with a throw-away CA and leaf certificate for
  `data.test` generated in the test session with `cryptography` (already
  installed through `mcp` → `pyjwt[crypto]`; declared as a test
  dependency) — or checked-in test certificates if that is simpler.
- The fetcher takes injectable `resolver` (name → addresses), `address
  policy` (so tests can allow `127.0.0.1` explicitly) and `ssl_context`;
  production code has no switch to disable the address check. Tests cover:
  every spec scenario of `mcp-url-sources` (redirect chains, gzip bomb,
  slow sender, HTML, JSON 400, credentials, proxies set in the
  environment, DNS rebinding resolver, certificate for another name,
  concurrent single flight, cancellation mid-download, cache cleanup in a
  subprocess on stdin close and SIGTERM).
- An optional live test (`SIMTEST_FUNNEL_LIVE=1`) fetches the documented
  Open-Meteo URL and checks the header line and columns (not the bytes:
  the API may reprocess archives).

### Conflicts with existing specs and how the deltas resolve them

- `mcp-server` "Stateless file access" forbids network connections, any
  state between calls and any write except plot files. The delta keeps all
  three for a server without network access and makes exactly two
  exceptions with it: GET requests and the process-lifetime cache.
- `mcp-server` "Local stdio server distribution" and `mcp-plots` "Tool
  annotations" require closed-world; the deltas make that conditional on
  network access being off.
- `mcp-server` "Workspace roots are honoured" says the server refuses "any
  path" outside the roots; the delta says "any local path" and adds a
  scenario that URLs are neither restricted nor resolved by roots.
- `mcp-server` "compare_signals time limit" says reading is not
  interrupted; the delta adds that fetching counts and is stopped at the
  deadline. "Time limit described as a deadline for the call" stays as is;
  the descriptions additionally mention fetching (tasks 5.2).
- `mcp-plots` "Output path safety" requires output checks before any CSV
  file is read; the new "Plot inputs from URLs" requirement extends that
  to "before any input is fetched" without modifying the original.
- `add-mcp-column-mapping-and-formats` modifies `mcp-server` "CSV dialect
  and time column", "describe_signals reports data problems" and "Column
  selection" and `mcp-plots` "Plot tool on the local server"; this change
  deliberately modifies none of those, so the two deltas archive in either
  order without overwriting each other (this one is ordered after it
  anyway).

## Risks / Trade-offs

- [A model-chosen URL can carry data from the conversation in its query
  string to any public host] → off by default; `--allow-host` documented as
  the recommended setting; README states it plainly.
- [`is_global` semantics differ slightly across Python versions] → the
  explicit unwrapping and refusal lists in decision 3 plus a table-driven
  test over the special-purpose ranges; Python ≥ 3.12 is required already.
- [OS trust store differs from Python's bundled store] → that is the
  intent (corporate CAs work); fallback to `ssl.create_default_context()`
  if `truststore` is unavailable.
- [Abandoned worker threads keep downloading after a cancelled call] →
  bounded by the 1 s socket slices and token checks, the fetch timeout and
  the size cap; their result is never committed.
- [Eviction plus a changed upstream file fails a later call] → only after
  more than 200 MB were fetched in one process; the error says to restart.
- [Leftover cache directories after a crash] → private to the user, public
  content only, removed by OS temp cleaning; documented.
- [Open-Meteo reprocesses or drops archived runs, so the live URL may later
  differ from the bundled bytes] → the walkthrough's numbers come from the
  bundled file; the live URL is documented as "the same request", and the
  snippet/hash machinery shows any difference.
- [IPv6-only or IPv4-only networks] → all resolved addresses are tried in
  order after all passed the check.

## Migration Plan

Nothing changes for existing users: network access is off unless enabled.
New optional result fields (`source`) and start-up options only. Rollback
is a package downgrade; leftover cache directories are harmless.

## Open Questions

- Whether to also accept `application/vnd.ms-excel` long-term or drop it
  once real-world URLs show it is unnecessary (affects only one entry in
  the accepted-type list).
