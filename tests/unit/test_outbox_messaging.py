from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from payment_service.messaging.rabbitmq import check_broker, declare_topology, publish_confirmed
from payment_service.outbox.publisher import publish_batch, run_forever


@pytest.mark.asyncio
async def test_publish_batch():
    repo = AsyncMock()
    event = Mock(event_id=uuid4(), payment_id=uuid4(), payload={"payment_id": str(uuid4())})
    repo.unpublished.return_value = [event]
    broker = AsyncMock()
    assert await publish_batch(repo, broker) == 1
    assert broker.publish.await_count == 1
    repo.mark_published.assert_awaited_once_with(event.event_id)
    repo.unpublished.return_value = []
    assert await publish_batch(repo, broker) == 0


@pytest.mark.asyncio
async def test_outbox_republishes_after_unconfirmed_delivery():
    repo = AsyncMock()
    event = Mock(event_id=uuid4(), payment_id=uuid4(), payload={"payment_id": str(uuid4())})
    repo.unpublished.return_value = [event]
    broker = AsyncMock()
    broker.publish.return_value = False
    with pytest.raises(RuntimeError):
        await publish_batch(repo, broker)
    repo.mark_published.assert_not_awaited()
    broker.publish.return_value = True
    assert await publish_batch(repo, broker) == 1
    assert broker.publish.await_count == 2
    repo.mark_published.assert_awaited_once_with(event.event_id)


@pytest.mark.asyncio
async def test_unconfirmed_publish():
    broker = AsyncMock()
    broker.publish.return_value = False
    with pytest.raises(RuntimeError):
        await publish_confirmed(broker, {}, "payments.new")


@pytest.mark.asyncio
async def test_topology():
    broker = AsyncMock()
    await declare_topology(broker)
    assert broker.declare_exchange.await_count == 2
    assert broker.declare_queue.await_count == 4
    assert broker.declare_queue.return_value.bind.await_count == 2


@pytest.mark.asyncio
async def test_broker_health(monkeypatch):
    broker = AsyncMock()
    broker.__aenter__.return_value = broker
    broker.ping.return_value = True
    monkeypatch.setattr(
        "payment_service.messaging.rabbitmq.RabbitBroker", Mock(return_value=broker)
    )
    assert await check_broker("amqp://test")
    broker.ping.side_effect = OSError
    assert not await check_broker("amqp://test")


@pytest.mark.asyncio
async def test_outbox_retries(monkeypatch):
    repo = AsyncMock()
    repo.unpublished.side_effect = OSError
    broker = AsyncMock()

    async def stop(_):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        await run_forever(repo, broker, stop)
