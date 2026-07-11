"""URL canonicalization and content hashing."""

from __future__ import annotations

from wikiforge.ingest.canonical import canonicalize_url, content_hash


def test_strips_tracking_params_and_fragment() -> None:
    url = "https://Example.com/Page/?utm_source=x&b=2&a=1&fbclid=z#frag"
    assert canonicalize_url(url) == "https://example.com/Page?a=1&b=2"


def test_normalizes_host_scheme_and_default_port() -> None:
    assert canonicalize_url("HTTPS://Example.com:443/") == "https://example.com"
    assert canonicalize_url("http://example.com:80/x/") == "http://example.com/x"


def test_two_tracking_variants_canonicalize_equal() -> None:
    a = canonicalize_url("https://site.com/post?utm_campaign=a&id=7")
    b = canonicalize_url("https://site.com/post?id=7&gclid=abc")
    assert a == b == "https://site.com/post?id=7"


def test_content_hash_is_stable_and_strips() -> None:
    assert content_hash("  hello  ") == content_hash("hello")
    assert len(content_hash("x")) == 64
    assert content_hash("a") != content_hash("b")
