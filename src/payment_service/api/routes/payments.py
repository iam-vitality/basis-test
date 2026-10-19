import uuid

from fastapi import APIRouter, Header, HTTPException, Request

from payment_service.api.auth import validate_key
from payment_service.api.schemas import PaymentCreate
from payment_service.notifications.security import InvalidWebhookUrl, resolve_allowed
from payment_service.payments.service import IdempotencyConflict, create_payment, get_payment

router = APIRouter()


def public_payment(payment: object) -> dict:
    return {
        "payment_id": str(payment.payment_id),
        "amount": format(payment.amount, ".2f"),
        "currency": payment.currency,
        "description": payment.description,
        "metadata": payment.metadata_json,
        "status": payment.status,
        "webhook_url": payment.webhook_url,
        "created_at": payment.created_at.isoformat(),
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
        "webhook_status": payment.webhook_status,
    }


@router.post("/api/v1/payments", status_code=202)
async def post_payment(
    request: Request, payload: PaymentCreate, idempotency_key: str | None = Header(None)
):
    key = validate_key(idempotency_key)
    try:
        await resolve_allowed(payload.webhook_url, request.app.state.settings)
    except InvalidWebhookUrl as exc:
        raise HTTPException(422) from exc
    try:
        result = await create_payment(
            request.app.state.repo, request.app.state.creation, key, payload
        )
        return {
            "payment_id": str(result.payment_id),
            "status": result.status,
            "created_at": result.created_at.isoformat(),
        }
    except IdempotencyConflict as exc:
        raise HTTPException(409) from exc


@router.get("/api/v1/payments/{payment_id}")
async def read_payment(request: Request, payment_id: str):
    try:
        parsed = uuid.UUID(payment_id)
    except ValueError as exc:
        raise HTTPException(422) from exc
    payment = await get_payment(request.app.state.repo, parsed)
    if payment is None:
        raise HTTPException(404)
    return public_payment(payment)
