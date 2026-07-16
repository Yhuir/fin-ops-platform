from __future__ import annotations

from typing import Any

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_usage_collection_source_versions import oa_pending_payment_source_versions
from fin_ops_platform.services.oa_pending_payment_read_model_repository import OaPendingPaymentReadModelRepositoryPort
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentQueryService
from fin_ops_platform.services.postgres_repositories.common import run_in_transaction
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_admission import (
    PostgresOaPendingPaymentAdmissionRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_relation import (
    PostgresOaPendingPaymentRelationRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentStatusSnapshotReader,
    oa_pending_payment_source_versions_from_snapshot,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository
from fin_ops_platform.services.postgres_repositories.read_models import MONTH_SCOPE_RE, PostgresReadModelRepository
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


OA_PENDING_PAYMENT_POSTGRES_PROJECTOR_VERSION = "2026-07-16-pg-only-v1"


def oa_pending_payment_base_source_versions() -> dict[str, object]:
    return {
        **oa_pending_payment_source_versions(),
        "oa_pending_payment_postgres_projector_version": OA_PENDING_PAYMENT_POSTGRES_PROJECTOR_VERSION,
    }


class OaPendingPaymentSqlProjectionBuilder:
    """Build only the OA pending-payment read model from PostgreSQL facts."""

    def __init__(self, *, connection: Any, read_model_repository: Any | None = None) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or PostgresReadModelRepository(connection)
        self._read_model_port = OaPendingPaymentReadModelRepositoryPort(self._read_model_repository)

    def list_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope_key = str(scope_key or "").strip()
        if MONTH_SCOPE_RE.match(normalized_scope_key):
            return [normalized_scope_key]
        completed = PostgresOAProjectionRepository(self._connection).list_available_months()
        admitted = PostgresOaPendingPaymentAdmissionRepository(self._connection).list_available_months()
        return sorted(
            {
                month
                for month in [*completed, *admitted]
                if MONTH_SCOPE_RE.match(str(month or ""))
            },
            reverse=True,
        )

    def prune_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._read_model_port.prune_oa_pending_payment_scope_shards(current_scope_keys)

    def rebuild_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        normalized_scope_key = _month_scope(scope_key)
        del force_refresh

        build = run_in_transaction(
            self._connection,
            lambda transaction: self._build_scope_snapshot(
                transaction,
                scope_key=normalized_scope_key,
                tenant_id=tenant_id,
            ),
        )
        published = self._read_model_port.publish_oa_pending_payment_rows(
            tenant_id=tenant_id,
            scope_key=normalized_scope_key,
            source_version=source_version,
            rows=build["rows"],
            source_versions=build["source_versions"],
        )
        if not published:
            return {
                "scope_key": normalized_scope_key,
                "source_version": source_version,
                "skipped": True,
                "skip_reason": "superseded_before_publish",
                "published": False,
            }
        return {
            "scope_key": normalized_scope_key,
            "source_version": source_version,
            "row_count": len(build["rows"]),
            "source_versions": build["source_versions"],
            "published": True,
        }

    def _build_scope_snapshot(
        self,
        connection: Any,
        *,
        scope_key: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        read_repository = PostgresReadModelRepository(connection)
        relation_facade = WorkbenchRelationReadFacade(read_model_repository=read_repository)
        relation_payload = relation_facade.list_by_month(
            scope_key,
            require_fresh=True,
            reason="oa_pending_payment_sql_projection",
        )
        if not isinstance(relation_payload, dict) or str(relation_payload.get("status") or "") != "fresh":
            raise RuntimeError("workbench_relation_read_model_not_fresh")

        payment_status_repository = PostgresOaPendingPaymentStatusSnapshotReader(
            connection,
            scope_key=scope_key,
            tenant_id=tenant_id,
        )
        admission_repository = PostgresOaPendingPaymentAdmissionRepository(connection)
        service = OaPendingPaymentQueryService(
            import_service=ImportNormalizationService.from_snapshot(
                None,
                fact_repository=PostgresCoreRepository(connection),
            ),
            relation_facade=relation_facade,
            pending_relation_service=PostgresOaPendingPaymentRelationRepository(connection),
            oa_projection=PostgresOAProjectionRepository(connection),
            in_progress_oa_projection=admission_repository,
            payment_status_repository=payment_status_repository,
            require_fresh_relations=True,
        )
        context = service._query_context(month_hint=scope_key)
        payment_statuses = service._payment_statuses_by_flow_id()
        completed_records = service._oa_records(
            month=scope_key,
            view_mode="completed",
            payment_statuses_by_flow_id=payment_statuses,
        )
        in_progress_records = service._oa_records(
            month=scope_key,
            view_mode="in_progress",
            payment_statuses_by_flow_id=payment_statuses,
        )
        rows = [
            *service._build_rows(
                month=scope_key,
                context=context,
                view_mode="completed",
                payment_statuses_by_flow_id=payment_statuses,
                records=completed_records,
            ),
            *service._build_rows(
                month=scope_key,
                context=context,
                view_mode="in_progress",
                payment_statuses_by_flow_id=payment_statuses,
                records=in_progress_records,
            ),
        ]
        return {
            "rows": rows,
            "source_versions": self._expected_source_versions(
                connection,
                scope_key=scope_key,
                tenant_id=tenant_id,
                relation_facade=relation_facade,
                read_repository=read_repository,
            ),
        }

    @staticmethod
    def _expected_source_versions(
        connection: Any,
        *,
        scope_key: str,
        tenant_id: str,
        relation_facade: WorkbenchRelationReadFacade | None = None,
        read_repository: PostgresReadModelRepository | None = None,
    ) -> dict[str, object]:
        snapshot_versions = oa_pending_payment_source_versions_from_snapshot(
            connection,
            scope_key=scope_key,
            tenant_id=tenant_id,
        )
        if not snapshot_versions or not snapshot_versions.get("oa_pending_payment_source_signature"):
            raise RuntimeError(f"oa_pending_payment_source_snapshot_missing:{scope_key}")
        target_read_repository = read_repository or PostgresReadModelRepository(connection)
        target_relation_facade = relation_facade or WorkbenchRelationReadFacade(
            read_model_repository=target_read_repository,
        )
        load_relation_versions = getattr(target_read_repository, "workbench_relation_source_versions", None)
        relation_versions = (
            load_relation_versions(scope_key=scope_key)
            if callable(load_relation_versions)
            else dict(target_relation_facade.last_source_versions)
        )
        pending_relation_versions = PostgresOaPendingPaymentRelationRepository(connection).source_versions(
            scope_key=scope_key,
            tenant_id=tenant_id,
        )
        if not pending_relation_versions:
            raise RuntimeError(f"oa_pending_payment_relation_version_missing:{scope_key}")
        return {
            **oa_pending_payment_base_source_versions(),
            **snapshot_versions,
            **pending_relation_versions,
            **(
                {"workbench_relation_source_versions": dict(relation_versions)}
                if isinstance(relation_versions, dict) and relation_versions
                else {}
            ),
        }

def _month_scope(scope_key: str) -> str:
    normalized_scope_key = str(scope_key or "").strip()
    if not MONTH_SCOPE_RE.match(normalized_scope_key):
        raise ValueError(f"OA pending payment read model scope must be a YYYY-MM shard: {scope_key}")
    return normalized_scope_key
