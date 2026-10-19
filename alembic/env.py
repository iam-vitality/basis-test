import asyncio
import os

from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from alembic import context
from payment_service.infrastructure.db import Base
from payment_service.outbox.sqlalchemy import OutboxRow
from payment_service.payments.sqlalchemy import PaymentRow

models = (PaymentRow, OutboxRow)
config = context.config
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
target_metadata = Base.metadata


def do_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section), poolclass=NullPool
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_migrations)
    await engine.dispose()


asyncio.run(run_async())
