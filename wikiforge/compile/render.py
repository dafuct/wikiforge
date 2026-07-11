"""Render a CompiledArticle into Obsidian-compatible Markdown."""

from __future__ import annotations

from wikiforge.models.schemas import CompiledArticle


def render_article_markdown(
    article: CompiledArticle,
    *,
    slug: str,
    confidence: float,
    see_also: list[tuple[str, str]],
) -> str:
    """Render an article to Markdown with citations, contested, see-also, open-questions.

    ``see_also`` is a list of ``(slug, title)`` pairs from the knowledge graph; each is
    rendered as BOTH an Obsidian wikilink (``[[slug|Title]]``) and a relative Markdown
    link, so the vault works in Obsidian and in a plain file browser.
    """
    lines: list[str] = [
        f"# {article.title}",
        "",
        f"*Confidence: {confidence:.2f}*",
        "",
        article.body,
        "",
    ]

    if article.citations:
        lines += ["## Citations", ""]
        for i, cit in enumerate(article.citations, start=1):
            quote = f' — "{cit.quote}"' if cit.quote else ""
            lines.append(f"{i}. **{cit.claim}** [{cit.source_id}]{quote}")
        lines.append("")

    if article.conflicts:
        lines += ["## Contested", ""]
        for conflict in article.conflicts:
            srcs = ", ".join(conflict.source_ids)
            lines.append(f"- **{conflict.claim}** — {conflict.nature} (sources: {srcs})")
        lines.append("")

    if see_also:
        lines += ["## See also", ""]
        for other_slug, title in see_also:
            lines.append(
                f"- [[{other_slug}|{title}]] · [{title}](../{other_slug}/wiki/{other_slug}.md)"
            )
        lines.append("")

    if article.open_questions:
        lines += ["## Open questions", ""]
        lines += [f"- {q}" for q in article.open_questions]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
