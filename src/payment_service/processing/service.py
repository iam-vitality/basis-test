from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime

from payment_service.logging_setup import log_event
from payment_service.payments.domain import Payment
from payment_service.payments.repository import PaymentRepository


async def process_gateway(
    repo: PaymentRepository,
    payment: Payment,
    gateway: Callable[[], Awaitable[bool]],
    now: Callable[[], datetime],
) -> Payment:
    outcome = await gateway()
    updated = replace(payment)
    if outcome:
        updated.finish_gateway(True, now())
    else:
        updated.record_gateway_failure(now())
    saved = await repo.change(payment.payment_id, payment, updated)
    if saved is None:
        raise RuntimeError("payment_missing")
    log_event(
        "gateway_result",
        "gateway",
        payment_id=payment.payment_id,
        status="succeeded" if outcome else "error",
        attempt=saved.gateway_failures + int(outcome),
        error_code=None if outcome else "gateway_declined",
    )
    if saved.status != "pending":
        log_event(
            "payment_transition",
            "gateway",
            payment_id=saved.payment_id,
            event_id=saved.event_id,
            status=saved.status,
        )
    return saved
