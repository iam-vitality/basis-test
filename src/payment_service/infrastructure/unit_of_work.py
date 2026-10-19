from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_service.outbox.event import OutboxEvent
from payment_service.outbox.sqlalchemy import to_row as outbox_to_row
from payment_service.payments.domain import Payment
from payment_service.payments.repository import DuplicateIdempotencyKey
from payment_service.payments.sqlalchemy import to_row as payment_to_row


class UnitOfWork:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def create(self, payment: Payment, event: OutboxEvent) -> None:
        try:
            async with self.factory() as session, session.begin():
                session.add(payment_to_row(payment))
                await session.flush()
                session.add(outbox_to_row(event))
        except IntegrityError as exc:
            raise DuplicateIdempotencyKey from exc
