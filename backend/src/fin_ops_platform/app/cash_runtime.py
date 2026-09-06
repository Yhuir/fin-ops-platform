"""Lazy composition of the isolated cash module; no ordinary ledger dependency."""

from __future__ import annotations

import os
from pathlib import Path

from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict
from pymongo import MongoClient

from fin_ops_platform.app.routes_cash import CashApiRoutes
from fin_ops_platform.services.cash_domain import CashError
from fin_ops_platform.services.cash_oa_projects import CashOaProjectService, load_project_stages
from fin_ops_platform.services.cash_queries import CashQueryService
from fin_ops_platform.services.cash_service import CashService
from fin_ops_platform.services.cash_tasks import CashTaskService
from fin_ops_platform.services.mongo_oa_adapter import load_mongo_oa_settings
from fin_ops_platform.services.oa_identity_service import OAIdentitySettings
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.cash import CashRepository
from fin_ops_platform.services.postgres_repositories.cash_queries import CashQueryRepository
from fin_ops_platform.services.postgres_repositories.cash_runtime_identity import assert_cash_runtime_identity
from fin_ops_platform.services.postgres_repositories.cash_tasks import CashTaskRepository


def cash_postgres_settings() -> PostgresSettings:
    cash_url = os.environ.get("FIN_OPS_CASH_POSTGRES_DATABASE_URL", "").strip()
    ordinary_url = (os.environ.get("FIN_OPS_POSTGRES_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not cash_url or not ordinary_url:
        raise CashError("cash_dependency_unavailable", "现金专用数据库身份未配置。", 503)
    try:
        cash, ordinary = conninfo_to_dict(cash_url), conninfo_to_dict(ordinary_url)
    except ProgrammingError:
        # libpq's parser may include credentials in its exception text.
        raise CashError("cash_dependency_unavailable", "现金数据库配置格式不正确。", 503) from None
    for info in (cash, ordinary):
        if (any(not info.get(key) for key in ("host", "dbname", "user"))
                or any(key in info for key in ("options", "service")) or "," in info["host"]):
            raise CashError("cash_dependency_unavailable", "现金连接必须明确单一数据库端点和身份，不能覆盖角色或服务配置。", 503)
    if (any(cash.get(key) != ordinary.get(key) for key in ("host", "hostaddr", "dbname"))
            or cash.get("port", "5432") != ordinary.get("port", "5432")):
        raise CashError("cash_dependency_unavailable", "现金必须连接当前 PostgreSQL 的同一数据库。", 503)
    if not cash.get("user") or not ordinary.get("user") or cash.get("user") == ordinary.get("user"):
        raise CashError("cash_dependency_unavailable", "现金必须使用独立的数据库运行身份。", 503)
    return PostgresSettings(
        database_url=cash_url, pool_min_size=1, pool_max_size=2,
        pool_max_waiting=8, pool_name="fin-ops-cash", statement_timeout_ms=5000,
    )


class CashRuntime:
    def __init__(self, data_dir: Path | None) -> None:
        self.connection = PostgresConnection(cash_postgres_settings())
        self.mongo_client = None
        ordinary_url = os.environ.get("FIN_OPS_POSTGRES_DATABASE_URL") or os.environ["DATABASE_URL"]
        try:
            assert_cash_runtime_identity(self.connection, conninfo_to_dict(ordinary_url)["user"])
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
