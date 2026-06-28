# Corpus Data

The 17 test directories in this folder are copied from
[LBNL Funnel](https://github.com/lbl-srg/funnel) (BSD-3-clause, Copyright
Lawrence Berkeley National Laboratory) from upstream commit `HEAD` of the
local working tree at `/home/iakovn/projects/funnel/tests/` on
2026-04-21. They are used by the Rust regression harness in
`../corpus_parity.rs` to assert numerical parity with the C reference.

## Provenance

Each sub-directory contains:

- `param.json` — compare parameters (tolerances + file names)
- `trended.csv` — reference trajectory (or `reference.csv` on a few cases)
- `simulated.csv` — test trajectory (or `test.csv`)
- `results/` — the committed C reference output (`reference.csv`,
  `test.csv`, `lowerBound.csv`, `upperBound.csv`, `errors.csv`)

## License

Corpus files inherit the BSD-3-clause license of the upstream LBNL Funnel
project. The rest of this repository is MIT; the BSD-3 attribution above
preserves compatibility per Q7 in the plan.
