"""The research fan-out orchestrator: waves of persona agents with budget + resume."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime

from wikiforge.config.settings import Config
from wikiforge.llm.provider import LLMProvider
from wikiforge.models.domain import RawSource, ResearchFinding, ResearchSession
from wikiforge.models.enums import SessionStatus, SourceType, Stance
from wikiforge.models.schemas import ResearchFindingOut
from wikiforge.research.context import SESSION_CTX, AgentResult, SessionContext
from wikiforge.research.personas import persona_system_prompt
from wikiforge.storage.repository import Repository

_WAVE_SIZE = 3


class ResearchOrchestrator:
    """Fans out persona research agents in waves, enforcing a budget and supporting resume."""

    def __init__(self, llm: LLMProvider, repo: Repository, config: Config) -> None:
        """Bind the orchestrator to an LLM backend, repository, and loaded config."""
        self._llm = llm
        self._repo = repo
        self._config = config

    async def research(
        self,
        *,
        topic_id: int,
        topic_title: str,
        mode: str,
        budget_usd: float | None = None,
        resume_session_id: int | None = None,
    ) -> ResearchSession:
        """Run (or resume) a research session over the personas for ``mode``.

        Runs personas in waves of ``_WAVE_SIZE``. Before each wave, if a
        ``budget_usd`` cap is set and accumulated session spend has already
        reached it, stops early and marks the session ``PARTIAL`` — so the
        first wave always runs, and the cap only ever stops a *later* wave.
        A resume (``resume_session_id`` set) re-runs only the personas with no
        persisted finding yet, and is governed solely by the ``budget_usd``
        passed to *this* call — it does not inherit the original session's
        (already-spent) cap.
        """
        personas = self._config.personas_for_mode(mode)
        if resume_session_id is not None:
            session_id = resume_session_id
        else:
            session_id = await self._repo.create_research_session(
                ResearchSession(
                    topic_id=topic_id,
                    mode=mode,
                    budget_usd=budget_usd,
                    status=SessionStatus.RUNNING,
                )
            )

        done = await self._repo.personas_with_findings(session_id)
        todo = [p for p in personas if p not in done]

        ctx = SessionContext(session_id=session_id, topic=topic_title, trace_id=uuid.uuid4().hex)
        token = SESSION_CTX.set(ctx)
        stopped_for_budget = False
        try:
            for wave_start in range(0, len(todo), _WAVE_SIZE):
                if (
                    budget_usd is not None
                    and await self._repo.session_spend(session_id) >= budget_usd
                ):
                    stopped_for_budget = True
                    break
                wave = todo[wave_start : wave_start + _WAVE_SIZE]
                async with asyncio.TaskGroup() as tg:
                    tasks = [
                        tg.create_task(self._run_agent(session_id, topic_title, p)) for p in wave
                    ]
                # AgentResult never raises; a failed agent is recorded but non-fatal.
                _ = [t.result() for t in tasks]
        finally:
            SESSION_CTX.reset(token)

        spent = await self._repo.session_spend(session_id)
        final_done = await self._repo.personas_with_findings(session_id)
        complete = final_done >= set(personas)
        status = (
            SessionStatus.DONE if (complete and not stopped_for_budget) else SessionStatus.PARTIAL
        )
        await self._repo.update_session(
            session_id,
            status=status,
            spend_usd=spent,
            ended_at=datetime.now(UTC).isoformat(),
        )
        result = await self._repo.get_research_session(session_id)
        if result is None:
            raise RuntimeError(f"research session {session_id} vanished after update")
        return result

    async def _run_agent(self, session_id: int, topic_title: str, persona: str) -> AgentResult:
        """Run one persona agent: search, persist finding, normalize. Never raises."""
        try:
            system = persona_system_prompt(persona)
            completion = await self._llm.complete(
                "research",
                system,
                f"Research this topic: {topic_title}",
                tier="flagship",
                use_web_search=True,
                session_id=session_id,
            )
            source = RawSource(
                content_hash=_finding_hash(session_id, persona, completion.text),
                source_type=SourceType.FINDING,
                title=f"{persona} research on {topic_title}",
                text=completion.text,
                fetched_at=datetime.now(UTC),
                first_seen_session_id=session_id,
                persona=persona,
                provenance={"session_id": str(session_id), "persona": persona},
            )
            source_id, _ = await self._repo.ingest_raw_source(source)
            normalized = await self._llm.parse(
                "normalize",
                "Normalize this research finding into the schema.",
                f"<source_data>{completion.text}</source_data>",
                tier="cheap",
                schema=ResearchFindingOut,
                session_id=session_id,
            )
            finding_id = await self._repo.add_finding(
                ResearchFinding(
                    session_id=session_id,
                    persona=persona,
                    raw_source_id=source_id,
                    summary=normalized.parsed.summary,
                    stance=_stance_of(normalized.parsed.stance),
                )
            )
            return AgentResult(persona=persona, ok=True, finding_id=finding_id)
        except Exception as exc:  # noqa: BLE001 — agents must never abort the round
            return AgentResult(persona=persona, ok=False, error=repr(exc))


def _finding_hash(session_id: int, persona: str, text: str) -> str:
    """Content-address a finding by session, persona, and text so re-runs dedup cleanly."""
    return hashlib.sha256(f"{session_id}:{persona}:{text}".encode()).hexdigest()


def _stance_of(value: str) -> Stance:
    """Coerce a model-reported stance string to :class:`Stance`, defaulting to NEUTRAL."""
    try:
        return Stance(value.lower())
    except ValueError:
        return Stance.NEUTRAL
