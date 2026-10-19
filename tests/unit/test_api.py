import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from payment_service.api.app import create_app


def client_for(settings, payment, monkeypatch, *, raise_server_exceptions=False):
    repo = AsyncMock()
    repo.factory = object()
    repo.get.return_value = payment
    monkeypatch.setattr("payment_service.api.routes.payments.resolve_allowed", AsyncMock())
    monkeypatch.setattr(
        "payment_service.api.routes.health.check_database", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "payment_service.api.routes.health.check_broker", AsyncMock(return_value=True)
    )
    return TestClient(
        create_app(settings, repo, repo), raise_server_exceptions=raise_server_exceptions
    ), repo


def headers():
    return {"X-API-Key": "test-key", "Idempotency-Key": "create-001"}


def payload():
    return {
        "amount": "10.00",
        "currency": "RUB",
        "webhook_url": "http://demo-receiver:8080/webhook",
    }


def test_api_create_get_and_errors(settings, payment, monkeypatch):
    client, repo = client_for(settings, payment, monkeypatch)
    repo.by_key.return_value = None
    with client:
        created = client.post("/api/v1/payments", headers=headers(), json=payload())
        assert created.status_code == 202
        assert created.json()["status"] == "pending"
        assert repo.create.await_count == 1
        obtained = client.get(f"/api/v1/payments/{payment.payment_id}", headers=headers())
        assert obtained.status_code == 200
        assert obtained.json()["amount"] == "10.00"
        assert obtained.json()["webhook_status"] == "not_started"
        assert "request_hash" not in obtained.json()
        assert client.get("/api/v1/payments/bad", headers=headers()).status_code == 422
        repo.get.return_value = None
        assert (
            client.get(f"/api/v1/payments/{payment.payment_id}", headers=headers()).status_code
            == 404
        )
        missing = client.post("/api/v1/payments", json=payload())
        assert missing.status_code == 401
        assert set(missing.json()) == {"error"}
        assert client.get("/docs").status_code == 401
        assert client.get("/openapi.json", headers=headers()).status_code == 200


def test_api_bad_requests(settings, payment, monkeypatch, capsys):
    client, repo = client_for(settings, payment, monkeypatch)
    with client:
        assert (
            client.post(
                "/api/v1/payments", headers={"X-API-Key": "test-key"}, json=payload()
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/payments", headers=headers(), json={**payload(), "amount": "0"}
            ).status_code
            == 422
        )
        monkeypatch.setattr(
            "payment_service.api.routes.payments.resolve_allowed",
            AsyncMock(side_effect=ValueError()),
        )
        assert client.post("/api/v1/payments", headers=headers(), json=payload()).status_code == 503
        from payment_service.notifications.security import InvalidWebhookUrl

        monkeypatch.setattr(
            "payment_service.api.routes.payments.resolve_allowed",
            AsyncMock(side_effect=InvalidWebhookUrl()),
        )
        assert client.post("/api/v1/payments", headers=headers(), json=payload()).status_code == 422
        monkeypatch.setattr("payment_service.api.routes.payments.resolve_allowed", AsyncMock())
        repo.by_key.return_value = payment
        payment.request_hash = "other"
        assert client.post("/api/v1/payments", headers=headers(), json=payload()).status_code == 409
        repo.by_key.side_effect = RuntimeError("secret")
        response = client.post("/api/v1/payments", headers=headers(), json=payload())
        assert response.status_code == 503
        assert "secret" not in response.text
        lines = capsys.readouterr().out.splitlines()
        assert any(
            json.loads(line).get("event") == "api_error"
            and json.loads(line).get("error_code") == "internal_error"
            for line in lines
        )
        assert all("secret" not in line for line in lines)


def test_unexpected_api_error_does_not_escape_to_server(settings, payment, monkeypatch):
    client, repo = client_for(settings, payment, monkeypatch, raise_server_exceptions=True)
    repo.get.side_effect = RuntimeError("sensitive database detail")
    with client:
        response = client.get(f"/api/v1/payments/{payment.payment_id}", headers=headers())
    assert response.status_code == 503
    assert "sensitive" not in response.text


@pytest.mark.parametrize(
    "db_ok,broker_ok,status", [(True, True, 200), (True, False, 503), (False, True, 503)]
)
def test_health(settings, payment, monkeypatch, db_ok, broker_ok, status):
    client, _ = client_for(settings, payment, monkeypatch)
    monkeypatch.setattr(
        "payment_service.api.routes.health.check_database", AsyncMock(return_value=db_ok)
    )
    monkeypatch.setattr(
        "payment_service.api.routes.health.check_broker", AsyncMock(return_value=broker_ok)
    )
    with client:
        assert client.get("/health").status_code == status
