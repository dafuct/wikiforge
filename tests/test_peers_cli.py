"""`wiki peers` — the only surface that writes the registry."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from wikiforge.cli.app import app
from wikiforge.federation.registry import load_registry
from wikiforge.services import init_wiki

runner = CliRunner()


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the machine-global registry at a throwaway XDG config home."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    return tmp_path / "cfg" / "wikiforge" / "peers.toml"


@pytest.mark.asyncio
async def _make_wiki(home: Path, name: str) -> None:
    await init_wiki(name, home)


def test_add_registers_a_peer_with_a_derived_alias(tmp_path: Path, registry: Path) -> None:
    """The default alias comes from the peer's wiki_name, slugified."""
    import asyncio

    peer = tmp_path / "peer"
    asyncio.run(init_wiki("My Wiki", peer))
    local = tmp_path / "local"
    asyncio.run(init_wiki("local", local))

    result = runner.invoke(app, ["peers", "add", str(peer), "--home", str(local)])

    assert result.exit_code == 0, result.output
    assert [p.alias for p in load_registry(registry)] == ["my-wiki"]


def test_add_rejects_a_path_that_is_not_a_wiki(tmp_path: Path, registry: Path) -> None:
    """Validation happens before writing, so the registry never holds junk."""
    import asyncio

    local = tmp_path / "local"
    asyncio.run(init_wiki("local", local))
    result = runner.invoke(app, ["peers", "add", str(tmp_path / "nope"), "--home", str(local)])
    assert result.exit_code != 0
    assert not registry.exists()


def test_add_rejects_the_local_wiki_itself(tmp_path: Path, registry: Path) -> None:
    """Self-federation would double every result (spec §4.3)."""
    import asyncio

    local = tmp_path / "local"
    asyncio.run(init_wiki("local", local))
    result = runner.invoke(app, ["peers", "add", str(local), "--home", str(local)])
    assert result.exit_code != 0
    assert "itself" in result.output.lower()


def test_add_rejects_a_duplicate_home(tmp_path: Path, registry: Path) -> None:
    """The same wiki cannot be registered twice under two aliases."""
    import asyncio

    peer = tmp_path / "peer"
    asyncio.run(init_wiki("peer", peer))
    local = tmp_path / "local"
    asyncio.run(init_wiki("local", local))
    runner.invoke(app, ["peers", "add", str(peer), "--home", str(local)])
    result = runner.invoke(
        app, ["peers", "add", str(peer), "--alias", "other", "--home", str(local)]
    )
    assert result.exit_code != 0
    assert len(load_registry(registry)) == 1


def test_add_rejects_a_control_character_in_an_explicit_alias(
    tmp_path: Path, registry: Path
) -> None:
    """A newline in --alias must not be able to corrupt peers.toml (it would
    otherwise land unescaped in save_registry's output, breaking every future
    `wiki peers list`/`add`/`rm` for every registered peer, not just this one)."""
    import asyncio

    peer = tmp_path / "peer"
    asyncio.run(init_wiki("peer", peer))
    local = tmp_path / "local"
    asyncio.run(init_wiki("local", local))

    result = runner.invoke(
        app, ["peers", "add", str(peer), "--alias", "bad\nalias", "--home", str(local)]
    )

    assert result.exit_code != 0
    assert not registry.exists()


def test_alias_collision_gets_a_suffix(tmp_path: Path, registry: Path) -> None:
    """Two wikis named the same still both register."""
    import asyncio

    a = tmp_path / "a"
    b = tmp_path / "b"
    asyncio.run(init_wiki("Same Name", a))
    asyncio.run(init_wiki("Same Name", b))
    local = tmp_path / "local"
    asyncio.run(init_wiki("local", local))
    runner.invoke(app, ["peers", "add", str(a), "--home", str(local)])
    runner.invoke(app, ["peers", "add", str(b), "--home", str(local)])
    assert [p.alias for p in load_registry(registry)] == ["same-name", "same-name-2"]


def test_rm_removes_by_alias(tmp_path: Path, registry: Path) -> None:
    """`rm` is the per-peer off switch."""
    import asyncio

    peer = tmp_path / "peer"
    asyncio.run(init_wiki("peer", peer))
    local = tmp_path / "local"
    asyncio.run(init_wiki("local", local))
    runner.invoke(app, ["peers", "add", str(peer), "--home", str(local)])
    result = runner.invoke(app, ["peers", "rm", "peer"])
    assert result.exit_code == 0
    assert load_registry(registry) == []


def test_list_shows_compat_and_the_fix(tmp_path: Path, registry: Path) -> None:
    """An unstamped peer is reported with the exact command that fixes it."""
    import asyncio

    peer = tmp_path / "peer"
    asyncio.run(init_wiki("peer", peer))
    local = tmp_path / "local"
    asyncio.run(init_wiki("local", local))
    runner.invoke(app, ["peers", "add", str(peer), "--home", str(local)])

    result = runner.invoke(app, ["peers", "list", "--home", str(local)])

    assert result.exit_code == 0
    assert "unknown" in result.output
    assert "wiki reindex --embeddings" in result.output


def test_list_with_no_peers_explains_how_to_add_one(tmp_path: Path, registry: Path) -> None:
    """An empty registry is the default state and must not read as an error."""
    import asyncio

    local = tmp_path / "local"
    asyncio.run(init_wiki("local", local))
    result = runner.invoke(app, ["peers", "list", "--home", str(local)])
    assert result.exit_code == 0
    assert "wiki peers add" in result.output
