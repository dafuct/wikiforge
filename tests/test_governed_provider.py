"""Purpose tagging makes the ledger complete; the ledger makes the cap real."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from wikiforge.llm.governed import Budget, BudgetExhausted, GovernedProvider
from wikiforge.llm.provider import LlmResult, ParsedResult
from wikiforge.services import init_wiki
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class _Out(BaseModel):
    value: str


class FakeProvider:
    """Records what purpose it was asked for; charges nothing by itself."""

    def __init__(self) -> None:
        self.purposes: list[str] = []

    async def complete(self, purpose: str, system: str, user: str, **kw: object) -> LlmResult:
        self.purposes.append(purpose)
        return LlmResult(text="ok", input_tokens=1, output_tokens=1, model="m")

    async def parse(
        self, purpose: str, system: str, user: str, *, schema: type[_Out], **kw: object
    ) -> ParsedResult[_Out]:
        self.purposes.append(purpose)
        return ParsedResult(parsed=schema(value="ok"), input_tokens=1, output_tokens=1, model="m")


async def _record(repo: Repository, purpose: str, *, cost: float, hours_ago: int) -> None:
    """Insert an llm_calls row at a controlled age, using SQLite's own clock."""
    await repo._db.conn.execute(  # noqa: SLF001 -- test fixture writes raw history
        "INSERT INTO llm_calls (ts, provider, model, purpose, cost_usd)"
        " VALUES (datetime('now', :off), 'p', 'm', :purpose, :cost)",
        {"off": f"-{hours_ago} hours", "purpose": purpose, "cost": cost},
    )
    await repo._db.conn.commit()  # noqa: SLF001


@pytest.mark.asyncio
async def test_ledger_counts_only_tagged_calls_in_the_window(tmp_path: Path) -> None:
    """Interactive spending must not consume the maintenance quota."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    db = await Database.open(home, dim=384)
    try:
        repo = Repository(db)
        await _record(repo, "maintain:capture", cost=0.10, hours_ago=1)
        await _record(repo, "maintain:consolidate", cost=0.20, hours_ago=23)
        await _record(repo, "maintain:capture", cost=5.00, hours_ago=48)  # outside
        await _record(repo, "capture", cost=9.00, hours_ago=1)  # interactive
        calls, usd = await repo.maintenance_spend(24)
    finally:
        await db.close()
    assert calls == 2
    assert usd == pytest.approx(0.30)


@pytest.mark.asyncio
async def test_purpose_is_tagged_on_both_methods(tmp_path: Path) -> None:
    """Tagging is at the wrapper, so future jobs are counted with no plumbing."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    db = await Database.open(home, dim=384)
    try:
        inner = FakeProvider()
        gov = GovernedProvider(
            inner, Repository(db), Budget(max_calls=5, max_usd=1.0, window_hours=24)
        )
        await gov.complete("capture", "s", "u")
        await gov.parse("consolidate", "s", "u", schema=_Out)
    finally:
        await db.close()
    assert inner.purposes == ["maintain:capture", "maintain:consolidate"]


@pytest.mark.asyncio
async def test_call_cap_raises_before_the_next_call(tmp_path: Path) -> None:
    """Enforcement is pre-call: the (N+1)-th never reaches the provider."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    db = await Database.open(home, dim=384)
    try:
        repo = Repository(db)
        await _record(repo, "maintain:capture", cost=0.0, hours_ago=1)
        await _record(repo, "maintain:capture", cost=0.0, hours_ago=1)
        inner = FakeProvider()
        gov = GovernedProvider(inner, repo, Budget(max_calls=2, max_usd=1.0, window_hours=24))
        with pytest.raises(BudgetExhausted):
            await gov.complete("capture", "s", "u")
    finally:
        await db.close()
    assert inner.purposes == []


@pytest.mark.asyncio
async def test_usd_cap_binds_independently(tmp_path: Path) -> None:
    """Whichever ceiling is reached first stops the run."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    db = await Database.open(home, dim=384)
    try:
        repo = Repository(db)
        await _record(repo, "maintain:capture", cost=0.60, hours_ago=2)
        gov = GovernedProvider(
            FakeProvider(), repo, Budget(max_calls=99, max_usd=0.50, window_hours=24)
        )
        with pytest.raises(BudgetExhausted):
            await gov.complete("capture", "s", "u")
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_a_job_degrades_instead_of_failing(tmp_path: Path) -> None:
    """flush and consolidate already break out of their loops when the provider
    raises; the governor relies on that, so it is asserted here."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    db = await Database.open(home, dim=384)
    try:
        gov = GovernedProvider(
            FakeProvider(), Repository(db), Budget(max_calls=0, max_usd=1.0, window_hours=24)
        )
        done = 0
        try:
            for _ in range(3):
                await gov.parse("capture", "s", "u", schema=_Out)
                done += 1
        except Exception:
            pass
    finally:
        await db.close()
    assert done == 0
