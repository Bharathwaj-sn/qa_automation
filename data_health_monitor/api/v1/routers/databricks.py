from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from data_health_monitor.api.dependencies import get_databricks_service
from data_health_monitor.api.v1.schemas import CatalogLookupRequest, SchemaLookupRequest, TableLookupRequest
from data_health_monitor.services.databricks_service import DatabricksService

router = APIRouter(prefix="/databricks", tags=["Databricks"])


@router.get("/whoami")
def whoami(service: Annotated[DatabricksService, Depends(get_databricks_service)]):
    try:
        return service.get_current_user()
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Databricks authentication failed or no active user session is available.",
        ) from exc


@router.get("/catalogs")
def list_catalogs(service: Annotated[DatabricksService, Depends(get_databricks_service)]):
    try:
        return {"catalogs": service.list_catalogs()}
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to load catalogs.",
        ) from exc


@router.post("/schemas:lookup")
def list_schemas(
    request: CatalogLookupRequest,
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        return {"schemas": service.list_schemas(catalog_name=request.catalog_name)}
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog '{request.catalog_name}' not found or inaccessible.",
        ) from exc


@router.post("/schema-objects:lookup")
def list_schema_objects(
    request: SchemaLookupRequest,
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        return service.list_schema_objects(
            catalog_name=request.catalog_name,
            schema_name=request.schema_name,
        ).model_dump()
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema '{request.schema_name}' in catalog '{request.catalog_name}' not found or inaccessible.",
        ) from exc


@router.post("/tables:lookup")
def get_table_metadata(
    request: TableLookupRequest,
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        return service.get_table_metadata(
            catalog_name=request.catalog_name,
            schema_name=request.schema_name,
            table_name=request.table_name,
        ).model_dump()
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Table '{request.table_name}' in schema '{request.schema_name}' not found or inaccessible."
            ),
        ) from exc