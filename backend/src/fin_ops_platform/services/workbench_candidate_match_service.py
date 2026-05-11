from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import re
from threading import RLock
from typing import Any


CANDIDATE_MATCH_SCHEMA_VERSION = "2026-05-exception-candidate-lifecycle"
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
VALID_CANDIDATE_STATUSES = {"auto_closed", "needs_review", "conflict", "incomplete", "consumed", "suppressed"}
VALID_CONFIDENCE_LEVELS = {"high", "medium", "low"}
VALID_SUPPRESSED_REASONS = {"", "active_exception_case", "active_pair_relation", "manual_override"}


class WorkbenchCandidateMatchService:
    def __init__(
        self,
        *,
        candidates: dict[str, dict[str, Any]] | None = None,
        scope_runs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._lock = RLock()
        self._candidates = self._normalize_candidates(candidates or {})
        self._scope_runs = self._normalize_scope_runs(scope_runs or {})

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "WorkbenchCandidateMatchService":
        if not snapshot:
            return cls()
        candidates = snapshot.get("candidates")
        scope_runs = snapshot.get("scope_runs")
        return cls(
            candidates=candidates if isinstance(candidates, dict) else {},
            scope_runs=scope_runs if isinstance(scope_runs, dict) else {},
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "candidates": deepcopy(self._candidates),
                "scope_runs": deepcopy(self._scope_runs),
            }

    @classmethod
    def build_candidate_key(
        cls,
        *,
        scope_month: str,
        rule_code: str,
        row_ids: list[str],
    ) -> str:
        payload = {
            "scope_month": cls._normalize_month(scope_month),
            "rule_code": cls._normalize_required_text(rule_code, "rule_code"),
            "row_ids": cls._normalize_row_ids(row_ids),
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"candidate:{digest}"

    def upsert_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            raise ValueError("candidate payload must be a dict.")

        normalized_input = deepcopy(candidate)
        candidate_key = self.build_candidate_key(
            scope_month=str(normalized_input.get("scope_month") or ""),
            rule_code=str(normalized_input.get("rule_code") or ""),
            row_ids=list(normalized_input.get("row_ids") or []),
        )
        with self._lock:
            existing = self._candidates.get(candidate_key)
            normalized = self._normalize_candidate(
                {
                    **(deepcopy(existing) if isinstance(existing, dict) else {}),
                    **normalized_input,
                    "candidate_key": candidate_key,
                    "candidate_id": (
                        str(existing.get("candidate_id"))
                        if isinstance(existing, dict) and existing.get("candidate_id")
                        else str(normalized_input.get("candidate_id") or candidate_key)
                    ),
                },
                fallback_candidate_key=candidate_key,
            )
            self._candidates[candidate_key] = normalized
            return deepcopy(normalized)

    def list_candidates_by_month(self, scope_month: str) -> list[dict[str, Any]]:
        resolved_month = self._normalize_month(scope_month)
        with self._lock:
            return [
                deepcopy(candidate)
                for candidate in self._candidates.values()
                if candidate.get("scope_month") == resolved_month
            ]

    def delete_month(self, scope_month: str) -> list[str]:
        resolved_month = self._normalize_month(scope_month)
        with self._lock:
            deleted_keys = [
                candidate_key
                for candidate_key, candidate in self._candidates.items()
                if candidate.get("scope_month") == resolved_month
            ]
            for candidate_key in deleted_keys:
                self._candidates.pop(candidate_key, None)
            self._scope_runs.pop(resolved_month, None)
            return deleted_keys

    def clear(self) -> list[str]:
        with self._lock:
            deleted_keys = list(self._candidates.keys())
            self._candidates.clear()
            self._scope_runs.clear()
            return deleted_keys

    def mark_candidates_consumed(
        self,
        *,
        candidate_keys: list[str] | None = None,
        candidate_ids: list[str] | None = None,
        row_ids: list[str] | None = None,
        consumed_by_case_id: str,
        consumed_by_relation_case_id: str | None = None,
        exception_preview: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        resolved_case_id = self._normalize_required_text(consumed_by_case_id, "consumed_by_case_id")
        return self._mark_candidates(
            candidate_keys=candidate_keys,
            candidate_ids=candidate_ids,
            row_ids=row_ids,
            updates={
                "status": "consumed",
                "consumed_by_case_id": resolved_case_id,
                "consumed_by_relation_case_id": str(consumed_by_relation_case_id or "").strip(),
                "suppressed_reason": "",
                "exception_preview": deepcopy(exception_preview) if isinstance(exception_preview, dict) else None,
            },
        )

    def mark_candidates_suppressed(
        self,
        *,
        candidate_keys: list[str] | None = None,
        candidate_ids: list[str] | None = None,
        row_ids: list[str] | None = None,
        suppressed_reason: str,
        consumed_by_case_id: str | None = None,
        consumed_by_relation_case_id: str | None = None,
        exception_preview: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        resolved_reason = str(suppressed_reason or "").strip()
        if resolved_reason not in VALID_SUPPRESSED_REASONS or not resolved_reason:
            raise ValueError("suppressed_reason must be active_exception_case, active_pair_relation, or manual_override.")
        return self._mark_candidates(
            candidate_keys=candidate_keys,
            candidate_ids=candidate_ids,
            row_ids=row_ids,
            updates={
                "status": "suppressed",
                "consumed_by_case_id": str(consumed_by_case_id or "").strip(),
                "consumed_by_relation_case_id": str(consumed_by_relation_case_id or "").strip(),
                "suppressed_reason": resolved_reason,
                "exception_preview": deepcopy(exception_preview) if isinstance(exception_preview, dict) else None,
            },
        )

    def mark_scope_processed(
        self,
        scope_month: str,
        *,
        source_versions: dict[str, Any] | None,
        candidate_count: int,
        request_id: str,
        reason: str,
    ) -> dict[str, Any]:
        resolved_month = self._normalize_month(scope_month)
        run = {
            "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
            "source_versions": deepcopy(source_versions if isinstance(source_versions, dict) else {}),
            "candidate_count": max(int(candidate_count or 0), 0),
            "generated_at": self._timestamp(),
            "request_id": str(request_id or "").strip(),
            "reason": str(reason or "").strip(),
        }
        with self._lock:
            self._scope_runs[resolved_month] = run
            return deepcopy(run)

    def is_scope_fresh(
        self,
        scope_month: str,
        *,
        source_versions: dict[str, Any] | None,
    ) -> bool:
        resolved_month = self._normalize_month(scope_month)
        expected_versions = deepcopy(source_versions if isinstance(source_versions, dict) else {})
        with self._lock:
            scope_run = self._scope_runs.get(resolved_month)
            if not isinstance(scope_run, dict):
                return False
            if str(scope_run.get("schema_version") or "").strip() != CANDIDATE_MATCH_SCHEMA_VERSION:
                return False
            persisted_versions = scope_run.get("source_versions")
            resolved_persisted_versions = persisted_versions if isinstance(persisted_versions, dict) else {}
            if not expected_versions:
                return resolved_persisted_versions == {}
            return all(resolved_persisted_versions.get(key) == value for key, value in expected_versions.items())

    def stale_scope_months(
        self,
        scope_months: list[str],
        *,
        source_versions: dict[str, Any] | None,
    ) -> list[str]:
        stale: list[str] = []
        for scope_month in sorted(dict.fromkeys(str(month or "").strip() for month in list(scope_months or []))):
            if not scope_month:
                continue
            if not self.is_scope_fresh(scope_month, source_versions=source_versions):
                stale.append(scope_month)
        return stale

    @classmethod
    def _normalize_candidates(cls, candidates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for candidate_key, candidate in candidates.items():
            if not isinstance(candidate, dict):
                continue
            try:
                normalized_candidate = cls._normalize_candidate(
                    candidate,
                    fallback_candidate_key=str(candidate_key),
                )
            except ValueError:
                continue
            normalized[str(normalized_candidate["candidate_key"])] = normalized_candidate
        return normalized

    def _mark_candidates(
        self,
        *,
        candidate_keys: list[str] | None,
        candidate_ids: list[str] | None,
        row_ids: list[str] | None,
        updates: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if updates.get("exception_preview") is None:
            updates = {key: value for key, value in updates.items() if key != "exception_preview"}
        with self._lock:
            selected_keys = self._select_candidate_keys(
                candidate_keys=candidate_keys,
                candidate_ids=candidate_ids,
                row_ids=row_ids,
            )
            updated_candidates: list[dict[str, Any]] = []
            for candidate_key in selected_keys:
                existing = self._candidates.get(candidate_key)
                if not isinstance(existing, dict):
                    continue
                normalized = self._normalize_candidate(
                    {
                        **deepcopy(existing),
                        **deepcopy(updates),
                    },
                    fallback_candidate_key=candidate_key,
                )
                self._candidates[candidate_key] = normalized
                updated_candidates.append(deepcopy(normalized))
            return updated_candidates

    def _select_candidate_keys(
        self,
        *,
        candidate_keys: list[str] | None,
        candidate_ids: list[str] | None,
        row_ids: list[str] | None,
    ) -> list[str]:
        selected: list[str] = []
        requested_keys = {
            str(candidate_key or "").strip()
            for candidate_key in list(candidate_keys or [])
            if str(candidate_key or "").strip()
        }
        requested_ids = {
            str(candidate_id or "").strip()
            for candidate_id in list(candidate_ids or [])
            if str(candidate_id or "").strip()
        }
        requested_row_ids = {
            str(row_id or "").strip()
            for row_id in list(row_ids or [])
            if str(row_id or "").strip()
        }
        if not requested_keys and not requested_ids and not requested_row_ids:
            raise ValueError("candidate_keys, candidate_ids, or row_ids is required.")
        for candidate_key, candidate in self._candidates.items():
            if candidate_key in requested_keys or str(candidate.get("candidate_id") or "").strip() in requested_ids:
                selected.append(candidate_key)
                continue
            candidate_row_ids = {str(row_id) for row_id in list(candidate.get("row_ids") or [])}
            if requested_row_ids and requested_row_ids.intersection(candidate_row_ids):
                selected.append(candidate_key)
        return selected

    @classmethod
    def _normalize_scope_runs(cls, scope_runs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for scope_month, scope_run in scope_runs.items():
            if not isinstance(scope_run, dict):
                continue
            try:
                resolved_month = cls._normalize_month(scope_month)
            except ValueError:
                continue
            if str(scope_run.get("schema_version") or "").strip() != CANDIDATE_MATCH_SCHEMA_VERSION:
                continue
            source_versions = scope_run.get("source_versions")
            normalized[resolved_month] = {
                "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "source_versions": deepcopy(source_versions if isinstance(source_versions, dict) else {}),
                "candidate_count": cls._non_negative_int(scope_run.get("candidate_count")),
                "generated_at": str(scope_run.get("generated_at") or cls._timestamp()),
                "request_id": str(scope_run.get("request_id") or "").strip(),
                "reason": str(scope_run.get("reason") or "").strip(),
            }
        return normalized

    @classmethod
    def _normalize_candidate(
        cls,
        candidate: dict[str, Any],
        *,
        fallback_candidate_key: str,
    ) -> dict[str, Any]:
        scope_month = cls._normalize_month(candidate.get("scope_month"))
        rule_code = cls._normalize_required_text(candidate.get("rule_code"), "rule_code")
        row_ids = cls._normalize_row_ids(candidate.get("row_ids"))
        expected_candidate_key = cls.build_candidate_key(
            scope_month=scope_month,
            rule_code=rule_code,
            row_ids=row_ids,
        )
        candidate_key = str(candidate.get("candidate_key") or fallback_candidate_key).strip()
        if candidate_key != expected_candidate_key:
            candidate_key = expected_candidate_key

        status = str(candidate.get("status") or "").strip()
        if status not in VALID_CANDIDATE_STATUSES:
            raise ValueError(
                "candidate.status must be one of auto_closed, needs_review, conflict, incomplete, consumed, suppressed."
            )
        confidence = str(candidate.get("confidence") or "").strip()
        if confidence not in VALID_CONFIDENCE_LEVELS:
            raise ValueError("candidate.confidence must be one of high, medium, low.")

        candidate_id = str(candidate.get("candidate_id") or candidate_key).strip()
        if not candidate_id:
            candidate_id = candidate_key

        source_versions = candidate.get("source_versions")

        suppressed_reason = str(candidate.get("suppressed_reason") or "").strip()
        if suppressed_reason not in VALID_SUPPRESSED_REASONS:
            raise ValueError("candidate.suppressed_reason is not supported.")

        return {
            "candidate_id": candidate_id,
            "candidate_key": candidate_key,
            "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
            "scope_month": scope_month,
            "candidate_type": cls._normalize_required_text(candidate.get("candidate_type"), "candidate_type"),
            "status": status,
            "confidence": confidence,
            "rule_code": rule_code,
            "row_ids": row_ids,
            "oa_row_ids": cls._normalize_optional_ids(candidate.get("oa_row_ids")),
            "bank_row_ids": cls._normalize_optional_ids(candidate.get("bank_row_ids")),
            "invoice_row_ids": cls._normalize_optional_ids(candidate.get("invoice_row_ids")),
            "amount": deepcopy(candidate.get("amount")),
            "amount_delta": deepcopy(candidate.get("amount_delta")),
            "explanation": str(candidate.get("explanation") or ""),
            "conflict_candidate_keys": cls._normalize_optional_ids(candidate.get("conflict_candidate_keys")),
            "generated_at": str(candidate.get("generated_at") or cls._timestamp()),
            "source_versions": deepcopy(source_versions if isinstance(source_versions, dict) else {}),
            "tags": cls._normalize_optional_texts(candidate.get("tags")),
            "special_metadata": deepcopy(
                candidate.get("special_metadata") if isinstance(candidate.get("special_metadata"), dict) else {}
            ),
            "consumed_by_case_id": str(candidate.get("consumed_by_case_id") or "").strip(),
            "consumed_by_relation_case_id": str(candidate.get("consumed_by_relation_case_id") or "").strip(),
            "suppressed_reason": suppressed_reason,
            "exception_preview": cls._normalize_exception_preview(candidate.get("exception_preview")),
        }

    @staticmethod
    def _normalize_month(month: Any) -> str:
        resolved_month = str(month or "").strip()
        if not resolved_month:
            raise ValueError("scope_month is required for workbench candidate matches.")
        if MONTH_RE.match(resolved_month):
            return resolved_month
        raise ValueError("scope_month must be YYYY-MM for workbench candidate matches.")

    @classmethod
    def _normalize_row_ids(cls, row_ids: Any) -> list[str]:
        normalized = cls._normalize_optional_ids(row_ids)
        if not normalized:
            raise ValueError("row_ids is required for workbench candidate matches.")
        return sorted(normalized)

    @staticmethod
    def _normalize_optional_ids(row_ids: Any) -> list[str]:
        if not isinstance(row_ids, list):
            return []
        normalized: list[str] = []
        for row_id in row_ids:
            resolved_row_id = str(row_id or "").strip()
            if resolved_row_id and resolved_row_id not in normalized:
                normalized.append(resolved_row_id)
        return normalized

    @staticmethod
    def _normalize_optional_texts(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            resolved_value = str(value or "").strip()
            if resolved_value and resolved_value not in normalized:
                normalized.append(resolved_value)
        return normalized

    @classmethod
    def _normalize_exception_preview(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        preview = deepcopy(value)
        scenario_code = str(preview.get("scenario_code") or "").strip()
        available_action_codes = cls._normalize_optional_texts(preview.get("available_action_codes"))
        normalized: dict[str, Any] = {}
        if scenario_code:
            normalized["scenario_code"] = scenario_code
        if available_action_codes:
            normalized["available_action_codes"] = available_action_codes
        for key, payload in preview.items():
            if key not in normalized and key not in {"scenario_code", "available_action_codes"}:
                normalized[str(key)] = deepcopy(payload)
        return normalized

    @staticmethod
    def _non_negative_int(value: Any) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_required_text(value: Any, field_name: str) -> str:
        resolved_value = str(value or "").strip()
        if not resolved_value:
            raise ValueError(f"{field_name} is required for workbench candidate matches.")
        return resolved_value

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
