import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from payment_service.api.auth import validate_key
from payment_service.api.schemas import PaymentCreate


@pytest.mark.parametrize("amount", ["0", "-1", "10000000000000000", "1.001", "NaN", 10])
def test_invalid_amount(amount):
    with pytest.raises(ValidationError):
        PaymentCreate(amount=amount, currency="RUB", webhook_url="https://example.com")


@pytest.mark.parametrize("amount", ["0.01", "9999999999999999.99"])
def test_valid_amount(amount):
    assert (
        PaymentCreate(amount=amount, currency="USD", webhook_url="https://example.com").amount > 0
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"currency": "rub"},
        {"currency": "GBP"},
        {"description": "x" * 501},
        {"metadata": []},
        {"metadata": {"x": "a" * 17000}},
        {"webhook_url": None},
    ],
)
def test_invalid_fields(fields):
    values = {"amount": "1", "currency": "RUB", "webhook_url": "https://example.com", **fields}
    with pytest.raises(ValidationError):
        PaymentCreate(**values)


@pytest.mark.parametrize("key", [None, " ", "x" * 256, "é", "line\nbreak"])
def test_invalid_key(key):
    with pytest.raises(HTTPException):
        validate_key(key)


def test_trimmed_key():
    assert validate_key(" abc ") == "abc"
