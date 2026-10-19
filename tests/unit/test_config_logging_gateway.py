import json
import logging
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from payment_service.config import Settings
from payment_service.logging_setup import JsonFormatter, configure_logging
from payment_service.processing.gateway import simulate_gateway


@pytest.mark.parametrize("value", ["not-postgres", "postgresql://legacy"])
def test_database_url_rejected(value):
    with pytest.raises(ValidationError):
        Settings(
            database_url=value,
            rabbitmq_url="amqp://local",
            api_key="key",
            webhook_secret="secret",
        )


def test_config_hosts(settings):
    settings.webhook_allowed_hosts = "demo-receiver, OTHER "
    assert settings.allowed_hosts == {"demo-receiver", "other"}


def test_log_drops_secrets(capsys):
    configure_logging()
    record = logging.LogRecord("unit", logging.ERROR, __file__, 1, "secret-message", (), None)
    record.event = "payment_error"
    record.stage = "gateway"
    record.payment_id = "payment-1"
    record.metadata = {"token": "secret-metadata"}
    record.webhook_url = "https://example.com/?token=secret-url"
    record.error_code = "gateway_declined"
    data = json.loads(JsonFormatter().format(record))
    assert data["payment_id"] == "payment-1"
    assert data["error_code"] == "gateway_declined"
    assert "secret" not in json.dumps(data)
    logging.getLogger("unit").error("api-key-secret", extra={"event": "failed", "stage": "unit"})
    assert "api-key-secret" not in capsys.readouterr().out


def test_library_logs_keep_safe_errors_without_info_noise(capsys):
    configure_logging()
    logger = logging.getLogger("uvicorn.error")
    logger.info("started server process")
    logger.warning("https://example.com/?token=secret")
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["error_code"] == "uvicorn_error"
    assert "secret" not in lines[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("random_value,expected", [(0.0, True), (0.899, True), (0.9, False)])
async def test_gateway_random_each_attempt(random_value, expected):
    sleep = AsyncMock()
    uniform = Mock(return_value=3.5)
    outcome = await simulate_gateway(sleep, uniform, Mock(return_value=random_value))
    assert outcome is expected
    sleep.assert_awaited_once_with(3.5)


@pytest.mark.asyncio
async def test_gateway_retries_are_independent():
    values = iter([0.95, 0.1])
    sleep = AsyncMock()
    assert not await simulate_gateway(sleep, Mock(return_value=2), lambda: next(values))
    assert await simulate_gateway(sleep, Mock(return_value=5), lambda: next(values))
    assert [call.args[0] for call in sleep.await_args_list] == [2, 5]
