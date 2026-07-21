from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
from http import HTTPStatus
import json
from threading import RLock
from typing import Any, Callable, Protocol
from uuid import uuid4

from fin_ops_platform.services.etc_service import EtcOAFormFieldMapping
from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageError,
    TARGET_APPLICANTS,
)
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.read_model_write_targets import write_target_envelope
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
DEFAULT_OA_FORM_ID = 2


class InputInvoiceUsageOaReverseStatus(str, Enum):
    DRAFT = "draft"
    OA_DRAFT_CREATED = "oa_draft_created"
    OA_DRAFT_FAILED = "oa_draft_failed"
    SUBMITTED_CONFIRMED = "submitted_confirmed"
    OA_SUBMISSION_DETECTING = "oa_submission_detecting"
    OA_DETECTED = "oa_detected"
    OA_DETECTION_MISSING = "oa_detection_missing"
    OA_DETECTION_CONFLICT = "oa_detection_conflict"
    OA_DETECTION_UNAVAILABLE = "oa_detection_unavailable"
    NOT_SUBMITTED = "not_submitted"
    MANUALLY_MARKED_SUBMITTED = "manually_marked_submitted"
    MANUALLY_MARKED_NOT_SUBMITTED = "manually_marked_not_submitted"


DETECTION_STATUSES = {
    InputInvoiceUsageOaReverseStatus.OA_SUBMISSION_DETECTING.value,
    InputInvoiceUsageOaReverseStatus.OA_DETECTION_MISSING.value,
    InputInvoiceUsageOaReverseStatus.OA_DETECTION_CONFLICT.value,
    InputInvoiceUsageOaReverseStatus.OA_DETECTION_UNAVAILABLE.value,
}

SUBMISSION_CONFIRMABLE_STATUSES = {
    InputInvoiceUsageOaReverseStatus.OA_DRAFT_CREATED.value,
}

MANUAL_FALLBACK_STATUSES = {
    InputInvoiceUsageOaReverseStatus.OA_DETECTION_MISSING.value,
    InputInvoiceUsageOaReverseStatus.OA_DETECTION_CONFLICT.value,
    InputInvoiceUsageOaReverseStatus.OA_DETECTION_UNAVAILABLE.value,
}


class InputInvoiceUsageOaReverseServiceError(RuntimeError):
    code = "input_invoice_usage_oa_reverse_error"


class InputInvoiceUsageOaReverseNotFoundError(InputInvoiceUsageOaReverseServiceError):
    code = "oa_reverse_batch_not_found"


class InputInvoiceUsageOaReverseStalePreviewError(InputInvoiceUsageOaReverseServiceError):
    code = "stale_oa_reverse_preview"


class InputInvoiceUsageOaReverseVersionConflictError(InputInvoiceUsageOaReverseServiceError):
    code = "oa_reverse_version_conflict"

    def __init__(self, batch_id: str, expected_version: int, actual_version: int) -> None:
        self.batch_id = batch_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__("Input invoice usage OA reverse batch version conflict.")


class InputInvoiceUsageOaReverseInvalidTransitionError(InputInvoiceUsageOaReverseServiceError):
    code = "oa_reverse_invalid_transition"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        if code:
            self.code = code
        super().__init__(message)


class InputInvoiceUsageOaReversePermissionError(InputInvoiceUsageOaReverseServiceError):
    code = "oa_reverse_permission_denied"


class InputInvoiceUsageOaReverseMissingClientError(InputInvoiceUsageOaReverseServiceError):
    code = "oa_reverse_missing_oa_client"


class InputInvoiceUsageOaDraftClient(Protocol):
    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        raise NotImplementedError


class InputInvoiceUsageOaDraftClientProvider(Protocol):
    def draft_client_for(self, target_applicant_code: str) -> InputInvoiceUsageOaDraftClient:
        raise NotImplementedError


class NotConfiguredInputInvoiceUsageOaDraftClient:
    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        raise InputInvoiceUsageOaReverseMissingClientError("Input invoice usage OA draft client is not configured.")


@dataclass(frozen=True, slots=True)
class InputInvoiceUsageOaEvidence:
    oa_row_id: str
    process_status: str = "in_progress"
    candidates: list[dict[str, object]] = field(default_factory=list)
    raw_payload: dict[str, object] = field(default_factory=dict)


class InputInvoiceUsageOaEvidenceProvider(Protocol):
    def find_oa_draft_evidence(self, batch: "InputInvoiceUsageOaReverseBatch") -> InputInvoiceUsageOaEvidence | None:
        raise NotImplementedError


class OAProjectionInputInvoiceUsageOaEvidenceProvider:
    def __init__(self, oa_projection: Any | None) -> None:
        self._oa_projection = oa_projection

    def find_oa_draft_evidence(self, batch: "InputInvoiceUsageOaReverseBatch") -> InputInvoiceUsageOaEvidence | None:
        if self._oa_projection is None:
            return None
        list_all = getattr(self._oa_projection, "list_all_application_records", None)
        if not callable(list_all):
            return None
        needles = [
            str(value).strip()
            for value in (batch.oa_draft_id, batch.batch_id)
            if str(value or "").strip()
        ]
        if not needles:
            return None
        candidates: list[dict[str, object]] = []
        for record in list(list_all() or []):
            if not isinstance(record, OAApplicationRecord):
                continue
            payload = _oa_record_payload(record)
            evidence_text = json.dumps(_serialize_value(payload), ensure_ascii=False, sort_keys=True)
            if any(needle in evidence_text for needle in needles):
                candidates.append(payload)
        if len(candidates) != 1:
            return None
        selected = candidates[0]
        return InputInvoiceUsageOaEvidence(
            oa_row_id=str(selected.get("id") or ""),
            process_status=str(selected.get("section") or selected.get("relationCode") or "in_progress"),
            candidates=candidates,
            raw_payload=selected,
        )


class WorkbenchInputInvoiceUsageOaReverseRelationWriter:
    relation_mode = "input_invoice_oa_reverse"

    def __init__(self, relation_command_service: Any) -> None:
        self._relation_command_service = relation_command_service

    def __call__(self, batch: "InputInvoiceUsageOaReverseBatch", evidence: InputInvoiceUsageOaEvidence) -> None:
        oa_row_id = str(evidence.oa_row_id or "").strip()
        invoice_ids = [
            str(invoice_id).strip()
            for invoice_id in list(batch.invoice_ids or [])
            if str(invoice_id).strip()
        ]
        if not oa_row_id or not invoice_ids:
            return
        row_ids = [oa_row_id, *invoice_ids]
        case_id = f"case_input_invoice_usage_oa_reverse_{batch.batch_id}"
        confirm_relation = getattr(self._relation_command_service, "confirm_relation", None)
        if not callable(confirm_relation):
            raise WorkbenchRelationCommandError(
                "workbench_relation_command_unavailable",
                "Workbench relation command service does not expose confirm_relation.",
                payload={
                    "batch_id": batch.batch_id,
                    "oa_row_id": oa_row_id,
                    "invoice_ids": invoice_ids,
                },
            )
        confirm_relation(
            case_id=case_id,
            row_ids=row_ids,
            row_types=["oa", *(["invoice"] * len(invoice_ids))],
            relation_mode=self.relation_mode,
            actor_id=str(batch.updated_by or batch.created_by or "input_invoice_usage_oa_reverse"),
            month_scope=_batch_month_scope(batch),
            special_metadata={
                "input_invoice_usage_oa_reverse_batch_id": batch.batch_id,
                "oa_draft_id": batch.oa_draft_id,
                "oa_row_id": oa_row_id,
                "invoice_ids": invoice_ids,
            },
            evidence={
                "oa_process_status": evidence.process_status,
                "candidate_count": len(list(evidence.candidates or [])),
                "raw_payload": dict(evidence.raw_payload or {}),
            },
            idempotency_key=f"input_invoice_oa_reverse:{batch.batch_id}:{oa_row_id}",
            history_operation_type="input_invoice_oa_reverse_confirm",
        )


@dataclass(slots=True)
class InputInvoiceUsageOaReverseBatch:
    batch_id: str
    status: str
    version: int
    target_applicant_code: str
    target_applicant_name: str
    invoice_ids: list[str]
    preview_id: str
    preview_hash: str
    preview_summary: dict[str, object]
    invoice_display_rows: list[dict[str, object]]
    idempotency_key: str | None = None
    operation_idempotency: dict[str, str] = field(default_factory=dict)
    oa_form_id: int = DEFAULT_OA_FORM_ID
    oa_draft_id: str | None = None
    oa_draft_url: str | None = None
    oa_row_id: str | None = None
    oa_process_status: str = "unknown"
    oa_detection_status: str = "not_started"
    oa_detection_attempts: int = 0
    oa_detection_reason: str | None = None
    oa_detection_error: str | None = None
    oa_detection_payload: dict[str, object] = field(default_factory=dict)
    created_by: str | None = None
    updated_by: str | None = None
    audit_events: list[dict[str, object]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InputInvoiceUsageOaReverseBatchRepository(Protocol):
    def get_batch(self, batch_id: str) -> InputInvoiceUsageOaReverseBatch | None:
        raise NotImplementedError

    def find_batch_by_create_idempotency_key(self, idempotency_key: str) -> InputInvoiceUsageOaReverseBatch | None:
        raise NotImplementedError

    def list_batches_by_status(self, statuses: list[str], *, limit: int = 50) -> list[InputInvoiceUsageOaReverseBatch]:
        raise NotImplementedError

    def save_batch(self, batch: InputInvoiceUsageOaReverseBatch) -> None:
        raise NotImplementedError


class InMemoryInputInvoiceUsageOaReverseBatchRepository:
    def __init__(self, batches: list[InputInvoiceUsageOaReverseBatch] | None = None) -> None:
        self._batches = {batch.batch_id: _copy_batch(batch) for batch in list(batches or [])}
        self._lock = RLock()

    def get_batch(self, batch_id: str) -> InputInvoiceUsageOaReverseBatch | None:
        with self._lock:
            batch = self._batches.get(str(batch_id or "").strip())
            return _copy_batch(batch) if batch is not None else None

    def find_batch_by_create_idempotency_key(self, idempotency_key: str) -> InputInvoiceUsageOaReverseBatch | None:
        normalized = str(idempotency_key or "").strip()
        if not normalized:
            return None
        with self._lock:
            for batch in self._batches.values():
                if batch.idempotency_key == normalized:
                    return _copy_batch(batch)
        return None

    def list_batches_by_status(self, statuses: list[str], *, limit: int = 50) -> list[InputInvoiceUsageOaReverseBatch]:
        wanted = {str(status or "").strip() for status in list(statuses or []) if str(status or "").strip()}
        if not wanted:
            return []
        with self._lock:
            batches = [
                _copy_batch(batch)
                for batch in self._batches.values()
                if str(batch.status or "").strip() in wanted
            ]
        batches.sort(key=lambda batch: batch.updated_at, reverse=True)
        return batches[: max(int(limit or 50), 1)]

    def save_batch(self, batch: InputInvoiceUsageOaReverseBatch) -> None:
        with self._lock:
            self._batches[batch.batch_id] = _copy_batch(batch)


class InputInvoiceUsageOaReverseService:
    def __init__(
        self,
        *,
        repository: InputInvoiceUsageOaReverseBatchRepository,
        oa_client: InputInvoiceUsageOaDraftClient | None = None,
        evidence_provider: InputInvoiceUsageOaEvidenceProvider | None = None,
        relation_writer: Callable[[InputInvoiceUsageOaReverseBatch, InputInvoiceUsageOaEvidence], None] | None = None,
        audit_recorder: Callable[[dict[str, object]], None] | None = None,
        read_model_invalidator: Callable[[list[str], str], None] | None = None,
        statistics_invalidator: Callable[[str], None] | None = None,
        read_model_rows_loader: Callable[[dict[str, list[Any]]], dict[str, object] | None] | None = None,
        read_model_rows_by_invoice_ids_loader: Callable[[list[str]], dict[str, object] | None] | None = None,
    ) -> None:
        self._repository = repository
        self._oa_client = oa_client or NotConfiguredInputInvoiceUsageOaDraftClient()
        self._evidence_provider = evidence_provider
        self._relation_writer = relation_writer
        self._audit_recorder = audit_recorder
        self._read_model_invalidator = read_model_invalidator
        self._statistics_invalidator = statistics_invalidator
        self._read_model_rows_loader = read_model_rows_loader
        self._read_model_rows_by_invoice_ids_loader = read_model_rows_by_invoice_ids_loader

    def preview(self, request: dict[str, Any] | None, *, can_create_draft: bool = False) -> dict[str, object]:
        payload = dict(request or {})
        target_code, target_name = self._resolve_target_applicant(payload.get("targetApplicantCode"))
        rows, missing_ids = self._rows_for_preview_payload(payload)

        candidate_rows: list[dict[str, object]] = []
        rejected: list[dict[str, object]] = []
        for invoice_id in missing_ids:
            rejected.append({"invoiceId": invoice_id, "reasonCode": "invoice_not_found", "reason": "发票不存在"})
        for row in rows:
            rejection = self._candidate_rejection(row)
            if rejection is not None:
                rejected.append({**self._invoice_display_row(row), **rejection})
                continue
            candidate_rows.append(row)

        display_rows = [self._invoice_display_row(row) for row in candidate_rows]
        total = sum((_decimal(row.get("totalWithTax")) for row in display_rows), start=ZERO)
        candidate_ids = [str(row["invoiceId"]) for row in display_rows]
        source = str(payload.get("source") or ("explicitSelection" if payload.get("invoiceIds") else "currentFilters")).strip()
        fingerprint = {
            "candidateInvoiceIds": candidate_ids,
            "targetApplicantCode": target_code,
            "totalWithTax": _money(total),
            "invoiceRows": display_rows,
        }
        preview_hash = _stable_hash(fingerprint)
        preview_id = f"oa_reverse_preview_{preview_hash[:16]}"
        can_submit = bool(can_create_draft and candidate_ids)
        return {
            "previewId": preview_id,
            "previewHash": preview_hash,
            "source": source,
            "targetApplicantCode": target_code,
            "targetApplicantName": target_name,
            "targetApplicants": self._target_applicant_options(),
            "invoiceCount": len(candidate_ids),
            "totalWithTax": _money(total),
            "invoiceRows": display_rows,
            "rejectedInvoices": rejected,
            "groups": [
                {
                    "targetApplicantCode": target_code,
                    "targetApplicantName": target_name,
                    "invoiceCount": len(candidate_ids),
                    "totalWithTax": _money(total),
                    "candidateInvoiceIds": candidate_ids,
                    "invoiceRows": display_rows,
                    "rejectedInvoices": rejected,
                }
            ],
            "warnings": [],
            "canCreateDraft": can_submit,
            "nextAction": "create_batch" if can_submit else "no_valid_candidates",
        }

    def create_batch(
        self,
        request: dict[str, Any],
        *,
        actor_id: str,
        can_mutate: bool,
    ) -> dict[str, object]:
        self._assert_mutation_permission(can_mutate)
        idempotency_key = _required_text(request.get("idempotencyKey"), "idempotencyKey")
        existing = self._repository.find_batch_by_create_idempotency_key(idempotency_key)
        if existing is not None:
            return self.batch_payload(existing)

        expected_hash = _required_text(request.get("expectedPreviewHash"), "expectedPreviewHash")
        preview_request = dict(request.get("previewRequest") if isinstance(request.get("previewRequest"), dict) else {})
        selected_ids = _text_list(request.get("selectedInvoiceIds") or request.get("invoiceIds"))
        if selected_ids:
            preview_request["invoiceIds"] = selected_ids
            preview_request["source"] = "explicitSelection"
        if request.get("targetApplicantCode") is not None:
            preview_request["targetApplicantCode"] = request.get("targetApplicantCode")
        preview_payload = self.preview(preview_request, can_create_draft=True)
        if str(preview_payload["previewHash"]) != expected_hash:
            raise InputInvoiceUsageOaReverseStalePreviewError("OA reverse preview is stale. Refresh preview before creating a batch.")
        invoice_rows = list(preview_payload.get("invoiceRows") or [])
        invoice_ids = [str(row.get("invoiceId") or "") for row in invoice_rows if str(row.get("invoiceId") or "").strip()]
        if not invoice_ids:
            raise InputInvoiceUsageOaReverseInvalidTransitionError("OA reverse batch requires at least one candidate invoice.", code="empty_oa_reverse_batch")

        now = datetime.now(UTC)
        batch = InputInvoiceUsageOaReverseBatch(
            batch_id=f"input_invoice_usage_oa_reverse_batch_{uuid4().hex[:16]}",
            status=InputInvoiceUsageOaReverseStatus.DRAFT.value,
            version=1,
            target_applicant_code=str(preview_payload["targetApplicantCode"]),
            target_applicant_name=str(preview_payload["targetApplicantName"]),
            invoice_ids=invoice_ids,
            preview_id=str(preview_payload["previewId"]),
            preview_hash=str(preview_payload["previewHash"]),
            preview_summary={
                "invoiceCount": len(invoice_ids),
                "totalWithTax": str(preview_payload["totalWithTax"]),
                "source": str(preview_payload["source"]),
            },
            invoice_display_rows=[dict(row) for row in invoice_rows if isinstance(row, dict)],
            idempotency_key=idempotency_key,
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        self._append_audit(batch, "oa_reverse_batch_created", actor_id=actor_id, before_status=None, after_status=batch.status)
        self._repository.save_batch(batch)
        self._invalidate_statistics("input_invoice_usage_oa_reverse_batch_created")
        self._record_external_audit(batch, "oa_reverse_batch_created", actor_id=actor_id)
        return self.batch_payload(batch)

    def create_oa_draft_from_selection(
        self,
        request: dict[str, Any],
        *,
        actor_id: str,
        can_mutate: bool,
        oa_client_provider: InputInvoiceUsageOaDraftClientProvider,
    ) -> dict[str, object]:
        self._assert_mutation_permission(can_mutate)
        idempotency_key = _required_text(request.get("idempotencyKey"), "idempotencyKey")
        expected_hash = _required_text(request.get("expectedPreviewHash"), "expectedPreviewHash")
        preview_request = dict(request.get("previewRequest") if isinstance(request.get("previewRequest"), dict) else {})
        selected_ids = _text_list(request.get("selectedInvoiceIds") or request.get("invoiceIds"))
        if selected_ids:
            preview_request["invoiceIds"] = selected_ids
            preview_request["source"] = "explicitSelection"
        if request.get("targetApplicantCode") is not None:
            preview_request["targetApplicantCode"] = request.get("targetApplicantCode")
        preview_payload = self.preview(preview_request, can_create_draft=True)
        if str(preview_payload.get("previewHash") or "") != expected_hash:
            raise InputInvoiceUsageOaReverseStalePreviewError("OA reverse preview is stale. Refresh preview before creating an OA draft.")
        if not list(preview_payload.get("invoiceRows") or []):
            raise InputInvoiceUsageOaReverseInvalidTransitionError("OA reverse draft requires at least one candidate invoice.", code="empty_oa_reverse_batch")
        target_applicant_code = str(preview_payload.get("targetApplicantCode") or "").strip()
        try:
            client = oa_client_provider.draft_client_for(target_applicant_code)
        except InputInvoiceUsageOaReverseServiceError:
            raise
        except Exception as exc:
            raise InputInvoiceUsageOaReverseMissingClientError("目标 OA 申请人凭据未配置或登录失败。") from exc

        batch_payload = self.create_batch(
            {
                **request,
                "previewRequest": preview_request,
                "invoiceIds": selected_ids,
                "targetApplicantCode": target_applicant_code,
                "expectedPreviewHash": expected_hash,
                "idempotencyKey": f"{idempotency_key}:batch",
            },
            actor_id=actor_id,
            can_mutate=can_mutate,
        )
        return self.create_oa_draft(
            str(batch_payload["batchId"]),
            expected_version=int(batch_payload["version"]),
            idempotency_key=f"{idempotency_key}:draft",
            actor_id=actor_id,
            can_mutate=can_mutate,
            oa_client=client,
        )

    def get_batch(self, batch_id: str) -> dict[str, object]:
        return self.batch_payload(self._get_batch(batch_id))

    def submitted_history(self, *, limit: int = 50) -> dict[str, object]:
        batches = self._repository.list_batches_by_status(
            [
                InputInvoiceUsageOaReverseStatus.SUBMITTED_CONFIRMED.value,
                InputInvoiceUsageOaReverseStatus.MANUALLY_MARKED_SUBMITTED.value,
            ],
            limit=limit,
        )
        return {"items": [self._submitted_history_item(batch) for batch in batches]}

    def staged_drafts(self, *, limit: int = 50) -> dict[str, object]:
        batches = self._repository.list_batches_by_status(
            [InputInvoiceUsageOaReverseStatus.OA_DRAFT_CREATED.value],
            limit=limit,
        )
        return {"items": [self.batch_payload(batch) for batch in batches]}

    def create_oa_draft(
        self,
        batch_id: str,
        *,
        expected_version: int | None,
        idempotency_key: str,
        actor_id: str,
        can_mutate: bool,
        oa_client: InputInvoiceUsageOaDraftClient | None = None,
    ) -> dict[str, object]:
        self._assert_mutation_permission(can_mutate)
        normalized_key = _required_text(idempotency_key, "idempotencyKey")
        batch = self._get_batch(batch_id)
        if self._is_operation_replay(batch, "create_oa_draft", normalized_key):
            return self.batch_payload(batch)
        self._assert_version(batch, expected_version)
        if batch.status not in {
            InputInvoiceUsageOaReverseStatus.DRAFT.value,
            InputInvoiceUsageOaReverseStatus.OA_DRAFT_FAILED.value,
            InputInvoiceUsageOaReverseStatus.NOT_SUBMITTED.value,
            InputInvoiceUsageOaReverseStatus.MANUALLY_MARKED_NOT_SUBMITTED.value,
        }:
            raise InputInvoiceUsageOaReverseInvalidTransitionError("current status does not allow creating an OA draft.")

        before_status = batch.status
        draft_payload = self._build_oa_draft_payload(batch)
        client = oa_client or self._oa_client
        try:
            oa_draft_id, oa_draft_url = client.create_form_draft(form_id=batch.oa_form_id, payload=draft_payload)
        except InputInvoiceUsageOaReverseMissingClientError as exc:
            self._mark_draft_failed(batch, actor_id=actor_id, before_status=before_status, reason=str(exc))
            raise
        except Exception as exc:
            self._mark_draft_failed(batch, actor_id=actor_id, before_status=before_status, reason=str(exc))
            raise InputInvoiceUsageOaReverseInvalidTransitionError(str(exc), code="oa_reverse_draft_request_failed") from exc

        batch.oa_draft_id = str(oa_draft_id or "").strip() or None
        batch.oa_draft_url = str(oa_draft_url or "").strip() or None
        if batch.oa_draft_id is None:
            self._mark_draft_failed(batch, actor_id=actor_id, before_status=before_status, reason="OA draft response did not include draft id.")
            raise InputInvoiceUsageOaReverseInvalidTransitionError("OA draft response did not include draft id.", code="oa_reverse_draft_response_invalid")
        batch.status = InputInvoiceUsageOaReverseStatus.OA_DRAFT_CREATED.value
        batch.oa_detection_status = "draft_created"
        batch.oa_detection_reason = None
        batch.oa_detection_error = None
        batch.operation_idempotency["create_oa_draft"] = normalized_key
        self._bump_version(batch, actor_id=actor_id, event_type="oa_reverse_draft_created", before_status=before_status, after_status=batch.status)
        self._repository.save_batch(batch)
        self._record_external_audit(batch, "oa_reverse_draft_created", actor_id=actor_id)
        return self.batch_payload(batch)

    def revoke_oa_draft(
        self,
        batch_id: str,
        *,
        reason: str,
        expected_version: int | None,
        idempotency_key: str,
        actor_id: str,
        can_mutate: bool,
    ) -> dict[str, object]:
        self._assert_mutation_permission(can_mutate)
        normalized_reason = _required_text(reason, "reason")
        normalized_key = _required_text(idempotency_key, "idempotencyKey")
        batch = self._get_batch(batch_id)
        if self._is_operation_replay(batch, "revoke_oa_draft", normalized_key):
            return self.batch_payload(batch)
        self._assert_version(batch, expected_version)
        if batch.status == InputInvoiceUsageOaReverseStatus.NOT_SUBMITTED.value and not batch.oa_draft_id:
            return self.batch_payload(batch)
        if batch.status not in DETECTION_STATUSES | SUBMISSION_CONFIRMABLE_STATUSES | {
            InputInvoiceUsageOaReverseStatus.OA_DRAFT_FAILED.value,
            InputInvoiceUsageOaReverseStatus.NOT_SUBMITTED.value,
            InputInvoiceUsageOaReverseStatus.MANUALLY_MARKED_NOT_SUBMITTED.value,
        }:
            raise InputInvoiceUsageOaReverseInvalidTransitionError("current status does not allow revoking the OA draft.")
        before_status = batch.status
        revoked_payload = {
            "revokedOaDraftId": batch.oa_draft_id,
            "revokedOaDraftUrl": batch.oa_draft_url,
            "reason": normalized_reason,
        }
        batch.oa_draft_id = None
        batch.oa_draft_url = None
        batch.oa_detection_status = "revoked"
        batch.oa_detection_reason = "user_revoked"
        batch.oa_detection_payload = {**dict(batch.oa_detection_payload or {}), **revoked_payload}
        batch.status = InputInvoiceUsageOaReverseStatus.NOT_SUBMITTED.value
        batch.operation_idempotency["revoke_oa_draft"] = normalized_key
        self._bump_version(batch, actor_id=actor_id, event_type="oa_reverse_draft_revoked", before_status=before_status, after_status=batch.status, reason=normalized_reason)
        self._repository.save_batch(batch)
        self._record_external_audit(batch, "oa_reverse_draft_revoked", actor_id=actor_id)
        return self.batch_payload(batch)

    def refresh_oa_status(
        self,
        batch_id: str,
        *,
        actor_id: str,
        can_mutate: bool,
        expected_version: int | None = None,
    ) -> dict[str, object]:
        self._assert_mutation_permission(can_mutate)
        batch = self._get_batch(batch_id)
        self._assert_version(batch, expected_version)
        if batch.status not in DETECTION_STATUSES:
            raise InputInvoiceUsageOaReverseInvalidTransitionError("current status does not allow OA status refresh.")
        before_status = batch.status
        evidence = self._evidence_provider.find_oa_draft_evidence(batch) if self._evidence_provider is not None else None
        batch.oa_detection_attempts += 1
        if evidence is None:
            batch.status = InputInvoiceUsageOaReverseStatus.OA_DETECTION_MISSING.value
            batch.oa_detection_status = "missing"
            batch.oa_detection_reason = "oa_projection_evidence_missing"
            self._bump_version(batch, actor_id=actor_id, event_type="oa_reverse_status_refreshed", before_status=before_status, after_status=batch.status, reason=batch.oa_detection_reason)
            self._repository.save_batch(batch)
            self._record_external_audit(batch, "oa_reverse_status_refreshed", actor_id=actor_id)
            return self.batch_payload(batch)

        batch.status = InputInvoiceUsageOaReverseStatus.OA_DETECTED.value
        batch.oa_row_id = evidence.oa_row_id
        batch.oa_process_status = evidence.process_status or "in_progress"
        batch.oa_detection_status = "detected"
        batch.oa_detection_reason = "oa_projection_evidence_detected"
        batch.oa_detection_payload = {
            "oaRowId": evidence.oa_row_id,
            "processStatus": evidence.process_status,
            "candidates": list(evidence.candidates or [])[:10],
            "raw": dict(evidence.raw_payload or {}),
        }
        if self._relation_writer is not None:
            self._relation_writer(batch, evidence)
        self._bump_version(batch, actor_id=actor_id, event_type="oa_reverse_status_detected", before_status=before_status, after_status=batch.status, reason=batch.oa_detection_reason)
        self._repository.save_batch(batch)
        self._record_external_audit(batch, "oa_reverse_status_detected", actor_id=actor_id)
        self._invalidate_read_models(batch, "input_invoice_usage_oa_reverse_evidence_detected")
        return self.batch_payload(batch, include_write_targets=True)

    def manual_oa_status(
        self,
        batch_id: str,
        *,
        decision: str,
        reason: str,
        expected_version: int | None,
        idempotency_key: str,
        actor_id: str,
        can_mutate: bool,
        candidate_oa_row_id: str | None = None,
    ) -> dict[str, object]:
        self._assert_mutation_permission(can_mutate)
        normalized_key = _required_text(idempotency_key, "idempotencyKey")
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"submitted", "not_submitted"}:
            raise InputInvoiceUsageOaReverseInvalidTransitionError("decision must be submitted or not_submitted.", code="invalid_manual_oa_reverse_decision")
        batch = self._get_batch(batch_id)
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            if batch.status in SUBMISSION_CONFIRMABLE_STATUSES:
                normalized_reason = "用户确认已在 OA 提交" if normalized_decision == "submitted" else "用户确认暂未提交 OA"
            else:
                normalized_reason = _required_text(reason, "reason")
        if self._is_operation_replay(batch, f"manual_oa_status:{normalized_decision}", normalized_key):
            return self.batch_payload(batch)
        self._assert_version(batch, expected_version)
        if batch.status not in MANUAL_FALLBACK_STATUSES | SUBMISSION_CONFIRMABLE_STATUSES:
            raise InputInvoiceUsageOaReverseInvalidTransitionError(
                "manual OA status is allowed only after draft creation or for detection exception states.",
                code="invalid_manual_oa_reverse_status",
            )
        before_status = batch.status
        if normalized_decision == "submitted" and batch.status in SUBMISSION_CONFIRMABLE_STATUSES:
            batch.status = InputInvoiceUsageOaReverseStatus.SUBMITTED_CONFIRMED.value
            batch.oa_process_status = "user_confirmed_submitted"
            batch.oa_detection_status = "user_confirmed_submitted"
            event_type = "oa_reverse_user_confirmed_submitted"
        elif normalized_decision == "submitted":
            batch.status = InputInvoiceUsageOaReverseStatus.SUBMITTED_CONFIRMED.value
            batch.oa_row_id = str(candidate_oa_row_id or "").strip() or None
            batch.oa_process_status = "manual_without_oa_row" if batch.oa_row_id is None else "in_progress"
            batch.oa_detection_status = "manual_submitted"
            event_type = "oa_reverse_manual_status_submitted"
        elif batch.status in SUBMISSION_CONFIRMABLE_STATUSES:
            batch.oa_detection_payload = {
                **dict(batch.oa_detection_payload or {}),
                "discardedOaDraftId": batch.oa_draft_id,
                "discardedOaDraftUrl": batch.oa_draft_url,
            }
            batch.oa_draft_id = None
            batch.oa_draft_url = None
            batch.oa_row_id = None
            batch.oa_process_status = "not_submitted"
            batch.status = InputInvoiceUsageOaReverseStatus.NOT_SUBMITTED.value
            batch.oa_detection_status = "user_confirmed_not_submitted"
            event_type = "oa_reverse_user_confirmed_not_submitted"
        else:
            batch.status = InputInvoiceUsageOaReverseStatus.MANUALLY_MARKED_NOT_SUBMITTED.value
            batch.oa_detection_status = "manual_not_submitted"
            event_type = "oa_reverse_manual_status_not_submitted"
        batch.oa_detection_reason = normalized_reason
        batch.operation_idempotency[f"manual_oa_status:{normalized_decision}"] = normalized_key
        self._bump_version(batch, actor_id=actor_id, event_type=event_type, before_status=before_status, after_status=batch.status, reason=normalized_reason)
        self._repository.save_batch(batch)
        self._record_external_audit(batch, event_type, actor_id=actor_id)
        return self.batch_payload(batch)

    @staticmethod
    def batch_payload(batch: InputInvoiceUsageOaReverseBatch, *, include_write_targets: bool = False) -> dict[str, object]:
        scope_keys = InputInvoiceUsageOaReverseService._batch_scope_keys(batch)
        payload: dict[str, object] = {
            "batchId": batch.batch_id,
            "status": batch.status,
            "version": batch.version,
            "targetApplicantCode": batch.target_applicant_code,
            "targetApplicantName": batch.target_applicant_name,
            "invoiceIds": list(batch.invoice_ids),
            "invoiceCount": len(batch.invoice_ids),
            "previewId": batch.preview_id,
            "previewHash": batch.preview_hash,
            "previewSummary": dict(batch.preview_summary or {}),
            "invoiceRows": [dict(row) for row in list(batch.invoice_display_rows or [])],
            "oaFormId": batch.oa_form_id,
            "oaDraftId": batch.oa_draft_id,
            "oaDraftUrl": batch.oa_draft_url,
            "oaRowId": batch.oa_row_id,
            "oaProcessStatus": batch.oa_process_status,
            "oaDetectionStatus": batch.oa_detection_status,
            "oaDetectionAttempts": batch.oa_detection_attempts,
            "oaDetectionReason": batch.oa_detection_reason,
            "oaDetectionError": batch.oa_detection_error,
            "oaDetectionPayload": dict(batch.oa_detection_payload or {}),
            "auditEvents": [_event_payload(event) for event in list(batch.audit_events or [])],
            "createdBy": batch.created_by,
            "updatedBy": batch.updated_by,
            "createdAt": _datetime_to_iso(batch.created_at),
            "updatedAt": _datetime_to_iso(batch.updated_at),
            "canCreateDraft": _can_create_oa_draft(batch),
            "canConfirmSubmission": _can_confirm_submission(batch),
            "canRevoke": _can_revoke_oa_draft(batch),
            "canRefreshStatus": batch.status in DETECTION_STATUSES,
            "canManualStatus": batch.status in MANUAL_FALLBACK_STATUSES,
        }
        if include_write_targets:
            payload.update(
                write_target_envelope(
                    read_model_key="input_invoice_usage",
                    scope_keys=scope_keys,
                    fallback_scope_key="all",
                )
            )
        return payload

    @staticmethod
    def _batch_scope_keys(batch: InputInvoiceUsageOaReverseBatch) -> list[str]:
        months = sorted(
            {
                month
                for row in list(batch.invoice_display_rows or [])
                for month in [str(row.get("invoiceDate") or "")[:7]]
                if len(month) == 7
            }
        )
        return months or ["all"]

    @staticmethod
    def _submitted_history_item(batch: InputInvoiceUsageOaReverseBatch) -> dict[str, object]:
        invoices: list[dict[str, object]] = []
        for row in list(batch.invoice_display_rows or []):
            invoices.append(
                {
                    "invoiceNo": str(row.get("invoiceNo") or ""),
                    "invoiceDate": str(row.get("invoiceDate") or ""),
                    "sellerName": str(row.get("sellerName") or ""),
                    "totalWithTax": str(row.get("totalWithTax") or ""),
                }
            )
        return {
            "targetApplicantName": batch.target_applicant_name,
            "submittedAt": _datetime_to_iso(batch.updated_at),
            "totalWithTax": str(batch.preview_summary.get("totalWithTax") or ""),
            "invoiceCount": len(batch.invoice_ids),
            "invoices": invoices,
        }

    def _rows_for_preview_payload(self, payload: dict[str, Any]) -> tuple[list[dict[str, object]], list[str]]:
        invoice_ids = _text_list(payload.get("invoiceIds"))
        if invoice_ids:
            read_model_payload = (
                self._read_model_rows_by_invoice_ids_loader(invoice_ids)
                if self._read_model_rows_by_invoice_ids_loader
                else None
            )
            read_model_rows = self._required_rows_from_read_model_payload(read_model_payload)
            known = {str(row.get("invoiceId") or "") for row in read_model_rows}
            missing_ids = _text_list(read_model_payload.get("missing_invoice_ids")) if isinstance(read_model_payload, dict) else []
            if not missing_ids:
                missing_ids = [invoice_id for invoice_id in invoice_ids if invoice_id not in known]
            return read_model_rows, missing_ids
        read_model_payload = (
            self._read_model_rows_loader(_preview_query_from_payload(payload))
            if self._read_model_rows_loader
            else None
        )
        return self._required_rows_from_read_model_payload(read_model_payload), []

    @classmethod
    def _required_rows_from_read_model_payload(cls, payload: dict[str, object] | None) -> list[dict[str, object]]:
        rows = cls._rows_from_read_model_payload(payload)
        if rows is not None:
            return rows
        raise InputInvoiceUsageError(
            "input_invoice_usage_oa_reverse_preview_refreshing",
            "进项发票使用情况读模型正在刷新，请稍后重试。",
            status_code=HTTPStatus.CONFLICT,
            details={
                "read_model_status": "missing",
                "read_model_scope_key": None,
                "read_model_stale_reasons": ["input_invoice_usage_read_model_unavailable"],
            },
        )

    @staticmethod
    def _rows_from_read_model_payload(payload: dict[str, object] | None) -> list[dict[str, object]] | None:
        if not isinstance(payload, dict):
            return None
        status = str(payload.get("read_model_status") or payload.get("refresh_status") or "fresh")
        if status != "fresh":
            raise InputInvoiceUsageError(
                "input_invoice_usage_oa_reverse_preview_refreshing",
                "进项发票使用情况读模型正在刷新，请稍后重试。",
                status_code=HTTPStatus.CONFLICT,
                details={
                    "read_model_status": status,
                    "read_model_scope_key": payload.get("read_model_scope_key"),
                    "read_model_stale_reasons": payload.get("read_model_stale_reasons"),
                },
            )
        return [row for row in list(payload.get("rows") or []) if isinstance(row, dict)]

    @staticmethod
    def _candidate_rejection(row: dict[str, object]) -> dict[str, object] | None:
        invoice_id = str(row.get("invoiceId") or "")
        oa_relation_status = InputInvoiceUsageOaReverseService._oa_relation_status(row)
        if oa_relation_status == "linked":
            return {
                "invoiceId": invoice_id,
                "reasonCode": "already_has_active_oa",
                "reason": "发票已有 active OA 关系",
                "oaRelationStatus": "linked",
            }
        return None

    @staticmethod
    def _invoice_display_row(row: dict[str, object]) -> dict[str, object]:
        invoice = row.get("invoice") if isinstance(row.get("invoice"), dict) else {}
        payment_status = row.get("paymentStatus") if isinstance(row.get("paymentStatus"), dict) else {}
        return {
            "invoiceId": str(row.get("invoiceId") or ""),
            "rowId": str(row.get("id") or ""),
            "invoiceIdentityKey": str(row.get("invoiceIdentityKey") or ""),
            "invoiceNo": str(invoice.get("invoiceNo") or ""),
            "invoiceDate": str(invoice.get("invoiceDate") or ""),
            "sellerName": str(invoice.get("sellerName") or ""),
            "sellerTaxNo": str(invoice.get("sellerTaxNo") or ""),
            "totalWithTax": _money(invoice.get("totalWithTax")),
            "paymentStatus": {
                "code": str(payment_status.get("code") or ""),
                "label": str(payment_status.get("label") or ""),
                "reason": str(payment_status.get("reason") or ""),
            },
            "oaRelationStatus": InputInvoiceUsageOaReverseService._oa_relation_status(row),
        }

    @staticmethod
    def _oa_relation_status(row: dict[str, object]) -> str:
        oa_payload = row.get("oa") if isinstance(row.get("oa"), dict) else {}
        summaries = [summary for summary in list(oa_payload.get("summaries") or []) if isinstance(summary, dict)]
        statuses = {
            str(summary.get("relationStatus") or summary.get("relation_status") or "linked").strip() or "linked"
            for summary in summaries
        }
        if "linked" in statuses:
            return "linked"
        if summaries:
            return "unlinked"
        if int(oa_payload.get("relationCount") or 0) > 0:
            return "linked"
        return "unlinked"

    @staticmethod
    def _resolve_target_applicant(value: Any) -> tuple[str, str]:
        code = str(value or "chen_xiuyun").strip() or "chen_xiuyun"
        name = TARGET_APPLICANTS.get(code)
        if name is None:
            if code not in set(TARGET_APPLICANTS.values()):
                raise InputInvoiceUsageError(
                    "invalid_target_applicant",
                    f"Unsupported target applicant: {code}",
                    details={"targetApplicantCode": code},
                )
            name = code
        return code, name

    @staticmethod
    def _target_applicant_options() -> list[dict[str, str]]:
        return [
            {"code": code, "name": name}
            for code, name in TARGET_APPLICANTS.items()
        ]

    @staticmethod
    def _build_oa_draft_payload(batch: InputInvoiceUsageOaReverseBatch) -> dict[str, object]:
        mapping = EtcOAFormFieldMapping.from_environment()
        total_with_tax = str(batch.preview_summary.get("totalWithTax") or "")
        invoice_numbers = [
            str(row.get("invoiceNo") or row.get("displayNo") or row.get("invoiceNumber") or "").strip()
            for row in list(batch.invoice_display_rows or [])
            if str(row.get("invoiceNo") or row.get("displayNo") or row.get("invoiceNumber") or "").strip()
        ]
        cause_parts = [
            "进项发票反提 OA",
            f"input_invoice_usage_oa_reverse_batch_id={batch.batch_id}",
            f"发票数={len(batch.invoice_ids)}",
        ]
        if invoice_numbers:
            cause_parts.append(f"发票号码={';'.join(invoice_numbers[:20])}")
        data = {
            mapping.applicant: batch.target_applicant_name,
            "applicant": batch.target_applicant_name,
            "targetApplicantCode": batch.target_applicant_code,
            mapping.application_date: date.today().isoformat(),
            mapping.category: mapping.category_value,
            mapping.payment_proof: mapping.payment_proof_value,
            mapping.project_name: mapping.project_name_value,
            mapping.amount: total_with_tax,
            "invoiceCount": len(batch.invoice_ids),
            "invoice_count": len(batch.invoice_ids),
            "inputInvoiceUsageOaReverseBatchId": batch.batch_id,
            mapping.cause: "；".join(cause_parts),
        }
        return {
            "formId": batch.oa_form_id,
            "isDraft": True,
            "data": data,
            "source": "input_invoice_usage_oa_reverse",
            "batchId": batch.batch_id,
            "targetApplicant": {
                "code": batch.target_applicant_code,
                "name": batch.target_applicant_name,
            },
            "summary": dict(batch.preview_summary or {}),
            "invoiceIds": list(batch.invoice_ids),
            "invoiceRows": [dict(row) for row in list(batch.invoice_display_rows or [])],
        }

    def _mark_draft_failed(
        self,
        batch: InputInvoiceUsageOaReverseBatch,
        *,
        actor_id: str,
        before_status: str,
        reason: str,
    ) -> None:
        batch.status = InputInvoiceUsageOaReverseStatus.OA_DRAFT_FAILED.value
        batch.oa_detection_status = "draft_failed"
        batch.oa_detection_error = reason
        self._bump_version(batch, actor_id=actor_id, event_type="oa_reverse_draft_failed", before_status=before_status, after_status=batch.status, reason=reason)
        self._repository.save_batch(batch)
        self._record_external_audit(batch, "oa_reverse_draft_failed", actor_id=actor_id)

    def _get_batch(self, batch_id: str) -> InputInvoiceUsageOaReverseBatch:
        batch = self._repository.get_batch(str(batch_id or "").strip())
        if batch is None:
            raise InputInvoiceUsageOaReverseNotFoundError(f"Input invoice usage OA reverse batch not found: {batch_id}")
        return batch

    @staticmethod
    def _assert_mutation_permission(can_mutate: bool) -> None:
        if not can_mutate:
            raise InputInvoiceUsageOaReversePermissionError("Permission denied for input invoice usage OA reverse mutation.")

    @staticmethod
    def _assert_version(batch: InputInvoiceUsageOaReverseBatch, expected_version: int | None) -> None:
        if expected_version is None:
            return
        if int(expected_version) != int(batch.version):
            raise InputInvoiceUsageOaReverseVersionConflictError(batch.batch_id, int(expected_version), int(batch.version))

    @staticmethod
    def _is_operation_replay(batch: InputInvoiceUsageOaReverseBatch, operation: str, idempotency_key: str) -> bool:
        return str(batch.operation_idempotency.get(operation) or "") == str(idempotency_key or "").strip()

    def _bump_version(
        self,
        batch: InputInvoiceUsageOaReverseBatch,
        *,
        actor_id: str,
        event_type: str,
        before_status: str | None,
        after_status: str,
        reason: str | None = None,
    ) -> None:
        batch.version += 1
        batch.updated_by = actor_id
        batch.updated_at = datetime.now(UTC)
        self._append_audit(batch, event_type, actor_id=actor_id, before_status=before_status, after_status=after_status, reason=reason)

    @staticmethod
    def _append_audit(
        batch: InputInvoiceUsageOaReverseBatch,
        event_type: str,
        *,
        actor_id: str,
        before_status: str | None,
        after_status: str | None,
        reason: str | None = None,
    ) -> None:
        batch.audit_events.append(
            {
                "eventId": f"input_invoice_usage_oa_reverse_audit_{uuid4().hex[:12]}",
                "eventType": event_type,
                "source": "api",
                "actorId": actor_id,
                "batchId": batch.batch_id,
                "beforeStatus": before_status,
                "afterStatus": after_status,
                "actualVersion": batch.version,
                "reason": reason,
                "createdAt": datetime.now(UTC),
            }
        )

    def _record_external_audit(self, batch: InputInvoiceUsageOaReverseBatch, action: str, *, actor_id: str) -> None:
        if self._audit_recorder is None:
            return
        self._audit_recorder(
            {
                "actor_id": actor_id,
                "action": action,
                "entity_type": "input_invoice_usage_oa_reverse_batch",
                "entity_id": batch.batch_id,
                "metadata": {
                    "status": batch.status,
                    "version": batch.version,
                    "invoice_ids": list(batch.invoice_ids),
                    "target_applicant_code": batch.target_applicant_code,
                    "oa_draft_id": batch.oa_draft_id,
                    "oa_row_id": batch.oa_row_id,
                },
            }
        )

    def _invalidate_read_models(self, batch: InputInvoiceUsageOaReverseBatch, reason: str) -> None:
        if self._read_model_invalidator is None:
            return
        months = sorted(
            {
                month
                for row in list(batch.invoice_display_rows or [])
                for month in [str(row.get("invoiceDate") or "")[:7]]
                if len(month) == 7
            }
        )
        self._read_model_invalidator(months or ["all"], reason)

    def _invalidate_statistics(self, reason: str) -> None:
        if self._statistics_invalidator is not None:
            self._statistics_invalidator(reason)


def _copy_batch(batch: InputInvoiceUsageOaReverseBatch | None) -> InputInvoiceUsageOaReverseBatch:
    if batch is None:
        raise ValueError("batch is required")
    return replace(
        batch,
        invoice_ids=list(batch.invoice_ids),
        preview_summary=dict(batch.preview_summary or {}),
        invoice_display_rows=[dict(row) for row in list(batch.invoice_display_rows or [])],
        operation_idempotency=dict(batch.operation_idempotency or {}),
        oa_detection_payload=dict(batch.oa_detection_payload or {}),
        audit_events=[dict(event) for event in list(batch.audit_events or [])],
    )


def _can_create_oa_draft(batch: InputInvoiceUsageOaReverseBatch) -> bool:
    if batch.oa_draft_id:
        return False
    return batch.status in {
        InputInvoiceUsageOaReverseStatus.DRAFT.value,
        InputInvoiceUsageOaReverseStatus.OA_DRAFT_FAILED.value,
        InputInvoiceUsageOaReverseStatus.NOT_SUBMITTED.value,
        InputInvoiceUsageOaReverseStatus.MANUALLY_MARKED_NOT_SUBMITTED.value,
    }


def _can_confirm_submission(batch: InputInvoiceUsageOaReverseBatch) -> bool:
    return bool(batch.oa_draft_id) and batch.status in SUBMISSION_CONFIRMABLE_STATUSES


def _can_revoke_oa_draft(batch: InputInvoiceUsageOaReverseBatch) -> bool:
    if not batch.oa_draft_id:
        return False
    return batch.status in DETECTION_STATUSES | SUBMISSION_CONFIRMABLE_STATUSES | {
        InputInvoiceUsageOaReverseStatus.OA_DRAFT_FAILED.value,
        InputInvoiceUsageOaReverseStatus.NOT_SUBMITTED.value,
        InputInvoiceUsageOaReverseStatus.MANUALLY_MARKED_NOT_SUBMITTED.value,
    }


def _batch_to_storage(batch: InputInvoiceUsageOaReverseBatch) -> dict[str, object]:
    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "version": batch.version,
        "target_applicant_code": batch.target_applicant_code,
        "target_applicant_name": batch.target_applicant_name,
        "invoice_ids": list(batch.invoice_ids),
        "preview_id": batch.preview_id,
        "preview_hash": batch.preview_hash,
        "preview_summary": dict(batch.preview_summary or {}),
        "invoice_display_rows": [dict(row) for row in list(batch.invoice_display_rows or [])],
        "idempotency_key": batch.idempotency_key,
        "operation_idempotency": dict(batch.operation_idempotency or {}),
        "oa_form_id": batch.oa_form_id,
        "oa_draft_id": batch.oa_draft_id,
        "oa_draft_url": batch.oa_draft_url,
        "oa_row_id": batch.oa_row_id,
        "oa_process_status": batch.oa_process_status,
        "oa_detection_status": batch.oa_detection_status,
        "oa_detection_attempts": batch.oa_detection_attempts,
        "oa_detection_reason": batch.oa_detection_reason,
        "oa_detection_error": batch.oa_detection_error,
        "oa_detection_payload": dict(batch.oa_detection_payload or {}),
        "created_by": batch.created_by,
        "updated_by": batch.updated_by,
        "audit_events": [_event_payload(event) for event in list(batch.audit_events or [])],
        "created_at": _datetime_to_iso(batch.created_at),
        "updated_at": _datetime_to_iso(batch.updated_at),
    }


def _batch_from_storage(value: Any) -> InputInvoiceUsageOaReverseBatch | None:
    if not isinstance(value, dict):
        return None
    return InputInvoiceUsageOaReverseBatch(
        batch_id=str(value.get("batch_id") or ""),
        status=str(value.get("status") or InputInvoiceUsageOaReverseStatus.DRAFT.value),
        version=int(value.get("version") or 1),
        target_applicant_code=str(value.get("target_applicant_code") or ""),
        target_applicant_name=str(value.get("target_applicant_name") or ""),
        invoice_ids=_text_list(value.get("invoice_ids")),
        preview_id=str(value.get("preview_id") or ""),
        preview_hash=str(value.get("preview_hash") or ""),
        preview_summary=dict(value.get("preview_summary") if isinstance(value.get("preview_summary"), dict) else {}),
        invoice_display_rows=[dict(row) for row in list(value.get("invoice_display_rows") or []) if isinstance(row, dict)],
        idempotency_key=str(value.get("idempotency_key") or "") or None,
        operation_idempotency=dict(value.get("operation_idempotency") if isinstance(value.get("operation_idempotency"), dict) else {}),
        oa_form_id=int(value.get("oa_form_id") or DEFAULT_OA_FORM_ID),
        oa_draft_id=str(value.get("oa_draft_id") or "") or None,
        oa_draft_url=str(value.get("oa_draft_url") or "") or None,
        oa_row_id=str(value.get("oa_row_id") or "") or None,
        oa_process_status=str(value.get("oa_process_status") or "unknown"),
        oa_detection_status=str(value.get("oa_detection_status") or "not_started"),
        oa_detection_attempts=int(value.get("oa_detection_attempts") or 0),
        oa_detection_reason=str(value.get("oa_detection_reason") or "") or None,
        oa_detection_error=str(value.get("oa_detection_error") or "") or None,
        oa_detection_payload=dict(value.get("oa_detection_payload") if isinstance(value.get("oa_detection_payload"), dict) else {}),
        created_by=str(value.get("created_by") or "") or None,
        updated_by=str(value.get("updated_by") or "") or None,
        audit_events=[dict(event) for event in list(value.get("audit_events") or []) if isinstance(event, dict)],
        created_at=_parse_datetime(value.get("created_at")),
        updated_at=_parse_datetime(value.get("updated_at")),
    )


def _event_payload(event: dict[str, object]) -> dict[str, object]:
    return {key: _serialize_value(value) for key, value in dict(event).items()}


def _oa_record_payload(record: OAApplicationRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "month": record.month,
        "section": record.section,
        "caseId": record.case_id,
        "applicant": record.applicant,
        "projectName": record.project_name,
        "applyType": record.apply_type,
        "amount": record.amount,
        "counterpartyName": record.counterparty_name,
        "reason": record.reason,
        "relationCode": record.relation_code,
        "source": record.source,
        "etcBatchId": record.etc_batch_id,
        "tags": list(record.tags or []),
        "detailFields": dict(record.detail_fields or {}),
        "attachmentEvidences": [dict(item) for item in list(record.attachment_evidences or [])],
        "attachmentArtifacts": [dict(item) for item in list(record.attachment_artifacts or [])],
        "attachmentInvoices": [dict(item) for item in list(record.attachment_invoices or [])],
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _datetime_to_iso(value)
    if isinstance(value, Decimal):
        return _money(value)
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


def _stable_hash(payload: dict[str, object]) -> str:
    return sha256(json.dumps(_serialize_value(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _batch_month_scope(batch: InputInvoiceUsageOaReverseBatch) -> str:
    months = sorted(
        {
            str(row.get("invoiceDate") or "")[:7]
            for row in list(batch.invoice_display_rows or [])
            if len(str(row.get("invoiceDate") or "")) >= 7
        }
    )
    return months[0] if len(months) == 1 else "all"


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise InputInvoiceUsageOaReverseInvalidTransitionError(f"{field_name} is required.", code=f"{field_name}_required")
    return text


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _preview_query_from_payload(payload: dict[str, Any]) -> dict[str, list[Any]]:
    query: dict[str, list[Any]] = {
        "page": ["1"],
        "page_size": ["200"],
        "sort_field": ["invoice_date"],
        "sort_direction": ["desc"],
    }
    for source_key, query_key in (
        ("keyword", "keyword"),
        ("invoiceDateFrom", "invoice_date_from"),
        ("invoiceDateTo", "invoice_date_to"),
        ("month", "month"),
    ):
        value = payload.get(source_key)
        if value not in (None, ""):
            query[query_key] = [value]
    if payload.get("filters") not in (None, ""):
        query["filters"] = [payload.get("filters")]
    return query


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ZERO


def _money(value: Any) -> str:
    return f"{_decimal(value).quantize(CENT)}"


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
