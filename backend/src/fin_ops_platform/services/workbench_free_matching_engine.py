from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_linking import oa_attachment_matches_oa
from fin_ops_platform.services.workbench_invoice_direction import invoice_workbench_direction_from_row
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
from fin_ops_platform.services.workbench_scheduled_payment_evidence import (
    scheduled_payment_date_compatible,
    scheduled_payment_date_match,
)
from fin_ops_platform.services.workbench_text_normalization import evidence_tokens, matching_tokens, normalize_match_text


RULE_VERSION = "2026-06-23-invoice-direction-normalization-v1"
OA_ATTACHMENT_INVOICE_SOURCE_KIND = "oa_attachment_invoice"
MATCHABLE_DIRECTIONS = {"expenditure", "income"}
MAX_INVOICE_COMBINATION_SIZE = 6
MAX_PAYMENT_PAIR_COMBINATION_SIZE = 6
MAX_SUBSET_GROUP_RESULTS = 2
MAX_SUBSET_SEARCH_STATES = 20000
OA_BANK_SUM_MIN_EVIDENCE_TOKEN_LENGTH = 4
OA_BANK_SUM_WEAK_TOKENS = frozenset({"科技"})


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
    oas: tuple[_Row, ...]
    banks: tuple[_Row, ...]
    invoices: tuple[_Row, ...]
    rule_code: str
    invoice_amount_closed: bool
    warning_codes: tuple[str, ...]
    evidence: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _BankInvoiceCandidate:
    bank: _Row
    invoice: _Row
    subject_evidence: list[dict[str, Any]]
    supporting_evidence: list[dict[str, Any]]
    score: int
    date_distance_days: int | None


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

        decisions: list[WorkbenchDecision] = []
        conflict_row_ids = set(conflicts)
        if conflicts:
            decisions.extend(self._open_decisions(scope_month, conflicts, window, source_versions))
        claimed: set[str] = set(conflict_row_ids)
        for candidate in sorted(three_way_candidates, key=lambda item: self._row_ids(item)):
            row_ids = self._row_ids(candidate)
            if any(row_id in claimed for row_id in row_ids):
                continue
            decision = self._paired_three_way_decision(candidate, window, source_versions)
            decisions.append(decision)
            claimed.update(row_ids)

        decisions.extend(self._two_way_decisions(scope_month, oa, bank, invoices, window, source_versions, claimed))
        return [decision for decision in decisions if decision.scope_month == scope_month]

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
                if oa.direction != bank.direction:
                    continue
                if oa.amount != bank.amount or not self._has_pair_evidence(oa, bank, "oa_bank"):
                    continue
                if not self._oa_bank_scheduled_payment_date_compatible(oa, bank):
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
                            oas=(oa,),
                            banks=(bank,),
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
        candidates.extend(self._oa_bank_pair_groups_for_single_invoice(oa_rows, bank_rows, invoice_rows, window))
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
            oas=(oa,),
            banks=(bank,),
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

    def _oa_bank_pair_groups_for_single_invoice(
        self,
        oa_rows: list[_Row],
        bank_rows: list[_Row],
        invoice_rows: list[_Row],
        window: tuple[str, ...],
    ) -> list[_ThreeWayCandidate]:
        exact_pairs = [
            (oa, bank)
            for oa, bank in self._unique_pairs(oa_rows, bank_rows, "oa_bank")
            if oa.amount == bank.amount
        ]
        candidates: list[_ThreeWayCandidate] = []
        for invoice in sorted(invoice_rows, key=lambda row: row.row_id):
            if invoice.data.get("source_kind") == OA_ATTACHMENT_INVOICE_SOURCE_KIND:
                continue
            compatible_pairs = [
                pair
                for pair in exact_pairs
                if pair[0].direction == invoice.direction
                and (
                    self._has_pair_evidence(pair[0], invoice, "oa_invoice")
                    or self._has_pair_evidence(pair[1], invoice, "bank_invoice")
                )
            ]
            pair_groups = self._subset_groups_by_amount(
                compatible_pairs,
                target_amount=invoice.amount,
                max_size=MAX_PAYMENT_PAIR_COMBINATION_SIZE,
                amount_getter=lambda pair: pair[0].amount,
            )
            for pair_group in pair_groups:
                if len(pair_group) < 2:
                    continue
                bank_total = sum((pair[1].amount for pair in pair_group), Decimal("0.00"))
                if bank_total != invoice.amount:
                    continue
                sorted_pairs = tuple(sorted(pair_group, key=lambda pair: (pair[0].row_id, pair[1].row_id)))
                oas = tuple(pair[0] for pair in sorted_pairs)
                banks = tuple(pair[1] for pair in sorted_pairs)
                invoices = (invoice,)
                candidates.append(
                    _ThreeWayCandidate(
                        oas=oas,
                        banks=banks,
                        invoices=invoices,
                        rule_code="oa_bank_pairs_single_invoice_exact_sum",
                        invoice_amount_closed=True,
                        warning_codes=(),
                        evidence=self._multi_payment_single_invoice_evidence(
                            window=window,
                            oas=oas,
                            banks=banks,
                            invoice=invoice,
                        ),
                    )
                )
        return candidates

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
            if invoice.direction == bank.direction
            and invoice.data.get("source_kind") != OA_ATTACHMENT_INVOICE_SOURCE_KIND
            and (
                self._has_pair_evidence(oa, invoice, "oa_invoice")
                or self._has_pair_evidence(bank, invoice, "bank_invoice")
            )
        ]
        exact_single_invoices = [
            invoice
            for invoice in eligible
            if invoice.amount == target_amount
        ]
        if exact_single_invoices:
            return [
                (invoice,)
                for invoice in sorted(exact_single_invoices, key=lambda row: row.row_id)
            ]
        return [
            tuple(sorted(group, key=lambda row: row.row_id))
            for group in self._subset_groups_by_amount(
                eligible,
                target_amount=target_amount,
                max_size=MAX_INVOICE_COMBINATION_SIZE,
                amount_getter=lambda invoice: invoice.amount,
            )
            if len(group) >= 2
        ]

    def _subset_groups_by_amount(
        self,
        items: list[Any],
        *,
        target_amount: Decimal,
        max_size: int,
        amount_getter,
    ) -> list[tuple[Any, ...]]:
        target_cents = self._amount_cents(target_amount)
        if target_cents <= 0:
            return []
        eligible = [
            item
            for item in items
            if 0 < self._amount_cents(amount_getter(item)) <= target_cents
        ]
        if not eligible:
            return []

        resolved_max_size = max(1, min(len(eligible), int(max_size)))
        groups_by_state: dict[tuple[int, int], list[tuple[int, ...]]] = {(0, 0): [()]}
        target_groups: list[tuple[int, ...]] = []
        for index, item in enumerate(eligible):
            amount_cents = self._amount_cents(amount_getter(item))
            additions: dict[tuple[int, int], list[tuple[int, ...]]] = {}
            for (count, total), groups in list(groups_by_state.items()):
                if count >= resolved_max_size:
                    continue
                next_count = count + 1
                next_total = total + amount_cents
                if next_total > target_cents:
                    continue
                state = (next_count, next_total)
                for group in groups:
                    next_group = (*group, index)
                    if next_total == target_cents:
                        target_groups.append(next_group)
                        if len(target_groups) >= MAX_SUBSET_GROUP_RESULTS:
                            return [
                                tuple(eligible[group_index] for group_index in result)
                                for result in target_groups[:MAX_SUBSET_GROUP_RESULTS]
                            ]
                    bucket = additions.setdefault(state, [])
                    if len(bucket) < MAX_SUBSET_GROUP_RESULTS:
                        bucket.append(next_group)
            for state, groups in additions.items():
                bucket = groups_by_state.setdefault(state, [])
                for group in groups:
                    if group not in bucket and len(bucket) < MAX_SUBSET_GROUP_RESULTS:
                        bucket.append(group)
            if len(groups_by_state) > MAX_SUBSET_SEARCH_STATES:
                return []

        return [
            tuple(eligible[group_index] for group_index in result)
            for result in target_groups[:MAX_SUBSET_GROUP_RESULTS]
        ]

    def _conflicted_rows(self, candidates: list[_ThreeWayCandidate]) -> dict[str, dict[str, Any]]:
        by_oa_bank: dict[tuple[str, str], list[_ThreeWayCandidate]] = {}
        by_payment_rows: dict[tuple[str, ...], list[_ThreeWayCandidate]] = {}
        by_row: dict[str, list[_ThreeWayCandidate]] = {}
        for candidate in candidates:
            if len(candidate.oas) == 1 and len(candidate.banks) == 1:
                by_oa_bank.setdefault((candidate.oas[0].row_id, candidate.banks[0].row_id), []).append(candidate)
            by_payment_rows.setdefault(self._payment_row_ids(candidate), []).append(candidate)
            for row_id in self._row_ids(candidate):
                by_row.setdefault(row_id, []).append(candidate)

        conflicted: dict[str, dict[str, Any]] = {}
        for pair_candidates in by_oa_bank.values():
            invoice_sets = {tuple(invoice.row_id for invoice in candidate.invoices) for candidate in pair_candidates}
            if len(invoice_sets) > 1:
                for candidate in pair_candidates:
                    self._mark_conflict(conflicted, candidate, "multiple_three_way_candidates")

        for payment_candidates in by_payment_rows.values():
            invoice_sets = {tuple(invoice.row_id for invoice in candidate.invoices) for candidate in payment_candidates}
            if len(invoice_sets) > 1:
                for candidate in payment_candidates:
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
        for row in (*candidate.oas, *candidate.banks, *candidate.invoices):
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
        claimed_row_ids: set[str] | None = None,
    ) -> list[WorkbenchDecision]:
        claimed = set(claimed_row_ids or set())
        decisions: list[WorkbenchDecision] = []
        pair_specs = (
            (oa_rows, bank_rows, "oa_bank", "oa_bank_exact_amount"),
            (oa_rows, invoice_rows, "oa_invoice", "oa_invoice_exact_amount"),
        )
        for left_rows, right_rows, match_shape, rule_code in pair_specs:
            available_left = [row for row in left_rows if row.row_id not in claimed]
            available_right = [row for row in right_rows if row.row_id not in claimed]
            candidate_pairs = self._pair_candidates(available_left, available_right, match_shape)
            pairs = sorted(self._mutual_unique_pairs(candidate_pairs), key=lambda pair: (pair[0].row_id, pair[1].row_id))
            conflicted = self._conflicted_two_way_rows(candidate_pairs, pairs, rule_code)
            if conflicted:
                decisions.extend(self._open_decisions(scope_month, conflicted, window, source_versions))
                claimed.update(conflicted.keys())
            for left, right in pairs:
                if left.row_id in claimed or right.row_id in claimed:
                    continue
                decisions.append(
                    self._paired_two_way_decision(
                        scope_month=scope_month,
                        left=left,
                        right=right,
                        match_shape=match_shape,
                        rule_code=rule_code,
                        window=window,
                        source_versions=source_versions,
                    )
                )
                claimed.update((left.row_id, right.row_id))
            if match_shape == "oa_bank":
                decisions.extend(
                    self._oa_bank_exact_sum_decisions(
                        oa_rows,
                        bank_rows,
                        window,
                        source_versions,
                        claimed,
                    )
                )
        decisions.extend(self._bank_invoice_decisions(scope_month, bank_rows, invoice_rows, window, source_versions, claimed))
        return decisions

    def _oa_bank_exact_sum_decisions(
        self,
        oa_rows: list[_Row],
        bank_rows: list[_Row],
        window: tuple[str, ...],
        source_versions: dict[str, Any],
        claimed_row_ids: set[str],
    ) -> list[WorkbenchDecision]:
        proposals: list[tuple[_Row, tuple[_Row, ...]]] = []
        for oa in sorted(oa_rows, key=lambda row: row.row_id):
            if oa.row_id in claimed_row_ids or oa.amount <= Decimal("0.00"):
                continue
            eligible_banks = [
                bank
                for bank in sorted(bank_rows, key=lambda row: row.row_id)
                if bank.row_id not in claimed_row_ids
                and bank.direction == oa.direction
                and Decimal("0.00") < bank.amount <= oa.amount
                and self._has_oa_bank_sum_evidence(oa, bank)
            ]
            bank_groups = [
                tuple(sorted(group, key=lambda row: row.row_id))
                for group in self._subset_groups_by_amount(
                    eligible_banks,
                    target_amount=oa.amount,
                    max_size=MAX_PAYMENT_PAIR_COMBINATION_SIZE,
                    amount_getter=lambda bank: bank.amount,
                )
                if len(group) >= 2
            ]
            if len(bank_groups) == 1:
                proposals.append((oa, bank_groups[0]))

        if not proposals:
            return []

        oa_counts: dict[str, int] = {}
        bank_counts: dict[str, int] = {}
        for oa, banks in proposals:
            oa_counts[oa.row_id] = oa_counts.get(oa.row_id, 0) + 1
            for bank in banks:
                bank_counts[bank.row_id] = bank_counts.get(bank.row_id, 0) + 1

        decisions: list[WorkbenchDecision] = []
        for oa, banks in sorted(proposals, key=lambda item: (item[0].row_id, tuple(bank.row_id for bank in item[1]))):
            row_ids = (oa.row_id, *(bank.row_id for bank in banks))
            if any(row_id in claimed_row_ids for row_id in row_ids):
                continue
            if oa_counts.get(oa.row_id, 0) != 1:
                continue
            if any(bank_counts.get(bank.row_id, 0) != 1 for bank in banks):
                continue
            decisions.append(
                self._paired_oa_bank_exact_sum_decision(
                    oa=oa,
                    banks=banks,
                    window=window,
                    source_versions=source_versions,
                )
            )
            claimed_row_ids.update(row_ids)
        return decisions

    def _paired_oa_bank_exact_sum_decision(
        self,
        *,
        oa: _Row,
        banks: tuple[_Row, ...],
        window: tuple[str, ...],
        source_versions: dict[str, Any],
    ) -> WorkbenchDecision:
        row_ids = (oa.row_id, *(bank.row_id for bank in banks))
        first_bank = banks[0]
        resolved_scope_month = resolve_decision_scope_month(
            has_bank=True,
            bank_trade_month=first_bank.month,
            has_oa=True,
            oa_month=oa.month,
        )
        bank_total = sum((bank.amount for bank in banks), Decimal("0.00"))
        return WorkbenchDecision(
            decision_id=self._decision_key(resolved_scope_month, "oa_bank_exact_sum", row_ids),
            decision_key=self._decision_key(resolved_scope_month, "oa_bank_exact_sum", row_ids),
            scope_month=resolved_scope_month,
            display_state=DISPLAY_STATE_PAIRED,
            decision_status=DECISION_STATUS_PAIRED,
            match_domain=MATCH_DOMAIN_FREE,
            match_shape="oa_bank",
            rule_code="oa_bank_exact_sum",
            rule_version=RULE_VERSION,
            row_ids=row_ids,
            oa_row_ids=(oa.row_id,),
            bank_row_ids=tuple(bank.row_id for bank in banks),
            invoice_row_ids=(),
            amount=bank_total,
            direction=first_bank.direction,
            payment_amount_closed=True,
            invoice_amount_closed=None,
            warnings=(),
            evidence={
                "scope_window": list(window),
                "uniqueness_scope": "five_month_window",
                "amount_relation": "bank_sum_exact_amount",
                "target_amount": str(oa.amount),
                "bank_total": str(bank_total),
                "bank_count": len(banks),
                "oa_bank_text_matches": [
                    {
                        "bank_row_id": bank.row_id,
                        "matches": matching_tokens(self._tokens(oa), self._tokens(bank)),
                    }
                    for bank in banks
                ],
            },
            blockers=(),
            explanation="OA amount equals the unique sum of multiple bank transactions in the five-month window.",
            source_versions=source_versions,
        )

    def _bank_invoice_decisions(
        self,
        scope_month: str,
        bank_rows: list[_Row],
        invoice_rows: list[_Row],
        window: tuple[str, ...],
        source_versions: dict[str, Any],
        claimed_row_ids: set[str],
    ) -> list[WorkbenchDecision]:
        decisions: list[WorkbenchDecision] = []
        claimed = claimed_row_ids
        for bank in sorted(bank_rows, key=lambda row: row.row_id):
            if bank.row_id in claimed:
                continue
            candidates = [
                candidate
                for invoice in sorted(invoice_rows, key=lambda row: row.row_id)
                if invoice.row_id not in claimed
                for candidate in self._bank_invoice_candidate(bank, invoice)
            ]
            if not candidates:
                continue

            sum_eligible = [candidate for candidate in candidates if candidate.invoice.amount < bank.amount]
            sum_groups = [
                tuple(sorted(group, key=lambda candidate: candidate.invoice.row_id))
                for group in self._subset_groups_by_amount(
                    sum_eligible,
                    target_amount=bank.amount,
                    max_size=MAX_INVOICE_COMBINATION_SIZE,
                    amount_getter=lambda candidate: candidate.invoice.amount,
                )
                if len(group) >= 2
            ]
            if len(sum_groups) == 1:
                group = sum_groups[0]
                decision = self._paired_bank_invoice_sum_decision(
                    bank=bank,
                    candidates=group,
                    window=window,
                    source_versions=source_versions,
                )
                decisions.append(decision)
                claimed.update(decision.row_ids)
                continue
            if len(sum_groups) > 1:
                decision = self._open_bank_invoice_conflict_decision(
                    bank=bank,
                    candidates=tuple(candidate for group in sum_groups for candidate in group),
                    window=window,
                    source_versions=source_versions,
                    blocker_code="multiple_bank_invoice_sum_candidates",
                    amount_relation="invoice_sum_exact_amount",
                    candidate_groups=[
                        [bank.row_id, *(candidate.invoice.row_id for candidate in group)]
                        for group in sum_groups
                    ],
                    reason="Multiple invoice combinations sum exactly to the bank transaction amount.",
                )
                decisions.append(decision)
                claimed.update(decision.row_ids)
                continue

            exact_candidates = [candidate for candidate in candidates if candidate.invoice.amount == bank.amount]
            if not exact_candidates:
                continue
            scored_candidates = self._with_unique_date_score(exact_candidates)
            if len(scored_candidates) == 1:
                decision = self._paired_bank_invoice_single_decision(
                    candidate=scored_candidates[0],
                    window=window,
                    source_versions=source_versions,
                )
                decisions.append(decision)
                claimed.update(decision.row_ids)
                continue

            best_score = max(candidate.score for candidate in scored_candidates)
            best_candidates = [candidate for candidate in scored_candidates if candidate.score == best_score]
            if len(best_candidates) == 1:
                decision = self._paired_bank_invoice_single_decision(
                    candidate=best_candidates[0],
                    window=window,
                    source_versions=source_versions,
                    candidate_scores=self._candidate_score_payload(scored_candidates),
                )
                decisions.append(decision)
                claimed.update(decision.row_ids)
                continue

            decision = self._open_bank_invoice_conflict_decision(
                bank=bank,
                candidates=tuple(scored_candidates),
                window=window,
                source_versions=source_versions,
                blocker_code="same_score_bank_invoice_candidates",
                amount_relation="single_exact_amount",
                candidate_groups=[[bank.row_id, candidate.invoice.row_id] for candidate in scored_candidates],
                reason="Multiple same-amount invoices have the same strongest evidence score.",
            )
            decisions.append(decision)
            claimed.update(decision.row_ids)
        return decisions

    def _bank_invoice_candidate(self, bank: _Row, invoice: _Row) -> list[_BankInvoiceCandidate]:
        if bank.row_type != "bank" or invoice.row_type != "invoice":
            return []
        if bank.direction != invoice.direction:
            return []
        if invoice.data.get("source_kind") == OA_ATTACHMENT_INVOICE_SOURCE_KIND:
            return []
        if invoice.amount <= Decimal("0.00") or invoice.amount > bank.amount:
            return []
        subject_evidence = self._bank_invoice_subject_evidence(bank, invoice)
        if not subject_evidence:
            return []
        supporting_evidence = self._bank_invoice_supporting_evidence(bank, invoice)
        score = self._bank_invoice_score(subject_evidence, supporting_evidence)
        return [
            _BankInvoiceCandidate(
                bank=bank,
                invoice=invoice,
                subject_evidence=subject_evidence,
                supporting_evidence=supporting_evidence,
                score=score,
                date_distance_days=self._date_distance_days(bank, invoice),
            )
        ]

    def _bank_invoice_subject_evidence(self, bank: _Row, invoice: _Row) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        bank_tax_values = self._normalized_field_values(
            {
                "bank.counterparty_tax_no": bank.data.get("counterparty_tax_no"),
            }
        )
        invoice_tax_values = self._normalized_field_values(self._invoice_tax_fields(invoice))
        for bank_field, bank_value in bank_tax_values:
            for invoice_field, invoice_value in invoice_tax_values:
                if bank_value and bank_value == invoice_value:
                    evidence.append(
                        {
                            "kind": "tax_no",
                            "bank_field": bank_field,
                            "invoice_field": invoice_field,
                            "token": bank_value,
                        }
                    )

        bank_name_tokens = self._bank_counterparty_tokens(bank)
        invoice_name_tokens = self._invoice_name_tokens(invoice)
        for match in matching_tokens(bank_name_tokens, invoice_name_tokens):
            kind = "name_exact" if self._is_exact_name_match(match, bank_name_tokens, invoice_name_tokens) else "name_partial"
            evidence.append(
                {
                    "kind": kind,
                    "bank_field": match["left_source_field"],
                    "invoice_field": match["right_source_field"],
                    "token": match["token"],
                }
            )
        return self._dedupe_evidence(evidence)

    def _bank_invoice_supporting_evidence(self, bank: _Row, invoice: _Row) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        bank_text_tokens = self._bank_text_tokens(bank)
        for match in matching_tokens(bank_text_tokens, self._invoice_identity_tokens(invoice)):
            if not self._is_full_invoice_identity_match(match, invoice):
                continue
            evidence.append(
                {
                    "kind": "invoice_number",
                    "bank_field": match["left_source_field"],
                    "invoice_field": match["right_source_field"],
                    "token": match["token"],
                }
            )
        for match in matching_tokens(bank_text_tokens, self._invoice_business_reference_tokens(invoice)):
            evidence.append(
                {
                    "kind": "business_reference",
                    "bank_field": match["left_source_field"],
                    "invoice_field": match["right_source_field"],
                    "token": match["token"],
                }
            )
        for match in matching_tokens(bank_text_tokens, self._invoice_name_tokens(invoice)):
            evidence.append(
                {
                    "kind": "buyer_name_in_bank_text" if invoice.direction == "income" else "seller_name_in_bank_text",
                    "bank_field": match["left_source_field"],
                    "invoice_field": match["right_source_field"],
                    "token": match["token"],
                }
            )
        return self._dedupe_evidence(evidence)

    @staticmethod
    def _bank_invoice_score(subject_evidence: list[dict[str, Any]], supporting_evidence: list[dict[str, Any]]) -> int:
        score = 0
        if any(item["kind"] == "tax_no" for item in subject_evidence):
            score += 100
        if any(item["kind"] == "invoice_number" for item in supporting_evidence):
            score += 80
        if any(item["kind"] == "business_reference" for item in supporting_evidence):
            score += 60
        if any(item["kind"] == "name_exact" for item in subject_evidence):
            score += 50
        if any(item["kind"] in {"buyer_name_in_bank_text", "seller_name_in_bank_text"} for item in supporting_evidence):
            score += 20
        return score

    def _with_unique_date_score(self, candidates: list[_BankInvoiceCandidate]) -> list[_BankInvoiceCandidate]:
        distances = [candidate.date_distance_days for candidate in candidates if candidate.date_distance_days is not None]
        if not distances:
            return candidates
        min_distance = min(distances)
        if sum(1 for candidate in candidates if candidate.date_distance_days == min_distance) != 1:
            return candidates
        return [
            replace(
                candidate,
                score=candidate.score + 10,
                supporting_evidence=[
                    *candidate.supporting_evidence,
                    {
                        "kind": "date_proximity",
                        "distance_days": candidate.date_distance_days,
                    },
                ],
            )
            if candidate.date_distance_days == min_distance
            else candidate
            for candidate in candidates
        ]

    def _paired_bank_invoice_single_decision(
        self,
        *,
        candidate: _BankInvoiceCandidate,
        window: tuple[str, ...],
        source_versions: dict[str, Any],
        candidate_scores: list[dict[str, Any]] | None = None,
    ) -> WorkbenchDecision:
        bank = candidate.bank
        invoice = candidate.invoice
        row_ids = (bank.row_id, invoice.row_id)
        evidence = {
            "scope_window": list(window),
            "uniqueness_scope": "five_month_window",
            "amount_relation": "single_exact_amount",
            "subject_evidence": candidate.subject_evidence,
            "supporting_evidence": candidate.supporting_evidence,
            "score": candidate.score,
            "selected_invoice_row_id": invoice.row_id,
        }
        if candidate_scores is not None:
            evidence["candidate_scores"] = candidate_scores
        return WorkbenchDecision(
            decision_id=self._decision_key(bank.month, "bank_invoice_exact_amount", row_ids),
            decision_key=self._decision_key(bank.month, "bank_invoice_exact_amount", row_ids),
            scope_month=bank.month,
            display_state=DISPLAY_STATE_PAIRED,
            decision_status=DECISION_STATUS_PAIRED,
            match_domain=MATCH_DOMAIN_FREE,
            match_shape="bank_invoice",
            rule_code="bank_invoice_exact_amount",
            rule_version=RULE_VERSION,
            row_ids=row_ids,
            bank_row_ids=(bank.row_id,),
            invoice_row_ids=(invoice.row_id,),
            amount=bank.amount,
            direction=bank.direction,
            payment_amount_closed=True,
            invoice_amount_closed=True,
            evidence=evidence,
            blockers=(),
            explanation="Bank transaction and output invoice match by subject evidence, amount and deterministic supporting evidence.",
            source_versions=source_versions,
        )

    def _paired_bank_invoice_sum_decision(
        self,
        *,
        bank: _Row,
        candidates: tuple[_BankInvoiceCandidate, ...],
        window: tuple[str, ...],
        source_versions: dict[str, Any],
    ) -> WorkbenchDecision:
        invoices = tuple(candidate.invoice for candidate in candidates)
        row_ids = (bank.row_id, *(invoice.row_id for invoice in invoices))
        invoice_total = sum((invoice.amount for invoice in invoices), Decimal("0.00"))
        evidence = {
            "scope_window": list(window),
            "uniqueness_scope": "five_month_window",
            "amount_relation": "invoice_sum_exact_amount",
            "subject_evidence": [
                {
                    "invoice_row_id": candidate.invoice.row_id,
                    "matches": candidate.subject_evidence,
                }
                for candidate in candidates
            ],
            "supporting_evidence": [
                {
                    "invoice_row_id": candidate.invoice.row_id,
                    "matches": candidate.supporting_evidence,
                    "score": candidate.score,
                }
                for candidate in candidates
            ],
            "invoice_total": str(invoice_total),
            "payment_amount": str(bank.amount),
        }
        return WorkbenchDecision(
            decision_id=self._decision_key(bank.month, "bank_invoice_exact_sum", row_ids),
            decision_key=self._decision_key(bank.month, "bank_invoice_exact_sum", row_ids),
            scope_month=bank.month,
            display_state=DISPLAY_STATE_PAIRED,
            decision_status=DECISION_STATUS_PAIRED,
            match_domain=MATCH_DOMAIN_FREE,
            match_shape="bank_invoice",
            rule_code="bank_invoice_exact_sum",
            rule_version=RULE_VERSION,
            row_ids=row_ids,
            bank_row_ids=(bank.row_id,),
            invoice_row_ids=tuple(invoice.row_id for invoice in invoices),
            amount=bank.amount,
            direction=bank.direction,
            payment_amount_closed=True,
            invoice_amount_closed=True,
            evidence=evidence,
            blockers=(),
            explanation="Bank transaction amount closes against a unique sum of output invoices for the same buyer.",
            source_versions=source_versions,
        )

    def _open_bank_invoice_conflict_decision(
        self,
        *,
        bank: _Row,
        candidates: tuple[_BankInvoiceCandidate, ...],
        window: tuple[str, ...],
        source_versions: dict[str, Any],
        blocker_code: str,
        amount_relation: str,
        candidate_groups: list[list[str]],
        reason: str,
    ) -> WorkbenchDecision:
        candidates_by_invoice = {candidate.invoice.row_id: candidate for candidate in candidates}
        invoice_ids = tuple(sorted(candidates_by_invoice))
        row_ids = (bank.row_id, *invoice_ids)
        evidence_summary = self._candidate_score_payload([candidates_by_invoice[row_id] for row_id in invoice_ids])
        blocker = {
            "code": blocker_code,
            "candidate_rows": list(row_ids),
            "candidate_groups": candidate_groups,
            "amount_relation": amount_relation,
            "evidence_summary": evidence_summary,
            "reason": reason,
        }
        return WorkbenchDecision(
            decision_id=self._decision_key(bank.month, "bank_invoice_conflict", row_ids),
            decision_key=self._decision_key(bank.month, "bank_invoice_conflict", row_ids),
            scope_month=bank.month,
            display_state=DISPLAY_STATE_OPEN,
            decision_status=DECISION_STATUS_OPEN,
            match_domain=MATCH_DOMAIN_FREE,
            match_shape="bank_invoice",
            rule_code="bank_invoice_conflict",
            rule_version=RULE_VERSION,
            row_ids=row_ids,
            bank_row_ids=(bank.row_id,),
            invoice_row_ids=invoice_ids,
            amount=bank.amount,
            direction=bank.direction,
            payment_amount_closed=False,
            invoice_amount_closed=False,
            evidence={
                "scope_window": list(window),
                "uniqueness_scope": "five_month_window",
                "amount_relation": amount_relation,
                "candidate_scores": evidence_summary,
            },
            blockers=(blocker,),
            explanation="Bank-invoice free matching found competing candidates and needs review.",
            source_versions=source_versions,
        )

    @staticmethod
    def _candidate_score_payload(candidates: list[_BankInvoiceCandidate]) -> list[dict[str, Any]]:
        return [
            {
                "bank_row_id": candidate.bank.row_id,
                "invoice_row_id": candidate.invoice.row_id,
                "score": candidate.score,
                "subject_evidence": candidate.subject_evidence,
                "supporting_evidence": candidate.supporting_evidence,
                "date_distance_days": candidate.date_distance_days,
            }
            for candidate in sorted(candidates, key=lambda item: item.invoice.row_id)
        ]

    def _unique_pairs(self, left_rows: list[_Row], right_rows: list[_Row], match_shape: str) -> list[tuple[_Row, _Row]]:
        return self._mutual_unique_pairs(self._pair_candidates(left_rows, right_rows, match_shape))

    def _pair_candidates(self, left_rows: list[_Row], right_rows: list[_Row], match_shape: str) -> list[tuple[_Row, _Row]]:
        return [
            (left, right)
            for left in left_rows
            for right in right_rows
            if left.direction == right.direction
            and left.amount == right.amount
            and self._has_pair_evidence(left, right, match_shape)
            and (
                match_shape != "oa_bank"
                or self._oa_bank_scheduled_payment_date_compatible(left, right)
            )
        ]

    @staticmethod
    def _mutual_unique_pairs(candidates: list[tuple[_Row, _Row]]) -> list[tuple[_Row, _Row]]:
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

    def _conflicted_two_way_rows(
        self,
        candidate_pairs: list[tuple[_Row, _Row]],
        selected_pairs: list[tuple[_Row, _Row]],
        rule_code: str,
    ) -> dict[str, dict[str, Any]]:
        selected_keys = {(left.row_id, right.row_id) for left, right in selected_pairs}
        conflicted: dict[str, dict[str, Any]] = {}
        for left, right in candidate_pairs:
            if (left.row_id, right.row_id) in selected_keys:
                continue
            candidate_rows = [left.row_id, right.row_id]
            for row in (left, right):
                entry = conflicted.setdefault(row.row_id, {"row": row, "blockers": []})
                entry["blockers"].append(
                    {
                        "code": "multiple_two_way_candidates",
                        "rule_code": rule_code,
                        "candidate_rows": candidate_rows,
                    }
                )
        return conflicted

    def _paired_three_way_decision(
        self,
        candidate: _ThreeWayCandidate,
        window: tuple[str, ...],
        source_versions: dict[str, Any],
    ) -> WorkbenchDecision:
        row_ids = self._row_ids(candidate)
        first_bank = candidate.banks[0] if candidate.banks else None
        first_oa = candidate.oas[0] if candidate.oas else None
        scope_month = resolve_decision_scope_month(
            has_bank=first_bank is not None,
            bank_trade_month=first_bank.month if first_bank is not None else None,
            has_oa=first_oa is not None,
            oa_month=first_oa.month if first_oa is not None else None,
        )
        warnings = tuple(self._warning(code, candidate) for code in candidate.warning_codes)
        total_amount = sum((row.amount for row in candidate.banks), Decimal("0.00"))
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
            oa_row_ids=tuple(row.row_id for row in candidate.oas),
            bank_row_ids=tuple(row.row_id for row in candidate.banks),
            invoice_row_ids=tuple(invoice.row_id for invoice in candidate.invoices),
            amount=total_amount,
            direction=candidate.banks[0].direction if candidate.banks else "expenditure",
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
        evidence = {
            "scope_window": list(window),
            "uniqueness_scope": "five_month_window",
            "text_matches": matching_tokens(self._tokens(left), self._tokens(right)),
        }
        scheduled_match = self._oa_bank_scheduled_payment_date_match(left, right)
        if match_shape == "oa_bank" and scheduled_match is not None:
            evidence["scheduled_payment_date_match"] = scheduled_match
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
            direction=left.direction,
            payment_amount_closed=True if match_shape in {"oa_bank", "bank_invoice"} else None,
            invoice_amount_closed=True if match_shape in {"oa_invoice", "bank_invoice"} else None,
            evidence=evidence,
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
            owner_month = row.month
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
                    direction=row.direction,
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
            direction = self._direction(row_type, row)
            if row_type == "oa" and direction != "expenditure":
                continue
            if direction not in MATCHABLE_DIRECTIONS:
                continue
            row_id = str(row.get("row_id") or row.get("id") or "").strip()
            amount = self._amount(row_type, row)
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
            "oa": ("month", "oa_month", "apply_month", "apply_date", "application_date", "pay_receive_time"),
            "bank": ("trade_month", "month", "transaction_month", "pay_receive_time", "trade_time"),
            "invoice": ("invoice_month", "month", "invoice_date", "issue_date"),
        }[row_type]
        for field in fields:
            value = str(row.get(field) or "").strip()
            if len(value) >= 7:
                return value[:7]
        detail_fields = row.get("detail_fields")
        if row_type == "oa" and isinstance(detail_fields, dict):
            for field in ("申请日期", "申请时间", "提交日期", "提交时间"):
                value = str(detail_fields.get(field) or "").strip()
                if len(value) >= 7:
                    return value[:7]
        return ""

    def _direction(self, row_type: str, row: dict[str, Any]) -> str:
        explicit = str(row.get("direction") or row.get("txn_direction") or "").strip().lower()
        if explicit in {"expenditure", "outflow", "debit", "支出", "付款", "支付"}:
            return "expenditure"
        if explicit in {"income", "inflow", "credit", "收入", "收款"}:
            return "income"
        if row_type == "oa":
            apply_type = str(row.get("apply_type") or row.get("application_type") or "").strip()
            return "income" if "收" in apply_type and "付" not in apply_type else "expenditure"
        if row_type == "bank":
            debit = self._decimal_value(row.get("debit_amount"))
            credit = self._decimal_value(row.get("credit_amount"))
            if debit is not None and debit > Decimal("0.00"):
                return "expenditure"
            if credit is not None and credit > Decimal("0.00"):
                return "income"
            return ""
        if row_type == "invoice":
            return invoice_workbench_direction_from_row(row) or ""
        return ""

    def _amount(self, row_type: str, row: dict[str, Any]) -> Decimal | None:
        if row_type == "bank":
            debit = self._decimal_value(row.get("debit_amount"))
            if debit is not None and debit > Decimal("0.00"):
                return debit
            credit = self._decimal_value(row.get("credit_amount"))
            if credit is not None:
                return credit
            return self._decimal_value(row.get("amount"))
        if row_type == "invoice":
            total_with_tax = self._decimal_value(row.get("total_with_tax"))
            if total_with_tax is not None:
                return total_with_tax
        return self._decimal_value(row.get("amount"))

    def _decimal_value(self, value: Any) -> Decimal | None:
        try:
            return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _amount_cents(amount: Decimal) -> int:
        return int((amount * Decimal("100")).to_integral_value())

    def _has_evidence(self, left: _Row, right: _Row) -> bool:
        return bool(matching_tokens(self._tokens(left), self._tokens(right)))

    def _has_pair_evidence(self, left: _Row, right: _Row, match_shape: str) -> bool:
        if match_shape == "bank_invoice":
            return self._has_bank_invoice_counterparty_evidence(left, right)
        return self._has_evidence(left, right)

    @staticmethod
    def _oa_bank_rows(left: _Row, right: _Row) -> tuple[_Row, _Row] | None:
        oa = left if left.row_type == "oa" else right if right.row_type == "oa" else None
        bank = left if left.row_type == "bank" else right if right.row_type == "bank" else None
        if oa is None or bank is None:
            return None
        return oa, bank

    def _oa_bank_scheduled_payment_date_compatible(self, left: _Row, right: _Row) -> bool:
        rows = self._oa_bank_rows(left, right)
        if rows is None:
            return True
        oa, bank = rows
        return scheduled_payment_date_compatible(oa.data, bank.data, owner_month=oa.month)

    def _oa_bank_scheduled_payment_date_match(self, left: _Row, right: _Row) -> dict[str, Any] | None:
        rows = self._oa_bank_rows(left, right)
        if rows is None:
            return None
        oa, bank = rows
        return scheduled_payment_date_match(oa.data, bank.data, owner_month=oa.month)

    def _has_oa_bank_sum_evidence(self, oa: _Row, bank: _Row) -> bool:
        return any(
            self._is_strong_oa_bank_sum_match(match)
            for match in matching_tokens(self._tokens(oa), self._tokens(bank))
        )

    @staticmethod
    def _is_strong_oa_bank_sum_match(match: dict[str, str]) -> bool:
        token = normalize_match_text(match.get("token"))
        return len(token) >= OA_BANK_SUM_MIN_EVIDENCE_TOKEN_LENGTH and token not in OA_BANK_SUM_WEAK_TOKENS

    def _has_bank_invoice_counterparty_evidence(self, left: _Row, right: _Row) -> bool:
        bank = left if left.row_type == "bank" else right if right.row_type == "bank" else None
        invoice = left if left.row_type == "invoice" else right if right.row_type == "invoice" else None
        if bank is None or invoice is None or bank.direction != invoice.direction:
            return False
        return bool(matching_tokens(self._bank_counterparty_tokens(bank), self._invoice_counterparty_tokens(invoice)))

    def _bank_counterparty_tokens(self, row: _Row):
        detail_fields = row.data.get("detail_fields") if isinstance(row.data.get("detail_fields"), dict) else {}
        return evidence_tokens(
            {
                "bank.counterparty": row.data.get("counterparty") or row.data.get("counterparty_name"),
                "bank.counterparty_tax_no": row.data.get("counterparty_tax_no"),
                "bank.detail_counterparty": detail_fields.get("对方户名") if isinstance(detail_fields, dict) else None,
            }
        )

    def _bank_text_tokens(self, row: _Row):
        detail_fields = row.data.get("detail_fields") if isinstance(row.data.get("detail_fields"), dict) else {}
        return evidence_tokens(
            {
                "bank.summary": row.data.get("summary"),
                "bank.remark": row.data.get("remark"),
                "bank.purpose": row.data.get("purpose"),
                "bank.postscript": row.data.get("postscript"),
                "bank.detail_summary": detail_fields.get("摘要") if isinstance(detail_fields, dict) else None,
                "bank.detail_remark": detail_fields.get("备注") if isinstance(detail_fields, dict) else None,
                "bank.detail_purpose": detail_fields.get("用途") if isinstance(detail_fields, dict) else None,
                "bank.detail_postscript": detail_fields.get("附言") if isinstance(detail_fields, dict) else None,
            }
        )

    def _invoice_counterparty_tokens(self, row: _Row):
        if row.direction == "income":
            return evidence_tokens(
                {
                    "invoice.buyer_name": row.data.get("buyer_name"),
                    "invoice.buyer_tax_no": row.data.get("buyer_tax_no"),
                }
            )
        return evidence_tokens(
            {
                "invoice.seller_name": row.data.get("seller_name"),
                "invoice.seller_tax_no": row.data.get("seller_tax_no"),
            }
        )

    def _invoice_name_tokens(self, row: _Row):
        if row.direction == "income":
            return evidence_tokens({"invoice.buyer_name": row.data.get("buyer_name")})
        return evidence_tokens({"invoice.seller_name": row.data.get("seller_name")})

    def _invoice_identity_tokens(self, row: _Row):
        return evidence_tokens(
            {
                "invoice.invoice_no": row.data.get("invoice_no") or row.data.get("invoice_number"),
                "invoice.digital_invoice_no": row.data.get("digital_invoice_no") or row.data.get("digital_no"),
                "invoice.invoice_code": row.data.get("invoice_code") or row.data.get("code"),
            }
        )

    def _invoice_business_reference_tokens(self, row: _Row):
        return evidence_tokens(
            {
                "invoice.contract_no": row.data.get("contract_no") or row.data.get("contract_number"),
                "invoice.order_no": row.data.get("order_no") or row.data.get("order_number"),
                "invoice.project_no": row.data.get("project_no") or row.data.get("project_code"),
                "invoice.project_name": row.data.get("project_name") or row.data.get("project"),
            }
        )

    def _invoice_tax_fields(self, row: _Row) -> dict[str, Any]:
        if row.direction == "income":
            return {"invoice.buyer_tax_no": row.data.get("buyer_tax_no")}
        return {"invoice.seller_tax_no": row.data.get("seller_tax_no")}

    @staticmethod
    def _normalized_field_values(fields: dict[str, Any]) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for field, raw_value in fields.items():
            value = normalize_match_text(raw_value)
            if not value:
                continue
            key = (field, value)
            if key in seen:
                continue
            seen.add(key)
            values.append(key)
        return values

    @staticmethod
    def _is_exact_name_match(match: dict[str, str], left_tokens, right_tokens) -> bool:
        left_values = [
            token.value
            for token in left_tokens
            if token.source_field == match["left_source_field"] and token.value == match["token"]
        ]
        right_values = [
            token.value
            for token in right_tokens
            if token.source_field == match["right_source_field"] and token.value == match["token"]
        ]
        return bool(left_values and right_values)

    def _is_full_invoice_identity_match(self, match: dict[str, str], invoice: _Row) -> bool:
        identity_values = {
            value
            for _, value in self._normalized_field_values(
                {
                    "invoice.invoice_no": invoice.data.get("invoice_no") or invoice.data.get("invoice_number"),
                    "invoice.digital_invoice_no": invoice.data.get("digital_invoice_no") or invoice.data.get("digital_no"),
                    "invoice.invoice_code": invoice.data.get("invoice_code") or invoice.data.get("code"),
                }
            )
        }
        return match["token"] in identity_values

    @staticmethod
    def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for item in items:
            key = tuple(sorted(item.items()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _date_distance_days(self, bank: _Row, invoice: _Row) -> int | None:
        bank_date = self._row_date(
            bank,
            ("trade_time", "pay_receive_time", "transaction_time", "transaction_date", "trade_date", "month", "trade_month"),
        )
        invoice_date = self._row_date(invoice, ("invoice_date", "issue_date", "month", "invoice_month"))
        if bank_date is None or invoice_date is None:
            return None
        return abs((bank_date - invoice_date).days)

    @staticmethod
    def _row_date(row: _Row, fields: tuple[str, ...]) -> date | None:
        for field in fields:
            value = str(row.data.get(field) or "").strip()
            if not value:
                continue
            if len(value) >= 10:
                try:
                    return date.fromisoformat(value[:10])
                except ValueError:
                    continue
            if len(value) >= 7:
                try:
                    return date.fromisoformat(f"{value[:7]}-01")
                except ValueError:
                    continue
        if row.month:
            try:
                return date.fromisoformat(f"{row.month}-01")
            except ValueError:
                return None
        return None

    def _tokens(self, row: _Row):
        if row.row_type == "oa":
            return evidence_tokens(
                {
                    "oa.applicant": row.data.get("applicant"),
                    "oa.counterparty": row.data.get("counterparty_name") or row.data.get("counterparty"),
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
        if row.direction == "income":
            return evidence_tokens(
                {
                    "invoice.buyer_name": row.data.get("buyer_name"),
                    "invoice.buyer_tax_no": row.data.get("buyer_tax_no"),
                }
            )
        return evidence_tokens(
            {
                "invoice.seller_name": row.data.get("seller_name"),
                "invoice.seller_tax_no": row.data.get("seller_tax_no"),
            }
        )

    def _attachment_invoices(self, oa: _Row, invoices: list[_Row]) -> tuple[_Row, ...]:
        attached = [
            invoice
            for invoice in invoices
            if invoice.data.get("source_kind") == OA_ATTACHMENT_INVOICE_SOURCE_KIND
            and self._is_attachment_for_oa(invoice, oa)
        ]
        return tuple(sorted(attached, key=lambda row: row.row_id))

    @staticmethod
    def _is_attachment_for_oa(invoice: _Row, oa: _Row) -> bool:
        return oa_attachment_matches_oa({"id": invoice.row_id, **invoice.data}, oa.row_id)

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
        scheduled_match = self._oa_bank_scheduled_payment_date_match(oa, bank)
        if scheduled_match is not None:
            payload["scheduled_payment_date_match"] = scheduled_match
        if extra:
            payload.update(extra)
        return payload

    def _multi_payment_single_invoice_evidence(
        self,
        *,
        window: tuple[str, ...],
        oas: tuple[_Row, ...],
        banks: tuple[_Row, ...],
        invoice: _Row,
    ) -> dict[str, Any]:
        oa_bank_matches = [
            match
            for oa, bank in zip(oas, banks, strict=False)
            for match in matching_tokens(self._tokens(oa), self._tokens(bank))
        ]
        invoice_matches = [
            match
            for row in (*oas, *banks)
            for match in matching_tokens(self._tokens(row), self._tokens(invoice))
        ]
        payment_total = sum((bank.amount for bank in banks), Decimal("0.00"))
        return {
            "scope_window": list(window),
            "uniqueness_scope": "five_month_window",
            "three_way_evidence": "multi_payment_single_invoice_sum",
            "oa_bank_text_matches": oa_bank_matches,
            "invoice_text_matches": invoice_matches,
            "payment_pair_count": len(banks),
            "payment_total": str(payment_total),
            "invoice_total": str(invoice.amount),
        }

    def _three_way_evidence_kind(self, oa: _Row, bank: _Row, invoices: tuple[_Row, ...]) -> str:
        has_oa_invoice = any(self._has_evidence(oa, invoice) for invoice in invoices)
        has_bank_invoice = any(self._has_evidence(bank, invoice) for invoice in invoices)
        if has_oa_invoice and has_bank_invoice:
            return "strong"
        return "bridged_by_oa"

    def _three_way_explanation(self, candidate: _ThreeWayCandidate) -> str:
        if candidate.rule_code == "oa_bank_pairs_single_invoice_exact_sum":
            return "Multiple OA-bank payment pairs sum exactly to one invoice in the five-month window."
        if candidate.warning_codes:
            return "OA and bank payment amounts close; OA attachment invoice amount does not close."
        if len(candidate.invoices) > 1:
            return "OA, bank and the unique invoice sum close in the five-month window."
        return "OA, bank and invoice amounts close uniquely in the five-month window."

    def _warning(self, code: str, candidate: _ThreeWayCandidate) -> DecisionWarning:
        if code == WARNING_INVOICE_AMOUNT_MISMATCH:
            invoice_sum = sum((invoice.amount for invoice in candidate.invoices), Decimal("0.00"))
            payment_sum = sum((bank.amount for bank in candidate.banks), Decimal("0.00"))
            delta = payment_sum - invoice_sum
            return DecisionWarning(
                code=code,
                message=(
                    "OA 与流水金额一致，但 OA 来源附件发票合计金额不一致。"
                    f"OA 金额 {payment_sum}，流水金额 {payment_sum}，"
                    f"附件发票合计 {invoice_sum}，差额 {delta}，正式发票数量 {len(candidate.invoices)}。"
                ),
            )
        return DecisionWarning(code=code, message=code)

    def _row_ids(self, candidate: _ThreeWayCandidate) -> tuple[str, ...]:
        return (
            *(row.row_id for row in candidate.oas),
            *(row.row_id for row in candidate.banks),
            *(invoice.row_id for invoice in candidate.invoices),
        )

    def _payment_row_ids(self, candidate: _ThreeWayCandidate) -> tuple[str, ...]:
        return (*(row.row_id for row in candidate.oas), *(row.row_id for row in candidate.banks))

    def _candidate_key(self, candidate: _ThreeWayCandidate) -> tuple[str, ...]:
        return (candidate.rule_code, *self._row_ids(candidate))

    def _decision_key(self, scope_month: str, rule_code: str, row_ids: tuple[str, ...]) -> str:
        return f"decision:{scope_month}:{rule_code}:{':'.join(row_ids)}"
