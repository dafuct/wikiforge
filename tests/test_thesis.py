"""Thesis evaluation produces a stored verdict; volatility inference maps to stale days."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import LlmResult, ParsedResult
from wikiforge.models.enums import Verdict, Volatility
from wikiforge.models.schemas import ResearchFindingOut, ThesisVerdictOut, VolatilityInference
from wikiforge.research.orchestrator import ResearchOrchestrator
from wikiforge.research.volatility import infer_volatility
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeLLM:
    """Deterministic LLM: returns a canned thesis verdict / volatility on `parse`."""

    def __init__(self) -> None:
        self.verdict = ThesisVerdictOut(
            verdict=Verdict.SUPPORTED,
            rationale="strong evidence",
            supporting_source_ids=["1", "2"],
            refuting_source_ids=["3"],
            evidence_strength=0.8,
        )

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
    ) -> LlmResult:
        return LlmResult(
            text="finding with source https://x", input_tokens=0, output_tokens=0, model="m"
        )

    async def parse(
        self, purpose, system, user, *, tier=None, schema=None, topic_id=None, session_id=None
    ) -> ParsedResult:
        if schema is ThesisVerdictOut:
            return ParsedResult(parsed=self.verdict, input_tokens=0, output_tokens=0, model="m")
        if schema is VolatilityInference:
            out = VolatilityInference(volatility=Volatility.HIGH, reasoning="fast-moving")
            return ParsedResult(parsed=out, input_tokens=0, output_tokens=0, model="m")
        out = ResearchFindingOut(claim="c", summary="s", key_points=[], cited_urls=[], stance="for")
        return ParsedResult(parsed=out, input_tokens=0, output_tokens=0, model="m")


@pytest.fixture
async def env(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    yield cfg, repo
    await db.close()


async def test_evaluate_thesis_stores_verdict(env) -> None:
    cfg, repo = env
    orch = ResearchOrchestrator(FakeLLM(), repo, cfg)
    verdict = await orch.evaluate_thesis(claim="Coffee improves memory", mode="standard")
    assert verdict.verdict is Verdict.SUPPORTED
    assert 0.0 <= verdict.confidence <= 1.0
    assert verdict.id is not None


async def test_infer_volatility_maps_to_stale_days(env) -> None:
    cfg, _ = env
    volatility, stale_days = await infer_volatility(FakeLLM(), "Breaking AI news", cfg)
    assert volatility is Volatility.HIGH
    assert stale_days == cfg.volatility.HIGH  # 14
