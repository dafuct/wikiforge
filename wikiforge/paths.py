"""Resolution of the wiki-home directory."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_home(explicit: str | Path | None = None) -> Path:
    """Return the wiki-home directory.

    Precedence: an explicit path (from ``--home``), then the ``WIKIFORGE_HOME``
    environment variable, then the default ``~/wiki``.
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    env = os.environ.get("WIKIFORGE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / "wiki"
