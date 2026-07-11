# wikiforge — Selectable LLM Backend (API key ↔ Subscription) Design

**Status:** Approved (brainstorming, 2026-07-11)
**Author:** makar + Claude
**Scope:** A post-M6 feature. Lets a wiki run its LLM calls against **either** the Anthropic developer API (API key / credits) **or** a Claude subscription (via the `claude` CLI), selected by one config line.

---

## 1. Goal

wikiforge's intelligence (research, thesis, compile, query, generate) runs on Claude. Today it calls the Anthropic **developer API** through a zero-arg `AsyncAnthropic()`, which bills against an **API credit balance** — separate from a Claude Pro/Max **subscription**. A subscription user with no API credits gets `400: "credit balance is too low"` on every LLM call.

This feature adds a second, config-selectable backend that routes LLM calls through the **`claude` CLI in headless mode** (`claude -p`), which runs under the user's Claude Code subscription — no API credits required. The user picks the backend per-wiki with one config line.

## 2. Scope & non-goals

**In scope**
- A `[llm] backend = "api" | "subscription"` config setting (default `"api"`; backward-compatible).
- An LLM provider factory that builds the selected backend (mirrors the existing embedding factory).
- A new `ClaudeCodeProvider` implementing the existing `LLMProvider` Protocol via `claude -p --output-format json`.
- Wiring the factory into the six `run_*` service call sites.
- Offline tests (injected subprocess runner — no real CLI, no network, no subscription burn).
- README documentation, including the honest caveats.

**Non-goals (YAGNI)**
- No auto-detection from the environment (explicit config only).
- No per-command or per-task backend overrides.
- No new Python dependency (shell out to the existing `claude` binary; not the `claude-agent-sdk` package).
- No change to the retrieval, storage, or embedding layers.
- No attempt to make raw, subscription-billed Messages-API calls — there is no such path; the subscription backend necessarily runs through the Claude Code harness.

## 3. Feasibility (verified 2026-07-11)

- `claude -p "…" --output-format json` returns a completion **under the subscription** (no credit error), confirming the path works.
- `--model haiku|sonnet|opus` selects the model tier; the JSON envelope reports `result` (text), `usage.{input,output,cache_*}_tokens`, and `modelUsage`.
- **Key caveat — harness overhead:** every `claude -p` call loads the Claude Code harness. Even minimized (`--system-prompt` replacing the base prompt, `--allowedTools ""`, `--model haiku`), one trivial call still consumed **~22.6K cache-creation tokens**. This overhead is unavoidable and recurs on every call, so a `wiki research` fan-out (≈10 model calls) burns ~220K tokens of pure overhead against the subscription's usage limits.

The subscription backend is therefore correct for **light/occasional** use (`query`, `generate`, a small `research`) and will exhaust subscription quota quickly on **heavy fan-out**. Having both backends selectable is exactly the point: light/free work on the subscription, heavy/quality work on the API.

## 4. Configuration

New optional section, defaulting to the current behavior:

```toml
[llm]
backend = "api"   # "api" = Anthropic developer API (needs an API key / credits)
                  # "subscription" = Claude Code CLI (`claude -p`), uses your Claude subscription
```

- New `LlmBackend(StrEnum)` in `wikiforge/models/enums.py` — a closed set matching the codebase's `TopicStatus`/`QueryDepth` style: `API = "api"`, `SUBSCRIPTION = "subscription"`.
- New `LlmConfig(BaseModel)` in `wikiforge/config/settings.py` with `backend: LlmBackend = LlmBackend.API`. An unknown TOML value fails validation with a clear Pydantic error naming the allowed set (enum validation).
- New field on `Config`: `llm: LlmConfig = LlmConfig()`. **The default is mandatory** — existing `config.toml` files (including the live `~/wiki`) have no `[llm]` section, and `Config.model_validate` must still succeed and default them to `"api"`.
- Add the `[llm]` block to `DEFAULT_CONFIG_TOML` in `wikiforge/config/defaults.py` so freshly-`init`ed wikis document the option (value `"api"`).

## 5. Factory

New `wikiforge/llm/factory.py`, mirroring `wikiforge/embed/factory.py`:

```python
def build_llm_provider(config: Config, cost_tracker: CostTracker) -> LLMProvider:
    """Return the LLM backend selected by [llm] backend.

    "api" -> AnthropicProvider over a zero-arg AsyncAnthropic() (developer API).
    "subscription" -> ClaudeCodeProvider shelling out to `claude -p` (subscription).
    """
```

- `api` branch: `AnthropicProvider(AsyncAnthropic(), cost_tracker, config)` (imports `AsyncAnthropic` lazily inside the branch).
- `subscription` branch: `ClaudeCodeProvider(config, cost_tracker)`; **fail fast** if the `claude` binary is not on `PATH` (`shutil.which("claude") is None`) with a clear message: *"the 'subscription' LLM backend requires the Claude Code CLI on PATH; install it and run `claude` once to log in, or set [llm] backend = 'api'."* (Mirrors how the Voyage embedder errors without `VOYAGE_API_KEY`.)

## 6. `ClaudeCodeProvider`

`wikiforge/llm/claude_code_provider.py` — implements `complete` and `parse` from the `LLMProvider` Protocol (`wikiforge/llm/provider.py`), unchanged from what `AnthropicProvider` satisfies.

### 6.1 Subprocess boundary (testability)

The provider does **not** call `asyncio.create_subprocess_exec` directly. It takes an injected async runner:

```python
Runner = Callable[[list[str], str], Awaitable[str]]   # (argv, stdin_text) -> stdout (the JSON envelope)

class ClaudeCodeProvider:
    def __init__(self, config: Config, cost_tracker: CostTracker, *, runner: Runner | None = None) -> None:
        self._runner = runner or _default_runner   # real subprocess runner
```

`_default_runner` runs `claude` via `asyncio.create_subprocess_exec(*argv, stdin=PIPE, stdout=PIPE, stderr=PIPE)`, writes `stdin_text`, awaits completion, and returns stdout. Non-zero exit → raise a `ClaudeCodeError` carrying stderr. Tests inject a fake runner that returns canned JSON envelopes — no real `claude`, no network, no subscription usage.

### 6.2 Command construction

- **User prompt** is passed on **stdin** (not as an argv element) to avoid arg-length limits and shell-escaping issues; invoke `claude -p` reading the prompt from stdin.
- **System prompt** replaces the Claude Code default via `--system-prompt` (or `--system-prompt-file` for large prompts), minimizing harness context.
- **Model:** map the configured model id (`config.model_for_task(purpose, tier)`) to a `--model` argument. Claude Code's `--model` accepts the family aliases `haiku`/`sonnet`/`opus`; the provider derives the alias from the configured id by family substring (e.g. `claude-haiku-4-5` → `haiku`, `claude-sonnet-5` → `sonnet`), preserving wikiforge's cheap/flagship tier routing. If no family matches, pass the id through unchanged.
- **Tools:** `--allowedTools ""` (no tools) by default. When `use_web_search=True`, `--allowedTools "WebSearch WebFetch"` so research agents can search — Claude Code runs its own agentic web search (behaviourally different from the API's bounded `web_search` server tool; see caveats).
- **Output:** `--output-format json` — the envelope carries `result`, `usage`, `modelUsage`.

### 6.3 `complete()`

Run the command, parse the JSON envelope, return:
```python
LlmResult(text=env["result"],
          input_tokens=env["usage"]["input_tokens"],
          output_tokens=env["usage"]["output_tokens"],
          model=<configured base model id>)
```
Then record usage via the cost tracker (§6.5).

### 6.4 `parse()`

The CLI has no `output_config.format` equivalent, so structured output is **prompt-and-validate**:
1. Append to the system prompt: *"Respond with ONLY a single JSON object that validates against this JSON Schema. No markdown, no code fences, no prose: `<schema.model_json_schema()>`"*.
2. Run `claude -p` with **no tools**.
3. Extract JSON from `result` — strip ```` ```json ```` fences if present, take the outermost `{ … }` object.
4. `schema.model_validate_json(extracted)`.
5. **On `ValidationError` or JSON-decode failure, retry once** with a corrective user message appending the error text (*"Your previous reply did not validate: <err>. Return only the corrected JSON."*). A second failure raises `ClaudeCodeError`.

Return `ParsedResult(parsed=…, input_tokens=…, output_tokens=…, model=…)` from the successful attempt.

### 6.5 Cost recording

Record via the existing `CostTracker.record(provider="claude-code", model=<configured base id>, input_tokens=…, output_tokens=…, purpose=…, topic_id=…, session_id=…)`. Under the subscription the dollar figure is a **notional API-equivalent estimate** (there is no per-call dollar charge; usage draws on subscription limits). Document this in the README and in a code comment; `wiki stats` therefore shows token usage and an "as-if-API" cost, clearly labelled as an estimate.

## 7. Wiring

`wikiforge/services.py` — every site that constructs `AnthropicProvider(AsyncAnthropic(), <tracker>, cfg)` (six of them at the time of writing) becomes `build_llm_provider(cfg, <tracker>)`. Each site already builds a `CostTracker`; pass it in. The plan enumerates the exact call sites. No other pipeline code changes — the orchestrator, compiler, query service, and generator all depend on the `LLMProvider` Protocol, not the concrete class.

## 8. Error handling & guardrails

- `backend="subscription"` with no `claude` on PATH → clear, actionable error at factory time (§5).
- `claude -p` non-zero exit or unparseable envelope → `ClaudeCodeError` with stderr, surfaced through the CLI's existing `ValueError`→exit-1 handling where those commands already catch it (research/thesis/query/generate/etc.). Confirm each command path surfaces provider errors as a clean message, not a traceback.
- Unknown `backend` value → validation error naming the allowed set.

## 9. Testing strategy (all offline)

- **Config:** default `Config` (no `[llm]`) → `backend == "api"`; a config with `[llm] backend = "subscription"` parses; an unknown value raises.
- **Factory:** `backend="api"` → `AnthropicProvider`; `backend="subscription"` (with a stubbed `which`) → `ClaudeCodeProvider`; subscription with no `claude` on PATH → the clear error.
- **`ClaudeCodeProvider` via injected fake runner:**
  - `complete()` parses a canned envelope → correct `LlmResult` (text/tokens/model); asserts the argv it built (model alias, `--allowedTools ""`, `--output-format json`) and that the user prompt went to stdin.
  - `complete(use_web_search=True)` → argv includes `WebSearch`/`WebFetch` in `--allowedTools`.
  - `parse()` extracts JSON (including a fenced ```` ```json ```` case) and validates against a small Pydantic schema.
  - `parse()` retry: fake runner returns invalid JSON first, valid second → provider retries once and returns the validated object; two failures raise.
  - cost recording: a `CostTracker` over a temp DB records a `claude-code` row with the right tokens.
- No test invokes the real `claude` binary.

## 10. Documentation

README gains a "Choosing an LLM backend" section:
- The `[llm] backend` setting and the two values.
- **API backend:** needs an API key / credits from console.anthropic.com; efficient, hard structured-output guarantee, native web search — the default and the recommended path for heavy use.
- **Subscription backend:** needs the `claude` CLI installed and logged in (Claude Code); no API credits. **Caveats, stated plainly:** ~22K-token Claude Code harness overhead per call → consumes subscription usage limits quickly on research fan-out; structured extraction is prompt-and-validate (slightly less robust than the API's schema guarantee); slower per call; `wiki stats` cost is a notional estimate, not a real charge.
- Guidance: subscription for light/occasional use; API for heavy research or when structured-output robustness matters.

## 11. Assumptions & decisions

- **Default `backend = "api"`** keeps every existing wiki (and the test suite) behaving exactly as before.
- **Shell out to `claude`, not the Agent SDK** — chosen for zero new dependencies and clean `--output-format json` usage data. The `claude` binary is assumed installed and logged in for the subscription backend (verified present on this machine).
- **Model tier preserved** via `--model` family aliases derived from the config's cheap/flagship ids.
- **Structured output is prompt-and-validate** on the subscription path — an accepted, documented reduction in robustness vs the API's `output_config.format`.
- **Notional cost** under subscription — token usage is real and recorded; the dollar figure is an API-equivalent estimate, labelled as such.
- **The subscription path runs through the Claude Code harness** by necessity (there is no raw subscription-billed API); its overhead and agentic web-search behavior are inherent, not defects.
