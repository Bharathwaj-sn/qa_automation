from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from data_health_monitor.api.dependencies import get_payor_config_service
from data_health_monitor.api.v1.schemas import PayorConfigLookupRequest, PayorLookupRequest
from data_health_monitor.models.payor_config import PayorConfig
from data_health_monitor.services.databricks_sql_service import DatabricksSQLExecutionError
from data_health_monitor.services.payor_config_service import (
    DuplicatePayorConfigError,
    PayorConfigNotFoundError,
    PayorConfigService,
)

router = APIRouter(prefix="/payor-config", tags=["Payor configuration"])


@router.get("/payors")
def list_payors(service: Annotated[PayorConfigService, Depends(get_payor_config_service)]):
    try:
        return {"payors": service.list_payors()}
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list payors.",
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list payors.",
        ) from exc


@router.post("/file-types:lookup")
def list_file_types(
    request: PayorLookupRequest,
    service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
):
    try:
        return {"file_types": service.list_file_types(payor=request.payor)}
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list file types.",
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list file types.",
        ) from exc


@router.post(":lookup", response_model=PayorConfig)
def get_payor_config(
    request: PayorConfigLookupRequest,
    service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
):
    try:
        return service.get_config(payor=request.payor, file_type=request.file_type)
    except PayorConfigNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicatePayorConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve payor configuration.",
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve payor configuration.",
        ) from exc


@router.post(":search", response_model=list[PayorConfig])
def list_payor_configs(
    request: PayorLookupRequest,
    service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
):
    try:
        return service.list_configs(payor=request.payor)
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list payor configurations.",
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list payor configurations.",
        ) from exc