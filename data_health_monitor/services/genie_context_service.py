from __future__ import annotations

from data_health_monitor.config import Settings, get_settings
from data_health_monitor.models.genie import (
    GenieColumnConfig,
    GenieConfig,
    GenieDataSources,
    GenieInstructions,
    GenieSampleQuestion,
    GenieSerializedSpace,
    GenieTableConfig,
    GenieTextInstruction,
)
from data_health_monitor.models.metadata import MetadataTable
from data_health_monitor.models.qa_context import QAContext, TableContext
from data_health_monitor.repositories.metadata_repository import MetadataSnapshotNotFoundError, MetadataTableNotFoundError
from data_health_monitor.services.metadata_service import MetadataService

from uuid import uuid4

class GenieContextError(RuntimeError):
    pass


class GenieContextService:
    def __init__(self, metadata_service: MetadataService, settings: Settings | None = None):
        self.metadata_service = metadata_service
        self.settings = settings or get_settings()

    @staticmethod
    def _genie_id() -> str:
        return uuid4().hex

    @staticmethod
    def _identifier(catalog: str, schema: str, table_name: str) -> str:
        return f"{catalog}.{schema}.{table_name}"

    @staticmethod
    def _table_config(metadata: MetadataTable) -> GenieTableConfig:
        return GenieTableConfig(
            identifier=GenieContextService._identifier(
                metadata.catalog_name,
                metadata.schema_name,
                metadata.name,
            ),
            column_configs=[
                GenieColumnConfig(
                    column_name=column.name,
                    enable_format_assistance=True,
                    enable_entity_matching=True,
                )
                for column in metadata.columns
            ],
        )

    def _static_table_metadata(self) -> list[MetadataTable]:
        locations = [
            (
                self.settings.databricks_catalog,
                self.settings.databricks_schema,
                self.settings.test_case_table_name,
            ),
            (
                self.settings.payor_config_catalog,
                self.settings.payor_config_schema,
                self.settings.payor_config_table_name,
            ),
        ]
        try:
            return [
                self.metadata_service.get_table_metadata(catalog, schema, table_name)
                for catalog, schema, table_name in locations
            ]
        except (MetadataSnapshotNotFoundError, MetadataTableNotFoundError) as exc:
            raise GenieContextError(str(exc)) from exc

    @staticmethod
    def _target_table_metadata(table_context: TableContext) -> MetadataTable:
        try:
            return MetadataTable.model_validate(table_context.metadata)
        except ValueError as exc:
            raise GenieContextError(
                f"Target table '{table_context.catalog}.{table_context.schema}.{table_context.table_name}' has invalid metadata."
            ) from exc

    def _instructions(self, qa_context: QAContext) -> GenieInstructions:
        test_case_identifier = self._identifier(
            self.settings.databricks_catalog,
            self.settings.databricks_schema,
            self.settings.test_case_table_name,
        )
        payor_config_identifier = self._identifier(
            self.settings.payor_config_catalog,
            self.settings.payor_config_schema,
            self.settings.payor_config_table_name,
        )
        target_context = [
            (
                f"For target table {self._identifier(table.catalog, table.schema, table.table_name)}, query "
                f"{payor_config_identifier} where payor is {table.payor_config.payor} and file type is "
                f"{table.payor_config.file_type}; validate only this target using that configuration."
            )
            for table in qa_context.tables
        ]
        return GenieInstructions(
            text_instructions=[
                GenieTextInstruction(
                    id=self._genie_id(),
                    content=[
                        "Generate validation SQL by following this numbered workflow.",
                        (
                            f"1. Query {test_case_identifier} where test_case_id is "
                            f"{qa_context.test_case.test_case_id}."
                        ),
                        "2. Execute that lookup as a small standalone query and inspect its result. Do not combine test-case, payor-configuration, and target investigation into one CTE or one SQL statement.",
                        "3. Inspect test_case_id, test_scenario, validation_check, and expected_result; treat validation_check and expected_result as the source of truth.",
                        (
                            f"4. For each target, query {payor_config_identifier} using its payor and file type "
                            "before generating validation SQL."
                        ),
                        *target_context,
                        "5. Only validate the target table or tables specified above; test case and payor configuration tables are lookup tables. Process each target independently with its corresponding configuration.",
                        "6. Use target metadata to verify referenced tables and columns. Execute small read-only payor-configuration lookups and target-table samples as needed, observe each result, then decide the next query.",
                        "7. Translate the specific test-case requirement into validation SQL for the applicable target table. Do not invent columns, values, business rules, or validation logic, and do not infer a rule solely from a column name.",
                        "8. Execute the candidate validation SQL and inspect its result. If it fails, is incomplete, or does not test the requirement, investigate further and revise it before responding. Do not generate SQL for unrelated tables. Never return a CTE, CASE, CONCAT, or other query that constructs validation SQL as a string. Return only the final executable validation SQL that directly validates the target table.",
                    ],
                )
            ],
        )

    def build_context(self, qa_context: QAContext) -> GenieSerializedSpace:
        static_tables = [self._table_config(metadata) for metadata in self._static_table_metadata()]
        target_tables = [self._table_config(self._target_table_metadata(table)) for table in qa_context.tables]
        tables = [*static_tables, *target_tables]
        identifiers = [table.identifier for table in tables]
        if len(identifiers) != len(set(identifiers)):
            raise GenieContextError("Genie context contains duplicate table identifiers.")

        return GenieSerializedSpace(
            version=2,
            config=GenieConfig(
                sample_questions=[
                    GenieSampleQuestion(
                        id=self._genie_id(),
                        question=[
                            (
                                f"Generate validation SQL for test case {qa_context.test_case.test_case_id} by first "
                                "reading the test case, then resolving the applicable payor configuration, then validating "
                                "the specified target table. You may execute read-only intermediate queries and reason over "
                                "their results one query at a time. Execute and revise the candidate validation SQL as needed, then return only the final executable validation SQL, never a query that constructs SQL as text."
                            )
                        ],
                    )
                ]
            ),
            data_sources=GenieDataSources(tables=tables),
            instructions=self._instructions(qa_context),
        )