from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from payment_service.infrastructure.db import check_database
from payment_service.messaging.rabbitmq import check_broker

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    db_ok = await check_database(request.app.state.factory)
    broker_ok = await check_broker(request.app.state.settings.rabbitmq_url)
    return JSONResponse(
        status_code=200 if db_ok and broker_ok else 503,
        content={"status": "ok" if db_ok and broker_ok else "unavailable"},
    )
