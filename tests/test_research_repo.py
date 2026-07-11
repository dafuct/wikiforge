"""Research session persistence, findings, resume set, and spend."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import LlmCall, RawSource, ResearchFinding, ResearchSession, Topic
from wikiforge.models.enums import SessionStatus, SourceType, Stance, Volatility
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def repo(wiki_home: Path):
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    yield Repository(db)
    await db.close()


async def _finding(repo: Repository, session_id: int, persona: str) -> int:
    src = RawSource(
        content_hash=f"h-{persona}",
        source_type=SourceType.FINDING,
        title=persona,
        text="finding text",
        fetched_at=datetime.now(UTC),
        persona=persona,
    )
    src_id, _ = await repo.ingest_raw_source(src)
    return await repo.add_finding(
        ResearchFinding(
            session_id=session_id,
            persona=persona,
            raw_source_id=src_id,
            summary="s",
            stance=Stance.NEUTRAL,
        )
    )


async def test_session_lifecycle(repo: Repository) -> None:
    tid = await repo.upsert_topic(
        Topic(slug="t", title="T", volatility=Volatility.MEDIUM, stale_after_days=90)
    )
    sid = await repo.create_research_session(
        ResearchSession(topic_id=tid, mode="standard", budget_usd=1.0)
    )
    assert sid > 0
    got = await repo.get_research_session(sid)
    assert got is not None and got.status is SessionStatus.RUNNING
    await repo.update_session(sid, status=SessionStatus.PARTIAL, spend_usd=0.4)
    got2 = await repo.get_research_session(sid)
    assert (
        got2 is not None
        and got2.status is SessionStatus.PARTIAL
        and got2.spend_usd == pytest.approx(0.4)
    )


async def test_personas_with_findings_for_resume(repo: Repository) -> None:
    tid = await repo.upsert_topic(Topic(slug="t", title="T", stale_after_days=90))
    sid = await repo.create_research_session(ResearchSession(topic_id=tid, mode="standard"))
    await _finding(repo, sid, "academic")
    await _finding(repo, sid, "technical")
    done = await repo.personas_with_findings(sid)
    assert done == {"academic", "technical"}


async def test_session_spend_sums_llm_calls(repo: Repository) -> None:
    tid = await repo.upsert_topic(Topic(slug="t", title="T", stale_after_days=90))
    sid = await repo.create_research_session(ResearchSession(topic_id=tid, mode="standard"))
    await repo.insert_llm_call(
        LlmCall(
            provider="anthropic",
            model="claude-sonnet-5",
            purpose="research",
            cost_usd=0.10,
            session_id=sid,
        )
    )
    await repo.insert_llm_call(
        LlmCall(
            provider="anthropic",
            model="claude-sonnet-5",
            purpose="research",
            cost_usd=0.25,
            session_id=sid,
        )
    )
    await repo.insert_llm_call(
        LlmCall(
            provider="anthropic",
            model="claude-haiku-4-5",
            purpose="normalize",
            cost_usd=0.01,
            session_id=999,
        )
    )
    assert await repo.session_spend(sid) == pytest.approx(0.35)
