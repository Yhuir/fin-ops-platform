from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import combinations
from typing import Any

from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DISPLAY_STATE_OPEN,
    DISPLAY_STATE_PAIRED,
    MATCH_DOMAIN_FREE,
    WARNING_INVOICE_AMOUNT_MISMATCH,
    DecisionWarning,
    WorkbenchDecision,
    expand_scope_month_window,
    resolve_decision_scope_month,
)
from fin_ops_platform.services.workbench_text_normalization import evidence_tokens, matching_tokens


RULE_VERSION = "2026-05-25"
OA_ATTACHMENT_INVOICE_SOURCE_KIND = "oa_attachment_invoice"
MAX_INVOICE_COMBINATION_SIZE = 6


@dataclass(frozen=True, slots=True)
class _Row:
    row_type: str
    row_id: str
    amount: Decimal
    direction: str
    month: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _ThreeWayCandidate:
    oa: _Row
    bank: _Row
    invoices: tuple[_Row, ...]
    rule_code: str
    invoice_amount_closed: bool
    warning_codes: tuple[str, ...]
    evidence: dict[str, Any]


class WorkbenchFreeMatchingEngine:
    def generate_decisions(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        *,
        source_versions: dict[str, Any] | None = None,
    ) -> list[WorkbenchDecision]:
        window = tuple(expand_scope_month_window(scope_month))
        oa = self._normalize_rows("oa", oa_rows, window)
        bank = self._normalize_rows("bank", bank_rows, window)
        invoices = self._normalize_rows("invoice", invoice_rows, window)
        source_versions = dict(source_versions or {})

        three_way_candidates = self._three_way_candidates(oa, bank, invoices, window)
        conflicts = self._conflicted_rows(three_way_candidates)
        if conflicts:
            return self._open_decisions(scope_month, conflicts, window, source_versions)

        decisions: list[WorkbenchDecision] = []
        claimed: set[str] = set()
        for candidate in sorted(three_way_candidates, key=lambda item: self._row_ids(item)):
            row_ids = self._row_ids(candidate)
            if any(row_id in claimed for row_id in row_ids):
                continue
            decision = self._paired_three_way_decision(candidate, window, source_versions)
            decisions.append(decision)
            claimed.update(row_ids)

        if decisions:
            return decisions

        return self._two_way_decisions(scope_month, oa, bank, invoices, window, source_versions)

    def _three_way_candidates(
        self,
        oa_rows: list[_Row],
        bank_rows: list[_Row],
        invoice_rows: list[_Row],
        window: tuple[str, ...],
    ) -> list[_ThreeWayCandidate]:
        candidates: list[_ThreeWayCandidate] = []
        for oa in oa_rows:
            for bank in bank_rows:
                if oa.amount != bank.amount or not self._has_evidence(oa, bank):
                    continue
                attachment_invoices = self._attachment_invoices(oa, invoice_rows)
                if attachment_invoices:
                    candidates.append(self._attachment_candidate(oa, bank, attachment_invoices, window))
                    continue

                invoice_groups = self._invoice_groups_for_amount(
                    oa=oa,
                    bank=bank,
                    invoices=invoice_rows,
                    target_amount=oa.amount,
                )
                for invoice_group in invoice_groups:
                    candidates.append(
                        _ThreeWayCandidate(
                            oa=oa,
                            bank=bank,
                            invoices=invoice_group,
                            rule_code="oa_bank_invoice_exact_amount",
                            invoice_amount_closed=True,
                            warning_codes=(),
                            evidence=self._evidence_payload(
                                window=window,
                                oa=oa,
                                bank=bank,
                                invoices=invoice_group,
                                three_way_evidence=self._three_way_evidence_kind(oa, bank, invoice_group),
                            ),
                        )
                    )
        return candidates

    def _attachment_candidate(
        self,
        oa: _Row,
        bank: _Row,
        invoices: tuple[_Row, ...],
        window: tuple[str, ...],
    ) -> _ThreeWayCandidate:
        invoice_sum = sum((invoice.amount for invoice in invoices), Decimal("0.00"))
        invoice_amount_closed = invoice_sum == oa.amount
        warning_codes = () if invoice_amount_closed else (WARNING_INVOICE_AMOUNT_MISMATCH,)
        return _ThreeWayCandidate(
            oa=oa,
            bank=bank,
            invoices=invoices,
            rule_code="oa_attachment_invoice_with_bank",
            invoice_amount_closed=invoice_amount_closed,
            warning_codes=warning_codes,
            evidence=self._evidence_payload(
                window=window,
                oa=oa,
                bank=bank,
                invoices=invoices,
                three_way_evidence="oa_attachment_source_link",
                extra={
                    "attachment_invoice_amount": str(invoice_sum),
                    "payment_amount": str(oa.amount),
                },
            ),
        )

    def _invoice_groups_for_amount(
        self,
        *,
        oa: _Row,
        bank: _Row,
        invoices: list[_Row],
        target_amount: Decimal,
    ) -> list[tuple[_Row, ...]]:
        eligible = [
            invoice
            for invoice in invoices
            if invoice.data.get("source_kind") != OA_ATTACHMENT_INVOICE_SOURCE_KIND
            and (self._has_evidence(oa, invoice) or self._has_evidence(bank, invoice))
        ]
        groups: list[tuple[_Row, ...]] = []
        max_size = min(len(eligible), MAX_INVOICE_COMBINATION_SIZE)
        for size in range(1, max_size + 1):
            for group in combinations(eligible, size):
                if sum((invoice.amount for invoice in group), Decimal("0.00")) == target_amount:
                    groups.append(tuple(sorted(group, key=lambda row: row.row_id)))
        return groups

    def _conflicted_rows(self, candidates: list[_ThreeWayCandidate]) -> dict[str, dict[str, Any]]:
        by_oa_bank: dict[tuple[str, str], list[_ThreeWayCandidate]] = {}
        by_row: dict[str, list[_ThreeWayCandidate]] = {}
        for candidate in candidates:
            by_oa_bank.setdefault((candidate.oa.row_id, candidate.bank.row_id), []).append(candidate)
            for row_id in self._row_ids(candidate):
                by_row.setdefault(row_id, []).append(candidate)

        conflicted: dict[str, dict[str, Any]] = {}
        for pair_candidates in by_oa_bank.values():
            invoice_sets = {tuple(invoice.row_id for invoice in candidate.invoices) for candidate in pair_candidates}
            if len(invoice_sets) > 1:
                for candidate in pair_candidates:
                    self._mark_conflict(conflicted, candidate, "multiple_three_way_candidates")

        for row_candidates in by_row.values():
            candidate_keys = {self._candidate_key(candidate) for candidate in row_candidates}
            if len(candidate_keys) > 1:
                for candidate in row_candidates:
                    self._mark_conflict(conflicted, candidate, "multiple_three_way_candidates")
        return conflicted

    def _mark_conflict(
        self,
        conflicted: dict[str, dict[str, Any]],
        candidate: _ThreeWayCandidate,
        code: str,
    ) -> None:
        for row in (candidate.oa, candidate.bank, *candidate.invoices):
            entry = conflicted.setdefault(
                row.row_id,
                {
                    "row": row,
                    "blockers": [],
                },
            )
            if not any(blocker["code"] == code for blocker in entry["blockers"]):
                entry["blockers"].append(
                    {
                        "code": code,
                        "candidate_rows": list(self._row_ids(candidate)),
                    }
                )

    def _two_way_decisions(
        self,
        scope_month: str,
        oa_rows: list[_Row],
        bank_rows: list[_Row],
        invoice_rows: list[_Row],
        window: tuple[str, ...],
        source_versions: dict[str, Any],
    ) -> list[WorkbenchDecision]:
        oa_bank = self._unique_pairs(oa_rows, bank_rows)
        if oa_bank:
            return [
                self._paired_two_way_decision(
                    scope_month=scope_month,
                    left=left,
                    right=right,
                    match_shape="oa_bank",
                    rule_code="oa_bank_exact_amount",
                    window=window,
                    source_versions=source_versions,
                )
                for left, right in oa_bank
            ]

        oa_invoice = self._unique_pairs(oa_rows, invoice_rows)
        if oa_invoice:
            return [
                self._paired_two_way_decision(
                    scope_month=scope_month,
                    left=left,
                    right=right,
                    match_shape="oa_invoice",
                    rule_code="oa_invoice_exact_amount",
                    window=window,
                    source_versions=source_versions,
                )
                for left, right in oa_invoice
            ]

        bank_invoice = self._unique_pairs(bank_rows, invoice_rows)
        return [
            self._paired_two_way_decision(
                scope_month=scope_month,
                left=left,
                right=right,
                match_shape="bank_invoice",
                rule_code="bank_invoice_exact_amount",
                window=window,
                source_versions=source_versions,
            )
            for left, right in bank_invoice
        ]

    def _unique_pairs(self, left_rows: list[_Row], right_rows: list[_Row]) -> list[tuple[_Row, _Row]]:
        candidates = [
            (left, right)
            for left in left_rows
            for right in right_rows
            if left.amount == right.amount and self._has_evidence(left, right)
        ]
        left_counts: dict[str, int] = {}
        right_counts: dict[str, int] = {}
        for left, right in candidates:
            left_counts[left.row_id] = left_counts.get(left.row_id, 0) + 1
            right_counts[right.row_id] = right_counts.get(right.row_id, 0) + 1
        return [
            (left, right)
            for left, right in candidates
            if left_counts[left.row_id] == 1 and right_counts[right.row_id] == 1
        ]

    def _paired_three_way_decision(
        self,
        candidate: _ThreeWayCandidate,
        window: tuple[str, ...],
        source_versions: dict[str, Any],
    ) -> WorkbenchDecision:
        row_ids = self._row_ids(candidate)
        scope_month = resolve_decision_scope_month(
            has_bank=True,
            bank_trade_month=candidate.bank.month,
            has_oa=True,
            oa_month=candidate.oa.month,
        )
        warnings = tuple(self._warning(code, candidate) for code in candidate.warning_codes)
        return WorkbenchDecision(
            decision_id=self._decision_key(scope_month, candidate.rule_code, row_ids),
            decision_key=self._decision_key(scope_month, candidate.rule_code, row_ids),
            scope_month=scope_month,
            display_state=DISPLAY_STATE_PAIRED,
            decision_status=DECISION_STATUS_PAIRED,
            match_domain=MATCH_DOMAIN_FREE,
            match_shape="oa_bank_invoice",
            rule_code=candidate.rule_code,
            rule_version=RULE_VERSION,
            row_ids=row_ids,
            oa_row_ids=(candidate.oa.row_id,),
            bank_row_ids=(candidate.bank.row_id,),
            invoice_row_ids=tuple(invoice.row_id for invoice in candidate.invoices),
            amount=candidate.oa.amount,
            direction="expenditure",
            payment_amount_closed=True,
            invoice_amount_closed=candidate.invoice_amount_closed,
            warnings=warnings,
            evidence={**candidate.evidence, "scope_window": list(window), "uniqueness_scope": "five_month_window"},
            blockers=(),
            explanation=self._three_way_explanation(candidate),
            source_versions=source_versions,
        )

    def _paired_two_way_decision(
        self,
        *,
        scope_month: str,
        left: _Row,
        right: _Row,
        match_shape: str,
        rule_code: str,
        window: tuple[str, ...],
        source_versions: dict[str, Any],
    ) -> WorkbenchDecision:
        has_bank = left.row_type == "bank" or right.row_type == "bank"
        bank_month = left.month if left.row_type == "bank" else right.month if right.row_type == "bank" else None
        has_oa = left.row_type == "oa" or right.row_type == "oa"
        oa_month = left.month if left.row_type == "oa" else right.month if right.row_type == "oa" else None
        resolved_scope_month = resolve_decision_scope_month(
            has_bank=has_bank,
            bank_trade_month=bank_month,
            has_oa=has_oa,
            oa_month=oa_month,
        )
        row_ids = tuple(row.row_id for row in (left, right))
        return WorkbenchDecision(
            decision_id=self._decision_key(resolved_scope_month, rule_code, row_ids),
            decision_key=self._decision_key(resolved_scope_month, rule_code, row_ids),
            scope_month=resolved_scope_month,
            display_state=DISPLAY_STATE_PAIRED,
            decision_status=DECISION_STATUS_PAIRED,
            match_domain=MATCH_DOMAIN_FREE,
            match_shape=match_shape,
            rule_code=rule_code,
            rule_version=RULE_VERSION,
            row_ids=row_ids,
            oa_row_ids=tuple(row.row_id for row in (left, right) if row.row_type == "oa"),
            bank_row_ids=tuple(row.row_id for row in (left, right) if row.row_type == "bank"),
            invoice_row_ids=tuple(row.row_id for row in (left, right) if row.row_type == "invoice"),
            amount=left.amount,
            direction="expenditure",
            payment_amount_closed=True if match_shape == "oa_bank" else None,
            invoice_amount_closed=True if match_shape in {"oa_invoice", "bank_invoice"} else None,
            evidence={
                "scope_window": list(window),
                "uniqueness_scope": "five_month_window",
                "text_matches": matching_tokens(self._tokens(left), self._tokens(right)),
            },
            blockers=(),
            explanation="Two-way free matching resolved after no unique three-way match formed.",
            source_versions=source_versions,
        )

    def _open_decisions(
        self,
        scope_month: str,
        conflicted: dict[str, dict[str, Any]],
        window: tuple[str, ...],
        source_versions: dict[str, Any],
    ) -> list[WorkbenchDecision]:
        decisions: list[WorkbenchDecision] = []
        for row_id in sorted(conflicted):
            row = conflicted[row_id]["row"]
            blockers = tuple(conflicted[row_id]["blockers"])
            owner_month = row.month if row.row_type != "invoice" else scope_month
            decisions.append(
                WorkbenchDecision(
                    decision_id=self._decision_key(owner_month, "free_matching_conflict", (row.row_id,)),
                    decision_key=self._decision_key(owner_month, "free_matching_conflict", (row.row_id,)),
                    scope_month=owner_month,
                    display_state=DISPLAY_STATE_OPEN,
                    decision_status=DECISION_STATUS_OPEN,
                    match_domain=MATCH_DOMAIN_FREE,
                    match_shape="single",
                    rule_code="free_matching_conflict",
                    rule_version=RULE_VERSION,
                    row_ids=(row.row_id,),
                    oa_row_ids=(row.row_id,) if row.row_type == "oa" else (),
                    bank_row_ids=(row.row_id,) if row.row_type == "bank" else (),
                    invoice_row_ids=(row.row_id,) if row.row_type == "invoice" else (),
                    amount=row.amount,
                    direction="expenditure",
                    evidence={"scope_window": list(window), "uniqueness_scope": "five_month_window"},
                    blockers=blockers,
                    explanation="Free matching found competing candidates, so the row remains open.",
                    source_versions=source_versions,
                )
            )
        return decisions

    def _normalize_rows(self, row_type: str, rows: list[dict[str, Any]], window: tuple[str, ...]) -> list[_Row]:
        normalized: list[_Row] = []
        for row in rows:
            direction = str(row.get("direction") or "").strip().lower()
            if direction != "expenditure":
                continue
            row_id = str(row.get("row_id") or row.get("id") or "").strip()
            amount = self._amount(row.get("amount"))
            month = self._month(row_type, row)
            if not row_id or amount is None or month not in window:
                continue
            normalized.append(
                _Row(
                    row_type=row_type,
                    row_id=row_id,
                    amount=amount,
                    direction=direction,
                    month=month,
                    data=dict(row),
                )
            )
        return normalized

    def _month(self, row_type: str, row: dict[str, Any]) -> str:
        fields = {
            "oa": ("month", "oa_month", "apply_month"),
            "bank": ("trade_month", "month", "transaction_month"),
            "invoice": ("invoice_month", "month"),
        }[row_type]
        for field in fields:
            value = str(row.get(field) or "").strip()
            if len(value) >= 7:
                return value[:7]
        return ""

    def _amount(self, value: Any) -> Decimal | None:
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _has_evidence(self, left: _Row, right: _Row) -> bool:
        return bool(matching_tokens(self._tokens(left), self._tokens(right)))

    def _tokens(self, row: _Row):
        if row.row_type == "oa":
            return evidence_tokens(
                {
                    "oa.applicant": row.data.get("applicant"),
                    "oa.project": row.data.get("project_name") or row.data.get("project"),
                    "oa.reason": row.data.get("reason") or row.data.get("summary"),
                }
            )
        if row.row_type == "bank":
            return evidence_tokens(
                {
                    "bank.counterparty": row.data.get("counterparty") or row.data.get("counterparty_name"),
                    "bank.summary": row.data.get("summary"),
                    "bank.remark": row.data.get("remark"),
                }
            )
        return evidence_tokens({"invoice.seller_name": row.data.get("seller_name")})

    def _attachment_invoices(self, oa: _Row, invoices: list[_Row]) -> tuple[_Row, ...]:
        attached = [
            invoice
            for invoice in invoices
            if invoice.data.get("source_kind") == OA_ATTACHMENT_INVOICE_SOURCE_KIND
            and str(invoice.data.get("source_oa_row_id") or invoice.data.get("oa_row_id") or "").strip() == oa.row_id
        ]
        return tuple(sorted(attached, key=lambda row: row.row_id))

    def _evidence_payload(
        self,
        *,
        window: tuple[str, ...],
        oa: _Row,
        bank: _Row,
        invoices: tuple[_Row, ...],
        three_way_evidence: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        invoice_matches = [
            match
            for invoice in invoices
            for match in (
                matching_tokens(self._tokens(oa), self._tokens(invoice))
                + matching_tokens(self._tokens(bank), self._tokens(invoice))
            )
        ]
        payload = {
            "scope_window": list(window),
            "uniqueness_scope": "five_month_window",
            "three_way_evidence": three_way_evidence,
            "oa_bank_text_matches": matching_tokens(self._tokens(oa), self._tokens(bank)),
            "invoice_text_matches": invoice_matches,
        }
        if extra:
            payload.update(extra)
        return payload

    def _three_way_evidence_kind(self, oa: _Row, bank: _Row, invoices: tuple[_Row, ...]) -> str:
        has_oa_invoice = any(self._has_evidence(oa, invoice) for invoice in invoices)
        has_bank_invoice = any(self._has_evidence(bank, invoice) for invoice in invoices)
        if has_oa_invoice and has_bank_invoice:
            return "strong"
        return "bridged_by_oa"

    def _three_way_explanation(self, candidate: _ThreeWayCandidate) -> str:
        if candidate.warning_codes:
            return "OA and bank payment amounts close; OA attachment invoice amount does not close."
        if len(candidate.invoices) > 1:
            return "OA, bank and the unique invoice sum close in the five-month window."
        return "OA, bank and invoice amounts close uniquely in the five-month window."

    def _warning(self, code: str, candidate: _ThreeWayCandidate) -> DecisionWarning:
        if code == WARNING_INVOICE_AMOUNT_MISMATCH:
            invoice_sum = sum((invoice.amount for invoice in candidate.invoices), Decimal("0.00"))
            delta = candidate.oa.amount - invoice_sum
            return DecisionWarning(
                code=code,
                message=(
                    "OA 与流水金额一致，但 OA 来源附件发票合计金额不一致。"
                    f"OA 金额 {candidate.oa.amount}，流水金额 {candidate.bank.amount}，"
                    f"附件发票合计 {invoice_sum}，差额 {delta}，正式发票数量 {len(candidate.invoices)}。"
                ),
            )
        return DecisionWarning(code=code, message=code)

    def _row_ids(self, candidate: _ThreeWayCandidate) -> tuple[str, ...]:
        return (candidate.oa.row_id, candidate.bank.row_id, *(invoice.row_id for invoice in candidate.invoices))

    def _candidate_key(self, candidate: _ThreeWayCandidate) -> tuple[str, ...]:
        return (candidate.rule_code, *self._row_ids(candidate))

    def _decision_key(self, scope_month: str, rule_code: str, row_ids: tuple[str, ...]) -> str:
        return f"decision:{scope_month}:{rule_code}:{':'.join(row_ids)}"
