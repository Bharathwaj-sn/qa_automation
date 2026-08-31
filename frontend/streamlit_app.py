from __future__ import annotations

from typing import Any

import requests
import streamlit as st
from requests import RequestException

API_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 30


def _get(path: str, timeout: int = REQUEST_TIMEOUT) -> Any:
    response = requests.get(f"{API_BASE_URL}{path}", timeout=timeout)
    response.raise_for_status()
    return response.json()


def _post(path: str, payload: dict[str, Any], timeout: int = REQUEST_TIMEOUT) -> Any:
    response = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def get_catalogs() -> list[dict[str, Any]]:
    return _get("/api/databricks/catalogs").get("catalogs", [])


def get_schemas(catalog: str) -> list[dict[str, Any]]:
    return _get(f"/api/databricks/catalogs/{catalog}/schemas").get("schemas", [])


def get_schema_objects(catalog: str, schema: str) -> dict[str, Any]:
    return _get(f"/api/databricks/catalogs/{catalog}/schemas/{schema}/objects")


def get_table_metadata(catalog: str, schema: str, table: str) -> dict[str, Any]:
    return _get(f"/api/databricks/catalogs/{catalog}/schemas/{schema}/tables/{table}")


def get_test_cases() -> list[dict[str, Any]]:
    return _get("/api/test-cases")


def get_payors() -> list[str]:
    return _get("/api/payor-config/payors").get("payors", [])


def get_file_types(payor: str) -> list[str]:
    return _get(f"/api/payor-config/{payor}/file-types").get("file_types", [])


def get_metadata_summary() -> dict[str, Any]:
    return _get("/api/metadata/summary")


def refresh_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/api/metadata/refresh", payload, timeout=60)


def generate_sql_context(payload: dict[str, Any]) -> None:
    try:
        context = _post("/api/qa/context", payload)
    except RequestException as error:
        st.error(_response_detail(error) or "Unable to build QA context.")
        return

    st.session_state.generated_sql_context = context
    st.success("QA context generated.")
    st.json(context)


def _response_detail(error: RequestException) -> str | None:
    response = getattr(error, "response", None)
    if response is None:
        return None
    try:
        return response.json().get("detail")
    except ValueError:
        return None


def _initialize_state() -> None:
    defaults: dict[str, Any] = {
        "selected_test_case": None,
        "selected_catalog": "",
        "selected_schema": "",
        "generation_selections": [],
        "generated_sql_context": None,
        "metadata_catalog": "",
        "metadata_schema": "",
        "metadata_table": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _select_option(label: str, values: list[str], placeholder: str, key: str) -> str:
    options = [placeholder, *values]
    current = st.session_state.get(key, "")
    index = options.index(current) if current in options else 0
    selected = st.selectbox(label, options, index=index, key=f"{key}_control")
    return "" if selected == placeholder else selected


def _handle_generation_catalog_change(catalog: str) -> None:
    if catalog != st.session_state.selected_catalog:
        st.session_state.selected_catalog = catalog
        st.session_state.selected_schema = ""
        st.session_state.generation_selections = []
        st.session_state.generated_sql_context = None


def _handle_generation_schema_change(schema: str) -> None:
    if schema != st.session_state.selected_schema:
        st.session_state.selected_schema = schema
        st.session_state.generation_selections = []
        st.session_state.generated_sql_context = None


def render_metadata_page() -> None:
    st.header("Metadata Management")
    st.subheader("Metadata Refresh")
    scope = st.radio("Scope", ("Catalog", "Schema", "Table"), horizontal=True, key="metadata_scope").lower()

    try:
        catalog_names = [catalog["name"] for catalog in get_catalogs()]
    except RequestException:
        catalog_names = []
        st.error("Unable to retrieve catalogs.")

    catalog = _select_option("Catalog", catalog_names, "Select a catalog", "metadata_catalog")
    if catalog != st.session_state.metadata_catalog:
        st.session_state.metadata_catalog = catalog
        st.session_state.metadata_schema = ""
        st.session_state.metadata_table = ""

    schema = ""
    if scope in ("schema", "table") and catalog:
        try:
            schema_names = [schema["name"] for schema in get_schemas(catalog)]
        except RequestException:
            schema_names = []
            st.error("Unable to retrieve schemas.")
        schema = _select_option("Schema", schema_names, "Select a schema", "metadata_schema")
        if schema != st.session_state.metadata_schema:
            st.session_state.metadata_schema = schema
            st.session_state.metadata_table = ""

    table = ""
    if scope == "table" and catalog and schema:
        try:
            table_names = [table["name"] for table in get_schema_objects(catalog, schema).get("tables", [])]
        except RequestException:
            table_names = []
            st.error("Unable to retrieve tables.")
        table = _select_option("Table", table_names, "Select a table", "metadata_table")
        st.session_state.metadata_table = table

    can_refresh = bool(catalog) and (scope == "catalog" or bool(schema)) and (scope != "table" or bool(table))
    if st.button("Refresh Metadata", disabled=not can_refresh, type="primary"):
        payload: dict[str, Any] = {"scope_type": scope, "catalog_name": catalog}
        if scope in ("schema", "table"):
            payload["schema_name"] = schema
        if scope == "table":
            payload["table_name"] = table
        try:
            response = refresh_metadata(payload)
        except RequestException:
            st.error("Unable to refresh metadata.")
        else:
            refresh = response.get("refresh", {})
            refresh_scope = refresh.get("scope", {})
            scope_text = ".".join(
                value
                for value in (
                    refresh_scope.get("catalog_name"),
                    refresh_scope.get("schema_name"),
                    refresh_scope.get("table_name"),
                )
                if value
            )
            st.success("Metadata refreshed successfully.")
            st.write(f"Scope: {scope_text}")
            st.write(f"Status: {refresh.get('status', 'UNKNOWN')}")
            st.write(f"Refreshed at: {refresh.get('refreshed_at', 'Unknown')}")

    st.divider()
    try:
        summary = get_metadata_summary()
    except RequestException as error:
        if _response_detail(error):
            st.info("No metadata summary is available yet.")
    else:
        columns = st.columns(4)
        columns[0].metric("Catalogs", summary.get("catalog_count", 0))
        columns[1].metric("Schemas", summary.get("schema_count", 0))
        columns[2].metric("Tables", summary.get("table_count", 0))
        columns[3].metric("Volumes", summary.get("volume_count", 0))


def render_test_cases_page() -> None:
    st.header("Test Cases")
    try:
        test_cases = get_test_cases()
    except RequestException:
        st.error("Unable to retrieve test cases.")
        return
    if not test_cases:
        st.info("No saved test cases are available.")
        return

    labels = {case["test_case_id"]: f"{case['test_case_id']} - {case['component']}" for case in test_cases}
    selected_id = st.selectbox("Select Test Case", list(labels), format_func=labels.get, key="test_case_picker")
    selected_case = next(case for case in test_cases if case["test_case_id"] == selected_id)
    st.subheader("Test Case Details")
    st.write(f"**ID:** {selected_case['test_case_id']}")
    st.write(f"**Pipeline:** {selected_case['pipeline']}")
    st.write(f"**Component:** {selected_case['component']}")
    st.write(f"**Scenario:** {selected_case['test_scenario']}")
    st.write(f"**Validation:** {selected_case['validation_check']}")
    st.write(f"**Expected Result:** {selected_case['expected_result']}")
    if st.button("Use This Test Case", type="primary"):
        if st.session_state.selected_test_case != selected_case:
            st.session_state.selected_test_case = selected_case
            st.session_state.generated_sql_context = None
        st.success(f"Selected {selected_case['test_case_id']} for SQL generation.")


def _build_generation_payload() -> dict[str, Any]:
    return {
        "test_case_id": st.session_state.selected_test_case["test_case_id"],
        "catalog": st.session_state.selected_catalog,
        "schema": st.session_state.selected_schema,
        "selections": st.session_state.generation_selections,
    }


def render_context_preview(payload: dict[str, Any]) -> None:
    with st.expander("Context Preview", expanded=True):
        test_case = st.session_state.selected_test_case
        st.subheader("Test Case")
        st.write(f"**ID:** {test_case['test_case_id']}")
        st.write(f"**Scenario:** {test_case['test_scenario']}")
        st.write(f"**Validation Check:** {test_case['validation_check']}")
        st.write(f"**Expected Result:** {test_case['expected_result']}")
        st.subheader("Technical Scope")
        st.write(f"**Catalog:** {payload['catalog']}")
        st.write(f"**Schema:** {payload['schema']}")
        st.subheader("Selected Configurations")
        st.dataframe(payload["selections"], hide_index=True, use_container_width=True)
    with st.expander("Context Request"):
        st.json(payload)


def render_sql_generation_page() -> None:
    st.header("Generate SQL")
    test_case = st.session_state.selected_test_case
    if not test_case:
        st.warning("Please select a test case from the Test Cases page.")
        return

    st.subheader("Selected Test Case")
    st.write(f"**{test_case['test_case_id']}**  {test_case['component']}")
    with st.expander("Test Case Details"):
        st.write(f"**Scenario:** {test_case['test_scenario']}")
        st.write(f"**Validation Check:** {test_case['validation_check']}")
        st.write(f"**Expected Result:** {test_case['expected_result']}")

    st.divider()
    try:
        catalog_names = [catalog["name"] for catalog in get_catalogs()]
    except RequestException:
        catalog_names = []
        st.error("Unable to retrieve catalogs.")
    catalog = _select_option("Step 2: Catalog", catalog_names, "Select a catalog", "selected_catalog")
    _handle_generation_catalog_change(catalog)

    schema = ""
    if catalog:
        try:
            schema_names = [schema["name"] for schema in get_schemas(catalog)]
        except RequestException:
            schema_names = []
            st.error("Unable to retrieve schemas.")
        schema = _select_option("Step 3: Schema", schema_names, "Select a schema", "selected_schema")
        _handle_generation_schema_change(schema)

    available_tables: list[str] = []
    if schema:
        try:
            available_tables = [table["name"] for table in get_schema_objects(catalog, schema).get("tables", [])]
        except RequestException:
            st.error("Unable to retrieve tables.")
    st.subheader("Step 4: Add Target Configuration")
    try:
        available_payors = get_payors()
    except RequestException:
        available_payors = []
        st.error("Unable to retrieve payors.")

    table_column, payor_column, file_type_column = st.columns(3)
    with table_column:
        selected_table = _select_option("Target table", available_tables, "Select a table", "generation_table")
    with payor_column:
        selected_payor = _select_option("Payor", available_payors, "Select a payor", "generation_payor")
    file_types: list[str] = []
    if selected_payor:
        try:
            file_types = get_file_types(selected_payor)
        except RequestException:
            st.error("Unable to retrieve file types.")
    with file_type_column:
        selected_file_type = _select_option("File type", file_types, "Select a file type", "generation_file_type")

    selection = {
        "table_name": selected_table,
        "payor": selected_payor,
        "file_type": selected_file_type,
    }
    if st.button("Add configuration", disabled=not all(selection.values())):
        if selection in st.session_state.generation_selections:
            st.warning("This target configuration is already selected.")
        else:
            st.session_state.generation_selections.append(selection)
            st.session_state.generated_sql_context = None

    if st.session_state.generation_selections:
        st.subheader("Configurations to Validate")
        for index, selected_configuration in enumerate(st.session_state.generation_selections):
            details, remove = st.columns((6, 1))
            details.write(
                f"{selected_configuration['table_name']} | {selected_configuration['payor']} | "
                f"{selected_configuration['file_type']}"
            )
            if remove.button("Remove", key=f"remove_configuration_{index}"):
                st.session_state.generation_selections.pop(index)
                st.session_state.generated_sql_context = None
                st.rerun()

    problems: list[str] = []
    if not catalog:
        problems.append("Select a catalog.")
    if not schema:
        problems.append("Select a schema.")
    if not st.session_state.generation_selections:
        problems.append("Add at least one target configuration.")
    for problem in problems:
        st.warning(problem)

    if not problems:
        payload = _build_generation_payload()
        render_context_preview(payload)
        if st.button("Generate SQL", type="primary"):
            generate_sql_context(payload)


def render_execution_page() -> None:
    st.header("Execution")
    st.info("SQL execution will be available in the next phase.")


def main() -> None:
    st.set_page_config(page_title="QA Automation", layout="wide")
    _initialize_state()
    st.title("QA Automation")
    metadata_tab, test_cases_tab, generate_sql_tab, execution_tab = st.tabs(
        ["Metadata", "Test Cases", "Generate SQL", "Execution"]
    )
    with metadata_tab:
        render_metadata_page()
    with test_cases_tab:
        render_test_cases_page()
    with generate_sql_tab:
        render_sql_generation_page()
    with execution_tab:
        render_execution_page()


main()