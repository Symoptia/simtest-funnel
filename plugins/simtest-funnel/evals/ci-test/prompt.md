---
description: Keep an agreed comparison as a pytest regression test.
tags: [skill, ci]
max_turns: 20
expected_outcome: compare_signals with include_snippet true, a test_*.py file written, the data files to commit named
---

Check results/run.csv against results/reference.csv within 0.05 °C, and if it passes keep the check as a pytest test in tests/.
