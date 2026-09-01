from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_debug: bool = True
    app_log_level: str = "INFO"
    app_log_file: str = "logs/data_health_monitor.log"
    app_log_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    app_log_backup_count: int = Field(default=5, ge=0)
    databricks_profile: str | None = None
    databricks_catalog: str = "main"
    databricks_schema: str = "qa"
    databricks_warehouse_id: str | None = None
    test_case_table_name: str = "test_cases"
    payor_config_catalog: str = "main"
    payor_config_schema: str = "qa"
    payor_config_table_name: str = "payor_config"
    validation_sql_catalog: str = "main"
    validation_sql_schema: str = "qa"
    validation_sql_table_name: str = "validation_sql"
    test_case_results_catalog: str = "main"
    test_case_results_schema: str = "qa"
    test_case_results_table_name: str = "test_case_results"
    genie_space_id: str | None = None
    genie_space_title: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("app_log_level")
    @classmethod
    def validate_app_log_level(cls, value: str) -> str:
        normalized_value = value.upper()
        if normalized_value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("APP_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
        return normalized_value


@lru_cache()
def get_settings() -> Settings:
    return Settings()
