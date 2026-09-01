from __future__ import annotations

import logging
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.responses import Response

from data_health_monitor.core.logging import log_event


_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or _request_id.get()


def add_request_id_header(request: Request, response: Response) -> Response:
    request_id = get_request_id(request)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


def request_duration_ms(request: Request) -> int | None:
    started_at = getattr(request.state, "request_started_at", None)
    if started_at is None:
        return None
    return int((perf_counter() - started_at) * 1000)


def log_request_completed(request: Request, status_code: int) -> None:
    if status_code >= 500:
        level = logging.ERROR
    elif status_code >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO
    log_event(
        level,
        "request_completed",
        request_id=get_request_id(request),
        method=request.method,
        path=request.url.path,
        status_code=status_code,
        duration_ms=request_duration_ms(request),
    )


def register_request_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def observe_request(request: Request, call_next) -> Response:
        request_id = uuid4().hex
        request.state.request_id = request_id
        request.state.request_started_at = perf_counter()
        token = _request_id.set(request_id)
        try:
            response = await call_next(request)
            add_request_id_header(request, response)
            log_request_completed(request, response.status_code)
            return response
        finally:
            _request_id.reset(token)