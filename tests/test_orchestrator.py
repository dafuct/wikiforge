"""Research fan-out: full run, budget-stop between waves, and resume."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import LlmResult, ParsedResult
from wikiforge.models.domain import LlmCall, Topic
from wikiforge.models.enums import SessionStatus
from wikiforge.models.schemas import ResearchFindingOut
from wikiforge.research.orchestrator import ResearchOrchestrator
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeLLM:
    """Deterministic LLM: records a fixed cost per `complete` (so the between-wave budget
    check sees spend), and returns a canned finding on `parse`."""

    def __init__(self, repo: Repository, cost_per_call: float) -> None:
        self._repo = repo
        self._cost = cost_per_call
        self.completes = 0

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
        self.completes += 1
        # Attribute a deterministic cost to the session so budget math is exact.
        await self._repo.insert_llm_call(
            LlmCall(
                provider="fake",
                model="fake",
                purpose=purpose,
                cost_usd=self._cost,
                session_id=session_id,
            )
        )
        return LlmResult(
            text="web finding text with a source https://x",
            input_tokens=0,
            output_tokens=0,
            model="claude-sonnet-5",
        )

    async def parse(
        self, purpose, system, user, *, tier=None, schema=None, topic_id=None, session_id=None
    ) -> ParsedResult:
        out = ResearchFindingOut(
            claim="c", summary="s", key_points=["k"], cited_urls=["https://x"], stance="neutral"
        )
        return ParsedResult(parsed=out, input_tokens=0, output_tokens=0, model="claude-haiku-4-5")


@pytest.fixture
async def env(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    tracker = CostTracker(repo, cfg)
    tid = await repo.upsert_topic(Topic(slug="t", title="Topic", stale_after_days=90))
    yield cfg, repo, tracker, tid
    await db.close()


async def test_standard_research_runs_five_personas(env) -> None:
    cfg, repo, tracker, tid = env
    orch = ResearchOrchestrator(FakeLLM(repo, cost_per_call=0.01), repo, cfg)
    session = await orch.research(topic_id=tid, topic_title="Topic", mode="standard")
    assert session.status is SessionStatus.DONE
    done = await repo.personas_with_findings(session.id)
    assert len(done) == 5


async def test_budget_stops_between_waves(env) -> None:
    cfg, repo, tracker, tid = env
    # cost 0.5/call, budget 1.2 -> first wave of 3 spends 1.5 >= 1.2 -> stop, PARTIAL
    orch = ResearchOrchestrator(FakeLLM(repo, cost_per_call=0.5), repo, cfg)
    session = await orch.research(
        topic_id=tid, topic_title="Topic", mode="standard", budget_usd=1.2
    )
    assert session.status is SessionStatus.PARTIAL
    done = await repo.personas_with_findings(session.id)
    assert len(done) == 3  # only the first wave completed


async def test_flaky_agent_does_not_abort_round(env) -> None:
    cfg, repo, tracker, tid = env

    class FlakyLLM(FakeLLM):
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
            if "'contrarian'" in system:  # persona name appears in the persona system prompt
                raise RuntimeError("simulated search failure")
            return await super().complete(
                purpose,
                system,
                user,
                tier=tier,
                use_web_search=use_web_search,
                topic_id=topic_id,
                session_id=session_id,
            )

    orch = ResearchOrchestrator(FlakyLLM(repo, cost_per_call=0.01), repo, cfg)
    session = await orch.research(topic_id=tid, topic_title="Topic", mode="standard")
    # Every wave ran (no budget stop) -> DONE, even though one persona failed.
    assert session.status is SessionStatus.DONE
    done = await repo.personas_with_findings(session.id)
    assert "contrarian" not in done  # the flaky persona produced no finding
    assert len(done) == 4  # the other four succeeded; the round was not aborted


async def test_resume_reruns_only_unfinished(env) -> None:
    cfg, repo, tracker, tid = env
    orch = ResearchOrchestrator(FakeLLM(repo, cost_per_call=0.5), repo, cfg)
    partial = await orch.research(
        topic_id=tid, topic_title="Topic", mode="standard", budget_usd=1.2
    )
    assert partial.status is SessionStatus.PARTIAL
    before = await repo.personas_with_findings(partial.id)
    # resume with no budget cap -> the remaining 2 personas run, session completes
    resumed = await orch.research(
        topic_id=tid, topic_title="Topic", mode="standard", resume_session_id=partial.id
    )
    assert resumed.status is SessionStatus.DONE
    after = await repo.personas_with_findings(resumed.id)
    assert after == set(cfg.personas_for_mode("standard"))
    assert before < after  # only the unfinished ones were added
