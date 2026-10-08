"""Read-only OA source discovery; business pages keep their PostgreSQL readers."""
from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from pymongo import MongoClient

from fin_ops_platform.services.mongo_oa_adapter import (
    MongoOAAdapter,
    MongoOASettings,
    OASearchUnavailable,
    load_mongo_oa_settings,
)
from fin_ops_platform.services.postgres_repositories.oa_source_identity import PostgresOASourceIdentityRepository
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository


class OAManualSearchSource:
    def __init__(self, *, settings: MongoOASettings | None, connection: Any) -> None:
        self._settings = settings
        self._connection = connection
        self._client = None
        self._lock = Lock()

    @classmethod
    def from_environment(cls, *, data_dir: Path | None, connection: Any) -> OAManualSearchSource:
        return cls(settings=load_mongo_oa_settings(data_dir), connection=connection)

    def search_application_record_rows(self, **kwargs: Any) -> dict[str, object]:
        settings = self._settings
        if settings is None:
            raise OASearchUnavailable("OA 源库未配置，无法搜索外部 OA。")
        with self._lock:
            if self._client is None:
                self._client = MongoClient(settings.mongo_uri, connect=False,
                    serverSelectionTimeoutMS=settings.request_timeout_ms,
                    connectTimeoutMS=settings.request_timeout_ms, socketTimeoutMS=settings.request_timeout_ms,
                    waitQueueTimeoutMS=settings.request_timeout_ms)
        # Request-local identity and attachment data; only the thread-safe pool is shared.
        adapter = MongoOAAdapter(settings=settings, client=self._client,
            identity_loader=PostgresOASourceIdentityRepository(self._connection).load_identities,
            attachment_invoice_cache=PostgresOpsTaxEtcRepository(self._connection))
        result = adapter.search_application_record_rows(**kwargs)
        states = PostgresOpsTaxEtcRepository(self._connection).load_oa_search_import_states(
            [str(row["row_id"]) for row in result["rows"]])
        for row in result["rows"]:
            row.update(states[row["row_id"]])
        return result

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
