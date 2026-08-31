from __future__ import annotations

from app.config import Settings, get_settings
from app.models.genie import (
    GenieColumnConfig,
    GenieConfig,
    GenieDataSources,
    GenieExampleQuestionSql,
    GenieInstructions,
    GenieSampleQuestion,
    GenieSerializedSpace,
    GenieTableConfig,
    GenieTextInstruction,
)
from app.models.metadata import MetadataTable
from app.models.qa_context import QAContext, TableContext
from app.repositories.metadata_repository import MetadataSnapshotNotFoundError, MetadataTableNotFoundError
from app.services.metadata_service import MetadataService


class GenieContextError(RuntimeError):
    pass


class GenieContextService:
    def __init__(self, metadata_service: MetadataService, settings: Settings | None = None):
        self.metadata_service = metadata_service
        self.settings = settings or get_settings()

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
                f"Target table {self._identifier(table.catalog, table.schema, table.table_name)} uses payor "
                f"{table.payor_config.payor} and file type {table.payor_config.file_type}."
            )
            for table in qa_context.tables
        ]
        return GenieInstructions(
            text_instructions=[
                GenieTextInstruction(
                    id="qa-validation-context",
                    content=[
                        "Generate validation SQL only. Do not execute SQL.",
                        f"Use test case {qa_context.test_case.test_case_id} to determine the validation requirement.",
                        f"Use {test_case_identifier} for additional test case context.",
                        f"Use {payor_config_identifier} for additional payor configuration context.",
                        *target_context,
                        "Return SQL only when asked to generate validation SQL.",
                    ],
                )
            ],
            example_question_sqls=self._examples(qa_context),
        )

    def _examples(self, qa_context: QAContext) -> list[GenieExampleQuestionSql]:
        return [
            GenieExampleQuestionSql(
                id=f"sample-target-{index + 1}",
                question=[f"Show me a sample of {self._identifier(table.catalog, table.schema, table.table_name)}."],
                sql=[f"SELECT * FROM {self._identifier(table.catalog, table.schema, table.table_name)} LIMIT 5"],
                usage_guidance=["Use this to inspect target-table data before generating validation SQL."],
            )
            for index, table in enumerate(qa_context.tables)
        ]

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
                        id="generate-validation-sql",
                        question=[f"Generate validation SQL for test case {qa_context.test_case.test_case_id}."],
                    )
                ]
            ),
            data_sources=GenieDataSources(tables=tables),
            instructions=self._instructions(qa_context),
        )