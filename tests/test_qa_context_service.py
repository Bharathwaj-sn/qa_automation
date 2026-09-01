from datetime import datetime, timezone

import pytest

from data_health_monitor.models.metadata import MetadataTable
from data_health_monitor.models.payor_config import PayorConfig
from data_health_monitor.models.qa_context import QAContextRequest, QAContextSelection
from data_health_monitor.models.test_case import TestCase
from data_health_monitor.repositories.metadata_repository import MetadataSnapshotNotFoundError, MetadataTableNotFoundError
from data_health_monitor.services.qa_context_service import (
    QAContextMetadataTableNotFoundError,
    QAContextService,
    QAContextTableMismatchError,
    QAContextTestCaseNotFoundError,
    resolve_expected_table,
)
from data_health_monitor.services.test_case_service import TestCaseNotFoundError


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


class FakeMetadataService:
    def __init__(self, names=("silver_member",), snapshot_missing=False):
        self.names = names
        self.snapshot_missing = snapshot_missing

    def get_table_metadata(self, catalog_name, schema_name, table_name):
        if self.snapshot_missing:
            raise MetadataSnapshotNotFoundError("No metadata snapshot has been generated yet.")
        if table_name not in self.names:
            raise MetadataTableNotFoundError(catalog_name, schema_name, table_name)
        return MetadataTable(catalog_name=catalog_name, schema_name=schema_name, name=table_name)


class FakePayorConfigService:
    def __init__(self, configs=None):
        self.configs = configs or []
        self.calls = []

    def get_config(self, payor, file_type):
        self.calls.append((payor, file_type))
        return self.configs[(payor, file_type)]


def make_service(test_case_missing=False, table_names=("silver_member",), snapshot_missing=False, configs=None):
    return QAContextService(
        test_case_service=FakeTestCaseService(test_case_missing),
        payor_config_service=FakePayorConfigService(configs),
        metadata_service=FakeMetadataService(table_names, snapshot_missing),
    )


def test_build_context_for_a_table_includes_metadata_and_matching_configs():
    service = make_service(
        configs={
            ("ABC", "member"): PayorConfig(
                payor="ABC",
                file_type="member",
                sql_pool_table="silver_member",
                natural_keys=["member_id"],
            )
        }
    )

    context = service.build_context(
        QAContextRequest(
            test_case_id="TC000073",
            catalog="dev",
            schema="poc",
            selections=[QAContextSelection(table_name="silver_member", payor="ABC", file_type="member")],
        )
    )

    assert context.test_case.test_case_id == "TC000073"
    assert context.tables[0].metadata["name"] == "silver_member"
    assert context.tables[0].expected_table == "silver_member"
    assert context.tables[0].payor_config.natural_keys == ["member_id"]


def test_context_rejects_selected_table_that_does_not_match_configured_expected_table():
    service = make_service(
        table_names=("members",),
        configs={("ABC", "member"): PayorConfig(sql_pool_table="claims")},
    )

    with pytest.raises(QAContextTableMismatchError):
        service.build_context(
            QAContextRequest(
                test_case_id="TC000073",
                catalog="dev",
                schema="poc",
                selections=[QAContextSelection(table_name="members", payor="ABC", file_type="member")],
            )
        )


def test_context_converts_missing_test_case_and_metadata_table_errors():
    selection = QAContextSelection(table_name="members", payor="ABC", file_type="member")
    config = {("ABC", "member"): PayorConfig(sql_pool_table="members")}

    with pytest.raises(QAContextTestCaseNotFoundError):
        make_service(test_case_missing=True, configs=config).build_context(
            QAContextRequest(test_case_id="missing", catalog="dev", schema="poc", selections=[selection])
        )
    with pytest.raises(QAContextMetadataTableNotFoundError):
        make_service(table_names=(), configs=config).build_context(
            QAContextRequest(test_case_id="TC000073", catalog="dev", schema="poc", selections=[selection])
        )


def test_context_request_rejects_empty_or_duplicate_selections():
    with pytest.raises(ValueError):
        QAContextRequest(test_case_id="TC000073", catalog="dev", schema="poc", selections=[])
    with pytest.raises(ValueError):
        QAContextRequest(
            test_case_id="TC000073",
            catalog="dev",
            schema="poc",
            selections=[
                QAContextSelection(table_name="members", payor="ABC", file_type="member"),
                QAContextSelection(table_name="members", payor="ABC", file_type="member"),
            ],
        )


def test_resolve_expected_table_uses_sql_pool_table_by_default():
    assert resolve_expected_table(PayorConfig(sql_pool_table="claims"), make_test_case()) == "claims"