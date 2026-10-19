import asyncio

from faststream.rabbit import RabbitBroker

from payment_service.config import get_settings
from payment_service.infrastructure.db import create_session_factory
from payment_service.logging_setup import configure_logging
from payment_service.messaging.consumer import run_forever
from payment_service.payments.sqlalchemy import SqlAlchemyPaymentRepository


def main() -> None:
    settings = get_settings()
    configure_logging()
    repo = SqlAlchemyPaymentRepository(create_session_factory(settings.database_url))
    asyncio.run(run_forever(repo, RabbitBroker(settings.rabbitmq_url), settings))


if __name__ == "__main__":
    main()
