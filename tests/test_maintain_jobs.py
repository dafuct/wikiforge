"""The job queue: free jobs always, paid jobs only within the window budget."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from wikiforge.config.settings import load_config
from wikiforge.llm.governed import Budget
from wikiforge.llm.provider import LlmResult, ParsedResult
from wikiforge.ops.maintain import JobContext, MaintainReport, run_jobs
from wikiforge.services import init_wiki
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def _ctx(home: Path) -> tuple[JobContext, Database]:
    """A context over a fresh wiki, with no LLM provider available."""
    from wikiforge.activity.cost import CostTracker

    cfg = load_config(home)
    db = await Database.open(home, dim=384)
    repo = Repository(db)
    return JobContext(home=home, cfg=cfg, repo=repo, tracker=CostTracker(repo, cfg), llm=None), db


@pytest.mark.asyncio
async def test_free_jobs_run_with_a_zero_budget(tmp_path: Path) -> None:
    """Free jobs never consume quota, so a spent budget cannot block them."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    ctx, db = await _ctx(home)
    try:
        report: MaintainReport = await run_jobs(
            ctx,
            names=["vectors", "paths", "peers"],
            budget=Budget(max_calls=0, max_usd=0.0, window_hours=24),
            dry_run=False,
        )
    finally:
        await db.close()
    assert {o.name for o in report.outcomes} == {"vectors", "paths", "peers"}
    assert all(o.status in {"done", "nothing"} for o in report.outcomes)


@pytest.mark.asyncio
async def test_paid_jobs_are_skipped_when_the_budget_is_spent(tmp_path: Path) -> None:
    """A skipped paid job is reported, never silently omitted."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    ctx, db = await _ctx(home)
    try:
        report = await run_jobs(
            ctx,
            names=["digests"],
            budget=Budget(max_calls=0, max_usd=1.0, window_hours=24),
            dry_run=False,
        )
    finally:
        await db.close()
    outcome = next(o for o in report.outcomes if o.name == "digests")
    assert outcome.status in {"skipped", "nothing"}
    assert "quota" in outcome.detail or "nothing" in outcome.detail


@pytest.mark.asyncio
async def test_dry_run_spends_nothing_and_still_reports(tmp_path: Path) -> None:
    """--dry-run answers "what would happen" without doing it."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    ctx, db = await _ctx(home)
    try:
        report = await run_jobs(
            ctx,
            names=["vectors", "paths", "peers", "digests", "consolidate"],
            budget=Budget(max_calls=8, max_usd=0.5, window_hours=24),
            dry_run=True,
        )
        rendered = report.render()
        row = await db.fetchone("SELECT COUNT(*) AS n FROM llm_calls")
    finally:
        await db.close()
    assert row is not None and row["n"] == 0
    assert len(report.outcomes) == 5
    assert "would" in rendered


@pytest.mark.asyncio
async def test_unknown_job_names_are_ignored(tmp_path: Path) -> None:
    """A config written for a later version still runs on this one."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    ctx, db = await _ctx(home)
    try:
        report = await run_jobs(
            ctx,
            names=["vectors", "teleport"],
            budget=Budget(max_calls=8, max_usd=0.5, window_hours=24),
            dry_run=False,
        )
    finally:
        await db.close()
    assert [o.name for o in report.outcomes] == ["vectors"]


@pytest.mark.asyncio
async def test_one_failing_job_does_not_stop_the_others(tmp_path: Path) -> None:
    """maintain --hook must never lose the rest of the queue to one bad job."""
    import wikiforge.ops.maintain as maintain

    home = tmp_path / "wiki"
    await init_wiki("w", home)
    ctx, db = await _ctx(home)

    async def boom(_: JobContext) -> str:
        raise RuntimeError("disk on fire")

    original = maintain.JOBS["paths"].run
    maintain.JOBS["paths"] = maintain.Job(
        name="paths", paid=False, probe=maintain.JOBS["paths"].probe, run=boom
    )
    try:
        report = await run_jobs(
            ctx,
            names=["paths", "vectors"],
            budget=Budget(max_calls=8, max_usd=0.5, window_hours=24),
            dry_run=False,
        )
    finally:
        maintain.JOBS["paths"] = maintain.Job(
            name="paths", paid=False, probe=maintain.JOBS["paths"].probe, run=original
        )
        await db.close()
    statuses = {o.name: o.status for o in report.outcomes}
    assert statuses["paths"] == "failed"
    assert statuses["vectors"] in {"done", "nothing"}


@pytest.mark.asyncio
async def test_embedder_is_not_built_when_there_is_nothing_to_embed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measured win over today's unconditional ~9s torch load (spec §8.2)."""
    import wikiforge.embed.factory as factory

    home = tmp_path / "wiki"
    await init_wiki("w", home)
    built = False

    def explode(*args: object, **kwargs: object) -> object:
        nonlocal built
        built = True
        raise AssertionError("the embedder must not be built with no backfill pending")

    monkeypatch.setattr(factory, "build_embedding_provider", explode)
    ctx, db = await _ctx(home)
    try:
        await run_jobs(
            ctx,
            names=["vectors"],
            budget=Budget(max_calls=8, max_usd=0.5, window_hours=24),
            dry_run=False,
        )
    finally:
        await db.close()
    assert built is False


class _FakeOut(BaseModel):
    """A trivial schema for the fake provider used below."""

    value: str


class _FakeProvider:
    """An LLMProvider stub whose ``parse`` is never expected to actually run.

    Used only to make ``ctx.llm`` non-``None`` so ``run_jobs`` builds a real
    ``GovernedProvider`` and lets a paid job's ``run()`` execute — the
    provider itself is irrelevant to the two tests below, which replace the
    job's ``run`` outright.
    """

    async def complete(self, purpose: str, system: str, user: str, **kw: object) -> LlmResult:
        return LlmResult(text="ok", input_tokens=1, output_tokens=1, model="m")

    async def parse(
        self, purpose: str, system: str, user: str, *, schema: type[_FakeOut], **kw: object
    ) -> ParsedResult[_FakeOut]:
        return ParsedResult(parsed=schema(value="ok"), input_tokens=1, output_tokens=1, model="m")


@pytest.mark.asyncio
async def test_budget_exhausted_mid_run_is_reported_as_skipped_not_failed(
    tmp_path: Path,
) -> None:
    """BudgetExhausted raised inside run() must map to "skipped", never "failed".

    ``run_jobs`` pre-checks the ledger before calling ``run()``, so this test
    forces the exhaustion to surface *from inside* ``run()`` instead (as a
    multi-call job's second call would) by having the job body raise
    ``BudgetExhausted`` directly — the case ``except BudgetExhausted`` (listed
    before the catch-all ``except Exception``) exists to handle.
    """
    import wikiforge.ops.maintain as maintain
    from wikiforge.llm.governed import BudgetExhausted

    home = tmp_path / "wiki"
    await init_wiki("w", home)
    ctx, db = await _ctx(home)
    ctx = JobContext(
        home=ctx.home, cfg=ctx.cfg, repo=ctx.repo, tracker=ctx.tracker, llm=_FakeProvider()
    )

    async def probe_true(_: JobContext) -> bool:
        return True

    async def exhausted(_: JobContext) -> str:
        raise BudgetExhausted("1/1 maintenance calls used in the last 24h")

    original = maintain.JOBS["digests"]
    maintain.JOBS["digests"] = maintain.Job(
        name="digests", paid=True, probe=probe_true, run=exhausted
    )
    try:
        report = await run_jobs(
            ctx,
            names=["digests"],
            budget=Budget(max_calls=5, max_usd=0.5, window_hours=24),
            dry_run=False,
        )
    finally:
        maintain.JOBS["digests"] = original
        await db.close()
    outcome = next(o for o in report.outcomes if o.name == "digests")
    assert outcome.status == "skipped"
    assert "quota" in outcome.detail


@pytest.mark.asyncio
async def test_paid_job_helpers_report_missing_llm_instead_of_raising(tmp_path: Path) -> None:
    """Calling a paid job's run() directly with no LLM must not raise AttributeError.

    ``run_jobs`` already gates paid jobs on ``ctx.llm`` before calling ``run()``,
    so this exercises the jobs' own defensive guard directly — the last line of
    defense against a future call site that skips that gate.
    """
    from wikiforge.ops.maintain import _run_consolidate, _run_digests

    home = tmp_path / "wiki"
    await init_wiki("w", home)
    ctx, db = await _ctx(home)
    try:
        digest_detail = await _run_digests(ctx)
        consolidate_detail = await _run_consolidate(ctx)
    finally:
        await db.close()
    assert digest_detail == "no LLM backend available"
    assert consolidate_detail == "no LLM backend available"
