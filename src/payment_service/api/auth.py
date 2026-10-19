import hmac

from fastapi import HTTPException, Request

from payment_service.api.errors import error_response
from payment_service.config import Settings


def validate_key(key: str | None) -> str:
    if key is None:
        raise HTTPException(422)
    trimmed = key.strip()
    if not 1 <= len(trimmed) <= 255 or any(not 32 <= ord(char) <= 126 for char in trimmed):
        raise HTTPException(422)
    return trimmed


async def require_access(request: Request, call_next, settings: Settings):
    if (
        request.url.path.startswith("/api/v1/payments")
        or request.url.path.startswith(("/docs", "/redoc"))
        or request.url.path == "/openapi.json"
    ):
        key = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(key, settings.api_key):
            return error_response(401, "unauthorized", "Доступ запрещён")
    return await call_next(request)
