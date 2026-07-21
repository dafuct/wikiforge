"""The machine-global peer registry file."""

from __future__ import annotations

from pathlib import Path

from wikiforge.federation.registry import (
    PeerRef,
    load_registry,
    load_registry_report,
    registry_path,
    save_registry,
    slugify_alias,
)


def test_registry_path_honours_xdg(tmp_path: Path) -> None:
    """XDG_CONFIG_HOME wins; otherwise ~/.config."""
    assert registry_path({"XDG_CONFIG_HOME": str(tmp_path)}) == (
        tmp_path / "wikiforge" / "peers.toml"
    )
    assert registry_path({}).parts[-3:] == (".config", "wikiforge", "peers.toml")


def test_missing_file_means_no_peers(tmp_path: Path) -> None:
    """Federation is off by construction until a peer is added."""
    assert load_registry(tmp_path / "absent.toml") == []


def test_round_trip(tmp_path: Path) -> None:
    """What save writes, load reads back — including a path needing escapes."""
    path = tmp_path / "peers.toml"
    peers = [
        PeerRef(alias="global", home=Path("/Users/x/wiki")),
        PeerRef(alias="odd", home=Path('/tmp/a "b"\\c')),
    ]
    save_registry(peers, path)
    assert load_registry(path) == peers


def test_malformed_file_degrades_with_a_reported_reason(tmp_path: Path) -> None:
    """A read path never raises because of the registry; `peers list` explains."""
    path = tmp_path / "peers.toml"
    path.write_text("this is not toml [[[", encoding="utf-8")
    assert load_registry(path) == []
    peers, error = load_registry_report(path)
    assert peers == []
    assert error is not None and "peers.toml" in error


def test_entries_missing_required_keys_are_skipped(tmp_path: Path) -> None:
    """One bad entry must not discard the good ones."""
    path = tmp_path / "peers.toml"
    path.write_text(
        '[[peer]]\nalias = "ok"\nhome = "/a"\n\n[[peer]]\nalias = "nohome"\n',
        encoding="utf-8",
    )
    peers, error = load_registry_report(path)
    assert [p.alias for p in peers] == ["ok"]
    assert error is not None and "nohome" in error


def test_invalid_utf8_degrades_with_a_reported_reason(tmp_path: Path) -> None:
    """Bytes that aren't valid UTF-8 are also a "malformed file", not a crash.

    tomllib.load raises UnicodeDecodeError (not TOMLDecodeError) for this
    case; both are ValueError subclasses and must be caught the same way.
    """
    path = tmp_path / "peers.toml"
    path.write_bytes(b'alias = "\xff\xfe not utf-8"\n')
    assert load_registry(path) == []
    peers, error = load_registry_report(path)
    assert peers == []
    assert error is not None and "peers.toml" in error


def test_slugify_alias() -> None:
    """Aliases come from wiki_name and must be short, lowercase and path-safe."""
    assert slugify_alias("My Wiki") == "my-wiki"
    assert slugify_alias("own-llmwiki") == "own-llmwiki"
    assert slugify_alias("  ???  ") == "peer"
