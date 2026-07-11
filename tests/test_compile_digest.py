"""Incremental-compile digest: stable inputs -> same digest; any change -> different."""

from __future__ import annotations

from wikiforge.compile.digest import compute_compile_digest


def _digest(**over) -> str:
    base = dict(
        source_hashes=["a", "b"], finding_ids=[1, 2], feedback_ids=[], model="claude-sonnet-5"
    )
    base.update(over)
    return compute_compile_digest(**base)


def test_digest_is_stable_and_order_independent() -> None:
    assert _digest() == _digest()
    assert _digest(source_hashes=["b", "a"]) == _digest(
        source_hashes=["a", "b"]
    )  # order-independent


def test_digest_changes_on_new_source() -> None:
    assert _digest() != _digest(source_hashes=["a", "b", "c"])


def test_digest_changes_on_feedback() -> None:
    assert _digest() != _digest(feedback_ids=[7])


def test_digest_changes_on_model() -> None:
    assert _digest() != _digest(model="claude-haiku-4-5")
