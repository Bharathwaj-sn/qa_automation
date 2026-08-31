from __future__ import annotations

from typing import Any

from app.config import Settings
from app.models.genie import GenieSerializedSpace, GenieSpace
from app.services.genie_service import GenieService


class GenieSpaceConfigurationError(RuntimeError):
    pass


class GenieSpaceCoordinator:
    def __init__(self, genie_service: GenieService, settings: Settings, runtime_state: Any):
        self.genie_service = genie_service
        self.settings = settings
        self.runtime_state = runtime_state

    def resolve(self) -> None:
        title = (self.settings.genie_space_title or "").strip()
        if not title:
            raise GenieSpaceConfigurationError("GENIE_SPACE_TITLE must be configured.")

        configured_id = (self.settings.genie_space_id or "").strip()
        if configured_id:
            self.genie_service.get_space(configured_id)
            self.runtime_state.genie_space_id = configured_id
            self.runtime_state.genie_space_status = "ready"
            return

        matches = [space for space in self.genie_service.list_spaces().spaces if space.title == title]
        if len(matches) > 1:
            raise GenieSpaceConfigurationError(f"Multiple Genie spaces have the configured title '{title}'.")
        if matches:
            self.runtime_state.genie_space_id = matches[0].space_id
            self.runtime_state.genie_space_status = "ready"
        else:
            self.runtime_state.genie_space_id = None
            self.runtime_state.genie_space_status = "pending_creation"

    def status(self) -> dict[str, str | None]:
        return {
            "space_id": getattr(self.runtime_state, "genie_space_id", None),
            "title": self.settings.genie_space_title,
            "status": getattr(self.runtime_state, "genie_space_status", "pending_creation"),
        }

    def apply_context(self, serialized_space: GenieSerializedSpace) -> GenieSpace:
        with self.runtime_state.genie_space_lock:
            space_id = self.runtime_state.genie_space_id
            if space_id:
                space = self.genie_service.update_space(space_id, serialized_space)
                self.runtime_state.genie_space_status = "ready"
                return space

            warehouse_id = (self.settings.databricks_warehouse_id or "").strip()
            if not warehouse_id:
                raise GenieSpaceConfigurationError(
                    "DATABRICKS_WAREHOUSE_ID must be configured before creating the Genie space."
                )
            title = (self.settings.genie_space_title or "").strip()
            if not title:
                raise GenieSpaceConfigurationError("GENIE_SPACE_TITLE must be configured.")
            space = self.genie_service.create_space(
                warehouse_id=warehouse_id,
                serialized_space=serialized_space,
                title=title,
            )
            self.runtime_state.genie_space_id = space.space_id
            self.runtime_state.genie_space_status = "ready"
            return space