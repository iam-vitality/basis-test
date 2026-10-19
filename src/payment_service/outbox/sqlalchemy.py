import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from payment_service.infrastructure.db import Base, utc_now
from payment_service.outbox.event import OutboxEvent


class OutboxRow(Base):
    __tablename__ = "outbox"

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("payments.payment_id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def to_domain(row: OutboxRow) -> OutboxEvent:
    return OutboxEvent(**{field: getattr(row, field) for field in OutboxEvent.__dataclass_fields__})


def to_row(event: OutboxEvent) -> OutboxRow:
    return OutboxRow(**{field: getattr(event, field) for field in OutboxEvent.__dataclass_fields__})


class SqlAlchemyOutboxRepository:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def unpublished(self, limit: int = 50) -> Sequence[OutboxEvent]:
        async with self.factory() as session:
            result = await session.scalars(
                select(OutboxRow)
                .where(OutboxRow.published_at.is_(None))
                .order_by(OutboxRow.created_at)
                .limit(limit)
            )
            return [to_domain(row) for row in result.all()]

    async def mark_published(self, event_id: uuid.UUID) -> None:
        async with self.factory() as session, session.begin():
            row = await session.get(OutboxRow, event_id, with_for_update=True)
            if row is not None and row.published_at is None:
                row.published_at = utc_now()
