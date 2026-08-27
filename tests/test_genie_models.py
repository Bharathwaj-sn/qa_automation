import json

import pytest
from pydantic import ValidationError

from app.models.genie import (
    GenieColumnConfig,
    GenieConfigurationError,
    GenieExampleQuestionSql,
    GenieSerializedSpace,
    GenieSpaceUpdateRequest,
    GenieTableConfig,
    GenieTextInstruction,
)


def serialized_space_payload():
    return {
        "version": 2,
        "config": {
            "sample_questions": [
                {"id": "sample-2", "question": ["Second sample"]},
                {"id": "sample-1", "question": ["First sample"]},
            ]
        },
        "data_sources": {
            "tables": [
                {
                    "identifier": "catalog.schema.table_b",
                    "column_configs": [
                        {"column_name": "column_z", "enable_format_assistance": True},
                        {"column_name": "column_a", "enable_entity_matching": True},
                        {"column_name": "column_m"},
                    ],
                },
                {"identifier": "catalog.schema.table_a", "column_configs": []},
                {"identifier": "catalog.schema.table_c", "column_configs": []},
            ]
        },
        "instructions": {
            "text_instructions": [
                {"id": "text-2", "content": ["Second instruction"]},
                {"id": "text-1", "content": ["First instruction"]},
            ],
            "example_question_sqls": [
                {
                    "id": "example-2",
                    "question": ["Second question"],
                    "sql": ["SELECT 2"],
                    "usage_guidance": ["Second guidance"],
                },
                {
                    "id": "example-1",
                    "question": ["First question"],
                    "sql": ["SELECT 1"],
                    "usage_guidance": ["First guidance"],
                },
            ],
        },
    }


def test_parses_representative_version_two_payload():
    space = GenieSerializedSpace.model_validate(serialized_space_payload())

    assert space.version == 2
    assert [table.identifier for table in space.data_sources.tables] == [
        "catalog.schema.table_b",
        "catalog.schema.table_a",
        "catalog.schema.table_c",
    ]
    assert [column.column_name for column in space.data_sources.tables[0].column_configs] == [
        "column_z",
        "column_a",
        "column_m",
    ]
    assert [instruction.id for instruction in space.instructions.text_instructions] == [
        "text-2",
        "text-1",
    ]
    assert [example.sql for example in space.instructions.example_question_sqls] == [
        ["SELECT 2"],
        ["SELECT 1"],
    ]
    assert [question.id for question in space.config.sample_questions] == ["sample-2", "sample-1"]


def test_canonicalize_sorts_tables_and_columns_without_mutating_source():
    space = GenieSerializedSpace.model_validate(serialized_space_payload())

    canonical = space.canonicalize()

    assert [table.identifier for table in canonical.data_sources.tables] == [
        "catalog.schema.table_a",
        "catalog.schema.table_b",
        "catalog.schema.table_c",
    ]
    assert [column.column_name for column in canonical.data_sources.tables[1].column_configs] == [
        "column_a",
        "column_m",
        "column_z",
    ]
    assert [table.identifier for table in space.data_sources.tables] == [
        "catalog.schema.table_b",
        "catalog.schema.table_a",
        "catalog.schema.table_c",
    ]


def test_canonicalize_preserves_instruction_and_sample_question_order():
    canonical = GenieSerializedSpace.model_validate(serialized_space_payload()).canonicalize()

    assert [instruction.id for instruction in canonical.instructions.text_instructions] == [
        "text-2",
        "text-1",
    ]
    assert [example.id for example in canonical.instructions.example_question_sqls] == [
        "example-2",
        "example-1",
    ]
    assert [question.id for question in canonical.config.sample_questions] == ["sample-2", "sample-1"]


def test_duplicate_table_identifiers_are_rejected():
    payload = serialized_space_payload()
    payload["data_sources"]["tables"].append(
        {"identifier": "catalog.schema.table_a", "column_configs": []}
    )

    with pytest.raises(ValidationError, match="duplicate identifier"):
        GenieSerializedSpace.model_validate(payload)


def test_duplicate_columns_within_one_table_are_rejected_but_shared_names_are_valid():
    payload = serialized_space_payload()
    payload["data_sources"]["tables"][0]["column_configs"].append(
        {"column_name": "column_a"}
    )

    with pytest.raises(ValidationError, match="duplicate column_name"):
        GenieSerializedSpace.model_validate(payload)

    payload = serialized_space_payload()
    payload["data_sources"]["tables"][1]["column_configs"] = [{"column_name": "column_a"}]
    space = GenieSerializedSpace.model_validate(payload)

    assert space.data_sources.tables[0].column_configs[1].column_name == "column_a"
    assert space.data_sources.tables[1].column_configs[0].column_name == "column_a"


def test_unknown_fields_survive_json_round_trip():
    payload = serialized_space_payload()
    payload["some_future_genie_field"] = {"enabled": True}
    payload["data_sources"]["future_data_source_field"] = "preserved"
    payload["data_sources"]["tables"][0]["future_table_field"] = {"value": 1}
    payload["data_sources"]["tables"][0]["column_configs"][0]["future_column_field"] = "yes"

    serialized = json.dumps(payload)
    result = json.loads(GenieSerializedSpace.from_serialized_space(serialized).to_serialized_space())

    assert result["some_future_genie_field"] == {"enabled": True}
    assert result["data_sources"]["future_data_source_field"] == "preserved"
    assert result["data_sources"]["tables"][0]["future_table_field"] == {"value": 1}
    assert result["data_sources"]["tables"][0]["column_configs"][0]["future_column_field"] == "yes"


def test_json_round_trip_with_canonicalization_preserves_configuration():
    serialized = json.dumps(serialized_space_payload())

    reparsed = GenieSerializedSpace.from_serialized_space(serialized).canonicalize()
    round_tripped = GenieSerializedSpace.from_serialized_space(reparsed.to_serialized_space())

    assert [table.identifier for table in round_tripped.data_sources.tables] == [
        "catalog.schema.table_a",
        "catalog.schema.table_b",
        "catalog.schema.table_c",
    ]
    assert [column.column_name for column in round_tripped.data_sources.tables[1].column_configs] == [
        "column_a",
        "column_m",
        "column_z",
    ]


def test_version_two_is_accepted_and_unknown_versions_are_rejected():
    assert GenieSerializedSpace.model_validate({"version": 2}).version == 2

    with pytest.raises(ValidationError, match="Unsupported Genie serialized space version: 3"):
        GenieSerializedSpace.model_validate({"version": 3})


def test_mutations_return_copies_and_preserve_unrelated_configuration():
    payload = serialized_space_payload()
    payload["future_root_field"] = {"retained": True}
    space = GenieSerializedSpace.model_validate(payload)

    added = space.add_table(GenieTableConfig(identifier="catalog.schema.table_d"))
    removed = added.remove_table("catalog.schema.table_b")
    updated = removed.update_table(
        GenieTableConfig(
            identifier="catalog.schema.table_a",
            column_configs=[GenieColumnConfig(column_name="replacement_column")],
        )
    )

    assert [table.identifier for table in space.data_sources.tables] == [
        "catalog.schema.table_b",
        "catalog.schema.table_a",
        "catalog.schema.table_c",
    ]
    assert [table.identifier for table in updated.data_sources.tables] == [
        "catalog.schema.table_a",
        "catalog.schema.table_c",
        "catalog.schema.table_d",
    ]
    assert updated.data_sources.tables[0].column_configs[0].column_name == "replacement_column"
    assert updated.instructions == space.instructions
    assert updated.config == space.config
    assert updated.model_extra == {"future_root_field": {"retained": True}}


def test_table_mutations_reject_duplicate_and_missing_identifiers():
    space = GenieSerializedSpace.model_validate(serialized_space_payload())

    with pytest.raises(GenieConfigurationError, match="already exists"):
        space.add_table(GenieTableConfig(identifier="catalog.schema.table_a"))
    with pytest.raises(GenieConfigurationError, match="does not exist"):
        space.remove_table("catalog.schema.missing")
    with pytest.raises(GenieConfigurationError, match="does not exist"):
        space.update_table(GenieTableConfig(identifier="catalog.schema.missing"))


def test_instruction_and_example_mutations_preserve_other_configuration():
    space = GenieSerializedSpace.model_validate(serialized_space_payload())
    replacement_instructions = [GenieTextInstruction(id="replacement", content=["New instruction"])]

    instructions_updated = space.update_instructions(replacement_instructions)
    example_updated = instructions_updated.add_sql_example(
        GenieExampleQuestionSql(
            id="example-3",
            question=["Third question"],
            sql=["SELECT 3"],
            usage_guidance=["Third guidance"],
        )
    )

    assert [instruction.id for instruction in space.instructions.text_instructions] == ["text-2", "text-1"]
    assert [instruction.id for instruction in example_updated.instructions.text_instructions] == ["replacement"]
    assert [example.id for example in example_updated.instructions.example_question_sqls] == [
        "example-2",
        "example-1",
        "example-3",
    ]
    assert example_updated.data_sources == space.data_sources
    assert example_updated.config == space.config


def test_update_request_uses_typed_serialized_space_and_does_not_expose_etag():
    serialized_space = GenieSerializedSpace.model_validate({"version": 2})
    request = GenieSpaceUpdateRequest(serialized_space=serialized_space)

    assert "etag" not in GenieSpaceUpdateRequest.model_fields
    assert request.serialized_space is serialized_space