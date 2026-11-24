from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app_logging import get_logger
from database.connection import DatabaseUnavailableError
from interfaces.api_interfaces import ErrorDetail, ErrorResponse

"""
Turns every error into the standard envelope: {"error": {"code": ..., "message": ...}}.

Endpoints raise ApiError for expected problems (bad cursor, run already active...).
Everything else is mapped here so no endpoint ever returns a raw stack trace or a
different error shape:
    invalid query/body           -> 400 invalid_request
    unknown route                -> 404 not_found
    database unreachable         -> 503 database_unavailable
    anything unexpected          -> 500 internal_error (details only in the logs)
"""


logger = get_logger("api")


class ApiError(Exception):
    """An expected error with a status code, a stable code and a user-facing message."""

    def __init__(self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def error_response(status_code: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    """Attaches every handler to the app (called once in main.py)."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError) -> JSONResponse:
        return error_response(error.status_code, error.code, error.message, error.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Name the offending parameters without echoing internal details
        problems = "; ".join(
            f"{'.'.join(str(part) for part in issue['loc'][1:]) or 'request'}: {issue['msg']}"
            for issue in error.errors()
        )
        return error_response(400, "invalid_request", f"The request was not valid ({problems}). Fix it and try again.")

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        if error.status_code == 404:
            return error_response(404, "not_found", "This endpoint does not exist. Check the URL.")
        if error.status_code == 405:
            return error_response(405, "method_not_allowed", "This endpoint does not support that HTTP method.")
        return error_response(error.status_code, "http_error", str(error.detail))

    @app.exception_handler(DatabaseUnavailableError)
    async def handle_database_unavailable(request: Request, error: DatabaseUnavailableError) -> JSONResponse:
        logger.error("Database unavailable", extra={"context": {"path": request.url.path, "error": str(error)}})
        return error_response(503, "database_unavailable",
                              "The database can't be reached right now. Try again in a minute; "
                              "if it keeps happening, check that Postgres is running.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled API error", extra={"context": {"path": request.url.path, "method": request.method}})
        return error_response(500, "internal_error", "Something went wrong on our side. Try again later.")
