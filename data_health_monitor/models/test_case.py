from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TestCaseCreate(BaseModel):
    pipeline: str
    component: str
    test_scenario: str
    target_object: str
    input_data: str
    validation_check: str
    expected_result: str


class TestCase(BaseModel):
    test_case_id: str
    pipeline: str
    component: str
    test_scenario: str
    target_object: str
    input_data: str
    validation_check: str
    expected_result: str
    status: str = "ACTIVE"
    created_at: datetime | None = None
    updated_at: datetime | None = None
