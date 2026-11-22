"""Cancellation, time limits, Ctrl-C and GIL release in ``simtest.funnel``.

The slow input is the shape that is still quadratic in the core: a nearly
noise-free sine with a wide tube in x (``rtolx = 0.1``). 100k samples take
about 0.8 s with a release wheel and several seconds with the unoptimised
``maturin develop`` build. Tests never let it finish: they stop it with a
time limit, a token or SIGINT, and bound every wait, so they are fast in
either build.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import threading
import time

import numpy as np
import pandas as pd
import pytest

from simtest.funnel import (
    CancelToken,
    ComparisonCancelled,
    ComparisonTimeout,
    Options,
    Tolerances,
    compare,
    compare_dataframes,
)

WIDE_X = Options(tolerances=Tolerances(rtolx=0.1))
#: Generous bound on how long a stopped comparison may take to return (the
#: core checks its signal every few milliseconds; this allows for a loaded
#: CI machine and the unoptimised build).
PROMPT = 2.0


def slow_signals(n: int = 100_000) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t = np.linspace(0.0, 10.0, n, endpoint=False)
    rng = np.random.default_rng(7)
    y_ref = np.sin(t) + 1e-3 * (rng.random(n) - 0.5)
    y_tst = np.sin(t) + 1e-3 * (rng.random(n) - 0.5)
    return t, y_ref, y_tst


def test_timeout_raises_promptly() -> None:
    t, yr, yt = slow_signals()
    start = time.monotonic()
    with pytest.raises(ComparisonTimeout, match="time limit of 0.05 s"):
        compare(t, yr, t, yt, WIDE_X, timeout=0.05)
    took = time.monotonic() - start
    assert 0.05 <= took < PROMPT


def test_timeout_is_a_cancellation() -> None:
    assert issubclass(ComparisonTimeout, ComparisonCancelled)
    assert issubclass(ComparisonCancelled, Exception)
    assert not issubclass(ComparisonCancelled, KeyboardInterrupt)


def test_zero_timeout_does_no_work() -> None:
    t, yr, yt = slow_signals()
    start = time.monotonic()
    with pytest.raises(ComparisonTimeout):
        compare(t, yr, t, yt, WIDE_X, timeout=0.0)
    assert time.monotonic() - start < PROMPT


def test_cancel_from_another_thread() -> None:
    t, yr, yt = slow_signals()
    token = CancelToken()
    assert not token.cancelled

    def cancel_soon() -> None:
        time.sleep(0.1)
        token.cancel()

    canceller = threading.Thread(target=cancel_soon)
    start = time.monotonic()
    canceller.start()
    try:
        with pytest.raises(ComparisonCancelled) as info:
            # The timeout only bounds the test if cancellation were broken.
            compare(t, yr, t, yt, WIDE_X, cancel=token, timeout=30.0)
    finally:
        canceller.join()
    assert type(info.value) is ComparisonCancelled
    assert token.cancelled
    assert time.monotonic() - start < 0.1 + PROMPT


def test_already_cancelled_token() -> None:
    t, yr, yt = slow_signals()
    token = CancelToken()
    token.cancel()
    token.cancel()  # idempotent
    assert token.cancelled
    assert repr(token) == "CancelToken(cancelled=True)"
    start = time.monotonic()
    with pytest.raises(ComparisonCancelled, match="cancelled"):
        compare(t, yr, t, yt, WIDE_X, cancel=token)
    assert time.monotonic() - start < PROMPT


def test_other_threads_run_during_a_comparison() -> None:
    """The GIL is released: a counting thread advances meanwhile."""
    t, yr, yt = slow_signals()
    count = 0
    stop = threading.Event()

    def counter() -> None:
        nonlocal count
        while not stop.is_set():
            count += 1

    worker = threading.Thread(target=counter)
    worker.start()
    try:
        time.sleep(0.02)  # let the counter start
        before = count
        # Runs (GIL released) until the limit stops it.
        with pytest.raises(ComparisonTimeout):
            compare(t, yr, t, yt, WIDE_X, timeout=0.5)
        during = count - before
    finally:
        stop.set()
        worker.join()
    # With the GIL held the counter could not advance at all while the
    # comparison ran; released, it counts to many thousands in 0.5 s.
    assert during > 10_000, during


def test_generous_limit_gives_identical_result() -> None:
    t, yr, yt = slow_signals(3_000)
    plain = compare(t, yr, t, yt, WIDE_X)
    limited = compare(t, yr, t, yt, WIDE_X, timeout=600.0, cancel=CancelToken())
    assert limited.status == plain.status
    for a, b in (
        (plain.lower, limited.lower),
        (plain.upper, limited.upper),
        (plain.errors, limited.errors),
    ):
        np.testing.assert_array_equal(a[0], b[0])
        np.testing.assert_array_equal(a[1], b[1])


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), float("-inf")])
def test_invalid_timeout(bad: float) -> None:
    t = np.array([0.0, 1.0, 2.0])
    with pytest.raises(ValueError, match="timeout"):
        compare(t, t, t, t, timeout=bad)
    frame = pd.DataFrame({"time": t, "y": t})
    with pytest.raises(ValueError, match="timeout"):
        compare_dataframes(frame, frame, timeout=bad)


def test_huge_timeout_means_no_limit() -> None:
    t = np.array([0.0, 1.0, 2.0])
    assert compare(t, t, t, t, timeout=1e300).status == 0


def test_compare_dataframes_honours_limit_and_token() -> None:
    t, yr, yt = slow_signals()
    ref = pd.DataFrame({"time": t, "a": np.zeros_like(t), "b": yr})
    tst = pd.DataFrame({"time": t, "a": np.zeros_like(t), "b": yt})
    start = time.monotonic()
    # The message names the caller's limit and the column, not the time
    # left for that column.
    message = r"column 'b' exceeded the time limit of 0\.2 s of compare_dataframes$"
    with pytest.raises(ComparisonTimeout, match=message):
        compare_dataframes(ref, tst, default_options=WIDE_X, timeout=0.2)
    assert time.monotonic() - start < 0.2 + PROMPT
    token = CancelToken()
    token.cancel()
    with pytest.raises(ComparisonCancelled):
        compare_dataframes(ref, tst, default_options=WIDE_X, cancel=token)
    # Without a signal it still works (constant column only, fast).
    out = compare_dataframes(ref[["time", "a"]], tst[["time", "a"]], timeout=60.0)
    assert out["a"].status == 0


_CHILD = textwrap.dedent(
    """
    import sys, time
    import numpy as np
    from simtest.funnel import Options, Tolerances, compare

    n = 200_000
    t = np.linspace(0.0, 10.0, n, endpoint=False)
    rng = np.random.default_rng(7)
    yr = np.sin(t) + 1e-3 * (rng.random(n) - 0.5)
    yt = np.sin(t) + 1e-3 * (rng.random(n) - 0.5)
    opts = Options(tolerances=Tolerances(rtolx=0.1))
    print("start", flush=True)
    try:
        compare(t, yr, t, yt, opts, timeout=60.0)
    except KeyboardInterrupt:
        print("interrupted", time.monotonic(), flush=True)
        sys.exit(0)
    print("finished", flush=True)
    sys.exit(1)
    """
)


@pytest.mark.skipif(os.name != "posix", reason="sends SIGINT")
def test_ctrl_c_interrupts_a_comparison() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", _CHILD],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "start"
        time.sleep(0.3)  # well inside the comparison (seconds long)
        sent = time.monotonic()
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
    assert proc.returncode == 0, (out, err)
    word, stamp = out.split()
    assert word == "interrupted"
    # CLOCK_MONOTONIC is system-wide on Linux; elsewhere only bound loosely.
    if sys.platform.startswith("linux"):
        assert float(stamp) - sent < PROMPT
