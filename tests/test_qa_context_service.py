from datetime import datetime, timezone

import pytest

from app.models.databricks import SchemaObjectsResponse, TableMetadata, TableSummary
from app.models.payor_config import PayorConfig
from app.models.qa_context import QAContextRequest
from app.models.test_case import TestCase
from app.services.qa_context_service import (
    QAContextService,
    QAContextTableNotFoundError,
    QAContextTestCaseNotFoundError,
)
from app.services.test_case_service import TestCaseNotFoundError


def make_test_case() -> TestCase:
    return TestCase(
        test_case_id="TC000073", pipeline="Silver", component="dates", test_scenario="valid dates",
        target_object="table", input_data="records", validation_check="check", expected_result="valid",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


class FakeTestCaseService:
    def __init__(self, missing=False):
        self.missing = missing

    def get_test_case(self, test_case_id):
        if self.missing:
            raise TestCaseNotFoundError(test_case_id)
        return make_test_case()


class FakeDatabricksService:
    def __init__(self, names=("silver_member",), fail=False):
        self.names = names
        self.fail = fail

    def list_schema_objects(self, catalog_name, schema_name):
        return SchemaObjectsResponse(tables=[TableSummary(name=name) for name in self.names], volumes=[])

    def get_table_metadata(self, catalog_name, schema_name, table_name):
        if self.fail:
            raise RuntimeError("missing")
        return TableMetadata(catalog_name=catalog_name, schema_name=schema_name, name=table_name)


class FakePayorConfigService:
    def __init__(self, configs=None):
        self.configs = configs or []
        self.calls = []

    def list_configs_for_table(self, table_name, schema_name=None):
        self.calls.append((table_name, schema_name))
        return self.configs


def make_service(test_case_missing=False, table_names=("silver_member",), metadata_fails=False, configs=None):
    return QAContextService(
        test_case_service=FakeTestCaseService(test_case_missing),
        payor_config_service=FakePayorConfigService(configs),
        databricks_service=FakeDatabricksService(table_names, metadata_fails),
    )


def test_build_context_for_a_table_includes_metadata_and_matching_configs():
    service = make_service(configs=[PayorConfig(payor="ABC", table_name="silver_member", natural_keys=["member_id"])])

    context = service.build_context(QAContextRequest(test_case_id="TC000073", catalog="dev", schema="poc", table_name="silver_member"))

    assert context.test_case.test_case_id == "TC000073"
    assert context.tables[0].metadata["name"] == "silver_member"
    assert context.tables[0].payor_configs[0].natural_keys == ["member_id"]


def test_build_context_discovers_all_supported_tables_and_allows_no_configs():
    service = make_service(table_names=("members", "claims"))

    context = service.build_context(QAContextRequest(test_case_id="TC000073", catalog="dev", schema="poc", include_all_tables=True))

    assert [table.table_name for table in context.tables] == ["members", "claims"]
    assert all(table.payor_configs == [] for table in context.tables)


def test_context_converts_missing_test_case_and_table_errors():
    with pytest.raises(QAContextTestCaseNotFoundError):
        make_service(test_case_missing=True).build_context(QAContextRequest(test_case_id="missing", catalog="dev", schema="poc", table_name="members"))
    with pytest.raises(QAContextTableNotFoundError):
        make_service(metadata_fails=True).build_context(QAContextRequest(test_case_id="TC000073", catalog="dev", schema="poc", table_name="members"))


def test_context_request_rejects_ambiguous_or_empty_scope():
    with pytest.raises(ValueError):
        QAContextRequest(test_case_id="TC000073", catalog="dev", schema="poc")
    with pytest.raises(ValueError):
        QAContextRequest(test_case_id="TC000073", catalog="dev", schema="poc", table_name="members", include_all_tables=True)