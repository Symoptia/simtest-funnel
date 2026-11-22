---
type: llm
---

PASS if the answer explains that test.csv covers less time than reference.csv (0 to 8 against 0 to 10) and treats this as a coverage problem rather than a tolerance violation, and reports that the overlap from 0 to 8 matches within 0.05 °C while the last part was not compared.
FAIL if it reports a plain pass for the whole file or calls the difference a tolerance failure.
