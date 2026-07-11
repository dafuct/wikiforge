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
