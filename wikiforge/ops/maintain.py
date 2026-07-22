"""The maintenance job queue.

Free jobs run unconditionally — they cost SQL time and nothing else. Paid jobs
run in order while the window budget allows, and a job that cannot run is
*reported*, never silently omitted: a maintenance system that hides what it
skipped is indistinguishable from one that is broken.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import Config
from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.llm.governed import Budget, BudgetExhausted, GovernedProvider
from wikiforge.llm.provider import LLMProvider
from wikiforge.storage.repository import Repository

JobStatus = Literal["done", "nothing", "skipped", "failed"]


@dataclass
class JobContext:
    """Everything a job may need, with the embedder built only on demand."""

    home: Path
    cfg: Config
    repo: Repository
    tracker: CostTracker
    llm: LLMProvider | None = None
    _embedder: EmbeddingProvider | None = field(default=None, repr=False)

    def embedder(self) -> EmbeddingProvider:
        """Build the embedding provider on first use and cache it.

        Today's SessionStart flush builds it unconditionally, paying a ~9 s
        cold torch load even with nothing to embed. Jobs probe first and call
        this only when they have work.
        """
        from wikiforge.embed.factory import build_embedding_provider

        if self._embedder is None:
            self._embedder = build_embedding_provider(
                self.cfg, self.repo, cost_tracker=self.tracker
            )
        return self._embedder


@dataclass(frozen=True)
class Job:
    """One unit of maintenance: is there work, and how is it done."""

    name: str
    paid: bool
    probe: Callable[[JobContext], Awaitable[bool]]
    run: Callable[[JobContext], Awaitable[str]]


@dataclass(frozen=True)
class JobOutcome:
    """What happened to one job, in words fit for a report."""

    name: str
    status: JobStatus
    detail: str


@dataclass(frozen=True)
class MaintainReport:
    """The result of one run, including what was deliberately not done."""

    outcomes: list[JobOutcome]
    calls_used: int
    usd_used: float
    calls_left: int
    dry_run: bool = False
    # Mirrors Budget.forced — the --force run that produced this report, so
    # render() can describe the budget honestly instead of printing the huge
    # placeholder ceilings a forced run is given internally.
    forced: bool = False

    def render(self) -> str:
        """One line per job plus a budget line."""
        verb = "would run" if self.dry_run else "ran"
        lines = [f"wiki maintain — {verb} {len(self.outcomes)} job(s)"]
        for o in self.outcomes:
            lines.append(f"  {o.name}: {o.status} — {o.detail}")
        if self.forced:
            lines.append(
                f"  budget: {self.calls_used} call(s) / ${self.usd_used:.4f} used, "
                "unlimited (--force)"
            )
        else:
            lines.append(
                f"  budget: {self.calls_used} call(s) / ${self.usd_used:.4f} used, "
                f"{self.calls_left} call(s) left in the window"
            )
        return "\n".join(lines)


async def _probe_vectors(ctx: JobContext) -> bool:
    """True when any dev-log chunk still lacks a stored vector."""
    pending = await ctx.repo.chunks_missing_vectors(owner_type="raw_source", limit=1)
    return bool(pending)


async def _run_vectors(ctx: JobContext) -> str:
    """Backfill dev-log chunk vectors (free: local embedder, no LLM).

    ``flush_dev_events`` backfills vectors unconditionally before it looks at
    ``digests`` — verified against ``wikiforge/ops/flush.py`` during plan
    review — so ``digests=False`` alone is enough to make this call vectors-only.
    """
    from wikiforge.ops.flush import flush_dev_events

    stats = await flush_dev_events(ctx.repo, ctx.embedder(), None, ctx.cfg, digests=False)
    return f"embedded {stats.embedded_chunks} chunk(s)"


async def _probe_paths(ctx: JobContext) -> bool:
    """True when the file index is missing rows it could hold."""
    return await ctx.repo.count_dev_event_files() == 0


async def _run_paths(ctx: JobContext) -> str:
    """Ensure and backfill the file→event index (free, pure SQL)."""
    await ctx.repo.ensure_dev_event_files()
    return f"{await ctx.repo.count_dev_event_files()} indexed path(s)"


async def _probe_peers(ctx: JobContext) -> bool:
    """True when this machine has any registered peer to validate."""
    from wikiforge.federation.fanout import active_peers

    return bool(active_peers(ctx.cfg))


async def _run_peers(ctx: JobContext) -> str:
    """Report each peer's reachability and compatibility; repair nothing.

    Repairing a peer would be a cross-wiki write, which the design forbids —
    so a peer needing a reindex or lacking a file index is named here, with the
    command its owner should run.
    """
    from wikiforge.embed.factory import effective_embedding_dim
    from wikiforge.federation.fanout import active_peers
    from wikiforge.federation.peers import fix_hint, peer_status

    notes: list[str] = []
    for peer in active_peers(ctx.cfg):
        status = await peer_status(
            peer, local_model=ctx.embedder().model, dim=effective_embedding_dim(ctx.cfg)
        )
        hint = fix_hint(status)
        notes.append(f"{peer.alias}: {status.compat}" + (f" ({hint})" if hint else ""))
    return "; ".join(notes) or "no peers"


async def _probe_digests(ctx: JobContext) -> bool:
    """True when events are waiting for a summary and digests are enabled."""
    if ctx.cfg.capture.auto_digest_batches <= 0:
        return False
    return await ctx.repo.count_dev_events_pending_digest() > 0


async def _run_digests(ctx: JobContext) -> str:
    """Batch-summarize pending dev events (one cheap call per 25)."""
    from wikiforge.ops.flush import flush_dev_events

    llm = ctx.llm
    if llm is None:
        return "no LLM backend available"
    stats = await flush_dev_events(
        ctx.repo,
        ctx.embedder(),
        llm,
        ctx.cfg,
        digests=True,
        max_batches=ctx.cfg.capture.auto_digest_batches,
    )
    return f"digested {stats.digested_events} event(s), {stats.pending_left} left"


async def _probe_consolidate(ctx: JobContext) -> bool:
    """True only when the user opted in — the governor adds no spending default."""
    return ctx.cfg.consolidate.auto


async def _run_consolidate(ctx: JobContext) -> str:
    """Roll old events into the development-log article (one cheap call/period)."""
    from datetime import UTC, datetime

    from wikiforge.ops.consolidate import consolidate_dev_log, routed_clause

    llm = ctx.llm
    if llm is None:
        return "no LLM backend available"
    stats = await consolidate_dev_log(
        ctx.repo, ctx.embedder(), llm, ctx.cfg, ctx.home, now=datetime.now(UTC)
    )
    return (
        f"consolidated {stats.events} event(s) across {stats.periods} period(s)"
        f"{routed_clause(stats)}"
    )


JOBS: dict[str, Job] = {
    "vectors": Job("vectors", False, _probe_vectors, _run_vectors),
    "paths": Job("paths", False, _probe_paths, _run_paths),
    "peers": Job("peers", False, _probe_peers, _run_peers),
    "digests": Job("digests", True, _probe_digests, _run_digests),
    "consolidate": Job("consolidate", True, _probe_consolidate, _run_consolidate),
}


async def run_jobs(
    ctx: JobContext, *, names: list[str], budget: Budget, dry_run: bool
) -> MaintainReport:
    """Run the named jobs in order, honouring the budget, reporting everything.

    Unknown names are ignored so a config written for a later version still
    runs here. Every job is isolated: one failure is recorded and the queue
    continues, because this runs from a SessionStart hook.
    """
    used_calls, used_usd = await ctx.repo.maintenance_spend(budget.window_hours)
    governed = GovernedProvider(ctx.llm, ctx.repo, budget) if ctx.llm is not None else None
    outcomes: list[JobOutcome] = []
    for name in names:
        job = JOBS.get(name)
        if job is None:
            continue
        try:
            has_work = await job.probe(ctx)
        except Exception as exc:  # noqa: BLE001 -- a broken probe is a reported failure
            outcomes.append(JobOutcome(name, "failed", f"probe failed: {exc}"))
            continue
        if not has_work:
            outcomes.append(JobOutcome(name, "nothing", "nothing to do"))
            continue
        if job.paid:
            if governed is None:
                outcomes.append(JobOutcome(name, "skipped", "no LLM backend available"))
                continue
            if used_calls >= budget.max_calls or used_usd >= budget.max_usd:
                outcomes.append(
                    JobOutcome(name, "skipped", f"quota spent ({used_calls} calls in window)")
                )
                continue
        if dry_run:
            outcomes.append(
                JobOutcome(name, "skipped", "would run" + (" (paid)" if job.paid else " (free)"))
            )
            continue
        try:
            paid_ctx = ctx
            if job.paid and governed is not None:
                paid_ctx = JobContext(
                    home=ctx.home,
                    cfg=ctx.cfg,
                    repo=ctx.repo,
                    tracker=ctx.tracker,
                    llm=governed,
                    _embedder=ctx._embedder,
                )
            outcomes.append(JobOutcome(name, "done", await job.run(paid_ctx)))
            ctx._embedder = paid_ctx._embedder
        except BudgetExhausted as exc:
            outcomes.append(JobOutcome(name, "skipped", f"quota: {exc}"))
        except Exception as exc:  # noqa: BLE001 -- one bad job must not lose the queue
            outcomes.append(JobOutcome(name, "failed", str(exc)))
        used_calls, used_usd = await ctx.repo.maintenance_spend(budget.window_hours)
    return MaintainReport(
        outcomes=outcomes,
        calls_used=used_calls,
        usd_used=used_usd,
        calls_left=max(0, budget.max_calls - used_calls),
        dry_run=dry_run,
        forced=budget.forced,
    )
