import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, LargeBinary, Numeric, String, Text, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from payment_service.infrastructure.db import Base, utc_now
from payment_service.payments.domain import Payment


class PaymentRow(Base):
    __tablename__ = "payments"

    payment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_status: Mapped[str] = mapped_column(String(16), nullable=False, default="not_started")
    gateway_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    webhook_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gateway_next_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    webhook_next_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    webhook_body: Mapped[bytes | None] = mapped_column(LargeBinary)
    dlq_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


FIELDS = tuple(Payment.__dataclass_fields__)


def to_domain(row: PaymentRow) -> Payment:
    return Payment(**{field: getattr(row, field) for field in FIELDS})


def to_row(payment: Payment) -> PaymentRow:
    return PaymentRow(**{field: getattr(payment, field) for field in FIELDS})


def copy_to_row(payment: Payment, row: PaymentRow) -> None:
    for field in FIELDS:
        setattr(row, field, getattr(payment, field))


class SqlAlchemyPaymentRepository:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def by_key(self, key: str) -> Payment | None:
        async with self.factory() as session:
            row = await session.scalar(select(PaymentRow).where(PaymentRow.idempotency_key == key))
            return to_domain(row) if row is not None else None

    async def get(self, payment_id: uuid.UUID) -> Payment | None:
        async with self.factory() as session:
            row = await session.get(PaymentRow, payment_id)
            return to_domain(row) if row is not None else None

    async def change(
        self, payment_id: uuid.UUID, expected: Payment, updated: Payment
    ) -> Payment | None:
        async with self.factory() as session, session.begin():
            row = await session.get(PaymentRow, payment_id, with_for_update=True)
            if row is None:
                return None
            current = to_domain(row)
            if current != expected:
                return current
            copy_to_row(updated, row)
            await session.flush()
            return to_domain(row)

    async def mark_dlq_published(self, payment_id: uuid.UUID, at: datetime) -> None:
        async with self.factory() as session, session.begin():
            row = await session.get(PaymentRow, payment_id, with_for_update=True)
            if row is not None and row.dlq_published_at is None:
                row.dlq_published_at = at
