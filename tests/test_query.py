"""Query service: retrieved context is wrapped in <source_data> and answered with citations."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import LlmResult
from wikiforge.models.domain import Article, Topic
from wikiforge.query.service import answer_query
from wikiforge.search.index import index_owner
from wikiforge.search.retriever import HybridRetriever
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class CapturingLLM:
    def __init__(self) -> None:
        self.last_user: str | None = None

    async def complete(
        self,
        purpose,
        system,
        user,
        *,
        tier=None,
        use_web_search=False,
        topic_id=None,
        session_id=None,
    ):
        self.last_user = user
        return LlmResult(
            text="Rust async is cooperative [1].", input_tokens=0, output_tokens=0, model="m"
        )

    async def parse(self, *a, **k):
        raise NotImplementedError


class KeywordEmbedder:
    @property
    def dim(self) -> int:
        return 4

    @property
    def model(self) -> str:
        return "kw"

    @property
    def provider_name(self) -> str:
        return "kw"

    async def embed(self, texts):
        return [[1.0 if "async" in t.lower() else 0.0, 0.0, 0.0, 0.1] for t in texts]


@pytest.fixture
async def env(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    emb = KeywordEmbedder()
    tid = await repo.upsert_topic(Topic(slug="rust-async", title="Rust Async", stale_after_days=90))
    aid = await repo.insert_article(
        Article(
            topic_id=tid,
            slug="rust-async",
            title="Rust Async",
            body_md="Rust async is cooperative and fast.",
            path="topics/rust-async/wiki/rust-async.md",
            confidence=0.7,
            compile_digest="d",
            version=1,
        )
    )
    await index_owner(
        repo, emb, owner_type="article", owner_id=aid, text="Rust async is cooperative and fast."
    )
    yield cfg, repo, emb
    await db.close()


async def test_query_wraps_context_and_returns_answer(env) -> None:
    cfg, repo, emb = env
    llm = CapturingLLM()
    retriever = HybridRetriever(repo, emb, cfg)
    result = await answer_query(llm, retriever, "how does async work in rust", depth="quick")
    assert "cooperative" in result.answer
    assert llm.last_user is not None and "<source_data" in llm.last_user
    assert result.sources  # the retrieved chunks are returned


async def test_query_no_results(tmp_path: Path) -> None:
    # An EMPTY wiki (no articles indexed) -> retrieval returns nothing.
    # (Vector KNN always returns a nearest chunk when any exist, so the genuine
    # no-results case is an empty index, not an "unrelated" query.)
    home = tmp_path / "empty"
    home.mkdir()
    write_default_config(home, wiki_name="x")
    cfg = load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    try:
        llm = CapturingLLM()
        retriever = HybridRetriever(Repository(db), KeywordEmbedder(), cfg)
        result = await answer_query(llm, retriever, "anything at all", depth="quick")
        assert result.sources == []
        assert "no" in result.answer.lower() or "not" in result.answer.lower()
        assert llm.last_user is None  # short-circuits with no LLM call on empty retrieval
    finally:
        await db.close()
