"""URL canonicalization and content hashing for dedup-stable ingestion."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_EXACT = frozenset({"fbclid", "gclid", "ref", "mc_eid"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _is_tracking(key: str) -> bool:
    return key in _TRACKING_EXACT or any(key.startswith(p) for p in _TRACKING_PREFIXES)


def canonicalize_url(url: str) -> str:
    """Return a canonical form of ``url`` stable across tracking-param variants.

    Lowercases scheme and host, drops the default port, removes tracking
    parameters and the fragment, sorts the remaining query parameters, and
    strips trailing slashes from the path (a root path becomes empty).
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    netloc = host
    if parts.port is not None and parts.port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"

    path = parts.path.rstrip("/")

    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking(k)
    ]
    query = urlencode(sorted(kept))

    return urlunsplit((scheme, netloc, path, query, ""))


def content_hash(text: str) -> str:
    """Return the sha256 hex digest of ``text`` after stripping surrounding whitespace."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
