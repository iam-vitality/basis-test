import json
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_AMOUNT = Decimal("9999999999999999.99")


class PaymentCreate(BaseModel):
    amount: Decimal
    currency: Literal["RUB", "USD", "EUR"]
    description: str = Field(default="", max_length=500)
    metadata: dict = Field(default_factory=dict)
    webhook_url: str

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: object) -> Decimal:
        if not isinstance(value, str):
            raise ValueError("сумма должна быть строкой")
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("неверная сумма") from exc
        if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
            raise ValueError("сумма вне допустимого диапазона")
        if amount.as_tuple().exponent < -2:
            raise ValueError("не более двух знаков после точки")
        return amount

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict) -> dict:
        try:
            size = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode())
        except (TypeError, ValueError) as exc:
            raise ValueError("метаданные должны быть JSON-объектом") from exc
        if size > 16 * 1024:
            raise ValueError("метаданные слишком велики")
        return value
