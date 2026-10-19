import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from payment_service.logging_setup import log_event
from payment_service.outbox.event import OutboxEvent
from payment_service.payments.domain import Payment
from payment_service.payments.repository import DuplicateIdempotencyKey, PaymentRepository


class IdempotencyConflict(Exception):
    pass


class PaymentCreation(Protocol):
    async def create(self, payment: Payment, event: OutboxEvent) -> None: ...


@dataclass(frozen=True)
class CreationResult:
    payment_id: uuid.UUID
    status: str
    created_at: datetime


def canonical_hash(
    amount: Decimal, currency: str, description: str, metadata: dict, webhook_url: str
) -> str:
    body = {
        "amount": format(amount, ".2f"),
        "currency": currency,
        "description": description,
        "metadata": metadata,
        "webhook_url": webhook_url,
    }
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def original_response(payment: Payment) -> CreationResult:
    return CreationResult(payment.payment_id, "pending", payment.created_at)


async def create_payment(
    repo: PaymentRepository, creation: PaymentCreation, key: str, data: object
) -> CreationResult:
    fingerprint = canonical_hash(
        data.amount, data.currency, data.description, data.metadata, data.webhook_url
    )
    existing = await repo.by_key(key)
    if existing is not None:
        if existing.request_hash != fingerprint:
            raise IdempotencyConflict
        return original_response(existing)
    payment_id = uuid.uuid4()
    payment = Payment(
        payment_id=payment_id,
        amount=data.amount,
        currency=data.currency,
        description=data.description,
        metadata_json=data.metadata,
        webhook_url=data.webhook_url,
        idempotency_key=key,
        request_hash=fingerprint,
        status="pending",
        webhook_status="not_started",
        gateway_failures=0,
        webhook_failures=0,
        created_at=datetime.now(UTC),
    )
    event = OutboxEvent(
        event_id=uuid.uuid4(),
        payment_id=payment_id,
        event_type="payment.created",
        payload={"payment_id": str(payment_id)},
        created_at=payment.created_at,
    )
    try:
        await creation.create(payment, event)
    except DuplicateIdempotencyKey:
        existing = await repo.by_key(key)
        if existing is None:
            raise
        if existing.request_hash != fingerprint:
            raise IdempotencyConflict from None
        return original_response(existing)
    log_event("payment_created", "api", payment_id=payment_id, event_id=event.event_id)
    return original_response(payment)


async def get_payment(repo: PaymentRepository, payment_id: uuid.UUID) -> Payment | None:
    return await repo.get(payment_id)
