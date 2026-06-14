from __future__ import annotations

from typing import Any

from fin_ops_platform.services.workbench_free_matching_engine import (
    OA_BANK_SUM_MIN_EVIDENCE_TOKEN_LENGTH,
    OA_BANK_SUM_WEAK_TOKENS,
)
from fin_ops_platform.services.workbench_text_normalization import normalize_match_text


ACTIVE_DECISION_STATUSES = {"proposed", "paired", "open"}
OA_BANK_EXACT_SUM_RULE_CODE = "oa_bank_exact_sum"
OA_BANK_SUM_NON_BUSINESS_OA_SOURCE_FIELDS = frozenset(
    {
        "applicant",
        "oa.applicant",
        "project",
        "oa.project",
    }
)


class WorkbenchReconciliationDecisionCleanupService:
    def __init__(self, *, repository: Any, tenant_id: str = "default") -> None:
        self._repository = repository
        self._tenant_id = str(tenant_id or "default").strip() or "default"

    def build_plan(
        self,
        *,
        scope_months: list[str] | None = None,
        decision_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        decisions = self._repository.list_active_workbench_reconciliation_decisions_for_cleanup(
            tenant_id=self._tenant_id,
            scope_months=list(scope_months or []),
            decision_keys=list(decision_keys or []),
        )
        items = [item for decision in decisions if (item := self._plan_item(decision)) is not None]
        affected_scopes = sorted({str(item.get("scope_month") or "") for item in items if str(item.get("scope_month") or "")})
        return {
            "tenant_id": self._tenant_id,
            "decision_count": len(decisions),
            "invalid_decision_count": len(items),
            "affected_scope_keys": affected_scopes,
            "items": items,
            "recommended_rebuild_scopes": [*affected_scopes, "all"] if affected_scopes else [],
        }

    def execute_plan(self, plan: dict[str, Any], *, reason: str) -> dict[str, Any]:
        items = list(plan.get("items") if isinstance(plan.get("items"), list) else [])
        decision_keys = [
            str(item.get("decision_key") or "").strip()
            for item in items
            if isinstance(item, dict) and str(item.get("decision_key") or "").strip()
        ]
        result = self._repository.expire_workbench_reconciliation_decisions_by_keys(
            tenant_id=self._tenant_id,
            decision_keys=decision_keys,
            reason=str(reason or "invalid_workbench_reconciliation_decision").strip()
            or "invalid_workbench_reconciliation_decision",
        )
        return {
            "tenant_id": self._tenant_id,
            "requested_decision_count": len(decision_keys),
            "expired_count": int(result.get("expired_count") or 0) if isinstance(result, dict) else 0,
            "affected_scope_keys": list(result.get("scope_keys") or []) if isinstance(result, dict) else [],
            "recommended_rebuild_scopes": [
                *list(result.get("scope_keys") or []),
                "all",
            ]
            if isinstance(result, dict) and result.get("scope_keys")
            else [],
        }

    def _plan_item(self, decision: dict[str, Any]) -> dict[str, Any] | None:
        if str(decision.get("decision_status") or "") not in ACTIVE_DECISION_STATUSES:
            return None
        reasons: list[dict[str, Any]] = []
        active_relation_overlaps = decision.get("active_relation_overlaps")
        if isinstance(active_relation_overlaps, list) and active_relation_overlaps:
            reasons.append(
                {
                    "code": "active_relation_row_overlap",
                    "message": "Decision reuses rows already owned by active workbench pair relations in the matching window.",
                    "active_relation_overlaps": active_relation_overlaps,
                }
            )
        submitted_no_oa_batch_overlaps = decision.get("submitted_no_oa_batch_overlaps")
        if isinstance(submitted_no_oa_batch_overlaps, list) and submitted_no_oa_batch_overlaps:
            reasons.append(
                {
                    "code": "submitted_no_oa_batch_row_overlap",
                    "message": "Decision reuses bank rows already closed by submitted no-OA bank batches.",
                    "submitted_no_oa_batch_overlaps": submitted_no_oa_batch_overlaps,
                }
            )
        if self._has_weak_only_oa_bank_sum_evidence(decision):
            reasons.append(
                {
                    "code": "weak_only_oa_bank_sum_evidence",
                    "message": "oa_bank_exact_sum is supported only by weak/generic text tokens.",
                }
            )
        if not reasons:
            return None
        return {
            "decision_key": str(decision.get("decision_key") or ""),
            "scope_month": str(decision.get("scope_month") or ""),
            "rule_code": str(decision.get("rule_code") or ""),
            "decision_status": str(decision.get("decision_status") or ""),
            "row_ids": list(decision.get("row_ids") or []),
            "oa_row_ids": list(decision.get("oa_row_ids") or []),
            "bank_row_ids": list(decision.get("bank_row_ids") or []),
            "invoice_row_ids": list(decision.get("invoice_row_ids") or []),
            "reasons": reasons,
            "planned_action": "expire",
        }

    @classmethod
    def _has_weak_only_oa_bank_sum_evidence(cls, decision: dict[str, Any]) -> bool:
        if str(decision.get("rule_code") or "") != OA_BANK_EXACT_SUM_RULE_CODE:
            return False
        evidence = decision.get("evidence")
        if not isinstance(evidence, dict):
            return False
        evidence_groups = evidence.get("oa_bank_text_matches")
        if not isinstance(evidence_groups, list):
            return False
        matches: list[dict[str, Any]] = []
        for group in evidence_groups:
            if not isinstance(group, dict):
                continue
            group_matches = group.get("matches")
            if isinstance(group_matches, list):
                matches.extend(match for match in group_matches if isinstance(match, dict))
        return bool(matches) and not any(cls._is_strong_oa_bank_sum_match(match) for match in matches)

    @staticmethod
    def _is_strong_oa_bank_sum_match(match: dict[str, Any]) -> bool:
        token = normalize_match_text(match.get("token"))
        left_source_field = str(match.get("left_source_field") or "").strip().lower()
        if left_source_field in OA_BANK_SUM_NON_BUSINESS_OA_SOURCE_FIELDS:
            return False
        return len(token) >= OA_BANK_SUM_MIN_EVIDENCE_TOKEN_LENGTH and token not in OA_BANK_SUM_WEAK_TOKENS
