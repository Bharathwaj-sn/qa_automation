from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.batch_execution import BatchExecutionRequest


def test_batch_request_requires_at_least_one_query():
    with pytest.raises(ValidationError):
        BatchExecutionRequest(validation_sql_ids=[])


def test_batch_request_rejects_duplicate_query_ids():
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        BatchExecutionRequest(validation_sql_ids=["validation-1", "validation-1"])


def test_batch_request_preserves_query_order():
    request = BatchExecutionRequest(
        validation_sql_ids=["validation-3", "validation-1", "validation-2"]
    )

    assert request.validation_sql_ids == ["validation-3", "validation-1", "validation-2"]