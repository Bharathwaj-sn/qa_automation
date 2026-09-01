from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from data_health_monitor.api.dependencies import (
    get_databricks_model_serving_service,
    get_databricks_service,
    get_genie_context_service,
    get_genie_service,
    get_genie_space_coordinator,
    get_litellm_service,
    get_metadata_service,
    get_payor_config_service,
    get_qa_context_service,
    get_sql_service,
    get_test_case_service,
    get_validation_sql_service,
)
from data_health_monitor.api.genie_prompt import sql_generation_message
from data_health_monitor.config import get_settings
from data_health_monitor.models.genie import GenieConversationMessageRequest, GenieSQLGeneration, GenieSerializedSpace, GenieSpace
from data_health_monitor.models.llm import LLMRequest, LLMResponse
from data_health_monitor.models.metadata import MetadataRefreshRequest
from data_health_monitor.models.model_serving import ModelServingRequest, ModelServingResponse
from data_health_monitor.models.payor_config import PayorConfig
from data_health_monitor.models.qa_context import QAContext, QAContextRequest
from data_health_monitor.models.test_case import TestCase, TestCaseCreate
from data_health_monitor.models.validation_sql import TestCaseResult, ValidationSQL, ValidationSQLCreate
from data_health_monitor.services.databricks_service import DatabricksService
from data_health_monitor.services.databricks_model_serving_service import (
    DatabricksModelServingError,
    DatabricksModelServingService,
)
from data_health_monitor.services.databricks_sql_service import DatabricksSQLExecutionError, DatabricksSQLService
from data_health_monitor.services.genie_context_service import GenieContextError, GenieContextService
from data_health_monitor.services.genie_service import GenieError, GenieService
from data_health_monitor.services.genie_space_coordinator import GenieSpaceConfigurationError, GenieSpaceCoordinator
from data_health_monitor.services.metadata_service import MetadataService
from data_health_monitor.services.litellm_service import LLMExecutionError, LiteLLMService
from data_health_monitor.services.payor_config_service import (
    DuplicatePayorConfigError,
    PayorConfigNotFoundError,
    PayorConfigService,
)
from data_health_monitor.services.qa_context_service import (
    QAContextExpectedTableMissingError,
    QAContextMetadataSnapshotNotFoundError,
    QAContextMetadataTableNotFoundError,
    QAContextService,
    QAContextTableMismatchError,
    QAContextTestCaseNotFoundError,
)
from data_health_monitor.services.test_case_service import (
    DuplicateTestCaseError,
    TestCaseNotFoundError,
    TestCaseService,
)
from data_health_monitor.services.validation_sql_service import ValidationSQLNotFoundError, ValidationSQLService

router = APIRouter(prefix="/api/databricks")
metadata_router = APIRouter(prefix="/api")


def _error_detail(message: str, error: Exception) -> str:
    raw_error = error
    while raw_error.__cause__:
        raw_error = raw_error.__cause__
    if get_settings().app_debug:
        return f"{message} Raw error: {raw_error}"
    return message


@router.get("/whoami")
def whoami(
    service: Annotated[DatabricksService, Depends(get_databricks_service)],
):
    try:
        return service.get_current_user()
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error_detail("Databricks authentication failed or no active user session is available.", exc),
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
            detail=_error_detail("Databricks authentication is not configured or is invalid.", exc),
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
            detail=_error_detail("Unable to load catalogs.", exc),
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
            detail=_error_detail(f"Catalog '{catalog_name}' not found or inaccessible.", exc),
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
            detail=_error_detail(f"Schema '{schema_name}' in catalog '{catalog_name}' not found or inaccessible.", exc),
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
            detail=_error_detail(f"Table '{table_name}' in schema '{schema_name}' not found or inaccessible.", exc),
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
            detail=_error_detail(f"Unable to refresh metadata for scope '{request.scope_type}'.", exc),
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
            detail=_error_detail("Unable to create test case.", exc),
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
            detail=_error_detail("Unable to retrieve test case.", exc),
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
            detail=_error_detail("Unable to list test cases.", exc),
        ) from exc


@metadata_router.get("/payor-config/{payor}/file-types")
def list_file_types(
    payor: str,
    service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
):
    try:
        return {"file_types": service.list_file_types(payor=payor)}
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_detail("Unable to list file types.", exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_detail("Unable to list file types.", exc),
        ) from exc


@metadata_router.get("/payor-config/{payor}/{file_type}", response_model=PayorConfig)
def get_payor_config(
    payor: str,
    file_type: str,
    service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
):
    try:
        return service.get_config(payor=payor, file_type=file_type)
    except PayorConfigNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicatePayorConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_detail("Unable to retrieve payor configuration.", exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_detail("Unable to retrieve payor configuration.", exc),
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
            detail=_error_detail("Unable to list payors.", exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_detail("Unable to list payors.", exc),
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
            detail=_error_detail("Unable to list payor configurations.", exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_detail("Unable to list payor configurations.", exc),
        ) from exc


@metadata_router.post("/qa/context", response_model=QAContext)
def build_qa_context(
    request: QAContextRequest,
    service: Annotated[QAContextService, Depends(get_qa_context_service)],
):
    try:
        return service.build_context(request)
    except (QAContextTestCaseNotFoundError, PayorConfigNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicatePayorConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (QAContextExpectedTableMissingError, QAContextTableMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except (QAContextMetadataSnapshotNotFoundError, QAContextMetadataTableNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail("Unable to build QA context.", exc),
        ) from exc


@metadata_router.post("/qa/genie-context", response_model=GenieSerializedSpace)
def build_genie_context(
    request: QAContextRequest,
    qa_context_service: Annotated[QAContextService, Depends(get_qa_context_service)],
    genie_context_service: Annotated[GenieContextService, Depends(get_genie_context_service)],
):
    try:
        qa_context = qa_context_service.build_context(request)
        return genie_context_service.build_context(qa_context)
    except (QAContextTestCaseNotFoundError, PayorConfigNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicatePayorConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (QAContextExpectedTableMissingError, QAContextTableMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except (QAContextMetadataSnapshotNotFoundError, QAContextMetadataTableNotFoundError, GenieContextError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail("Unable to build Genie context.", exc),
        ) from exc


@metadata_router.post("/qa/genie-space", response_model=GenieSQLGeneration)
def apply_genie_context(
    request: QAContextRequest,
    qa_context_service: Annotated[QAContextService, Depends(get_qa_context_service)],
    genie_context_service: Annotated[GenieContextService, Depends(get_genie_context_service)],
    genie_space_coordinator: Annotated[GenieSpaceCoordinator, Depends(get_genie_space_coordinator)],
):
    try:
        qa_context = qa_context_service.build_context(request)
        serialized_space = genie_context_service.build_context(qa_context)
        return genie_space_coordinator.generate_sql(
            serialized_space,
            sql_generation_message(qa_context),
        )
    except (QAContextTestCaseNotFoundError, PayorConfigNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicatePayorConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (QAContextExpectedTableMissingError, QAContextTableMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except (QAContextMetadataSnapshotNotFoundError, QAContextMetadataTableNotFoundError, GenieContextError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GenieSpaceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GenieError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(str(exc), exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail("Unable to create or update Genie space.", exc),
        ) from exc


@metadata_router.post("/qa/genie/conversations/{conversation_id}/messages", response_model=GenieSQLGeneration)
def continue_genie_conversation(
    conversation_id: str,
    request: GenieConversationMessageRequest,
    genie_space_coordinator: Annotated[GenieSpaceCoordinator, Depends(get_genie_space_coordinator)],
):
    try:
        return genie_space_coordinator.continue_conversation(conversation_id, request.content)
    except GenieSpaceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GenieError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(str(exc), exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail("Unable to continue Genie conversation.", exc),
        ) from exc


@metadata_router.post("/qa/validation-sql", response_model=ValidationSQL)
def save_validation_sql(
    request: ValidationSQLCreate,
    service: Annotated[ValidationSQLService, Depends(get_validation_sql_service)],
):
    try:
        return service.save(request)
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail("Unable to save validation SQL.", exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail("Unable to save validation SQL.", exc),
        ) from exc


@metadata_router.get("/qa/validation-sql", response_model=list[ValidationSQL])
def list_validation_sql(
    service: Annotated[ValidationSQLService, Depends(get_validation_sql_service)],
    test_case_id: str | None = None,
):
    try:
        return service.list_saved(test_case_id)
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail("Unable to retrieve saved validation SQL.", exc),
        ) from exc


@metadata_router.post("/qa/validation-sql/{validation_sql_id}/execute", response_model=TestCaseResult)
def execute_validation_sql(
    validation_sql_id: str,
    service: Annotated[ValidationSQLService, Depends(get_validation_sql_service)],
):
    try:
        return service.execute_saved(validation_sql_id)
    except ValidationSQLNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail("Unable to execute saved validation SQL.", exc),
        ) from exc


@metadata_router.get("/genie-space/status")
def get_genie_space_status(
    genie_space_coordinator: Annotated[GenieSpaceCoordinator, Depends(get_genie_space_coordinator)],
):
    return genie_space_coordinator.status()


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
            detail=_error_detail("LLM request failed.", exc),
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
            detail=_error_detail("Databricks model serving request failed.", exc),
        ) from exc


app = APIRouter()
app.include_router(router)
app.include_router(metadata_router)
