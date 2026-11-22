# Design

## D1. Window extension that provably reproduces the full-range tube

### Problem

The extension used to be a fixed margin: every reference point whose x
half-width, taken twice, reaches the window, plus three samples. The
corner algorithm (C reference `algorithmRectangle.c`, `corners.rs`)
inserts no corners at a point whose incoming and outgoing slopes are
equal (within `1e-10`) and skips points equal to their successor (x in
normalized units and y within `1e-10`; with epoch-sized x, normalized by
~1.7e9, samples less than ~0.17 s apart with equal y). Inside such a run
the tube boundary is one segment between the corners before and after the
run. Cutting the reference inside the run moves the end of that segment,
which changes the boundary over the whole run, i.e. possibly over the
window however far away the cut is. Reviewer's case A: y = 0 for 13
points, then a long run of 2 at ~0.02 s spacing, epoch x, `atolx =
0.5585`: the upper boundary at the first sample is 0.4085 in the full
comparison (deviation 0.0915, Fail) and 2.0555 with the old extension
(Pass). Case B (one long linear run, `ltoly = 0.018`): the end corners of
a cut run lie on a different line than those of the whole run because
`hy` varies along it.

### Decision

Keep the old margin as the initial extension and grow it (doubling the
extension of a failing side) until a check on the corners of the
extended slice proves that the slice gives the full-range tube over the
window (`window.rs`). Once the slice would cover more than half of the
reference, use the whole reference. The check needs the corner scan to
report, per corner, the reference point it belongs to, the start point,
the *firm* corner points and the undone candidates; `corners.rs` gets a
`CornerObserver` (the plain comparison uses the no-op observer `()`, so
its arithmetic and results are unchanged bit for bit).

### Argument (also in the `window.rs` module docs)

`T` = corner list of the slice `s..e`, `F` = corner list of the whole
reference, per curve (lower and upper).

1. **Corner state.** The scan carries `(s0, m0)`, the sign and slope of
   the last processed segment. The slice scan starts at `b` (first point
   of the slice not equal to its successor) with the slope of `(b, b+1)`;
   the whole-reference scan processes `b` (it is not skipped) and leaves
   it with the same `(s0, m0)`. Hence both scans make the same corner
   decisions for every point in `(b, e-2]`, including steps (vertical
   segments, slope `±1e15`) and runs of repeated points (skipped
   identically, since skipping depends only on a point and its
   successor). They differ only in the corners of `b` and before, and in
   the undo step (a point's new corners are removed when the previous
   corner, the new corner and the next point's edge are at the same y),
   which reads the previous corner. A point is *firm* when its undo
   condition (`y[i+1] ± hy[i+1]` equal to its corner's y) is false: its
   corners stay whatever precedes them. From the first firm point `q > b`
   on, `T` and `F` are identical up to the corners of `e-2`.
2. **Bounds on what differs.** `hx = max(c, ltolx*|x|)` (absolute,
   local; no range-relative part when `rtolx = 0`), so `x + hx` and
   `x - hx` are non-decreasing for `ltolx <= 1` (the initial extension
   already uses the whole reference when `2*ltolx > 1`). Corners of
   points `<= b` lie at most at `x[b] + hx[b]`; corners of points in
   `(b, q)` are corners or undone candidates of `T`; corners of points
   `>= e-1` lie at least at `x[e-1] - hx[e-1]`. `hy` is per point
   (`max(atoly, ltoly*|y|)`), so varying `hy` along a run (case B) is
   covered by step 1 without further conditions.
3. **Loop removal.** `remove_loop` walks left to right; at a backward
   segment `(j, j+1)` it scans back to the last point with `x <= x[j+1]`,
   forward to the first point with `x >= x[j]`, deletes the points in
   between and inserts the intersection. A corner `A` is a *gap* when all
   corners before it (in `T`, and in `F` by step 2) are left of `x(A)`
   and all after it right of `x(A)`, by more than `2.5e-10` (normalized;
   more than the algorithm's equality tolerance, so `A` is never merged
   with a neighbour). No backward segment spans a gap; a removal left of a
   gap stops at it unchanged; a removal right of a gap reaches back at
   most to the gap (may delete it) and the point before (reads it). So
   for two consecutive gaps `P, A`, the processed curve left of `x(P)`
   depends only on corners up to `P` and the processed curve right of
   `x(P)` only on corners from `P` on. With a pair `x(P_L) < lo` and a
   pair `x(P_R) > hi`, all four corners common to `T` and `F`, the
   processed curves agree on `[x(P_L), x(P_R)]`, which contains the
   window. The deviation interpolation walks a cursor over the bounds;
   everything left of `x(P_L)` is left of every judged point, so the
   cursor lands in the common part in both comparisons and the judged
   deviations are bit-identical.

**Assumption.** Step 3 uses that each removal inserts its intersection
on the segment it cuts (a genuine crossing). The C reference's heuristic
can, in degenerate geometry (nearly parallel segments, crossings within
rounding of a corner), intersect the extended lines elsewhere; then a
removal could reach one point further back. This is the only part of the
guarantee that is not proven; the documentation says so.

**Remove-loop interaction across the boundary** (asked for in the
review): handled by step 3, which is why a pair of consecutive gaps is
needed on each side and not a single gap or a point count.
**ltolx / ltoly varying along a run**: handled by steps 1–2 (per-point
half-widths, monotone reach for `ltolx <= 1`; whole reference otherwise).

### Guarantee as now stated

With `rtolx = rtoly = 0` and any `atolx`, `atoly`, `ltolx`, `ltoly`, every
test point inside the window gets the same deviation, bit for bit, and so
the same verdict, as in the comparison without an x-range; exact for the
corner construction, assuming genuine crossings in loop removal. With
`rtolx` / `rtoly` the window is the base of the tolerances by design.

### Cost

The check reads only the slice, so the cost is proportional to the final
extension (geometric growth). For smooth and step signals it stays within
a few half-widths (measured on 10^6 samples, 10-unit window: within 30 %
of the old cost). It reaches the data end through a collinear or constant
run that long, or where the reference turns more often than the x
tolerance is wide (noise with `atolx` of several samples): then the
window costs about 1.5× a full-range comparison (measured: 190–270 ms vs
120–175 ms full, 2–3 ms before). A weaker but still exact condition for
such signals would need a proof that loop removal forgets distant
history, which the heuristic does not obviously give; not attempted.

### Verification

- Regression tests from the reviewer's dumped cases
  (`tests/fixtures/window/*.txt`): case A, case B, an `ltoly` run at epoch
  x, an `ltolx` case.
- `extension_reaches_the_end_of_a_collinear_run`, constant reference,
  cost on 2·10^6 samples.
- Property tests now require bit-identical deviations; new
  `adversarial_windows_match_full_range_bit_for_bit` ports the reviewer's
  harness (collinear runs, steps, repeated/clustered/log-uniform x, epoch
  x, window edges inside runs).
- Reviewer's harness and an extended version run at scale (numbers in the
  task list).

## D2. IP-literal hosts (finding 2)

`_PinnedHTTPSConnection.connect` passed `server_hostname=None` for an IP
literal while the context has `check_hostname=True`, which makes `ssl`
raise `ValueError`. Now the URL's host is always passed: for an IP literal
`ssl` sends no SNI and matches the certificate's IP address entries. Any
other exception from the TLS handshake becomes a `FetchError` naming the
host; `ValueError` from the request/response step too.

## D3. Fetched content is untrusted (finding 3)

Decision: error responses report the host, the status with its *standard*
phrase (`http.HTTPStatus`, not the server's reason phrase) and the content
type (only if it looks like a media type). No body text is quoted, except
the `reason` / `error` / `message` string of a JSON object body: Open-Meteo,
the bundled example's service, explains a bad request that way ("End-date
must be larger or equals than start-date"), which tells the agent exactly
what to change. That string is reduced to `[A-Za-z0-9 .,:;=+-_/()%]`
(no quotes, brackets, braces, angle brackets, backticks or line breaks, so
it cannot pose as markup or as another speaker), whitespace collapsed, at
most 120 characters, and labelled "the server's JSON reason, sanitised".
Column names and values of a fetched file still reach the model (they are
the data); the README, the server instructions (network on) and the
INPUT FILES paragraph now say that content from a URL is untrusted data,
not instructions, and the README and instructions explain that without
`--allow-host` the host name itself is sent to DNS before any check, so it
can carry data out even when the fetch fails; `--allow-host` (checked
before any lookup) is the recommended way to enable network access.

## D4. A column paired with itself (finding 4)

`_pair_problem` returns an error row when `tst is ref` (the same loaded
file: no `test_path`, or the same path and header line) and both sides name
the same column. `prepare_plot` refuses the same case (no or the same test
column) with a `PlotArgumentError`; nothing is written. Plain `columns`
with an explicit identical `test_path` are left alone (an explicit request;
without `test_path` they were already refused).

## D5. ASCII digits in ISO timestamps (finding 5)

`\d` matches any Unicode decimal digit and `parse_iso` then computes with
code points; the patterns in `reader.py` (embedded verbatim in snippets)
now use `[0-9]`. `models.XRange` uses the same pattern.

## D6. Address policy and resolver bound (finding 6)

An explicit deny-list (`_DENY`) is checked besides `is_global`: the IPv4
special ranges, `::/128`, `::1`, `100::/64`, `2001:db8::/32`, `3fff::/20`,
`5f00::/16` (SRv6), `fc00::/7`, `fe80::/10`, `fec0::/10` (site-local) and
`ff00::/8`. Python 3.14's `is_global` is true for `fec0::1` and `5f00::1`.
`2001::/23` is not listed, since it contains global assignments that
`is_global` handles. The lookup runs in a daemon helper thread; the fetch
waits in `WATCH_INTERVAL` slices, calling `_Watchdog.check()` (deadline and
cancellation), and abandons the thread on a trip; the answer goes into a box
local to that call, so a late answer is never used.

## D7. Cache bound counts downloads in progress (finding 7)

The `.part` file is wrapped in a writer that adds each written block to the
download's count under the cache lock and evicts; `_evict` counts copies
plus bytes in progress. At most `MAX_IN_FLIGHT = TOTAL_FACTOR` downloads run
at once (another call fails with a clear error), so with the default bound
the bytes in progress alone never exceed it. `_seen` keeps the last 4096
URLs (oldest forgotten): beyond that a re-fetched URL is not compared with
its old hash; documented.

## D8. Snippet download (finding 8)

Redirect targets cannot be checked for public addresses robustly in a few
standard-library lines (urllib resolves again when it connects), so the
snippet follows no redirect; it downloads from the URL the server finally
read (`source.final_url`), so the common case meets no redirect. It asks
for `Accept-Encoding: identity` and refuses any other `Content-Encoding`
(the hash is of the bytes received), stops after `DOWNLOAD_DEADLINE = 300`
s checked between reads (`read1`, so a slow sender cannot hold one read for
the whole body; each read also has a 30 s socket timeout), and puts the
copy in place with `os.link` (fails if the file exists), falling back to an
exclusive `open(..., "xb")` copy where hard links are unsupported.

## D9. CSV timing test (finding 9)

100 000 rows instead of 1 000 000, best of three, and `iso < 4 × numeric +
0.1 s`: the absolute slack absorbs timer and scheduling noise, while a
per-cell parse (seconds) still fails it.

## D10. Description consistency (finding 10)

The `x_range` argument descriptions of both tools now state the unit
(seconds since 1970 on a date-time axis), that only test points inside are
judged against the tube of the whole reference there, built from the
reference extended as far as needed, and that rtol bases come from inside;
the plot description and the X_RANGE paragraph use the same wording as the
guarantee of D1.

## D11. Smaller items (finding 11)

- **gzip padding.** RFC 1952 defines no padding, but gzip(1) ("trailing
  zero bytes ignored") and Python's `gzip` module accept NUL bytes after the
  last member (tape-block legacy). Accepting exactly that is consistent with
  the common tools and harmless; any non-NUL byte after the padding is
  refused, other data after a member must be another member.
- **Preamble hint for CR-only files.** `_head_lines` reads at most 1 MiB and
  splits at CR LF, CR or LF, as the reader counts lines.
- **sdist.** `test_mcp_examples.py` is skipped (module-level `skipif`) when
  the repository's `examples/` sample is absent, as in the sdist. Other
  sdist tests also use repository files (`examples/web`, `.mcp.json`, the
  README); excluding tests from the sdist would change release packaging,
  which this change does not touch.
