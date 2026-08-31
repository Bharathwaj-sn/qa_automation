from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_debug: bool = True
    databricks_profile: str | None = None
    databricks_serving_model: str | None = None
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
    genie_space_id: str | None = None
    genie_space_title: str | None = None
    litellm_model: str | None = None
    litellm_api_base: str | None = None
    litellm_api_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
