"""Fetching public ``https://`` URLs (design.md §2-§5 of add-mcp-url-ingestion).

Only the standard library is used for the HTTP exchange, so that every
safety property is visible here:

- URLs are parsed with :func:`urllib.parse.urlsplit`; only ``https`` with a
  host and without user info is accepted (:func:`parse_url`).
- The host is resolved once, every address must pass the address policy
  (:func:`public_address_refusal`: public unicast only, embedded IPv4
  unwrapped), and the TCP connection goes to one of exactly those
  addresses (:class:`_PinnedHTTPSConnection`), while SNI, the ``Host``
  header and the certificate check use the URL's host name. There is no
  second lookup, so a resolver that answers differently later is never
  asked again.
- ``http.client`` never reads proxy variables, ``.netrc`` or cookies, and
  :mod:`urllib.request` is not used. Only the headers in :meth:`Fetcher._request`
  are sent.
- Redirects are followed here (at most :data:`MAX_REDIRECTS`), each hop
  checked again from the start.
- The body is streamed into the caller's file with a size cap counted after
  decompression (bounded ``zlib`` steps), hashed on the way.
- A watchdog thread shuts the socket down when the call is cancelled or the
  fetch deadline passes, so a blocked read returns at once (design §5).
"""

from __future__ import annotations

import errno
import hashlib
import http.client
import ipaddress
import json
import re
import select
import socket
import ssl
import threading
import time
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urljoin, urlsplit

from simtest_funnel_mcp import __version__

#: Default size cap in MB (1 MB = 1 000 000 bytes), counted after decompression.
DEFAULT_MAX_DOWNLOAD_MB = 20.0
#: Default timeout in seconds for a whole fetch (all redirect hops).
DEFAULT_FETCH_TIMEOUT = 30.0
#: Largest accepted ``--fetch-timeout``.
MAX_FETCH_TIMEOUT = 600.0
#: Timeout in seconds of one TCP connection attempt.
CONNECT_TIMEOUT = 10.0
#: Redirect hops followed at most.
MAX_REDIRECTS = 5
#: Bytes read from the socket per step.
READ_BLOCK = 65536
#: How often the watchdog checks cancellation and the deadline (seconds).
WATCH_INTERVAL = 0.05
#: Bytes of a JSON error response read for its reason, and characters shown.
ERROR_BODY_BYTES = 4096
ERROR_REASON_CHARS = 120

USER_AGENT = f"simtest-funnel-mcp/{__version__} (+https://github.com/Symoptia/simtest-funnel)"
ACCEPT = "text/csv, text/plain;q=0.9, */*;q=0.1"

#: Option names, quoted in messages.
ALLOW_NETWORK_OPTION = "--allow-network"
ALLOW_NETWORK_ENV = "SIMTEST_FUNNEL_MCP_ALLOW_NETWORK"
ALLOW_HOST_OPTION = "--allow-host"
MAX_DOWNLOAD_OPTION = "--max-download-mb"
FETCH_TIMEOUT_OPTION = "--fetch-timeout"

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
#: Media types read as CSV.
ACCEPTED_TYPES = frozenset(
    {
        "text/csv",
        "application/csv",
        "text/comma-separated-values",
        "text/plain",
        "application/octet-stream",
        "binary/octet-stream",
        "application/vnd.ms-excel",
    }
)
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_CHARSETS = frozenset({"utf-8", "utf8", "us-ascii", "ascii"})
_PROXY_HINT = (
    "proxies are not supported yet (the server connects directly and ignores "
    "HTTPS_PROXY and similar variables); download the file and pass its local path"
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
#: ``(host, port) -> addresses`` (strings), the result of one lookup.
Resolver = Callable[[str, int], Sequence[str]]
#: An address -> ``None`` when allowed, else the reason it is refused.
AddressPolicy = Callable[[IPAddress], str | None]


class Cancellable(Protocol):
    """What the fetch needs of a cancel token (``funnel.CancelToken``)."""

    @property
    def cancelled(self) -> bool: ...


class Sink(Protocol):
    """Where a fetch writes the body (a binary file, or a wrapper of one)."""

    def write(self, data: bytes, /) -> int: ...


class FetchError(Exception):
    """A URL cannot be fetched; the message is meant for the agent."""


class FetchCancelled(FetchError):
    """The call was cancelled while fetching."""


class FetchTimeout(FetchError):
    """The fetch timeout or the call's time limit was reached."""


# --------------------------------------------------------------------------
# URLs
# --------------------------------------------------------------------------


def is_url(raw: str) -> bool:
    """True when ``raw`` starts with a scheme followed by ``://``.

    Windows paths (``C:\\x``) and relative paths never match.
    """
    return bool(_SCHEME.match(raw.strip()))


@dataclass(frozen=True)
class ParsedUrl:
    """An accepted ``https`` URL."""

    #: Lower-case IDNA (ASCII) host name or IP literal (IPv6 without brackets).
    host: str
    port: int
    #: Path and query as sent in the request line (``/`` when empty).
    target: str
    #: The normalised URL (design §6): the cache key and what results show.
    url: str

    @property
    def netloc(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return host if self.port == 443 else f"{host}:{self.port}"


def _strip_userinfo(raw: str) -> str:
    """``raw`` without anything between ``://`` and the last ``@`` of the
    authority (for messages; never repeats a password)."""
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*://)([^/?#]*)(.*)$", raw, re.S)
    if not m:
        return raw
    return m.group(1) + m.group(2).rpartition("@")[2] + m.group(3)


#: Printable ASCII except space: kept as is; everything else is percent-encoded.
_SAFE = "".join(chr(c) for c in range(0x21, 0x7F))


def parse_url(raw: str) -> ParsedUrl:
    """Parse and check a URL argument; raise :class:`FetchError` if it is not
    a plain ``https`` URL with a host.

    Normalisation: scheme and host lower case, host IDNA-encoded, default
    port removed, fragment dropped, empty path ``/``; path and query are
    kept byte for byte (non-ASCII and space percent-encoded), so a different
    parameter order is a different URL.
    """
    text = raw.strip()
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in text):
        raise FetchError("the URL contains control characters")
    try:
        parts = urlsplit(text)
    except ValueError as exc:
        raise FetchError(f"{_strip_userinfo(text)} is not a valid URL: {exc}") from None
    scheme = parts.scheme.lower()
    if scheme != "https":
        shown = _strip_userinfo(text)
        if scheme == "http":
            raise FetchError(
                f"{shown}: only https URLs are fetched, not http. Use the https form of the "
                "URL if the server offers it, or download the file and pass its local path"
            )
        raise FetchError(
            f"{shown}: only https URLs are fetched (scheme {scheme!r} is not supported); "
            "pass a local path instead"
        )
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise FetchError(
            f"{_strip_userinfo(text)}: URLs with credentials (user name or password) are "
            "not accepted; only public files that need no login are fetched"
        )
    try:
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise FetchError(f"{text}: invalid host or port: {exc}") from None
    if not hostname:
        raise FetchError(f"{text}: the URL has no host")
    host = normalise_host(hostname)
    if port is None:
        port = 443
    if not 0 < port < 65536:
        raise FetchError(f"{text}: invalid port {port}")
    path = quote(parts.path, safe=_SAFE) or "/"
    target = path + ("?" + quote(parts.query, safe=_SAFE) if parts.query else "")
    netloc = f"[{host}]" if ":" in host else host
    if port != 443:
        netloc += f":{port}"
    return ParsedUrl(host=host, port=port, target=target, url=f"https://{netloc}{target}")


def normalise_host(host: str) -> str:
    """Lower-case IDNA (ASCII) form of a host name; IP literals unchanged
    (IPv6 compressed). Raises :class:`FetchError` for invalid names."""
    h = host.strip().rstrip(".").lower()
    try:
        return str(ipaddress.ip_address(h.split("%", 1)[0] if ":" in h else h))
    except ValueError:
        pass
    if not h:
        raise FetchError("the URL has no host")
    try:
        ascii_host = h.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise FetchError(f"invalid host name {host!r}: {exc}") from None
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*", ascii_host):
        raise FetchError(f"invalid host name {host!r}")
    return ascii_host


# --------------------------------------------------------------------------
# Address check (design §3)
# --------------------------------------------------------------------------

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
_TEREDO = ipaddress.ip_network("2001::/32")
_SIX_TO_FOUR = ipaddress.ip_network("2002::/16")
#: Deprecated IPv4-compatible (``::a.b.c.d``) and IPv4-translated forms.
_V4_COMPATIBLE = ipaddress.ip_network("::/96")
_V4_TRANSLATED = ipaddress.ip_network("::ffff:0:0:0/96")
#: Never public, refused whatever ``is_global`` says (its table follows the
#: IANA special-purpose registries, which do not list every range below,
#: e.g. the deprecated site-local ``fec0::/10`` or SRv6 ``5f00::/16``).
_DENY: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24",
        "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
        "224.0.0.0/4", "240.0.0.0/4",
        "::/128", "::1/128", "100::/64", "2001:db8::/32", "3fff::/20", "5f00::/16",
        "fc00::/7", "fe80::/10", "fec0::/10", "ff00::/8",
    )
)


def public_address_refusal(ip: IPAddress) -> str | None:
    """``None`` when ``ip`` is a public unicast address, else why not.

    IPv6 forms embedding an IPv4 address (IPv4-mapped, NAT64 ``64:ff9b::/96``,
    6to4) are judged by that IPv4 address; Teredo and the local-use NAT64
    prefix ``64:ff9b:1::/48`` (whose embedding depends on the local prefix
    length) and the deprecated IPv4-compatible ``::/96`` and IPv4-translated
    ``::ffff:0:0:0/96`` forms are refused outright. Otherwise the address must be
    ``is_global`` and not multicast, which excludes loopback, RFC 1918,
    link-local (including ``169.254.169.254``), unique-local, CGNAT,
    unspecified, reserved, benchmarking and documentation ranges; the
    explicit list :data:`_DENY` is checked as well (site-local
    ``fec0::/10``, SRv6 ``5f00::/16`` and the ranges above), so the policy
    does not depend on the Python version's ``is_global`` table alone.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        if ip in _TEREDO:
            return "Teredo address"
        if ip in _NAT64_LOCAL:
            return "local-use NAT64 address"
        if ip in _V4_COMPATIBLE or ip in _V4_TRANSLATED:
            return "non-public address"
        embedded: ipaddress.IPv4Address | None = None
        if ip.ipv4_mapped is not None:
            embedded = ip.ipv4_mapped
        elif ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        elif ip in _SIX_TO_FOUR:
            embedded = ip.sixtofour
        if embedded is not None:
            return public_address_refusal(embedded)
        if ip.scope_id:
            return "scoped address"
    if ip.is_multicast:
        return "multicast address"
    if any(ip in net for net in _DENY if net.version == ip.version):
        return "non-public address"
    if not ip.is_global:
        return "non-public address"
    return None


def system_resolver(host: str, port: int) -> list[str]:
    """All addresses of ``host`` from the system resolver (one lookup)."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    out: list[str] = []
    for _family, _type, _proto, _canon, sockaddr in infos:
        addr = str(sockaddr[0]).split("%", 1)[0]
        if addr not in out:
            out.append(addr)
    return out


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FetchConfig:
    """Network settings fixed at server start-up (design §1)."""

    allow_network: bool = False
    #: Allowed host names (normalised); empty: any public host.
    allow_hosts: tuple[str, ...] = ()
    max_download_mb: float = DEFAULT_MAX_DOWNLOAD_MB
    fetch_timeout: float = DEFAULT_FETCH_TIMEOUT

    @property
    def max_bytes(self) -> int:
        return int(self.max_download_mb * 1_000_000)

    def cap_text(self) -> str:
        return f"{self.max_download_mb:g} MB"


@dataclass(frozen=True)
class FetchResult:
    """What a completed fetch delivered into the caller's file."""

    final_url: str
    content_type: str | None
    size: int
    sha256: str


# --------------------------------------------------------------------------
# Watchdog: cancellation and deadline stop a blocked socket operation
# --------------------------------------------------------------------------


class _Watchdog:
    """Shuts the current socket down when the call is cancelled or the
    deadline passes, so a blocked connect, handshake or read returns."""

    def __init__(self, deadline: float, cancel: Cancellable | None) -> None:
        self.deadline = deadline
        self.cancel = cancel
        self.reason: str | None = None  # "cancelled" or "deadline"
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, name="url-fetch-watchdog", daemon=True)

    def __enter__(self) -> _Watchdog:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._done.set()
        self._thread.join()

    def _tripped(self) -> str | None:
        if self.cancel is not None and self.cancel.cancelled:
            return "cancelled"
        if time.monotonic() >= self.deadline:
            return "deadline"
        return None

    def _run(self) -> None:
        while not self._done.wait(WATCH_INTERVAL):
            reason = self._tripped()
            if reason is not None:
                with self._lock:
                    self.reason = reason
                    if self._sock is not None:
                        _shutdown(self._sock)
                return

    def attach(self, sock: socket.socket | None) -> None:
        with self._lock:
            self._sock = sock
            if sock is not None and self.reason is not None:
                _shutdown(sock)

    def check(self) -> None:
        """Record and act on a trip now (between steps)."""
        reason = self.reason or self._tripped()
        if reason is not None:
            with self._lock:
                self.reason = reason
                if self._sock is not None:
                    _shutdown(self._sock)
            raise _Stopped()

    def remaining(self) -> float:
        return self.deadline - time.monotonic()


class _Stopped(Exception):
    """Internal: the watchdog tripped; turned into the right message."""


def _shutdown(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Connection to a checked address
# --------------------------------------------------------------------------


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection over an already connected socket.

    ``self.host`` stays the URL's host name, so SNI, the ``Host`` header and
    the certificate's host-name check use it, while the TCP connection was
    made to a checked address (no second lookup).
    """

    def __init__(
        self, host: str, port: int, sock: socket.socket, context: ssl.SSLContext,
        timeout: float,
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._raw = sock
        self._ctx = context

    def connect(self) -> None:
        # Always the URL's host: for an IP literal, ``ssl`` sends no SNI and
        # checks the certificate's IP address entries (a ``None`` name would
        # make a context with ``check_hostname`` raise ``ValueError``).
        self.sock = self._ctx.wrap_socket(self._raw, server_hostname=self.host)


def default_ssl_context() -> ssl.SSLContext:
    """TLS client context on the OS trust store (``truststore``), falling
    back to Python's default context; host names and certificates are
    always verified."""
    ctx: ssl.SSLContext
    try:
        import truststore

        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # pragma: no cover - platforms without truststore
        ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


# --------------------------------------------------------------------------
# Fetcher
# --------------------------------------------------------------------------


def _media_type(value: str | None) -> tuple[str | None, dict[str, str]]:
    if value is None or not value.strip():
        return None, {}
    head, *params = value.split(";")
    out: dict[str, str] = {}
    for p in params:
        k, _, v = p.partition("=")
        out[k.strip().lower()] = v.strip().strip('"').lower()
    return head.strip().lower(), out


class Fetcher:
    """Fetches one URL into a file with every check of the design.

    ``resolver``, ``address_policy`` and ``ssl_context`` are injectable for
    tests (a local test server needs ``127.0.0.1`` and a private CA);
    production uses :func:`system_resolver`, :func:`public_address_refusal`
    and :func:`default_ssl_context`. There is no option that disables the
    address check from the command line.
    """

    def __init__(
        self,
        config: FetchConfig,
        *,
        resolver: Resolver = system_resolver,
        address_policy: AddressPolicy = public_address_refusal,
        ssl_context: ssl.SSLContext | None = None,
        connect_timeout: float = CONNECT_TIMEOUT,
    ) -> None:
        self.config = config
        self.resolver = resolver
        self.address_policy = address_policy
        self._ssl_context = ssl_context
        self.connect_timeout = connect_timeout

    @property
    def ssl_context(self) -> ssl.SSLContext:
        if self._ssl_context is None:
            self._ssl_context = default_ssl_context()
        return self._ssl_context

    # -- checks before connecting -------------------------------------------

    def check_host_allowed(self, url: ParsedUrl, redirected_from: str | None = None) -> None:
        hosts = self.config.allow_hosts
        if not hosts or url.host in hosts:
            return
        listed = ", ".join(hosts)
        where = f"redirect from {redirected_from} to {url.host}" if redirected_from else url.host
        raise FetchError(
            f"{where}: host {url.host} is not in the allowed hosts ({listed}); to allow it, "
            f"start the server with {ALLOW_HOST_OPTION} {url.host} as well"
        )

    def _resolve(self, url: ParsedUrl, wd: _Watchdog | None) -> list[str]:
        """One lookup through :attr:`resolver`, bounded by the watchdog.

        ``getaddrinfo`` cannot be interrupted, so it runs in a helper thread
        and the fetch stops waiting at the deadline or on cancellation
        (:meth:`_Watchdog.check` raises); a result that arrives later is
        dropped with the thread's local box, never used."""
        if wd is None:
            return list(self.resolver(url.host, url.port))
        box: dict[str, object] = {}
        done = threading.Event()

        def run() -> None:
            try:
                box["value"] = list(self.resolver(url.host, url.port))
            except BaseException as exc:  # handed to the caller below
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=run, name="url-fetch-resolve", daemon=True).start()
        while not done.wait(WATCH_INTERVAL):
            wd.check()
        error = box.get("error")
        if isinstance(error, BaseException):
            raise error
        value = box["value"]
        assert isinstance(value, list)
        return [str(a) for a in value]

    def checked_addresses(self, url: ParsedUrl, wd: _Watchdog | None = None) -> list[IPAddress]:
        """Resolve once (bounded by ``wd``, see :meth:`_resolve`) and check
        every address; all must pass."""
        try:
            literal: IPAddress | None = ipaddress.ip_address(url.host)
        except ValueError:
            literal = None
        if literal is not None:
            reason = self.address_policy(literal)
            if reason is not None:
                raise FetchError(
                    f"{url.host} is a {reason}; only public internet addresses are fetched"
                )
            return [literal]
        try:
            raw = self._resolve(url, wd)
        except (OSError, UnicodeError) as exc:
            raise FetchError(
                f"cannot resolve host {url.host}: {exc}. If this machine reaches the internet "
                f"only through a proxy: {_PROXY_HINT}"
            ) from None
        if not raw:
            raise FetchError(f"cannot resolve host {url.host}: no addresses")
        addresses: list[IPAddress] = []
        for a in raw:
            try:
                ip = ipaddress.ip_address(a.split("%", 1)[0])
            except ValueError:
                raise FetchError(f"cannot resolve host {url.host}: invalid address") from None
            if self.address_policy(ip) is not None:
                # Do not list the internal address itself.
                raise FetchError(
                    f"host {url.host} resolves to a non-public address; only hosts whose "
                    "every address is a public internet address are fetched"
                )
            if ip not in addresses:
                addresses.append(ip)
        return addresses

    # -- the fetch -------------------------------------------------------------

    def fetch(
        self,
        url: ParsedUrl,
        dest: Sink,
        *,
        cancel: Cancellable | None = None,
        call_deadline: float | None = None,
        call_limit_text: str | None = None,
    ) -> FetchResult:
        """Fetch ``url`` into ``dest``; raise :class:`FetchError` otherwise.

        The fetch stops at ``min(now + fetch_timeout, call_deadline)``
        (``call_deadline`` a ``time.monotonic()`` value; ``call_limit_text``
        names that limit in messages) or when ``cancel`` is cancelled.
        """
        start = time.monotonic()
        own = start + self.config.fetch_timeout
        deadline = own if call_deadline is None else min(own, call_deadline)
        call_first = call_deadline is not None and call_deadline < own

        def stopped(wd: _Watchdog, host: str) -> FetchError:
            if wd.reason == "cancelled":
                return FetchCancelled(f"the call was cancelled while fetching from {host}")
            if call_first:
                return FetchTimeout(
                    f"the call's time limit of {call_limit_text or 'the call'} was reached "
                    f"while fetching from {host}; pass a larger time_limit"
                )
            return FetchTimeout(
                f"the fetch timeout of {self.config.fetch_timeout:g} s was reached while "
                f"fetching from {host} (raise it with {FETCH_TIMEOUT_OPTION} when starting "
                "the server, or download the file and pass its local path)"
            )

        with _Watchdog(deadline, cancel) as wd:
            current = url
            previous: str | None = None
            for hop in range(MAX_REDIRECTS + 1):
                try:
                    wd.check()
                    location = self._hop(current, previous, dest, wd)
                except _Stopped:
                    raise stopped(wd, current.host) from None
                except FetchError:
                    if wd.reason is not None:
                        raise stopped(wd, current.host) from None
                    raise
                if isinstance(location, FetchResult):
                    return location
                try:
                    nxt = parse_url(urljoin(current.url, location))
                except FetchError as exc:
                    target = _strip_userinfo(urljoin(current.url, location))
                    if urlsplit(target).scheme.lower() == "http":
                        raise FetchError(
                            f"{current.host} redirects to {target}, which leaves https; only "
                            "https URLs are fetched"
                        ) from None
                    raise FetchError(f"{current.host} redirects to {target}: {exc}") from None
                if hop == MAX_REDIRECTS:
                    break
                previous, current = current.host, nxt
            raise FetchError(
                f"{url.host}: more than {MAX_REDIRECTS} redirects (last to {current.host})"
            )

    def _connect(self, url: ParsedUrl, addresses: list[IPAddress], wd: _Watchdog) -> socket.socket:
        errors: list[str] = []
        for ip in addresses:
            family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM)
            wd.attach(sock)
            try:
                _connect_nonblocking(sock, (str(ip), url.port), self.connect_timeout, wd)
                return sock
            except _Stopped:
                sock.close()
                raise
            except OSError as exc:
                sock.close()
                errors.append(exc.strerror or str(exc) or type(exc).__name__)
        wd.attach(None)
        detail = "; ".join(dict.fromkeys(errors))
        raise FetchError(f"cannot connect to {url.host} port {url.port} ({detail}); {_PROXY_HINT}")

    def _hop(
        self, url: ParsedUrl, previous: str | None, dest: Sink, wd: _Watchdog
    ) -> FetchResult | str:
        """One request. Returns the result, or a redirect ``Location``."""
        self.check_host_allowed(url, previous)
        try:
            addresses = self.checked_addresses(url, wd)
        except FetchError as exc:
            if previous is not None:
                raise FetchError(f"redirect from {previous} to {url.host}: {exc}") from None
            raise
        sock = self._connect(url, addresses, wd)
        sock.settimeout(max(0.01, wd.remaining()))
        conn = _PinnedHTTPSConnection(
            url.host, url.port, sock, self.ssl_context, timeout=max(0.01, wd.remaining())
        )
        try:
            try:
                conn.connect()
            except ssl.SSLCertVerificationError as exc:
                raise FetchError(
                    f"certificate verification failed for {url.host}: "
                    f"{exc.verify_message or exc.reason or exc}"
                ) from None
            except (ssl.SSLError, OSError) as exc:
                wd.check()
                raise FetchError(f"TLS connection to {url.host} failed: {exc}") from None
            except Exception as exc:  # any other failure of the TLS layer
                # E.g. ValueError from a TLS backend: a fetch error naming the
                # host, never a traceback.
                wd.check()
                raise FetchError(
                    f"TLS connection to {url.host} failed ({type(exc).__name__}: {exc})"
                ) from None
            wd.attach(conn.sock)
            try:
                self._request(conn, url)
                response = conn.getresponse()
            except (http.client.HTTPException, OSError, ValueError) as exc:
                wd.check()
                raise FetchError(f"request to {url.host} failed: {exc}") from None
            if response.status in _REDIRECTS:
                location = response.getheader("Location")
                if not location:
                    raise FetchError(
                        f"{url.host} answered {response.status} without a Location header"
                    )
                return location
            if response.status != 200:
                raise FetchError(self._status_message(url, response, wd))
            return self._body(url, response, dest, wd)
        finally:
            wd.attach(None)
            conn.close()
            sock.close()

    def _request(self, conn: http.client.HTTPConnection, url: ParsedUrl) -> None:
        conn.putrequest("GET", url.target, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", url.netloc)
        conn.putheader("User-Agent", USER_AGENT)
        conn.putheader("Accept", ACCEPT)
        conn.putheader("Accept-Encoding", "gzip")
        conn.putheader("Connection", "close")
        conn.endheaders()

    def _status_message(
        self, url: ParsedUrl, response: http.client.HTTPResponse, wd: _Watchdog
    ) -> str:
        """Status, standard reason phrase and content type of an error
        response. The body is remote, untrusted text and is not quoted; only
        the ``reason`` (or ``error`` / ``message``) string of a JSON object
        body is shown, without the characters :data:`_REASON_DROP` removes and at most
        :data:`ERROR_REASON_CHARS` characters (see :func:`_json_reason`)."""
        try:
            phrase = http.HTTPStatus(response.status).phrase
        except ValueError:
            phrase = ""
        text = f"{url.host} answered {response.status} {phrase}".rstrip()
        header = response.getheader("Content-Type")
        mtype, _params = _media_type(header)
        encoding = (response.getheader("Content-Encoding") or "identity").strip().lower()
        if mtype is None:
            return text
        shown_type = mtype if _MEDIA_TYPE.fullmatch(mtype) else "an unusual type"
        text += f" with a {shown_type} body (not shown: content from a URL is not repeated)"
        if mtype != "application/json" or encoding not in ("identity", "gzip"):
            return text
        try:
            raw = response.read(ERROR_BODY_BYTES)
            if encoding == "gzip":
                raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, ERROR_BODY_BYTES)
        except (OSError, zlib.error, http.client.HTTPException):
            wd.check()
            return text
        reason = _json_reason(raw)
        if reason is None:
            return text
        return f"{text}; the server's JSON reason, sanitised: {reason}"

    def _check_content(
        self, url: ParsedUrl, response: http.client.HTTPResponse
    ) -> tuple[str | None, bool]:
        """Check type, charset, encoding and announced length; return the
        content type header and whether the body is gzip-compressed."""
        header = response.getheader("Content-Type")
        mtype, params = _media_type(header)
        if mtype in _HTML_TYPES:
            raise FetchError(_html_message(url))
        if mtype == "application/json" or (mtype is not None and mtype.endswith("/xml")) or (
            mtype is not None and mtype.endswith("+xml")
        ) or (mtype is not None and mtype.endswith("+json")):
            raise FetchError(
                f"{url.host} returned {mtype}, not CSV; only CSV is read. If the service "
                "offers CSV, ask for it (e.g. format=csv)"
            )
        if mtype is not None and mtype not in ACCEPTED_TYPES:
            raise FetchError(
                f"{url.host} returned content type {mtype}; only CSV or plain text is read"
            )
        charset = params.get("charset")
        if charset is not None and charset not in _CHARSETS:
            raise FetchError(
                f"{url.host} returned text in charset {charset}; only UTF-8 (or ASCII) is "
                "read: ask the source for UTF-8, or download the file, convert it to UTF-8 "
                "and pass its local path"
            )
        encoding = (response.getheader("Content-Encoding") or "identity").strip().lower()
        if encoding not in ("identity", "gzip"):
            raise FetchError(
                f"{url.host} returned Content-Encoding {encoding}; only uncompressed or gzip "
                "responses are read"
            )
        length = response.getheader("Content-Length")
        if length is not None and length.strip().isdigit():
            if int(length) > self.config.max_bytes:
                raise FetchError(self._cap_message(url, announced=int(length)))
        return header, encoding == "gzip"

    def _cap_message(self, url: ParsedUrl, announced: int | None = None) -> str:
        what = (
            f"announces {announced} bytes" if announced is not None
            else "sent more data than allowed (counted after decompression)"
        )
        return (
            f"{url.host} {what}, over the size cap of {self.config.cap_text()}; raise it with "
            f"{MAX_DOWNLOAD_OPTION} when starting the server, or download the file and pass "
            "its local path"
        )

    def _body(
        self, url: ParsedUrl, response: http.client.HTTPResponse, dest: Sink, wd: _Watchdog
    ) -> FetchResult:
        content_type, gzipped = self._check_content(url, response)
        cap = self.config.max_bytes
        digest = hashlib.sha256()
        size = 0
        sniff = b""
        sniffed = False
        inflater = zlib.decompressobj(16 + zlib.MAX_WBITS) if gzipped else None
        #: Whether the current gzip member has received data (truncation check).
        fed = False
        #: Complete gzip members so far, and whether NUL padding has started.
        members = 0
        padded = False

        def emit(data: bytes) -> None:
            nonlocal size, sniff, sniffed
            if not data:
                return
            size += len(data)
            if size > cap:
                raise FetchError(self._cap_message(url))
            if not sniffed:
                sniff = (sniff + data)[:512]
                head = sniff.lstrip()
                if len(head) >= 14 or len(sniff) >= 512:
                    sniffed = True
                    _check_not_html(url, head)
            digest.update(data)
            dest.write(data)

        while True:
            wd.check()
            try:
                block = response.read1(READ_BLOCK)
            except (http.client.HTTPException, OSError, ValueError) as exc:
                wd.check()
                raise FetchError(
                    f"the connection to {url.host} broke before the whole file was received "
                    f"({type(exc).__name__}: {exc})"
                ) from None
            if not block:
                break
            if inflater is None:
                emit(block)
                continue
            data = block
            while True:
                if padded or (members and not fed and data[:1] == b"\0"):
                    # NUL padding after a complete member, as gzip(1) and
                    # Python's gzip module accept it (RFC 1952 has no
                    # padding; anything else after a member must be another
                    # member).
                    padded = True
                    if data.strip(b"\0"):
                        raise FetchError(f"{url.host} sent data after NUL padding of gzip data")
                    break
                fed = True
                # Each step expands at most READ_BLOCK bytes (and never past the cap).
                limit = max(1, min(READ_BLOCK, cap - size + 1))
                try:
                    out = inflater.decompress(data, limit)
                except zlib.error as exc:
                    raise FetchError(f"{url.host} sent invalid gzip data: {exc}") from None
                emit(out)
                if inflater.eof:
                    data = inflater.unused_data
                    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    fed = False
                    members += 1
                    if not data:
                        break
                    continue
                data = inflater.unconsumed_tail
                if not data and len(out) < limit:
                    break  # input used up and no output pending
        if response.length:
            raise FetchError(
                f"the connection to {url.host} broke before the whole file was received "
                f"({response.length} announced bytes missing)"
            )
        if inflater is not None:
            if fed and not inflater.eof:
                raise FetchError(f"{url.host} sent truncated gzip data")
        if not sniffed:
            _check_not_html(url, sniff.lstrip())
        wd.check()
        return FetchResult(
            final_url=url.url, content_type=content_type, size=size, sha256=digest.hexdigest()
        )


#: A media type as shown in messages (anything else is not repeated).
_MEDIA_TYPE = re.compile(r"[a-z0-9][a-z0-9.+-]{0,40}/[a-z0-9][a-z0-9.+-]{0,40}")
#: Characters kept in a JSON error reason: letters, digits, space and plain
#: punctuation, no quotes, brackets, braces, angle brackets, backticks or
#: line breaks, so the text cannot pose as markup or as a message from the
#: server or the user.
_REASON_DROP = re.compile(r"[^A-Za-z0-9 .,:;=+\-_/()%]")


def _json_reason(raw: bytes) -> str | None:
    """The ``reason``, ``error`` or ``message`` string of a JSON object
    (first found), sanitised: other characters removed, whitespace
    collapsed, at most :data:`ERROR_REASON_CHARS` characters; ``None`` when
    there is none. Open-Meteo, for example, answers a bad request with
    ``{"error": true, "reason": "..."}``; the reason tells the agent what to
    change, which justifies showing this much of a remote body."""

    try:
        doc = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(doc, dict):
        return None
    for key in ("reason", "error", "message"):
        value = doc.get(key)
        if isinstance(value, str):
            text = " ".join(_REASON_DROP.sub(" ", value).split())
            if not text:
                return None
            if len(text) > ERROR_REASON_CHARS:
                text = text[: ERROR_REASON_CHARS - 3] + "..."
            return text
    return None


def _html_message(url: ParsedUrl) -> str:
    return (
        f"{url.host} returned an HTML page, probably a web view of the file rather than the "
        "file itself; use the raw-file URL (e.g. the 'Raw' link of a code-hosting page)"
    )


def _check_not_html(url: ParsedUrl, head: bytes) -> None:
    low = head[:14].lower()
    if low.startswith(b"<!doctype html") or low.startswith(b"<html"):
        raise FetchError(_html_message(url))


#: ``errno`` values of a non-blocking connect that is in progress.
_IN_PROGRESS = frozenset(
    e for e in (errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EAGAIN, 10035) if e is not None
)


def _connect_nonblocking(
    sock: socket.socket, address: tuple[str, int], timeout: float, wd: _Watchdog
) -> None:
    """Connect ``sock`` within ``timeout`` (and the watchdog's deadline),
    checking cancellation every few milliseconds."""
    sock.setblocking(False)
    err = sock.connect_ex(address)
    if err != 0 and err not in _IN_PROGRESS:
        raise OSError(err, _strerror(err))
    if err != 0:
        limit = time.monotonic() + timeout
        while True:
            wd.check()
            left = min(limit - time.monotonic(), wd.remaining())
            if left <= 0:
                wd.check()
                raise OSError(errno.ETIMEDOUT, f"connection timed out after {timeout:g} s")
            _, writable, failed = select.select([], [sock], [sock], min(left, WATCH_INTERVAL))
            if writable or failed:
                code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if code:
                    raise OSError(code, _strerror(code))
                break
    sock.setblocking(True)


def _strerror(code: int) -> str:
    import os

    try:
        return os.strerror(code)
    except ValueError:
        return f"error {code}"
