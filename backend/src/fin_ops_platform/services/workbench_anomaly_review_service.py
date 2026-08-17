from __future__ import annotations

from typing import Any


WORKBENCH_AMOUNT_REVIEW_CLASSIFICATION_CODES = frozenset(
    {
        "oa_bank_amount_mismatch",
        "oa_invoice_amount_mismatch",
        "bank_invoice_amount_mismatch",
    }
)
WORKBENCH_NO_ANOMALY_REVIEW_CLASSIFICATION = "no_anomaly"


class WorkbenchAnomalyReviewConflict(ValueError):
    def __init__(self, message: str, *, code: str = "workbench_anomaly_changed") -> None:
        super().__init__(message)
        self.code = code


class WorkbenchAnomalyReviewService:
    def __init__(self, *, group_repository: Any, decision_repository: Any) -> None:
        self._group_repository = group_repository
        self._decision_repository = decision_repository

    def review(self, payload: dict[str, object], *, actor_id: str) -> dict[str, object]:
        scope_key = str(payload.get("month") or "").strip()
        zone = str(payload.get("zone") or "").strip()
        group_id = str(payload.get("group_id") or "").strip()
        detail_key = str(payload.get("detail_key") or "").strip()
        fingerprint = str(payload.get("fingerprint") or "").strip().lower()
        decision = str(payload.get("decision") or "").strip()
        note = str(payload.get("note") or "").strip()
        review_classification_codes = sorted(
            dict.fromkeys(
                str(value or "").strip()
                for value in list(payload.get("review_classification_codes") or [])
                if str(value or "").strip()
            )
        )
        reviewed_items = sorted(
            dict.fromkeys(
                str(value or "").strip().lower()
                for value in list(payload.get("reviewed_item_fingerprints") or [])
                if str(value or "").strip()
            )
        )
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
        current_items = sorted(
            str(item.get("fingerprint") or "").strip().lower()
            for item in list(anomaly.get("items") or [])
            if isinstance(item, dict) and str(item.get("fingerprint") or "").strip()
        )
        if reviewed_items != current_items:
            raise ValueError("必须审阅当前异常中的每一项后才能提交判断。")
        current_amount_codes = {
            str(item.get("code") or "").strip()
            for item in list(anomaly.get("items") or [])
            if isinstance(item, dict)
            and str(item.get("code") or "").strip()
            in WORKBENCH_AMOUNT_REVIEW_CLASSIFICATION_CODES
        }
        allowed_classification_codes = {
            *WORKBENCH_AMOUNT_REVIEW_CLASSIFICATION_CODES,
            WORKBENCH_NO_ANOMALY_REVIEW_CLASSIFICATION,
        }
        unknown_classification_codes = sorted(
            set(review_classification_codes) - allowed_classification_codes
        )
        if unknown_classification_codes:
            raise ValueError("人工金额判断包含不支持的类型。")
        is_legacy_paired_withdrawal = (
            decision == "keep_unpaired"
            and str(anomaly.get("review_decision") or "").strip() == "accept_paired"
        )
        if (
            current_amount_codes
            and not review_classification_codes
            and not is_legacy_paired_withdrawal
        ):
            raise ValueError("存在金额异常时必须选择人工金额判断。")
        if not current_amount_codes and review_classification_codes:
            raise ValueError("当前异常不包含需要人工判断的金额异常。")
        if (
            WORKBENCH_NO_ANOMALY_REVIEW_CLASSIFICATION in review_classification_codes
            and len(review_classification_codes) > 1
        ):
            raise ValueError("无异常不能与金额不一致类型同时选择。")
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
            decision=decision,
            note=note,
            review_classification_codes=review_classification_codes,
            reviewed_item_fingerprints=reviewed_items,
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
    "WORKBENCH_AMOUNT_REVIEW_CLASSIFICATION_CODES",
    "WORKBENCH_NO_ANOMALY_REVIEW_CLASSIFICATION",
    "WorkbenchAnomalyReviewConflict",
    "WorkbenchAnomalyReviewService",
]
