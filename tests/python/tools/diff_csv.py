#!/usr/bin/env python3
"""Diff two funnel CSV outputs with an adaptive tolerance.

Usage:
    python diff_csv.py <rust.csv> <c.csv> [--tol 1e-6]

Exits with 0 when every matching row is within tolerance, 1 otherwise.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def _read(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    with path.open() as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if len(row) < 2:
                continue
            try:
                x = float(row[0])
                y = float(row[1])
            except ValueError:
                if i == 0:
                    continue
                raise
            rows.append((x, y))
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("rust", type=Path)
    p.add_argument("c", type=Path)
    p.add_argument("--tol", type=float, default=1e-6)
    args = p.parse_args()
    a = _read(args.rust)
    b = _read(args.c)
    n = min(len(a), len(b))
    worst = 0.0
    bad = 0
    for i in range(n):
        dx = abs(a[i][0] - b[i][0])
        dy = abs(a[i][1] - b[i][1])
        rel = args.tol * max(abs(a[i][1]), abs(b[i][1]))
        floor_ = max(args.tol, rel)
        if dy > floor_:
            bad += 1
        worst = max(worst, dy, dx)
    print(f"rows: rust={len(a)} c={len(b)}, worst={worst:.3e}, bad={bad}/{n}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
