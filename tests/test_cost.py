"""CostTracker computes prices from the pricing table and records calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def tracker(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    yield CostTracker(Repository(db), cfg)
    await db.close()


def test_compute_cost_uses_pricing_table(tracker: CostTracker) -> None:
    # haiku: $1/M input, $5/M output. 1_000_000 in + 200_000 out = 1.0 + 1.0 = 2.0
    cost = tracker.compute_cost("claude-haiku-4-5", 1_000_000, 200_000)
    assert cost == pytest.approx(2.0)


def test_compute_cost_unknown_model_is_zero(tracker: CostTracker) -> None:
    assert tracker.compute_cost("no-such-model", 1000, 1000) == 0.0


async def test_record_writes_row_and_returns_cost(tracker: CostTracker) -> None:
    cost = await tracker.record(
        provider="anthropic",
        model="claude-sonnet-5",
        purpose="synthesize",
        input_tokens=500_000,
        output_tokens=100_000,
    )
    # sonnet-5: $3/M in, $15/M out -> 1.5 + 1.5 = 3.0
    assert cost == pytest.approx(3.0)
    totals = await tracker.totals_by_model()
    assert totals["claude-sonnet-5"] == pytest.approx(3.0)
