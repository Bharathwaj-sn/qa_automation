import pytest
from pydantic import ValidationError

from data_health_monitor.api.v1.schemas import (
    CatalogLookupRequest,
    PayorConfigLookupRequest,
    SchemaLookupRequest,
    TableLookupRequest,
    ValidationSQLSearchRequest,
)


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