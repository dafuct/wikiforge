"""The machine-global peer registry (``peers.toml``).

Peer entries are absolute, machine-specific paths, and a project's
``.wikiforge/config.toml`` can travel with its repository — so the list of
peers lives outside every wiki, in the user's config directory, and only the
decision to *read* peers is per-wiki (``[federation] enabled``).
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_HEADER = "# wikiforge peer registry — managed by `wiki peers`.\n"
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class PeerRef:
    """One registered peer wiki: a short alias and its home directory."""

    alias: str
    home: Path


def registry_path(env: Mapping[str, str] = os.environ) -> Path:
    """Where the registry lives: ``$XDG_CONFIG_HOME/wikiforge/peers.toml``."""
    base = env.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "wikiforge" / "peers.toml"


def load_registry(path: Path | None = None) -> list[PeerRef]:
    """Registered peers, or ``[]`` when the file is absent or unreadable.

    Deliberately total: every read path in the codebase calls this, and a
    broken registry must degrade to "no peers" rather than break `wiki why`.
    Use :func:`load_registry_report` where the reason should be shown.
    """
    peers, _ = load_registry_report(path)
    return peers


def load_registry_report(path: Path | None = None) -> tuple[list[PeerRef], str | None]:
    """Registered peers plus a human-readable problem description, if any."""
    target = path if path is not None else registry_path()
    if not target.exists():
        return [], None
    try:
        with target.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [], f"{target} is unreadable: {exc}"

    entries = data.get("peer")
    if not isinstance(entries, list):
        return [], f"{target} has no [[peer]] entries"

    peers: list[PeerRef] = []
    skipped: list[str] = []
    for entry in entries:
        alias = entry.get("alias") if isinstance(entry, dict) else None
        home = entry.get("home") if isinstance(entry, dict) else None
        if isinstance(alias, str) and alias and isinstance(home, str) and home:
            peers.append(PeerRef(alias=alias, home=Path(home).expanduser()))
        else:
            skipped.append(str(alias or home or entry))
    error = f"{target}: skipped malformed entries: {', '.join(skipped)}" if skipped else None
    return peers, error


def save_registry(peers: Sequence[PeerRef], path: Path | None = None) -> None:
    """Write the registry. The format is two keys per entry, so it is rendered
    literally — the stdlib has no TOML writer (same constraint as
    ``config/defaults.py``) and this shape is too small to earn a dependency."""
    target = path if path is not None else registry_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    parts = [_HEADER]
    for peer in peers:
        parts.append(
            f'\n[[peer]]\nalias = "{_escape(peer.alias)}"\nhome = "{_escape(str(peer.home))}"\n'
        )
    target.write_text("".join(parts), encoding="utf-8")


def slugify_alias(name: str) -> str:
    """A short, lowercase, path-safe alias derived from a wiki name."""
    slug = _SLUG_STRIP.sub("-", name.strip().lower()).strip("-")
    return slug or "peer"


def _escape(value: str) -> str:
    """Escape a value for a TOML basic string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
