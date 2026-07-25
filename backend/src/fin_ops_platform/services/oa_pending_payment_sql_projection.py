from __future__ import annotations

from time import perf_counter
from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.services.invoice_usage_collection_source_versions import oa_pending_payment_source_versions
from fin_ops_platform.services.oa_pending_payment_projection_rows import (
    build_oa_pending_payment_rows,
    relation_member_ids,
)
from fin_ops_platform.services.oa_pending_payment_read_model_repository import OaPendingPaymentReadModelRepositoryPort
from fin_ops_platform.services.postgres_repositories.common import run_in_transaction
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_admission import (
    PostgresOaPendingPaymentAdmissionRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_relation import (
    PostgresOaPendingPaymentRelationRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentStatusSnapshotReader,
    oa_pending_payment_coverage_only_source_versions,
    oa_pending_payment_source_versions_from_snapshot,
    oa_pending_payment_workbench_relation_versions_by_scope,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository
from fin_ops_platform.services.postgres_repositories.read_models import MONTH_SCOPE_RE, PostgresReadModelRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.workbench_relation_modes import TURNOVER_MANUAL_CLOSURE_RELATION_MODE


OA_PENDING_PAYMENT_POSTGRES_PROJECTOR_VERSION = "2026-07-26-active-relation-membership-v7"


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

    def list_scope_shards(self, scope_key: str, *, tenant_id: str = "default") -> list[str]:
        normalized_scope_key = str(scope_key or "").strip()
        if MONTH_SCOPE_RE.match(normalized_scope_key):
            return [normalized_scope_key]
        source_prefix = f"oa_pending_payment_source:{str(tenant_id or 'default').strip() or 'default'}:"
        rows = self._connection.fetch_all(
            """
            select scope_key
            from (
                select substring(watermark.sync_key from length(%s) + 1) as scope_key
                from app.oa_sync_watermarks watermark
                where watermark.sync_key like %s
                union
                select distinct to_char(bank.txn_month, 'YYYY-MM') as scope_key
                from app.bank_transactions bank
                where bank.txn_month is not null
                  and bank.status <> 'deleted'
                union
                select distinct to_char(invoice.invoice_month, 'YYYY-MM') as scope_key
                from app.invoices invoice
                where invoice.invoice_month is not null
                  and invoice.status <> 'deleted'
                  and invoice.invoice_type = %s
            ) inventory
            where scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key desc
            """,
            (source_prefix, f"{source_prefix}%", InvoiceType.INPUT.value),
        )
        return sorted(
            {
                str(row.get("scope_key") or "").strip()
                for row in list(rows or [])
                if isinstance(row, dict) and MONTH_SCOPE_RE.match(str(row.get("scope_key") or "").strip())
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
        started_at = perf_counter()
        build = run_in_transaction(
            self._connection,
            lambda transaction: self._build_scope_snapshot(
                transaction,
                scope_key=normalized_scope_key,
                tenant_id=tenant_id,
            ),
        )
        publish_started_at = perf_counter()
        published = self._read_model_port.publish_oa_pending_payment_rows(
            tenant_id=tenant_id,
            scope_key=normalized_scope_key,
            source_version=source_version,
            rows=build["rows"],
            source_versions=build["source_versions"],
            statistics=build["statistics"],
        )
        publish_ms = _elapsed_ms(publish_started_at)
        if not published:
            return {
                "scope_key": normalized_scope_key,
                "source_version": source_version,
                "skipped": True,
                "skip_reason": "superseded_before_publish",
                "published": False,
                "load_ms": float(build.get("load_ms") or 0),
                "assemble_ms": float(build.get("assemble_ms") or 0),
                "publish_ms": publish_ms,
                "total_ms": _elapsed_ms(started_at),
            }
        return {
            "scope_key": normalized_scope_key,
            "source_version": source_version,
            "row_count": len(build["rows"]),
            "source_versions": build["source_versions"],
            "published": True,
            "load_ms": float(build.get("load_ms") or 0),
            "assemble_ms": float(build.get("assemble_ms") or 0),
            "publish_ms": publish_ms,
            "total_ms": _elapsed_ms(started_at),
            "refresh_mode": "full",
        }

    def _build_scope_snapshot(
        self,
        connection: Any,
        *,
        scope_key: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        load_started_at = perf_counter()
        payment_status_repository = PostgresOaPendingPaymentStatusSnapshotReader(
            connection,
            scope_key=scope_key,
            tenant_id=tenant_id,
        )
        admission_repository = PostgresOaPendingPaymentAdmissionRepository(connection)
        completed_records = PostgresOAProjectionRepository(connection).list_application_records(scope_key)
        in_progress_records = [
            record
            for record in admission_repository.list_application_records(scope_key, tenant_id=tenant_id)
            if str(record.workflow_status or "").strip() == "in_progress"
        ]
        payment_statuses = payment_status_repository.list_payment_statuses()

        canonical_snapshot = (
            PostgresWorkbenchRelationRepository(
                connection
            ).load_active_workbench_pair_relations_for_row_ids(
                [record.id for record in completed_records],
            )
        )
        canonical_relations = [
            dict(relation)
            for relation in dict(canonical_snapshot.get("pair_relations") or {}).values()
            if isinstance(relation, dict)
            and str(relation.get("relation_mode") or "").strip()
            != TURNOVER_MANUAL_CLOSURE_RELATION_MODE
        ]
        pending_relations = PostgresOaPendingPaymentRelationRepository(connection).active_relations_for_row_ids(
            [record.id for record in in_progress_records]
        )
        all_relations = [*canonical_relations, *pending_relations]
        core_repository = PostgresCoreRepository(connection)
        bank_transactions = core_repository.list_bank_transactions_by_ids(
            relation_member_ids(all_relations, row_types={"bank", "bank_transaction"})
        )
        invoices = core_repository.list_invoices_by_ids(
            relation_member_ids(all_relations, row_types={"invoice"})
        )
        load_ms = _elapsed_ms(load_started_at)
        assemble_started_at = perf_counter()
        rows = [
            *build_oa_pending_payment_rows(
                records=completed_records,
                relations=canonical_relations,
                bank_transactions=bank_transactions,
                invoices=invoices,
                payment_statuses_by_flow_id=payment_statuses,
                flow_id_resolver=payment_status_repository.resolve_flow_id,
                scope_key=scope_key,
            ),
            *build_oa_pending_payment_rows(
                records=in_progress_records,
                relations=pending_relations,
                bank_transactions=bank_transactions,
                invoices=invoices,
                payment_statuses_by_flow_id=payment_statuses,
                flow_id_resolver=payment_status_repository.resolve_flow_id,
                scope_key=scope_key,
            ),
        ]
        statistics, coverage_versions = _oa_pending_payment_statistics(
            connection,
            scope_key=scope_key,
            completed_records=completed_records,
            in_progress_records=in_progress_records,
            rows=rows,
        )
        coverage_only = (
            not completed_records
            and not in_progress_records
            and not payment_statuses
            and (
                int(statistics.get("bank_transaction_count") or 0) > 0
                or int(statistics.get("input_invoice_count") or 0) > 0
            )
        )
        return {
            "rows": rows,
            "statistics": statistics,
            "load_ms": load_ms,
            "assemble_ms": _elapsed_ms(assemble_started_at),
            "source_versions": {
                **self._expected_source_versions(
                    connection,
                    scope_key=scope_key,
                    tenant_id=tenant_id,
                    coverage_only=coverage_only,
                ),
                **coverage_versions,
            },
        }

    @staticmethod
    def _expected_source_versions(
        connection: Any,
        *,
        scope_key: str,
        tenant_id: str,
        coverage_only: bool = False,
    ) -> dict[str, object]:
        snapshot_versions = oa_pending_payment_source_versions_from_snapshot(
            connection,
            scope_key=scope_key,
            tenant_id=tenant_id,
        )
        pending_relation_versions = PostgresOaPendingPaymentRelationRepository(connection).source_versions(
            scope_key=scope_key,
            tenant_id=tenant_id,
        )
        workbench_relation_versions = oa_pending_payment_workbench_relation_versions_by_scope(
            connection,
            scope_keys=[scope_key],
        ).get(scope_key, {})
        if not snapshot_versions and coverage_only:
            return {
                **oa_pending_payment_base_source_versions(),
                **oa_pending_payment_coverage_only_source_versions(scope_key),
                **workbench_relation_versions,
                "oa_pending_payment_relation_version": int(
                    pending_relation_versions.get("oa_pending_payment_relation_version") or 0
                ),
            }
        if not snapshot_versions or not snapshot_versions.get("oa_pending_payment_source_signature"):
            raise RuntimeError(f"oa_pending_payment_source_snapshot_missing:{scope_key}")
        if not pending_relation_versions:
            raise RuntimeError(f"oa_pending_payment_relation_version_missing:{scope_key}")
        return {
            **oa_pending_payment_base_source_versions(),
            **snapshot_versions,
            **workbench_relation_versions,
            **pending_relation_versions,
        }

def _oa_pending_payment_statistics(
    connection: Any,
    *,
    scope_key: str,
    completed_records: list[Any],
    in_progress_records: list[Any],
    rows: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, str]]:
    coverage = connection.fetch_one(
        """
        with bank_coverage as (
            select
                count(distinct coalesce(bank.legacy_mongo_id, bank.id::text))::integer as row_count,
                count(distinct coalesce(bank.legacy_mongo_id, bank.id::text)) filter (
                    where bank.txn_direction = 'outflow'
                )::integer as expense_count,
                count(distinct coalesce(bank.legacy_mongo_id, bank.id::text)) filter (
                    where bank.txn_direction = 'inflow'
                )::integer as income_count,
                md5(coalesce(string_agg(
                    concat(
                        coalesce(bank.legacy_mongo_id, bank.id::text),
                        '|',
                        coalesce(bank.txn_direction, '')
                    ),
                    E'\n' order by coalesce(bank.legacy_mongo_id, bank.id::text)
                ), '')) as membership_digest
            from app.bank_transactions bank
            where bank.txn_month = to_date(%s, 'YYYY-MM')
              and bank.status <> 'deleted'
        ), invoice_coverage as (
            select
                count(distinct coalesce(invoice.legacy_mongo_id, invoice.id::text))::integer as row_count,
                md5(coalesce(string_agg(
                    concat(
                        coalesce(invoice.legacy_mongo_id, invoice.id::text),
                        '|',
                        coalesce(invoice.invoice_type, '')
                    ),
                    E'\n' order by coalesce(invoice.legacy_mongo_id, invoice.id::text)
                ), '')) as membership_digest
            from app.invoices invoice
            where invoice.invoice_month = to_date(%s, 'YYYY-MM')
              and invoice.status <> 'deleted'
              and (
                  invoice.invoice_type in (%s, %s)
                  or invoice.invoice_type like %s
              )
        )
        select
            bank_coverage.row_count as bank_transaction_count,
            bank_coverage.expense_count as expense_bank_transaction_count,
            bank_coverage.income_count as income_bank_transaction_count,
            bank_coverage.membership_digest as bank_membership_digest,
            invoice_coverage.row_count as input_invoice_count,
            invoice_coverage.membership_digest as input_invoice_membership_digest
        from bank_coverage
        cross join invoice_coverage
        """,
        (
            scope_key,
            scope_key,
            InvoiceType.INPUT.value,
            f"{InvoiceType.INPUT.value}_invoice",
            "进项%",
        ),
    ) or {}
    completed_ids = {str(record.id) for record in completed_records if str(getattr(record, "id", "")).strip()}
    in_progress_ids = {
        str(record.id) for record in in_progress_records if str(getattr(record, "id", "")).strip()
    }
    all_oa_ids = completed_ids | in_progress_ids
    paid_oa_ids: set[str] = set()
    linked_bank_oa_ids: set[str] = set()
    linked_invoice_oa_ids: set[str] = set()
    for row in rows:
        oa_payload = row.get("oa") if isinstance(row.get("oa"), dict) else {}
        summaries = oa_payload.get("summaries") if isinstance(oa_payload.get("summaries"), list) else []
        row_oa_ids = {
            str(item.get("oaId") or item.get("id") or "").strip()
            for item in summaries
            if isinstance(item, dict) and str(item.get("oaId") or item.get("id") or "").strip()
        }
        if not row_oa_ids:
            oa_id = str(oa_payload.get("id") or oa_payload.get("primaryOaId") or "").strip()
            if oa_id:
                row_oa_ids.add(oa_id)
        payment_status = row.get("paymentStatus") if isinstance(row.get("paymentStatus"), dict) else {}
        if str(payment_status.get("code") or "") == "paid":
            paid_oa_ids.update(row_oa_ids)
        bank_payload = row.get("bankTransaction") if isinstance(row.get("bankTransaction"), dict) else {}
        if int(bank_payload.get("linkedRelationCount") or 0) > 0:
            linked_bank_oa_ids.update(row_oa_ids)
        invoice_payload = row.get("invoice") if isinstance(row.get("invoice"), dict) else {}
        invoice_summaries = (
            invoice_payload.get("summaries") if isinstance(invoice_payload.get("summaries"), list) else []
        )
        if any(
            isinstance(item, dict) and str(item.get("relationStatus") or "") == "linked"
            for item in invoice_summaries
        ):
            linked_invoice_oa_ids.update(row_oa_ids)
    statistics = {
        "oa_count": len(all_oa_ids),
        "bank_transaction_count": int(coverage.get("bank_transaction_count") or 0),
        "expense_transaction_count": int(coverage.get("expense_bank_transaction_count") or 0),
        "income_transaction_count": int(coverage.get("income_bank_transaction_count") or 0),
        "input_invoice_count": int(coverage.get("input_invoice_count") or 0),
        "paid_oa_count": len(paid_oa_ids & all_oa_ids),
        "unpaid_oa_count": len(all_oa_ids - paid_oa_ids),
        "completed_oa_count": len(completed_ids),
        "in_progress_oa_count": len(in_progress_ids),
        "linked_bank_oa_count": len(linked_bank_oa_ids & all_oa_ids),
        "linked_input_invoice_oa_count": len(linked_invoice_oa_ids & all_oa_ids),
    }
    return statistics, {
        "oa_pending_payment_bank_coverage_signature": (
            f"rows:{statistics['bank_transaction_count']}|digest:{coverage.get('bank_membership_digest') or ''}"
        ),
        "oa_pending_payment_input_invoice_coverage_signature": (
            f"rows:{statistics['input_invoice_count']}|digest:"
            f"{coverage.get('input_invoice_membership_digest') or ''}"
        ),
    }


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)

def _month_scope(scope_key: str) -> str:
    normalized_scope_key = str(scope_key or "").strip()
    if not MONTH_SCOPE_RE.match(normalized_scope_key):
        raise ValueError(f"OA pending payment read model scope must be a YYYY-MM shard: {scope_key}")
    return normalized_scope_key
