"""Read-only access to one peer wiki.

``Database.open`` cannot be reused for a peer: it calls ``mkdir`` and executes
``PRAGMA journal_mode=WAL``, so pointing it at a stale path would *create* a
wiki and write to a database this process does not own. This module opens the
peer's file with SQLite's ``mode=ro``, which refuses every write at the driver
level — including the raw ``conn.execute`` calls ``Repository`` uses for most
of its writes, which no Python-side wrapper could intercept.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, NoReturn, Self

import aiosqlite
import sqlite_vec

from wikiforge.storage.db import DB_FILENAME


class PeerUnavailable(Exception):
    """A peer could not be opened: missing, unreadable, or not a wiki."""


class PeerWriteAttempted(RuntimeError):
    """A write was routed at a peer wiki. Always a programming error."""


class ReadOnlyDatabase:
    """A peer's database, opened read-only, shaped like :class:`Database`.

    Exposes exactly what ``Repository`` consumes — ``conn`` (132 call sites),
    ``lock`` (38), ``execute`` (3), ``fetchone`` and ``fetchall`` — so the
    repository is reused unchanged for reads.
    """

    def __init__(self, conn: aiosqlite.Connection, dim: int) -> None:
        """Wrap an already-open, extension-loaded read-only connection."""
        self._conn = conn
        self._dim = dim
        self._lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        """The underlying aiosqlite connection."""
        return self._conn

    @property
    def lock(self) -> asyncio.Lock:
        """Present for interface parity; a read-only peer has no writer."""
        return self._lock

    @classmethod
    async def open(cls, home: Path, *, dim: int) -> Self:
        """Open ``<home>/wiki.db`` read-only with sqlite-vec loaded.

        ``as_uri()`` percent-encodes the path, so a home containing ``?`` or
        ``#`` cannot corrupt the URI. Nothing is created and no pragma is set
        by this call itself — the peer's journal mode and schema are its own
        business. The first *read* through the returned connection is a
        different story: every wikiforge wiki is created in WAL mode, and
        SQLite's read-only mode still has to create ``-shm``/``-wal``
        bookkeeping files to consult the peer's write-ahead log. That's what
        lets a read here see the peer's freshly-captured, not-yet-checkpointed
        events, which is the whole point of federation — but it means that
        first read fails with ``sqlite3.OperationalError: attempt to write a
        readonly database`` if the peer's directory isn't writable by this
        process, a confusing message for what looks like a plain ``SELECT``.
        ``immutable=1`` would sidestep that, but was tried and rejected: it
        makes SQLite ignore the WAL file outright, so a lightly-used peer with
        any uncheckpointed writes (the common case) would read back empty or
        stale indefinitely — exactly the failure federation exists to avoid.
        The non-writable-directory case is accepted instead, since it's rare
        for this feature's target deployment (one user's own wikis on one
        machine, normally all writable by that user), and it degrades
        gracefully wherever this class is consumed: callers wrap peer reads in
        a broad exception handler and treat a failure as "peer unreachable",
        not a crash.
        """
        db_path = home.expanduser() / DB_FILENAME
        if not db_path.is_file():
            raise PeerUnavailable(f"no wiki database at {db_path}")
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        try:
            conn = await aiosqlite.connect(uri, uri=True)
            conn.row_factory = aiosqlite.Row
            await conn.enable_load_extension(True)
            await conn.load_extension(sqlite_vec.loadable_path())
            await conn.enable_load_extension(False)
        except Exception as exc:  # noqa: BLE001 -- any open failure is "unavailable"
            raise PeerUnavailable(f"cannot open {db_path}: {exc}") from exc
        return cls(conn, dim)

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> NoReturn:
        """Always raises: a peer is never written to."""
        raise PeerWriteAttempted(f"refusing to write to a peer wiki: {sql[:60]!r}")

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        """Run a read query and return the first row, or ``None``."""
        async with self._conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        """Run a read query and return all matching rows."""
        async with self._conn.execute(sql, params) as cur:
            return list(await cur.fetchall())

    async def close(self) -> None:
        """Close the underlying connection."""
        await self._conn.close()
