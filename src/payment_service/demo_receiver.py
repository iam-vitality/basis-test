import json

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from payment_service.config import Settings, get_settings
from payment_service.logging_setup import configure_logging, log_event
from payment_service.notifications.security import verify_signature


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/webhook")
    async def webhook(request: Request, x_webhook_signature: str = Header(default="")):
        body = await request.body()
        if not verify_signature(body, settings.webhook_secret, x_webhook_signature):
            log_event("webhook_received", "receiver", status="invalid_signature")
            return JSONResponse(status_code=401, content={"status": "invalid_signature"})
        try:
            payload = json.loads(body)
            payment_id = payload["payment_id"]
            event_id = payload["event_id"]
        except (ValueError, KeyError, TypeError):
            log_event("webhook_received", "receiver", status="invalid_body")
            return JSONResponse(status_code=422, content={"status": "invalid_body"})
        log_event(
            "webhook_received",
            "receiver",
            payment_id=payment_id,
            event_id=event_id,
            status="verified",
        )
        return {"status": "ok"}

    return app


def run() -> None:
    import uvicorn

    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=8080,
        access_log=False,
        log_config=None,
        log_level="warning",
    )


if __name__ == "__main__":
    run()
