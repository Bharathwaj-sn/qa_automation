from frontend import streamlit_app


def test_schema_lookup_uses_the_v1_request_body_contract(monkeypatch):
    calls = []

    def fake_post(path, payload, timeout=streamlit_app.REQUEST_TIMEOUT):
        calls.append((path, payload, timeout))
        return {"schemas": [{"name": "qa"}]}

    monkeypatch.setattr(streamlit_app, "_post", fake_post)

    assert streamlit_app.get_schemas("main") == [{"name": "qa"}]
    assert calls == [
        (
            "/api/v1/databricks/schemas:lookup",
            {"catalog_name": "main"},
            streamlit_app.REQUEST_TIMEOUT,
        )
    ]


def test_payor_file_type_lookup_uses_the_v1_request_body_contract(monkeypatch):
    calls = []

    def fake_post(path, payload, timeout=streamlit_app.REQUEST_TIMEOUT):
        calls.append((path, payload, timeout))
        return {"file_types": ["claims"]}

    monkeypatch.setattr(streamlit_app, "_post", fake_post)

    assert streamlit_app.get_file_types("ABC") == ["claims"]
    assert calls == [
        (
            "/api/v1/payor-config/file-types:lookup",
            {"payor": "ABC"},
            streamlit_app.REQUEST_TIMEOUT,
        )
    ]


def test_validation_sql_operations_use_v1_action_endpoints(monkeypatch):
    calls = []

    def fake_post(path, payload, timeout=streamlit_app.REQUEST_TIMEOUT):
        calls.append((path, payload, timeout))
        return [] if path.endswith(":search") else {"validation_sql_id": "validation-1"}

    monkeypatch.setattr(streamlit_app, "_post", fake_post)

    assert streamlit_app.get_saved_validation_sql() == []
    assert streamlit_app.execute_saved_validation_sql("validation-1") == {"validation_sql_id": "validation-1"}
    assert calls == [
        ("/api/v1/qa/validation-sql:search", {}, streamlit_app.REQUEST_TIMEOUT),
        (
            "/api/v1/qa/validation-sql/validation-1:execute",
            {},
            streamlit_app.REQUEST_TIMEOUT,
        ),
    ]