from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from data_health_monitor.config import get_settings
from data_health_monitor.repositories.metadata_repository import MetadataRepository
from data_health_monitor.services.databricks_service import DatabricksService
from data_health_monitor.services.databricks_sql_service import DatabricksSQLService
from data_health_monitor.services.genie_context_service import GenieContextService
from data_health_monitor.services.genie_service import GenieService
from data_health_monitor.services.genie_space_coordinator import GenieSpaceCoordinator
from data_health_monitor.services.metadata_service import MetadataService
from data_health_monitor.services.payor_config_service import PayorConfigService
from data_health_monitor.services.qa_context_service import QAContextService
from data_health_monitor.services.test_case_service import TestCaseService
from data_health_monitor.services.validation_sql_service import ValidationSQLService


def get_databricks_service() -> DatabricksService:
    return DatabricksService(settings=get_settings())


def get_metadata_service(
    databricks_service: Annotated[DatabricksService, Depends(get_databricks_service)],
) -> MetadataService:
    return MetadataService(databricks_service=databricks_service, repository=MetadataRepository())


def get_sql_service() -> DatabricksSQLService:
    return DatabricksSQLService(settings=get_settings())


def get_test_case_service(
    sql_service: Annotated[DatabricksSQLService, Depends(get_sql_service)],
) -> TestCaseService:
    return TestCaseService(sql_service=sql_service)


def get_payor_config_service(
    sql_service: Annotated[DatabricksSQLService, Depends(get_sql_service)],
) -> PayorConfigService:
    return PayorConfigService(sql_service=sql_service)


def get_qa_context_service(
    test_case_service: Annotated[TestCaseService, Depends(get_test_case_service)],
    payor_config_service: Annotated[PayorConfigService, Depends(get_payor_config_service)],
    metadata_service: Annotated[MetadataService, Depends(get_metadata_service)],
) -> QAContextService:
    return QAContextService(
        test_case_service=test_case_service,
        payor_config_service=payor_config_service,
        metadata_service=metadata_service,
    )


def get_genie_context_service(
    metadata_service: Annotated[MetadataService, Depends(get_metadata_service)],
) -> GenieContextService:
    return GenieContextService(metadata_service=metadata_service, settings=get_settings())


def get_genie_service() -> GenieService:
    return GenieService(settings=get_settings())


def get_genie_space_coordinator(
    request: Request,
    genie_service: Annotated[GenieService, Depends(get_genie_service)],
) -> GenieSpaceCoordinator:
    return GenieSpaceCoordinator(genie_service, get_settings(), request.app.state)


def get_validation_sql_service(
    sql_service: Annotated[DatabricksSQLService, Depends(get_sql_service)],
) -> ValidationSQLService:
    return ValidationSQLService(sql_service=sql_service, settings=get_settings())