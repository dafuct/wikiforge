"""AnthropicProvider: complete + parse, with cost recorded and HTTP stubbed."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.anthropic_provider import AnthropicProvider
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_MESSAGES = "https://api.anthropic.com/v1/messages"


def _message_json(text: str, model: str) -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


@pytest.fixture
async def provider(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    tracker = CostTracker(Repository(db), cfg)
    client = AsyncAnthropic(api_key="test-key")
    yield AnthropicProvider(client, tracker, cfg), tracker
    await db.close()


@respx.mock
async def test_complete_returns_text_and_records_cost(provider) -> None:
    prov, tracker = provider
    respx.post(_MESSAGES).mock(
        return_value=httpx.Response(200, json=_message_json("the answer", "claude-haiku-4-5"))
    )
    result = await prov.complete("extract", "sys", "user", tier="cheap")
    assert result.text == "the answer"
    assert result.input_tokens == 12 and result.output_tokens == 8
    totals = await tracker.totals_by_model()
    # haiku: 12/1e6*1 + 8/1e6*5 = 5.2e-5
    assert totals["claude-haiku-4-5"] == pytest.approx(5.2e-5)


@respx.mock
async def test_parse_binds_schema(provider) -> None:
    prov, _ = provider

    class Person(BaseModel):
        name: str
        age: int

    respx.post(_MESSAGES).mock(
        return_value=httpx.Response(
            200, json=_message_json('{"name": "Ada", "age": 36}', "claude-sonnet-5")
        )
    )
    result = await prov.parse("normalize", "sys", "user", tier="flagship", schema=Person)
    assert result.parsed.name == "Ada"
    assert result.parsed.age == 36
