from __future__ import annotations

from typing import Any

from databricks.sdk import WorkspaceClient

from app.config import Settings, get_settings
from app.models.model_serving import ModelServingRequest, ModelServingResponse


class DatabricksModelServingError(RuntimeError):
    pass


class DatabricksModelServingService:
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
    def _value(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    def predict(self, request: ModelServingRequest) -> ModelServingResponse:
        endpoint = self.settings.databricks_serving_endpoint
        if not endpoint:
            raise DatabricksModelServingError("Databricks serving endpoint is not configured.")

        try:
            response = self.client.serving_endpoints_data_plane.query(name=endpoint, inputs=request.inputs)
            predictions = self._value(response, "predictions")
            if predictions is None:
                predictions = self._value(response, "output")
            return ModelServingResponse(
                predictions=predictions,
                request_id=self._value(response, "request_id"),
            )
        except DatabricksModelServingError:
            raise
        except Exception as exc:
            raise DatabricksModelServingError("Databricks Model Serving request failed.") from exc