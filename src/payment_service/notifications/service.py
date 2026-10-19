from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime

from payment_service.config import Settings
from payment_service.logging_setup import log_event
from payment_service.notifications.client import WebhookDeliveryError
from payment_service.payments.domain import Payment
from payment_service.payments.repository import PaymentRepository


async def deliver_webhook(
    repo: PaymentRepository,
    payment: Payment,
    settings: Settings,
    webhook: Callable[[str, bytes, Settings], Awaitable[None]],
    now: Callable[[], datetime],
) -> Payment:
    updated = replace(payment)
    try:
        await webhook(payment.webhook_url, payment.webhook_body, settings)
    except WebhookDeliveryError:
        updated.record_webhook_failure(now())
        error_code = "delivery_failed"
    else:
        updated.record_webhook_delivered()
        error_code = None
    saved = await repo.change(payment.payment_id, payment, updated)
    if saved is None:
        raise RuntimeError("payment_missing")
    log_event(
        "webhook_attempt",
        "webhook",
        payment_id=payment.payment_id,
        event_id=payment.event_id,
        attempt=saved.webhook_failures + int(error_code is None),
        status="delivered" if error_code is None else None,
        error_code=error_code,
    )
    return saved
