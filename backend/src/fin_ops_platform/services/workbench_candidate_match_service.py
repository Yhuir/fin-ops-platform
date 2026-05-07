from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import re
from threading import RLock
from typing import Any


CANDIDATE_MATCH_SCHEMA_VERSION = "2026-05-workbench-candidate-match-v1"
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
VALID_CANDIDATE_STATUSES = {"auto_closed", "needs_review", "conflict", "incomplete"}
VALID_CONFIDENCE_LEVELS = {"high", "medium", "low"}


class WorkbenchCandidateMatchService:
    def __init__(self, *, candidates: dict[str, dict[str, Any]] | None = None) -> None:
        self._lock = RLock()
        self._candidates = self._normalize_candidates(candidates or {})

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "WorkbenchCandidateMatchService":
        if not snapshot:
            return cls()
        candidates = snapshot.get("candidates")
        return cls(candidates=candidates if isinstance(candidates, dict) else {})

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"candidates": deepcopy(self._candidates)}

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
            return deleted_keys

    def clear(self) -> list[str]:
        with self._lock:
            deleted_keys = list(self._candidates.keys())
            self._candidates.clear()
            return deleted_keys

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
            raise ValueError("candidate.status must be one of auto_closed, needs_review, conflict, incomplete.")
        confidence = str(candidate.get("confidence") or "").strip()
        if confidence not in VALID_CONFIDENCE_LEVELS:
            raise ValueError("candidate.confidence must be one of high, medium, low.")

        candidate_id = str(candidate.get("candidate_id") or candidate_key).strip()
        if not candidate_id:
            candidate_id = candidate_key

        source_versions = candidate.get("source_versions")

        return {
            "candidate_id": candidate_id,
            "candidate_key": candidate_key,
            "schema_version": str(candidate.get("schema_version") or CANDIDATE_MATCH_SCHEMA_VERSION),
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
    def _normalize_required_text(value: Any, field_name: str) -> str:
        resolved_value = str(value or "").strip()
        if not resolved_value:
            raise ValueError(f"{field_name} is required for workbench candidate matches.")
        return resolved_value

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
