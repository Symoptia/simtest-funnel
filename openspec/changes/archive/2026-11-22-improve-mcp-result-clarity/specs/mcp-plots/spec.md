## ADDED Requirements

### Requirement: Plot result explains the worst point and carries all notes

The plot result's row SHALL carry the same `difference` and
`worst_difference` fields as the corresponding `compare_signals` row, and
the result SHALL carry every note that `compare_signals` gives for the
same comparison, including the record-edge and differing-span notes.

#### Scenario: Delayed test plotted with an x tolerance
- **WHEN** an agent plots a reference sin(t) against the same delayed by
  0.1 with `atoly 0.06, atolx 0.15`
- **THEN** the row's worst point at t = 0 carries the difference sin(-0.1)
  and the notes contain the record-edge note
