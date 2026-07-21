"""The changelog service and CLI: git preconditions, exclusion parsing, prose fallback."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from wikiforge.cli.app import app

pytestmark = pytest.mark.asyncio


async def test_changelog_requires_a_git_repository(
    wiki_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wikiforge import services

    await services.init_wiki("T", wiki_home)
    monkeypatch.setattr(services, "repo_root", lambda **kw: "")

    with pytest.raises(ValueError, match="git repository"):
        await services.run_changelog(wiki_home, "a..b")


def test_cli_reports_a_bad_range_as_an_error() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["changelog", "definitely-not-a-ref..HEAD"])

    assert result.exit_code == 1
    assert "Error:" in result.output


async def test_prose_failure_still_prints_the_structured_changelog(
    wiki_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed nicety must not lose the data the user already has."""
    from wikiforge import services
    from wikiforge.ops import changelog as changelog_ops

    await services.init_wiki("T", wiki_home)
    monkeypatch.setattr(services, "repo_root", lambda **kw: "/r")
    monkeypatch.setattr(
        changelog_ops, "resolve_range",
        lambda spec, runner=None: changelog_ops.Range(
            base="aaaa", head="bbbb",
            base_iso="2026-07-20T00:00:00.000000+00:00",
            head_iso="2026-07-20T23:59:59.999999+00:00",
            commits=1, paths=[],
        ),
    )

    async def boom(*args: object, **kwargs: object) -> str:
        raise RuntimeError("no backend")

    monkeypatch.setattr(changelog_ops, "compose_prose", boom)

    out = await services.run_changelog(wiki_home, "a..b", prose=True)

    assert out.startswith("# Changelog:")


async def test_prose_wraps_the_rendered_changelog_in_a_source_data_envelope(
    wiki_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """compose_prose must honor the <source_data> contract _PROSE_SYSTEM promises."""
    from wikiforge import services
    from wikiforge.llm.provider import LlmResult
    from wikiforge.llm.safety import seal_source_data
    from wikiforge.ops import changelog as changelog_ops

    await services.init_wiki("T", wiki_home)
    monkeypatch.setattr(services, "repo_root", lambda **kw: "/r")
    monkeypatch.setattr(
        changelog_ops, "resolve_range",
        lambda spec, runner=None: changelog_ops.Range(
            base="aaaa", head="bbbb",
            base_iso="2026-07-20T00:00:00.000000+00:00",
            head_iso="2026-07-20T23:59:59.999999+00:00",
            commits=1, paths=[],
        ),
    )

    class RecordingLLM:
        def __init__(self) -> None:
            self.user: str | None = None

        async def complete(
            self, purpose: str, system: str, user: str, *, tier: str | None = None,
            use_web_search: bool = False, topic_id: int | None = None,
            session_id: int | None = None,
        ) -> LlmResult:
            self.user = user
            return LlmResult(text="PROSE", input_tokens=1, output_tokens=1, model="fake")

        async def parse(self, *args: object, **kwargs: object) -> object:
            raise NotImplementedError

    llm = RecordingLLM()
    monkeypatch.setattr(services, "build_llm_provider", lambda cfg, tracker: llm)

    plain = await services.run_changelog(wiki_home, "a..b", prose=False)
    out = await services.run_changelog(wiki_home, "a..b", prose=True)

    assert out == "PROSE"
    assert llm.user is not None
    assert llm.user.startswith("<source_data>")
    assert llm.user.endswith("</source_data>")
    assert llm.user == f"<source_data>{seal_source_data(plain)}</source_data>"
