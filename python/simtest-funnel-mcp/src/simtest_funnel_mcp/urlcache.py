"""Process-lifetime cache of fetched URLs (design.md §6, §7 of add-mcp-url-ingestion).

The first call that uses a URL fetches it into a private temporary
directory; later calls in the same process reuse that copy without
connecting, so a URL gives the same content for the life of the process.
The directory is created on the first fetch and removed at exit.

- A fetch writes ``<random>.part`` and renames it into place only when the
  body is complete and the call is still live, checked under the call's
  :class:`~simtest_funnel_mcp.server.PublishGate`-like gate, so a cancelled
  or timed-out call leaves no entry and no file. Failures are not cached.
- One fetch per URL at a time (single flight): a second call waits for the
  running fetch within its own time limit and cancellation, and fetches
  itself if that fetch failed.
- The total size is bounded (10 x the size cap by default), counting the
  bytes already written by downloads in progress; least recently used copies
  not in use are dropped, and their hashes remembered (the last
  :data:`MAX_SEEN` URLs): a dropped URL fetched again must have the same
  SHA-256. At most :data:`MAX_IN_FLIGHT` downloads run at once.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import secrets
import shutil
import tempfile
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from simtest_funnel_mcp.fetch import (
    Cancellable,
    FetchCancelled,
    FetchError,
    Fetcher,
    FetchTimeout,
    ParsedUrl,
)

#: Prefix of the cache directory in the system temporary directory.
DIR_PREFIX = "simtest-funnel-mcp-"
#: Total cache size as a multiple of the size cap.
TOTAL_FACTOR = 10
#: How often a call waiting for another call's fetch checks its own limits.
WAIT_SLICE = 0.1
#: Downloads running at once at most (each at most the size cap, so together
#: at most the default total bound).
MAX_IN_FLIGHT = TOTAL_FACTOR
#: URLs whose hash is remembered after their copy was dropped.
MAX_SEEN = 4096


@dataclass(frozen=True)
class CacheEntry:
    """A complete cached copy."""

    url: str
    final_url: str
    #: UTC, ISO 8601 with ``Z`` and whole seconds.
    fetched_at: str
    size: int
    sha256: str
    content_type: str | None
    file: Path


@dataclass(frozen=True)
class Fetched:
    """An entry as seen by one call."""

    entry: CacheEntry
    #: False for the call that fetched it.
    reused: bool


class _Flight:
    def __init__(self) -> None:
        self.done = threading.Event()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class UrlCache:
    """The URL cache of one server process."""

    def __init__(self, fetcher: Fetcher, max_total_bytes: int | None = None) -> None:
        self.fetcher = fetcher
        self.max_total_bytes = (
            max_total_bytes if max_total_bytes is not None
            else TOTAL_FACTOR * fetcher.config.max_bytes
        )
        self._lock = threading.Lock()
        self._index: OrderedDict[str, CacheEntry] = OrderedDict()
        self._pins: dict[str, int] = {}
        self._flights: dict[str, _Flight] = {}
        #: Hash and fetch time of the last :data:`MAX_SEEN` URLs cached
        #: (survives eviction).
        self._seen: OrderedDict[str, tuple[str, str]] = OrderedDict()
        #: Bytes written so far by each download in progress.
        self._in_flight: dict[int, int] = {}
        self._next_flight = 0
        self._dir: Path | None = None
        self._closed = False

    # -- directory ---------------------------------------------------------

    @property
    def directory(self) -> Path | None:
        """The cache directory, ``None`` before the first fetch."""
        return self._dir

    def _ensure_dir(self) -> Path:
        with self._lock:
            if self._closed:
                raise FetchError("the server is shutting down")
            if self._dir is None:
                # mkdtemp creates the directory with mode 0700 on POSIX.
                self._dir = Path(tempfile.mkdtemp(prefix=DIR_PREFIX))
                atexit.register(self.cleanup)
            return self._dir

    def cleanup(self) -> None:
        """Remove the cache directory (idempotent; no new fetch afterwards)."""
        with self._lock:
            self._closed = True
            d, self._dir = self._dir, None
            self._index.clear()
        if d is not None:
            shutil.rmtree(d, ignore_errors=True)

    # -- lookup ------------------------------------------------------------

    def use(
        self,
        url: ParsedUrl,
        *,
        cancel: Cancellable | None = None,
        call_deadline: float | None = None,
        call_limit_text: str | None = None,
        gate: AbstractContextManager[object] | None = None,
    ) -> AbstractContextManager[Fetched]:
        """Context manager giving the cached copy of ``url`` (fetched first
        if needed); the copy is not evicted while the block runs."""
        return self._use(url, cancel, call_deadline, call_limit_text, gate)

    @contextlib.contextmanager
    def _use(
        self,
        url: ParsedUrl,
        cancel: Cancellable | None,
        call_deadline: float | None,
        call_limit_text: str | None,
        gate: AbstractContextManager[object] | None,
    ) -> Iterator[Fetched]:
        fetched = self._get(url, cancel, call_deadline, call_limit_text, gate)
        try:
            yield fetched
        finally:
            with self._lock:
                n = self._pins.get(url.url, 1) - 1
                if n:
                    self._pins[url.url] = n
                else:
                    self._pins.pop(url.url, None)
                self._evict()

    def _get(
        self,
        url: ParsedUrl,
        cancel: Cancellable | None,
        call_deadline: float | None,
        call_limit_text: str | None,
        gate: AbstractContextManager[object] | None,
    ) -> Fetched:
        key = url.url
        while True:
            with self._lock:
                entry = self._index.get(key)
                if entry is not None:
                    self._index.move_to_end(key)
                    self._pins[key] = self._pins.get(key, 0) + 1
                    return Fetched(entry, reused=True)
                flight = self._flights.get(key)
                owner = flight is None
                if flight is None:
                    flight = self._flights[key] = _Flight()
            if not owner:
                self._wait(flight, url, cancel, call_deadline, call_limit_text)
                continue  # the entry, or our own fetch if that one failed
            try:
                entry = self._fetch(url, cancel, call_deadline, call_limit_text, gate)
            finally:
                with self._lock:
                    self._flights.pop(key, None)
                flight.done.set()
            return Fetched(entry, reused=False)

    def _wait(
        self,
        flight: _Flight,
        url: ParsedUrl,
        cancel: Cancellable | None,
        call_deadline: float | None,
        call_limit_text: str | None,
    ) -> None:
        own = time.monotonic() + self.fetcher.config.fetch_timeout
        while not flight.done.wait(WAIT_SLICE):
            if cancel is not None and cancel.cancelled:
                raise FetchCancelled(
                    f"the call was cancelled while waiting for {url.host} to be fetched"
                )
            now = time.monotonic()
            if call_deadline is not None and now >= call_deadline:
                raise FetchTimeout(
                    f"the call's time limit of {call_limit_text or 'the call'} was reached "
                    f"while waiting for {url.host} to be fetched; pass a larger time_limit"
                )
            if now >= own:
                raise FetchTimeout(
                    f"the fetch timeout of {self.fetcher.config.fetch_timeout:g} s was reached "
                    f"while waiting for {url.host} to be fetched by another call"
                )

    def _fetch(
        self,
        url: ParsedUrl,
        cancel: Cancellable | None,
        call_deadline: float | None,
        call_limit_text: str | None,
        gate: AbstractContextManager[object] | None,
    ) -> CacheEntry:
        directory = self._ensure_dir()
        with self._lock:
            if len(self._in_flight) >= MAX_IN_FLIGHT:
                raise FetchError(
                    f"{len(self._in_flight)} other URLs are being downloaded right now (at most "
                    f"{MAX_IN_FLIGHT} at once); try {url.host} again when they have finished"
                )
            flight = self._next_flight
            self._next_flight += 1
            self._in_flight[flight] = 0
        part = directory / f"{secrets.token_hex(8)}.part"
        final = directory / f"{_url_hash(url.url)}.csv"
        try:
            with open(part, "xb") as fh:
                result = self.fetcher.fetch(
                    url, _CountedFile(fh, self, flight), cancel=cancel,
                    call_deadline=call_deadline, call_limit_text=call_limit_text,
                )
            with self._lock:
                seen = self._seen.get(url.url)
            if seen is not None and seen[0] != result.sha256:
                raise FetchError(
                    f"content of {url.url} changed during this server process (sha256 "
                    f"{seen[0]} then {result.sha256}); restart the server to use the new "
                    "content"
                )
            with gate if gate is not None else contextlib.nullcontext():
                if cancel is not None and cancel.cancelled:
                    raise FetchCancelled(f"the call was cancelled while fetching from {url.host}")
                if call_deadline is not None and time.monotonic() >= call_deadline:
                    raise FetchTimeout(
                        f"the call's time limit of {call_limit_text or 'the call'} was reached "
                        f"while fetching from {url.host}; pass a larger time_limit"
                    )
                with self._lock:
                    if self._closed:
                        raise FetchError("the server is shutting down")
                    os.replace(part, final)
                    entry = CacheEntry(
                        url=url.url,
                        final_url=result.final_url,
                        fetched_at=seen[1] if seen is not None else _now_iso(),
                        size=result.size,
                        sha256=result.sha256,
                        content_type=result.content_type,
                        file=final,
                    )
                    self._index[url.url] = entry
                    self._in_flight.pop(flight, None)  # now counted as an entry
                    self._remember(url.url, entry.sha256, entry.fetched_at)
                    self._pins[url.url] = self._pins.get(url.url, 0) + 1
                    self._evict()
            return entry
        except OSError as exc:
            raise FetchError(f"cannot store the copy of {url.url}: {exc}") from None
        finally:
            with self._lock:
                self._in_flight.pop(flight, None)
            with contextlib.suppress(OSError):
                part.unlink()

    def _remember(self, url: str, sha256: str, fetched_at: str) -> None:
        """Record the hash of ``url``, forgetting the oldest beyond
        :data:`MAX_SEEN` (caller holds the lock)."""
        self._seen[url] = (sha256, fetched_at)
        self._seen.move_to_end(url)
        while len(self._seen) > MAX_SEEN:
            self._seen.popitem(last=False)

    def _count(self, flight: int, n: int) -> None:
        """``n`` more bytes written by download ``flight``; evict to stay
        within the bound."""
        with self._lock:
            if flight in self._in_flight:
                self._in_flight[flight] += n
                self._evict()

    def _evict(self) -> None:
        """Drop least recently used, unpinned copies while the copies plus the
        bytes of downloads in progress exceed the size bound (caller holds the
        lock)."""
        total = sum(e.size for e in self._index.values()) + sum(self._in_flight.values())
        for key in list(self._index):
            if total <= self.max_total_bytes:
                break
            if self._pins.get(key):
                continue
            entry = self._index.pop(key)
            total -= entry.size
            with contextlib.suppress(OSError):
                entry.file.unlink()

    # -- inspection (tests) --------------------------------------------------

    def entries(self) -> list[CacheEntry]:
        with self._lock:
            return list(self._index.values())


class _CountedFile:
    """The ``.part`` file of a download, counting what is written toward the
    cache bound."""

    def __init__(self, fh: BinaryIO, cache: UrlCache, flight: int) -> None:
        self._fh = fh
        self._cache = cache
        self._flight = flight

    def write(self, data: bytes, /) -> int:
        n = self._fh.write(data)
        self._cache._count(self._flight, len(data))
        return n


def _url_hash(url: str) -> str:
    import hashlib

    return hashlib.sha256(url.encode("utf-8")).hexdigest()
