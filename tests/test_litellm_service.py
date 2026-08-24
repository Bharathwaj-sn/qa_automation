from types import SimpleNamespace

import pytest

from app.config import Settings
from app.models.llm import LLMMessage, LLMRequest
from app.services.litellm_service import LLMExecutionError, LiteLLMService


def test_chat_passes_request_and_normalizes_response(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model="openai/gpt-test",
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hello"), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, total_tokens=7),
        )

    monkeypatch.setattr("app.services.litellm_service.completion", fake_completion)
    service = LiteLLMService(settings=Settings(litellm_model="openai/gpt-default"))

    response = service.chat(
        LLMRequest(
            messages=[LLMMessage(role="user", content="Hi")],
            temperature=0.3,
            max_tokens=50,
        )
    )

    assert captured == {
        "model": "openai/gpt-default",
        "messages": [{"role": "user", "content": "Hi"}],
        "temperature": 0.3,
        "max_tokens": 50,
    }
    assert response.content == "Hello"
    assert response.model == "openai/gpt-test"
    assert response.finish_reason == "stop"
    assert response.usage.prompt_tokens == 5
    assert response.usage.completion_tokens == 2
    assert response.usage.total_tokens == 7


def test_request_model_overrides_configured_model(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.services.litellm_service.completion",
        lambda **kwargs: captured.update(kwargs) or {"choices": [{"message": {"content": "ok"}}]},
    )
    service = LiteLLMService(settings=Settings(litellm_model="openai/gpt-default"))

    service.chat(LLMRequest(model="anthropic/claude-test", messages=[LLMMessage(role="user", content="Hi")]))

    assert captured["model"] == "anthropic/claude-test"
    assert "max_tokens" not in captured


def test_provider_error_becomes_application_error(monkeypatch):
    def failing_completion(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.services.litellm_service.completion", failing_completion)
    service = LiteLLMService(settings=Settings(litellm_model="openai/gpt-default"))

    with pytest.raises(LLMExecutionError, match="LLM request failed"):
        service.chat(LLMRequest(messages=[LLMMessage(role="user", content="Hi")]))


def test_request_model_overrides_default_and_max_tokens_is_optional(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.services.litellm_service.completion",
        lambda **kwargs: captured.update(kwargs) or {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
    )
    service = LiteLLMService(Settings(litellm_model="configured-model"))

    service.chat(LLMRequest(model="request-model", messages=[LLMMessage(role="user", content="Hi")]))

    assert captured["model"] == "request-model"
    assert "max_tokens" not in captured


def test_provider_error_becomes_llm_execution_error(monkeypatch):
    monkeypatch.setattr("app.services.litellm_service.completion", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("secret failure")))
    service = LiteLLMService(Settings(litellm_model="configured-model"))

    with pytest.raises(LLMExecutionError, match="LLM request failed"):
        service.chat(LLMRequest(messages=[LLMMessage(role="user", content="Hi")]))