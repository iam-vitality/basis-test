import socket

import aiohttp
from aiohttp.abc import AbstractResolver

from payment_service.config import Settings
from payment_service.notifications.security import InvalidWebhookUrl, resolve_allowed, signature


class WebhookDeliveryError(Exception):
    pass


class PinnedResolver(AbstractResolver):
    def __init__(self, host: str, addresses: list[str]) -> None:
        self.host = host
        self.addresses = addresses

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET) -> list[dict]:
        if host != self.host:
            raise OSError("неожиданный хост")
        return [
            {
                "hostname": host,
                "host": address,
                "port": port,
                "family": socket.AF_INET6 if ":" in address else socket.AF_INET,
                "proto": 0,
                "flags": 0,
            }
            for address in self.addresses
        ]

    async def close(self) -> None:
        return None


async def send_webhook(url: str, body: bytes, settings: Settings) -> None:
    try:
        host, _, addresses = await resolve_allowed(url, settings)
        connector = aiohttp.TCPConnector(
            resolver=PinnedResolver(host, addresses), use_dns_cache=False
        )
        async with aiohttp.ClientSession(
            connector=connector, timeout=aiohttp.ClientTimeout(total=5)
        ) as client:
            async with client.post(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature(body, settings.webhook_secret),
                },
                allow_redirects=False,
            ) as response:
                if not 200 <= response.status < 300:
                    raise WebhookDeliveryError
    except (aiohttp.ClientError, TimeoutError, InvalidWebhookUrl) as exc:
        raise WebhookDeliveryError from exc
