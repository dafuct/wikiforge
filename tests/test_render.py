"""Article rendering: dual wikilinks, Contested, See also, Open questions, confidence."""

from __future__ import annotations

from wikiforge.compile.render import render_article_markdown
from wikiforge.models.schemas import ClaimCitation, CompiledArticle, ConflictOut, WikiLink


def _article() -> CompiledArticle:
    return CompiledArticle(
        title="Rust Async",
        body="Rust async is cooperative. [1]",
        citations=[ClaimCitation(claim="cooperative scheduling", source_id="s1", quote="...")],
        conflicts=[
            ConflictOut(
                claim="runtime overhead", nature="sources disagree on cost", source_ids=["s1", "s2"]
            )
        ],
        open_questions=["What about io_uring?"],
        wikilinks=[WikiLink(slug="tokio", title="Tokio")],
        source_ids=["s1", "s2"],
        distinct_domains=2,
        distinct_personas=3,
        source_dates=["2026-01-01"],
        evidence_strength=0.8,
    )


def test_render_has_all_sections_and_dual_links() -> None:
    md = render_article_markdown(
        _article(),
        slug="rust-async",
        confidence=0.73,
        see_also=[("tokio", "Tokio"), ("async-std", "Async Std")],
    )
    assert "# Rust Async" in md
    assert "0.73" in md  # confidence in header
    assert "## Contested" in md and "runtime overhead" in md
    assert "## Open questions" in md and "io_uring" in md
    assert "## Citations" in md
    assert "## See also" in md
    assert "[[tokio|Tokio]]" in md  # obsidian dual link
    assert "(../tokio/wiki/tokio.md)" in md  # relative link
