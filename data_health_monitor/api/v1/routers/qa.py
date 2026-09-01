from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from data_health_monitor.api.dependencies import (
    get_genie_context_service,
    get_genie_space_coordinator,
    get_qa_context_service,
    get_validation_sql_service,
)
from data_health_monitor.api.genie_prompt import sql_generation_message
from data_health_monitor.api.v1.schemas import ValidationSQLSearchRequest
from data_health_monitor.models.genie import GenieConversationMessageRequest, GenieSQLGeneration, GenieSerializedSpace
from data_health_monitor.models.qa_context import QAContext, QAContextRequest
from data_health_monitor.models.validation_sql import TestCaseResult, ValidationSQL, ValidationSQLCreate
from data_health_monitor.services.databricks_sql_service import DatabricksSQLExecutionError
from data_health_monitor.services.genie_context_service import GenieContextError, GenieContextService
from data_health_monitor.services.genie_service import GenieError
from data_health_monitor.services.genie_space_coordinator import GenieSpaceConfigurationError, GenieSpaceCoordinator
from data_health_monitor.services.payor_config_service import DuplicatePayorConfigError, PayorConfigNotFoundError
from data_health_monitor.services.qa_context_service import (
    QAContextExpectedTableMissingError,
    QAContextMetadataSnapshotNotFoundError,
    QAContextMetadataTableNotFoundError,
    QAContextService,
    QAContextTableMismatchError,
    QAContextTestCaseNotFoundError,
)
from data_health_monitor.services.validation_sql_service import ValidationSQLNotFoundError, ValidationSQLService

router = APIRouter(tags=["Quality assurance"])


@router.post("/qa/context", response_model=QAContext)
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
            detail="Unable to build QA context.",
        ) from exc


@router.post("/qa/genie-context", response_model=GenieSerializedSpace)
def build_genie_context(
    request: QAContextRequest,
    qa_context_service: Annotated[QAContextService, Depends(get_qa_context_service)],
    genie_context_service: Annotated[GenieContextService, Depends(get_genie_context_service)],
):
    try:
        return genie_context_service.build_context(qa_context_service.build_context(request))
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
            detail="Unable to build Genie context.",
        ) from exc


@router.post("/qa/genie-space", response_model=GenieSQLGeneration)
def apply_genie_context(
    request: QAContextRequest,
    qa_context_service: Annotated[QAContextService, Depends(get_qa_context_service)],
    genie_context_service: Annotated[GenieContextService, Depends(get_genie_context_service)],
    genie_space_coordinator: Annotated[GenieSpaceCoordinator, Depends(get_genie_space_coordinator)],
):
    try:
        qa_context = qa_context_service.build_context(request)
        serialized_space = genie_context_service.build_context(qa_context)
        return genie_space_coordinator.generate_sql(serialized_space, sql_generation_message(qa_context))
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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to create or update Genie space.",
        ) from exc


@router.post("/qa/genie/conversations/{conversation_id}/messages", response_model=GenieSQLGeneration)
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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to continue Genie conversation.",
        ) from exc


@router.post("/qa/validation-sql", response_model=ValidationSQL)
def save_validation_sql(
    request: ValidationSQLCreate,
    service: Annotated[ValidationSQLService, Depends(get_validation_sql_service)],
):
    try:
        return service.save(request)
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to save validation SQL.",
        ) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to save validation SQL.",
        ) from exc


@router.post("/qa/validation-sql:search", response_model=list[ValidationSQL])
def list_validation_sql(
    request: ValidationSQLSearchRequest,
    service: Annotated[ValidationSQLService, Depends(get_validation_sql_service)],
):
    try:
        return service.list_saved(request.test_case_id)
    except DatabricksSQLExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to retrieve saved validation SQL.",
        ) from exc


@router.post("/qa/validation-sql/{validation_sql_id}:execute", response_model=TestCaseResult)
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
            detail="Unable to execute saved validation SQL.",
        ) from exc


@router.get("/genie-space/status")
def get_genie_space_status(
    genie_space_coordinator: Annotated[GenieSpaceCoordinator, Depends(get_genie_space_coordinator)],
):
    return genie_space_coordinator.status()