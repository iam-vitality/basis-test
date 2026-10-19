import asyncio
import socket
from unittest.mock import AsyncMock, Mock

import pytest

from payment_service.notifications.client import (
    PinnedResolver,
    WebhookDeliveryError,
    send_webhook,
)
from payment_service.notifications.security import (
    InvalidWebhookUrl,
    allowed_url,
    resolve_allowed,
    signature,
    verify_signature,
)


def test_signature(settings):
    body = b'{"event_id":"one"}'
    signed = signature(body, settings.webhook_secret)
    assert signed.startswith("sha256=")
    assert verify_signature(body, settings.webhook_secret, signed)
    assert not verify_signature(body + b" ", settings.webhook_secret, signed)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://127.0.0.1",
        "https://user:pass@example.com",
        "ftp://example.com",
        "https://example.com/#frag",
        "bad",
    ],
)
def test_invalid_url(settings, url):
    settings.webhook_dev_mode = False
    with pytest.raises(InvalidWebhookUrl):
        allowed_url(url, settings)


def test_dev_url(settings):
    assert allowed_url("http://demo-receiver:8080/webhook", settings) == ("demo-receiver", 8080)
    assert allowed_url("https://example.com", settings) == ("example.com", 443)
    with pytest.raises(InvalidWebhookUrl):
        allowed_url("http://other", settings)


@pytest.mark.asyncio
async def test_resolve_external_and_internal(settings, monkeypatch):
    loop = asyncio.get_running_loop()
    fake = AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 443))])
    monkeypatch.setattr(loop, "getaddrinfo", fake)
    assert (await resolve_allowed("https://example.com", settings))[2] == ["8.8.8.8"]
    fake.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))]
    with pytest.raises(InvalidWebhookUrl):
        await resolve_allowed("https://example.com", settings)
    assert (await resolve_allowed("http://demo-receiver/webhook", settings))[2] == ["127.0.0.1"]
    fake.return_value = []
    with pytest.raises(InvalidWebhookUrl):
        await resolve_allowed("https://example.com", settings)
    fake.side_effect = OSError()
    with pytest.raises(InvalidWebhookUrl):
        await resolve_allowed("https://example.com", settings)


@pytest.mark.asyncio
async def test_pinned_resolver():
    resolver = PinnedResolver("example.com", ["8.8.8.8", "2001:4860:4860::8888"])
    answers = await resolver.resolve("example.com", 443)
    assert {answer["host"] for answer in answers} == set(resolver.addresses)
    with pytest.raises(OSError):
        await resolver.resolve("evil.example", 443)
    await resolver.close()


class Response:
    def __init__(self, status):
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


class Session:
    def __init__(self, status):
        self.status = status
        self.post_args = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def post(self, *args, **kwargs):
        self.post_args = args, kwargs
        if self.status == "timeout":
            raise TimeoutError
        return Response(self.status)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,success",
    [(200, True), (204, True), (299, True), (301, False), (500, False), ("timeout", False)],
)
async def test_send_webhook(settings, monkeypatch, status, success):
    session = Session(status)
    monkeypatch.setattr(
        "payment_service.notifications.client.resolve_allowed",
        AsyncMock(return_value=("example.com", 443, ["8.8.8.8"])),
    )
    monkeypatch.setattr("payment_service.notifications.client.aiohttp.TCPConnector", Mock())
    monkeypatch.setattr(
        "payment_service.notifications.client.aiohttp.ClientSession", Mock(return_value=session)
    )
    body = b"{}"
    if success:
        await send_webhook("https://example.com", body, settings)
    else:
        with pytest.raises(WebhookDeliveryError):
            await send_webhook("https://example.com", body, settings)
    if status != "timeout":
        assert session.post_args[1]["allow_redirects"] is False
        assert session.post_args[1]["headers"]["X-Webhook-Signature"] == signature(
            body, settings.webhook_secret
        )
