from types import SimpleNamespace

import pytest

from app.config import Settings
from app.models.model_serving import ModelServingRequest
from app.services.databricks_model_serving_service import (
    DatabricksModelServingError,
    DatabricksModelServingService,
)


def test_predict_uses_configured_endpoint_and_normalizes_response():
    calls = []

    class FakeServingEndpoints:
        def query(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(predictions=[{"result": "passed"}], request_id="req-123")

    client = SimpleNamespace(serving_endpoints_data_plane=FakeServingEndpoints())
    service = DatabricksModelServingService(
        client=client,
        settings=Settings(databricks_serving_endpoint="qa-endpoint"),
    )

    response = service.predict(ModelServingRequest(inputs={"question": "test"}))

    assert service.client is client
    assert calls == [{"name": "qa-endpoint", "inputs": {"question": "test"}}]
    assert response.predictions == [{"result": "passed"}]
    assert response.request_id == "req-123"


def test_missing_endpoint_raises_clear_error():
    client = SimpleNamespace(serving_endpoints_data_plane=SimpleNamespace())
    service = DatabricksModelServingService(client=client, settings=Settings())

    with pytest.raises(DatabricksModelServingError, match="endpoint is not configured"):
        service.predict(ModelServingRequest(inputs={"question": "test"}))


def test_sdk_failure_becomes_application_error():
    class FailingServingEndpoints:
        def query(self, **kwargs):
            raise RuntimeError("endpoint unavailable")

    client = SimpleNamespace(serving_endpoints_data_plane=FailingServingEndpoints())
    service = DatabricksModelServingService(
        client=client,
        settings=Settings(databricks_serving_endpoint="qa-endpoint"),
    )

    with pytest.raises(DatabricksModelServingError, match="Model Serving request failed"):
        service.predict(ModelServingRequest(inputs={"question": "test"}))