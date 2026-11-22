"""Fetching URLs: parsing, address check, pinned TLS connection, redirects,
content checks and limits, against a local HTTPS server (offline)."""

from __future__ import annotations

import gzip
import io
import ipaddress
import socket
import threading
import time
import tracemalloc
from typing import Any

import pytest
from urlserver import (
    Certs,
    CountingResolver,
    TestServer,
    body,
    free_port,
    gzip_bomb,
    redirect,
    send,
    slow,
    test_fetcher,
)

import simtest.funnel as funnel
from simtest_funnel_mcp.fetch import (
    USER_AGENT,
    FetchCancelled,
    FetchConfig,
    FetchError,
    Fetcher,
    FetchResult,
    FetchTimeout,
    is_url,
    parse_url,
    public_address_refusal,
)

CSV = b"time,a\n0,1\n1,2\n"


def _fetch(fetcher: Fetcher, url: str, **kwargs: Any) -> tuple[FetchResult, bytes]:
    buf = io.BytesIO()
    result = fetcher.fetch(parse_url(url), buf, **kwargs)
    return result, buf.getvalue()


# --------------------------------------------------------------------------
# 2.1 URL parsing and policy
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.org/a.csv", True),
        ("HTTP://x", True),
        ("file:///etc/hosts", True),
        ("C:\\data\\a.csv", False),
        ("C:/data/a.csv", False),
        ("data/a.csv", False),
        ("/abs/a.csv", False),
        ("  https://example.org/a.csv", True),
    ],
)
def test_is_url(raw: str, expected: bool) -> None:
    assert is_url(raw) is expected


def test_only_https_is_accepted() -> None:
    with pytest.raises(FetchError, match="only https URLs are fetched, not http") as info:
        parse_url("http://example.org/run.csv")
    assert "https form" in str(info.value) and "local path" in str(info.value)
    for raw in ("file:///etc/hosts", "ftp://example.org/a.csv", "gopher://x/"):
        with pytest.raises(FetchError, match="only https URLs are fetched"):
            parse_url(raw)
    with pytest.raises(FetchError, match="no host"):
        parse_url("https:///a.csv")


def test_credentials_are_refused_without_echoing_the_password() -> None:
    for raw in (
        "https://user:secret@example.org/run.csv",
        "https://user@example.org/run.csv",
        "https://:secret@example.org/run.csv",
    ):
        with pytest.raises(FetchError, match="credentials") as info:
            parse_url(raw)
        assert "secret" not in str(info.value)
        assert "example.org/run.csv" in str(info.value)


def test_normalisation() -> None:
    a = parse_url("https://Example.org:443/a.csv#top")
    assert a.url == "https://example.org/a.csv"
    assert a.host == "example.org" and a.port == 443 and a.target == "/a.csv"
    assert parse_url("HTTPS://EXAMPLE.ORG").url == "https://example.org/"
    assert parse_url("https://example.org:8443/x?b=1").url == "https://example.org:8443/x?b=1"
    # Query order is kept: different URLs.
    assert parse_url("https://e.org/f?a=1&b=2").url != parse_url("https://e.org/f?b=2&a=1").url
    # IDNA host, percent-encoded non-ASCII path.
    u = parse_url("https://Bücher.example/ä b.csv")
    assert u.url == "https://xn--bcher-kva.example/%C3%A4%20b.csv"
    assert parse_url("https://[2001:4860::8888]:444/").url == "https://[2001:4860::8888]:444/"


def test_allow_list_is_exact() -> None:
    f = Fetcher(FetchConfig(allow_network=True, allow_hosts=("open-meteo.com",)))
    f.check_host_allowed(parse_url("https://Open-Meteo.com/x"))
    with pytest.raises(FetchError, match="api.open-meteo.com is not in the allowed hosts") as info:
        f.check_host_allowed(parse_url("https://api.open-meteo.com/x"))
    assert "--allow-host api.open-meteo.com" in str(info.value)
    with pytest.raises(FetchError, match="not in the allowed hosts"):
        f.check_host_allowed(parse_url("https://evil-open-meteo.com/x"))
    Fetcher(FetchConfig(allow_network=True)).check_host_allowed(parse_url("https://any.org/"))


# --------------------------------------------------------------------------
# 2.2 Address check
# --------------------------------------------------------------------------

REFUSED = [
    "127.0.0.1", "127.8.9.10", "10.0.0.5", "172.16.0.1", "192.168.1.10",
    "169.254.169.254", "100.64.0.1", "0.0.0.0", "255.255.255.255", "224.0.0.1",
    "240.0.0.1", "192.0.2.1", "198.51.100.7", "203.0.113.9", "198.18.0.1",
    "::1", "::", "fe80::1", "fc00::1", "fd12:3456::1", "ff02::1", "2001:db8::1",
    "::ffff:10.0.0.1", "::ffff:127.0.0.1", "::ffff:169.254.169.254",
    "64:ff9b::7f00:1", "64:ff9b::a00:1", "64:ff9b:1::808:808",
    "2002:0a00:0001::1", "2002:7f00:0001::1", "2001::1", "2001:0:4136:e378::1",
    "::a00:1", "::808:808", "::ffff:0:808:808",
]
ACCEPTED = [
    "8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111", "2a00:1450:4001::1",
    "::ffff:8.8.8.8", "64:ff9b::808:808", "2002:0808:0808::1",
]


@pytest.mark.parametrize("address", REFUSED)
def test_non_public_addresses_are_refused(address: str) -> None:
    assert public_address_refusal(ipaddress.ip_address(address)) is not None


@pytest.mark.parametrize("address", ACCEPTED)
def test_public_addresses_are_accepted(address: str) -> None:
    assert public_address_refusal(ipaddress.ip_address(address)) is None


def _public_fetcher(resolver: CountingResolver) -> Fetcher:
    """Production address policy with an injected resolver."""
    return Fetcher(FetchConfig(allow_network=True), resolver=resolver)


def test_loopback_and_metadata_literals_are_refused_before_connecting() -> None:
    resolver = CountingResolver()
    f = _public_fetcher(resolver)
    for url in ("https://127.0.0.1/run.csv", "https://169.254.169.254/latest/meta-data",
                "https://[::ffff:127.0.0.1]/x", "https://[::1]:8443/x"):
        with pytest.raises(FetchError, match="non-public address"):
            _fetch(f, url)
    assert resolver.calls == []  # literals are never resolved


def test_localhost_resolving_to_loopback_is_refused(https_server: TestServer) -> None:
    https_server.routes.routes["/run.csv"] = body(CSV)
    f = _public_fetcher(CountingResolver())
    with pytest.raises(FetchError, match="resolves to a non-public address"):
        _fetch(f, https_server.url("/run.csv", host="localhost"))
    assert https_server.routes.seen == []


def test_mixed_public_and_private_answer_is_refused_without_listing_addresses() -> None:
    resolver = CountingResolver(answers={"mixed.test": ["93.184.216.34", "10.0.0.5"]})
    with pytest.raises(FetchError) as info:
        _fetch(_public_fetcher(resolver), "https://mixed.test/a.csv")
    text = str(info.value)
    assert "mixed.test resolves to a non-public address" in text
    assert "10.0.0.5" not in text
    resolver = CountingResolver(answers={"mapped.test": ["::ffff:192.168.0.1"]})
    with pytest.raises(FetchError, match="non-public"):
        _fetch(_public_fetcher(resolver), "https://mapped.test/a.csv")


def test_resolution_failure_is_its_own_error() -> None:
    with pytest.raises(FetchError, match="cannot resolve host nowhere.test"):
        _fetch(_public_fetcher(CountingResolver()), "https://nowhere.test/a.csv")


# --------------------------------------------------------------------------
# 2.3 Pinned TLS connection
# --------------------------------------------------------------------------


def test_request_is_a_plain_get(https_server: TestServer, certs: Certs) -> None:
    https_server.routes.routes["/run.csv?x=1"] = body(CSV, headers={"Set-Cookie": "a=b"})
    https_server.routes.routes["/again.csv"] = body(CSV)
    f = test_fetcher(certs)
    result, data = _fetch(f, https_server.url("/run.csv?x=1"))
    assert data == CSV and result.size == len(CSV)
    _fetch(f, https_server.url("/again.csv"))
    first, second = https_server.routes.seen
    assert first.method == "GET" and first.path == "/run.csv?x=1"
    assert first.headers["user-agent"] == USER_AGENT
    assert USER_AGENT.startswith("simtest-funnel-mcp/")
    assert first.headers["host"] == f"data.test:{https_server.port}"
    assert set(first.headers) == {"host", "user-agent", "accept", "accept-encoding", "connection"}
    assert first.headers["accept-encoding"] == "gzip"
    # The cookie the server set is not sent back.
    assert "cookie" not in second.headers and "authorization" not in second.headers


def test_connection_goes_to_the_checked_address_without_a_second_lookup(
    https_server: TestServer, certs: Certs
) -> None:
    """data.test exists only in the injected resolver: the fetch works, so
    the connection used the checked address; a resolver that would answer
    private on a second lookup is asked exactly once."""
    https_server.routes.routes["/a.csv"] = body(CSV)

    class Rebinding(CountingResolver):
        def __call__(self, host: str, port: int) -> list[str]:
            self.calls.append(host)
            return ["127.0.0.1"] if len(self.calls) == 1 else ["10.0.0.5"]

    resolver = Rebinding()
    f = test_fetcher(certs, resolver=resolver)
    _, data = _fetch(f, https_server.url("/a.csv"))
    assert data == CSV
    assert resolver.calls == ["data.test"]
    assert https_server.routes.count("/a.csv") == 1


def test_certificate_is_checked_against_the_url_host(certs: Certs) -> None:
    wrong = TestServer(certs.wrong_cert, certs.wrong_key)
    try:
        wrong.routes.routes["/a.csv"] = body(CSV)
        with pytest.raises(FetchError, match="certificate verification failed for data.test"):
            _fetch(test_fetcher(certs), wrong.url("/a.csv"))
        assert wrong.routes.seen == []
        # The same server is fine for the name its certificate names.
        _, data = _fetch(test_fetcher(certs), wrong.url("/a.csv", host="elsewhere.test"))
        assert data == CSV
    finally:
        wrong.close()


def test_untrusted_certificate_fails(https_server: TestServer, certs: Certs) -> None:
    import ssl

    https_server.routes.routes["/a.csv"] = body(CSV)
    f = Fetcher(
        FetchConfig(allow_network=True), resolver=CountingResolver(),
        address_policy=test_fetcher(certs).address_policy,
        ssl_context=ssl.create_default_context(),  # does not trust the test CA
    )
    with pytest.raises(FetchError, match="certificate verification failed for data.test"):
        _fetch(f, https_server.url("/a.csv"))


def test_proxy_variables_are_ignored(
    https_server: TestServer, certs: Certs, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = f"http://127.0.0.1:{free_port()}"
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY",
                 "all_proxy"):
        monkeypatch.setenv(name, dead)
    monkeypatch.setenv("NO_PROXY", "")
    https_server.routes.routes["/a.csv"] = body(CSV)
    _, data = _fetch(test_fetcher(certs), https_server.url("/a.csv"))
    assert data == CSV
    assert https_server.routes.seen[0].path == "/a.csv"  # direct, not via a proxy


# --------------------------------------------------------------------------
# 2.4 Redirects, status and content
# --------------------------------------------------------------------------


def test_redirects_are_followed_and_rechecked(https_server: TestServer, certs: Certs) -> None:
    r = https_server.routes.routes
    r["/a"] = redirect(https_server.url("/b", host="other.test"), 301)
    r["/b"] = redirect("/c", 307)
    r["/c"] = body(CSV)
    result, data = _fetch(test_fetcher(certs), https_server.url("/a"))
    assert data == CSV
    assert result.final_url == https_server.url("/c", host="other.test")
    hosts = [s.headers["host"].split(":")[0] for s in https_server.routes.seen]
    assert hosts == ["data.test", "other.test", "other.test"]


def test_redirect_to_http_is_refused(https_server: TestServer, certs: Certs) -> None:
    https_server.routes.routes["/a"] = redirect("http://data.test/a.csv")
    with pytest.raises(FetchError, match="leaves https"):
        _fetch(test_fetcher(certs), https_server.url("/a"))


def test_redirect_to_a_private_address_is_refused(https_server: TestServer, certs: Certs) -> None:
    https_server.routes.routes["/a"] = redirect("https://192.168.1.10/run.csv")
    resolver = CountingResolver(answers={"lan.test": ["192.168.1.10"]})
    with pytest.raises(FetchError, match="192.168.1.10 is a non-public address"):
        _fetch(test_fetcher(certs, resolver=resolver), https_server.url("/a"))
    https_server.routes.routes["/b"] = redirect("https://lan.test/run.csv")
    with pytest.raises(FetchError, match="redirect from data.test to lan.test: .*non-public"):
        _fetch(test_fetcher(certs, resolver=resolver), https_server.url("/b"))


def test_redirect_to_an_unlisted_host(https_server: TestServer, certs: Certs) -> None:
    https_server.routes.routes["/a"] = redirect(https_server.url("/b", host="other.test"))
    config = FetchConfig(allow_network=True, allow_hosts=("data.test",))
    resolver = CountingResolver()
    with pytest.raises(FetchError) as info:
        _fetch(test_fetcher(certs, config, resolver), https_server.url("/a"))
    text = str(info.value)
    assert "redirect from data.test to other.test" in text
    assert "--allow-host other.test" in text
    assert resolver.calls == ["data.test"]  # the unlisted host was never resolved


def test_redirect_hops_are_limited(https_server: TestServer, certs: Certs) -> None:
    r = https_server.routes.routes
    for i in range(6):
        r[f"/r{i}"] = redirect(f"/r{i + 1}")
    r["/r6"] = body(CSV)
    with pytest.raises(FetchError, match="more than 5 redirects"):
        _fetch(test_fetcher(certs), https_server.url("/r0"))
    _, data = _fetch(test_fetcher(certs), https_server.url("/r1"))  # exactly 5 hops
    assert data == CSV


def test_error_status_quotes_a_short_reason(https_server: TestServer, certs: Certs) -> None:
    reason = b'{"error":true,"reason":"End-date must be larger or equals than start-date"}'
    https_server.routes.routes["/bad"] = body(reason, status=400, ctype="application/json")
    with pytest.raises(FetchError) as info:
        _fetch(test_fetcher(certs), https_server.url("/bad"))
    text = str(info.value)
    assert "data.test answered 400 Bad Request" in text
    assert "End-date must be larger or equals than start-date" in text
    https_server.routes.routes["/long"] = body(b"x" * 5000, status=503, ctype="text/plain")
    with pytest.raises(FetchError) as info:
        _fetch(test_fetcher(certs), https_server.url("/long"))
    assert "503" in str(info.value) and str(info.value).count("x") <= 300


def test_html_is_refused_by_type_and_by_content(https_server: TestServer, certs: Certs) -> None:
    r = https_server.routes.routes
    r["/view"] = body(b"<html><body>table</body></html>", ctype="text/html; charset=utf-8")
    r["/sniff"] = body(b"\n  <!DOCTYPE html>\n<html></html>", ctype="text/plain")
    for path in ("/view", "/sniff"):
        with pytest.raises(FetchError, match="returned an HTML page") as info:
            _fetch(test_fetcher(certs), https_server.url(path))
        assert "raw-file URL" in str(info.value)


def test_json_and_other_types_are_refused(https_server: TestServer, certs: Certs) -> None:
    r = https_server.routes.routes
    r["/json"] = body(b'{"a": 1}', ctype="application/json")
    r["/pdf"] = body(b"%PDF", ctype="application/pdf")
    with pytest.raises(FetchError, match="application/json, not CSV; only CSV is read") as info:
        _fetch(test_fetcher(certs), https_server.url("/json"))
    assert "format=csv" in str(info.value)
    with pytest.raises(FetchError, match="content type application/pdf"):
        _fetch(test_fetcher(certs), https_server.url("/pdf"))


def test_accepted_types_charsets_and_encodings(https_server: TestServer, certs: Certs) -> None:
    r = https_server.routes.routes
    r["/gz"] = body(CSV, ctype="text/csv; charset=utf-8", gzipped=True)
    r["/none"] = body(CSV, ctype=None)
    r["/octet"] = body(CSV, ctype="application/octet-stream")
    r["/excel"] = body(CSV, ctype="application/vnd.ms-excel")
    r["/latin"] = body(CSV, ctype="text/csv; charset=latin-1")
    r["/br"] = body(CSV, headers={"Content-Encoding": "br"})
    for path in ("/gz", "/none", "/octet", "/excel"):
        result, data = _fetch(test_fetcher(certs), https_server.url(path))
        assert data == CSV and result.size == len(CSV), path
    with pytest.raises(FetchError, match="charset latin-1"):
        _fetch(test_fetcher(certs), https_server.url("/latin"))
    with pytest.raises(FetchError, match="Content-Encoding br"):
        _fetch(test_fetcher(certs), https_server.url("/br"))


def test_sha256_is_of_the_decompressed_content(https_server: TestServer, certs: Certs) -> None:
    import hashlib

    https_server.routes.routes["/gz"] = body(CSV, gzipped=True)
    result, _ = _fetch(test_fetcher(certs), https_server.url("/gz"))
    assert result.sha256 == hashlib.sha256(CSV).hexdigest()


def test_truncated_body_fails(https_server: TestServer, certs: Certs) -> None:
    https_server.routes.routes["/short"] = body(CSV, length=len(CSV) + 100)

    def gz_cut(h: Any) -> None:
        data = gzip.compress(CSV * 100)[:-20]
        send(h, data, headers={"Content-Encoding": "gzip"})
        # Content-Encoding header set by hand above; body is a truncated stream.

    https_server.routes.routes["/gzcut"] = gz_cut
    with pytest.raises(FetchError, match="broke before the whole file"):
        _fetch(test_fetcher(certs), https_server.url("/short"))
    with pytest.raises(FetchError, match="truncated gzip"):
        _fetch(test_fetcher(certs), https_server.url("/gzcut"))


# --------------------------------------------------------------------------
# 2.5 Limits
# --------------------------------------------------------------------------


def test_announced_length_over_the_cap_is_refused_unread(
    https_server: TestServer, certs: Certs
) -> None:
    https_server.routes.routes["/big"] = body(CSV, length=50_000_000)
    with pytest.raises(FetchError) as info:
        _fetch(test_fetcher(certs), https_server.url("/big"))
    text = str(info.value)
    assert "announces 50000000 bytes" in text and "20 MB" in text and "--max-download-mb" in text


def test_body_over_the_cap_is_stopped(https_server: TestServer, certs: Certs) -> None:
    config = FetchConfig(allow_network=True, max_download_mb=0.001)  # 1000 bytes

    def unannounced(h: Any) -> None:
        h.send_response(200)
        h.send_header("Content-Type", "text/csv")
        h.send_header("Connection", "close")
        h.end_headers()
        h.wfile.write(b"0\n" * 5000)

    https_server.routes.routes["/big"] = unannounced
    with pytest.raises(FetchError, match="over the size cap of 0.001 MB"):
        _fetch(test_fetcher(certs, config), https_server.url("/big"))


@pytest.fixture(scope="module")
def bomb() -> bytes:
    data = gzip_bomb(100_000_000)  # 100 MB of zeros
    assert len(data) < 150_000
    return data


def test_gzip_bomb_is_stopped_at_the_cap_with_bounded_memory(
    https_server: TestServer, certs: Certs, bomb: bytes
) -> None:
    https_server.routes.routes["/bomb"] = lambda h: send(
        h, bomb, ctype="text/csv", headers={"Content-Encoding": "gzip"}
    )

    class Counting(io.RawIOBase):
        written = 0

        def writable(self) -> bool:
            return True

        def write(self, b: Any) -> int:
            self.written += len(b)
            return len(b)

    sink = Counting()
    tracemalloc.start()
    try:
        with pytest.raises(FetchError, match="over the size cap of 20 MB") as info:
            test_fetcher(certs).fetch(
                parse_url(https_server.url("/bomb")), sink  # type: ignore[arg-type]
            )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert "--max-download-mb" in str(info.value)
    assert sink.written <= 20_000_000
    assert peak < 8_000_000, peak  # bounded zlib steps, never the whole expansion


def test_slow_sender_hits_the_fetch_timeout(https_server: TestServer, certs: Certs) -> None:
    stop = threading.Event()
    https_server.routes.routes["/slow"] = slow(CSV * 10, 1.0, stop=stop)
    config = FetchConfig(allow_network=True, fetch_timeout=2.0)
    start = time.monotonic()
    try:
        with pytest.raises(FetchTimeout) as info:
            _fetch(test_fetcher(certs, config), https_server.url("/slow"))
    finally:
        stop.set()
    took = time.monotonic() - start
    assert 1.8 < took < 3.5, took
    text = str(info.value)
    assert "fetch timeout of 2 s" in text and "--fetch-timeout" in text and "data.test" in text


def test_call_deadline_shorter_than_the_fetch_timeout(
    https_server: TestServer, certs: Certs
) -> None:
    stop = threading.Event()
    https_server.routes.routes["/slow"] = slow(CSV * 10, 1.0, stop=stop)
    start = time.monotonic()
    try:
        with pytest.raises(FetchTimeout) as info:
            _fetch(
                test_fetcher(certs), https_server.url("/slow"),
                call_deadline=start + 1.0, call_limit_text="1 s",
            )
    finally:
        stop.set()
    assert time.monotonic() - start < 2.5
    assert "the call's time limit of 1 s" in str(info.value)
    assert "time_limit" in str(info.value)


def test_cancellation_stops_a_download_promptly(https_server: TestServer, certs: Certs) -> None:
    stop = threading.Event()
    https_server.routes.routes["/slow"] = slow(CSV * 10, 1.0, stop=stop)
    token = funnel.CancelToken()
    threading.Timer(0.5, token.cancel).start()
    start = time.monotonic()
    try:
        with pytest.raises(FetchCancelled, match="cancelled"):
            _fetch(test_fetcher(certs), https_server.url("/slow"), cancel=token)
    finally:
        stop.set()
    assert time.monotonic() - start < 1.5


def test_connection_refused_mentions_proxies(certs: Certs) -> None:
    port = free_port()
    with pytest.raises(FetchError) as info:
        _fetch(test_fetcher(certs), f"https://data.test:{port}/a.csv")
    text = str(info.value)
    assert f"cannot connect to data.test port {port}" in text
    assert "proxies are not supported yet" in text
    assert "download the file and pass its local path" in text


def test_connect_timeout(certs: Certs) -> None:
    """A listener whose accept queue is full drops further SYNs on Linux, so
    connecting hangs until the connect timeout."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(0)
    port = listener.getsockname()[1]
    fillers = []
    try:
        for _ in range(8):
            s = socket.socket()
            s.setblocking(False)
            s.connect_ex(("127.0.0.1", port))
            fillers.append(s)
        time.sleep(0.2)
        probe = socket.socket()
        probe.settimeout(0.5)
        try:
            probe.connect(("127.0.0.1", port))
        except (TimeoutError, OSError):
            pass
        else:
            pytest.skip("this platform accepts connections beyond the backlog")
        finally:
            probe.close()
        start = time.monotonic()
        with pytest.raises(FetchError, match="timed out after 1 s") as info:
            _fetch(test_fetcher(certs, connect_timeout=1.0), f"https://data.test:{port}/a")
        assert time.monotonic() - start < 2.5
        assert "proxies are not supported yet" in str(info.value)
    finally:
        for s in fillers:
            s.close()
        listener.close()


def test_unknown_charset_in_an_error_body(https_server: TestServer, certs: Certs) -> None:
    https_server.routes.routes["/e"] = body(b"busy", status=503, ctype="text/plain; charset=nope")
    with pytest.raises(FetchError, match="503 Service Unavailable: busy"):
        _fetch(test_fetcher(certs), https_server.url("/e"))


def test_resolution_failure_mentions_proxies() -> None:
    with pytest.raises(FetchError, match="proxies are not supported yet"):
        _fetch(_public_fetcher(CountingResolver()), "https://nowhere.test/a.csv")
