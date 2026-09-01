from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from data_health_monitor.api.dependencies import get_test_case_service
from data_health_monitor.models.test_case import TestCaseCreate
from data_health_monitor.services.test_case_service import (
    DuplicateTestCaseError,
    TestCaseNotFoundError,
    TestCaseService,
)

__test__ = False

router = APIRouter(prefix="/test-cases", tags=["Test cases"])


@router.post("")
def create_test_case(
    request: TestCaseCreate,
    service: Annotated[TestCaseService, Depends(get_test_case_service)],
):
    try:
        return service.create_test_case(request).model_dump(mode="json")
    except DuplicateTestCaseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create test case.",
        ) from exc


@router.get("/{test_case_id}")
def get_test_case(
    test_case_id: str,
    service: Annotated[TestCaseService, Depends(get_test_case_service)],
):
    try:
        return service.get_test_case(test_case_id).model_dump(mode="json")
    except TestCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve test case.",
        ) from exc


@router.get("")
def list_test_cases(service: Annotated[TestCaseService, Depends(get_test_case_service)]):
    try:
        return [test_case.model_dump(mode="json") for test_case in service.list_test_cases()]
    except Exception as exc:  # pragma: no cover - simple API-level handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list test cases.",
        ) from exc