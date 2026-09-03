from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable

from fin_ops_platform.services.oa_adapter import (
    OAApplicationRecord,
    is_in_progress_expense_claim,
)
from fin_ops_platform.services.oa_payment_status_service import (
    OAPaymentStatusRecord,
    PAY_STATUS_PAID,
    PAY_STATUS_PENDING,
    oa_flow_id_candidates,
)
from fin_ops_platform.services.oa_payment_status_reconcile_contract import (
    OA_PAYMENT_STATUS_RECONCILE_EVENT,
    OA_PAYMENT_STATUS_REMOVE_MISSING_OPERATION,
)
from fin_ops_platform.services.postgres_repositories.common import jsonb, run_in_transaction, serialize_value, text
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    PostgresOAProjectionRepository,
    is_completed_workflow_status,
)
from fin_ops_platform.services.postgres_repositories.workbench_matching_queue import (
    PostgresWorkbenchMatchingQueueRepository,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.workbench_reconciliation_dirty_queue import expand_scope_month_window


OA_PENDING_PAYMENT_COVERAGE_ONLY_SCHEMA_VERSION = 1


def oa_pending_payment_coverage_only_source_versions(scope_key: str) -> dict[str, object]:
    """Return the deterministic empty OA vector for a coverage-only month.

    This vector is projection metadata, not an integration watermark. It lets the
    OA page publish bank/invoice inventory for a month that has no OA source
    snapshot without making a page query the owner of integration facts.
    """

    normalized_scope_key = _month(scope_key)
    if not normalized_scope_key:
        raise ValueError("coverage-only OA source versions require a YYYY-MM scope_key.")
    empty_signature = hashlib.sha256(b"[]").hexdigest()
    source_signature = hashlib.sha256(
        f"oa_pending_payment:coverage_only:{normalized_scope_key}:v{OA_PENDING_PAYMENT_COVERAGE_ONLY_SCHEMA_VERSION}".encode()
    ).hexdigest()
    return {
        "oa_pending_payment_coverage_only_schema_version": OA_PENDING_PAYMENT_COVERAGE_ONLY_SCHEMA_VERSION,
        "oa_pending_payment_source_snapshot_version": 0,
        "completed_oa_signature": empty_signature,
        "in_progress_admission_signature": empty_signature,
        "payment_status_signature": empty_signature,
        "oa_pending_payment_source_signature": source_signature,
    }


@dataclass(slots=True, frozen=True)
class OaPendingPaymentSourceSnapshotResult:
    completed_projection_changed_scopes: tuple[str, ...]
    oa_pending_payment_changed_scopes: tuple[str, ...]
    payment_status_count: int
    admission_count: int
    source_signatures: dict[str, str]
    pending_admission_changed_scopes: tuple[str, ...] = ()
    relation_cleanup: tuple[dict[str, object], ...] = ()
    upserted_completed_count: int = 0
    removed_stale_completed_count: int = 0
    removed_non_completed_count: int = 0
    pruned_scope_keys: tuple[str, ...] = ()
    upserted_pending_count: int = 0
    removed_payment_status_flow_ids: tuple[str, ...] = ()


class PostgresOaPendingPaymentSourceSnapshotRepository:
    """Own the integration-side, PostgreSQL-only inputs for the OA pending projection."""

    def __init__(
        self,
        connection: Any,
        *,
        relation_command_service_for_transaction: Callable[[Any], Any],
    ) -> None:
        self._connection = connection
        self._relation_command_service_for_transaction = relation_command_service_for_transaction

    def payment_status_reader(
        self,
        *,
        scope_key: str | None = None,
        tenant_id: str = "default",
    ) -> "PostgresOaPendingPaymentStatusSnapshotReader":
        return PostgresOaPendingPaymentStatusSnapshotReader(
            self._connection,
            scope_key=scope_key,
            tenant_id=tenant_id,
        )

    def source_versions(self, *, scope_key: str, tenant_id: str = "default") -> dict[str, object]:
        return oa_pending_payment_source_versions_from_snapshot(
            self._connection,
            scope_key=scope_key,
            tenant_id=tenant_id,
        )

    def commit_targeted_attachment_refresh(
        self,
        *,
        records: list[OAApplicationRecord],
        tenant_id: str = "default",
    ) -> OaPendingPaymentSourceSnapshotResult:
        """Atomically refresh exact OA rows without advancing full-sync watermarks."""

        normalized_tenant_id = text(tenant_id) or "default"
        normalized_records = _canonical_owner_records(records)
        if not normalized_records:
            raise ValueError("OA targeted attachment refresh requires at least one record.")
        in_progress_flow_ids: dict[str, str] = {}
        for record in normalized_records:
            if not text(record.id) or not _month(record.month):
                raise ValueError("OA targeted attachment refresh requires row_id and month.")
            if not is_completed_workflow_status(record.workflow_status):
                if not is_in_progress_expense_claim(record):
                    raise ValueError(
                        "OA targeted attachment refresh supports completed workflows "
                        f"and in-progress expense claims only: {record.id}."
                    )
                flow_id = _record_flow_id(record)
                if not flow_id:
                    raise ValueError(
                        "OA targeted attachment refresh requires a stable pending flow_id: "
                        f"{record.id}."
                    )
                in_progress_flow_ids[record.id] = flow_id

        row_ids = sorted(record.id for record in normalized_records)

        def write(transaction: Any) -> OaPendingPaymentSourceSnapshotResult:
            _lock_oa_owner_writes(
                transaction,
                tenant_id=normalized_tenant_id,
            )
            completed_rows = list(
                transaction.fetch_all(
                    """
                    select row_id
                    from app.oa_applications
                    where row_id = any(%s::text[])
                    """,
                    (row_ids,),
                )
                or []
            )
            existing_completed_ids = {
                row_id
                for row in completed_rows
                if (row_id := text(row.get("row_id")))
            }
            in_progress_ids = {
                record.id
                for record in normalized_records
                if not is_completed_workflow_status(record.workflow_status)
            }
            regressed_ids = sorted(existing_completed_ids.intersection(in_progress_ids))
            if regressed_ids:
                raise RuntimeError(
                    "OA targeted attachment refresh refused completed-to-in-progress owner regression: "
                    + ", ".join(regressed_ids)
                )

            old_rows = list(
                transaction.fetch_all(
                    """
                    select scope_key, oa_id, source_signature, source_payload
                    from app.oa_pending_payment_admissions
                    where tenant_id = %s and oa_id = any(%s::text[])
                    """,
                    (normalized_tenant_id, row_ids),
                )
                or []
            )
            old_by_id = {
                oa_id: {
                    "scope_key": _month(row.get("scope_key")),
                    "source_signature": text(row.get("source_signature")) or "",
                    "source_payload": _dict(row.get("source_payload")),
                }
                for row in old_rows
                if (oa_id := text(row.get("oa_id")))
            }
            pending_owner_counts: dict[str, int] = {}
            for row in old_rows:
                oa_id = text(row.get("oa_id"))
                if oa_id:
                    pending_owner_counts[oa_id] = pending_owner_counts.get(oa_id, 0) + 1
            invalid_pending_owner_ids = sorted(
                row_id
                for row_id in in_progress_ids
                if pending_owner_counts.get(row_id, 0) != 1
            )
            if invalid_pending_owner_ids:
                raise RuntimeError(
                    "OA targeted attachment refresh requires exactly one existing pending owner: "
                    + ", ".join(invalid_pending_owner_ids)
                )
            invalid_pending_scope_ids = sorted(
                record.id
                for record in normalized_records
                if record.id in in_progress_ids
                and _month((old_by_id.get(record.id) or {}).get("scope_key"))
                != _month(record.month)
            )
            if invalid_pending_scope_ids:
                raise RuntimeError(
                    "OA targeted attachment refresh requires the existing pending owner scope: "
                    + ", ".join(invalid_pending_scope_ids)
                )

            projection_repository = PostgresOAProjectionRepository(transaction)
            upserted_completed_count = 0
            completed_projection_changed_scopes: set[str] = set()
            for scope_key in sorted(
                {
                    scope
                    for record in normalized_records
                    if is_completed_workflow_status(record.workflow_status)
                    and (scope := _month(record.month))
                }
            ):
                scope_records = [
                    record
                    for record in normalized_records
                    if is_completed_workflow_status(record.workflow_status)
                    and _month(record.month) == scope_key
                ]
                changed = projection_repository.upsert_targeted_application_records(
                    scope_records,
                    scope_key=scope_key,
                )
                upserted_completed_count += int(changed)
                if changed:
                    completed_projection_changed_scopes.add(scope_key)

            desired_pending: dict[str, dict[str, Any]] = {}
            for record in normalized_records:
                if is_completed_workflow_status(record.workflow_status):
                    continue
                flow_id = in_progress_flow_ids[record.id]
                payload = _admission_payload(record, flow_id=flow_id)
                desired_pending[record.id] = {
                    "scope_key": _month(record.month),
                    "source_signature": _signature(payload),
                    "source_payload": payload,
                }

            changed_pending_ids = {
                record.id
                for record in normalized_records
                if is_completed_workflow_status(record.workflow_status)
                and record.id in old_by_id
            }
            changed_pending_ids.update(
                oa_id
                for oa_id, desired in desired_pending.items()
                if (
                    (old_by_id.get(oa_id) or {}).get("scope_key"),
                    (old_by_id.get(oa_id) or {}).get("source_signature"),
                )
                != (desired["scope_key"], desired["source_signature"])
            )
            changed_pending_scopes = {
                scope
                for oa_id in changed_pending_ids
                for scope in (
                    _month((old_by_id.get(oa_id) or {}).get("scope_key")),
                    _month((desired_pending.get(oa_id) or {}).get("scope_key")),
                )
                if scope
            }
            if changed_pending_ids:
                self._replace_targeted_admissions(
                    transaction,
                    tenant_id=normalized_tenant_id,
                    changed_oa_ids=changed_pending_ids,
                    admissions=desired_pending,
                )

            return OaPendingPaymentSourceSnapshotResult(
                completed_projection_changed_scopes=tuple(sorted(completed_projection_changed_scopes)),
                oa_pending_payment_changed_scopes=tuple(sorted(changed_pending_scopes)),
                payment_status_count=0,
                admission_count=len(desired_pending),
                source_signatures={},
                pending_admission_changed_scopes=tuple(sorted(changed_pending_scopes)),
                upserted_completed_count=upserted_completed_count,
                upserted_pending_count=len(changed_pending_ids.intersection(desired_pending)),
            )

        return run_in_transaction(self._connection, write)

    def replace_authoritative_snapshot(
        self,
        *,
        scope_key: str,
        completed_projection_records: list[OAApplicationRecord],
        admission_records: list[OAApplicationRecord],
        payment_statuses: dict[str, OAPaymentStatusRecord],
        removed_projection_oa_row_ids: list[str] | None = None,
        tenant_id: str = "default",
        transaction: Any | None = None,
    ) -> OaPendingPaymentSourceSnapshotResult:
        normalized_scope_key = _scope_key(scope_key)
        normalized_tenant_id = text(tenant_id) or "default"
        normalized_completed_records = _canonical_owner_records([
            record
            for record in list(completed_projection_records or [])
            if isinstance(record, OAApplicationRecord) and is_completed_workflow_status(record.workflow_status)
        ])
        normalized_admission_records = _canonical_owner_records([
            record for record in list(admission_records or []) if isinstance(record, OAApplicationRecord)
        ])
        completed_owner_ids = {
            record.id
            for record in normalized_admission_records
            if is_completed_workflow_status(record.workflow_status)
        }
        normalized_statuses = _normalized_statuses(payment_statuses)
        normalized_removed_projection_oa_row_ids = {
            row_id
            for value in list(removed_projection_oa_row_ids or [])
            if (row_id := text(value))
        }

        def write(transaction: Any) -> OaPendingPaymentSourceSnapshotResult:
            old_status_rows = list(
                transaction.fetch_all(
                    """
                    select flow_id, pay_status, to_char(scope_month, 'YYYY-MM') as scope_month, source_signature
                    from app.oa_pending_payment_status_snapshots
                    where tenant_id = %s
                    """,
                    (normalized_tenant_id,),
                )
                or []
            )
            old_admission_rows = list(
                transaction.fetch_all(
                    """
                    select scope_key, oa_id, source_signature, source_payload
                    from app.oa_pending_payment_admissions
                    where tenant_id = %s
                    """,
                    (normalized_tenant_id,),
                )
                or []
            )
            old_watermark_rows = list(
                transaction.fetch_all(
                    """
                    select sync_key, payload
                    from app.oa_sync_watermarks
                    where sync_key like %s
                    """,
                    (f"oa_pending_payment_source:{normalized_tenant_id}:%",),
                )
                or []
            )

            old_statuses = {
                text(row.get("flow_id")) or "": {
                    "pay_status": int(row.get("pay_status") or 0),
                    "scope_month": _month(row.get("scope_month")),
                    "source_signature": text(row.get("source_signature")) or "",
                }
                for row in old_status_rows
                if text(row.get("flow_id"))
            }
            old_admissions = {
                (_month(row.get("scope_key")) or "", text(row.get("oa_id")) or ""): {
                    "source_signature": text(row.get("source_signature")) or "",
                    "source_payload": _dict(row.get("source_payload")),
                }
                for row in old_admission_rows
                if _month(row.get("scope_key")) and text(row.get("oa_id"))
            }
            old_watermarks = {
                str(row.get("sync_key") or "").rsplit(":", 1)[-1]: _dict(row.get("payload"))
                for row in old_watermark_rows
                if str(row.get("sync_key") or "").startswith(
                    f"oa_pending_payment_source:{normalized_tenant_id}:"
                )
            }

            replaced_scopes = _replaced_scopes(
                normalized_scope_key,
                normalized_admission_records,
                old_admissions,
                old_watermarks,
            )
            record_scope_by_flow = _record_scope_by_flow(normalized_admission_records)
            removed_payment_status_flow_ids = _removed_payment_status_flow_ids(
                scope_key=normalized_scope_key,
                current_flow_ids=set(record_scope_by_flow),
                old_statuses=old_statuses,
                old_admissions=old_admissions,
            )
            new_statuses: dict[str, dict[str, Any]] = {}
            for flow_id, status in normalized_statuses.items():
                if flow_id in removed_payment_status_flow_ids:
                    continue
                scope_month = record_scope_by_flow.get(flow_id) or _month(
                    (old_statuses.get(flow_id) or {}).get("scope_month")
                )
                payload = {
                    "flow_id": flow_id,
                    "pay_status": status.pay_status,
                    "scope_month": scope_month,
                }
                new_statuses[flow_id] = {**payload, "source_signature": _signature(payload)}

            completed_owner_cleanup_scopes = {
                admission_scope
                for (admission_scope, oa_id) in old_admissions
                if oa_id in completed_owner_ids
            }
            new_admissions = dict(old_admissions) if normalized_scope_key != "all" else {}
            for key in [key for key in new_admissions if key[0] in replaced_scopes]:
                new_admissions.pop(key, None)
            for key in [key for key in new_admissions if key[1] in completed_owner_ids]:
                new_admissions.pop(key, None)
            for record in normalized_admission_records:
                scope_month = _month(record.month)
                flow_id = _record_flow_id(record)
                if (
                    not scope_month
                    or not flow_id
                    or flow_id not in new_statuses
                    or is_completed_workflow_status(record.workflow_status)
                    or record.id in completed_owner_ids
                ):
                    continue
                payload = _admission_payload(record, flow_id=flow_id)
                new_admissions[(scope_month, text(record.id) or "")] = {
                    "source_signature": _signature(payload),
                    "source_payload": payload,
                }

            oa_pending_payment_changed_scopes = _changed_status_scopes(old_statuses, new_statuses)
            changed_admission_scopes = _changed_admission_scopes(old_admissions, new_admissions)
            oa_pending_payment_changed_scopes.update(changed_admission_scopes)
            touched_scopes = set(replaced_scopes)
            if normalized_scope_key != "all":
                touched_scopes.add(normalized_scope_key)
            elif not touched_scopes and not old_watermarks:
                touched_scopes.add("all")

            completed_signatures = _completed_signatures(normalized_completed_records)
            completed_projection_changed_scopes: set[str] = set()
            for scope in sorted(touched_scopes):
                previous = old_watermarks.get(scope) or {}
                completed_signature = completed_signatures.get(scope, _signature([]))
                if (text(previous.get("completed_oa_signature")) or _signature([])) != completed_signature:
                    completed_projection_changed_scopes.add(scope)
                expected_payload = _watermark_payload(
                    scope_key=scope,
                    completed_oa_signature=completed_signature,
                    statuses=new_statuses,
                    admissions=new_admissions,
                )
                if _source_contract(previous) != _source_contract(expected_payload):
                    oa_pending_payment_changed_scopes.add(scope)

            unknown_status_change = any(
                not _month((old_statuses.get(flow_id) or {}).get("scope_month"))
                and not _month((new_statuses.get(flow_id) or {}).get("scope_month"))
                for flow_id in set(old_statuses) ^ set(new_statuses)
            ) or any(
                (old_statuses.get(flow_id) or {}).get("pay_status")
                != (new_statuses.get(flow_id) or {}).get("pay_status")
                and not (
                    _month((old_statuses.get(flow_id) or {}).get("scope_month"))
                    or _month((new_statuses.get(flow_id) or {}).get("scope_month"))
                )
                for flow_id in set(old_statuses) & set(new_statuses)
            )
            if unknown_status_change:
                oa_pending_payment_changed_scopes.add("all")

            self._replace_payment_statuses(
                transaction,
                tenant_id=normalized_tenant_id,
                statuses=new_statuses,
            )
            self._replace_admissions(
                transaction,
                tenant_id=normalized_tenant_id,
                replaced_scopes=(replaced_scopes | completed_owner_cleanup_scopes).intersection(
                    changed_admission_scopes
                ),
                admissions=new_admissions,
            )

            current_oa_row_ids = {
                oa_id for admission_scope, oa_id in new_admissions if admission_scope in replaced_scopes
            }
            current_oa_row_ids.update(record.id for record in normalized_completed_records)
            unavailable_oa_row_ids = sorted(
                (
                    {
                        oa_id
                        for admission_scope, oa_id in old_admissions
                        if admission_scope in replaced_scopes
                    }
                    | normalized_removed_projection_oa_row_ids
                )
                - current_oa_row_ids
            )
            cleanup_results: list[dict[str, object]] = []
            relation_cleanup_scopes: set[str] = set()
            if unavailable_oa_row_ids:
                relation_command_service = self._relation_command_service_for_transaction(transaction)
                cleanup_result = relation_command_service.remove_rows_from_active_relations(
                    row_ids=unavailable_oa_row_ids,
                    actor_id="system:oa_pending_payment_source_sync",
                    reason="OA 已不在已完成或进行中事实集中，移除失效关系成员。",
                    emit_payment_status_reconcile=False,
                )
                normalized_cleanup_result = dict(cleanup_result)
                cleanup_results.append(normalized_cleanup_result)
                cleanup_affected_scopes = {
                    scope
                    for value in list(normalized_cleanup_result.get("affected_months") or [])
                    if (scope := _month(value))
                }
                if list(normalized_cleanup_result.get("changed_case_ids") or []) and not cleanup_affected_scopes:
                    cleanup_affected_scopes.update(replaced_scopes)
                oa_pending_payment_changed_scopes.update(cleanup_affected_scopes)
                relation_cleanup_scopes.update(cleanup_affected_scopes)

            external_removed_flow_ids = sorted(
                removed_payment_status_flow_ids.intersection(normalized_statuses)
            )
            if external_removed_flow_ids:
                RuntimeQueueRepository(transaction).enqueue_in_transaction(
                    transaction=transaction,
                    event_type=OA_PAYMENT_STATUS_RECONCILE_EVENT,
                    aggregate_type="oa_source_snapshot",
                    aggregate_id=normalized_scope_key,
                    scope_type="oa_payment_status",
                    scope_key=normalized_scope_key,
                    payload={
                        "operation": OA_PAYMENT_STATUS_REMOVE_MISSING_OPERATION,
                        "removed_flow_ids": external_removed_flow_ids,
                        "reason": "authoritative_oa_removed",
                    },
                    tenant_id=normalized_tenant_id,
                    priority="high",
                )

            source_signatures: dict[str, str] = {}
            for scope in sorted(
                oa_pending_payment_changed_scopes,
                key=lambda value: (value == "all", value),
            ):
                previous = old_watermarks.get(scope) or {}
                completed_signature = (
                    completed_signatures.get(scope, _signature([]))
                    if scope in touched_scopes
                    else text(previous.get("completed_oa_signature")) or _signature([])
                )
                payload = _watermark_payload(
                    scope_key=scope,
                    completed_oa_signature=completed_signature,
                    statuses=new_statuses,
                    admissions=new_admissions,
                )
                self._save_watermark(
                    transaction,
                    tenant_id=normalized_tenant_id,
                    scope_key=scope,
                    payload=payload,
                )
                source_signatures[scope] = str(payload["source_signature"])

            matching_changed_scopes = {
                *changed_admission_scopes,
                *completed_projection_changed_scopes,
                *relation_cleanup_scopes,
            }
            matching_scope_months = {
                month
                for scope in matching_changed_scopes
                if (month := _month(scope))
            }
            if "all" in matching_changed_scopes:
                matching_scope_months.update(
                    scope
                    for scope, _oa_id in {*old_admissions, *new_admissions}
                    if _month(scope)
                )
                matching_scope_months.update(
                    month
                    for status in [*old_statuses.values(), *new_statuses.values()]
                    if (month := _month(status.get("scope_month")))
                )
                matching_scope_months.update(
                    month
                    for record in normalized_completed_records
                    if (month := _month(record.month))
                )
            expanded_matching_months = sorted(
                {
                    expanded
                    for month in matching_scope_months
                    for expanded in expand_scope_month_window(month)
                }
            )
            if expanded_matching_months:
                PostgresWorkbenchMatchingQueueRepository.mark_workbench_matching_dirty_scopes_in_transaction(
                    transaction=transaction,
                    tenant_id=normalized_tenant_id,
                    scope_months=expanded_matching_months,
                    reason="oa_pending_payment_source_changed",
                    source_versions={},
                    debounce_seconds=0,
                )

            return OaPendingPaymentSourceSnapshotResult(
                completed_projection_changed_scopes=tuple(
                    sorted(completed_projection_changed_scopes, key=lambda value: (value == "all", value))
                ),
                oa_pending_payment_changed_scopes=tuple(
                    sorted(oa_pending_payment_changed_scopes, key=lambda value: (value == "all", value))
                ),
                payment_status_count=len(new_statuses),
                admission_count=len(new_admissions),
                source_signatures=source_signatures,
                pending_admission_changed_scopes=tuple(
                    sorted(changed_admission_scopes, key=lambda value: (value == "all", value))
                ),
                relation_cleanup=tuple(cleanup_results),
                removed_payment_status_flow_ids=tuple(
                    sorted(removed_payment_status_flow_ids)
                ),
            )

        if transaction is not None:
            return write(transaction)
        return run_in_transaction(self._connection, write)

    def commit_authoritative_snapshot(
        self,
        *,
        scope_key: str,
        projection_records: list[OAApplicationRecord],
        admission_records: list[OAApplicationRecord],
        payment_statuses: dict[str, OAPaymentStatusRecord],
        retention_cutoff_month: str | None = None,
        tenant_id: str = "default",
    ) -> OaPendingPaymentSourceSnapshotResult:
        """Commit completed OA facts and all pending-payment inputs as one PostgreSQL write."""

        normalized_projection_records = _canonical_owner_records([
            record for record in list(projection_records or []) if isinstance(record, OAApplicationRecord)
        ])
        normalized_admission_records = _canonical_owner_records([
            record for record in list(admission_records or []) if isinstance(record, OAApplicationRecord)
        ])
        completed_records = [
            record
            for record in normalized_projection_records
            if is_completed_workflow_status(record.workflow_status)
        ]

        def write(transaction: Any) -> OaPendingPaymentSourceSnapshotResult:
            _lock_oa_owner_writes(
                transaction,
                tenant_id=text(tenant_id) or "default",
            )
            projection_repository = PostgresOAProjectionRepository(transaction)
            upserted_count = projection_repository.upsert_application_records(completed_records, scope_key=scope_key)
            removed_stale_row_ids = (
                projection_repository.delete_stale_completed_application_records(
                    scope_key=scope_key,
                    records=completed_records,
                    scanned_records=normalized_projection_records,
                )
                or []
            )
            removed_non_completed_row_ids = (
                projection_repository.delete_non_completed_application_records(
                    scope_key=scope_key,
                    records=normalized_admission_records,
                )
                or []
            )
            pruned_scope_keys = (
                projection_repository.prune_records_before(retention_cutoff_month)
                if scope_key == "all" and retention_cutoff_month
                else []
            )
            snapshot = self.replace_authoritative_snapshot(
                scope_key=scope_key,
                completed_projection_records=completed_records,
                admission_records=normalized_admission_records,
                payment_statuses=payment_statuses,
                removed_projection_oa_row_ids=[
                    *removed_stale_row_ids,
                    *removed_non_completed_row_ids,
                ],
                tenant_id=tenant_id,
                transaction=transaction,
            )
            return OaPendingPaymentSourceSnapshotResult(
                completed_projection_changed_scopes=snapshot.completed_projection_changed_scopes,
                oa_pending_payment_changed_scopes=snapshot.oa_pending_payment_changed_scopes,
                payment_status_count=snapshot.payment_status_count,
                admission_count=snapshot.admission_count,
                source_signatures=snapshot.source_signatures,
                pending_admission_changed_scopes=snapshot.pending_admission_changed_scopes,
                relation_cleanup=snapshot.relation_cleanup,
                upserted_completed_count=upserted_count,
                removed_stale_completed_count=len(removed_stale_row_ids),
                removed_non_completed_count=len(removed_non_completed_row_ids),
                pruned_scope_keys=tuple(sorted(set(pruned_scope_keys or []))),
                removed_payment_status_flow_ids=snapshot.removed_payment_status_flow_ids,
            )

        return run_in_transaction(self._connection, write)

    def record_payment_statuses(
        self,
        *,
        records: list[OAApplicationRecord],
        pay_statuses_by_flow_id: dict[str, int],
        tenant_id: str = "default",
    ) -> OaPendingPaymentSourceSnapshotResult:
        """Reconcile external payment status writes into the canonical PG snapshot."""

        normalized_tenant_id = text(tenant_id) or "default"
        reconciled_rows: dict[str, dict[str, Any]] = {}
        for record in list(records or []):
            if not isinstance(record, OAApplicationRecord):
                raise ValueError("OA payment-status reconciliation requires OAApplicationRecord values.")
            flow_id = _record_flow_id(record)
            scope_month = _month(record.month)
            if not flow_id or not scope_month:
                raise ValueError(f"OA payment-status reconciliation requires flow_id and month for {record.id}.")
            if flow_id not in pay_statuses_by_flow_id:
                raise ValueError(f"OA payment-status reconciliation requires a status for {flow_id}.")
            pay_status = int(pay_statuses_by_flow_id[flow_id])
            if pay_status not in {PAY_STATUS_PENDING, PAY_STATUS_PAID}:
                raise ValueError(f"Unsupported OA payment status for snapshot reconciliation: {pay_status}.")
            payload = {
                "flow_id": flow_id,
                "pay_status": pay_status,
                "scope_month": scope_month,
            }
            reconciled_rows[flow_id] = {**payload, "source_signature": _signature(payload)}

        if not reconciled_rows:
            return OaPendingPaymentSourceSnapshotResult(
                completed_projection_changed_scopes=(),
                oa_pending_payment_changed_scopes=(),
                payment_status_count=0,
                admission_count=0,
                source_signatures={},
            )

        def write(transaction: Any) -> OaPendingPaymentSourceSnapshotResult:
            current_rows = list(
                transaction.fetch_all(
                    """
                    select flow_id, pay_status, to_char(scope_month, 'YYYY-MM') as scope_month, source_signature
                    from app.oa_pending_payment_status_snapshots
                    where tenant_id = %s
                    """,
                    (normalized_tenant_id,),
                )
                or []
            )
            statuses = {
                text(row.get("flow_id")) or "": {
                    "flow_id": text(row.get("flow_id")) or "",
                    "pay_status": int(row.get("pay_status") or 0),
                    "scope_month": _month(row.get("scope_month")),
                    "source_signature": text(row.get("source_signature")) or "",
                }
                for row in current_rows
                if text(row.get("flow_id"))
            }
            changed_scopes: set[str] = set()
            changed_rows: list[dict[str, Any]] = []
            for flow_id, reconciled_row in reconciled_rows.items():
                current = statuses.get(flow_id) or {}
                if (
                    int(current.get("pay_status") or 0),
                    _month(current.get("scope_month")),
                ) == (reconciled_row["pay_status"], reconciled_row["scope_month"]):
                    continue
                for scope in (_month(current.get("scope_month")), reconciled_row["scope_month"]):
                    if scope:
                        changed_scopes.add(scope)
                statuses[flow_id] = reconciled_row
                changed_rows.append(reconciled_row)

            if not changed_rows:
                return OaPendingPaymentSourceSnapshotResult(
                    completed_projection_changed_scopes=(),
                    oa_pending_payment_changed_scopes=(),
                    payment_status_count=len(statuses),
                    admission_count=0,
                    source_signatures={},
                )

            watermark_rows = list(
                transaction.fetch_all(
                    """
                    select sync_key, payload
                    from app.oa_sync_watermarks
                    where sync_key = any(%s::text[])
                    """,
                    (
                        [
                            f"oa_pending_payment_source:{normalized_tenant_id}:{scope}"
                            for scope in sorted(changed_scopes)
                        ],
                    ),
                )
                or []
            )
            watermarks = {
                str(row.get("sync_key") or "").rsplit(":", 1)[-1]: _dict(row.get("payload"))
                for row in watermark_rows
            }
            missing_scopes = sorted(changed_scopes.difference(watermarks))
            if missing_scopes:
                raise RuntimeError(
                    "OA pending payment source snapshot is not initialized for scopes: "
                    + ", ".join(missing_scopes)
                )

            self._upsert_payment_statuses(
                transaction,
                tenant_id=normalized_tenant_id,
                rows=changed_rows,
            )
            source_signatures: dict[str, str] = {}
            for scope in sorted(changed_scopes):
                previous = watermarks[scope]
                payload = _payment_status_writeback_watermark_payload(
                    scope_key=scope,
                    previous=previous,
                    statuses=statuses,
                )
                self._save_watermark(
                    transaction,
                    tenant_id=normalized_tenant_id,
                    scope_key=scope,
                    payload=payload,
                )
                source_signatures[scope] = str(payload["source_signature"])

            return OaPendingPaymentSourceSnapshotResult(
                completed_projection_changed_scopes=(),
                oa_pending_payment_changed_scopes=tuple(sorted(changed_scopes)),
                payment_status_count=len(statuses),
                admission_count=sum(
                    int(watermarks[scope].get("admission_count") or 0)
                    for scope in changed_scopes
                ),
                source_signatures=source_signatures,
            )

        return run_in_transaction(self._connection, write)

    @staticmethod
    def _replace_payment_statuses(
        transaction: Any,
        *,
        tenant_id: str,
        statuses: dict[str, dict[str, Any]],
    ) -> None:
        rows = [statuses[flow_id] for flow_id in sorted(statuses)]
        transaction.execute(
            """
            delete from app.oa_pending_payment_status_snapshots
            where tenant_id = %s
              and not (flow_id = any(%s::text[]))
            """,
            (tenant_id, [row["flow_id"] for row in rows]),
        )
        if not rows:
            return
        transaction.execute(
            """
            insert into app.oa_pending_payment_status_snapshots(
                tenant_id, flow_id, pay_status, scope_month, source_signature, synced_at, updated_at
            )
            select %s, item.flow_id, item.pay_status, (item.scope_month || '-01')::date, item.source_signature, now(), now()
            from jsonb_to_recordset(%s::jsonb) as item(
                flow_id text, pay_status integer, scope_month text, source_signature text
            )
            on conflict (tenant_id, flow_id) do update set
                pay_status = excluded.pay_status,
                scope_month = excluded.scope_month,
                source_signature = excluded.source_signature,
                synced_at = now(),
                updated_at = now()
            where (
                app.oa_pending_payment_status_snapshots.pay_status,
                app.oa_pending_payment_status_snapshots.scope_month,
                app.oa_pending_payment_status_snapshots.source_signature
            ) is distinct from (
                excluded.pay_status,
                excluded.scope_month,
                excluded.source_signature
            )
            """,
            (tenant_id, jsonb(rows)),
        )

    @staticmethod
    def _upsert_payment_statuses(
        transaction: Any,
        *,
        tenant_id: str,
        rows: list[dict[str, Any]],
    ) -> None:
        if not rows:
            return
        transaction.execute(
            """
            insert into app.oa_pending_payment_status_snapshots(
                tenant_id, flow_id, pay_status, scope_month, source_signature, synced_at, updated_at
            )
            select %s, item.flow_id, item.pay_status, (item.scope_month || '-01')::date, item.source_signature, now(), now()
            from jsonb_to_recordset(%s::jsonb) as item(
                flow_id text, pay_status integer, scope_month text, source_signature text
            )
            on conflict (tenant_id, flow_id) do update set
                pay_status = excluded.pay_status,
                scope_month = excluded.scope_month,
                source_signature = excluded.source_signature,
                synced_at = now(),
                updated_at = now()
            """,
            (tenant_id, jsonb(rows)),
        )

    @staticmethod
    def _replace_admissions(
        transaction: Any,
        *,
        tenant_id: str,
        replaced_scopes: set[str],
        admissions: dict[tuple[str, str], dict[str, Any]],
    ) -> None:
        if not replaced_scopes:
            return
        transaction.execute(
            """
            delete from app.oa_pending_payment_admissions
            where tenant_id = %s and scope_key = any(%s::text[])
            """,
            (tenant_id, sorted(replaced_scopes)),
        )
        rows = []
        for (scope_key, oa_id), admission in sorted(admissions.items()):
            if scope_key not in replaced_scopes:
                continue
            payload = dict(admission["source_payload"])
            rows.append(
                {
                    "scope_key": scope_key,
                    "oa_id": oa_id,
                    "workflow_status": text(payload.get("workflow_status")),
                    "applicant": text(payload.get("applicant")),
                    "project_name": text(payload.get("project_name")),
                    "project_name_display": text(payload.get("project_name_display")),
                    "amount": text(payload.get("amount")),
                    "source_signature": admission["source_signature"],
                    "source_payload": payload,
                }
            )
        if not rows:
            return
        transaction.execute(
            """
            insert into app.oa_pending_payment_admissions(
                tenant_id, scope_key, oa_id, workflow_status, applicant,
                project_name, project_name_display, amount, source_signature,
                source_payload, raw_payload, registered_at, updated_at
            )
            select
                %s, item.scope_key, item.oa_id, item.workflow_status, item.applicant,
                item.project_name, item.project_name_display, nullif(item.amount, '')::numeric,
                item.source_signature, item.source_payload, jsonb_build_object('normalized_payload', item.source_payload),
                now(), now()
            from jsonb_to_recordset(%s::jsonb) as item(
                scope_key text, oa_id text, workflow_status text, applicant text,
                project_name text, project_name_display text, amount text,
                source_signature text, source_payload jsonb
            )
            """,
            (tenant_id, jsonb(rows)),
        )

    @staticmethod
    def _replace_targeted_admissions(
        transaction: Any,
        *,
        tenant_id: str,
        changed_oa_ids: set[str],
        admissions: dict[str, dict[str, Any]],
    ) -> None:
        normalized_oa_ids = sorted(
            oa_id for value in changed_oa_ids if (oa_id := text(value))
        )
        if not normalized_oa_ids:
            return
        transaction.execute(
            """
            delete from app.oa_pending_payment_admissions
            where tenant_id = %s and oa_id = any(%s::text[])
            """,
            (tenant_id, normalized_oa_ids),
        )
        rows: list[dict[str, Any]] = []
        for oa_id in normalized_oa_ids:
            admission = admissions.get(oa_id)
            if not admission:
                continue
            payload = dict(admission["source_payload"])
            rows.append(
                {
                    "scope_key": admission["scope_key"],
                    "oa_id": oa_id,
                    "workflow_status": text(payload.get("workflow_status")),
                    "applicant": text(payload.get("applicant")),
                    "project_name": text(payload.get("project_name")),
                    "project_name_display": text(payload.get("project_name_display")),
                    "amount": text(payload.get("amount")),
                    "source_signature": admission["source_signature"],
                    "source_payload": payload,
                }
            )
        if not rows:
            return
        transaction.execute(
            """
            insert into app.oa_pending_payment_admissions(
                tenant_id, scope_key, oa_id, workflow_status, applicant,
                project_name, project_name_display, amount, source_signature,
                source_payload, raw_payload, registered_at, updated_at
            )
            select
                %s, item.scope_key, item.oa_id, item.workflow_status, item.applicant,
                item.project_name, item.project_name_display, nullif(item.amount, '')::numeric,
                item.source_signature, item.source_payload,
                jsonb_build_object('normalized_payload', item.source_payload),
                now(), now()
            from jsonb_to_recordset(%s::jsonb) as item(
                scope_key text, oa_id text, workflow_status text, applicant text,
                project_name text, project_name_display text, amount text,
                source_signature text, source_payload jsonb
            )
            """,
            (tenant_id, jsonb(rows)),
        )

    @staticmethod
    def _save_watermark(
        transaction: Any,
        *,
        tenant_id: str,
        scope_key: str,
        payload: dict[str, Any],
    ) -> None:
        transaction.execute(
            """
            insert into app.oa_sync_watermarks(
                sync_key, form_id, last_success_at, status, payload, raw_payload
            )
            values (%s, %s, now(), 'succeeded', %s, %s)
            on conflict (sync_key) do update set
                form_id = excluded.form_id,
                last_success_at = excluded.last_success_at,
                status = excluded.status,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                version = case
                    when app.oa_sync_watermarks.payload is distinct from excluded.payload
                    then app.oa_sync_watermarks.version + 1
                    else app.oa_sync_watermarks.version
                end,
                updated_at = now()
            """,
            (
                f"oa_pending_payment_source:{tenant_id}:{scope_key}",
                scope_key,
                jsonb(payload),
                jsonb({"normalized_payload": payload}),
            ),
        )



class PostgresOaPendingPaymentStatusSnapshotReader:
    def __init__(self, connection: Any, *, scope_key: str | None = None, tenant_id: str = "default") -> None:
        self._connection = connection
        self._scope_key = _month(scope_key)
        self._tenant_id = text(tenant_id) or "default"

    @staticmethod
    def resolve_flow_id(record: OAApplicationRecord) -> str | None:
        return _record_flow_id(record)

    def list_payment_statuses(self) -> dict[str, OAPaymentStatusRecord]:
        params: list[object] = [self._tenant_id]
        scope_clause = ""
        if self._scope_key:
            scope_clause = "and scope_month = %s::date"
            params.append(f"{self._scope_key}-01")
        rows = self._connection.fetch_all(
            f"""
            select flow_id, pay_status
            from app.oa_pending_payment_status_snapshots
            where tenant_id = %s
              {scope_clause}
            order by flow_id
            """,
            tuple(params),
        )
        return {
            flow_id: OAPaymentStatusRecord(flow_id=flow_id, pay_status=int(row.get("pay_status") or 0))
            for row in list(rows or [])
            if isinstance(row, dict) and (flow_id := text(row.get("flow_id")))
        }

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None:
        normalized_flow_id = text(flow_id)
        if not normalized_flow_id:
            return None
        row = self._connection.fetch_one(
            """
            select flow_id, pay_status
            from app.oa_pending_payment_status_snapshots
            where tenant_id = %s and flow_id = %s
            """,
            (self._tenant_id, normalized_flow_id),
        )
        if not isinstance(row, dict):
            return None
        return OAPaymentStatusRecord(flow_id=normalized_flow_id, pay_status=int(row.get("pay_status") or 0))


def oa_pending_payment_source_versions_from_snapshot(
    connection: Any,
    *,
    scope_key: str,
    tenant_id: str = "default",
) -> dict[str, object]:
    normalized_scope_key = _scope_key(scope_key)
    row = connection.fetch_one(
        """
        select version, payload
        from app.oa_sync_watermarks
        where sync_key = %s
        """,
        (f"oa_pending_payment_source:{text(tenant_id) or 'default'}:{normalized_scope_key}",),
    )
    if not isinstance(row, dict):
        return {}
    payload = _dict(row.get("payload"))
    return {
        "oa_pending_payment_source_snapshot_version": int(row.get("version") or 0),
        "completed_oa_signature": text(payload.get("completed_oa_signature")) or "",
        "in_progress_admission_signature": text(payload.get("admission_signature")) or "",
        "payment_status_signature": text(payload.get("payment_status_signature")) or "",
        "oa_pending_payment_source_signature": text(payload.get("source_signature")) or "",
    }


def _canonical_owner_records(records: list[OAApplicationRecord]) -> list[OAApplicationRecord]:
    """Select one deterministic owner per canonical OA row; completed is monotonic."""

    records_by_id: dict[str, OAApplicationRecord] = {}
    for record in list(records or []):
        if not isinstance(record, OAApplicationRecord):
            raise ValueError("OA owner snapshot contains an unsupported record.")
        row_id = text(record.id)
        if not row_id:
            raise ValueError("OA owner snapshot contains an empty row_id.")
        current = records_by_id.get(row_id)
        if current is None:
            records_by_id[row_id] = record
            continue
        current_completed = is_completed_workflow_status(current.workflow_status)
        candidate_completed = is_completed_workflow_status(record.workflow_status)
        if current_completed != candidate_completed:
            records_by_id[row_id] = current if current_completed else record
            continue
        raise ValueError(f"OA owner snapshot contains duplicate winning row_id: {row_id}.")
    return [records_by_id[row_id] for row_id in sorted(records_by_id)]


def _lock_oa_owner_writes(transaction: Any, *, tenant_id: str) -> None:
    transaction.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"oa_owner:{tenant_id}",),
    )


def _normalized_statuses(statuses: dict[str, OAPaymentStatusRecord]) -> dict[str, OAPaymentStatusRecord]:
    normalized: dict[str, OAPaymentStatusRecord] = {}
    for key, value in dict(statuses or {}).items():
        if isinstance(value, OAPaymentStatusRecord):
            flow_id = text(value.flow_id) or text(key)
            pay_status = value.pay_status
        elif isinstance(value, dict):
            flow_id = text(value.get("flow_id")) or text(key)
            pay_status = value.get("pay_status")
        else:
            raise ValueError("OA payment status snapshot contains an unsupported record.")
        if not flow_id:
            raise ValueError("OA payment status snapshot contains an empty flow_id.")
        if isinstance(pay_status, bool):
            raise ValueError(f"OA payment status snapshot contains an invalid pay_status for {flow_id}.")
        try:
            normalized_pay_status = int(pay_status)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"OA payment status snapshot contains an invalid pay_status for {flow_id}.") from exc
        normalized[flow_id] = OAPaymentStatusRecord(flow_id=flow_id, pay_status=normalized_pay_status)
    return normalized


def _record_flow_id(record: OAApplicationRecord) -> str | None:
    candidates = oa_flow_id_candidates(record)
    return candidates.payment_flow_ids[0] if candidates.payment_flow_ids else None


def _record_scope_by_flow(records: list[OAApplicationRecord]) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in records:
        flow_id = _record_flow_id(record)
        scope_month = _month(record.month)
        if flow_id and scope_month:
            result[flow_id] = scope_month
    return result


def _replaced_scopes(
    scope_key: str,
    records: list[OAApplicationRecord],
    old_admissions: dict[tuple[str, str], dict[str, Any]],
    old_watermarks: dict[str, dict[str, Any]],
) -> set[str]:
    if scope_key != "all":
        return {scope_key}
    scopes = {_month(record.month) for record in records}
    scopes.update(key[0] for key in old_admissions)
    scopes.update(_month(scope) for scope in old_watermarks)
    return {scope for scope in scopes if scope}


def _removed_payment_status_flow_ids(
    *,
    scope_key: str,
    current_flow_ids: set[str],
    old_statuses: dict[str, dict[str, Any]],
    old_admissions: dict[tuple[str, str], dict[str, Any]],
) -> set[str]:
    if scope_key != "all":
        return set()
    previously_managed_flow_ids = {
        flow_id
        for flow_id, status in old_statuses.items()
        if _month(status.get("scope_month"))
    }
    previously_managed_flow_ids.update(
        flow_id
        for admission in old_admissions.values()
        if (
            flow_id := text(
                _dict(admission.get("source_payload")).get("flow_id")
            )
        )
    )
    return previously_managed_flow_ids - current_flow_ids


def _changed_status_scopes(
    old: dict[str, dict[str, Any]],
    new: dict[str, dict[str, Any]],
) -> set[str]:
    scopes: set[str] = set()
    for flow_id in set(old) | set(new):
        old_row = old.get(flow_id) or {}
        new_row = new.get(flow_id) or {}
        if (
            old_row.get("pay_status"),
            _month(old_row.get("scope_month")),
        ) == (
            new_row.get("pay_status"),
            _month(new_row.get("scope_month")),
        ):
            continue
        for scope in (_month(old_row.get("scope_month")), _month(new_row.get("scope_month"))):
            if scope:
                scopes.add(scope)
    return scopes


def _changed_admission_scopes(
    old: dict[tuple[str, str], dict[str, Any]],
    new: dict[tuple[str, str], dict[str, Any]],
) -> set[str]:
    scopes: set[str] = set()
    for key in set(old) | set(new):
        if (old.get(key) or {}).get("source_signature") != (new.get(key) or {}).get("source_signature"):
            scopes.add(key[0])
    return scopes


def _completed_signatures(records: list[OAApplicationRecord]) -> dict[str, str]:
    by_scope: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        scope = _month(record.month)
        if scope and is_completed_workflow_status(record.workflow_status):
            by_scope.setdefault(scope, []).append(_record_payload(record))
    record_scopes = {_month(record.month) for record in records}
    return {
        scope: _signature(sorted(by_scope.get(scope, []), key=lambda payload: str(payload.get("id") or "")))
        for scope in record_scopes
        if scope
    }


def _watermark_payload(
    *,
    scope_key: str,
    completed_oa_signature: str,
    statuses: dict[str, dict[str, Any]],
    admissions: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    status_signatures = sorted(
        row["source_signature"]
        for row in statuses.values()
        if _month(row.get("scope_month")) == scope_key or scope_key == "all"
    )
    admission_signatures = sorted(
        admission["source_signature"]
        for (scope, _oa_id), admission in admissions.items()
        if scope == scope_key or scope_key == "all"
    )
    contract = {
        "completed_oa_signature": completed_oa_signature,
        "admission_signature": _signature(admission_signatures),
        "payment_status_signature": _signature(status_signatures),
    }
    return {
        "scope_key": scope_key,
        **contract,
        "source_signature": _signature(contract),
        "admission_count": len(admission_signatures),
        "payment_status_count": len(status_signatures),
    }


def _payment_status_writeback_watermark_payload(
    *,
    scope_key: str,
    previous: dict[str, Any],
    statuses: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    status_signatures = sorted(
        row["source_signature"]
        for row in statuses.values()
        if _month(row.get("scope_month")) == scope_key
    )
    contract = {
        "completed_oa_signature": text(previous.get("completed_oa_signature")) or _signature([]),
        "admission_signature": text(previous.get("admission_signature")) or _signature([]),
        "payment_status_signature": _signature(status_signatures),
    }
    return {
        "scope_key": scope_key,
        **contract,
        "source_signature": _signature(contract),
        "admission_count": int(previous.get("admission_count") or 0),
        "payment_status_count": len(status_signatures),
    }


def _source_contract(payload: dict[str, Any]) -> dict[str, str]:
    return {
        key: text(payload.get(key)) or ""
        for key in (
            "completed_oa_signature",
            "admission_signature",
            "payment_status_signature",
            "source_signature",
        )
    }


def _admission_payload(record: OAApplicationRecord, *, flow_id: str) -> dict[str, Any]:
    payload = _record_payload(record)
    project_name = text(payload.get("project_name"))
    return {
        **payload,
        "flow_id": flow_id,
        "project_name": project_name,
        "project_name_display": text(payload.get("project_name_display")) or project_name,
    }


def _record_payload(record: OAApplicationRecord) -> dict[str, Any]:
    payload = serialize_value(record)
    return dict(payload) if isinstance(payload, dict) else {}


def _scope_key(value: object) -> str:
    normalized = str(value or "").strip() or "all"
    if normalized == "all" or _month(normalized):
        return normalized
    raise ValueError("OA pending payment source snapshot scope must be YYYY-MM or all.")


def _month(value: object) -> str | None:
    normalized = str(value or "").strip()
    if len(normalized) >= 7 and normalized[4] == "-" and normalized[:4].isdigit() and normalized[5:7].isdigit():
        month = int(normalized[5:7])
        if 1 <= month <= 12:
            return normalized[:7]
    return None


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _signature(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
