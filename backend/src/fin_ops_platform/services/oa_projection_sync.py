from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from typing import Any

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.postgres_repositories.oa_projection import is_completed_workflow_status
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.search_read_model_refresh_producer import SearchReadModelRefreshProducer


MONTH_FORMAT = "%Y-%m"


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
    ) -> None:
        self._source_adapter = source_adapter
        self._projection_repository = projection_repository
        self._queue_repository = queue_repository
        self._retention_cutoff_date_provider = retention_cutoff_date_provider
        self._pending_payment_relation_promoter = pending_payment_relation_promoter
        self._search_read_model_refresh_producer = (
            search_read_model_refresh_producer
            or SearchReadModelRefreshProducer(
                refresh_gateway_provider=lambda: ReadModelRefreshGateway(queue_repository=self._queue_repository)
            )
        )

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        scope_key = self._event_scope_key(event)
        cutoff_month = self._retention_cutoff_month()
        records = self._sanitized_records(self._load_records(scope_key))
        completed_records = [record for record in records if _is_completed_workflow(record)]
        upserted_count = self._projection_repository.upsert_application_records(completed_records, scope_key=scope_key)
        removed_stale_completed_count = self._delete_stale_completed_projection_records(
            scope_key=scope_key,
            completed_records=completed_records,
            scanned_records=records,
        )
        removed_non_completed_count = self._delete_non_completed_projection_records(scope_key=scope_key, records=records)
        pruned_months = self._prune_before_cutoff(scope_key, cutoff_month)
        promotion_result = self._promote_completed_pending_payment_relations(completed_records)
        result = {
            "sync_type": "oa_projection",
            "scope_key": scope_key,
            "status": "succeeded",
            "scanned_count": len(records),
            "upserted_count": upserted_count,
            "skipped_count": max(0, len(records) - upserted_count),
            "removed_stale_completed_count": removed_stale_completed_count,
            "removed_non_completed_count": removed_non_completed_count,
            "pruned_count": len(pruned_months),
            "promoted_pending_payment_relation_count": int(promotion_result.get("promoted_count") or 0),
            "skipped_pending_payment_relation_promotion_count": int(promotion_result.get("skipped_count") or 0),
            "pending_payment_relation_promotion_error_count": int(promotion_result.get("error_count") or 0),
            "pending_payment_relation_promotion_errors": list(promotion_result.get("errors") or []),
            "error_count": int(promotion_result.get("error_count") or 0),
        }
        record_sync_run = getattr(self._projection_repository, "record_sync_run", None)
        if callable(record_sync_run):
            record_sync_run(result)
        self._mark_downstream_dirty(
            scope_key,
            records,
            extra_months=[*pruned_months, *list(promotion_result.get("affected_months") or [])],
        )
        return result

    @staticmethod
    def _event_scope_key(event: RuntimeQueueEvent) -> str:
        payload_scope = event.payload.get("scope_key") if isinstance(event.payload, dict) else None
        return str(payload_scope or event.scope_key or event.aggregate_id or "all").strip() or "all"

    def _load_records(self, scope_key: str) -> list[OAApplicationRecord]:
        cutoff_month = self._retention_cutoff_month()
        if cutoff_month and scope_key != "all" and self._is_month_scope(scope_key) and scope_key < cutoff_month:
            return []
        sync_parse = getattr(self._source_adapter, "force_attachment_invoice_sync_parse", None)
        context = sync_parse() if callable(sync_parse) else nullcontext()
        with context:
            return self._load_records_with_attachment_parse(scope_key, cutoff_month=cutoff_month)

    def _load_records_with_attachment_parse(self, scope_key: str, *, cutoff_month: str | None) -> list[OAApplicationRecord]:
        if scope_key != "all":
            return list(self._source_adapter.list_application_records(scope_key))
        list_months = getattr(self._source_adapter, "list_available_months", None)
        months = [
            month
            for month in (list(list_months()) if callable(list_months) else [])
            if self._is_month_scope(month) and (cutoff_month is None or month >= cutoff_month)
        ]
        if months:
            records: list[OAApplicationRecord] = []
            for month in months:
                records.extend(self._source_adapter.list_application_records(month))
            return records
        list_all = getattr(self._source_adapter, "list_all_application_records", None)
        if callable(list_all):
            return [
                record
                for record in list(list_all())
                if cutoff_month is None or not self._is_month_scope(str(record.month)) or str(record.month) >= cutoff_month
            ]
        records: list[OAApplicationRecord] = []
        for month in months:
            records.extend(self._source_adapter.list_application_records(month))
        return records

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
        extra_months: list[str] | None = None,
    ) -> None:
        months = {
            str(record.month).strip()
            for record in list(records or [])
            if str(getattr(record, "month", "")).strip()
        }
        months.update(month for month in list(extra_months or []) if month)
        if scope_key != "all" and scope_key:
            months.add(scope_key)
        target_scopes = sorted({month for month in months if month and month != "all"})
        if target_scopes:
            target_scopes.append("all")
        else:
            target_scopes = ["all"]
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            return
        refresh_gateway.enqueue_many("workbench", target_scopes, reason="oa_projection_sync")
        self._search_read_model_refresh_producer.enqueue(target_scopes, reason="oa_projection_sync")
        refresh_gateway.enqueue_many("oa_pending_payment", target_scopes, reason="oa_projection_sync")
        refresh_gateway.enqueue_many("pending_invoice", ["expense:all", "income:all"], reason="oa_projection_sync")


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
