from __future__ import annotations

from data_health_monitor.models.payor_config import PayorConfig
from data_health_monitor.models.qa_context import QAContext, QAContextRequest, TableContext
from data_health_monitor.models.test_case import TestCase
from data_health_monitor.repositories.metadata_repository import MetadataSnapshotNotFoundError, MetadataTableNotFoundError
from data_health_monitor.services.metadata_service import MetadataService
from data_health_monitor.services.payor_config_service import PayorConfigNotFoundError, PayorConfigService
from data_health_monitor.services.test_case_service import TestCaseNotFoundError, TestCaseService


class QAContextTestCaseNotFoundError(RuntimeError):
    def __init__(self, test_case_id: str):
        super().__init__(f"Test case '{test_case_id}' was not found while building QA context.")


class QAContextExpectedTableMissingError(RuntimeError):
    def __init__(self, payor: str, file_type: str):
        super().__init__(f"Payor configuration '{payor}/{file_type}' does not define an expected target table.")


class QAContextTableMismatchError(RuntimeError):
    def __init__(self, selected_table: str, expected_table: str, payor: str, file_type: str):
        super().__init__(
            f"Selected table '{selected_table}' does not match expected table '{expected_table}' for '{payor}/{file_type}'."
        )


class QAContextMetadataTableNotFoundError(RuntimeError):
    def __init__(self, catalog: str, schema: str, table_name: str):
        super().__init__(f"Table '{catalog}.{schema}.{table_name}' was not found in the metadata snapshot.")


class QAContextMetadataSnapshotNotFoundError(RuntimeError):
    pass


def resolve_expected_table(payor_config: PayorConfig, test_case: TestCase) -> str | None:
    return payor_config.sql_pool_table


class QAContextService:
    def __init__(
        self,
        test_case_service: TestCaseService,
        payor_config_service: PayorConfigService,
        metadata_service: MetadataService,
    ):
        self.test_case_service = test_case_service
        self.payor_config_service = payor_config_service
        self.metadata_service = metadata_service

    def build_context(self, request: QAContextRequest) -> QAContext:
        try:
            test_case = self.test_case_service.get_test_case(request.test_case_id)
        except TestCaseNotFoundError as exc:
            raise QAContextTestCaseNotFoundError(request.test_case_id) from exc

        table_contexts = []
        for selection in request.selections:
            try:
                payor_config = self.payor_config_service.get_config(
                    payor=selection.payor,
                    file_type=selection.file_type,
                )
            except PayorConfigNotFoundError:
                raise

            expected_table = resolve_expected_table(payor_config, test_case)
            if not expected_table:
                raise QAContextExpectedTableMissingError(selection.payor, selection.file_type)
            if expected_table.casefold() != selection.table_name.casefold():
                raise QAContextTableMismatchError(
                    selection.table_name,
                    expected_table,
                    selection.payor,
                    selection.file_type,
                )

            try:
                metadata = self.metadata_service.get_table_metadata(
                    catalog_name=request.catalog,
                    schema_name=request.schema,
                    table_name=selection.table_name,
                )
            except MetadataSnapshotNotFoundError as exc:
                raise QAContextMetadataSnapshotNotFoundError(str(exc)) from exc
            except MetadataTableNotFoundError as exc:
                raise QAContextMetadataTableNotFoundError(
                    request.catalog,
                    request.schema,
                    selection.table_name,
                ) from exc

            table_contexts.append(
                TableContext(
                    catalog=request.catalog,
                    schema=request.schema,
                    table_name=metadata.name,
                    metadata=metadata.model_dump(mode="json"),
                    expected_table=expected_table,
                    payor_config=payor_config,
                )
            )

        return QAContext(test_case=test_case, tables=table_contexts)