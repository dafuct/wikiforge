"""OutputGenerator wraps the article as source_data and returns the model's text."""

from __future__ import annotations

from wikiforge.llm.provider import LlmResult
from wikiforge.models.enums import OutputKind
from wikiforge.output.generator import OutputGenerator


class RecordingLLM:
    def __init__(self) -> None:
        self.system: str | None = None
        self.user: str | None = None

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
    ):
        self.system, self.user = system, user
        return LlmResult(text="GENERATED", input_tokens=0, output_tokens=0, model="m")

    async def parse(self, *a, **k):
        raise NotImplementedError


async def test_generate_wraps_article_and_returns_text() -> None:
    llm = RecordingLLM()
    gen = OutputGenerator(llm)
    out = await gen.generate(
        OutputKind.SUMMARY, topic_title="Rust Async", article_body="Async is cooperative."
    )
    assert out == "GENERATED"
    # Prompt-injection defense: the article body is wrapped as data.
    assert "<source_data>" in llm.user and "</source_data>" in llm.user
    assert "Async is cooperative." in llm.user
    assert "summary" in llm.system.lower()


async def test_each_kind_has_a_distinct_prompt() -> None:
    llm = RecordingLLM()
    gen = OutputGenerator(llm)
    seen: set[str] = set()
    for kind in OutputKind:
        await gen.generate(kind, topic_title="T", article_body="B")
        assert llm.system is not None
        seen.add(llm.system)
    assert len(seen) == len(list(OutputKind))  # no two kinds share a prompt
