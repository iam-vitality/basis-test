import uuid
from collections.abc import Sequence
from typing import Protocol

from payment_service.outbox.event import OutboxEvent


class OutboxRepository(Protocol):
    async def unpublished(self, limit: int = 50) -> Sequence[OutboxEvent]: ...

    async def mark_published(self, event_id: uuid.UUID) -> None: ...
