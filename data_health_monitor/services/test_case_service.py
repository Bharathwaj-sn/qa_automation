from __future__ import annotations

from datetime import datetime, timezone

from data_health_monitor.config import Settings, get_settings
from data_health_monitor.models.databricks_sql import SQLExecutionRequest, SQLParameter
from data_health_monitor.models.test_case import TestCase, TestCaseCreate
from data_health_monitor.services.databricks_sql_service import (
    DatabricksSQLExecutionError,
    DatabricksSQLService,
)


class TestCaseNotFoundError(RuntimeError):
    def __init__(self, test_case_id: str):
        self.test_case_id = test_case_id
        super().__init__(f"Test case '{test_case_id}' not found.")


class DuplicateTestCaseError(RuntimeError):
    def __init__(self, test_case_id: str):
        self.test_case_id = test_case_id
        super().__init__(f"Test case '{test_case_id}' already exists.")


class TestCaseService:
    def __init__(
        self,
        sql_service: DatabricksSQLService,
        settings: Settings | None = None,
    ):
        self.sql_service = sql_service
        self.settings = settings or get_settings()

    @property
    def _table_name(self) -> str:
        return f"{self.settings.databricks_catalog}.{self.settings.databricks_schema}.{self.settings.test_case_table_name}"

    def _generate_test_case_id(self) -> str:
        """Generate the next test case ID by querying the max existing ID."""
        sql = f"SELECT MAX(SUBSTRING(test_case_id, 3)) as max_num FROM {self._table_name}"
        try:
            result = self.sql_service.execute(
                SQLExecutionRequest(
                    statement=sql,
                    warehouse_id=self.settings.databricks_warehouse_id or "",
                    catalog=self.settings.databricks_catalog,
                    schema_name=self.settings.databricks_schema,
                )
            )

            if not result.rows or not result.rows[0]:
                next_num = 1
            else:
                max_num_str = result.rows[0][0]
                try:
                    max_num = int(max_num_str) if max_num_str else 0
                except (ValueError, TypeError):
                    max_num = 0
                next_num = max_num + 1
        except (DatabricksSQLExecutionError, Exception):
            # If table doesn't exist or query fails, start from 1
            next_num = 1

        return f"TC{next_num:06d}"

    def create_test_case(self, test_case: TestCaseCreate) -> TestCase:
        """Create a new test case and store it in Databricks."""

        self.initialize_table(
            sql_service=self.sql_service,
            settings=self.settings,
        )

        test_case_id = self._generate_test_case_id()
        now = datetime.now(timezone.utc)

        statement = f"""
INSERT INTO {self._table_name}
(
    test_case_id,
    pipeline,
    component,
    test_scenario,
    target_object,
    input_data,
    validation_check,
    expected_result,
    status,
    created_at,
    updated_at
)
VALUES
(
    :test_case_id,
    :pipeline,
    :component,
    :test_scenario,
    :target_object,
    :input_data,
    :validation_check,
    :expected_result,
    :status,
    :created_at,
    :updated_at
)
        """.strip()

        try:
            self.sql_service.execute(
                SQLExecutionRequest(
                    statement=statement,
                    warehouse_id=self.settings.databricks_warehouse_id or "",
                    catalog=self.settings.databricks_catalog,
                    schema_name=self.settings.databricks_schema,
                    parameters=[
                        SQLParameter(name="test_case_id", value=test_case_id),
                        SQLParameter(name="pipeline", value=test_case.pipeline),
                        SQLParameter(name="component", value=test_case.component),
                        SQLParameter(name="test_scenario", value=test_case.test_scenario),
                        SQLParameter(name="target_object", value=test_case.target_object),
                        SQLParameter(name="input_data", value=test_case.input_data),
                        SQLParameter(name="validation_check", value=test_case.validation_check),
                        SQLParameter(name="expected_result", value=test_case.expected_result),
                        SQLParameter(name="status", value="ACTIVE"),
                        SQLParameter(name="created_at", value=now.isoformat()),
                        SQLParameter(name="updated_at", value=now.isoformat()),
                    ],
                )
            )
        except DatabricksSQLExecutionError as exc:
            if "already exists" in str(exc).lower():
                raise DuplicateTestCaseError(test_case_id) from exc
            raise

        return TestCase(
            test_case_id=test_case_id,
            pipeline=test_case.pipeline,
            component=test_case.component,
            test_scenario=test_case.test_scenario,
            target_object=test_case.target_object,
            input_data=test_case.input_data,
            validation_check=test_case.validation_check,
            expected_result=test_case.expected_result,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )

    def get_test_case(self, test_case_id: str) -> TestCase:
        """Retrieve a test case by ID."""
        statement = f"""
SELECT
    test_case_id,
    pipeline,
    component,
    test_scenario,
    target_object,
    input_data,
    validation_check,
    expected_result,
    status,
    created_at,
    updated_at
FROM {self._table_name}
WHERE test_case_id = :test_case_id
        """.strip()

        try:
            result = self.sql_service.execute(
                SQLExecutionRequest(
                    statement=statement,
                    warehouse_id=self.settings.databricks_warehouse_id or "",
                    catalog=self.settings.databricks_catalog,
                    schema_name=self.settings.databricks_schema,
                    parameters=[SQLParameter(name="test_case_id", value=test_case_id)],
                )
            )
        except DatabricksSQLExecutionError as exc:
            raise TestCaseNotFoundError(test_case_id) from exc

        if not result.rows:
            raise TestCaseNotFoundError(test_case_id)

        row = result.rows[0]
        return TestCase(
            test_case_id=str(row[0]),
            pipeline=str(row[1]),
            component=str(row[2]),
            test_scenario=str(row[3]),
            target_object=str(row[4]),
            input_data=str(row[5]),
            validation_check=str(row[6]),
            expected_result=str(row[7]),
            status=str(row[8]),
            created_at=row[9] if row[9] else None,
            updated_at=row[10] if row[10] else None,
        )

    def list_test_cases(self) -> list[TestCase]:
        """List all active test cases."""
        statement = f"""
SELECT
    test_case_id,
    pipeline,
    component,
    test_scenario,
    target_object,
    input_data,
    validation_check,
    expected_result,
    status,
    created_at,
    updated_at
FROM {self._table_name}
WHERE status = 'ACTIVE'
ORDER BY test_case_id
        """.strip()

        try:
            result = self.sql_service.execute(
                SQLExecutionRequest(
                    statement=statement,
                    warehouse_id=self.settings.databricks_warehouse_id or "",
                    catalog=self.settings.databricks_catalog,
                    schema_name=self.settings.databricks_schema,
                )
            )
        except DatabricksSQLExecutionError:
            return []

        test_cases = []
        for row in result.rows:
            test_cases.append(
                TestCase(
                    test_case_id=str(row[0]),
                    pipeline=str(row[1]),
                    component=str(row[2]),
                    test_scenario=str(row[3]),
                    target_object=str(row[4]),
                    input_data=str(row[5]),
                    validation_check=str(row[6]),
                    expected_result=str(row[7]),
                    status=str(row[8]),
                    created_at=row[9] if row[9] else None,
                    updated_at=row[10] if row[10] else None,
                )
            )

        return test_cases

    @staticmethod
    def initialize_table(
        sql_service: DatabricksSQLService,
        settings: Settings | None = None,
    ) -> None:
        """Create the test_cases table if it does not exist."""
        settings = settings or get_settings()
        table_name = f"{settings.databricks_catalog}.{settings.databricks_schema}.{settings.test_case_table_name}"

        create_table_sql = f"""
CREATE TABLE IF NOT EXISTS {table_name}
(
    test_case_id STRING NOT NULL,
    pipeline STRING NOT NULL,
    component STRING NOT NULL,
    test_scenario STRING NOT NULL,
    target_object STRING NOT NULL,
    input_data STRING NOT NULL,
    validation_check STRING NOT NULL,
    expected_result STRING NOT NULL,
    status STRING NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
)
USING DELTA
        """.strip()

        sql_service.execute(
            SQLExecutionRequest(
                statement=create_table_sql,
                warehouse_id=settings.databricks_warehouse_id or "",
                catalog=settings.databricks_catalog,
                schema_name=settings.databricks_schema,
            )
        )
