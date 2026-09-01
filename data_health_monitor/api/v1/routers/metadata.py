from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from data_health_monitor.api.dependencies import get_metadata_service
from data_health_monitor.models.metadata import MetadataRefreshRequest
from data_health_monitor.services.metadata_service import MetadataService

router = APIRouter(tags=["Metadata"])


@router.post("/metadata/refresh")
def refresh_metadata(
    request: MetadataRefreshRequest,
    service: Annotated[MetadataService, Depends(get_metadata_service)],
):
    try:
        return service.refresh(request).model_dump(mode="json")
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to refresh metadata for scope '{request.scope_type}'.",
        ) from exc


@router.get("/metadata")
def get_metadata(service: Annotated[MetadataService, Depends(get_metadata_service)]):
    snapshot = service.get_snapshot()
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No metadata snapshot has been generated yet.",
        )
    return snapshot.model_dump(mode="json")


@router.get("/metadata/summary")
def get_metadata_summary(service: Annotated[MetadataService, Depends(get_metadata_service)]):
    summary = service.get_summary()
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No metadata summary is available yet.",
        )
    return summary.model_dump(mode="json")