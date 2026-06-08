from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Callable, Iterable

from fin_ops_platform.services.imports import clean_string
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter
from fin_ops_platform.services.oa_adapter import OAApplicationRecord


DETECTION_DETECTED = "detected"
DETECTION_CONFLICT = "conflict"
DETECTION_MISSING = "missing"
DETECTION_UNAVAILABLE = "unavailable"
DETECTION_TIMEOUT = "timeout"
PAYMENT_REQUEST_FORM_ID = "2"


@dataclass(frozen=True, slots=True)
class EtcOADetectionContext:
    business_batch_id: str
    external_etc_batch_id: str
    amount: Decimal | str | int
    invoice_count: int
    owner_user_id: str | None = None
    owner_org_id: str | None = None
    oa_draft_created_at: datetime | None = None
    oa_detection_deadline_at: datetime | None = None
    oa_detection_final_retry_until: datetime | None = None


@dataclass(slots=True)
class EtcOADetectionResult:
    status: str
    reason: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    oa_row_id: str | None = None
    process_status: str | None = None
    error: str | None = None


@dataclass(slots=True)
class _PreparedCandidate:
    raw: Any
    summary: dict[str, Any]
    marker: str | None
    form_id: str
    amount: Decimal | None
    invoice_count: int | None
    owner_user_id: str
    owner_org_id: str
    created_at: datetime | None
    process_status: str
    search_text: str


class EtcOADetectionService:
    def detect(
        self,
        context: EtcOADetectionContext,
        candidates: Iterable[Any],
        *,
        now: datetime | None = None,
    ) -> EtcOADetectionResult:
        prepared = [self._prepare_candidate(candidate, context) for candidate in list(candidates or [])]
        deadline_exceeded = now is not None and context.oa_detection_deadline_at and now > context.oa_detection_deadline_at

        business_marker_candidates = [
            candidate for candidate in prepared if candidate.marker == "business_batch_id"
        ]
        marker_candidates = business_marker_candidates or [
            candidate for candidate in prepared if candidate.marker == "external_etc_batch_id"
        ]
        if not marker_candidates:
            if deadline_exceeded:
                return EtcOADetectionResult(
                    status=DETECTION_TIMEOUT,
                    reason="oa_detection_deadline_exceeded",
                    candidates=[candidate.summary for candidate in prepared[:10]],
                )
            return EtcOADetectionResult(
                status=DETECTION_MISSING,
                reason="oa_marker_missing",
                candidates=[candidate.summary for candidate in prepared[:10]],
            )
        invalid_reason: str | None = None
        valid_candidates: list[_PreparedCandidate] = []
        for candidate in marker_candidates:
            reason = self._candidate_rejection_reason(context, candidate)
            if reason is None:
                valid_candidates.append(candidate)
            elif invalid_reason is None:
                invalid_reason = reason

        if len(valid_candidates) == 1:
            candidate = valid_candidates[0]
            return EtcOADetectionResult(
                status=DETECTION_DETECTED,
                reason="unique_candidate_detected",
                candidates=[candidate.summary],
                oa_row_id=clean_string(candidate.summary.get("oaRowId")),
                process_status=candidate.process_status,
            )
        if len(valid_candidates) > 1:
            return EtcOADetectionResult(
                status=DETECTION_CONFLICT,
                reason="multiple_candidates",
                candidates=[candidate.summary for candidate in valid_candidates[:10]],
            )
        return EtcOADetectionResult(
            status=DETECTION_CONFLICT,
            reason=invalid_reason or "candidate_validation_failed",
            candidates=[candidate.summary for candidate in marker_candidates[:10]],
        )

    def detect_with_adapter(
        self,
        context: EtcOADetectionContext,
        query: Callable[[EtcOADetectionContext], Iterable[Any]],
        *,
        now: datetime | None = None,
    ) -> EtcOADetectionResult:
        try:
            return self.detect(context, query(context), now=now)
        except (OSError, TimeoutError, ValueError, RuntimeError) as exc:
            return EtcOADetectionResult(
                status=DETECTION_UNAVAILABLE,
                reason="oa_query_unavailable",
                error=str(exc),
            )

    @staticmethod
    def detection_window(context: EtcOADetectionContext) -> tuple[datetime | None, datetime | None]:
        start = context.oa_draft_created_at - timedelta(days=1) if context.oa_draft_created_at else None
        return start, None

    def _candidate_rejection_reason(
        self,
        context: EtcOADetectionContext,
        candidate: _PreparedCandidate,
    ) -> str | None:
        if clean_string(candidate.form_id) != PAYMENT_REQUEST_FORM_ID:
            return "form_id_mismatch"
        if candidate.amount != self._decimal(context.amount):
            return "amount_mismatch"
        if candidate.invoice_count != int(context.invoice_count):
            return "invoice_count_mismatch"
        if not self._organization_matches(context, candidate):
            return "organization_mismatch"
        if not self._within_detection_window(context, candidate):
            return "time_window_mismatch"
        if candidate.process_status != "in_progress":
            return "process_status_mismatch"
        return None

    def _prepare_candidate(self, candidate: Any, context: EtcOADetectionContext) -> _PreparedCandidate:
        payload = self._candidate_payload(candidate)
        detail_fields = payload.get("detail_fields")
        if not isinstance(detail_fields, dict):
            detail_fields = {}
        search_text = self._candidate_search_text(payload, detail_fields)
        marker = self._matched_marker(context, search_text)
        process_status = self._canonical_process_status(payload)
        summary = {
            "oaRowId": self._first_text(payload, "oa_row_id", "oaRowId", "id"),
            "applicant": self._first_text(payload, "applicant", "applicant_name", "userName"),
            "organization": self._first_text(payload, "organization", "owner_org_id", "org_id", "department"),
            "amount": self._first_text(payload, "amount"),
            "invoiceCount": self._invoice_count(payload, detail_fields),
            "createdAt": self._format_datetime(self._candidate_created_at(payload)),
            "processStatus": process_status,
            "matchedMarker": marker,
        }
        return _PreparedCandidate(
            raw=candidate,
            summary=summary,
            marker=marker,
            form_id=self._first_text(payload, "form_id", "formId") or clean_string(detail_fields.get("表单ID")),
            amount=self._decimal(payload.get("amount")),
            invoice_count=self._invoice_count(payload, detail_fields),
            owner_user_id=self._first_text(payload, "owner_user_id", "applicant_user_id", "user_id", "applicant"),
            owner_org_id=self._first_text(
                payload,
                "owner_org_id",
                "org_id",
                "organization_id",
                "department_id",
                "organization",
            ),
            created_at=self._candidate_created_at(payload),
            process_status=process_status,
            search_text=search_text,
        )

    @staticmethod
    def _candidate_payload(candidate: Any) -> dict[str, Any]:
        if isinstance(candidate, OAApplicationRecord):
            return {
                "id": candidate.id,
                "amount": candidate.amount,
                "applicant": candidate.applicant,
                "reason": candidate.reason,
                "form_id": candidate.detail_fields.get("表单ID"),
                "process_status": candidate.detail_fields.get("流程状态"),
                "detail_fields": candidate.detail_fields,
            }
        if isinstance(candidate, dict):
            return dict(candidate)
        payload: dict[str, Any] = {}
        for key in (
            "id",
            "oa_row_id",
            "form_id",
            "amount",
            "applicant",
            "reason",
            "process_status",
            "detail_fields",
            "created_at",
        ):
            if hasattr(candidate, key):
                payload[key] = getattr(candidate, key)
        return payload

    @staticmethod
    def _canonical_process_status(payload: dict[str, Any]) -> str:
        explicit = payload.get("process_status") or payload.get("processStatus")
        if explicit not in (None, ""):
            normalized = clean_string(explicit)
            if normalized in {"completed", "in_progress"}:
                return normalized
            return MongoOAAdapter.canonical_process_status({"processStatus": explicit})
        return MongoOAAdapter.canonical_process_status(payload)

    @staticmethod
    def _candidate_search_text(payload: dict[str, Any], detail_fields: dict[str, Any]) -> str:
        values: list[str] = []
        for key in ("reason", "cause", "remark", "comments", "description"):
            value = payload.get(key)
            if value not in (None, ""):
                values.append(clean_string(value))
        for value in detail_fields.values():
            if value not in (None, ""):
                values.append(clean_string(value))
        return "\n".join(values)

    @staticmethod
    def _matched_marker(context: EtcOADetectionContext, text: str) -> str | None:
        if context.business_batch_id and re.search(
            rf"business_batch_id\s*=\s*{re.escape(context.business_batch_id)}",
            text,
            re.IGNORECASE,
        ):
            return "business_batch_id"
        if context.external_etc_batch_id and re.search(
            rf"etc_batch_id\s*=\s*{re.escape(context.external_etc_batch_id)}",
            text,
            re.IGNORECASE,
        ):
            return "external_etc_batch_id"
        return None

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(clean_string(value).replace(",", ""))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _invoice_count(payload: dict[str, Any], detail_fields: dict[str, Any]) -> int | None:
        for value in (
            payload.get("invoice_count"),
            payload.get("invoiceCount"),
            detail_fields.get("ETC发票数量"),
            detail_fields.get("发票数量"),
        ):
            if value in (None, ""):
                continue
            try:
                return int(clean_string(value))
            except ValueError:
                continue
        text = "\n".join(clean_string(value) for value in payload.values() if isinstance(value, str))
        match = re.search(r"(?:invoice_count|发票数量)\s*[=:：]\s*(\d+)", text, re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _organization_matches(context: EtcOADetectionContext, candidate: _PreparedCandidate) -> bool:
        expected_user = clean_string(context.owner_user_id)
        expected_org = clean_string(context.owner_org_id)
        if expected_user and candidate.owner_user_id == expected_user:
            return True
        if expected_org and candidate.owner_org_id == expected_org:
            return True
        return not expected_user and not expected_org

    def _within_detection_window(self, context: EtcOADetectionContext, candidate: _PreparedCandidate) -> bool:
        if candidate.marker in {"business_batch_id", "external_etc_batch_id"}:
            return True
        start, _end = self.detection_window(context)
        if start is None:
            return True
        if candidate.created_at is None:
            return False
        return start <= candidate.created_at

    @staticmethod
    def _candidate_created_at(payload: dict[str, Any]) -> datetime | None:
        value = payload.get("created_at") or payload.get("createdAt") or payload.get("applicationDate")
        if isinstance(value, datetime):
            return value
        text = clean_string(value)
        if not text:
            return None
        for candidate in (text, text.replace("Z", "+00:00")):
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
        if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            try:
                return datetime.fromisoformat(f"{text}T00:00:00")
            except ValueError:
                return None
        return None

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        return value.isoformat() if isinstance(value, datetime) else None

    @staticmethod
    def _first_text(payload: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return clean_string(value)
        return ""
