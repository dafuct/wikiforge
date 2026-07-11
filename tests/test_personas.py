"""Persona registry, injection-defense guard, and thesis stance prompts."""

from __future__ import annotations

import pytest

from wikiforge.research.personas import (
    INJECTION_GUARD,
    RESEARCH_PERSONAS,
    persona_system_prompt,
    thesis_system_prompt,
)


def test_all_ten_research_personas_present() -> None:
    assert set(RESEARCH_PERSONAS) == {
        "academic",
        "technical",
        "applied",
        "news",
        "contrarian",
        "historical",
        "adjacent_fields",
        "data_stats",
        "methodological",
        "speculative",
    }


def test_persona_prompt_embeds_injection_guard_and_focus() -> None:
    prompt = persona_system_prompt("contrarian")
    assert INJECTION_GUARD in prompt
    assert RESEARCH_PERSONAS["contrarian"] in prompt


def test_unknown_persona_raises() -> None:
    with pytest.raises(KeyError):
        persona_system_prompt("nope")


def test_thesis_prompt_carries_stance_and_claim_and_guard() -> None:
    p = thesis_system_prompt("for", "Coffee improves memory")
    assert "Coffee improves memory" in p
    assert INJECTION_GUARD in p
    assert "support" in p.lower()
