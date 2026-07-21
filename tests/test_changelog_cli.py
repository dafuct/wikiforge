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
