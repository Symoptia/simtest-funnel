---
type: llm
---

PASS if the answer says where the test file was written and that results/reference.csv and results/run.csv must be committed at those paths (or that pytest must run from the project root, or with SIMTEST_FUNNEL_DATA_ROOT set) for the test to find them.
FAIL if it does not mention the data files the test needs.
