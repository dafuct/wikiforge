"""Infer a topic's freshness volatility at creation time."""

from __future__ import annotations

from wikiforge.config.settings import Config
from wikiforge.llm.provider import LLMProvider
from wikiforge.llm.safety import seal_source_data
from wikiforge.models.enums import Volatility
from wikiforge.models.schemas import VolatilityInference


async def infer_volatility(llm: LLMProvider, title: str, config: Config) -> tuple[Volatility, int]:
    """Infer a topic's volatility class and its configured stale-after-days.

    LOW/MEDIUM/HIGH map to the ``[volatility]`` day thresholds in config.
    """
    result = await llm.parse(
        "extract",
        "Classify how quickly knowledge about a topic becomes stale: LOW (stable, ~yearly), "
        "MEDIUM (~quarterly), or HIGH (fast-moving, ~biweekly).",
        f"<source_data>{seal_source_data(title)}</source_data>",
        tier="cheap",
        schema=VolatilityInference,
    )
    volatility = result.parsed.volatility
    stale_days = {
        Volatility.LOW: config.volatility.LOW,
        Volatility.MEDIUM: config.volatility.MEDIUM,
        Volatility.HIGH: config.volatility.HIGH,
    }[volatility]
    return volatility, stale_days
