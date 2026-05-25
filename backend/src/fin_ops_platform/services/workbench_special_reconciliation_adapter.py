from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DISPLAY_STATE_OPEN,
    DISPLAY_STATE_PAIRED,
    MATCH_DOMAIN_SPECIAL,
    WorkbenchDecision,
)
from fin_ops_platform.services.workbench_special_pair_rule_service import (
    INTERNAL_TRANSFER_PAIR,
    OA_INVOICE_OFFSET_AUTO_MATCH,
    WORKBENCH_SPECIAL_RULES_VERSION,
    WorkbenchSpecialPairRuleService,
)


@dataclass(frozen=True, slots=True)
class WorkbenchSpecialReconciliationResult:
    decisions: tuple[WorkbenchDecision, ...]
    claimed_row_ids_by_domain: dict[str, set[str]]

    @property
    def claimed_row_ids(self) -> set[str]:
        return set(self.claimed_row_ids_by_domain.get(MATCH_DOMAIN_SPECIAL, set()))


class WorkbenchSpecialReconciliationAdapter:
    def __init__(self, *, special_rule_service: WorkbenchSpecialPairRuleService | None = None) -> None:
        self._special_rule_service = special_rule_service or WorkbenchSpecialPairRuleService()

    def generate_decisions(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        *,
        settings: dict[str, Any] | None = None,
        source_versions: dict[str, Any] | None = None,
    ) -> WorkbenchSpecialReconciliationResult:
        candidates = self._special_rule_service.generate_candidates(
            scope_month,
            oa_rows,
            bank_rows,
            invoice_rows,
            settings=settings,
            source_versions=source_versions,
        )
        return self.adapt_candidates(scope_month, candidates)

    def adapt_candidates(
        self,
        scope_month: str,
        candidates: list[dict[str, Any]],
    ) -> WorkbenchSpecialReconciliationResult:
        decisions = tuple(
            self._decision_from_candidate(scope_month, candidate)
            for candidate in candidates
            if self._row_ids(candidate)
        )
        claimed_row_ids = {
            row_id
            for decision in decisions
            for row_id in decision.row_ids
        }
        return WorkbenchSpecialReconciliationResult(
            decisions=decisions,
            claimed_row_ids_by_domain={MATCH_DOMAIN_SPECIAL: claimed_row_ids},
        )

    @staticmethod
    def exclude_claimed_free_candidates(
        candidates: list[dict[str, Any]],
        *,
        claimed_row_ids: set[str],
    ) -> list[dict[str, Any]]:
        claims = {str(row_id or "").strip() for row_id in claimed_row_ids if str(row_id or "").strip()}
        if not claims:
            return list(candidates)
        return [
            deepcopy(candidate)
            for candidate in candidates
            if not claims.intersection(WorkbenchSpecialReconciliationAdapter._row_ids(candidate))
        ]

    def _decision_from_candidate(self, scope_month: str, candidate: dict[str, Any]) -> WorkbenchDecision:
        row_ids = self._row_ids(candidate)
        oa_row_ids = self._typed_row_ids(candidate, "oa_row_ids")
        bank_row_ids = self._typed_row_ids(candidate, "bank_row_ids")
        invoice_row_ids = self._typed_row_ids(candidate, "invoice_row_ids")
        rule_code = self._required_text(candidate.get("rule_code"), "rule_code")
        display_state, decision_status = self._display_contract(candidate)
        match_shape = self._match_shape(oa_row_ids, bank_row_ids, invoice_row_ids)
        decision_key = self._decision_key(scope_month, rule_code, row_ids)
        payment_amount_closed, invoice_amount_closed = self._amount_closure(match_shape, decision_status)
        return WorkbenchDecision(
            decision_id=decision_key,
            decision_key=decision_key,
            scope_month=scope_month,
            display_state=display_state,
            decision_status=decision_status,
            match_domain=MATCH_DOMAIN_SPECIAL,
            match_shape=match_shape,
            rule_code=rule_code,
            rule_version=WORKBENCH_SPECIAL_RULES_VERSION,
            row_ids=row_ids,
            oa_row_ids=oa_row_ids,
            bank_row_ids=bank_row_ids,
            invoice_row_ids=invoice_row_ids,
            amount=candidate.get("amount"),
            direction=self._direction(candidate),
            payment_amount_closed=payment_amount_closed,
            invoice_amount_closed=invoice_amount_closed,
            evidence=self._evidence(candidate),
            blockers=self._blockers(candidate, decision_status),
            explanation=str(candidate.get("explanation") or "").strip(),
            source_versions=deepcopy(candidate.get("source_versions") if isinstance(candidate.get("source_versions"), dict) else {}),
        )

    @staticmethod
    def _display_contract(candidate: dict[str, Any]) -> tuple[str, str]:
        if str(candidate.get("status") or "").strip() == "auto_closed":
            return DISPLAY_STATE_PAIRED, DECISION_STATUS_PAIRED
        rule_code = str(candidate.get("rule_code") or "").strip()
        special_metadata = candidate.get("special_metadata") if isinstance(candidate.get("special_metadata"), dict) else {}
        cost_policy = str(special_metadata.get("cost_policy") or "").strip()
        if rule_code == INTERNAL_TRANSFER_PAIR and cost_policy == "exclude_all":
            return DISPLAY_STATE_PAIRED, DECISION_STATUS_PAIRED
        if rule_code == OA_INVOICE_OFFSET_AUTO_MATCH and cost_policy == "exclude_all":
            return DISPLAY_STATE_PAIRED, DECISION_STATUS_PAIRED
        return DISPLAY_STATE_OPEN, DECISION_STATUS_OPEN

    @staticmethod
    def _match_shape(
        oa_row_ids: tuple[str, ...],
        bank_row_ids: tuple[str, ...],
        invoice_row_ids: tuple[str, ...],
    ) -> str:
        parts: list[str] = []
        if oa_row_ids:
            parts.append("oa")
        if bank_row_ids:
            parts.append("bank_bank" if len(bank_row_ids) > 1 and not oa_row_ids and not invoice_row_ids else "bank")
        if invoice_row_ids:
            parts.append("invoice")
        if not parts:
            return "single"
        if parts == ["bank_bank"]:
            return "bank_bank"
        return "_".join(parts) if len(parts) > 1 else "single"

    @staticmethod
    def _amount_closure(match_shape: str, decision_status: str) -> tuple[bool | None, bool | None]:
        if decision_status != DECISION_STATUS_PAIRED:
            return None, None
        if match_shape == "bank_bank":
            return True, None
        if match_shape == "oa_invoice":
            return None, True
        if match_shape == "oa_bank":
            return True, None
        if match_shape == "bank_invoice":
            return True, True
        if match_shape == "oa_bank_invoice":
            return True, True
        return None, None

    @staticmethod
    def _evidence(candidate: dict[str, Any]) -> dict[str, Any]:
        evidence: dict[str, Any] = {}
        special_metadata = candidate.get("special_metadata")
        if isinstance(special_metadata, dict):
            evidence["special_metadata"] = deepcopy(special_metadata)
        for key in ("confidence", "tags", "amount_delta", "conflict_candidate_keys"):
            if key in candidate:
                evidence[key] = deepcopy(candidate.get(key))
        return evidence

    @staticmethod
    def _blockers(candidate: dict[str, Any], decision_status: str) -> tuple[dict[str, Any], ...]:
        if decision_status == DECISION_STATUS_PAIRED:
            return ()
        status = str(candidate.get("status") or "").strip()
        special_metadata = candidate.get("special_metadata") if isinstance(candidate.get("special_metadata"), dict) else {}
        cost_policy = str(special_metadata.get("cost_policy") or "").strip()
        if status == "needs_review" or cost_policy == "hint_only":
            return ({"code": "hint_only_special_rule", "status": status, "cost_policy": cost_policy},)
        if status:
            return ({"code": "non_projected_special_rule", "status": status},)
        return ()

    @staticmethod
    def _direction(candidate: dict[str, Any]) -> str:
        special_metadata = candidate.get("special_metadata") if isinstance(candidate.get("special_metadata"), dict) else {}
        evidence = special_metadata.get("evidence") if isinstance(special_metadata.get("evidence"), dict) else {}
        return str(evidence.get("direction") or "").strip()

    @staticmethod
    def _decision_key(scope_month: str, rule_code: str, row_ids: tuple[str, ...]) -> str:
        return f"workbench:special:{scope_month}:{rule_code}:{'|'.join(row_ids)}"

    @staticmethod
    def _row_ids(candidate: dict[str, Any]) -> tuple[str, ...]:
        return tuple(sorted(str(row_id or "").strip() for row_id in list(candidate.get("row_ids") or []) if str(row_id or "").strip()))

    @staticmethod
    def _typed_row_ids(candidate: dict[str, Any], field_name: str) -> tuple[str, ...]:
        return tuple(sorted(str(row_id or "").strip() for row_id in list(candidate.get(field_name) or []) if str(row_id or "").strip()))

    @staticmethod
    def _required_text(value: Any, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field_name} is required.")
        return text
