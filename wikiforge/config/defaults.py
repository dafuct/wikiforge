"""The default ``config.toml`` template written by ``wiki init``.

Kept as a literal string (not serialized) so comments and layout are stable;
Python's stdlib has no TOML writer. ``{wiki_name}`` is the only substitution.
"""

from __future__ import annotations

DEFAULT_CONFIG_TOML = """\
# wikiforge configuration. Secrets (API keys) are NOT stored here — they come
# from the environment (ANTHROPIC_API_KEY, VOYAGE_API_KEY).

wiki_name = "{wiki_name}"

[models]
cheap = "claude-haiku-4-5"
flagship = "claude-sonnet-5"

[models.tasks]
extract = "cheap"
normalize = "cheap"
summarize = "cheap"
research = "flagship"
synthesize = "flagship"
thesis = "flagship"
query = "flagship"

[pricing."claude-haiku-4-5"]
input = 1.0
output = 5.0

[pricing."claude-sonnet-5"]
input = 3.0
output = 15.0

[pricing."voyage-3.5"]
input = 0.06
output = 0.0

[web_search]
tool_version = "web_search_20260209"
max_uses = 15

[volatility]
LOW = 365
MEDIUM = 90
HIGH = 14

[embedding]
provider = "auto"
voyage_model = "voyage-3.5"
local_model = "BAAI/bge-small-en-v1.5"
dim = 1024
local_dim = 384

[retrieval]
rrf_k = 60
top_k = 12
chunk_tokens = 512
chunk_overlap = 64
rerank_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"

[research]
standard_personas = ["academic", "technical", "applied", "news", "contrarian"]
deep_extra = ["historical", "adjacent_fields", "data_stats"]
max_extra = ["methodological", "speculative"]

[confidence]
count_target = 8
div_target = 6
w_count = 0.35
w_diversity = 0.25
w_recency = 0.25
w_evidence = 0.15
conflict_penalty_per = 0.1
conflict_penalty_cap = 0.4

[llm]
# "api" = Anthropic developer API (needs an API key / credits from console.anthropic.com).
# "subscription" = Claude Code CLI (`claude -p`), uses your Claude subscription (no API credits).
backend = "api"

[capture]
auto = true                # auto-capture when a Claude Code task changed files
summarize = "deferred"     # off | sync | deferred: digests via `capture --flush --digests`
summarize_min_chars = 200  # deferred mode: requests this short need no digest (own summary)
topic_label = "development-log"
max_diff_lines = 200
redact = true

[recall]
enabled = true             # UserPromptSubmit hook: inject wiki excerpts into session (no LLM)
max_excerpts = 3
max_chars = 600
min_similarity = 0.6     # measured on bge-small: unrelated prompts peak ~0.50, relevant ~0.72+
"""
