from unittest.mock import Mock

from fastapi.testclient import TestClient

from payment_service.demo_receiver import create_app
from payment_service.notifications.security import signature


def test_receiver(settings, monkeypatch):
    logged = Mock()
    monkeypatch.setattr("payment_service.demo_receiver.log_event", logged)
    client = TestClient(create_app(settings))
    body = b'{"payment_id":"p1","event_id":"e1"}'
    with client:
        assert client.post("/webhook", content=body).status_code == 401
        assert (
            client.post(
                "/webhook",
                content=b"{}",
                headers={"X-Webhook-Signature": signature(b"{}", settings.webhook_secret)},
            ).status_code
            == 422
        )
        response = client.post(
            "/webhook",
            content=body,
            headers={"X-Webhook-Signature": signature(body, settings.webhook_secret)},
        )
        assert response.status_code == 200
    assert logged.call_args.kwargs == {"payment_id": "p1", "event_id": "e1", "status": "verified"}
