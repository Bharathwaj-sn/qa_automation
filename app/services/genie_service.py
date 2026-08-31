from __future__ import annotations

from typing import Any

from databricks.sdk import WorkspaceClient

from app.config import Settings, get_settings
from app.models.genie import (
    GenieSQLGeneration,
    GenieSerializedSpace,
    GenieSpace,
    GenieSpaceListResponse,
    GenieSpaceSummary,
)


class GenieError(RuntimeError):
    pass


class GenieService:
    def __init__(
        self,
        client: WorkspaceClient | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()

        if client:
            self.client = client
        elif self.settings.databricks_profile:
            self.client = WorkspaceClient(profile=self.settings.databricks_profile)
        else:
            self.client = WorkspaceClient()

    @staticmethod
    def _to_genie_space(response: Any) -> GenieSpace:
        space_id = getattr(response, "space_id", None)
        if not space_id:
            missing_space_id_error = ValueError("Genie API response did not include space_id.")
            raise GenieError("Genie API response did not include space_id.") from missing_space_id_error

        serialized_space = getattr(response, "serialized_space", None)
        if not serialized_space:
            missing_space_error = ValueError("Genie API response did not include serialized_space.")
            raise GenieError("Genie API response did not include serialized_space.") from missing_space_error

        try:
            configuration = GenieSerializedSpace.from_serialized_space(serialized_space)
        except Exception as exc:
            raise GenieError("Genie API response contained invalid serialized_space.") from exc

        return GenieSpace(
            space_id=space_id,
            title=getattr(response, "title", None),
            description=getattr(response, "description", None),
            warehouse_id=getattr(response, "warehouse_id", None),
            parent_path=getattr(response, "parent_path", None),
            serialized_space=configuration,
        )

    @staticmethod
    def _to_genie_space_summary(response: Any) -> GenieSpaceSummary:
        space_id = getattr(response, "space_id", None)
        if not space_id:
            missing_space_id_error = ValueError("Genie API response did not include space_id.")
            raise GenieError("Genie API response did not include space_id.") from missing_space_id_error

        return GenieSpaceSummary(
            space_id=space_id,
            title=getattr(response, "title", None),
            description=getattr(response, "description", None),
            warehouse_id=getattr(response, "warehouse_id", None),
            parent_path=getattr(response, "parent_path", None),
        )

    def list_spaces(self) -> GenieSpaceListResponse:
        try:
            spaces = []
            page_token = None
            while True:
                response = (
                    self.client.genie.list_spaces()
                    if page_token is None
                    else self.client.genie.list_spaces(page_token=page_token)
                )
                spaces.extend(getattr(response, "spaces", None) or [])
                page_token = getattr(response, "next_page_token", None)
                if not page_token:
                    break
            return GenieSpaceListResponse(spaces=[self._to_genie_space_summary(space) for space in spaces])
        except GenieError:
            raise
        except Exception as exc:
            raise GenieError("Unable to list Genie spaces.") from exc

    def get_space(self, space_id: str) -> GenieSpace:
        try:
            response = self.client.genie.get_space(
                space_id=space_id,
                include_serialized_space=True,
            )
            return self._to_genie_space(response)
        except GenieError:
            raise
        except Exception as exc:
            raise GenieError("Unable to retrieve Genie space.") from exc

    def create_space(
        self,
        warehouse_id: str,
        serialized_space: GenieSerializedSpace,
        title: str,
        description: str | None = None,
    ) -> GenieSpace:
        request = {
            "warehouse_id": warehouse_id,
            "serialized_space": serialized_space.canonicalize().to_serialized_space(),
            "title": title,
        }
        if description is not None:
            request["description"] = description

        try:
            response = self.client.genie.create_space(**request)
            return self._to_genie_space(response)
        except GenieError:
            raise
        except Exception as exc:
            raise GenieError("Unable to create Genie space.") from exc

    def update_space(
        self,
        space_id: str,
        serialized_space: GenieSerializedSpace,
    ) -> GenieSpace:
        try:
            response = self.client.genie.update_space(
                space_id=space_id,
                serialized_space=serialized_space.canonicalize().to_serialized_space(),
            )
            return self._to_genie_space(response)
        except GenieError:
            raise
        except Exception as exc:
            raise GenieError("Unable to update Genie space.") from exc

    @staticmethod
    def _to_sql_generation(response: Any, space_id: str) -> GenieSQLGeneration:
        sql = next(
            (
                query.query
                for attachment in getattr(response, "attachments", None) or []
                if (query := getattr(attachment, "query", None)) and getattr(query, "query", None)
            ),
            None,
        )
        if not sql:
            raise GenieError("Genie response did not contain generated SQL.")

        conversation_id = getattr(response, "conversation_id", None)
        message_id = getattr(response, "message_id", None)
        if not conversation_id or not message_id:
            raise GenieError("Genie response did not include conversation_id or message_id.")
        return GenieSQLGeneration(
            space_id=space_id,
            conversation_id=conversation_id,
            message_id=message_id,
            sql=sql,
        )

    def start_conversation_and_wait(self, space_id: str, content: str) -> GenieSQLGeneration:
        try:
            response = self.client.genie.start_conversation_and_wait(
                space_id=space_id,
                content=content,
            )
            return self._to_sql_generation(response, space_id)
        except GenieError:
            raise
        except Exception as exc:
            raise GenieError("Unable to start Genie conversation.") from exc

    def create_message_and_wait(
        self,
        space_id: str,
        conversation_id: str,
        content: str,
    ) -> GenieSQLGeneration:
        try:
            response = self.client.genie.create_message_and_wait(
                space_id=space_id,
                conversation_id=conversation_id,
                content=content,
            )
            return self._to_sql_generation(response, space_id)
        except GenieError:
            raise
        except Exception as exc:
            raise GenieError("Unable to send message to Genie space.") from exc

    def trash_space(self, space_id: str) -> None:
        try:
            self.client.genie.trash_space(space_id=space_id)
        except Exception as exc:
            raise GenieError("Unable to trash Genie space.") from exc