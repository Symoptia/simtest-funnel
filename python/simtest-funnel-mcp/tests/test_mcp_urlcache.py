"""The process-lifetime URL cache: reuse, no partial entries, single flight,
eviction with remembered hashes and cleanup (local HTTPS server, offline)."""

from __future__ import annotations

import hashlib
import os
import stat
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from urlserver import Certs, TestServer, body, delayed, slow, test_fetcher

import simtest.funnel as funnel
from simtest_funnel_mcp.fetch import FetchCancelled, FetchConfig, FetchError, FetchTimeout, parse_url
from simtest_funnel_mcp.server import PublishGate
from simtest_funnel_mcp.urlcache import DIR_PREFIX, Fetched, UrlCache

CSV = b"time,a\n0,1\n1,2\n"
CSV2 = b"time,a\n0,5\n1,6\n"


@pytest.fixture
def cache(certs: Certs) -> object:
    c = UrlCache(test_fetcher(certs))
    yield c
    c.cleanup()


def _get(cache: UrlCache, url: str, **kwargs: object) -> Fetched:
    with cache.use(parse_url(url), **kwargs) as fetched:  # type: ignore[arg-type]
        assert fetched.entry.file.read_bytes()  # readable inside the block
        return fetched


def test_no_directory_before_the_first_fetch(cache: UrlCache) -> None:
    assert cache.directory is None


def test_second_use_reuses_the_copy(https_server: TestServer, cache: UrlCache) -> None:
    url = https_server.url("/a.csv")
    https_server.routes.routes["/a.csv"] = body(CSV)
    first = _get(cache, url)
    assert first.reused is False
    assert cache.directory is not None and cache.directory.name.startswith(DIR_PREFIX)
    if os.name == "posix":
        assert stat.S_IMODE(cache.directory.stat().st_mode) == 0o700
    https_server.routes.routes["/a.csv"] = body(CSV2)  # the remote file changes
    second = _get(cache, url.replace("data.test", "DATA.test") + "#frag")
    assert second.reused is True
    assert https_server.routes.count("/a.csv") == 1  # no second connection
    assert second.entry.sha256 == first.entry.sha256 == hashlib.sha256(CSV).hexdigest()
    assert second.entry.fetched_at == first.entry.fetched_at
    assert second.entry.fetched_at.endswith("Z") and len(second.entry.fetched_at) == 20
    assert second.entry.file.read_bytes() == CSV
    assert [p.suffix for p in cache.directory.iterdir()] == [".csv"]


def test_different_query_order_is_fetched_separately(
    https_server: TestServer, cache: UrlCache
) -> None:
    https_server.routes.routes["/f?a=1&b=2"] = body(CSV)
    https_server.routes.routes["/f?b=2&a=1"] = body(CSV2)
    a = _get(cache, https_server.url("/f?a=1&b=2"))
    b = _get(cache, https_server.url("/f?b=2&a=1"))
    assert a.entry.sha256 != b.entry.sha256 and not b.reused


def test_failure_is_not_cached(https_server: TestServer, cache: UrlCache) -> None:
    url = https_server.url("/flaky.csv")
    https_server.routes.routes["/flaky.csv"] = body(b"busy", status=503, ctype="text/plain")
    with pytest.raises(FetchError, match="503"):
        _get(cache, url)
    assert cache.entries() == []
    https_server.routes.routes["/flaky.csv"] = body(CSV)
    assert _get(cache, url).reused is False
    assert https_server.routes.count("/flaky.csv") == 2


def _no_files(cache: UrlCache) -> bool:
    d = cache.directory
    return d is None or [p for p in d.iterdir() if p.suffix != ".csv"] == []


def test_timed_out_and_cancelled_fetches_leave_nothing(
    https_server: TestServer, cache: UrlCache
) -> None:
    stop = threading.Event()
    https_server.routes.routes["/slow.csv"] = slow(CSV * 5, 0.3, stop=stop)
    url = https_server.url("/slow.csv")
    try:
        with pytest.raises(FetchTimeout):
            _get(cache, url, call_deadline=time.monotonic() + 0.5, call_limit_text="0.5 s")
        assert cache.entries() == [] and _no_files(cache)
        token = funnel.CancelToken()
        threading.Timer(0.4, token.cancel).start()
        with pytest.raises(FetchCancelled):
            _get(cache, url, cancel=token)
        assert cache.entries() == [] and _no_files(cache)
        assert cache.directory is not None and list(cache.directory.iterdir()) == []
    finally:
        stop.set()
    # A later call with enough time fetches the URL completely.
    https_server.routes.routes["/slow.csv"] = body(CSV * 5)
    fetched = _get(cache, url)
    assert fetched.entry.file.read_bytes() == CSV * 5


def test_cancellation_after_the_body_arrived_commits_nothing(
    https_server: TestServer, cache: UrlCache
) -> None:
    """The commit happens under the call's gate and only while the call is
    live: a call cancelled under the gate (as run_off_loop does) never adds
    an entry, even when its download already completed."""
    https_server.routes.routes["/a.csv"] = body(CSV)
    token = funnel.CancelToken()
    gate = PublishGate()
    original = cache.fetcher.fetch

    def fetch_then_cancel(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        with gate:
            token.cancel()
        return result

    cache.fetcher.fetch = fetch_then_cancel  # type: ignore[method-assign, assignment]
    with pytest.raises(FetchCancelled):
        _get(cache, https_server.url("/a.csv"), cancel=token, gate=gate)
    assert cache.entries() == [] and _no_files(cache)
    assert cache.directory is not None and list(cache.directory.iterdir()) == []


def test_two_threads_share_one_fetch(https_server: TestServer, cache: UrlCache) -> None:
    https_server.routes.routes["/a.csv"] = delayed(0.5, body(CSV))
    url = https_server.url("/a.csv")
    results: list[Fetched] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(_get(cache, url))
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert https_server.routes.count("/a.csv") == 1
    assert {r.entry.sha256 for r in results} == {hashlib.sha256(CSV).hexdigest()}
    assert {r.entry.fetched_at for r in results} == {results[0].entry.fetched_at}
    assert sorted(r.reused for r in results) == [False, True]


def test_waiter_fetches_itself_when_the_first_call_is_cancelled(
    https_server: TestServer, cache: UrlCache
) -> None:
    stop = threading.Event()
    https_server.routes.routes["/a.csv"] = slow(CSV, 0.2, stop=stop)
    url = https_server.url("/a.csv")
    token = funnel.CancelToken()
    first_error: list[BaseException] = []

    def first() -> None:
        try:
            _get(cache, url, cancel=token)
        except BaseException as exc:
            first_error.append(exc)

    t = threading.Thread(target=first)
    t.start()
    time.sleep(0.3)  # the first call is downloading
    second: list[Fetched] = []

    def waiter() -> None:
        second.append(_get(cache, url))

    w = threading.Thread(target=waiter)
    w.start()
    time.sleep(0.2)
    token.cancel()
    t.join()
    w.join(timeout=30)
    stop.set()
    assert first_error and isinstance(first_error[0], FetchCancelled)
    assert second and second[0].reused is False
    assert second[0].entry.file.read_bytes() == CSV
    assert https_server.routes.count("/a.csv") == 2


def test_eviction_refetches_and_detects_changed_content(
    https_server: TestServer, certs: Certs
) -> None:
    cache = UrlCache(test_fetcher(certs), max_total_bytes=40)
    try:
        r = https_server.routes.routes
        r["/a.csv"] = body(CSV)  # 16 bytes
        r["/b.csv"] = body(CSV2)
        r["/c.csv"] = body(CSV)
        a = _get(cache, https_server.url("/a.csv"))
        _get(cache, https_server.url("/b.csv"))
        _get(cache, https_server.url("/c.csv"))  # 48 bytes: /a.csv is dropped
        assert [e.url.rsplit("/", 1)[1] for e in cache.entries()] == ["b.csv", "c.csv"]
        assert not a.entry.file.exists()
        # Unchanged: fetched again transparently, same hash and fetch time.
        again = _get(cache, https_server.url("/a.csv"))
        assert again.reused is False and again.entry.sha256 == a.entry.sha256
        assert again.entry.fetched_at == a.entry.fetched_at
        assert https_server.routes.count("/a.csv") == 2
        # /b.csv was dropped meanwhile; its content changes upstream.
        assert "b.csv" not in [e.url.rsplit("/", 1)[1] for e in cache.entries()]
        r["/b.csv"] = body(b"time,a\n0,9\n")
        with pytest.raises(FetchError, match="changed during this server process") as info:
            _get(cache, https_server.url("/b.csv"))
        text = str(info.value)
        assert hashlib.sha256(CSV2).hexdigest() in text
        assert hashlib.sha256(b"time,a\n0,9\n").hexdigest() in text
        assert "restart the server" in text
    finally:
        cache.cleanup()


def test_entries_in_use_are_not_evicted(https_server: TestServer, certs: Certs) -> None:
    cache = UrlCache(test_fetcher(certs), max_total_bytes=20)
    try:
        https_server.routes.routes["/a.csv"] = body(CSV)
        https_server.routes.routes["/b.csv"] = body(CSV2)
        with cache.use(parse_url(https_server.url("/a.csv"))) as a:
            _get(cache, https_server.url("/b.csv"))
            assert a.entry.file.read_bytes() == CSV  # pinned while in use
    finally:
        cache.cleanup()


def test_cleanup_removes_the_directory(https_server: TestServer, certs: Certs) -> None:
    cache = UrlCache(test_fetcher(certs))
    https_server.routes.routes["/a.csv"] = body(CSV)
    _get(cache, https_server.url("/a.csv"))
    d = cache.directory
    assert d is not None and d.is_dir()
    cache.cleanup()
    assert not d.exists() and cache.directory is None
    with pytest.raises(FetchError, match="shutting down"):
        _get(cache, https_server.url("/a.csv"))
    cache.cleanup()  # idempotent


def test_an_unused_cache_creates_nothing(tmp_path: Path, certs: Certs,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    cache = UrlCache(test_fetcher(certs))
    cache.cleanup()
    assert list(tmp_path.iterdir()) == []


def test_size_cap_bounds_the_total(certs: Certs) -> None:
    cfg = FetchConfig(allow_network=True, max_download_mb=1.5)
    assert UrlCache(test_fetcher(certs, cfg)).max_total_bytes == 15_000_000


def _wait_until(cond: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.005)
    return False


def test_bytes_of_a_download_in_progress_count_toward_the_bound(
    https_server: TestServer, certs: Certs
) -> None:
    """The bound covers the copies plus what downloads in progress have
    written: a cached copy is dropped before the new download completes."""
    cache = UrlCache(test_fetcher(certs), max_total_bytes=24)
    stop = threading.Event()
    try:
        https_server.routes.routes["/a.csv"] = body(CSV)  # 16 bytes
        https_server.routes.routes["/slow.csv"] = slow(CSV2, 0.05, stop=stop)
        a = _get(cache, https_server.url("/a.csv"))
        t = threading.Thread(target=_get, args=(cache, https_server.url("/slow.csv")))
        t.start()
        # 16 cached + 9 written > 24: /a.csv goes while /slow.csv still arrives.
        assert _wait_until(lambda: not a.entry.file.exists())
        with cache._lock:
            written = sum(cache._in_flight.values())
        assert t.is_alive() and 9 <= written < len(CSV2)
        assert cache.entries() == []
        t.join()
        assert [e.url.rsplit("/", 1)[1] for e in cache.entries()] == ["slow.csv"]
    finally:
        stop.set()
        cache.cleanup()


def test_downloads_at_once_are_limited(
    https_server: TestServer, certs: Certs, monkeypatch: pytest.MonkeyPatch
) -> None:
    import simtest_funnel_mcp.urlcache as urlcache

    monkeypatch.setattr(urlcache, "MAX_IN_FLIGHT", 1)
    cache = UrlCache(test_fetcher(certs))
    stop = threading.Event()
    try:
        https_server.routes.routes["/slow.csv"] = slow(CSV, 0.02, stop=stop)
        https_server.routes.routes["/b.csv"] = body(CSV2)
        t = threading.Thread(target=_get, args=(cache, https_server.url("/slow.csv")))
        t.start()
        assert _wait_until(lambda: bool(cache._in_flight))
        with pytest.raises(FetchError, match="other URLs are being downloaded right now"):
            _get(cache, https_server.url("/b.csv"))
        t.join()
        # Afterwards the next download runs.
        assert _get(cache, https_server.url("/b.csv")).entry.file.read_bytes() == CSV2
    finally:
        stop.set()
        cache.cleanup()


def test_remembered_hashes_are_bounded(
    https_server: TestServer, certs: Certs, monkeypatch: pytest.MonkeyPatch
) -> None:
    import simtest_funnel_mcp.urlcache as urlcache

    monkeypatch.setattr(urlcache, "MAX_SEEN", 2)
    cache = UrlCache(test_fetcher(certs))
    try:
        for name in ("a", "b", "c"):
            https_server.routes.routes[f"/{name}.csv"] = body(CSV)
            _get(cache, https_server.url(f"/{name}.csv"))
        assert [u.rsplit("/", 1)[1] for u in cache._seen] == ["b.csv", "c.csv"]
    finally:
        cache.cleanup()
