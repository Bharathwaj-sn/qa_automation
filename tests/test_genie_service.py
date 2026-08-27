import json
from types import SimpleNamespace
from typing import cast

import pytest
from databricks.sdk import WorkspaceClient

from app.config import Settings
from app.models.genie import GenieSerializedSpace
from app.services.genie_service import GenieError, GenieService


def serialized_payload():
    return {
        "version": 2,
        "config": {"sample_questions": [{"id": "sample", "question": ["Question"]}]},
        "data_sources": {
            "tables": [
                {
                    "identifier": "catalog.schema.table_b",
                    "column_configs": [{"column_name": "z"}, {"column_name": "a"}],
                },
                {"identifier": "catalog.schema.table_a", "column_configs": []},
            ]
        },
        "instructions": {
            "text_instructions": [{"id": "text", "content": ["Instruction"]}],
            "example_question_sqls": [
                {
                    "id": "example",
                    "question": ["Question"],
                    "sql": ["SELECT 1"],
                    "usage_guidance": ["Guidance"],
                }
            ],
        },
        "future_root_field": {"retained": True},
    }


def sdk_space(serialized_space: str | None = None):
    return SimpleNamespace(
        space_id="space-123",
        title="Example space",
        description="Example description",
        warehouse_id="warehouse-123",
        parent_path="/Users/example",
        serialized_space=(
            json.dumps(serialized_payload()) if serialized_space is None else serialized_space
        ),
    )


def service_with(genie_api):
    return GenieService(
        client=cast(WorkspaceClient, SimpleNamespace(genie=genie_api)),
        settings=Settings(),
    )


def test_list_spaces_maps_metadata_without_fetching_serialized_configuration():
    list_calls = []
    get_calls = []
    genie_api = SimpleNamespace(
        list_spaces=lambda: list_calls.append(True)
        or SimpleNamespace(
            spaces=[
                SimpleNamespace(
                    space_id="space-a",
                    title="Space A",
                    description="Description A",
                    warehouse_id="warehouse-a",
                    parent_path="/Users/a",
                    serialized_space=None,
                ),
                SimpleNamespace(
                    space_id="space-b",
                    title="Space B",
                    description="Description B",
                    warehouse_id="warehouse-b",
                    parent_path="/Users/b",
                    serialized_space=None,
                ),
            ],
            next_page_token="abc123",
        ),
        get_space=lambda **kwargs: get_calls.append(kwargs),
    )

    result = service_with(genie_api).list_spaces()

    assert list_calls == [True]
    assert get_calls == []
    assert [(space.space_id, space.title, space.description, space.warehouse_id, space.parent_path) for space in result.spaces] == [
        ("space-a", "Space A", "Description A", "warehouse-a", "/Users/a"),
        ("space-b", "Space B", "Description B", "warehouse-b", "/Users/b"),
    ]
    assert result.next_page_token == "abc123"


@pytest.mark.parametrize("spaces", [None, []])
def test_list_spaces_handles_empty_responses_and_preserves_none_page_token(spaces):
    genie_api = SimpleNamespace(
        list_spaces=lambda: SimpleNamespace(spaces=spaces, next_page_token=None)
    )

    result = service_with(genie_api).list_spaces()

    assert result.spaces == []
    assert result.next_page_token is None


def test_list_spaces_converts_sdk_failure_to_chained_genie_error():
    genie_api = SimpleNamespace(
        list_spaces=lambda: (_ for _ in ()).throw(RuntimeError("sdk failed"))
    )

    with pytest.raises(GenieError, match="Unable to list Genie spaces") as error:
        service_with(genie_api).list_spaces()

    assert isinstance(error.value.__cause__, RuntimeError)


def test_list_spaces_rejects_missing_space_id():
    genie_api = SimpleNamespace(
        list_spaces=lambda: SimpleNamespace(
            spaces=[SimpleNamespace(space_id=None)],
            next_page_token=None,
        )
    )

    with pytest.raises(GenieError, match="did not include space_id") as error:
        service_with(genie_api).list_spaces()

    assert error.value.__cause__ is not None


def test_get_space_requests_serialized_configuration_and_returns_typed_model():
    calls = []
    genie_api = SimpleNamespace(get_space=lambda **kwargs: calls.append(kwargs) or sdk_space())

    space = service_with(genie_api).get_space("space-123")

    assert calls == [{"space_id": "space-123", "include_serialized_space": True}]
    assert isinstance(space.serialized_space, GenieSerializedSpace)
    assert space.serialized_space.data_sources.tables[0].identifier == "catalog.schema.table_b"


def test_create_space_canonicalizes_complete_configuration_and_passes_optional_description():
    calls = []
    genie_api = SimpleNamespace(create_space=lambda **kwargs: calls.append(kwargs) or sdk_space(kwargs["serialized_space"]))
    configuration = GenieSerializedSpace.model_validate(serialized_payload())

    space = service_with(genie_api).create_space(
        warehouse_id="warehouse-123",
        serialized_space=configuration,
        title="Example space",
        description="Example description",
    )

    request = calls[0]
    sent = json.loads(request["serialized_space"])
    assert request["warehouse_id"] == "warehouse-123"
    assert request["title"] == "Example space"
    assert request["description"] == "Example description"
    assert [table["identifier"] for table in sent["data_sources"]["tables"]] == [
        "catalog.schema.table_a",
        "catalog.schema.table_b",
    ]
    assert [column["column_name"] for column in sent["data_sources"]["tables"][1]["column_configs"]] == ["a", "z"]
    assert sent["future_root_field"] == {"retained": True}
    assert space.serialized_space is not None


def test_create_space_omits_none_description():
    calls = []
    genie_api = SimpleNamespace(create_space=lambda **kwargs: calls.append(kwargs) or sdk_space(kwargs["serialized_space"]))

    service_with(genie_api).create_space(
        warehouse_id="warehouse-123",
        serialized_space=GenieSerializedSpace.model_validate(serialized_payload()),
        title="Example space",
    )

    assert "description" not in calls[0]


def test_update_space_sends_full_canonicalized_configuration_without_etag():
    calls = []
    genie_api = SimpleNamespace(update_space=lambda **kwargs: calls.append(kwargs) or sdk_space(kwargs["serialized_space"]))
    configuration = GenieSerializedSpace.model_validate(serialized_payload())

    service_with(genie_api).update_space("space-123", configuration)

    request = calls[0]
    sent = json.loads(request["serialized_space"])
    assert request["space_id"] == "space-123"
    assert "etag" not in request
    assert [table["identifier"] for table in sent["data_sources"]["tables"]] == [
        "catalog.schema.table_a",
        "catalog.schema.table_b",
    ]
    assert sent["instructions"] == serialized_payload()["instructions"]
    assert sent["config"] == serialized_payload()["config"]
    assert sent["future_root_field"] == {"retained": True}


def test_trash_space_delegates_to_sdk():
    calls = []
    genie_api = SimpleNamespace(trash_space=lambda **kwargs: calls.append(kwargs))

    result = service_with(genie_api).trash_space("space-123")

    assert result is None
    assert calls == [{"space_id": "space-123"}]


@pytest.mark.parametrize("operation", ["get", "create", "update"])
def test_missing_serialized_space_response_raises_chained_error(operation):
    missing_response = sdk_space(serialized_space="")
    genie_api = SimpleNamespace(
        get_space=lambda **kwargs: missing_response,
        create_space=lambda **kwargs: missing_response,
        update_space=lambda **kwargs: missing_response,
    )
    service = service_with(genie_api)
    configuration = GenieSerializedSpace.model_validate(serialized_payload())

    with pytest.raises(GenieError, match="did not include serialized_space") as error:
        if operation == "get":
            service.get_space("space-123")
        elif operation == "create":
            service.create_space("warehouse-123", configuration, "Example space")
        else:
            service.update_space("space-123", configuration)

    assert error.value.__cause__ is not None


def test_sdk_and_invalid_serialized_space_failures_become_genie_errors():
    failing_api = SimpleNamespace(get_space=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sdk failed")))
    with pytest.raises(GenieError, match="Unable to retrieve") as sdk_error:
        service_with(failing_api).get_space("space-123")
    assert isinstance(sdk_error.value.__cause__, RuntimeError)

    invalid_api = SimpleNamespace(get_space=lambda **kwargs: sdk_space("not json"))
    with pytest.raises(GenieError, match="invalid serialized_space") as json_error:
        service_with(invalid_api).get_space("space-123")
    assert json_error.value.__cause__ is not None