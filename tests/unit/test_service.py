from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from payment_service.api.schemas import PaymentCreate
from payment_service.payments.repository import DuplicateIdempotencyKey
from payment_service.payments.service import (
    IdempotencyConflict,
    canonical_hash,
    create_payment,
)


def test_canonical_hash():
    first = canonical_hash(Decimal("10.0"), "RUB", "", {"a": 1, "b": 2}, "https://a.com")
    second = canonical_hash(Decimal("10.00"), "RUB", "", {"b": 2, "a": 1}, "https://a.com")
    changed = canonical_hash(Decimal("10"), "RUB", "", {"a": 1, "b": 2}, "https://b.com")
    assert first == second
    assert first != changed


@pytest.mark.asyncio
async def test_create_and_repeat(payment):
    repo = AsyncMock()
    repo.by_key.return_value = None
    data = PaymentCreate(amount="10.00", currency="RUB", webhook_url="https://a.com")
    first = await create_payment(repo, repo, "key", data)
    assert first.status == "pending"
    assert repo.create.await_count == 1
    saved, event = repo.create.await_args.args
    assert saved.payment_id == event.payment_id
    saved.status = "succeeded"
    repo.by_key.return_value = saved
    again = await create_payment(repo, repo, "key", data)
    assert again == first
    assert repo.create.await_count == 1
    with pytest.raises(IdempotencyConflict):
        await create_payment(
            repo,
            repo,
            "key",
            PaymentCreate(amount="11", currency="RUB", webhook_url="https://a.com"),
        )


@pytest.mark.asyncio
async def test_concurrent_key_race():
    repo = AsyncMock()
    repo.by_key.side_effect = [None, None]
    repo.create.side_effect = DuplicateIdempotencyKey()
    data = PaymentCreate(amount="10", currency="RUB", webhook_url="https://a.com")
    with pytest.raises(DuplicateIdempotencyKey):
        await create_payment(repo, repo, "key", data)


@pytest.mark.asyncio
async def test_concurrent_same_request():
    repo = AsyncMock()
    data = PaymentCreate(amount="10", currency="RUB", webhook_url="https://a.com")
    repo.by_key.return_value = None
    repo.create.side_effect = DuplicateIdempotencyKey()

    async def existing(_):
        if repo.by_key.await_count == 1:
            return None
        payment = repo.create.await_args.args[0]
        return payment

    repo.by_key.side_effect = existing
    result = await create_payment(repo, repo, "key", data)
    assert result.status == "pending"


def test_gateway_and_webhook_transitions(payment):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    payment.record_gateway_failure(start)
    assert (payment.status, payment.gateway_failures, payment.gateway_next_at) == (
        "pending",
        1,
        start + timedelta(seconds=1),
    )
    payment.record_gateway_failure(start)
    assert payment.gateway_next_at == start + timedelta(seconds=2)
    payment.record_gateway_failure(start)
    assert payment.status == "failed"
    assert payment.processed_at == start
    assert payment.webhook_status == "pending"
    first_body = payment.webhook_body
    first_event = payment.event_id
    payment.record_gateway_failure(start)
    payment.finish_gateway(True, start)
    assert payment.gateway_failures == 3
    assert payment.event_id == first_event
    assert payment.webhook_body == first_body
    payment.record_webhook_failure(start)
    assert payment.webhook_next_at == start + timedelta(seconds=1)
    payment.record_webhook_failure(start)
    assert payment.webhook_next_at == start + timedelta(seconds=2)
    payment.record_webhook_failure(start)
    assert payment.webhook_status == "failed"
    payment.record_webhook_delivered()
    assert payment.webhook_status == "failed"


def test_success_and_delivery(payment):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    payment.finish_gateway(True, at)
    assert payment.status == "succeeded"
    assert b'"amount":"10.00"' in payment.webhook_body
    payment.record_webhook_delivered()
    assert payment.webhook_status == "delivered"
