from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    databricks_profile: str | None = None
    databricks_catalog: str = "main"
    databricks_schema: str = "qa"
    databricks_warehouse_id: str | None = None
    test_case_table_name: str = "test_cases"
    payor_config_catalog: str = "main"
    payor_config_schema: str = "qa"
    payor_config_table_name: str = "payor_config"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
