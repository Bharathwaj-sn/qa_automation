from threading import Lock
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.models.genie import GenieSQLGeneration, GenieSerializedSpace, GenieSpace, GenieSpaceListResponse, GenieSpaceSummary
from app.services.genie_space_coordinator import GenieSpaceConfigurationError, GenieSpaceCoordinator


class FakeGenieService:
    def __init__(self, spaces=None):
        self.spaces = spaces or []
        self.get_calls = []
        self.create_calls = []
        self.update_calls = []
        self.start_conversation_calls = []

    def get_space(self, space_id):
        self.get_calls.append(space_id)
        return GenieSpace(space_id=space_id, serialized_space=GenieSerializedSpace(version=2))

    def list_spaces(self):
        return GenieSpaceListResponse(spaces=self.spaces)

    def create_space(self, warehouse_id, serialized_space, title):
        self.create_calls.append((warehouse_id, serialized_space, title))
        return GenieSpace(space_id="created-space", title=title, serialized_space=serialized_space)

    def update_space(self, space_id, serialized_space):
        self.update_calls.append((space_id, serialized_space))
        return GenieSpace(space_id=space_id, serialized_space=serialized_space)

    def start_conversation_and_wait(self, space_id, content):
        self.start_conversation_calls.append((space_id, content))
        return GenieSQLGeneration(
            space_id=space_id,
            conversation_id="conversation-1",
            message_id="message-1",
            sql="SELECT 1",
        )


def runtime_state():
    return SimpleNamespace(genie_space_id=None, genie_space_status="pending_creation", genie_space_lock=Lock())


def test_resolve_uses_configured_space_id():
    service = FakeGenieService()
    state = runtime_state()

    GenieSpaceCoordinator(service, Settings(genie_space_id="configured", genie_space_title="QA"), state).resolve()

    assert service.get_calls == ["configured"]
    assert state.genie_space_id == "configured"
    assert state.genie_space_status == "ready"


def test_resolve_uses_one_exact_title_match_or_defers_creation():
    matched = GenieSpaceSummary(space_id="matched", title="QA")
    state = runtime_state()
    GenieSpaceCoordinator(FakeGenieService([matched]), Settings(genie_space_title="QA"), state).resolve()

    assert state.genie_space_id == "matched"

    pending_state = runtime_state()
    GenieSpaceCoordinator(FakeGenieService(), Settings(genie_space_title="QA"), pending_state).resolve()

    assert pending_state.genie_space_id is None
    assert pending_state.genie_space_status == "pending_creation"


def test_resolve_rejects_missing_title_and_duplicate_title_matches():
    with pytest.raises(GenieSpaceConfigurationError, match="GENIE_SPACE_TITLE"):
        GenieSpaceCoordinator(
            FakeGenieService(),
            Settings(genie_space_title=None),
            runtime_state(),
        ).resolve()

    duplicate_spaces = [
        GenieSpaceSummary(space_id="one", title="QA"),
        GenieSpaceSummary(space_id="two", title="QA"),
    ]
    with pytest.raises(GenieSpaceConfigurationError, match="Multiple"):
        GenieSpaceCoordinator(FakeGenieService(duplicate_spaces), Settings(genie_space_title="QA"), runtime_state()).resolve()


def test_apply_context_creates_once_then_updates_the_runtime_resolved_space():
    service = FakeGenieService()
    state = runtime_state()
    coordinator = GenieSpaceCoordinator(
        service,
        Settings(genie_space_title="QA", databricks_warehouse_id="warehouse"),
        state,
    )
    context = GenieSerializedSpace(version=2)

    created = coordinator.apply_context(context)
    updated = coordinator.apply_context(context)

    assert created.space_id == "created-space"
    assert updated.space_id == "created-space"
    assert len(service.create_calls) == 1
    assert service.update_calls == [("created-space", context)]


def test_generate_sql_updates_the_space_before_starting_a_conversation():
    service = FakeGenieService()
    state = runtime_state()
    state.genie_space_id = "existing-space"
    coordinator = GenieSpaceCoordinator(service, Settings(genie_space_title="QA"), state)

    result = coordinator.generate_sql(GenieSerializedSpace(version=2), "Generate validation SQL for test case TC1.")

    assert service.update_calls == [("existing-space", GenieSerializedSpace(version=2))]
    assert service.start_conversation_calls == [
        ("existing-space", "Generate validation SQL for test case TC1.")
    ]
    assert result.sql == "SELECT 1"


def test_generate_sql_does_not_start_a_conversation_when_context_update_fails():
    class FailingUpdateGenieService(FakeGenieService):
        def update_space(self, space_id, serialized_space):
            raise RuntimeError("update failed")

    service = FailingUpdateGenieService()
    state = runtime_state()
    state.genie_space_id = "existing-space"
    coordinator = GenieSpaceCoordinator(service, Settings(genie_space_title="QA"), state)

    with pytest.raises(RuntimeError, match="update failed"):
        coordinator.generate_sql(GenieSerializedSpace(version=2), "Generate validation SQL for test case TC1.")

    assert service.start_conversation_calls == []