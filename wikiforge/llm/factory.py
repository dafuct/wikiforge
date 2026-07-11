"""Config-selecting LLM-provider factory (mirrors embed/factory.py)."""

from __future__ import annotations

import shutil

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import Config
from wikiforge.llm.provider import LLMProvider
from wikiforge.models.enums import LlmBackend


def build_llm_provider(config: Config, cost_tracker: CostTracker) -> LLMProvider:
    """Return the LLM backend selected by ``[llm] backend``.

    ``api`` builds an :class:`~wikiforge.llm.anthropic_provider.AnthropicProvider` over a
    zero-arg ``AsyncAnthropic()`` (Anthropic developer API). ``subscription`` builds a
    :class:`~wikiforge.llm.claude_code_provider.ClaudeCodeProvider` that shells out to the
    ``claude`` CLI (Claude subscription); it raises ``ValueError`` if the ``claude`` binary
    is not on ``PATH``.
    """
    if config.llm.backend is LlmBackend.SUBSCRIPTION:
        from wikiforge.llm.claude_code_provider import ClaudeCodeProvider

        if shutil.which("claude") is None:
            raise ValueError(
                "the 'subscription' LLM backend requires the Claude Code CLI on PATH; "
                "install it and run `claude` once to log in, or set [llm] backend = 'api'."
            )
        return ClaudeCodeProvider(config, cost_tracker)

    from anthropic import AsyncAnthropic

    from wikiforge.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider(AsyncAnthropic(), cost_tracker, config)
