from __future__ import annotations

import requests
import streamlit as st
from requests import RequestException

API_BASE_URL = "http://127.0.0.1:8000"


def get_catalogs():
    try:
        resp = requests.get(f"{API_BASE_URL}/api/databricks/catalogs", timeout=30)
        resp.raise_for_status()
        return resp.json().get("catalogs", [])
    except RequestException:
        raise


def get_schemas(catalog: str):
    try:
        resp = requests.get(f"{API_BASE_URL}/api/databricks/catalogs/{catalog}/schemas", timeout=30)
        resp.raise_for_status()
        return resp.json().get("schemas", [])
    except RequestException:
        raise


def get_schema_objects(catalog: str, schema: str):
    try:
        resp = requests.get(
            f"{API_BASE_URL}/api/databricks/catalogs/{catalog}/schemas/{schema}/objects",
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except RequestException:
        raise


def refresh_metadata(payload: dict):
    try:
        resp = requests.post(f"{API_BASE_URL}/api/metadata/refresh", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except RequestException:
        raise


def _reset_schema_table():
    st.session_state.selected_schema = ""
    st.session_state.selected_table = ""


def _reset_table():
    st.session_state.selected_table = ""


st.set_page_config(page_title="QA Automation - Metadata Refresh")

st.title("QA Automation - Metadata Refresh")

st.write("## Metadata Refresh Scope")

scope_display = st.radio("Select scope", ("Catalog", "Schema", "Table"), key="selected_scope")
scope = scope_display.lower()

# Initialize session state keys if missing
for key in ("selected_catalog", "selected_schema", "selected_table"):
    if key not in st.session_state:
        st.session_state[key] = ""

catalogs = []
try:
    catalogs = get_catalogs()
    catalog_names = [c["name"] for c in catalogs]
except RequestException:
    catalog_names = []

catalog_placeholder = "-- select a catalog --"
catalog_options = [catalog_placeholder] + catalog_names

selected_catalog = st.selectbox("Catalog", catalog_options, index=0, key="selected_catalog_select")
if selected_catalog != catalog_placeholder:
    # store normalized value
    if st.session_state.get("selected_catalog") != selected_catalog:
        st.session_state.selected_catalog = selected_catalog
        _reset_schema_table()
else:
    st.session_state.selected_catalog = ""
    _reset_schema_table()

schema_placeholder = "-- select a schema --"
schema_options = [schema_placeholder]

if scope in ("schema", "table") and st.session_state.selected_catalog:
    try:
        schemas = get_schemas(st.session_state.selected_catalog)
        schema_names = [s["name"] for s in schemas]
        schema_options = [schema_placeholder] + schema_names
    except RequestException:
        st.error("Unable to retrieve schemas.")

selected_schema = ""
if scope in ("schema", "table"):
    selected_schema = st.selectbox("Schema", schema_options, index=0, key="selected_schema_select")
    if selected_schema != schema_placeholder:
        if st.session_state.get("selected_schema") != selected_schema:
            st.session_state.selected_schema = selected_schema
            _reset_table()
    else:
        st.session_state.selected_schema = ""

table_placeholder = "-- select a table --"
table_options = [table_placeholder]

if scope == "table" and st.session_state.selected_catalog and st.session_state.selected_schema:
    try:
        objects = get_schema_objects(st.session_state.selected_catalog, st.session_state.selected_schema)
        tables = objects.get("tables", [])
        table_names = [t["name"] for t in tables]
        table_options = [table_placeholder] + table_names
    except RequestException:
        st.error("Unable to retrieve tables for the selected schema.")

if scope == "table":
    selected_table = st.selectbox("Table", table_options, index=0, key="selected_table_select")
    if selected_table != table_placeholder:
        st.session_state.selected_table = selected_table
    else:
        st.session_state.selected_table = ""

# Determine if the refresh button should be enabled
can_refresh = False
if scope == "catalog":
    can_refresh = bool(st.session_state.selected_catalog)
elif scope == "schema":
    can_refresh = bool(st.session_state.selected_catalog and st.session_state.selected_schema)
elif scope == "table":
    can_refresh = bool(st.session_state.selected_catalog and st.session_state.selected_schema and st.session_state.selected_table)

status_placeholder = st.empty()

if st.button("Refresh Metadata", disabled=not can_refresh):
    payload: dict = {"scope_type": scope, "catalog_name": st.session_state.selected_catalog}
    if scope in ("schema", "table"):
        payload["schema_name"] = st.session_state.selected_schema
    if scope == "table":
        payload["table_name"] = st.session_state.selected_table

    status_placeholder.info("Refreshing metadata...")
    try:
        resp = refresh_metadata(payload)
    except RequestException:
        status_placeholder.error("Unable to refresh metadata.")
    else:
        # Build concise summary
        refresh_obj = resp.get("refresh", {})
        scope_obj = refresh_obj.get("scope", {})
        scope_type = scope_obj.get("type")
        catalog_name = scope_obj.get("catalog_name")
        schema_name = scope_obj.get("schema_name")
        table_name = scope_obj.get("table_name")
        status = refresh_obj.get("status")
        refreshed_at = refresh_obj.get("refreshed_at")

        if scope_type == "table" and table_name:
            scope_text = f"{catalog_name}.{schema_name}.{table_name}"
        elif scope_type == "schema" and schema_name:
            scope_text = f"{catalog_name}.{schema_name}"
        else:
            scope_text = f"{catalog_name}"

        status_placeholder.success("Metadata refreshed successfully.")
        st.write("---")
        st.header("Metadata Refresh")
        st.write(f"Scope: {scope_text}")
        st.write(f"Status: {status}")
        if refreshed_at:
            st.write(f"Refreshed at: {refreshed_at}")
