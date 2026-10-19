import uuid
from datetime import datetime
from typing import Protocol

from payment_service.payments.domain import Payment


class DuplicateIdempotencyKey(Exception):
    pass


class PaymentRepository(Protocol):
    async def by_key(self, key: str) -> Payment | None: ...

    async def get(self, payment_id: uuid.UUID) -> Payment | None: ...

    async def change(
        self, payment_id: uuid.UUID, expected: Payment, updated: Payment
    ) -> Payment | None: ...

    async def mark_dlq_published(self, payment_id: uuid.UUID, at: datetime) -> None: ...
