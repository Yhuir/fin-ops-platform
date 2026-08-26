from __future__ import annotations

from typing import Any


class WorkbenchAnomalyReviewConflict(ValueError):
    def __init__(self, message: str, *, code: str = "workbench_anomaly_changed") -> None:
        super().__init__(message)
        self.code = code


class WorkbenchAnomalyReviewService:
    def __init__(self, *, group_repository: Any, decision_repository: Any) -> None:
        self._group_repository = group_repository
        self._decision_repository = decision_repository

    def review(
        self,
        payload: dict[str, object],
        *,
        actor_id: str,
        actor_account: str,
        actor_name: str,
    ) -> dict[str, object]:
        scope_key = str(payload.get("month") or "").strip()
        zone = str(payload.get("zone") or "").strip()
        group_id = str(payload.get("group_id") or "").strip()
        detail_key = str(payload.get("detail_key") or "").strip()
        fingerprint = str(payload.get("fingerprint") or "").strip().lower()
        decision = str(payload.get("decision") or "").strip()
        note = str(payload.get("note") or "").strip()
        if zone not in {"paired", "unpaired"}:
            raise ValueError("zone must be paired or unpaired.")
        if decision not in {"accept_paired", "keep_unpaired"}:
            raise ValueError("decision must be accept_paired or keep_unpaired.")
        if not scope_key or not group_id or not fingerprint:
            raise ValueError("month, group_id and fingerprint are required.")

        detail = self._group_repository.get_workbench_group_detail(
            scope_key=scope_key,
            zone=zone,
            group_id=group_id,
            detail_key=detail_key or None,
        )
        group = detail.get("group") if isinstance(detail, dict) else None
        if not isinstance(group, dict) and isinstance(detail, dict):
            group = detail
        if not isinstance(group, dict):
            raise WorkbenchAnomalyReviewConflict("异常关系组已变化，请刷新后重试。")
        anomaly = group.get("workbench_anomaly")
        if not isinstance(anomaly, dict) or str(anomaly.get("fingerprint") or "") != fingerprint:
            raise WorkbenchAnomalyReviewConflict("异常已变化或已消失，请刷新后重试。")
        evidence_item_fingerprints = sorted(
            str(value or "").strip().lower()
            for value in list(anomaly.get("evidence_item_fingerprints") or [])
            if str(value or "").strip()
        )
        detected_classification_codes = sorted(
            {
                str(item.get("code") or "").strip()
                for item in list(anomaly.get("items") or [])
                if isinstance(item, dict) and str(item.get("code") or "").strip()
            }
        )
        if not evidence_item_fingerprints or not detected_classification_codes:
            raise WorkbenchAnomalyReviewConflict("异常已变化或已消失，请刷新后重试。")
        if decision == "accept_paired":
            other_blockers = [
                reason
                for reason in list((group.get("completion") or {}).get("blocking_reasons") or [])
                if reason != "anomaly_review_required"
            ]
            if other_blockers:
                raise WorkbenchAnomalyReviewConflict(
                    "该关系仍有未解决的配对条件，不能强制进入已配对。",
                    code="workbench_anomaly_review_blocked",
                )

        source_scope = str(
            (detail.get("source_scope_key") if isinstance(detail, dict) else None)
            or group.get("source_scope_key")
            or group.get("scope_month")
            or group.get("month")
            or ""
        ).strip()
        row_scopes = self._group_row_scopes(group)
        if source_scope:
            decision_scope_key = self._normalize_scope_key(source_scope)
        elif len(row_scopes) == 1:
            decision_scope_key = next(iter(row_scopes))
        elif len(row_scopes) > 1:
            decision_scope_key = "all"
        else:
            decision_scope_key = self._normalize_scope_key(
                str(group.get("scope_key") or scope_key).strip()
            )
        result = self._decision_repository.set_workbench_anomaly_review_decision(
            fingerprint=fingerprint,
            group_id=group_id,
            scope_key=decision_scope_key,
            actor_id=actor_id,
            actor_account=actor_account,
            actor_name=actor_name,
            decision=decision,
            note=note,
            detected_classification_codes=detected_classification_codes,
            evidence_item_fingerprints=evidence_item_fingerprints,
        )
        return {**result, "affected_scope_keys": [decision_scope_key]}

    @staticmethod
    def _group_row_scopes(group: dict[str, object]) -> set[str]:
        return {
            WorkbenchAnomalyReviewService._normalize_scope_key(
                str(
                    row.get("source_scope_key")
                    or row.get("scope_month")
                    or row.get("month")
                    or ""
                ).strip()
            )
            for pane in ("oa", "bank", "invoice")
            for row in list(group.get(f"{pane}_rows") or [])
            if isinstance(row, dict)
            and str(
                row.get("source_scope_key")
                or row.get("scope_month")
                or row.get("month")
                or ""
            ).strip()
        }

    @staticmethod
    def _normalize_scope_key(scope_key: str) -> str:
        if scope_key == "all":
            return "all"
        normalized = scope_key[:7]
        if (
            len(normalized) != 7
            or normalized[4] != "-"
            or not normalized[:4].isdigit()
            or not normalized[5:].isdigit()
            or not 1 <= int(normalized[5:]) <= 12
        ):
            raise ValueError("异常所属月份无效，请刷新后重试。")
        return normalized


__all__ = [
    "WorkbenchAnomalyReviewConflict",
    "WorkbenchAnomalyReviewService",
]
