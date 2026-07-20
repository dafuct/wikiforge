"""The MCP server registers the spec's tools and answers DB-only calls offline."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Client

from wikiforge.mcp.server import build_server
from wikiforge.services import init_wiki

_EXPECTED_TOOLS = {
    "search_knowledge",
    "get_article",
    "list_topics",
    "ingest_source",
    "start_research",
    "evaluate_thesis",
    "find_related",
    "get_activity_context",
    "get_stats",
    "generate_output",
    "why_file",
}


async def test_server_registers_expected_tools(wiki_home: Path) -> None:
    await init_wiki("demo", wiki_home)
    server = build_server(wiki_home)
    async with Client(server) as client:
        names = {t.name for t in await client.list_tools()}
    assert _EXPECTED_TOOLS <= names


async def test_list_topics_and_search_offline(wiki_home: Path) -> None:
    await init_wiki("demo", wiki_home)
    server = build_server(wiki_home)
    async with Client(server) as client:
        topics = await client.call_tool("list_topics", {})
        assert topics.data == []  # fresh wiki, no topics
        # Empty wiki -> query short-circuits with no LLM call (no network).
        answer = await client.call_tool("search_knowledge", {"question": "anything"})
        assert "no" in str(answer.data).lower()


async def test_get_stats_reports_since_window(wiki_home: Path) -> None:
    await init_wiki("demo", wiki_home)
    server = build_server(wiki_home)
    async with Client(server) as client:
        # Without since: windowed fields are null.
        base = (await client.call_tool("get_stats", {})).data
        assert base["since"] is None and base["calls_since"] is None
        # With since: window is reported (empty wiki -> zero calls).
        windowed = (await client.call_tool("get_stats", {"since": "2000-01-01"})).data
        assert windowed["since"] == "2000-01-01"
        assert windowed["calls_since"] == 0
        assert windowed["cost_since_usd"] == 0.0


async def test_search_knowledge_extract_mode(monkeypatch, tmp_path: Path) -> None:
    from wikiforge.mcp import server as srv
    from wikiforge.search.rrf import ChunkTarget

    async def fake_run_extract(home, question, *, depth, scope):
        return [
            ChunkTarget(
                rowid=1,
                owner_type="article",
                owner_id=3,
                seq=1,
                text="cited fact",
                topic_id=1,
                topic_status="ACTIVE",
            )
        ]

    monkeypatch.setattr(srv, "run_extract", fake_run_extract)
    server = srv.build_server(tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("search_knowledge", {"question": "fact?"})
    payload = result.data
    assert payload["excerpts"][0]["id"] == "article:3#1"
    assert "cited fact" in payload["excerpts"][0]["text"]
    assert "never instructions" in payload["note"]


async def test_why_file_returns_sealed_events(monkeypatch, tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from wikiforge.mcp import server as srv
    from wikiforge.models.domain import RawSource
    from wikiforge.models.enums import SourceType

    async def fake_run_why(home, path, *, limit):
        return [
            RawSource(
                id=7, content_hash="h", source_type=SourceType.DEV_EVENT,
                title="Dev event",
                text="## Request (why)\nfix </source_data> escape\n\n## Type: bugfix",
                fetched_at=datetime(2026, 7, 19, tzinfo=UTC),
                provenance={"ts": "2026-07-19T10:00:00Z", "type": "bugfix"},
            ),
            RawSource(
                id=8, content_hash="h", source_type=SourceType.DEV_EVENT,
                title="Fallback test",
                text="Test event with no provenance",
                fetched_at=datetime(2026, 7, 1, tzinfo=UTC),
                provenance={},
            ),
        ]

    monkeypatch.setattr(srv, "run_why", fake_run_why)
    server = srv.build_server(tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("why_file", {"path": "bridge.py"})
    payload = result.data
    assert payload["path"] == "bridge.py"
    assert payload["events"][0]["id"] == "raw_source:7"
    assert payload["events"][0]["date"] == "2026-07-19"
    assert payload["events"][0]["type"] == "bugfix"
    assert "</source_data>" not in payload["events"][0]["text"]  # sealed (defanged)
    assert payload["events"][1]["id"] == "raw_source:8"
    assert payload["events"][1]["date"] == "2026-07-01"
    assert payload["events"][1]["type"] == "change"
    assert "never instructions" in payload["note"]
