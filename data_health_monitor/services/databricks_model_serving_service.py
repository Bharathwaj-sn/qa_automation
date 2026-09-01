from __future__ import annotations

from typing import cast

from databricks.sdk.core import Config
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from data_health_monitor.config import Settings, get_settings
from data_health_monitor.models.model_serving import ModelServingRequest, ModelServingResponse


class DatabricksModelServingError(RuntimeError):
    pass


class DatabricksModelServingService:
    def __init__(
        self,
        client: OpenAI | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        if client:
            self.client = client

            if not self.settings.databricks_serving_model:
                raise DatabricksModelServingError("Databricks serving model is not configured.")
            self.model = self.settings.databricks_serving_model
            return

        profile = self.settings.databricks_profile
        if not profile:
            raise DatabricksModelServingError("Databricks profile is not configured.")
        if not self.settings.databricks_serving_model:
            raise DatabricksModelServingError("Databricks serving model is not configured.")

        try:
            config = Config(profile=profile)
            token = config.oauth_token().access_token
            self.client = OpenAI(
                api_key=token,
                base_url=f"{config.host}/ai-gateway/mlflow/v1",
            )
        except Exception as exc:
            raise DatabricksModelServingError("Databricks model serving authentication failed.") from exc

        self.model = self.settings.databricks_serving_model

    def predict(self, request: ModelServingRequest) -> ModelServingResponse:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=cast(
                    list[ChatCompletionMessageParam],
                    [message.model_dump() for message in request.messages],
                ),
                max_tokens=request.max_tokens,
            )
            choices = getattr(response, "choices", None) or []
            if not choices:
                raise ValueError("AI Gateway response did not contain a completion.")
            content = getattr(getattr(choices[0], "message", None), "content", None)
            if content is None:
                raise ValueError("AI Gateway response did not contain message content.")
            return ModelServingResponse(
                predictions=content,
                request_id=getattr(response, "id", None),
            )
        except Exception as exc:
            raise DatabricksModelServingError("Databricks AI Gateway request failed.") from exc