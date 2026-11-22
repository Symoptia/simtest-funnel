---
type: llm
---

PASS if the answer names the tolerance values it used for the comparison and gives a reason for them (or asks the user which tolerance to use before giving a verdict), and its verdict agrees with the tolerance it names (run.csv is offset from reference.csv by a constant 0.03 °C).
FAIL if it gives a match or no-match verdict without saying which tolerance it is based on, or presents the server's default as an obvious choice without saying so.
