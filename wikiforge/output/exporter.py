"""Export the wiki to an Obsidian vault, a static site, or a JSON dump."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from wikiforge.models.domain import Article, Topic
from wikiforge.models.enums import ExportTarget
from wikiforge.storage.repository import Repository

_TEMPLATES = Path(__file__).parent / "templates"


class Exporter:
    """Renders the wiki's topics/articles/graph to a chosen export target."""

    def __init__(self, repo: Repository, *, wiki_name: str = "wikiforge") -> None:
        self._repo = repo
        self._wiki_name = wiki_name
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES)),
            autoescape=select_autoescape(["html", "j2"]),
        )

    async def export(self, target: ExportTarget, out: Path) -> Path:
        """Write the export for ``target`` under directory ``out`` and return ``out``."""
        out.mkdir(parents=True, exist_ok=True)
        if target is ExportTarget.JSON:
            await self._export_json(out)
        elif target is ExportTarget.OBSIDIAN:
            await self._export_obsidian(out)
        else:
            await self._export_site(out)
        return out

    async def _topic_articles(self) -> list[tuple[Topic, Article]]:
        """Return (topic, latest article) pairs for every topic that has one."""
        pairs: list[tuple[Topic, Article]] = []
        for topic in await self._repo.list_topics():
            assert topic.id is not None
            article = await self._repo.latest_article_for_topic(topic.id)
            if article is not None:
                pairs.append((topic, article))
        return pairs

    async def _export_json(self, out: Path) -> None:
        pairs = await self._topic_articles()
        conflicts: list[dict[str, object]] = []
        links: list[dict[str, object]] = []
        citations: list[dict[str, object]] = []
        for topic, _ in pairs:
            assert topic.id is not None
            for c in await self._repo.conflicts_for_topic(topic.id):
                conflicts.append(c.model_dump(mode="json"))
            for related_id, score in await self._repo.topic_links(topic.id):
                links.append({"topic_id": topic.id, "related_topic_id": related_id, "score": score})
            for cit in await self._repo.citations_with_source_for_topic(topic.id):
                citations.append(
                    {
                        "topic_slug": topic.slug,
                        "claim": cit.claim,
                        "quote": cit.quote,
                        "raw_source_id": cit.raw_source_id,
                    }
                )
        data = {
            "wiki_name": self._wiki_name,
            "topics": [t.model_dump(mode="json") for t, _ in pairs],
            "articles": [a.model_dump(mode="json") for _, a in pairs],
            "citations": citations,
            "conflicts": conflicts,
            "topic_links": links,
            "inventory": [i.model_dump(mode="json") for i in await self._repo.list_all_inventory()],
            "datasets": [d.model_dump(mode="json") for d in await self._repo.list_datasets()],
        }
        (out / "wiki.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    async def _export_obsidian(self, out: Path) -> None:
        pairs = await self._topic_articles()
        for topic, article in pairs:
            fields = {
                "title": topic.title,
                "slug": topic.slug,
                "confidence": article.confidence,
                "status": str(topic.status),
            }
            lines = ["---"] + [f"{k}: {json.dumps(v)}" for k, v in fields.items()] + ["---", ""]
            body = "\n".join(lines) + article.body_md
            (out / f"{topic.slug}.md").write_text(body, encoding="utf-8")
        moc = ["# " + self._wiki_name, ""] + [
            f"- [[{t.slug}|{self._safe_alias(t.title)}]]" for t, _ in pairs
        ]
        (out / "index.md").write_text("\n".join(moc) + "\n", encoding="utf-8")

    @staticmethod
    def _safe_alias(title: str) -> str:
        """Strip characters that would break an Obsidian ``[[slug|alias]]`` wikilink."""
        return title.replace("]", "").replace("|", " ")

    async def _export_site(self, out: Path) -> None:
        pairs = await self._topic_articles()
        by_id = {t.id: t for t, _ in pairs}
        index_rows = [
            {"slug": t.slug, "title": t.title, "confidence": a.confidence} for t, a in pairs
        ]
        (out / "index.html").write_text(
            self._env.get_template("index.html.j2").render(
                wiki_name=self._wiki_name, topics=index_rows
            ),
            encoding="utf-8",
        )
        for topic, article in pairs:
            (out / f"{topic.slug}.html").write_text(
                self._env.get_template("topic.html.j2").render(
                    title=topic.title, confidence=article.confidence, body=article.body_md
                ),
                encoding="utf-8",
            )
        nodes = []
        for topic, _ in pairs:
            assert topic.id is not None
            related = []
            for related_id, score in await self._repo.topic_links(topic.id):
                other = by_id.get(related_id)
                if other is not None:
                    related.append({"slug": other.slug, "title": other.title, "score": score})
            nodes.append({"slug": topic.slug, "title": topic.title, "related": related})
        (out / "graph.html").write_text(
            self._env.get_template("graph.html.j2").render(nodes=nodes), encoding="utf-8"
        )
        (out / "style.css").write_text(
            (_TEMPLATES / "style.css").read_text(encoding="utf-8"), encoding="utf-8"
        )
