import asyncio
import hashlib
import hmac
import ipaddress
import socket
from urllib.parse import urlsplit

from payment_service.config import Settings


class InvalidWebhookUrl(ValueError):
    pass


def allowed_url(url: str, settings: Settings) -> tuple[str, int]:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise InvalidWebhookUrl from exc
    if not host or parsed.username or parsed.password:
        raise InvalidWebhookUrl
    if parsed.fragment or parsed.scheme not in {"http", "https"}:
        raise InvalidWebhookUrl
    if parsed.scheme == "http" and not (
        settings.webhook_dev_mode and host.lower() in settings.allowed_hosts
    ):
        raise InvalidWebhookUrl
    return host, port


async def resolve_allowed(url: str, settings: Settings) -> tuple[str, int, list[str]]:
    host, port = allowed_url(url, settings)
    loop = asyncio.get_running_loop()
    try:
        answers = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise InvalidWebhookUrl from exc
    addresses = sorted({answer[4][0] for answer in answers})
    if not addresses:
        raise InvalidWebhookUrl
    internal_allowed = settings.webhook_dev_mode and host.lower() in settings.allowed_hosts
    if not internal_allowed and any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise InvalidWebhookUrl
    return host, port, addresses


def signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, secret: str, supplied: str) -> bool:
    return hmac.compare_digest(signature(body, secret), supplied)
