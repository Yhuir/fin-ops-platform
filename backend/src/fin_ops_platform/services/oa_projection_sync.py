from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from typing import Any

from fin_ops_platform.services.oa_adapter import (
    OAApplicationRecord,
    is_in_progress_expense_claim,
)
from fin_ops_platform.services.oa_attachment_refresh_request_service import (
    REFRESH_ATTACHMENTS_OPERATION,
)
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord
from fin_ops_platform.services.postgres_repositories.oa_projection import is_completed_workflow_status
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent

MONTH_FORMAT = "%Y-%m"
TARGETED_ATTACHMENT_FAILURE_STATUSES = frozenset({"download_failed", "parse_failed"})


class OAProjectionSyncService:
    def __init__(
        self,
        *,
        source_adapter: Any,
        projection_repository: Any,
        retention_cutoff_date_provider: Any | None = None,
        attachment_invoice_promoter: Any | None = None,
        payment_status_repository: Any | None = None,
        pending_payment_source_snapshot_repository: Any | None = None,
    ) -> None:
        if payment_status_repository is not None and pending_payment_source_snapshot_repository is None:
            raise ValueError(
                "payment_status_repository requires pending_payment_source_snapshot_repository."
            )
        self._source_adapter = source_adapter
        self._projection_repository = projection_repository
        self._retention_cutoff_date_provider = retention_cutoff_date_provider
        self._attachment_invoice_promoter = attachment_invoice_promoter
        self._payment_status_repository = payment_status_repository
        self._pending_payment_source_snapshot_repository = pending_payment_source_snapshot_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.payload.get("operation") == REFRESH_ATTACHMENTS_OPERATION:
            try:
                return self._run_targeted_attachment_refresh(event)
            except Exception as exc:
                self._record_failed_sync_run(
                    scope_key="targeted",
                    error=exc,
                    sync_type="oa_attachment_refresh",
                )
                raise
        scope_key = self._event_scope_key(event)
        try:
            return self._run_sync(scope_key)
        except Exception as exc:
            self._record_failed_sync_run(scope_key=scope_key, error=exc)
            raise

    def _run_targeted_attachment_refresh(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        row_ids = _targeted_refresh_row_ids(event.payload.get("row_ids"))
        expected_scope_keys = _targeted_refresh_scope_keys(
            event.payload.get("affected_scope_keys")
        )
        refresh = getattr(self._source_adapter, "refresh_application_record_attachments", None)
        if not callable(refresh):
            raise RuntimeError(
                "OA sync source adapter must expose refresh_application_record_attachments()."
            )
        commit_targeted = getattr(
            self._pending_payment_source_snapshot_repository,
            "commit_targeted_attachment_refresh",
            None,
        )
        if not callable(commit_targeted):
            raise RuntimeError(
                "OA attachment refresh requires atomic targeted owner writes."
            )
        promote_records = getattr(self._attachment_invoice_promoter, "promote_records", None)
        if not callable(promote_records):
            raise RuntimeError("OA attachment refresh requires the attachment invoice promoter.")
        refreshed_records = list(refresh(row_ids))
        if any(not isinstance(record, OAApplicationRecord) for record in refreshed_records):
            raise RuntimeError("OA attachment refresh source returned an invalid record.")
        records_by_id = {record.id: record for record in refreshed_records}
        if len(records_by_id) != len(refreshed_records):
            raise RuntimeError("OA attachment refresh source returned duplicate row_ids.")
        missing_row_ids = [row_id for row_id in row_ids if row_id not in records_by_id]
        if missing_row_ids:
            raise RuntimeError(
                f"OA attachment refresh source did not return row_ids: {', '.join(missing_row_ids)}"
            )
        unexpected_row_ids = sorted(set(records_by_id) - set(row_ids))
        if unexpected_row_ids:
            raise RuntimeError(
                f"OA attachment refresh source returned unrequested row_ids: {', '.join(unexpected_row_ids)}"
            )
        selected_records = [records_by_id[row_id] for row_id in row_ids]
        unsupported_row_ids = [
            record.id
            for record in selected_records
            if not _is_completed_workflow(record)
            and not is_in_progress_expense_claim(record)
        ]
        if unsupported_row_ids:
            raise RuntimeError(
                "OA attachment refresh supports completed workflows and in-progress expense claims only: "
                + ", ".join(unsupported_row_ids)
            )
        failed_parse_row_ids = _targeted_attachment_failure_row_ids(selected_records)
        if failed_parse_row_ids:
            raise RuntimeError(
                "OA attachment refresh failed to download or parse attachments for row_ids: "
                + ", ".join(failed_parse_row_ids)
            )
        records_by_scope: dict[str, list[OAApplicationRecord]] = {}
        for record in selected_records:
            scope_key = str(record.month or "").strip()
            if not self._is_month_scope(scope_key):
                raise RuntimeError(f"OA attachment refresh row {record.id} has an invalid month.")
            records_by_scope.setdefault(scope_key, []).append(record)
        affected_scope_keys = sorted(records_by_scope)
        if affected_scope_keys != expected_scope_keys:
            raise RuntimeError(
                "OA attachment refresh source scopes changed after enqueue."
            )
        owner_write = commit_targeted(records=selected_records)
        upserted_completed_count = getattr(owner_write, "upserted_completed_count", None)
        upserted_pending_count = getattr(owner_write, "upserted_pending_count", None)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (upserted_completed_count, upserted_pending_count)
        ):
            raise RuntimeError("OA attachment refresh owner writer returned an invalid result.")
        upserted_count = upserted_completed_count + upserted_pending_count
        promotion = promote_records(
            selected_records,
            ensure_matching=True,
        )
        if not isinstance(promotion, dict):
            raise RuntimeError("OA attachment invoice promoter returned an invalid result.")
        promotion_summary = dict(promotion.get("summary") or {})
        result = {
            "sync_type": "oa_attachment_refresh",
            "operation": REFRESH_ATTACHMENTS_OPERATION,
            "status": "succeeded",
            "row_ids": row_ids,
            "rows": [_attachment_summary(record) for record in selected_records],
            "errors": [],
            "promotion_summary": promotion_summary,
            "affected_scope_keys": affected_scope_keys,
            "upserted_count": upserted_count,
            "removed_stale_completed_count": 0,
            "removed_non_completed_count": 0,
        }
        record_sync_run = getattr(self._projection_repository, "record_sync_run", None)
        if callable(record_sync_run):
            record_sync_run(
                {
                    "sync_type": "oa_attachment_refresh",
                    "scope_key": ",".join(affected_scope_keys),
                    "status": "succeeded",
                    "scanned_count": len(selected_records),
                    "upserted_count": upserted_count,
                    "skipped_count": max(0, len(selected_records) - upserted_count),
                    "error_count": 0,
                }
            )
        return result

    def _run_sync(self, scope_key: str) -> dict[str, Any]:
        cutoff_month = self._retention_cutoff_month()
        source_batch = self._load_source_batch(scope_key, cutoff_month=cutoff_month)
        projection_records = self._sanitized_records(list(source_batch["projection_records"]))
        admission_records = self._sanitized_records(list(source_batch["admission_records"]))
        payment_statuses = self._load_payment_statuses()
        completed_records = [record for record in projection_records if _is_completed_workflow(record)]
        if self._payment_status_repository is not None:
            if self._pending_payment_source_snapshot_repository is None:
                raise RuntimeError(
                    "OA payment snapshot sync requires pending_payment_source_snapshot_repository."
                )
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
        attachment_invoice_records = completed_records
        if source_snapshot_result is not None:
            completed_changed_scopes = set(
                getattr(source_snapshot_result, "completed_projection_changed_scopes", ())
            )
            pending_admission_changed_scopes = set(
                getattr(source_snapshot_result, "pending_admission_changed_scopes", ())
            )
            attachment_invoice_records = [
                record
                for record in completed_records
                if "all" in completed_changed_scopes
                or str(record.month) in completed_changed_scopes
            ]
            attachment_invoice_records.extend(
                record
                for record in admission_records
                if is_in_progress_expense_claim(record)
                and (
                    "all" in pending_admission_changed_scopes
                    or str(record.month) in pending_admission_changed_scopes
                )
            )
        elif upserted_count == 0:
            attachment_invoice_records = []
        attachment_invoice_promotion_result = self._promote_attachment_invoices(
            attachment_invoice_records
        )
        attachment_invoice_summary = dict(attachment_invoice_promotion_result.get("summary") or {})
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
            "scanned_oa_attachment_invoice_candidate_count": int(
                attachment_invoice_summary.get("cache_candidate_count") or 0
            ),
            "promoted_oa_attachment_invoice_count": int(
                attachment_invoice_summary.get("affected_invoice_count") or 0
            ),
            "linked_existing_oa_attachment_invoice_count": int(
                attachment_invoice_summary.get("linked_existing_invoice_count") or 0
            ),
            "created_oa_attachment_invoice_count": int(
                attachment_invoice_summary.get("created_invoice_count") or 0
            ),
            "error_count": 0,
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
            "pending_admission_changed_scope_keys": (
                list(getattr(source_snapshot_result, "pending_admission_changed_scopes", ()))
                if source_snapshot_result is not None
                else []
            ),
        }
        record_sync_run = getattr(self._projection_repository, "record_sync_run", None)
        if callable(record_sync_run):
            record_sync_run(result)
        return result

    def _promote_attachment_invoices(
        self,
        records: list[OAApplicationRecord],
    ) -> dict[str, Any]:
        if self._attachment_invoice_promoter is None or not records:
            return {"summary": {}}
        return dict(self._attachment_invoice_promoter.promote_records(records) or {})

    def _record_failed_sync_run(
        self,
        *,
        scope_key: str,
        error: Exception,
        sync_type: str = "oa_projection",
    ) -> None:
        record_sync_run = getattr(self._projection_repository, "record_sync_run", None)
        if not callable(record_sync_run):
            return
        try:
            record_sync_run(
                {
                    "sync_type": sync_type,
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


def _targeted_refresh_row_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("OA attachment refresh payload.row_ids must be an array.")
    if any(not isinstance(item, str) for item in value):
        raise ValueError("OA attachment refresh payload.row_ids must contain strings only.")
    row_ids = list(dict.fromkeys(row_id for item in value if (row_id := item.strip())))
    if not row_ids:
        raise ValueError("OA attachment refresh payload.row_ids must not be empty.")
    return row_ids


def _targeted_refresh_scope_keys(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("OA attachment refresh payload.affected_scope_keys must be an array.")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(
            "OA attachment refresh payload.affected_scope_keys must contain strings only."
        )
    scope_keys = sorted(
        dict.fromkeys(scope_key for item in value if (scope_key := item.strip()))
    )
    if not scope_keys or any(not OAProjectionSyncService._is_month_scope(key) for key in scope_keys):
        raise ValueError(
            "OA attachment refresh payload.affected_scope_keys must contain valid months."
        )
    return scope_keys


def _targeted_attachment_failure_row_ids(
    records: list[OAApplicationRecord],
) -> list[str]:
    failed_row_ids: list[str] = []
    for record in records:
        artifacts = list(record.attachment_artifacts or [])
        artifacts.extend(
            artifact
            for item in list(record.expense_items or [])
            if isinstance(item, dict)
            for artifact in list(item.get("attachment_artifacts") or [])
        )
        if any(
            isinstance(artifact, dict)
            and str(artifact.get("parse_status") or "").strip().lower()
            in TARGETED_ATTACHMENT_FAILURE_STATUSES
            for artifact in artifacts
        ):
            failed_row_ids.append(record.id)
    return failed_row_ids


def _attachment_summary(record: OAApplicationRecord) -> dict[str, object]:
    attachment_file_count = max(
        int(record.attachment_file_count or 0),
        len(record.attachment_artifacts),
        len(record.attachment_invoices),
    )
    importable_invoice_count = len(
        [invoice for invoice in record.attachment_invoices if isinstance(invoice, dict)]
    )
    return {
        "row_id": record.id,
        "attachment_file_count": attachment_file_count,
        "importable_invoice_count": importable_invoice_count,
        "unrecognized_attachment_count": max(
            0,
            attachment_file_count - importable_invoice_count,
        ),
    }
