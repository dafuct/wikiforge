"""User feedback: recording judgments against articles/findings and topic lookup."""

from __future__ import annotations

from wikiforge.models.domain import Feedback
from wikiforge.models.enums import FeedbackVerdict
from wikiforge.storage.repository import Repository


class FeedbackStore:
    """Records and retrieves user feedback against compiled articles/findings."""

    def __init__(self, repo: Repository) -> None:
        """Bind this store to an open :class:`~wikiforge.storage.repository.Repository`."""
        self._repo = repo

    async def record(
        self, target_type: str, target_id: int, verdict: FeedbackVerdict, note: str
    ) -> int:
        """Insert a feedback row and return its id."""
        return await self._repo.insert_feedback(
            Feedback(target_type=target_type, target_id=target_id, verdict=verdict, note=note)
        )

    async def for_topic(self, topic_id: int) -> list[Feedback]:
        """Return feedback recorded against a topic's articles.

        Delegates to the M3 :meth:`~wikiforge.storage.repository.Repository.feedback_for_topic`.
        """
        return await self._repo.feedback_for_topic(topic_id)
