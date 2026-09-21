from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from backend.api.v1.schemas import (
    CatalogLookupRequest,
    PayorLookupRequest,
    SchemaLookupRequest,
    TableLookupRequest,
    ValidationSQLSearchRequest,
)
from backend.models.databricks import (
    CatalogResponse,
    SchemaObjectsResponse,
    SchemaResponse,
    TableMetadata,
)
from backend.models.genie import (
    GenieConversationMessageRequest,
    GenieSQLGeneration,
    GenieSerializedSpace,
)
from backend.models.metadata import MetadataRefreshRequest, MetadataSnapshot, MetadataSummary
from backend.models.qa_context import QAContextRequest
from backend.models.test_case import TestCase as CaseModel
from backend.models.test_case import TestCaseCreate as CaseCreateModel
from backend.models.validation_sql import TestCaseResult as CaseResultModel
from backend.models.validation_sql import ValidationSQL, ValidationSQLCreate


FIXTURE_DIRECTORY = Path(__file__).resolve().parents[1] / "frontend" / "tests" / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _resolve_case(fixture: dict[str, Any], path: str) -> Any:
    value: Any = fixture
    for segment in path.split("."):
        value = value[segment]
    return value


def test_databricks_fixtures_match_backend_contracts() -> None:
    fixture = _load_fixture("databricks.fixtures.json")

    TypeAdapter(list[CatalogResponse]).validate_python(fixture["catalogs"]["success"]["catalogs"])
    TypeAdapter(list[CatalogResponse]).validate_python(fixture["catalogs"]["empty"]["catalogs"])

    CatalogLookupRequest.model_validate(fixture["schemas"]["request"])
    TypeAdapter(list[SchemaResponse]).validate_python(fixture["schemas"]["success"]["schemas"])
    TypeAdapter(list[SchemaResponse]).validate_python(fixture["schemas"]["empty"]["schemas"])

    SchemaLookupRequest.model_validate(fixture["schema_objects"]["request"])
    SchemaObjectsResponse.model_validate(fixture["schema_objects"]["success"])
    SchemaObjectsResponse.model_validate(fixture["schema_objects"]["empty"])

    TableLookupRequest.model_validate(fixture["table_metadata"]["request"])
    TableMetadata.model_validate(fixture["table_metadata"]["success"])


def test_metadata_fixtures_match_backend_contracts() -> None:
    fixture = _load_fixture("metadata.fixtures.json")

    MetadataSummary.model_validate(fixture["summary"]["success"])
    MetadataSummary.model_validate(fixture["summary"]["empty"])
    for request in fixture["refresh"]["requests"].values():
        MetadataRefreshRequest.model_validate(request)
    MetadataSnapshot.model_validate(fixture["refresh"]["success"])


def test_test_case_fixtures_match_backend_contracts() -> None:
    fixture = _load_fixture("test-case.fixtures.json")

    CaseCreateModel.model_validate(fixture["create"]["request"])
    CaseModel.model_validate(fixture["create"]["success"])
    TypeAdapter(list[CaseModel]).validate_python(fixture["list"]["success"])
    TypeAdapter(list[CaseModel]).validate_python(fixture["list"]["empty"])


def test_payor_config_fixtures_match_backend_contracts() -> None:
    fixture = _load_fixture("payor-config.fixtures.json")

    TypeAdapter(list[str]).validate_python(fixture["payors"]["success"]["payors"])
    TypeAdapter(list[str]).validate_python(fixture["payors"]["empty"]["payors"])
    PayorLookupRequest.model_validate(fixture["file_types"]["request"])
    TypeAdapter(list[str]).validate_python(fixture["file_types"]["success"]["file_types"])
    TypeAdapter(list[str]).validate_python(fixture["file_types"]["empty"]["file_types"])


def test_genie_fixtures_match_backend_contracts() -> None:
    fixture = _load_fixture("genie.fixtures.json")

    for status_fixture in fixture["status"].values():
        assert set(status_fixture) == {"status", "title", "space_id"}
        assert status_fixture["status"] in {"ready", "pending_creation"}

    QAContextRequest.model_validate(fixture["context"]["request"])
    GenieSerializedSpace.model_validate(fixture["context"]["success"])
    QAContextRequest.model_validate(fixture["generation"]["request"])
    GenieSQLGeneration.model_validate(fixture["generation"]["success"])
    GenieConversationMessageRequest.model_validate(fixture["conversation"]["request"])
    GenieSQLGeneration.model_validate(fixture["conversation"]["success"])


def test_validation_sql_fixtures_match_backend_contracts() -> None:
    fixture = _load_fixture("validation-sql.fixtures.json")

    ValidationSQLCreate.model_validate(fixture["save"]["request"])
    ValidationSQL.model_validate(fixture["save"]["success"])
    ValidationSQLSearchRequest.model_validate(fixture["search"]["request"])
    TypeAdapter(list[ValidationSQL]).validate_python(fixture["search"]["success"])
    TypeAdapter(list[ValidationSQL]).validate_python(fixture["search"]["empty"])
    CaseResultModel.model_validate(fixture["execute"]["success"])
    CaseResultModel.model_validate(fixture["execute"]["no_columns"])


def test_error_fixtures_cover_string_and_structured_details() -> None:
    fixture = _load_fixture("error.fixtures.json")

    assert isinstance(fixture["string_detail"]["status"], int)
    assert isinstance(fixture["string_detail"]["body"]["detail"], str)
    assert fixture["validation_detail"]["status"] == 422
    assert isinstance(fixture["validation_detail"]["body"]["detail"], list)
    assert fixture["validation_detail"]["body"]["detail"][0]["loc"] == ["body", "catalog_name"]


def test_manifest_covers_every_migrated_endpoint_and_workflow() -> None:
    manifest = _load_fixture("api-contract.fixtures.json")
    expected_endpoints = {
        "GET /api/v1/databricks/catalogs",
        "POST /api/v1/databricks/schemas:lookup",
        "POST /api/v1/databricks/schema-objects:lookup",
        "POST /api/v1/databricks/tables:lookup",
        "GET /api/v1/test-cases",
        "POST /api/v1/test-cases",
        "GET /api/v1/payor-config/payors",
        "POST /api/v1/payor-config/file-types:lookup",
        "GET /api/v1/metadata/summary",
        "POST /api/v1/metadata/refresh",
        "GET /api/v1/genie-space/status",
        "POST /api/v1/qa/genie-context",
        "POST /api/v1/qa/genie-space",
        "POST /api/v1/qa/genie/conversations/{conversation_id}/messages",
        "POST /api/v1/qa/validation-sql",
        "POST /api/v1/qa/validation-sql:search",
        "POST /api/v1/qa/validation-sql/{validation_sql_id}:execute",
    }
    endpoint_keys = {f"{item['method']} {item['path']}" for item in manifest["endpoints"]}

    assert endpoint_keys == expected_endpoints
    assert set(manifest["workflows"]) == {
        "metadata",
        "test_cases",
        "generation_configuration",
        "genie_and_save",
        "execution",
    }
    assert set().union(*map(set, manifest["workflows"].values())) <= endpoint_keys

    for item in manifest["endpoints"]:
        fixture = _load_fixture(item["fixture"])
        if request_path := item.get("request"):
            _resolve_case(fixture, request_path)
        _resolve_case(fixture, item["response"])