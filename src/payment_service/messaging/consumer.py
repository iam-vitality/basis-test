import asyncio
import base64
import json
import uuid
from datetime import UTC, datetime

from aio_pika import IncomingMessage
from faststream.rabbit import RabbitBroker

from payment_service.config import Settings
from payment_service.logging_setup import log_event
from payment_service.messaging.rabbitmq import (
    DEAD,
    DELAY_1,
    DELAY_2,
    DLQ,
    NEW,
    declare_topology,
    publish_confirmed,
)
from payment_service.notifications.client import send_webhook
from payment_service.notifications.service import deliver_webhook
from payment_service.payments.domain import Payment
from payment_service.payments.repository import PaymentRepository
from payment_service.processing.gateway import simulate_gateway
from payment_service.processing.service import process_gateway


def decode_payment_id(body: bytes) -> uuid.UUID:
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("payment_id"), str):
        raise ValueError("неверное сообщение")
    return uuid.UUID(payload["payment_id"])


async def route_retry(broker: RabbitBroker, payment_id: uuid.UUID, failures: int) -> None:
    queue = DELAY_1 if failures == 1 else DELAY_2
    await publish_confirmed(broker, {"payment_id": str(payment_id)}, queue.name)
    log_event("retry_scheduled", "consumer", payment_id=payment_id, attempt=failures + 1)


async def route_dead(
    repo: PaymentRepository,
    broker: RabbitBroker,
    payment: Payment | None,
    body: bytes,
    reason: str | None = None,
    payment_id: uuid.UUID | None = None,
) -> None:
    if payment is not None and payment.dlq_published_at is not None:
        return
    reasons = []
    if payment is not None:
        if payment.status == "failed":
            reasons.append("gateway_exhausted")
        if payment.webhook_status == "failed":
            reasons.append("webhook_exhausted")
    if reason:
        reasons.append(reason)
    payload = {
        "payment_id": str(payment.payment_id)
        if payment
        else str(payment_id)
        if payment_id
        else None,
        "stage": ",".join(
            stage
            for stage, code in (("gateway", "gateway_exhausted"), ("webhook", "webhook_exhausted"))
            if code in reasons
        )
        if payment
        else "message",
        "reasons": reasons,
        "gateway_failures": payment.gateway_failures if payment else 0,
        "webhook_failures": payment.webhook_failures if payment else 0,
        "original_body": base64.b64encode(body).decode(),
    }
    await publish_confirmed(broker, payload, DLQ.name, DEAD)
    if payment is not None:
        await repo.mark_dlq_published(payment.payment_id, datetime.now(UTC))
    log_event(
        "sent_to_dlq",
        "consumer",
        payment_id=payment.payment_id if payment else None,
        error_code=",".join(reasons),
    )


async def process_message(
    body: bytes,
    repo: PaymentRepository,
    broker: RabbitBroker,
    settings: Settings,
    gateway=simulate_gateway,
    webhook=send_webhook,
    now=lambda: datetime.now(UTC),
) -> None:
    try:
        payment_id = decode_payment_id(body)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        await route_dead(repo, broker, None, body, "malformed_message")
        return
    payment = await repo.get(payment_id)
    if payment is None:
        await route_dead(repo, broker, None, body, "payment_not_found", payment_id)
        return
    current_time = now()
    if payment.status == "pending":
        if payment.gateway_next_at and payment.gateway_next_at > current_time:
            await route_retry(broker, payment_id, payment.gateway_failures)
            return
        payment = await process_gateway(repo, payment, gateway, now)
        if payment.status == "pending":
            await route_retry(broker, payment_id, payment.gateway_failures)
            return
    if payment.webhook_status == "pending":
        if payment.webhook_next_at and payment.webhook_next_at > now():
            await route_retry(broker, payment_id, payment.webhook_failures)
            return
        payment = await deliver_webhook(repo, payment, settings, webhook, now)
        if payment.webhook_status == "pending":
            await route_retry(broker, payment_id, payment.webhook_failures)
            return
    if payment.status == "failed" or payment.webhook_status == "failed":
        await route_dead(repo, broker, payment, body)


async def handle_delivery(
    message: IncomingMessage,
    repo: PaymentRepository,
    broker: RabbitBroker,
    settings: Settings,
) -> None:
    try:
        await process_message(message.body, repo, broker, settings)
    except Exception:
        log_event("message_retry", "consumer", error_code="infrastructure")
        await asyncio.sleep(1)
        await message.nack(requeue=True)
    else:
        # Подтверждаем исходное сообщение только после подтверждения маршрута повтора или DLQ.
        await message.ack()


async def run_forever(repo: PaymentRepository, broker: RabbitBroker, settings: Settings) -> None:
    while True:
        try:
            async with broker:
                await declare_topology(broker)
                queue = await broker.declare_queue(NEW)
                await queue.channel.set_qos(prefetch_count=1)
                async with queue.iterator() as iterator:
                    async for message in iterator:
                        await handle_delivery(message, repo, broker, settings)
        except Exception:
            log_event("consumer_retry", "consumer", error_code="infrastructure")
            await asyncio.sleep(1)
