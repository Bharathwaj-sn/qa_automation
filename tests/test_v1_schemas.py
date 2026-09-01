import pytest
from pydantic import ValidationError

from data_health_monitor.api.v1.schemas import (
    CatalogLookupRequest,
    PayorConfigLookupRequest,
    SchemaLookupRequest,
    TableLookupRequest,
    ValidationSQLSearchRequest,
)
from data_health_monitor.models.databricks_sql import SQLExecutionRequest
from data_health_monitor.models.payor_config import PayorConfig
from data_health_monitor.models.qa_context import QAContextRequest, QAContextSelection, TableContext


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (CatalogLookupRequest, {}),
        (CatalogLookupRequest, {"catalog_name": ""}),
        (SchemaLookupRequest, {"catalog_name": "main"}),
        (TableLookupRequest, {"catalog_name": "main", "schema_name": "qa"}),
        (PayorConfigLookupRequest, {"payor": "ABC"}),
        (PayorConfigLookupRequest, {"payor": "ABC", "file_type": ""}),
        (ValidationSQLSearchRequest, {"test_case_id": ""}),
    ],
)
def test_v1_lookup_models_reject_missing_or_empty_required_values(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_validation_sql_search_allows_an_unfiltered_request():
    assert ValidationSQLSearchRequest().test_case_id is None


def test_schema_name_models_accept_and_serialize_the_schema_alias():
    sql_request = SQLExecutionRequest(
        statement="SELECT 1",
        warehouse_id="warehouse-1",
        schema_name="qa",
    )
    context_request = QAContextRequest.model_validate(
        {
            "test_case_id": "TC1",
            "catalog": "main",
            "schema": "qa",
            "selections": [{"table_name": "members", "payor": "ABC", "file_type": "member"}],
        }
    )
    table_context = TableContext(
        catalog="main",
        schema_name="qa",
        table_name="members",
        metadata={},
        expected_table="members",
        payor_config=PayorConfig(payor="ABC", file_type="member"),
    )

    assert sql_request.schema_name == context_request.schema_name == table_context.schema_name == "qa"
    assert sql_request.model_dump()["schema"] == "qa"
    assert context_request.model_dump()["schema"] == "qa"
    assert table_context.model_dump()["schema"] == "qa"