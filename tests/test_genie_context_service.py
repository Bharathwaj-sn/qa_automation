from datetime import datetime, timezone
import re

import pytest

from app.config import Settings
from app.models.metadata import MetadataTable
from app.models.payor_config import PayorConfig
from app.models.qa_context import QAContext, TableContext
from app.models.test_case import TestCase
from app.repositories.metadata_repository import MetadataTableNotFoundError
from app.services.genie_context_service import GenieContextError, GenieContextService


class FakeMetadataService:
    def __init__(self, tables):
        self.tables = tables

    def get_table_metadata(self, catalog_name, schema_name, table_name):
        key = (catalog_name, schema_name, table_name)
        if key not in self.tables:
            raise MetadataTableNotFoundError(*key)
        return self.tables[key]


def make_table(catalog, schema, name, columns):
    return MetadataTable.model_validate(
        {
            "catalog_name": catalog,
            "schema_name": schema,
            "name": name,
            "columns": [{"name": column} for column in columns],
        }
    )


def make_qa_context(*target_tables):
    return QAContext(
        test_case=TestCase(
            test_case_id="TC000002",
            pipeline="Silver",
            component="Demographic",
            test_scenario="Validate demographic data",
            target_object="table",
            input_data="records",
            validation_check="check",
            expected_result="valid",
            created_at=datetime.now(timezone.utc),
        ),
        tables=[
            TableContext(
                catalog="dev_adls_lakehouse",
                schema="silver",
                table_name=table.name,
                metadata=table.model_dump(mode="json"),
                expected_table=table.name,
                payor_config=PayorConfig(payor="advent", file_type="Demographic"),
            )
            for table in target_tables
        ],
    )


def make_service(static_tables):
    settings = Settings(
        databricks_catalog="dev_adls_lakehouse",
        databricks_schema="testing_poc",
        test_case_table_name="test_cases",
        payor_config_catalog="dev_adls_lakehouse",
        payor_config_schema="util",
        payor_config_table_name="payor_config",
    )
    return GenieContextService(FakeMetadataService(static_tables), settings=settings)


def test_build_context_adds_static_and_selected_target_tables_with_all_metadata_columns():
    test_cases = make_table("dev_adls_lakehouse", "testing_poc", "test_cases", ["test_case_id", "validation_check"])
    payor_config = make_table("dev_adls_lakehouse", "util", "payor_config", ["payor", "file_type"])
    target = make_table("dev_adls_lakehouse", "silver", "advent_demographic", ["member_number", "birth_date"])

    space = make_service(
        {
            (test_cases.catalog_name, test_cases.schema_name, test_cases.name): test_cases,
            (payor_config.catalog_name, payor_config.schema_name, payor_config.name): payor_config,
        }
    ).build_context(make_qa_context(target))

    tables = {table.identifier: table for table in space.data_sources.tables}
    assert set(tables) == {
        "dev_adls_lakehouse.testing_poc.test_cases",
        "dev_adls_lakehouse.util.payor_config",
        "dev_adls_lakehouse.silver.advent_demographic",
    }
    columns = tables["dev_adls_lakehouse.silver.advent_demographic"].column_configs
    assert [column.column_name for column in columns] == ["member_number", "birth_date"]
    assert all(column.enable_format_assistance is True for column in columns)
    assert all(column.enable_entity_matching is True for column in columns)
    assert space.version == 2


def test_build_context_adds_multiple_target_tables_and_procedural_instructions_and_examples():
    test_cases = make_table("dev_adls_lakehouse", "testing_poc", "test_cases", ["test_case_id"])
    payor_config = make_table("dev_adls_lakehouse", "util", "payor_config", ["payor"])
    demographic = make_table("dev_adls_lakehouse", "silver", "advent_demographic", ["member_number"])
    claims = make_table("dev_adls_lakehouse", "silver", "advent_medicalclaim", ["claim_id"])
    space = make_service(
        {
            (test_cases.catalog_name, test_cases.schema_name, test_cases.name): test_cases,
            (payor_config.catalog_name, payor_config.schema_name, payor_config.name): payor_config,
        }
    ).build_context(make_qa_context(demographic, claims))

    instruction = space.instructions.text_instructions[0].content
    assert "Generate validation SQL only. Do not execute SQL." in instruction
    assert any("dev_adls_lakehouse.testing_poc.test_cases" in value and "TC000002" in value for value in instruction)
    assert "Inspect test_case_id, test_scenario, validation_check, and expected_result." in instruction
    assert "Treat validation_check and expected_result as the source of truth for the validation requirement." in instruction
    assert any("dev_adls_lakehouse.util.payor_config" in value and "payor and file type" in value for value in instruction)
    assert any(
        "advent" in value
        and "Demographic" in value
        and "dev_adls_lakehouse.util.payor_config" in value
        for value in instruction
    )
    assert "Only validate the target table or tables specified above; test case and payor configuration tables are lookup tables." in instruction
    assert "Use target metadata to verify referenced tables and columns exist; inspect a small sample only when needed." in instruction
    assert "Do not invent columns, values, business rules, or validation logic, and do not infer a rule solely from a column name." in instruction
    assert "Return only the final validation SQL." in instruction
    sample_question = space.config.sample_questions[0].question[0]
    assert "TC000002" in sample_question
    assert "first reading the test case" in sample_question
    assert "resolving the applicable payor configuration" in sample_question
    assert "Return only the validation SQL." in sample_question
    assert [example.sql[0] for example in space.instructions.example_question_sqls] == [
        "SELECT * FROM dev_adls_lakehouse.silver.advent_demographic LIMIT 5",
        "SELECT * FROM dev_adls_lakehouse.silver.advent_medicalclaim LIMIT 5",
    ]
    generated_ids = [
        *(instruction.id for instruction in space.instructions.text_instructions),
        *(example.id for example in space.instructions.example_question_sqls),
        *(question.id for question in space.config.sample_questions),
    ]
    assert all(re.fullmatch(r"[0-9a-f]{32}", generated_id) for generated_id in generated_ids)

    canonical = space.canonicalize()
    assert [instruction.id for instruction in canonical.instructions.text_instructions] == sorted(
        instruction.id for instruction in canonical.instructions.text_instructions
    )
    assert [example.id for example in canonical.instructions.example_question_sqls] == sorted(
        example.id for example in canonical.instructions.example_question_sqls
    )
    assert [question.id for question in canonical.config.sample_questions] == sorted(
        question.id for question in canonical.config.sample_questions
    )
    reparsed = type(canonical).from_serialized_space(canonical.to_serialized_space())
    assert reparsed == canonical


def test_build_context_fails_when_static_table_metadata_is_missing():
    target = make_table("dev_adls_lakehouse", "silver", "advent_demographic", ["member_number"])

    with pytest.raises(GenieContextError, match="test_cases"):
        make_service({}).build_context(make_qa_context(target))