import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.routes.v1 import router
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import make_engine, make_session_factory
from app.schemas.contracts import ErrorOut, HealthOut

logger = logging.getLogger(__name__)


def error_response(status, code, message, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await engine.dispose()

    app = FastAPI(
        title="Expense Sharing Service",
        version="1.0.0",
        lifespan=lifespan,
        description=(
            "A REST API for managing group expenses, splitting costs among members, "
            "tracking balances, and simplifying settlements."
        ),
        responses={code: {"model": ErrorOut} for code in (404, 409, 422, 503)},
    )
    # Shared database objects
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    # Exception Handler (custom for all application errors)
    @app.exception_handler(AppError)
    async def application_error(request: Request, exc: AppError):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):

        details = [
            {"location": list(e["loc"]), "message": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return error_response(422, "validation_error", "Request validation failed", details)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return error_response(409, "integrity_conflict", "Request conflicts with stored data")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error("Database operation failed (%s)", type(exc).__name__)
        return error_response(503, "database_unavailable", "Database operation unavailable")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unhandled application error (%s)", type(exc).__name__)
        return error_response(500, "internal_error", "An unexpected error occurred")

    @app.get("/health", response_model=HealthOut, tags=["Health"])
    async def health():
        return {"status": "ok"}

    @app.get("/ready", response_model=HealthOut, tags=["Health"])
    async def ready():
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise AppError(503, "database_unavailable", "Database is not ready") from error
        return {"status": "ready"}

    # Register API routes
    app.include_router(router)
    return app


app = create_app()
