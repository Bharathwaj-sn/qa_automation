from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI

from app.api.routes import metadata_router, router
from app.config import get_settings
from app.services.genie_service import GenieService
from app.services.genie_space_coordinator import GenieSpaceCoordinator


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.genie_space_lock = Lock()
    app.state.genie_space_id = None
    app.state.genie_space_status = "pending_creation"
    GenieSpaceCoordinator(GenieService(settings=settings), settings, app.state).resolve()
    yield


app = FastAPI(
    title="QA Automation API",
    version="0.1.0",
    debug=get_settings().app_debug,
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(metadata_router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}
