"""The orchestrator emits reporter events; a fake LLM keeps it offline."""

from __future__ import annotations

from pathlib import Path

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import LlmResult, ParsedResult
from wikiforge.models.domain import Topic
from wikiforge.models.schemas import ResearchFindingOut
from wikiforge.research.context import AgentResult
from wikiforge.research.orchestrator import ResearchOrchestrator
from wikiforge.research.progress import NullReporter, ResearchReporter
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class RecordingReporter:
    """Records every reporter event in call order, for assertion."""

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def on_start(self, personas: list[str]) -> None:
        self.events.append(("start", tuple(personas)))

    def on_agent_start(self, persona: str) -> None:
        self.events.append(("agent_start", persona))

    def on_agent_finish(self, result: AgentResult) -> None:
        self.events.append(("agent_finish", result.persona))

    def on_wave_complete(self, *, spend_usd: float) -> None:
        self.events.append(("wave", spend_usd))


class FakeLLM:
    """Deterministic offline LLM: canned text on `complete`, a canned finding on `parse`."""

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
            text="finding text", input_tokens=0, output_tokens=0, model="claude-sonnet-5"
        )

    async def parse(
        self, purpose, system, user, *, tier=None, schema=None, topic_id=None, session_id=None
    ) -> ParsedResult:
        out = ResearchFindingOut(
            claim="c", summary="s", key_points=["k"], cited_urls=["https://x"], stance="neutral"
        )
        return ParsedResult(parsed=out, input_tokens=0, output_tokens=0, model="claude-haiku-4-5")


async def test_null_reporter_satisfies_protocol() -> None:
    reporter: ResearchReporter = NullReporter()
    reporter.on_start(["a"])
    reporter.on_agent_start("a")
    reporter.on_wave_complete(spend_usd=0.0)  # no-ops, no error


async def test_research_emits_events_per_agent(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    try:
        repo = Repository(db)
        tid = await repo.upsert_topic(Topic(slug="t", title="T", stale_after_days=90))
        orch = ResearchOrchestrator(FakeLLM(), repo, cfg)
        reporter = RecordingReporter()
        assert tid is not None
        await orch.research(topic_id=tid, topic_title="T", mode="standard", reporter=reporter)
        kinds = [e[0] for e in reporter.events]
        assert kinds[0] == "start"
        personas = cfg.personas_for_mode("standard")
        assert kinds.count("agent_finish") == len(personas)
        assert "wave" in kinds
    finally:
        await db.close()
