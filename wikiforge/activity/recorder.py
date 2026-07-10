"""Redacted activity logging and the `wiki context` digest renderer."""

from __future__ import annotations

from wikiforge.models.domain import ActivityEntry
from wikiforge.storage.repository import Repository

_SECRET_MARKERS = ("key", "token", "secret", "password", "authorization")


class ActivityRecorder:
    """Records redacted command activity and renders a recent-activity digest."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    @staticmethod
    def redact(args: dict[str, str]) -> dict[str, str]:
        """Mask values whose key names suggest a secret."""
        redacted: dict[str, str] = {}
        for key, value in args.items():
            if any(marker in key.lower() for marker in _SECRET_MARKERS):
                redacted[key] = "***"
            else:
                redacted[key] = value
        return redacted

    async def record(
        self,
        command: str,
        args: dict[str, str] | None = None,
        *,
        topic_id: int | None = None,
        summary: str = "",
    ) -> int:
        """Write one redacted activity row."""
        return await self._repo.insert_activity(
            ActivityEntry(
                command=command,
                args_redacted=self.redact(args or {}),
                topic_id=topic_id,
                summary=summary,
            )
        )

    async def context_digest(self, limit: int = 20) -> str:
        """Render the most recent activity as a CLAUDE.md-style digest (newest first)."""
        entries = await self._repo.recent_activity(limit)
        lines = ["# wikiforge — recent activity", ""]
        for e in entries:
            summary = e.summary or e.command
            lines.append(f"- `{e.ts}` **{e.command}** — {summary}")
        return "\n".join(lines)
