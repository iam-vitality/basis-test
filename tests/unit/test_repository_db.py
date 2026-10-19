from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, call
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from payment_service.infrastructure.db import check_database, create_session_factory
from payment_service.infrastructure.unit_of_work import UnitOfWork
from payment_service.outbox.event import OutboxEvent
from payment_service.outbox.sqlalchemy import (
    OutboxRow,
    SqlAlchemyOutboxRepository,
)
from payment_service.outbox.sqlalchemy import (
    to_domain as outbox_to_domain,
)
from payment_service.outbox.sqlalchemy import (
    to_row as outbox_to_row,
)
from payment_service.payments.repository import DuplicateIdempotencyKey
from payment_service.payments.sqlalchemy import (
    PaymentRow,
    SqlAlchemyPaymentRepository,
    to_domain,
    to_row,
)


def fake_factory():
    session = Mock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value.__aenter__ = AsyncMock()
    session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock()
    session.get = AsyncMock()
    session.scalars = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return Mock(return_value=session), session


@pytest.mark.asyncio
async def test_payment_repository_round_trip(payment):
    factory, session = fake_factory()
    repo = SqlAlchemyPaymentRepository(factory)
    row = to_row(payment)
    assert isinstance(row, PaymentRow)
    assert to_domain(row) == payment
    session.scalar.return_value = row
    assert await repo.by_key("key") == payment
    session.get.return_value = row
    assert await repo.get(payment.payment_id) == payment
    updated = replace(payment)
    updated.finish_gateway(True, datetime.now(UTC))
    saved = await repo.change(payment.payment_id, payment, updated)
    assert saved == updated
    assert to_domain(row) == updated
    await repo.mark_dlq_published(payment.payment_id, datetime.now(UTC))
    assert row.dlq_published_at is not None

    stale = replace(payment)
    stale.record_gateway_failure(datetime.now(UTC))
    assert await repo.change(payment.payment_id, payment, stale) == to_domain(row)
    assert to_domain(row).status == "succeeded"


@pytest.mark.asyncio
async def test_outbox_repository_round_trip(payment):
    factory, session = fake_factory()
    repo = SqlAlchemyOutboxRepository(factory)
    event = OutboxEvent(uuid4(), payment.payment_id, "payment.created", {}, payment.created_at)
    row = outbox_to_row(event)
    assert isinstance(row, OutboxRow)
    assert outbox_to_domain(row) == event
    result = Mock()
    result.all.return_value = [row]
    session.scalars.return_value = result
    assert await repo.unpublished() == [event]
    session.get.return_value = row
    await repo.mark_published(event.event_id)
    assert row.published_at is not None


@pytest.mark.asyncio
async def test_unit_of_work_atomic_creation(payment):
    factory, session = fake_factory()
    event = OutboxEvent(uuid4(), payment.payment_id, "payment.created", {}, payment.created_at)
    await UnitOfWork(factory).create(payment, event)
    assert session.add.call_count == 2
    first, second = (entry.args[0] for entry in session.add.call_args_list)
    assert isinstance(first, PaymentRow)
    assert isinstance(second, OutboxRow)
    assert session.mock_calls.index(call.add(first)) < session.mock_calls.index(call.flush())
    assert session.mock_calls.index(call.flush()) < session.mock_calls.index(call.add(second))
    assert session.begin.return_value.__aexit__.await_count == 1
    assert session.begin.return_value.__aexit__.await_args.args[0] is None


@pytest.mark.asyncio
async def test_unit_of_work_reports_conflicting_key(payment):
    factory, session = fake_factory()
    session.flush.side_effect = IntegrityError("insert", {}, Exception())
    event = OutboxEvent(uuid4(), payment.payment_id, "payment.created", {}, payment.created_at)
    with pytest.raises(DuplicateIdempotencyKey):
        await UnitOfWork(factory).create(payment, event)
    assert session.add.call_count == 1
    assert session.begin.return_value.__aexit__.await_count == 1
    assert session.begin.return_value.__aexit__.await_args.args[0] is IntegrityError


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_when_outbox_fails(payment):
    factory, session = fake_factory()
    event = OutboxEvent(uuid4(), payment.payment_id, "payment.created", {}, payment.created_at)

    def add(row):
        if isinstance(row, OutboxRow):
            raise RuntimeError("outbox_write_failed")

    session.add.side_effect = add
    with pytest.raises(RuntimeError, match="outbox_write_failed"):
        await UnitOfWork(factory).create(payment, event)
    assert session.begin.return_value.__aexit__.await_args.args[0] is RuntimeError


@pytest.mark.asyncio
async def test_database_check_and_factory(monkeypatch):
    factory, session = fake_factory()
    assert await check_database(factory)
    session.execute.side_effect = OSError
    assert not await check_database(factory)
    engine = Mock()
    create_engine = Mock(return_value=engine)
    sessionmaker = Mock(return_value=factory)
    monkeypatch.setattr("payment_service.infrastructure.db.create_async_engine", create_engine)
    monkeypatch.setattr("payment_service.infrastructure.db.async_sessionmaker", sessionmaker)
    assert create_session_factory("postgresql+asyncpg://test") is factory
