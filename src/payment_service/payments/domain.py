import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass
class Payment:
    payment_id: uuid.UUID
    amount: Decimal
    currency: str
    description: str
    metadata_json: dict
    status: str
    idempotency_key: str
    request_hash: str
    webhook_url: str
    webhook_status: str
    gateway_failures: int
    webhook_failures: int
    created_at: datetime
    processed_at: datetime | None = None
    gateway_next_at: datetime | None = None
    webhook_next_at: datetime | None = None
    event_id: uuid.UUID | None = None
    webhook_body: bytes | None = None
    dlq_published_at: datetime | None = None

    def finish_gateway(self, succeeded: bool, at: datetime) -> None:
        if self.status != "pending":
            return
        self.status = "succeeded" if succeeded else "failed"
        self.processed_at = at
        self.gateway_next_at = None
        self.webhook_status = "pending"
        self.event_id = uuid.uuid4()
        event = {
            "event_id": str(self.event_id),
            "payment_id": str(self.payment_id),
            "status": self.status,
            "amount": format(self.amount, ".2f"),
            "currency": self.currency,
            "processed_at": at.isoformat(),
        }
        self.webhook_body = json.dumps(event, separators=(",", ":")).encode()

    def record_gateway_failure(self, at: datetime) -> None:
        if self.status != "pending":
            return
        self.gateway_failures += 1
        if self.gateway_failures == 3:
            self.finish_gateway(False, at)
        else:
            self.gateway_next_at = at + timedelta(seconds=self.gateway_failures)

    def record_webhook_failure(self, at: datetime) -> None:
        if self.webhook_status != "pending":
            return
        self.webhook_failures += 1
        if self.webhook_failures == 3:
            self.webhook_status = "failed"
            self.webhook_next_at = None
        else:
            self.webhook_next_at = at + timedelta(seconds=self.webhook_failures)

    def record_webhook_delivered(self) -> None:
        if self.webhook_status == "pending":
            self.webhook_status = "delivered"
            self.webhook_next_at = None
