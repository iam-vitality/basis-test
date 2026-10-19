import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from payment_service.logging_setup import log_event


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


async def translate_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        code = "database_error" if isinstance(exc, SQLAlchemyError) else "internal_error"
        log_event("api_error", "api", level=logging.ERROR, error_code=code)
        return error_response(503, "service_unavailable", "Сервис временно недоступен")


async def validation_error(_: Request, __: RequestValidationError):
    return error_response(422, "validation_error", "Неверные данные запроса")


async def http_error(_: Request, exc: HTTPException):
    codes = {404: "not_found", 409: "idempotency_conflict", 422: "validation_error"}
    return error_response(
        exc.status_code, codes.get(exc.status_code, "request_error"), "Запрос отклонён"
    )
