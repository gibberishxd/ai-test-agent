"""URL helpers for the crawler.

Two URLs that point to the same page must compare equal, otherwise the crawler would treat
`/cart` and `/cart#top` as different pages and could keep finding "new" ones forever.
"""

from urllib.parse import urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple[str, str, int | None]:
    """(scheme, host, port) with the scheme's default port filled in when it's missing."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    return scheme, (parts.hostname or "").lower(), parts.port or DEFAULT_PORTS.get(scheme)


def normalize(url: str) -> str:
    """A canonical form of `url`, so the same page always gives the same string.

    Drops the #fragment (it never reaches the server), lowercases scheme and host
    (they're case-insensitive), drops a default port, and turns an empty path into "/".
    Path and query are kept as they are: servers may treat them case-sensitively.
    """
    parts = urlsplit(url)
    scheme, host, port = _origin(url)
    netloc = host if port == DEFAULT_PORTS.get(scheme) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def is_same_origin(url: str, start_url: str) -> bool:
    """True if `url` has the same scheme, host and port as `start_url`, and is http(s)."""
    origin = _origin(url)
    return origin[0] in DEFAULT_PORTS and origin == _origin(start_url)
