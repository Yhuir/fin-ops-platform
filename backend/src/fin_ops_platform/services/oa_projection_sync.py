from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from typing import Any

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord
from fin_ops_platform.services.postgres_repositories.oa_projection import is_completed_workflow_status
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.search_read_model_refresh_producer import SearchReadModelRefreshProducer


MONTH_FORMAT = "%Y-%m"

OA_PROJECTION_SCOPED_READ_MODEL_DEPENDENTS = (
    "workbench_relation",
    "bank_detail",
    "invoice_lifecycle",
    "input_invoice_usage",
    "output_invoice_collection",
    "turnover_ledger",
    "no_oa_bank_batch",
    "bank_flow_rule_batch",
)


class OAProjectionSyncService:
    def __init__(
        self,
        *,
        source_adapter: Any,
        projection_repository: Any,
        queue_repository: Any,
        retention_cutoff_date_provider: Any | None = None,
        pending_payment_relation_promoter: Any | None = None,
        search_read_model_refresh_producer: Any | None = None,
        payment_status_repository: Any | None = None,
        pending_payment_source_snapshot_repository: Any | None = None,
        workbench_matching_dirty_queue: Any | None = None,
    ) -> None:
        if (payment_status_repository is None) != (pending_payment_source_snapshot_repository is None):
            raise ValueError(
                "payment_status_repository and pending_payment_source_snapshot_repository must be configured together."
            )
        self._source_adapter = source_adapter
        self._projection_repository = projection_repository
        self._queue_repository = queue_repository
        self._retention_cutoff_date_provider = retention_cutoff_date_provider
        self._pending_payment_relation_promoter = pending_payment_relation_promoter
        self._payment_status_repository = payment_status_repository
        self._pending_payment_source_snapshot_repository = pending_payment_source_snapshot_repository
        self._workbench_matching_dirty_queue = workbench_matching_dirty_queue
        self._search_read_model_refresh_producer = (
            search_read_model_refresh_producer
            or SearchReadModelRefreshProducer(
                refresh_gateway_provider=lambda: ReadModelRefreshGateway(queue_repository=self._queue_repository)
            )
        )

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        scope_key = self._event_scope_key(event)
        try:
            return self._run_sync(scope_key)
        except Exception as exc:
            self._record_failed_sync_run(scope_key=scope_key, error=exc)
            raise

    def _run_sync(self, scope_key: str) -> dict[str, Any]:
        cutoff_month = self._retention_cutoff_month()
        source_batch = self._load_source_batch(scope_key, cutoff_month=cutoff_month)
        projection_records = self._sanitized_records(list(source_batch["projection_records"]))
        admission_records = self._sanitized_records(list(source_batch["admission_records"]))
        payment_statuses = self._load_payment_statuses()
        completed_records = [record for record in projection_records if _is_completed_workflow(record)]
        if self._pending_payment_source_snapshot_repository is not None:
            source_snapshot_result = self._commit_pending_payment_source_snapshot(
                scope_key=scope_key,
                projection_records=projection_records,
                admission_records=admission_records,
                payment_statuses=payment_statuses,
                cutoff_month=cutoff_month,
            )
            upserted_count = int(getattr(source_snapshot_result, "upserted_completed_count", 0))
            removed_stale_completed_count = int(
                getattr(source_snapshot_result, "removed_stale_completed_count", 0)
            )
            removed_non_completed_count = int(
                getattr(source_snapshot_result, "removed_non_completed_count", 0)
            )
            pruned_months = list(getattr(source_snapshot_result, "pruned_scope_keys", ()))
        else:
            upserted_count = self._projection_repository.upsert_application_records(
                completed_records,
                scope_key=scope_key,
            )
            removed_stale_completed_count = self._delete_stale_completed_projection_records(
                scope_key=scope_key,
                completed_records=completed_records,
                scanned_records=projection_records,
            )
            removed_non_completed_count = self._delete_non_completed_projection_records(
                scope_key=scope_key,
                records=admission_records,
            )
            pruned_months = self._prune_before_cutoff(scope_key, cutoff_month)
            source_snapshot_result = None
        promotion_result = self._promote_completed_pending_payment_relations(completed_records)
        result = {
            "sync_type": "oa_projection",
            "scope_key": scope_key,
            "status": "succeeded",
            "scanned_count": len(admission_records),
            "scanned_projection_count": len(projection_records),
            "scanned_completed_count": sum(
                1 for record in admission_records if _is_completed_workflow(record)
            ),
            "scanned_in_progress_count": sum(
                1 for record in admission_records if not _is_completed_workflow(record)
            ),
            "upserted_count": upserted_count,
            "skipped_count": max(0, len(projection_records) - upserted_count),
            "removed_stale_completed_count": removed_stale_completed_count,
            "removed_non_completed_count": removed_non_completed_count,
            "pruned_count": len(pruned_months),
            "promoted_pending_payment_relation_count": int(promotion_result.get("promoted_count") or 0),
            "skipped_pending_payment_relation_promotion_count": int(promotion_result.get("skipped_count") or 0),
            "pending_payment_relation_promotion_error_count": int(promotion_result.get("error_count") or 0),
            "pending_payment_relation_promotion_errors": list(promotion_result.get("errors") or []),
            "error_count": int(promotion_result.get("error_count") or 0),
            "pending_payment_source_snapshot_count": (
                int(getattr(source_snapshot_result, "payment_status_count", 0))
                if source_snapshot_result is not None
                else 0
            ),
            "pending_payment_admission_count": (
                int(getattr(source_snapshot_result, "admission_count", 0))
                if source_snapshot_result is not None
                else 0
            ),
            "pending_payment_affected_scope_keys": (
                list(getattr(source_snapshot_result, "oa_pending_payment_changed_scopes", ()))
                if source_snapshot_result is not None
                else []
            ),
            "completed_projection_changed_scope_keys": (
                list(getattr(source_snapshot_result, "completed_projection_changed_scopes", ()))
                if source_snapshot_result is not None
                else []
            ),
        }
        record_sync_run = getattr(self._projection_repository, "record_sync_run", None)
        if callable(record_sync_run):
            record_sync_run(result)
        completed_projection_changed_scopes = (
            list(getattr(source_snapshot_result, "completed_projection_changed_scopes", ()))
            if source_snapshot_result is not None
            else None
        )
        promotion_scopes = list(promotion_result.get("affected_months") or [])
        self._mark_downstream_dirty(
            scope_key,
            projection_records,
            changed_scope_keys=completed_projection_changed_scopes,
            extra_months=[*pruned_months, *promotion_scopes],
        )
        if self._pending_payment_source_snapshot_repository is not None:
            self._mark_oa_pending_payment_dirty([*pruned_months, *promotion_scopes])
        return result

    def _record_failed_sync_run(self, *, scope_key: str, error: Exception) -> None:
        record_sync_run = getattr(self._projection_repository, "record_sync_run", None)
        if not callable(record_sync_run):
            return
        try:
            record_sync_run(
                {
                    "sync_type": "oa_projection",
                    "scope_key": scope_key,
                    "status": "failed",
                    "scanned_count": 0,
                    "upserted_count": 0,
                    "skipped_count": 0,
                    "error_count": 1,
                    "last_error": str(error),
                }
            )
        except Exception:
            return

    def _load_payment_statuses(self) -> dict[str, OAPaymentStatusRecord] | None:
        repository = self._payment_status_repository
        if repository is None:
            return None
        list_statuses = getattr(repository, "list_payment_statuses", None)
        if not callable(list_statuses):
            raise RuntimeError("payment_status_repository must expose list_payment_statuses().")
        statuses = list_statuses()
        if not isinstance(statuses, dict):
            raise RuntimeError("OA payment status source did not return a complete mapping.")
        return statuses

    def _commit_pending_payment_source_snapshot(
        self,
        *,
        scope_key: str,
        projection_records: list[OAApplicationRecord],
        admission_records: list[OAApplicationRecord],
        payment_statuses: dict[str, OAPaymentStatusRecord] | None,
        cutoff_month: str | None,
    ) -> Any:
        repository = self._pending_payment_source_snapshot_repository
        commit_snapshot = getattr(repository, "commit_authoritative_snapshot", None)
        if not callable(commit_snapshot):
            raise RuntimeError(
                "pending_payment_source_snapshot_repository must expose commit_authoritative_snapshot()."
            )
        if payment_statuses is None:
            raise RuntimeError("A complete OA payment status mapping is required before snapshot replacement.")
        return commit_snapshot(
            scope_key=scope_key,
            projection_records=projection_records,
            admission_records=admission_records,
            payment_statuses=payment_statuses,
            retention_cutoff_month=cutoff_month,
        )

    @staticmethod
    def _event_scope_key(event: RuntimeQueueEvent) -> str:
        payload_scope = event.payload.get("scope_key") if isinstance(event.payload, dict) else None
        return str(payload_scope or event.scope_key or event.aggregate_id or "all").strip() or "all"

    def _load_source_batch(self, scope_key: str, *, cutoff_month: str | None) -> dict[str, tuple[OAApplicationRecord, ...]]:
        if cutoff_month and scope_key != "all" and self._is_month_scope(scope_key) and scope_key < cutoff_month:
            return {"projection_records": (), "admission_records": ()}
        load_batch = getattr(self._source_adapter, "load_sync_application_batch", None)
        if not callable(load_batch):
            raise RuntimeError("OA sync source adapter must expose load_sync_application_batch().")
        sync_parse = getattr(self._source_adapter, "force_attachment_invoice_sync_parse", None)
        context = sync_parse() if callable(sync_parse) else nullcontext()
        with context:
            batch = load_batch(scope_key, retention_cutoff_month=cutoff_month)
        projection_records = getattr(batch, "projection_records", None)
        admission_records = getattr(batch, "admission_records", None)
        if not isinstance(projection_records, (list, tuple)) or not isinstance(admission_records, (list, tuple)):
            raise RuntimeError("OA sync source adapter returned an incomplete source batch.")

        def retained(records: list[OAApplicationRecord] | tuple[OAApplicationRecord, ...]) -> tuple[OAApplicationRecord, ...]:
            return tuple(
                record
                for record in records
                if cutoff_month is None
                or not self._is_month_scope(str(getattr(record, "month", "")))
                or str(record.month) >= cutoff_month
            )

        return {
            "projection_records": retained(projection_records),
            "admission_records": retained(admission_records),
        }

    def _retention_cutoff_month(self) -> str | None:
        provider = self._retention_cutoff_date_provider
        if not callable(provider):
            return None
        try:
            raw_value = provider()
        except Exception:
            return None
        text = str(raw_value or "").strip()
        if len(text) < 7:
            return None
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
        return parsed.strftime(MONTH_FORMAT)

    @staticmethod
    def _is_month_scope(value: object) -> bool:
        text = str(value or "").strip()
        if len(text) != 7:
            return False
        try:
            datetime.strptime(text, MONTH_FORMAT)
        except ValueError:
            return False
        return True

    @staticmethod
    def _sanitized_records(records: list[OAApplicationRecord]) -> list[OAApplicationRecord]:
        sanitized: list[OAApplicationRecord] = []
        for record in list(records or []):
            if not isinstance(record, OAApplicationRecord):
                continue
            expense_items = []
            for item in list(record.expense_items or []):
                if not isinstance(item, dict):
                    continue
                normalized_item = dict(item)
                normalized_item["attachment_evidences"] = [
                    dict(evidence)
                    for evidence in list(item.get("attachment_evidences") or [])
                    if _is_invoice_attachment_payload(evidence)
                ]
                normalized_item["attachment_artifacts"] = [
                    dict(artifact)
                    for artifact in list(item.get("attachment_artifacts") or [])
                    if _is_invoice_attachment_payload(artifact)
                ]
                expense_items.append(normalized_item)
            sanitized.append(
                replace(
                    record,
                    attachment_evidences=[
                        dict(evidence)
                        for evidence in list(record.attachment_evidences or [])
                        if _is_invoice_attachment_payload(evidence)
                    ],
                    attachment_artifacts=[
                        dict(artifact)
                        for artifact in list(record.attachment_artifacts or [])
                        if _is_invoice_attachment_payload(artifact)
                    ],
                    expense_items=expense_items,
                )
            )
        return sanitized

    def _prune_before_cutoff(self, scope_key: str, cutoff_month: str | None) -> list[str]:
        if scope_key != "all" or not cutoff_month:
            return []
        prune = getattr(self._projection_repository, "prune_records_before", None)
        if not callable(prune):
            return []
        return [
            month
            for month in list(prune(cutoff_month) or [])
            if self._is_month_scope(month)
        ]

    def _delete_stale_completed_projection_records(
        self,
        *,
        scope_key: str,
        completed_records: list[OAApplicationRecord],
        scanned_records: list[OAApplicationRecord],
    ) -> int:
        delete_stale_completed = getattr(self._projection_repository, "delete_stale_completed_application_records", None)
        if not callable(delete_stale_completed) or (scope_key == "all" and not scanned_records):
            return 0
        return len(
            list(
                delete_stale_completed(
                    scope_key=scope_key,
                    records=completed_records,
                    scanned_records=scanned_records,
                )
                or []
            )
        )

    def _delete_non_completed_projection_records(self, *, scope_key: str, records: list[OAApplicationRecord]) -> int:
        delete_non_completed = getattr(self._projection_repository, "delete_non_completed_application_records", None)
        if not callable(delete_non_completed) or (scope_key == "all" and not records):
            return 0
        return len(list(delete_non_completed(scope_key=scope_key, records=records) or []))

    def _promote_completed_pending_payment_relations(self, completed_records: list[OAApplicationRecord]) -> dict[str, Any]:
        promoter = self._pending_payment_relation_promoter
        if promoter is None:
            return {
                "promoted_count": 0,
                "skipped_count": 0,
                "error_count": 0,
                "errors": [],
                "affected_months": [],
            }
        promote = getattr(promoter, "promote_completed_records", None)
        if not callable(promote):
            raise RuntimeError("pending payment relation promoter must expose promote_completed_records().")
        result = promote(completed_records, actor_id="oa_projection_sync")
        return result if isinstance(result, dict) else {}

    def _mark_downstream_dirty(
        self,
        scope_key: str,
        records: list[OAApplicationRecord],
        *,
        changed_scope_keys: list[str] | None = None,
        extra_months: list[str] | None = None,
    ) -> None:
        if changed_scope_keys is None:
            months = {
                str(record.month).strip()
                for record in list(records or [])
                if str(getattr(record, "month", "")).strip()
            }
            if scope_key != "all" and scope_key:
                months.add(scope_key)
        else:
            months = {str(value).strip() for value in changed_scope_keys if str(value).strip()}
        months.update(month for month in list(extra_months or []) if month)
        if not months:
            return
        target_scopes = sorted({month for month in months if month and month != "all"})
        if target_scopes:
            target_scopes.append("all")
        else:
            target_scopes = ["all"]
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            return
        refresh_gateway.enqueue_many("workbench", target_scopes, reason="oa_projection_sync")
        matching_months = [scope for scope in target_scopes if scope != "all"]
        mark_matching_dirty = getattr(self._workbench_matching_dirty_queue, "mark_dirty_expanded", None)
        if matching_months and callable(mark_matching_dirty):
            mark_matching_dirty(
                matching_months,
                reason="oa_projection_sync",
                debounce_seconds=0,
            )
        self._search_read_model_refresh_producer.enqueue(target_scopes, reason="oa_projection_sync")
        if self._pending_payment_source_snapshot_repository is None:
            refresh_gateway.enqueue_many("oa_pending_payment", target_scopes, reason="oa_projection_sync")
        refresh_gateway.enqueue_many("pending_invoice", ["expense:all", "income:all"], reason="oa_projection_sync")
        concrete_month_scopes = [scope for scope in target_scopes if scope != "all"] or ["all"]
        for read_model_key in OA_PROJECTION_SCOPED_READ_MODEL_DEPENDENTS:
            refresh_gateway.enqueue_many(read_model_key, concrete_month_scopes, reason="oa_projection_sync")

    def _mark_oa_pending_payment_dirty(self, scope_keys: list[str]) -> None:
        normalized_scope_keys = sorted(
            {
                str(scope_key).strip()
                for scope_key in list(scope_keys or [])
                if str(scope_key).strip() == "all" or self._is_month_scope(scope_key)
            }
        )
        if not normalized_scope_keys:
            return
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if refresh_gateway.can_enqueue():
            refresh_gateway.enqueue_many(
                "oa_pending_payment",
                normalized_scope_keys,
                reason="oa_projection_relation_or_prune_changed",
            )


def _is_invoice_attachment_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    invoice_fields = (
        "invoice_no",
        "invoice_code",
        "digital_invoice_no",
        "seller_name",
        "seller_tax_no",
        "buyer_name",
        "buyer_tax_no",
        "total_with_tax",
        "tax_amount",
    )
    if any(str(value.get(field) or "").strip() for field in invoice_fields):
        return True
    kind_text = " ".join(
        str(value.get(field) or "").strip().lower()
        for field in ("source_kind", "evidence_type", "document_kind", "attachment_type", "file_type")
    )
    if any(token in kind_text for token in ("invoice", "发票", "payment_receipt", "payment", "receipt")):
        return True
    parse_status = str(value.get("parse_status") or "").strip()
    if parse_status:
        return True
    name_text = " ".join(
        str(value.get(field) or "").strip().lower()
        for field in ("source_attachment_name", "attachment_name", "filename", "name")
    )
    return any(token in name_text for token in ("发票", "invoice", "付款", "支付", "payment", "receipt"))


def _is_completed_workflow(record: OAApplicationRecord) -> bool:
    return is_completed_workflow_status(getattr(record, "workflow_status", ""))
