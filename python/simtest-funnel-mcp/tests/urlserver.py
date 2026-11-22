"""A local HTTPS test server for the URL-fetch tests (offline).

A throw-away CA and leaf certificates are generated with ``cryptography``;
the server runs ``http.server.ThreadingHTTPServer`` over TLS on
``127.0.0.1``. Test fetchers resolve the test host names to ``127.0.0.1``
through an injected resolver and allow loopback through an injected address
policy (production code has no such switch).
"""

from __future__ import annotations

import datetime as dt
import gzip
import http.server
import ipaddress
import socket
import ssl
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from simtest_funnel_mcp.fetch import (
    FetchConfig,
    Fetcher,
    IPAddress,
    public_address_refusal,
)

#: Host names the good certificate is valid for (all resolve to 127.0.0.1).
TEST_HOSTS = ("data.test", "other.test", "localhost")
#: The certificate of the "wrong" server names only this host.
WRONG_HOST = "elsewhere.test"


@dataclass(frozen=True)
class Certs:
    ca: Path
    good_cert: Path
    good_key: Path
    wrong_cert: Path
    wrong_key: Path


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def make_certs(directory: Path) -> Certs:
    """A CA and two leaf certificates signed by it (PEM files)."""
    now = dt.datetime.now(dt.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(_name("simtest-funnel test CA"))
        .issuer_name(_name("simtest-funnel test CA"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )

    def leaf(names: list[str], ips: list[str]) -> tuple[bytes, bytes]:
        key = ec.generate_private_key(ec.SECP256R1())
        sans: list[x509.GeneralName] = [x509.DNSName(n) for n in names]
        sans += [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
        cert = (
            x509.CertificateBuilder()
            .subject_name(_name(names[0]))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        pem_key = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        return cert.public_bytes(serialization.Encoding.PEM), pem_key

    files = {}
    good = leaf(list(TEST_HOSTS), ["127.0.0.1"])
    wrong = leaf([WRONG_HOST], [])
    for name, data in {
        "ca.pem": ca_cert.public_bytes(serialization.Encoding.PEM),
        "good.pem": good[0], "good.key": good[1],
        "wrong.pem": wrong[0], "wrong.key": wrong[1],
    }.items():
        p = directory / name
        p.write_bytes(data)
        files[name] = p
    return Certs(
        ca=files["ca.pem"], good_cert=files["good.pem"], good_key=files["good.key"],
        wrong_cert=files["wrong.pem"], wrong_key=files["wrong.key"],
    )


# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------


@dataclass
class Seen:
    """One request as the server saw it."""

    method: str
    path: str
    headers: dict[str, str]


Responder = Callable[["Handler"], None]


@dataclass
class Routes:
    routes: dict[str, Responder] = field(default_factory=dict)
    seen: list[Seen] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def count(self, path: str) -> int:
        with self.lock:
            return sum(1 for s in self.seen if s.path == path)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: _Server

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:  # noqa: N802
        routes = self.server.routes
        with routes.lock:
            routes.seen.append(
                Seen(self.command, self.path, {k.lower(): v for k, v in self.headers.items()})
            )
            responder = routes.routes.get(self.path)
        if responder is None:
            send(self, b"not found", status=404, ctype="text/plain")
            return
        try:
            responder(self)
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
            pass

    def do_POST(self) -> None:  # noqa: N802
        send(self, b"no", status=405, ctype="text/plain")


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    routes: Routes

    def handle_error(self, request: Any, client_address: Any) -> None:
        pass  # failed handshakes and aborted clients are expected in these tests


def send(
    h: Handler,
    body: bytes,
    *,
    status: int = 200,
    ctype: str | None = "text/csv; charset=utf-8",
    headers: dict[str, str] | None = None,
    gzipped: bool = False,
    length: int | None = None,
) -> None:
    """Send a complete response (``gzipped`` compresses ``body`` first)."""
    data = gzip.compress(body) if gzipped else body
    h.send_response(status)
    if ctype is not None:
        h.send_header("Content-Type", ctype)
    if gzipped:
        h.send_header("Content-Encoding", "gzip")
    h.send_header("Content-Length", str(len(data) if length is None else length))
    h.send_header("Connection", "close")
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(data)
    h.wfile.flush()


def body(data: bytes, **kwargs: Any) -> Responder:
    return lambda h: send(h, data, **kwargs)


def redirect(location: str, status: int = 302) -> Responder:
    return lambda h: send(h, b"", status=status, ctype=None, headers={"Location": location})


def slow(data: bytes, interval: float = 1.0, *, stop: threading.Event | None = None) -> Responder:
    """Send ``data`` one byte per ``interval`` seconds."""

    def respond(h: Handler) -> None:
        h.send_response(200)
        h.send_header("Content-Type", "text/csv")
        h.send_header("Content-Length", str(len(data)))
        h.send_header("Connection", "close")
        h.end_headers()
        h.wfile.flush()
        for b in data:
            if stop is not None and stop.is_set():
                return
            h.wfile.write(bytes([b]))
            h.wfile.flush()
            time.sleep(interval)

    return respond


def delayed(delay: float, then: Responder) -> Responder:
    def respond(h: Handler) -> None:
        time.sleep(delay)
        then(h)

    return respond


class TestServer:
    """A running HTTPS server on 127.0.0.1 (``.port``, ``.routes``)."""

    __test__ = False

    def __init__(self, cert: Path, key: Path) -> None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        self.httpd = _Server(("127.0.0.1", 0), Handler)
        self.httpd.routes = Routes()
        self.httpd.socket = ctx.wrap_socket(
            self.httpd.socket, server_side=True, do_handshake_on_connect=False
        )
        self.port = int(self.httpd.server_address[1])
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def routes(self) -> Routes:
        return self.httpd.routes

    def reset(self) -> None:
        with self.routes.lock:
            self.routes.routes.clear()
            self.routes.seen.clear()

    def url(self, path: str, host: str = "data.test") -> str:
        return f"https://{host}:{self.port}{path}"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# --------------------------------------------------------------------------
# Test fetchers
# --------------------------------------------------------------------------


def loopback_allowed(ip: IPAddress) -> str | None:
    """Test address policy: production policy, but 127.0.0.1 allowed."""
    if ip == ipaddress.IPv4Address("127.0.0.1"):
        return None
    return public_address_refusal(ip)


@dataclass
class CountingResolver:
    """Resolves the test host names; counts lookups; ``answers`` overrides."""

    answers: dict[str, list[str]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def __call__(self, host: str, port: int) -> list[str]:
        self.calls.append(host)
        if host in self.answers:
            return self.answers[host]
        if host in TEST_HOSTS or host == WRONG_HOST:
            return ["127.0.0.1"]
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")


def client_context(ca: Path) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=str(ca))
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def test_fetcher(
    certs: Certs,
    config: FetchConfig | None = None,
    resolver: CountingResolver | None = None,
    **kwargs: Any,
) -> Fetcher:
    return Fetcher(
        config if config is not None else FetchConfig(allow_network=True),
        resolver=resolver if resolver is not None else CountingResolver(),
        address_policy=loopback_allowed,
        ssl_context=client_context(certs.ca),
        **kwargs,
    )


test_fetcher.__test__ = False  # type: ignore[attr-defined]


def free_port() -> int:
    """A port on 127.0.0.1 where nothing listens (connection refused)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def iter_zeros(total: int, block: int = 1 << 20) -> Iterator[bytes]:
    while total > 0:
        n = min(block, total)
        yield b"0" * n
        total -= n


def gzip_bomb(expanded: int) -> bytes:
    """A gzip stream of ``expanded`` ASCII zeros (compresses ~1000:1)."""
    comp = __import__("zlib").compressobj(9, 8, 16 + 15)
    parts = [comp.compress(chunk) for chunk in iter_zeros(expanded)]
    parts.append(comp.flush())
    return b"".join(parts)
