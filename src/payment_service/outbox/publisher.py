import asyncio

from faststream.rabbit import RabbitBroker

from payment_service.logging_setup import log_event
from payment_service.messaging.rabbitmq import NEW, WORK, declare_topology, publish_confirmed
from payment_service.outbox.repository import OutboxRepository


async def publish_batch(repo: OutboxRepository, broker: RabbitBroker) -> int:
    events = await repo.unpublished()
    for event in events:
        await publish_confirmed(broker, event.payload, NEW.name, WORK)
        await repo.mark_published(event.event_id)
        log_event(
            "outbox_published", "outbox", payment_id=event.payment_id, event_id=event.event_id
        )
    return len(events)


async def run_forever(repo: OutboxRepository, broker: RabbitBroker, sleep=asyncio.sleep) -> None:
    while True:
        try:
            async with broker:
                await declare_topology(broker)
                while True:
                    count = await publish_batch(repo, broker)
                    if not count:
                        await sleep(0.5)
        except Exception:
            log_event("publish_retry", "outbox", error_code="infrastructure")
            await sleep(1)
