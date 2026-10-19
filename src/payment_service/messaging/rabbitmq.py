import json
from typing import Any

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

WORK = RabbitExchange("payments.work", type=ExchangeType.DIRECT, durable=True)
DEAD = RabbitExchange("payments.dead", type=ExchangeType.DIRECT, durable=True)
NEW = RabbitQueue("payments.new", durable=True)
DELAY_1 = RabbitQueue(
    "payments.retry.1",
    durable=True,
    arguments={
        "x-message-ttl": 1000,
        "x-dead-letter-exchange": WORK.name,
        "x-dead-letter-routing-key": NEW.name,
    },
)
DELAY_2 = RabbitQueue(
    "payments.retry.2",
    durable=True,
    arguments={
        "x-message-ttl": 2000,
        "x-dead-letter-exchange": WORK.name,
        "x-dead-letter-routing-key": NEW.name,
    },
)
DLQ = RabbitQueue("payments.dlq", durable=True)


async def declare_topology(broker: RabbitBroker) -> None:
    work = await broker.declare_exchange(WORK)
    dead = await broker.declare_exchange(DEAD)
    new = await broker.declare_queue(NEW)
    await new.bind(work, routing_key=NEW.name)
    await broker.declare_queue(DELAY_1)
    await broker.declare_queue(DELAY_2)
    dlq = await broker.declare_queue(DLQ)
    await dlq.bind(dead, routing_key=DLQ.name)


async def publish_confirmed(
    broker: RabbitBroker, body: dict[str, Any], queue: str, exchange: RabbitExchange | None = None
) -> None:
    result = await broker.publish(
        json.dumps(body, separators=(",", ":")).encode(),
        queue=queue,
        exchange=exchange,
        mandatory=True,
        persist=True,
        content_type="application/json",
    )
    if result is False or result is None:
        raise RuntimeError("публикация не подтверждена")


async def check_broker(url: str) -> bool:
    try:
        async with RabbitBroker(url) as broker:
            return await broker.ping(timeout=2)
    except Exception:
        return False
