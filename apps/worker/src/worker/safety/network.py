"""Safety rule 6.1: never let the worker's browser reach private or internal addresses (SSRF).

The worker runs inside our infrastructure. Without this guard, a user could submit
http://169.254.169.254/ (the cloud metadata service, which hands out credentials) or an
internal admin page, and our browser would fetch it for them. This is server-side request
forgery (SSRF).

`NetworkGuard` decides: resolve the host, and every resulting IP must be a public (global)
address. `GuardProxy` (proxy.py) enforces it: the browser sends every request through it,
including each redirect hop, and the proxy connects to the exact IP it checked.
"""

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from worker.urls import is_same_site

# Cloud metadata endpoints. Most are already non-global addresses, but list them explicitly.
METADATA_IPS = {"169.254.169.254", "fd00:ec2::254", "100.100.100.200"}
METADATA_HOSTS = {"metadata", "metadata.google.internal"}

# Schemes that never leave the browser, so there's nothing to guard.
LOCAL_SCHEMES = {"data", "blob", "about"}

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

Resolver = Callable[[str], list[str]]


def resolve(host: str) -> list[str]:
    """All IP addresses `host` resolves to (IPv4 and IPv6)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    return sorted({info[4][0] for info in infos})


def is_public_ip(ip: str) -> bool:
    """True only for globally routable addresses that aren't a metadata endpoint."""
    address = ipaddress.ip_address(ip.split("%")[0])  # drop an IPv6 zone like %en0
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped  # ::ffff:10.0.0.1 is really 10.0.0.1
    return address.is_global and str(address) not in METADATA_IPS


class BlockedError(Exception):
    pass


@dataclass
class BlockedRequest:
    url: str
    reason: str


@dataclass
class NetworkGuard:
    """Decides which URLs the browser may load.

    allowed_local: (host, port) pairs exempt from the private-address rule. In dev mode these
    are our own demo shops on localhost; in production the set is empty.
    target_url: if set, main-frame navigations must stay on its origin (rule 6.1, last line).
    """

    allowed_local: set[tuple[str, int]] = field(default_factory=set)
    target_url: str | None = None
    resolver: Resolver = resolve
    blocked: list[BlockedRequest] = field(default_factory=list)
    _cache: dict[str, list[str]] = field(default_factory=dict)

    def check(self, url: str) -> str | None:
        """None if `url` may be loaded, otherwise the reason it's refused."""
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme in LOCAL_SCHEMES:
            return None
        if scheme not in ("http", "https"):
            return f"scheme '{scheme}' is not allowed"
        port = parts.port or (443 if scheme == "https" else 80)
        try:
            self.vet(parts.hostname or "", port)
        except BlockedError as error:
            return str(error)
        return None

    def vet(self, host: str, port: int) -> str:
        """Return the address to connect to for host:port, or raise BlockedError.

        Returning the checked IP (not the name) matters: the proxy connects to exactly this
        address, so DNS can't answer "public" for the check and "private" for the connection.
        """
        host = host.lower().strip("[]")
        if not host:
            raise BlockedError("no host in URL")
        if (host, port) in self.allowed_local:
            return host
        if host in METADATA_HOSTS:
            raise BlockedError(f"{host} is a cloud metadata host")
        if host not in self._cache:
            self._cache[host] = self.resolver(host)
        ips = self._cache[host]
        if not ips:
            raise BlockedError(f"could not resolve {host}")
        for ip in ips:
            if not is_public_ip(ip):
                raise BlockedError(f"{host} resolves to a private or internal address ({ip})")
        return ips[0]

    def check_navigation(self, url: str) -> str | None:
        """Like `check`, plus: top-level page loads must stay on the target's origin."""
        reason = self.check(url)
        if reason is None and self.target_url and not is_same_site(url, self.target_url):
            if urlsplit(url).scheme.lower() not in LOCAL_SCHEMES:
                return "navigation leaves the target's origin"
        return reason


def dev_allowed_local(urls: list[str]) -> set[tuple[str, int]]:
    """(host, port) pairs for our own localhost apps, e.g. the demo shops in dev mode."""
    allowed: set[tuple[str, int]] = set()
    for url in urls:
        parts = urlsplit(url)
        if parts.hostname and parts.port:
            for host in (*LOCAL_HOSTS, parts.hostname.lower()):
                allowed.add((host, parts.port))
    return allowed
