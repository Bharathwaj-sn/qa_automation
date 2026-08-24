from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import get_settings
from app.models.llm import LLMRequest, LLMResponse
from app.models.metadata import MetadataRefreshRequest
from app.models.model_serving import ModelServingRequest, ModelServingResponse
from app.models.payor_config import PayorConfig
from app.models.qa_context import QAContext, QAContextRequest
from app.models.test_case import TestCase, TestCaseCreate
from app.repositories.metadata_repository import MetadataRepository
from app.services.databricks_service import DatabricksService
from app.services.databricks_model_serving_service import (
    DatabricksModelServingError,
    DatabricksModelServingService,
)
from app.services.databricks_sql_service import DatabricksSQLExecutionError, DatabricksSQLService
from app.services.metadata_service import MetadataService
from app.services.litellm_service import LLMExecutionError, LiteLLMService
from app.services.payor_config_service import (
    DuplicatePayorConfigError,
    PayorConfigNotFoundError,
    PayorConfigService,
)
from app.services.qa_context_service import (
    QAContextService,
    QAContextTableNotFoundError,
    QAContextTestCaseNotFoundError,
)
from app.services.test_case_service import (
    DuplicateTestCaseError,
    TestCaseNotFoundError,
    TestCaseService,
)

router = APIRouter(prefix="/api/databricks")
metadata_router = APIRouter(prefix="/api")


def get_databricks_service() -> DatabricksService:
    settings = get_settings()
    return DatabricksService(settings=settings)


def get_metadata_service(
    databricks_service: Annotated[DatabricksService, Depends(get_databricks_service)],
) -> MetadataService:
    return MetadataService(databricks_service=databricks_service, repository=MetadataRepository())


def get_sql_service() -> DatabricksSQLService:
    settings = get_settings()
    return DatabricksSQLService(settings=settings)


def get_litellm_service() -> LiteLLMService:
    return LiteLLMService(settings=get_settings())


def get_databricks_model_serving_service() -> DatabricksModelServingService:
    return DatabricksModelServingService(settings=get_settings())


def get_test_case_service(
    sql_service: Annotated[DatabricksSQLService, Depends(get_sql_service)],
) -> TestCaseService:
    return TestCaseService(sql_service=sql_service)


def get_payor_config_service(
    sql_service: Annotated[DatabricksSQLService, Depends(get_sql_service)],
) -> PayorConfigService:
    return PayorConfigService(sql_service=sql_service)


def get_qa_context_service(
    test_case_service: Annotated[TestCaseService, Depends(get_test_case_service)],
    payor_config_service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
    databricks_service: Annotated[DatabricksService, Depends(get_databricks_service)],
) -> QAContextService:
    return QAContextService(
        test_case_service=test_case_service,
        payor_config_service=payor_config_service,
        databricks_service=databricks_service,
    )


@router.get("/whoami")
def whoami(
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        return service.get_current_user()
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Databricks authentication failed or no active user session is available.",
        ) from exc


@router.get("/whoami")
def who_am_i(
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        me = service.client.current_user.me()
        return {
            "authenticated": True,
            "user_name": getattr(me, "user_name", None) or getattr(me, "email", None),
            "display_name": getattr(me, "display_name", None),
        }
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Databricks authentication is not configured or is invalid.",
        ) from exc


@router.get("/catalogs")
def list_catalogs(
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        return {"catalogs": service.list_catalogs()}
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to load catalogs: {exc}",
        ) from exc


@router.get("/catalogs/{catalog_name}/schemas")
def list_schemas(
    catalog_name: str,
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        return {"schemas": service.list_schemas(catalog_name=catalog_name)}
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog '{catalog_name}' not found or inaccessible.",
        ) from exc


@router.get("/catalogs/{catalog_name}/schemas/{schema_name}/objects")
def list_schema_objects(
    catalog_name: str,
    schema_name: str,
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        return service.list_schema_objects(catalog_name=catalog_name, schema_name=schema_name).model_dump()
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema '{schema_name}' in catalog '{catalog_name}' not found or inaccessible.",
        ) from exc


@router.get("/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}")
def get_table_metadata(
    catalog_name: str,
    schema_name: str,
    table_name: str,
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        return service.get_table_metadata(
            catalog_name=catalog_name,
            schema_name=schema_name,
            table_name=table_name,
        ).model_dump()
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' in schema '{schema_name}' not found or inaccessible.",
        ) from exc


@metadata_router.post("/metadata/refresh")
def refresh_metadata(
    request: MetadataRefreshRequest,
    service: Annotated[MetadataService, Depends(get_metadata_service)],
):
    try:
        snapshot = service.refresh(request)
        return snapshot.model_dump(mode="json")
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to refresh metadata for scope '{request.scope_type}': {exc}",
        ) from exc


@metadata_router.get("/metadata")
def get_metadata(
    service: Annotated[MetadataService, Depends(get_metadata_service)],
):
    snapshot = service.get_snapshot()
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No metadata snapshot has been generated yet.",
        )
    return snapshot.model_dump(mode="json")


@metadata_router.get("/metadata/summary")
def get_metadata_summary(
    service: Annotated[MetadataService, Depends(get_metadata_service)],
):
    summary = service.get_summary()
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No metadata summary is available yet.",
        )
    return summary.model_dump(mode="json")


@metadata_router.post("/test-cases")
def create_test_case(
    test_case: TestCaseCreate,
    service: Annotated[TestCaseService, Depends(get_test_case_service)],
):
    try:
        created = service.create_test_case(test_case)
        return created.model_dump(mode="json")
    except DuplicateTestCaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to create test case: {exc}",
        ) from exc


@metadata_router.get("/test-cases/{test_case_id}")
def get_test_case(
    test_case_id: str,
    service: Annotated[TestCaseService, Depends(get_test_case_service)],
):
    try:
        test_case = service.get_test_case(test_case_id)
        return test_case.model_dump(mode="json")
    except TestCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to retrieve test case: {exc}",
        ) from exc


@metadata_router.get("/test-cases")
def list_test_cases(
    service: Annotated[TestCaseService, Depends(get_test_case_service)],
):
    try:
        test_cases = service.list_test_cases()
        return [tc.model_dump(mode="json") for tc in test_cases]
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to list test cases: {exc}",
        ) from exc


@metadata_router.get("/payor-config/{payor}/{table_name}", response_model=PayorConfig)
def get_payor_config(
    payor: str,
    table_name: str,
    service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
):
    try:
        return service.get_config(payor=payor, table_name=table_name)
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


@metadata_router.get("/payor-config/payors")
def list_payors(
    service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
):
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


@metadata_router.get("/payor-config/{payor}", response_model=list[PayorConfig])
def list_payor_configs(
    payor: str,
    service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
):
    try:
        return service.list_configs(payor=payor)
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


@metadata_router.post("/qa/context", response_model=QAContext)
def build_qa_context(
    request: QAContextRequest,
    service: Annotated[QAContextService, Depends(get_qa_context_service)],
):
    try:
        return service.build_context(request)
    except (QAContextTestCaseNotFoundError, QAContextTableNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to build QA context.",
        ) from exc


@metadata_router.post("/llm/chat", response_model=LLMResponse)
def chat_with_llm(
    request: LLMRequest,
    service: Annotated[LiteLLMService, Depends(get_litellm_service)],
):
    try:
        return service.chat(request)
    except LLMExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM request failed.",
        ) from exc


@metadata_router.post("/model-serving/predict", response_model=ModelServingResponse)
def predict_with_databricks_model_serving(
    request: ModelServingRequest,
    service: Annotated[DatabricksModelServingService, Depends(get_databricks_model_serving_service)],
):
    try:
        return service.predict(request)
    except DatabricksModelServingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Databricks model serving request failed.",
        ) from exc


app = APIRouter()
app.include_router(router)
app.include_router(metadata_router)
