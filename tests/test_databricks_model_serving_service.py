from types import SimpleNamespace

import pytest

from data_health_monitor.config import Settings
from data_health_monitor.models.model_serving import ModelServingRequest
from data_health_monitor.services.databricks_model_serving_service import (
    DatabricksModelServingError,
    DatabricksModelServingService,
)


def request() -> ModelServingRequest:
    return ModelServingRequest(messages=[{"role": "user", "content": "Generate SQL"}], max_tokens=256)


def test_missing_profile_and_model_raise_clear_errors():
    with pytest.raises(DatabricksModelServingError, match="profile is not configured"):
        DatabricksModelServingService(settings=Settings(databricks_profile=None, databricks_serving_model="qa-model"))

    client = SimpleNamespace()
    with pytest.raises(DatabricksModelServingError, match="model is not configured"):
        DatabricksModelServingService(client=client, settings=Settings(databricks_serving_model=None))


def test_constructor_uses_oauth_profile_to_create_ai_gateway_client(monkeypatch):
    captured = {}

    class FakeConfig:
        host = "https://workspace.cloud.databricks.com"

        def __init__(self, profile):
            captured["profile"] = profile

        def oauth_token(self):
            return SimpleNamespace(access_token="oauth-secret")

    fake_client = SimpleNamespace()
    monkeypatch.setattr("data_health_monitor.services.databricks_model_serving_service.Config", FakeConfig)
    monkeypatch.setattr(
        "data_health_monitor.services.databricks_model_serving_service.OpenAI",
        lambda **kwargs: captured.update(kwargs) or fake_client,
    )

    service = DatabricksModelServingService(settings=Settings(databricks_profile="qa-profile", databricks_serving_model="qa-model"))

    assert service.client is fake_client
    assert captured == {
        "profile": "qa-profile",
        "api_key": "oauth-secret",
        "base_url": "https://workspace.cloud.databricks.com/ai-gateway/mlflow/v1",
    }


def test_predict_passes_chat_request_and_normalizes_response():
    calls = []
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
                    id="request-123",
                    choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 1"))],
                )
            )
        )
    )
    service = DatabricksModelServingService(client=client, settings=Settings(databricks_serving_model="qa-model"))

    response = service.predict(request())

    assert service.client is client
    assert calls == [{"model": "qa-model", "messages": [{"role": "user", "content": "Generate SQL"}], "max_tokens": 256}]
    assert response.predictions == "SELECT 1"
    assert response.request_id == "request-123"


def test_oauth_and_api_failures_do_not_expose_sensitive_details(monkeypatch):
    class FailingConfig:
        def __init__(self, profile):
            pass

        def oauth_token(self):
            raise RuntimeError("oauth-secret")

    monkeypatch.setattr("data_health_monitor.services.databricks_model_serving_service.Config", FailingConfig)
    with pytest.raises(DatabricksModelServingError, match="authentication failed") as oauth_error:
        DatabricksModelServingService(settings=Settings(databricks_profile="qa-profile", databricks_serving_model="qa-model"))
    assert "oauth-secret" not in str(oauth_error.value)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("oauth-secret")))))
    service = DatabricksModelServingService(client=client, settings=Settings(databricks_serving_model="qa-model"))
    with pytest.raises(DatabricksModelServingError, match="AI Gateway request failed") as api_error:
        service.predict(request())
    assert "oauth-secret" not in str(api_error.value)