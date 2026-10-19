import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from payment_service.messaging.consumer import handle_delivery, process_message, run_forever
from payment_service.notifications.client import WebhookDeliveryError


class MemoryRepository:
    def __init__(self, payment):
        self.payment = payment

    async def get(self, payment_id):
        return self.payment if payment_id == self.payment.payment_id else None

    async def change(self, payment_id, expected, updated):
        assert payment_id == self.payment.payment_id
        assert expected == self.payment
        for field in self.payment.__dataclass_fields__:
            setattr(self.payment, field, getattr(updated, field))
        return self.payment

    async def mark_dlq_published(self, payment_id, at):
        assert payment_id == self.payment.payment_id
        self.payment.dlq_published_at = at


def body_for(payment):
    return json.dumps({"payment_id": str(payment.payment_id)}).encode()


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [0, 1, 2])
async def test_gateway_success_after_failures(payment, settings, failures):
    repo = MemoryRepository(payment)
    broker = AsyncMock()
    gateway = AsyncMock(return_value=True)
    webhook = AsyncMock()
    at = datetime(2026, 1, 1, tzinfo=UTC)
    payment.gateway_failures = failures
    await process_message(body_for(payment), repo, broker, settings, gateway, webhook, lambda: at)
    assert payment.status == "succeeded"
    assert payment.webhook_status == "delivered"
    assert gateway.await_count == 1
    assert webhook.await_count == 1
    broker.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_three_gateway_errors_and_webhook_errors(payment, settings):
    repo = MemoryRepository(payment)
    broker = AsyncMock()
    gateway = AsyncMock(return_value=False)
    webhook = AsyncMock(side_effect=WebhookDeliveryError)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    for attempt in range(3):
        payment.gateway_next_at = None
        await process_message(
            body_for(payment), repo, broker, settings, gateway, webhook, lambda: at
        )
        assert payment.gateway_failures == attempt + 1
    assert payment.status == "failed"
    assert payment.webhook_failures == 1
    for _ in range(2):
        payment.webhook_next_at = None
        await process_message(
            body_for(payment), repo, broker, settings, gateway, webhook, lambda: at
        )
    assert payment.webhook_status == "failed"
    assert payment.gateway_failures == 3
    assert gateway.await_count == 3
    published = [call.args[0] for call in broker.publish.await_args_list]
    dlq = [json.loads(item) for item in published if b"original_body" in item]
    assert len(dlq) == 1
    assert dlq[0]["reasons"] == ["gateway_exhausted", "webhook_exhausted"]
    assert dlq[0]["stage"] == "gateway,webhook"
    await process_message(body_for(payment), repo, broker, settings, gateway, webhook, lambda: at)
    assert gateway.await_count == 3
    assert webhook.await_count == 3
    assert (
        len([call for call in broker.publish.await_args_list if b"original_body" in call.args[0]])
        == 1
    )


@pytest.mark.asyncio
async def test_duplicate_cannot_skip_delay(payment, settings):
    repo = MemoryRepository(payment)
    broker = AsyncMock()
    gateway = AsyncMock()
    at = datetime(2026, 1, 1, tzinfo=UTC)
    payment.gateway_failures = 1
    payment.gateway_next_at = at + timedelta(seconds=1)
    await process_message(
        body_for(payment), repo, broker, settings, gateway, AsyncMock(), lambda: at
    )
    gateway.assert_not_awaited()
    assert payment.gateway_failures == 1
    assert broker.publish.await_args.kwargs["queue"] == "payments.retry.1"


@pytest.mark.asyncio
async def test_resume_webhook_without_gateway(payment, settings):
    repo = MemoryRepository(payment)
    broker = AsyncMock()
    gateway = AsyncMock()
    webhook = AsyncMock()
    payment.finish_gateway(True, datetime.now(UTC))
    await process_message(body_for(payment), repo, broker, settings, gateway, webhook)
    assert payment.webhook_status == "delivered"
    gateway.assert_not_awaited()
    webhook.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"broken", b"{}"])
async def test_malformed_message(payment, settings, body):
    broker = AsyncMock()
    await process_message(body, MemoryRepository(payment), broker, settings)
    assert broker.publish.await_args.kwargs["queue"] == "payments.dlq"


@pytest.mark.asyncio
async def test_missing_payment(payment, settings):
    broker = AsyncMock()
    repo = MemoryRepository(payment)
    await process_message(
        json.dumps({"payment_id": "00000000-0000-0000-0000-000000000000"}).encode(),
        repo,
        broker,
        settings,
    )
    payload = json.loads(broker.publish.await_args.args[0])
    assert payload["payment_id"] == "00000000-0000-0000-0000-000000000000"


@pytest.mark.asyncio
async def test_ack_after_publish(payment, settings):
    message = AsyncMock(body=body_for(payment))
    repo = MemoryRepository(payment)
    broker = AsyncMock()
    payment.finish_gateway(False, datetime.now(UTC))
    payment.webhook_status = "delivered"
    await handle_delivery(message, repo, broker, settings)
    message.ack.assert_awaited_once()
    assert broker.publish.await_count == 1


@pytest.mark.asyncio
async def test_publish_failure_nacks(payment, settings, monkeypatch):
    message = AsyncMock(body=body_for(payment))
    repo = MemoryRepository(payment)
    broker = AsyncMock()
    broker.publish.side_effect = RuntimeError("broker")
    payment.finish_gateway(False, datetime.now(UTC))
    payment.webhook_status = "delivered"
    monkeypatch.setattr("payment_service.messaging.consumer.asyncio.sleep", AsyncMock())
    await handle_delivery(message, repo, broker, settings)
    message.nack.assert_awaited_once_with(requeue=True)
    message.ack.assert_not_awaited()


@pytest.mark.asyncio
async def test_dlq_confirmed_before_source_ack(payment, settings):
    events = []
    message = AsyncMock(body=body_for(payment))
    broker = AsyncMock()

    async def publish(*args, **kwargs):
        events.append("published")
        return True

    async def acknowledge():
        events.append("acknowledged")

    broker.publish.side_effect = publish
    message.ack.side_effect = acknowledge
    payment.finish_gateway(False, datetime.now(UTC))
    payment.webhook_status = "delivered"
    await handle_delivery(message, MemoryRepository(payment), broker, settings)
    assert events == ["published", "acknowledged"]


@pytest.mark.asyncio
async def test_consumer_prefetch_one(payment, settings):
    broker = AsyncMock()
    broker.__aenter__.return_value = broker
    queue = AsyncMock()
    broker.declare_queue.return_value = queue

    async def messages():
        raise KeyboardInterrupt
        yield

    iterator = Mock()
    iterator.__aenter__ = AsyncMock(return_value=messages())
    iterator.__aexit__ = AsyncMock(return_value=False)
    queue.iterator = Mock(return_value=iterator)
    with pytest.raises(KeyboardInterrupt):
        await run_forever(MemoryRepository(payment), broker, settings)
    queue.channel.set_qos.assert_awaited_once_with(prefetch_count=1)
