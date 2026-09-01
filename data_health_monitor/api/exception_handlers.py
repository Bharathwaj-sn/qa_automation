from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

from data_health_monitor.core.logging import get_logger, log_event
from data_health_monitor.api.observability import (
    add_request_id_header,
    get_request_id,
    log_request_completed,
)


def _error_log_level(status_code: int) -> int:
    return logging.ERROR if status_code >= 500 else logging.WARNING


def _request_error_fields(request: Request, status_code: int, error: Exception) -> dict[str, str | int | None]:
    return {
        "request_id": get_request_id(request),
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "error_type": type(error).__name__,
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, error: StarletteHTTPException) -> Response:
        log_event(
            _error_log_level(error.status_code),
            "http_exception",
            **_request_error_fields(request, error.status_code, error),
        )
        return add_request_id_header(request, await http_exception_handler(request, error))

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(request: Request, error: RequestValidationError) -> Response:
        log_event(
            logging.WARNING,
            "request_validation_failed",
            **_request_error_fields(request, 422, error),
        )
        return add_request_id_header(request, await request_validation_exception_handler(request, error))

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, error: Exception) -> Response:
        get_logger().error(
            "unhandled_exception",
            extra={
                "event": "unhandled_exception",
                **_request_error_fields(request, 500, error),
            },
            exc_info=(type(error), error, error.__traceback__),
        )
        response = add_request_id_header(
            request,
            JSONResponse(status_code=500, content={"detail": "Internal server error."}),
        )
        log_request_completed(request, response.status_code)
        return response