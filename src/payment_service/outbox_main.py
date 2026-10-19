import asyncio

from faststream.rabbit import RabbitBroker

from payment_service.config import get_settings
from payment_service.infrastructure.db import create_session_factory
from payment_service.logging_setup import configure_logging
from payment_service.outbox.publisher import run_forever
from payment_service.outbox.sqlalchemy import SqlAlchemyOutboxRepository


def main() -> None:
    settings = get_settings()
    configure_logging()
    repo = SqlAlchemyOutboxRepository(create_session_factory(settings.database_url))
    asyncio.run(run_forever(repo, RabbitBroker(settings.rabbitmq_url)))


if __name__ == "__main__":
    main()
