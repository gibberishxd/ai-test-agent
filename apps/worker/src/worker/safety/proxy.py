"""An egress proxy that enforces the SSRF guard on every browser request.

Why a proxy: Playwright's request interception (`context.route`) only sees the first request
of a redirect chain; the browser follows redirects on its own. Through a proxy, every hop is a
separate request we can check. The proxy also connects to the exact IP address it checked, which
stops DNS rebinding (a name that resolves to a public IP for the check and a private one later).

- HTTPS: the browser sends `CONNECT host:443`; we check host:port, open a TCP connection to the
  checked IP and pass bytes through untouched (TLS stays end-to-end between browser and site).
- HTTP: the browser sends `GET http://host/path`; we check, then forward the request to the
  checked IP and relay the response.

Blocked requests get a 403 and are recorded in `guard.blocked`.
"""

import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from worker.safety.network import BlockedError, BlockedRequest, NetworkGuard

HOP_BY_HOP = {"proxy-connection", "proxy-authorization", "connection", "keep-alive"}
CONNECT_TIMEOUT_S = 10
IDLE_TIMEOUT_S = 60


class GuardProxy:
    """Use as `with GuardProxy(guard) as proxy:`; give the browser `proxy.playwright_config`."""

    def __init__(self, guard: NetworkGuard):
        self.guard = guard
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format, *args):
                pass

            def do_CONNECT(self):
                host, _, port = self.path.rpartition(":")
                owner._tunnel(self, host, int(port))

            def _forward(self):
                owner._forward(self)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _forward

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    @property
    def playwright_config(self) -> dict[str, str]:
        # Chromium skips the proxy for localhost unless told otherwise ("<-loopback>"), which
        # would let a page reach our own services on 127.0.0.1 unchecked.
        return {"server": self.url, "bypass": "<-loopback>"}

    def __enter__(self) -> "GuardProxy":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _vet(self, handler: BaseHTTPRequestHandler, url: str, host: str, port: int) -> str | None:
        try:
            return self.guard.vet(host, port)
        except BlockedError as error:
            self.guard.blocked.append(BlockedRequest(url=url, reason=str(error)))
            handler.send_error(403, "Blocked by the AI Test Agent network guard")
            return None

    def _tunnel(self, handler: BaseHTTPRequestHandler, host: str, port: int) -> None:
        address = self._vet(handler, f"https://{host}:{port}/", host, port)
        if address is None:
            return
        try:
            upstream = socket.create_connection((address, port), timeout=CONNECT_TIMEOUT_S)
        except OSError:
            handler.send_error(502, "Could not connect")
            return
        handler.send_response(200, "Connection Established")
        handler.end_headers()
        with upstream:
            _pipe(handler.connection, upstream)
        handler.close_connection = True

    def _forward(self, handler: BaseHTTPRequestHandler) -> None:
        parts = urlsplit(handler.path)
        if parts.scheme != "http" or not parts.hostname:
            handler.send_error(400, "Expected an absolute http:// URL")
            return
        port = parts.port or 80
        address = self._vet(handler, handler.path, parts.hostname, port)
        if address is None:
            return
        body = handler.rfile.read(int(handler.headers.get("Content-Length") or 0))
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        lines = [f"{handler.command} {target} HTTP/1.1"]
        lines += [f"{k}: {v}" for k, v in handler.headers.items() if k.lower() not in HOP_BY_HOP]
        lines.append("Connection: close")  # one request per upstream connection: simple framing
        request = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body
        try:
            upstream = socket.create_connection((address, port), timeout=CONNECT_TIMEOUT_S)
        except OSError:
            handler.send_error(502, "Could not connect")
            return
        with upstream:
            upstream.sendall(request)
            while chunk := upstream.recv(65536):
                handler.wfile.write(chunk)
        handler.close_connection = True


def _pipe(a: socket.socket, b: socket.socket) -> None:
    """Copy bytes both ways until either side closes or goes idle."""
    sockets = [a, b]
    while True:
        readable, _, broken = select.select(sockets, [], sockets, IDLE_TIMEOUT_S)
        if broken or not readable:
            return
        for sock in readable:
            data = sock.recv(65536)
            if not data:
                return
            (b if sock is a else a).sendall(data)
