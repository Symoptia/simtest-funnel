"""Example: compare two multi-signal trajectories with per-signal overrides."""

from __future__ import annotations

import numpy as np
import pandas as pd

from simtest.funnel import (
    Options,
    Status,
    Tolerances,
    compare_dataframes,
    status_message,
)


def main() -> int:
    t = np.linspace(0.0, 1.0, 201)
    reference = pd.DataFrame(
        {
            "time": t,
            "temperature": 20.0 + 5.0 * np.sin(2 * np.pi * t),
            "pressure": 101.3 + 0.5 * np.cos(2 * np.pi * t),
        }
    )
    test = pd.DataFrame(
        {
            "time": t,
            "temperature": 20.0 + 5.0 * np.sin(2 * np.pi * t) + 0.1,
            "pressure": 101.3 + 0.5 * np.cos(2 * np.pi * t) + 0.02,
        }
    )

    default = Options(tolerances=Tolerances(atoly=0.2))
    overrides = {"pressure": Options(tolerances=Tolerances(atoly=0.01))}

    results = compare_dataframes(
        reference,
        test,
        default_options=default,
        option_overrides=overrides,
    )
    for name, r in results.items():
        print(f"{name}: status={Status(r.status).name} — {status_message(r.status)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
