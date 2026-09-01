from data_health_monitor.config import get_settings
from data_health_monitor.models.qa_context import QAContext


def sql_generation_message(qa_context: QAContext) -> str:
    settings = get_settings()
    test_case_id = qa_context.test_case.test_case_id
    test_case_identifier = (
        f"{settings.databricks_catalog}.{settings.databricks_schema}.{settings.test_case_table_name}"
    )
    payor_config_identifier = (
        f"{settings.payor_config_catalog}.{settings.payor_config_schema}.{settings.payor_config_table_name}"
    )
    targets = "; ".join(
        f"{table.catalog}.{table.schema}.{table.table_name} ({table.payor_config.payor}/{table.payor_config.file_type})"
        for table in qa_context.tables
    )
    return (
        f"Generate validation SQL for test case {test_case_id}. "
        f"1. Query {test_case_identifier} where test_case_id is {test_case_id}; use validation_check and "
        "expected_result as the requirement. "
        "2. Execute the test-case lookup separately and inspect its result; do not combine lookup and validation work in a CTE. "
        f"3. For each target, separately query {payor_config_identifier} where payor and file_type match the listed values. "
        f"4. Validate only these target tables: {targets}. "
        "5. Use metadata to verify columns; execute small intermediate lookup and sample queries, observe each result, and reason before the next query. "
        "6. Generate the candidate validation SQL without inventing validation logic, execute it, and inspect the result. "
        "7. If it fails, is incomplete, or does not test the requirement, investigate and revise it before responding. "
        "8. Return only the final executable validation SQL that directly validates the target; never return a CTE, CASE, CONCAT, or other query that constructs SQL as text."
    )