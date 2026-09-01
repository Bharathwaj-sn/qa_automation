from fastapi import APIRouter

from data_health_monitor.api.v1.routers import databricks, metadata, payor_config, qa, test_cases

router = APIRouter(prefix="/api/v1")
router.include_router(databricks.router)
router.include_router(metadata.router)
router.include_router(test_cases.router)
router.include_router(payor_config.router)
router.include_router(qa.router)