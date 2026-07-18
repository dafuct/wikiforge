"""Async SQLite wrapper: WAL, sqlite-vec loading, single-writer lock, schema init."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import aiosqlite
import sqlite_vec

DB_FILENAME = "wiki.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """A single-file SQLite database with FTS5 + sqlite-vec, WAL, and a write lock."""

    def __init__(self, conn: aiosqlite.Connection, dim: int) -> None:
        """Wrap an already-open, extension-loaded connection."""
        self._conn = conn
        self._dim = dim
        self._lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        """The underlying aiosqlite connection."""
        return self._conn

    @property
    def lock(self) -> asyncio.Lock:
        """Guards writes — SQLite is single-writer."""
        return self._lock

    @classmethod
    async def open(cls, home: Path, *, dim: int) -> Self:
        """Open (creating if needed) ``<home>/wiki.db`` with extensions loaded."""
        home.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(home / DB_FILENAME)
        conn.row_factory = aiosqlite.Row
        await conn.enable_load_extension(True)
        await conn.load_extension(sqlite_vec.loadable_path())
        await conn.enable_load_extension(False)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.commit()
        return cls(conn, dim)

    async def init_schema(self) -> None:
        """Create all tables and virtual tables idempotently.

        Substitutes the ``{dim}`` placeholder with a plain string replace
        rather than ``str.format`` — the schema contains literal ``'{}'``
        JSON defaults that ``str.format`` would misparse as replacement
        fields.
        """
        ddl = _SCHEMA_PATH.read_text(encoding="utf-8").replace("{dim}", str(self._dim))
        async with self._lock:
            await self._conn.executescript(ddl)
            await self._conn.commit()

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """Run a write statement under the writer lock and commit."""
        async with self._lock:
            await self._conn.execute(sql, params)
            await self._conn.commit()

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        """Run a read query and return the first row, or ``None``."""
        async with self._conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        """Run a read query and return all matching rows."""
        async with self._conn.execute(sql, params) as cur:
            return list(await cur.fetchall())

    async def recreate_vec_table(self) -> None:
        """Drop and re-create ``chunks_vec`` at this database's dimension.

        Used by reindex: a changed embedding provider may change the vector
        dimension, and vec0 fixes it at CREATE time.
        """
        async with self._lock:
            await self._conn.execute("DROP TABLE IF EXISTS chunks_vec")
            await self._conn.execute(
                f"CREATE VIRTUAL TABLE chunks_vec USING vec0(embedding float[{self._dim}])"
            )
            await self._conn.commit()

    async def close(self) -> None:
        """Close the underlying connection."""
        await self._conn.close()

    async def __aenter__(self) -> Self:
        """Enter the async context manager, returning ``self``."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager, closing the connection."""
        await self.close()
