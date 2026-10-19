import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class OutboxEvent:
    event_id: uuid.UUID
    payment_id: uuid.UUID
    event_type: str
    payload: dict
    created_at: datetime
    published_at: datetime | None = None
