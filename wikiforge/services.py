"""The shared service layer. Both the CLI and the MCP server call these functions.

Milestone 1 provides only ``init_wiki``; later milestones extend this module.
"""

from __future__ import annotations

from pathlib import Path

from wikiforge.activity.recorder import ActivityRecorder
from wikiforge.config.settings import (
    CONFIG_FILENAME,
    load_config,
    write_default_config,
)
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def init_wiki(name: str, home: Path) -> Path:
    """Scaffold a wiki home: config, database, topics dir, and an init log row.

    Idempotent: an existing ``config.toml`` is left untouched; the schema is
    created with ``IF NOT EXISTS`` DDL.
    """
    home.mkdir(parents=True, exist_ok=True)
    (home / "topics").mkdir(exist_ok=True)
    if not (home / CONFIG_FILENAME).exists():
        write_default_config(home, wiki_name=name)
    cfg = load_config(home)

    db = await Database.open(home, dim=cfg.embedding.dim)
    try:
        await db.init_schema()
        recorder = ActivityRecorder(Repository(db))
        await recorder.record("init", {"name": name}, summary=f"created wiki {name!r}")
    finally:
        await db.close()
    return home
