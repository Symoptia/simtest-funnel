"""Time limit, partial results and cancellation of compare_signals / plot_signals.

The slow column ``b`` is the shape that is still quadratic in the core: a
nearly noise-free sine with a wide tube in x (``rtolx = 0.3``). Its cost
grows with the square of the sample count: with the 100k samples of
:func:`slow_files` it takes about 1.3 s in a release build (far longer in
the unoptimised development build), several times the limits of at most
0.5 s used with it; the stdio test uses 200k samples (about 4.5 s
release) against a limit derived from how fast the server reads the files. Column ``a`` (constant) compares in milliseconds.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path
from typing import Any

import anyio
import numpy as np
import pytest
from conftest import structured
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server.mcpserver.exceptions import ToolError

import simtest.funnel as funnel
from simtest_funnel_mcp.compare import TimeLimit, run_compare
from simtest_funnel_mcp.csvio import SignalFile, load_csv
from simtest_funnel_mcp.models import ToleranceSet
from simtest_funnel_mcp.plot import prepare_plot, render
from simtest_funnel_mcp import server
from simtest_funnel_mcp.server import (
    compare_signals_impl,
    mcp,
    plot_signals_impl,
    run_off_loop,
)
from simtest_funnel_mcp.snippet import make_snippet

N = 100_000
#: Samples of the stdio test's files (see its docstring).
N_STDIO = 200_000
WIDE_X = ToleranceSet(label="wide", rtolx=0.3)
#: Generous bound for "promptly" (core checks every few ms).
PROMPT = 2.0


def _write_slow_files(d: Path, n: int) -> tuple[Path, Path]:
    """Columns ``a`` (zero) and ``b`` (slow) on ``n`` samples."""
    t = np.linspace(0.0, 10.0, n, endpoint=False)
    rng = np.random.default_rng(7)
    paths = []
    for name in ("reference.csv", "test.csv"):
        y = np.sin(t) + 1e-3 * (rng.random(n) - 0.5)
        p = d / name
        # repr round-trips exactly and is about twice as fast as savetxt.
        rows = "".join(f"{ti!r},0,{yi!r}\n" for ti, yi in zip(t.tolist(), y.tolist()))
        p.write_text("time,a,b\n" + rows)
        paths.append(p)
    return paths[0], paths[1]


@pytest.fixture(scope="module")
def slow_files(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    return _write_slow_files(tmp_path_factory.mktemp("slow"), N)


@pytest.fixture(scope="module")
def slow_loaded(slow_files: tuple[Path, Path]) -> tuple[SignalFile, SignalFile]:
    return load_csv(slow_files[0]), load_csv(slow_files[1])


def test_run_compare_returns_finished_rows_on_timeout(
    slow_loaded: tuple[SignalFile, SignalFile],
) -> None:
    ref, tst = slow_loaded
    start = time.monotonic()
    outcome = run_compare(ref, tst, tolerances=[WIDE_X], limit=TimeLimit.start(0.5))
    took = time.monotonic() - start
    assert took < 0.5 + PROMPT
    res = outcome.result
    assert [(r.column, r.verdict) for r in res.rows] == [("a", "pass")]
    assert outcome.not_completed == [("b", "wide")]
    assert res.time_limit_reached is True
    assert res.totals.rows == 1 and res.totals.passed == 1
    assert res.totals.not_completed == 1
    assert res.not_completed is not None
    assert [(p.column, p.tolerance_set) for p in res.not_completed] == [("b", "wide")]
    assert res.not_completed_omitted is None
    assert any("time limit of 0.5 s reached: 1 of 2 comparisons" in n for n in res.notes)
    # The snippet covers the completed row only and says so.
    snippet = make_snippet(outcome, "test", funnel.version(), Path.cwd())
    # Case tuples: (row key, reference column, test column, tolerance set, ...).
    assert "('a', 'a', 'a', 'wide'" in snippet
    assert "('b'" not in snippet
    assert "1 comparison(s) not completed" in snippet


def test_all_comparisons_complete_without_new_fields(
    demo_reference: Path, demo_test: Path
) -> None:
    result = compare_signals_impl(str(demo_reference), str(demo_test), [], time_limit=60.0)
    out = structured(result)
    assert "time_limit_reached" not in out
    assert "not_completed" not in out
    assert "not_completed" not in out["totals"]


def test_expired_limit_completes_nothing_but_succeeds(
    demo_reference: Path, demo_test: Path
) -> None:
    result = compare_signals_impl(
        str(demo_reference),
        str(demo_test),
        [],
        columns=["*", "nope"],
        max_rows=2,
        time_limit=1e-9,
    )
    assert not result.is_error
    out = structured(result)
    assert out["time_limit_reached"] is True
    # Server-detected problems need no comparison and are still reported.
    assert [(r["column"], r["verdict"]) for r in out["rows"]] == [("nope", "error")]
    n_signals = out["totals"]["not_completed"]
    assert n_signals >= 2
    assert len(out["not_completed"]) == 2
    assert out["not_completed_omitted"] == n_signals - 2
    text = result.content[0].text  # type: ignore[union-attr]
    assert f"{n_signals} not completed (time limit)" in text
    assert "NOT COMPLETED (time limit): " in text
    assert f"(+{n_signals - 2} more)" in text


@pytest.mark.parametrize("bad", [0.0, -1.0, float("inf"), float("nan")])
def test_invalid_time_limit_is_a_tool_error(
    bad: float, demo_reference: Path, demo_test: Path
) -> None:
    with pytest.raises(ToolError, match="time_limit"):
        compare_signals_impl(str(demo_reference), str(demo_test), [], time_limit=bad)
    with pytest.raises(ToolError, match="time_limit"):
        plot_signals_impl(str(demo_reference), str(demo_test), [], column="x", time_limit=bad)


@pytest.mark.parametrize("bad", [0, -5])
def test_invalid_time_limit_over_the_protocol(
    bad: float, demo_reference: Path, demo_test: Path
) -> None:
    async def run() -> Any:
        async with Client(mcp) as client:
            return await client.call_tool(
                "compare_signals",
                {
                    "reference_path": str(demo_reference),
                    "test_path": str(demo_test),
                    "time_limit": bad,
                },
            )

    result = asyncio.run(run())
    assert result.is_error
    assert "time_limit" in result.content[0].text


def test_plot_timeout_fails_without_writing(
    slow_files: tuple[Path, Path], tmp_path: Path
) -> None:
    ref, tst = slow_files
    target = tmp_path / "plot.svg"
    start = time.monotonic()
    with pytest.raises(ToolError) as info:
        plot_signals_impl(
            str(ref),
            str(tst),
            [tmp_path, ref.parent],
            column="b",
            tolerance=WIDE_X,
            output_path=str(target),
            time_limit=0.2,
        )
    msg = str(info.value)
    assert "did not finish within the time limit of 0.2 s" in msg
    assert "No file was written" in msg
    assert not target.exists()
    assert time.monotonic() - start < 0.2 + 2 * PROMPT  # reading counts too


def test_cancelled_call_cancels_the_comparison(
    slow_loaded: tuple[SignalFile, SignalFile],
) -> None:
    """``run_off_loop`` cancels the token when the awaiting task is cancelled."""
    ref, tst = slow_loaded
    seen: dict[str, Any] = {}
    done = threading.Event()

    def work(token: funnel.CancelToken) -> None:
        seen["token"] = token
        try:
            run_compare(ref, tst, tolerances=[WIDE_X], limit=TimeLimit.start(60.0, token))
            seen["outcome"] = "finished"
        except funnel.ComparisonCancelled as exc:
            seen["outcome"] = type(exc).__name__
        finally:
            done.set()

    async def main() -> float:
        start = time.monotonic()
        with anyio.move_on_after(0.3):
            await run_off_loop(work)
        return time.monotonic() - start

    returned_after = anyio.run(main)
    assert returned_after < 0.3 + 0.5  # the handler does not wait for the worker
    assert done.wait(PROMPT), "worker did not stop"
    assert seen["token"].cancelled
    assert seen["outcome"] == "ComparisonCancelled"


def test_protocol_cancellation_cancels_the_token(
    slow_files: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A client abandoning a call sends notifications/cancelled; the server's
    token for that call is cancelled and the server keeps serving."""
    created: list[funnel.CancelToken] = []
    real_token = funnel.CancelToken
    real_compare = funnel.compare
    comparing = threading.Event()

    def recording_token() -> funnel.CancelToken:
        token = real_token()
        created.append(token)
        return token

    def signalling_compare(*args: Any, **kwargs: Any) -> funnel.CompareResult:
        comparing.set()
        return real_compare(*args, **kwargs)

    monkeypatch.setattr(funnel, "CancelToken", recording_token)
    monkeypatch.setattr(funnel, "compare", signalling_compare)
    ref, tst = slow_files

    async def run() -> Any:
        async with Client(mcp) as client:
            async with anyio.create_task_group() as tg:

                async def call() -> None:
                    await client.call_tool(
                        "compare_signals",
                        {
                            "reference_path": str(ref),
                            "test_path": str(tst),
                            "columns": ["b"],
                            "tolerances": [{"label": "wide", "rtolx": 0.3}],
                        },
                    )
                    raise AssertionError("the call should not finish")

                tg.start_soon(call)
                # Cancel once the comparison runs (after reading the files).
                assert await anyio.to_thread.run_sync(lambda: comparing.wait(60))
                tg.cancel_scope.cancel()
            deadline = time.monotonic() + PROMPT
            while not (created and created[0].cancelled) and time.monotonic() < deadline:
                await anyio.sleep(0.02)
            return await client.list_tools()

    tools = asyncio.run(run())
    assert {t.name for t in tools.tools} >= {"compare_signals"}
    assert created and created[0].cancelled


#: Runs the stdio server with ``funnel.compare`` wrapped to append the
#: sample count to the file named by its first argument whenever a
#: comparison starts, so the test can wait for the comparing phase instead
#: of guessing how long reading the files takes.
_PROBED_SERVER = """
import sys
import simtest.funnel as funnel
from simtest_funnel_mcp.server import main

marker = sys.argv[1]
real_compare = funnel.compare

def compare(*args, **kwargs):
    with open(marker, "a") as fh:
        fh.write(f"{len(args[0])}\\n")
    return real_compare(*args, **kwargs)

funnel.compare = compare
main([])
"""


def test_stdio_server_stays_responsive_and_returns_partial_results(
    tmp_path_factory: pytest.TempPathFactory, tmp_path: Path
) -> None:
    """Over stdio: tools/list is answered while column ``b`` is compared,
    and the call returns ``a``'s row with ``b`` not completed.

    Timing: the test waits until the second comparison (``b``) has started,
    i.e. both files are read and ``a`` is done, so a slow machine only
    delays the wait. The limit must cover reading the two 200k-row files
    but leave ``b`` unfinished. Both scale with the machine, so the limit is
    derived from a measured read in the server itself (a describe_signals
    call on the reference, which reads the file just like the comparison
    will): twice the time to read both files plus 0.5 s. Here reading one
    file takes about 0.5 s and ``b`` about 4.5 s in a release build (far
    longer unoptimised), roughly nine file reads, so ``b`` gets at most
    about half of what it needs on a machine of any speed, while reading
    gets twice what it took a moment before.
    """
    ref, tst = _write_slow_files(tmp_path_factory.mktemp("stdio"), N_STDIO)
    marker = tmp_path / "comparisons.log"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", _PROBED_SERVER, str(marker)],
        cwd=str(tmp_path),
    )

    def started() -> int:
        """Comparisons of the files' columns started so far."""
        try:
            return marker.read_text().split().count(str(N_STDIO))
        except FileNotFoundError:
            return 0

    async def run() -> tuple[bool, Any, float]:
        async with Client(params, read_timeout_seconds=120) as client:
            await client.list_tools()  # warm up
            start = time.monotonic()
            described = await client.call_tool("describe_signals", {"path": str(ref)})
            assert not described.is_error
            time_limit = 2 * 2 * (time.monotonic() - start) + 0.5
            result: dict[str, Any] = {}

            async def slow_call() -> None:
                result["compare"] = await client.call_tool(
                    "compare_signals",
                    {
                        "reference_path": str(ref),
                        "test_path": str(tst),
                        "tolerances": [{"label": "wide", "rtolx": 0.3}],
                        "time_limit": time_limit,
                    },
                )

            async with anyio.create_task_group() as tg:
                tg.start_soon(slow_call)
                deadline = time.monotonic() + 120
                while started() < 2 and "compare" not in result:
                    assert time.monotonic() < deadline, "comparison of b never started"
                    await anyio.sleep(0.02)
                start = time.monotonic()
                await client.list_tools()
                list_took = time.monotonic() - start
                compare_pending = "compare" not in result
            return compare_pending, result["compare"], list_took

    compare_pending, compare, list_took = asyncio.run(run())
    assert compare_pending, "tools/list was answered only after the comparison"
    assert list_took < 2.0
    out = structured(compare)
    assert not compare.is_error
    assert [(r["column"], r["verdict"]) for r in out["rows"]] == [("a", "pass")]
    assert out["not_completed"] == [{"column": "b", "tolerance_set": "wide"}]
    assert out["totals"]["not_completed"] == 1
    assert out["time_limit_reached"] is True
    assert "NOT COMPLETED (time limit): b [wide]" in compare.content[0].text
    assert started() == 2


# --------------------------------------------------------------------------
# plot_signals: no file from a call that is no longer live
# --------------------------------------------------------------------------


def _plot_args(demo_reference: Path, demo_test: Path, out_dir: Path) -> dict[str, Any]:
    return {
        "reference_path": str(demo_reference),
        "test_path": str(demo_test),
        "roots": [out_dir, demo_reference.parent],
        "column": "z",
        "output_path": str(out_dir / "z.svg"),
    }


def test_plot_cancelled_while_rendering_never_writes(
    demo_reference: Path, demo_test: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The client cancels after the comparison finished, while the abandoned
    worker is still rendering: the call is reported cancelled at once and
    the worker, finishing later, writes nothing (no partial file either)."""
    rendering = threading.Event()
    release = threading.Event()
    done = threading.Event()
    real_preview = server._preview_png

    def slow_preview(data: Any) -> bytes:
        rendering.set()
        release.wait(30)
        return real_preview(data)

    monkeypatch.setattr(server, "_preview_png", slow_preview)
    gate = server.PublishGate()
    errors: list[BaseException] = []

    def work(token: funnel.CancelToken) -> Any:
        try:
            return plot_signals_impl(
                **_plot_args(demo_reference, demo_test, tmp_path), cancel=token, gate=gate
            )
        except BaseException as exc:
            errors.append(exc)
            raise
        finally:
            done.set()

    async def main() -> bool:
        async with anyio.create_task_group() as tg:

            async def call() -> None:
                await run_off_loop(work, gate)
                raise AssertionError("the call should have been cancelled")

            tg.start_soon(call)
            assert await anyio.to_thread.run_sync(lambda: rendering.wait(30))
            tg.cancel_scope.cancel()
        return (tmp_path / "z.svg").exists()

    assert anyio.run(main) is False  # reported cancelled, nothing written yet
    release.set()  # let the abandoned worker finish rendering
    assert done.wait(30)
    assert list(tmp_path.iterdir()) == []
    assert len(errors) == 1 and "cancelled before rendering the file" in str(errors[0])


@pytest.mark.parametrize("stop", ["cancel", "deadline"])
def test_plot_stopped_after_rendering_never_publishes(
    stop: str,
    demo_reference: Path,
    demo_test: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation or the deadline arriving while the file is rendered is
    caught immediately before the file is moved into place."""
    token = funnel.CancelToken()
    stopped = threading.Event()
    real_render = render
    real_remaining = TimeLimit.remaining
    calls = 0

    def render_then_stop(*args: Any, **kwargs: Any) -> bytes:
        nonlocal calls
        out = real_render(*args, **kwargs)
        calls += 1
        if calls == 2:  # 1: inline preview, 2: the file
            if stop == "cancel":
                token.cancel()
            stopped.set()
        return out

    def remaining(self: TimeLimit) -> float:
        return 0.0 if stopped.is_set() else real_remaining(self)

    monkeypatch.setattr("simtest_funnel_mcp.server.render", render_then_stop)
    if stop == "deadline":
        monkeypatch.setattr(TimeLimit, "remaining", remaining)
    with pytest.raises(ToolError) as info:
        plot_signals_impl(
            **_plot_args(demo_reference, demo_test, tmp_path), cancel=token, time_limit=30.0
        )
    msg = str(info.value)
    assert "before the file was written; no file was written" in msg
    if stop == "deadline":
        assert "time limit of 30 s" in msg and "rendering" in msg
    else:
        assert "cancelled" in msg
    assert list(tmp_path.iterdir()) == []  # neither the file nor a temporary one


def test_plot_cancelled_after_comparison_skips_rendering(
    demo_reference: Path, demo_test: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = funnel.CancelToken()
    real_prepare = prepare_plot

    def prepare_then_cancel(*args: Any, **kwargs: Any) -> Any:
        out = real_prepare(*args, **kwargs)
        token.cancel()
        return out

    def no_render(*args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("rendered after cancellation")

    monkeypatch.setattr("simtest_funnel_mcp.server.prepare_plot", prepare_then_cancel)
    monkeypatch.setattr("simtest_funnel_mcp.server.render", no_render)
    with pytest.raises(ToolError, match="cancelled before rendering; no file was written"):
        plot_signals_impl(**_plot_args(demo_reference, demo_test, tmp_path), cancel=token)
    assert list(tmp_path.iterdir()) == []


def test_time_limit_is_described_as_a_deadline_for_the_call() -> None:
    async def run() -> Any:
        async with Client(mcp) as client:
            return await client.list_tools()

    tools = {t.name: t for t in asyncio.run(run()).tools}
    for name in ("compare_signals", "plot_signals"):
        field = tools[name].input_schema["properties"]["time_limit"]["description"]
        assert "whole call" in field and "counted from its start" in field, field
        assert "reading" in field and "the files" in field, field
        assert "comparisons of this call may take" not in (tools[name].description or "")
    assert "rendering" in tools["plot_signals"].input_schema["properties"]["time_limit"][
        "description"
    ]
