from __future__ import annotations

from typing import Any

from litellm import completion

from data_health_monitor.config import Settings, get_settings
from data_health_monitor.models.llm import LLMRequest, LLMResponse, LLMUsage


class LLMExecutionError(RuntimeError):
    pass


class LiteLLMService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @staticmethod
    def _value(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    @classmethod
    def _normalize_response(cls, response: Any) -> LLMResponse:
        choices = cls._value(response, "choices", []) or []
        choice = choices[0] if choices else None
        message = cls._value(choice, "message", {})
        content = cls._value(message, "content", "") or ""
        usage_data = cls._value(response, "usage")
        usage = None
        if usage_data is not None:
            usage = LLMUsage(
                prompt_tokens=cls._value(usage_data, "prompt_tokens"),
                completion_tokens=cls._value(usage_data, "completion_tokens"),
                total_tokens=cls._value(usage_data, "total_tokens"),
            )
        return LLMResponse(
            content=content,
            model=cls._value(response, "model"),
            usage=usage,
            finish_reason=cls._value(choice, "finish_reason"),
        )

    def chat(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.settings.litellm_model
        if not model:
            raise LLMExecutionError("No LiteLLM model is configured.")

        parameters: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            parameters["max_tokens"] = request.max_tokens
        if self.settings.litellm_api_base:
            parameters["api_base"] = self.settings.litellm_api_base
        if self.settings.litellm_api_key:
            parameters["api_key"] = self.settings.litellm_api_key

        try:
            response = completion(**parameters)
            return self._normalize_response(response)
        except LLMExecutionError:
            raise
        except Exception as exc:
            raise LLMExecutionError("LLM request failed.") from exc