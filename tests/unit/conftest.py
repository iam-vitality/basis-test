from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from payment_service.config import Settings
from payment_service.payments.domain import Payment


@pytest.fixture
def settings():
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        rabbitmq_url="amqp://guest:guest@localhost/",
        api_key="test-key",
        webhook_secret="test-secret",
        webhook_dev_mode=True,
        webhook_allowed_hosts="demo-receiver",
    )


@pytest.fixture
def payment():
    return Payment(
        payment_id=uuid4(),
        amount=Decimal("10.00"),
        currency="RUB",
        description="",
        metadata_json={},
        status="pending",
        webhook_url="http://demo-receiver:8080/webhook",
        webhook_status="not_started",
        gateway_failures=0,
        webhook_failures=0,
        idempotency_key="key",
        request_hash="hash",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
