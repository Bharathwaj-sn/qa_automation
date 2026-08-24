from __future__ import annotations

from app.models.qa_context import QAContext, QAContextRequest, TableContext
from app.services.databricks_service import DatabricksService
from app.services.payor_config_service import PayorConfigService
from app.services.test_case_service import TestCaseNotFoundError, TestCaseService


class QAContextTestCaseNotFoundError(RuntimeError):
    def __init__(self, test_case_id: str):
        super().__init__(f"Test case '{test_case_id}' was not found while building QA context.")


class QAContextTableNotFoundError(RuntimeError):
    def __init__(self, catalog: str, schema: str, table_name: str):
        super().__init__(f"Table '{catalog}.{schema}.{table_name}' was not found or is inaccessible.")


class QAContextService:
    def __init__(
        self,
        test_case_service: TestCaseService,
        payor_config_service: PayorConfigService,
        databricks_service: DatabricksService,
    ):
        self.test_case_service = test_case_service
        self.payor_config_service = payor_config_service
        self.databricks_service = databricks_service

    def _table_names(self, request: QAContextRequest) -> list[str]:
        if request.table_name:
            return [request.table_name]
        objects = self.databricks_service.list_schema_objects(
            catalog_name=request.catalog,
            schema_name=request.schema,
        )
        return [table.name for table in objects.tables]

    def build_context(self, request: QAContextRequest) -> QAContext:
        try:
            test_case = self.test_case_service.get_test_case(request.test_case_id)
        except TestCaseNotFoundError as exc:
            raise QAContextTestCaseNotFoundError(request.test_case_id) from exc

        table_contexts = []
        for table_name in self._table_names(request):
            try:
                metadata = self.databricks_service.get_table_metadata(
                    catalog_name=request.catalog,
                    schema_name=request.schema,
                    table_name=table_name,
                )
            except Exception as exc:
                raise QAContextTableNotFoundError(request.catalog, request.schema, table_name) from exc

            table_contexts.append(
                TableContext(
                    catalog=request.catalog,
                    schema=request.schema,
                    table_name=table_name,
                    metadata=metadata.model_dump(mode="json"),
                    payor_configs=self.payor_config_service.list_configs_for_table(
                        table_name=table_name,
                        schema_name=request.schema,
                    ),
                )
            )

        return QAContext(test_case=test_case, tables=table_contexts)