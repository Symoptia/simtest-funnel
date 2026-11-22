## MODIFIED Requirements

### Requirement: Description explains the x-range window

The `compare_signals` description SHALL state that only test points inside
the x-range are judged, that the tube there is built from the reference
extended beyond the x-range as far as needed for it to equal the tube of
the whole reference there, so that without `rtolx` / `rtoly` every judged
point gets the same deviation and verdict as for the whole files, and that
the bases of `rtolx` / `rtoly` are the reference inside the x-range.

#### Scenario: Agent learns the window semantics
- **WHEN** an agent reads the `compare_signals` description
- **THEN** it finds that only points inside x_range are judged, against a
  tube built from the reference extended beyond x_range, with the same
  verdicts as a comparison of the whole files when rtolx and rtoly are 0
