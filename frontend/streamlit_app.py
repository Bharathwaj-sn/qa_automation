from __future__ import annotations

import json
from typing import Any

import requests
import streamlit as st
from requests import RequestException

API_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 30
GENIE_REQUEST_TIMEOUT = 20 * 60 + 30


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


def create_test_case(payload: dict[str, str]) -> dict[str, Any]:
    return _post("/api/test-cases", payload)


def get_payors() -> list[str]:
    return _get("/api/payor-config/payors").get("payors", [])


def get_file_types(payor: str) -> list[str]:
    return _get(f"/api/payor-config/{payor}/file-types").get("file_types", [])


def get_metadata_summary() -> dict[str, Any]:
    return _get("/api/metadata/summary")


def get_genie_space_status() -> dict[str, Any]:
    return _get("/api/genie-space/status")


def get_genie_context(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/api/qa/genie-context", payload)


def refresh_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/api/metadata/refresh", payload, timeout=60)


def generate_sql_context(payload: dict[str, Any]) -> None:
    try:
        with st.spinner(
            "Updating Genie context and waiting for SQL generation. Maximum wait: 20 minutes.",
            show_time=True,
        ):
            genie_space = _post(
                "/api/qa/genie-space",
                payload,
                timeout=GENIE_REQUEST_TIMEOUT,
            )
    except RequestException as error:
        st.error(_response_detail(error) or "Unable to create or update the Genie space.")
        return

    st.session_state.generated_sql_context = genie_space
    st.session_state.genie_chat_messages = [
        {"role": "user", "content": f"Generate validation SQL for {payload['test_case_id']}."},
        {"role": "assistant", "content": genie_space["sql"]},
    ]
    st.session_state.validation_sql_saved = False


def continue_genie_conversation(conversation_id: str, content: str) -> dict[str, Any]:
    return _post(
        f"/api/qa/genie/conversations/{conversation_id}/messages",
        {"content": content},
        timeout=GENIE_REQUEST_TIMEOUT,
    )


def save_validation_sql(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/api/qa/validation-sql", payload)


def get_saved_validation_sql() -> list[dict[str, Any]]:
    return _get("/api/qa/validation-sql")


def execute_saved_validation_sql(validation_sql_id: str) -> dict[str, Any]:
    return _post(f"/api/qa/validation-sql/{validation_sql_id}/execute", {})


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
        "genie_chat_messages": [],
        "validation_sql_saved": False,
        "genie_context_preview": None,
        "genie_context_preview_key": None,
        "test_case_execution_result": None,
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
        st.session_state.genie_chat_messages = []
        st.session_state.validation_sql_saved = False


def _handle_generation_schema_change(schema: str) -> None:
    if schema != st.session_state.selected_schema:
        st.session_state.selected_schema = schema
        st.session_state.generation_selections = []
        st.session_state.generated_sql_context = None
        st.session_state.genie_chat_messages = []
        st.session_state.validation_sql_saved = False


def render_metadata_page() -> None:
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
    st.header("Health Check Definitions")
    with st.expander("Add Health Check", expanded=False):
        with st.form("create_test_case"):
            pipeline = st.text_input("Pipeline")
            component = st.text_input("Component")
            test_scenario = st.text_area("Test scenario")
            target_object = st.text_input("Target object")
            input_data = st.text_area("Input data")
            validation_check = st.text_area("Validation check")
            expected_result = st.text_area("Expected result")
            submitted = st.form_submit_button("Create Health Check", type="primary")
        if submitted:
            payload = {
                "pipeline": pipeline,
                "component": component,
                "test_scenario": test_scenario,
                "target_object": target_object,
                "input_data": input_data,
                "validation_check": validation_check,
                "expected_result": expected_result,
            }
            if not all(value.strip() for value in payload.values()):
                st.error("Complete every health check field.")
            else:
                try:
                    created = create_test_case(payload)
                except RequestException as error:
                    st.error(_response_detail(error) or "Unable to create health check.")
                else:
                    st.session_state.selected_test_case = created
                    st.session_state.generated_sql_context = None
                    st.success(f"Created {created['test_case_id']}.")
                    st.rerun()

    try:
        test_cases = get_test_cases()
    except RequestException:
        st.error("Unable to retrieve health check definitions.")
        return
    if not test_cases:
        st.info("No health check definitions are available.")
        return

    labels = {case["test_case_id"]: f"{case['test_case_id']} - {case['component']}" for case in test_cases}
    selected_id = st.selectbox(
        "Select Health Check",
        list(labels),
        format_func=lambda test_case_id: labels.get(test_case_id, ""),
        key="test_case_picker",
    )
    selected_case = next(case for case in test_cases if case["test_case_id"] == selected_id)
    st.subheader("Health Check Details")
    st.write(f"**ID:** {selected_case['test_case_id']}")
    st.write(f"**Pipeline:** {selected_case['pipeline']}")
    st.write(f"**Component:** {selected_case['component']}")
    st.write(f"**Scenario:** {selected_case['test_scenario']}")
    st.write(f"**Validation:** {selected_case['validation_check']}")
    st.write(f"**Expected Result:** {selected_case['expected_result']}")
    if st.button("Use This Health Check", type="primary"):
        if st.session_state.selected_test_case != selected_case:
            st.session_state.selected_test_case = selected_case
            st.session_state.generated_sql_context = None
        st.success(f"Selected {selected_case['test_case_id']} for health check SQL generation.")


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
        st.subheader("Health Check")
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


def render_genie_context_preview(payload: dict[str, Any]) -> None:
    payload_key = json.dumps(payload, sort_keys=True)
    if st.session_state.genie_context_preview_key != payload_key:
        try:
            st.session_state.genie_context_preview = get_genie_context(payload)
            st.session_state.genie_context_preview_key = payload_key
        except RequestException as error:
            st.session_state.genie_context_preview = None
            st.session_state.genie_context_preview_key = None
            st.error(_response_detail(error) or "Unable to build the Genie context preview.")

    with st.expander("Raw Genie Context", expanded=False):
        if st.session_state.genie_context_preview:
            st.json(st.session_state.genie_context_preview)


def render_genie_chat() -> None:
    generation = st.session_state.generated_sql_context
    if not generation:
        return

    st.divider()
    st.subheader("Genie Refinement")
    st.caption(f"Conversation: {generation['conversation_id']}")
    for message in st.session_state.genie_chat_messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                st.code(message["content"], language="sql")
            else:
                st.write(message["content"])

    action_column, reset_column = st.columns(2)
    with action_column:
        if st.button("Save SQL", disabled=st.session_state.validation_sql_saved):
            try:
                with st.spinner("Saving generated SQL..."):
                    for selection in st.session_state.generation_selections:
                        save_validation_sql(
                            {
                                "test_case_id": st.session_state.selected_test_case["test_case_id"],
                                "target_table": (
                                    f"{st.session_state.selected_catalog}.{st.session_state.selected_schema}."
                                    f"{selection['table_name']}"
                                ),
                                "payor": selection["payor"],
                                "file_type": selection["file_type"],
                                "generated_sql": generation["sql"],
                                "genie_space_id": generation["space_id"],
                                "conversation_id": generation["conversation_id"],
                                "message_id": generation["message_id"],
                            }
                        )
            except RequestException as error:
                st.error(_response_detail(error) or "Unable to save validation SQL.")
            else:
                st.session_state.validation_sql_saved = True
                st.success("Validation SQL saved.")
    with reset_column:
        if st.button("Start New Conversation"):
            st.session_state.generated_sql_context = None
            st.session_state.genie_chat_messages = []
            st.session_state.validation_sql_saved = False
            st.rerun()

    prompt = st.chat_input("Describe how to refine the validation SQL")
    if prompt:
        st.session_state.genie_chat_messages.append({"role": "user", "content": prompt})
        try:
            with st.spinner("Waiting for Genie to refine the SQL. Maximum wait: 20 minutes.", show_time=True):
                response = continue_genie_conversation(generation["conversation_id"], prompt)
        except RequestException as error:
            st.error(_response_detail(error) or "Unable to continue Genie conversation.")
        else:
            st.session_state.generated_sql_context = response
            st.session_state.genie_chat_messages.append({"role": "assistant", "content": response["sql"]})
            st.session_state.validation_sql_saved = False
            st.rerun()


def render_sql_generation_page() -> None:
    st.header("Create Health Check SQL")
    try:
        genie_status = get_genie_space_status()
        if genie_status["status"] == "ready":
            st.caption(f"Genie space: {genie_status['title']} ({genie_status['space_id']})")
        else:
            st.caption(f"Genie space: {genie_status['title']} (pending creation)")
    except RequestException:
        st.warning("Unable to retrieve Genie space status.")

    test_case = st.session_state.selected_test_case
    if not test_case:
        st.warning("Please select a health check from the Health Check Definitions page.")
        return

    st.subheader("Selected Health Check")
    st.write(f"**{test_case['test_case_id']}**  {test_case['component']}")
    with st.expander("Health Check Details"):
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
        render_genie_context_preview(payload)
        if st.button("Generate Health Check SQL", type="primary"):
            generate_sql_context(payload)
        render_genie_chat()


def render_execution_page() -> None:
    st.header("Run Health Checks")
    try:
        saved_sql_items = get_saved_validation_sql()
    except RequestException as error:
        st.error(_response_detail(error) or "Unable to retrieve saved validation SQL.")
        return

    if not saved_sql_items:
        st.info("No saved validation SQL is available to test.")
        return

    st.subheader("Saved Health Checks")
    for saved_sql in saved_sql_items:
        test_case_column, table_column, scope_column, action_column = st.columns((2, 4, 3, 1))
        test_case_column.write(saved_sql["test_case_id"])
        table_column.write(saved_sql["target_table"])
        scope_column.write(f"{saved_sql['payor']} | {saved_sql['file_type']}")
        if action_column.button("Test", key=f"test_{saved_sql['validation_sql_id']}"):
            try:
                with st.spinner(f"Testing {saved_sql['target_table']}..."):
                    st.session_state.test_case_execution_result = execute_saved_validation_sql(
                        saved_sql["validation_sql_id"]
                    )
            except RequestException as error:
                st.error(_response_detail(error) or "Unable to execute saved validation SQL.")

        result = st.session_state.test_case_execution_result
        if result and result["validation_sql_id"] == saved_sql["validation_sql_id"]:
            st.success(
                f"{result['execution_status']}: {result['row_count']} row(s) returned."
            )
            if result["columns"]:
                rows = [dict(zip(result["columns"], row)) for row in result["rows"]]
                st.dataframe(rows, hide_index=True, use_container_width=True)
            else:
                st.json(result)


def main() -> None:
    st.set_page_config(page_title="Data Health Monitor", layout="wide")
    _initialize_state()
    st.title("Data Health Monitor")
    metadata_tab, test_cases_tab, generate_sql_tab, execution_tab = st.tabs(
        ["Metadata", "Health Check Definitions", "Create Health Check", "Run Health Checks"]
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