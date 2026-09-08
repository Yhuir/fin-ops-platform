"""Lazy composition of the isolated cash module; no ordinary ledger dependency."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pymongo import MongoClient

from fin_ops_platform.app.routes_cash import CashApiRoutes
from fin_ops_platform.services.cash_domain import CashError
from fin_ops_platform.services.cash_oa_projects import CashOaProjectService, load_project_stages
from fin_ops_platform.services.cash_queries import CashQueryService
from fin_ops_platform.services.cash_service import CashService
from fin_ops_platform.services.cash_tasks import CashTaskService
from fin_ops_platform.services.mongo_oa_adapter import load_mongo_oa_settings
from fin_ops_platform.services.oa_identity_service import OAIdentitySettings
from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.cash import CashRepository
from fin_ops_platform.services.postgres_repositories.cash_queries import CashQueryRepository
from fin_ops_platform.services.postgres_repositories.cash_tasks import CashTaskRepository


def cash_postgres_settings() -> PostgresSettings:
    try:
        settings = PostgresSettings.from_env()
    except PostgresConfigurationError:
        raise CashError("cash_dependency_unavailable", "当前 PostgreSQL 连接配置不完整或不正确。", 503) from None
    # Same database and login as the App; a small independent pool bounds cash
    # resource use, not SQL permissions. Repositories enforce cash-only I/O.
    return replace(
        settings, pool_min_size=1, pool_max_size=min(settings.pool_max_size, 2),
        pool_max_waiting=min(settings.pool_max_waiting, 8), pool_name="fin-ops-cash", pool_enabled=True,
        statement_timeout_ms=min(settings.statement_timeout_ms, 5000),
        connect_timeout_seconds=min(settings.connect_timeout_seconds, 5),
        pool_acquire_timeout_seconds=min(settings.pool_acquire_timeout_seconds, 2),
    )


class CashRuntime:
    def __init__(self, data_dir: Path | None) -> None:
        self.connection = PostgresConnection(cash_postgres_settings())
        self.mongo_client = None
        try:
            self.repository = CashRepository(self.connection)
            self.queries = CashQueryService(CashQueryRepository(self.connection))
            self.task_repository = CashTaskRepository(self.connection)
            self.mongo_settings = load_mongo_oa_settings(data_dir)
            self.oa_settings = OAIdentitySettings.from_environment()
            if self.mongo_settings is not None:
                settings = self.mongo_settings
                self.mongo_client = MongoClient(
                    host=settings.host, port=settings.port, username=settings.username,
                    password=settings.password, authSource=settings.auth_source,
                    serverSelectionTimeoutMS=settings.request_timeout_ms,
                    connectTimeoutMS=settings.request_timeout_ms,
                    socketTimeoutMS=settings.request_timeout_ms,
                    maxPoolSize=4, minPoolSize=0, waitQueueTimeoutMS=2000, connect=False,
                )
        except Exception:
            # Cleanup only: configuration/dependency failure is never replaced
            # with another pool, fake source, or a successful response.
            self.close()
            raise

    def routes(self, session, json_response) -> CashApiRoutes:
        # A request-scoped token is never retained by the shared runtime or pool.
        service = CashService(self.repository)
        projects = CashOaProjectService(
            self.mongo_settings, service.get_project_selection,
            lambda: load_project_stages(
                self.oa_settings.base_url, session.token,
                self.oa_settings.request_timeout_ms / 1000,
            ),
            mongo_client=self.mongo_client,
        )
        service = CashService(self.repository, projects.resolve_project,
                              stage_validator=projects.validate_stage_codes)
        tasks = CashTaskService(self.task_repository, service)
        return CashApiRoutes(service, self.queries, tasks, projects, json_response)

    def close(self) -> None:
        self.connection.close()
        if self.mongo_client is not None:
            self.mongo_client.close()
