from contextlib import asynccontextmanager
import logging
from threading import Lock

from fastapi import FastAPI

from backend.api.exception_handlers import register_exception_handlers
from backend.api.observability import register_request_observability
from backend.api.v1.router import router as v1_router
from backend.config import get_settings
from backend.core.logging import configure_logging, get_logger, log_event
from backend.services.genie_service import GenieService
from backend.services.genie_space_coordinator import GenieSpaceCoordinator


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    log_event(logging.INFO, "application_starting")
    try:
        app.state.genie_space_lock = Lock()
        app.state.genie_space_id = None
        app.state.genie_space_status = "pending_creation"
        GenieSpaceCoordinator(GenieService(settings=settings), settings, app.state).resolve()
    except Exception as error:
        get_logger().error(
            "application_startup_failed",
            extra={"event": "application_startup_failed", "error_type": type(error).__name__},
            exc_info=(type(error), error, error.__traceback__),
        )
        raise
    log_event(logging.INFO, "application_started")
    try:
        yield
    finally:
        log_event(logging.INFO, "application_stopping")


app = FastAPI(
    title="Data Health Monitor API",
    version="0.1.0",
    debug=False,
    lifespan=lifespan,
)
register_request_observability(app)
register_exception_handlers(app)
app.include_router(v1_router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}
