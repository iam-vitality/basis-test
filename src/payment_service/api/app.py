from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from payment_service.api.auth import require_access
from payment_service.api.errors import http_error, translate_errors, validation_error
from payment_service.api.routes.health import router as health_router
from payment_service.api.routes.payments import router as payments_router
from payment_service.config import Settings, get_settings
from payment_service.infrastructure.db import create_session_factory
from payment_service.infrastructure.unit_of_work import UnitOfWork
from payment_service.logging_setup import configure_logging
from payment_service.payments.sqlalchemy import SqlAlchemyPaymentRepository


def create_app(
    settings: Settings | None = None,
    repo: SqlAlchemyPaymentRepository | None = None,
    creation: UnitOfWork | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    factory = None if repo is not None else create_session_factory(settings.database_url)
    repository = repo or SqlAlchemyPaymentRepository(factory)
    creator = creation or UnitOfWork(factory or repository.factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if factory is not None:
            await factory.kw["bind"].dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.repo = repository
    app.state.creation = creator
    app.state.factory = factory or repository.factory
    app.state.settings = settings

    @app.middleware("http")
    async def middleware(request: Request, call_next):
        async def protected(req: Request):
            return await require_access(req, call_next, settings)

        return await translate_errors(request, protected)

    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)
    app.include_router(payments_router)
    app.include_router(health_router)
    return app
