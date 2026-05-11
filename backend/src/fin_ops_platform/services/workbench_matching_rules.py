from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from fin_ops_platform.services.imports import normalize_name
from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_special_pair_rule_service import WorkbenchSpecialPairRuleService


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MAX_SUM_MATCH_CANDIDATES = 150
MAX_SUM_MATCH_SIZE = 6
MAX_SUM_MATCH_STATE_COUNT = 20000
MAX_SUM_COMBINATION_SIZE = MAX_SUM_MATCH_SIZE
OA_BANK_CANDIDATE_MAX_DAYS = 60
OA_BANK_MEDIUM_EVIDENCE_THRESHOLD = 2
GENERIC_COUNTERPARTY_NAMES = {
    normalize_name(value)
    for value in (
        "批量账务集中处理",
        "批量代发",
        "代发",
        "集中处理",
        "银行批量处理",
        "网上银行",
        "银企直连",
    )
}
GENERIC_SUMMARY_TERMS = {"报销", "转账", "付款", "支付", "费用", "代付", "批量"}
TEXT_SPLIT_RE = re.compile(r"[\s,，.。;；:：、/\\|()（）\[\]【】{}<>《》\"'“”‘’+-]+")
WORKBENCH_MATCHING_RULES_VERSION = "2026-05-11-deterministic-row-grouping"


class WorkbenchMatchingRules:
    def __init__(self, *, include_special_rules: bool = True) -> None:
        self._skipped_rules: list[dict[str, Any]] = []
        self._include_special_rules = include_special_rules
        self._special_rule_service = WorkbenchSpecialPairRuleService()

    def generate_candidates(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        *,
        settings: dict[str, Any] | None = None,
        source_versions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._skipped_rules = []
        resolved_settings = settings if isinstance(settings, dict) else {}
        resolved_versions = deepcopy(source_versions if isinstance(source_versions, dict) else {})
        oa = [self._with_type(row, "oa") for row in oa_rows]
        bank = [self._with_type(row, "bank") for row in bank_rows]
        invoices = [self._with_type(row, "invoice") for row in invoice_rows]

        candidates: list[dict[str, Any]] = []
        candidates.extend(self._oa_bank_exact_amount(scope_month, oa, bank, resolved_versions))
        candidates.extend(self._oa_attachment_invoice_source_link(scope_month, oa, bank, invoices, resolved_versions))
        candidates.extend(self._oa_multi_invoice_exact_sum(scope_month, oa, invoices, resolved_versions))
        candidates.extend(self._oa_bank_multi_invoice_exact_sum(scope_month, oa, bank, invoices, resolved_versions))
        candidates.extend(self._oa_item_invoice_exact_amount(scope_month, oa, invoices, resolved_versions))
        candidates.extend(self._bank_invoice_exact_amount(scope_month, bank, invoices, resolved_versions))
        if self._include_special_rules:
            candidates.extend(
                self._special_rule_service.generate_candidates(
                    scope_month,
                    oa,
                    bank,
                    invoices,
                    settings=resolved_settings,
                    source_versions=resolved_versions,
                )
            )
        candidates.extend(self._matching_engine_compatibility(scope_month, bank, invoices, resolved_versions))
        return self._mark_conflicts(self._dedupe_candidates(candidates))

    def last_summary(self) -> dict[str, Any]:
        skipped_rules = deepcopy(self._skipped_rules)
        return {
            "skipped_rule_count": len(skipped_rules),
            "skipped_rules": skipped_rules,
        }

    def _oa_bank_exact_amount(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        scored_pairs: list[dict[str, Any]] = []
        for oa_row in sorted(oa_rows, key=self._row_id):
            oa_amount = self._amount(oa_row)
            if oa_amount is None:
                continue
            for bank_row in sorted(bank_rows, key=self._row_id):
                if self._direction(oa_row) != self._direction(bank_row):
                    continue
                if oa_amount != self._amount(bank_row):
                    continue
                evidence = self._oa_bank_evidence(oa_row, bank_row)
                if not evidence["eligible"]:
                    continue
                scored_pairs.append(
                    {
                        "oa_row": oa_row,
                        "bank_row": bank_row,
                        "amount": oa_amount,
                        "evidence": evidence,
                        "score": int(evidence["score"]),
                    }
                )

        unique_pairs = self._mutual_unique_top_oa_bank_pairs(scored_pairs)
        candidates: list[dict[str, Any]] = []
        for pair in unique_pairs:
            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code="oa_bank_exact_amount",
                    rows=[pair["oa_row"], pair["bank_row"]],
                    status="incomplete",
                    confidence="medium",
                    amount=pair["amount"],
                    explanation=(
                        "OA and bank transaction have the same amount and business evidence; "
                        "invoice evidence is missing."
                    ),
                    source_versions=source_versions,
                    special_metadata={
                        "evidence": {
                            "score": pair["evidence"]["score"],
                            "strong": pair["evidence"]["strong"],
                            "medium": pair["evidence"]["medium"],
                            "negative": pair["evidence"]["negative"],
                        }
                    },
                )
            )
        return candidates

    def _mutual_unique_top_oa_bank_pairs(self, scored_pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_oa: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_bank: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for pair in scored_pairs:
            by_oa[self._row_id(pair["oa_row"])].append(pair)
            by_bank[self._row_id(pair["bank_row"])].append(pair)

        unique_top_by_oa = {
            row_id: top[0]
            for row_id, pairs in by_oa.items()
            if (top := self._unique_top_scored_pairs(pairs))
        }
        unique_top_by_bank = {
            row_id: top[0]
            for row_id, pairs in by_bank.items()
            if (top := self._unique_top_scored_pairs(pairs))
        }

        resolved: list[dict[str, Any]] = []
        for pair in sorted(scored_pairs, key=lambda item: (self._row_id(item["oa_row"]), self._row_id(item["bank_row"]))):
            oa_id = self._row_id(pair["oa_row"])
            bank_id = self._row_id(pair["bank_row"])
            if unique_top_by_oa.get(oa_id) is pair and unique_top_by_bank.get(bank_id) is pair:
                resolved.append(pair)
        return resolved

    @staticmethod
    def _unique_top_scored_pairs(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not pairs:
            return []
        top_score = max(int(pair["score"]) for pair in pairs)
        top_pairs = [pair for pair in pairs if int(pair["score"]) == top_score]
        return top_pairs if len(top_pairs) == 1 else []

    def _oa_bank_evidence(self, oa_row: dict[str, Any], bank_row: dict[str, Any]) -> dict[str, Any]:
        strong: list[str] = []
        medium: list[str] = []
        negative: list[str] = []

        oa_date = self._row_date(oa_row)
        bank_date = self._row_date(bank_row)
        if oa_date is not None and bank_date is not None:
            days_delta = abs((oa_date - bank_date).days)
            if days_delta > OA_BANK_CANDIDATE_MAX_DAYS:
                return {
                    "eligible": False,
                    "score": 0,
                    "strong": [],
                    "medium": [],
                    "negative": ["date_outside_max_window"],
                }
            if days_delta <= 7:
                medium.append("date_within_7_days")

        oa_counterparty = self._counterparty(oa_row)
        bank_counterparty = self._counterparty(bank_row)
        bank_counterparty_is_generic = self._is_generic_counterparty(bank_counterparty)
        bank_summary = self._bank_text(bank_row)
        bank_summary_is_generic = self._is_generic_summary(bank_summary)
        applicant = self._normalized_applicant(oa_row)
        applicant_text = self._applicant_text(oa_row)
        oa_text = self._oa_business_text(oa_row)

        if oa_counterparty and bank_counterparty and oa_counterparty == bank_counterparty and not bank_counterparty_is_generic:
            strong.append("counterparty_match")
        if bank_counterparty and not bank_counterparty_is_generic and bank_counterparty in self._oa_item_counterparties(oa_row):
            strong.append("oa_item_counterparty_match")
        if (
            self._is_daily_reimbursement(oa_row)
            and applicant
            and bank_counterparty
            and applicant == bank_counterparty
            and not bank_counterparty_is_generic
        ):
            strong.append("daily_reimbursement_applicant_counterparty_match")
        if applicant_text and applicant_text in bank_summary and not bank_summary_is_generic:
            strong.append("bank_text_contains_applicant")
        if bank_counterparty and not bank_counterparty_is_generic and bank_counterparty in normalize_name(oa_text):
            strong.append("oa_text_contains_bank_counterparty")

        project_keywords = self._significant_keywords(self._text_from_fields(oa_row, ("project_name", "project", "project_title")))
        reason_keywords = self._significant_keywords(self._text_from_fields(oa_row, ("reason", "purpose", "description", "summary")))
        bank_keywords = self._significant_keywords(bank_summary)
        normalized_bank_text = normalize_name(bank_summary)
        normalized_oa_text = normalize_name(oa_text)
        if project_keywords and self._contains_any_keyword(normalized_bank_text, project_keywords):
            medium.append("bank_text_contains_project_keyword")
        if reason_keywords and self._contains_any_keyword(normalized_bank_text, reason_keywords):
            medium.append("bank_text_contains_reason_keyword")
        if bank_keywords and self._contains_any_keyword(normalized_oa_text, bank_keywords):
            medium.append("oa_text_contains_bank_keyword")
        if applicant_text and applicant_text in bank_summary:
            medium.append("bank_text_contains_applicant")

        if bank_counterparty_is_generic:
            negative.append("generic_bank_counterparty")
        if bank_summary_is_generic:
            negative.append("generic_bank_summary")

        score = (100 if strong else 0) + len(set(medium))
        eligible = bool(strong) or len(set(medium)) >= OA_BANK_MEDIUM_EVIDENCE_THRESHOLD
        return {
            "eligible": eligible,
            "score": score,
            "strong": sorted(set(strong)),
            "medium": sorted(set(medium)),
            "negative": sorted(set(negative)),
        }

    def _oa_attachment_invoice_source_link(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        attachment_invoices_by_oa_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for invoice_row in sorted(invoice_rows, key=self._row_id):
            if self._source_kind(invoice_row) != "oa_attachment_invoice":
                continue
            linked_oa_id = self._linked_oa_id(invoice_row)
            if linked_oa_id:
                attachment_invoices_by_oa_id[linked_oa_id].append(invoice_row)

        candidates: list[dict[str, Any]] = []
        for oa_row in sorted(oa_rows, key=self._row_id):
            oa_id = self._row_id(oa_row)
            target = self._amount(oa_row)
            if target is None or target <= ZERO:
                continue
            attachment_invoices = attachment_invoices_by_oa_id.get(oa_id, [])
            if not attachment_invoices:
                continue
            invoice_total = self._sum_amounts(attachment_invoices)
            if invoice_total is None:
                continue
            invoice_delta = abs(invoice_total - target).quantize(CENT)
            invoice_amount_closed = invoice_delta == ZERO

            credible_bank_pairs = []
            for bank_row in sorted(bank_rows, key=self._row_id):
                if self._direction(bank_row) != self._direction(oa_row) or self._amount(bank_row) != target:
                    continue
                evidence = self._oa_bank_evidence(oa_row, bank_row)
                if not evidence["eligible"]:
                    continue
                credible_bank_pairs.append(
                    {
                        "bank_row": bank_row,
                        "evidence": evidence,
                        "score": int(evidence["score"]),
                    }
                )
            unique_bank_pairs = self._unique_top_scored_pairs(credible_bank_pairs)
            if unique_bank_pairs:
                pair = unique_bank_pairs[0]
                evidence = pair["evidence"]
                candidates.append(
                    self._candidate(
                        scope_month,
                        rule_code="oa_attachment_invoice_source_link",
                        rows=[oa_row, pair["bank_row"], *attachment_invoices],
                        status="auto_closed",
                        confidence="high",
                        amount=target,
                        amount_delta=invoice_delta,
                        explanation=(
                            "OA attachment invoices are source-linked to the OA row and close with credible OA-bank evidence."
                            if invoice_amount_closed
                            else "OA attachment invoices are source-linked to the OA row; OA amount closes with credible OA-bank evidence even though attachment invoice total differs."
                        ),
                        source_versions=source_versions,
                        special_metadata={
                            "evidence": {
                                "strong": sorted({"oa_attachment_invoice_source_link", *evidence["strong"]}),
                                "medium": evidence["medium"],
                                "negative": evidence["negative"],
                                "score": evidence["score"],
                                "invoice_amount_field": "total_with_tax_or_amount",
                                "invoice_total": self._format_amount(invoice_total),
                                "target_amount": self._format_amount(target),
                                "amount_closed": invoice_amount_closed,
                            }
                        },
                    )
                )
                continue

            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code="oa_attachment_invoice_source_link",
                    rows=[oa_row, *attachment_invoices],
                    status="incomplete",
                    confidence="high",
                    amount=target,
                    amount_delta=invoice_delta,
                    explanation=(
                        "OA attachment invoices are source-linked to the OA row and close the OA amount; bank transaction is missing."
                        if invoice_amount_closed
                        else "OA attachment invoices are source-linked to the OA row, but invoice total differs from OA amount and bank transaction is missing."
                    ),
                    source_versions=source_versions,
                    special_metadata={
                        "evidence": {
                            "strong": ["oa_attachment_invoice_source_link"],
                            "invoice_amount_field": "total_with_tax_or_amount",
                            "invoice_total": self._format_amount(invoice_total),
                            "target_amount": self._format_amount(target),
                            "amount_closed": invoice_amount_closed,
                        }
                    },
                )
            )
        return candidates

    def _oa_multi_invoice_exact_sum(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for oa_row in sorted(oa_rows, key=self._row_id):
            target = self._amount(oa_row)
            if target is None or target <= ZERO:
                continue
            invoices = self._compatible_invoices_for_oa(oa_row, invoice_rows)
            match = self._find_unique_sum_match(
                invoices,
                target,
                scope_month=scope_month,
                rule_code="oa_multi_invoice_exact_sum",
            )
            if not match:
                continue
            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code="oa_multi_invoice_exact_sum",
                    rows=[oa_row, *match],
                    status="incomplete",
                    confidence="medium",
                    amount=target,
                    explanation="OA amount equals the exact sum of multiple invoices; bank transaction is missing.",
                    source_versions=source_versions,
                )
            )
        return candidates

    def _oa_bank_multi_invoice_exact_sum(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for oa_row in sorted(oa_rows, key=self._row_id):
            target = self._amount(oa_row)
            if target is None or target <= ZERO:
                continue
            for bank_row in sorted(bank_rows, key=self._row_id):
                if target != self._amount(bank_row):
                    continue
                if self._direction(oa_row) != self._direction(bank_row):
                    continue
                if not self._counterparties_compatible(oa_row, bank_row):
                    continue
                invoices = [
                    row
                    for row in self._compatible_invoices_for_oa(oa_row, invoice_rows)
                    if self._direction(row) == self._direction(bank_row)
                ]
                match = self._find_unique_sum_match(
                    invoices,
                    target,
                    scope_month=scope_month,
                    rule_code="oa_bank_multi_invoice_exact_sum",
                )
                if not match:
                    continue
                candidates.append(
                    self._candidate(
                        scope_month,
                        rule_code="oa_bank_multi_invoice_exact_sum",
                        rows=[oa_row, bank_row, *match],
                        status="auto_closed",
                        confidence="high",
                        amount=target,
                        explanation="OA, one bank transaction, and multiple invoices close exactly.",
                        source_versions=source_versions,
                    )
                )
        return candidates

    def _oa_item_invoice_exact_amount(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for oa_row in sorted(oa_rows, key=self._row_id):
            for item in self._oa_items(oa_row):
                item_amount = self._amount_from_value(item.get("amount"))
                if item_amount is None or item_amount <= ZERO:
                    continue
                for invoice_row in sorted(invoice_rows, key=self._row_id):
                    if self._direction(oa_row) != self._direction(invoice_row):
                        continue
                    if item_amount != self._amount(invoice_row):
                        continue
                    item_id = str(item.get("id") or item.get("item_id") or item.get("name") or "").strip()
                    candidates.append(
                        self._candidate(
                            scope_month,
                            rule_code="oa_item_invoice_exact_amount",
                            rows=[oa_row, invoice_row],
                            status="needs_review",
                            confidence="medium",
                            amount=item_amount,
                            explanation=f"OA item-level amount matches one invoice exactly. item={item_id or 'unknown'}",
                            source_versions=source_versions,
                        )
                    )
        return candidates

    def _bank_invoice_exact_amount(
        self,
        scope_month: str,
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for bank_row in sorted(bank_rows, key=self._row_id):
            bank_amount = self._amount(bank_row)
            if bank_amount is None:
                continue
            for invoice_row in sorted(invoice_rows, key=self._row_id):
                if bank_amount != self._amount(invoice_row):
                    continue
                if self._direction(bank_row) != self._direction(invoice_row):
                    continue
                same_counterparty = self._counterparties_compatible(bank_row, invoice_row, require_known=True)
                if not same_counterparty:
                    continue
                candidates.append(
                    self._candidate(
                        scope_month,
                        rule_code="exact_counterparty_amount_one_to_one",
                        rows=[bank_row, invoice_row],
                        status="auto_closed",
                        confidence="high",
                        amount=bank_amount,
                        explanation="Counterparty, direction, and amount matched exactly.",
                        source_versions=source_versions,
                    )
                )
        return candidates

    def _matching_engine_compatibility(
        self,
        scope_month: str,
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        claimed_bank_ids: set[str] = set()
        claimed_invoice_ids: set[str] = set()

        exact_matches = [
            candidate
            for candidate in self._bank_invoice_exact_amount(scope_month, bank_rows, invoice_rows, source_versions)
            if candidate["rule_code"] == "exact_counterparty_amount_one_to_one"
        ]
        candidates.extend(exact_matches)
        claimed_bank_ids.update(row_id for candidate in exact_matches for row_id in candidate["bank_row_ids"])
        claimed_invoice_ids.update(row_id for candidate in exact_matches for row_id in candidate["invoice_row_ids"])

        for bank_row in sorted(bank_rows, key=self._row_id):
            bank_id = self._row_id(bank_row)
            if bank_id in claimed_bank_ids:
                continue
            bank_amount = self._amount(bank_row)
            if bank_amount is None:
                continue
            invoices = [
                invoice
                for invoice in invoice_rows
                if self._row_id(invoice) not in claimed_invoice_ids
                and self._direction(invoice) == self._direction(bank_row)
                and self._counterparties_compatible(bank_row, invoice, require_known=True)
            ]
            match = self._find_unique_sum_match(
                invoices,
                bank_amount,
                scope_month=scope_month,
                rule_code="same_counterparty_many_invoices_one_transaction",
            )
            if not match:
                continue
            candidate = self._candidate(
                scope_month,
                rule_code="same_counterparty_many_invoices_one_transaction",
                rows=[bank_row, *match],
                status="needs_review",
                confidence="medium",
                amount=bank_amount,
                explanation="Multiple invoices under the same counterparty sum to one transaction.",
                source_versions=source_versions,
            )
            candidates.append(candidate)
            claimed_bank_ids.add(bank_id)
            claimed_invoice_ids.update(self._row_id(row) for row in match)

        for invoice_row in sorted(invoice_rows, key=self._row_id):
            invoice_id = self._row_id(invoice_row)
            if invoice_id in claimed_invoice_ids:
                continue
            invoice_amount = self._amount(invoice_row)
            if invoice_amount is None:
                continue
            banks = [
                bank
                for bank in bank_rows
                if self._row_id(bank) not in claimed_bank_ids
                and self._direction(bank) == self._direction(invoice_row)
                and self._counterparties_compatible(bank, invoice_row, require_known=True)
            ]
            match = self._find_unique_sum_match(
                banks,
                invoice_amount,
                scope_month=scope_month,
                rule_code="same_counterparty_one_invoice_many_transactions",
            )
            if not match:
                continue
            candidate = self._candidate(
                scope_month,
                rule_code="same_counterparty_one_invoice_many_transactions",
                rows=[invoice_row, *match],
                status="needs_review",
                confidence="medium",
                amount=invoice_amount,
                explanation="One invoice amount can be composed by multiple transactions under the same counterparty.",
                source_versions=source_versions,
            )
            candidates.append(candidate)
            claimed_invoice_ids.add(invoice_id)
            claimed_bank_ids.update(self._row_id(row) for row in match)

        for invoice_row in sorted(invoice_rows, key=self._row_id):
            invoice_id = self._row_id(invoice_row)
            if invoice_id in claimed_invoice_ids:
                continue
            invoice_amount = self._amount(invoice_row)
            if invoice_amount is None:
                continue
            banks = [
                bank
                for bank in bank_rows
                if self._row_id(bank) not in claimed_bank_ids
                and self._direction(bank) == self._direction(invoice_row)
                and self._counterparties_compatible(bank, invoice_row, require_known=True)
            ]
            if len(banks) != 1:
                continue
            bank = banks[0]
            bank_amount = self._amount(bank)
            if bank_amount is None or bank_amount == invoice_amount:
                continue
            amount = min(bank_amount, invoice_amount)
            delta = abs(bank_amount - invoice_amount)
            candidate = self._candidate(
                scope_month,
                rule_code="same_counterparty_partial_amount_match",
                rows=[invoice_row, bank],
                status="needs_review",
                confidence="low",
                amount=amount,
                amount_delta=delta,
                explanation="Counterparty and direction matched, but the amount differed and requires manual confirmation.",
                source_versions=source_versions,
            )
            candidates.append(candidate)
            claimed_invoice_ids.add(invoice_id)
            claimed_bank_ids.add(self._row_id(bank))

        for invoice_row in sorted(invoice_rows, key=self._row_id):
            if self._row_id(invoice_row) in claimed_invoice_ids:
                continue
            amount = self._amount(invoice_row)
            if amount is None:
                continue
            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code="no_confident_match",
                    rows=[invoice_row],
                    status="needs_review",
                    confidence="low",
                    amount=amount,
                    explanation="No confident bank transaction match was found for this invoice.",
                    source_versions=source_versions,
                )
            )
        for bank_row in sorted(bank_rows, key=self._row_id):
            if self._row_id(bank_row) in claimed_bank_ids:
                continue
            amount = self._amount(bank_row)
            if amount is None:
                continue
            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code="no_confident_match",
                    rows=[bank_row],
                    status="needs_review",
                    confidence="low",
                    amount=amount,
                    explanation="No confident invoice match was found for this bank transaction.",
                    source_versions=source_versions,
                )
            )
        return candidates

    def _mark_conflicts(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        auto_candidates = [candidate for candidate in candidates if candidate["status"] == "auto_closed"]
        by_row_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in auto_candidates:
            for row_id in candidate["row_ids"]:
                by_row_id[str(row_id)].append(candidate)

        conflict_peers_by_key: dict[str, set[str]] = defaultdict(set)
        for claimants in by_row_id.values():
            if len(claimants) <= 1:
                continue
            keys = [self._candidate_key(candidate) for candidate in claimants]
            for candidate in claimants:
                own_key = self._candidate_key(candidate)
                conflict_peers_by_key[own_key].update(key for key in keys if key != own_key)

        if not conflict_peers_by_key:
            return candidates

        resolved: list[dict[str, Any]] = []
        for candidate in candidates:
            candidate_key = self._candidate_key(candidate)
            if candidate_key not in conflict_peers_by_key:
                resolved.append(candidate)
                continue
            updated = deepcopy(candidate)
            updated["status"] = "conflict"
            updated["conflict_candidate_keys"] = sorted(conflict_peers_by_key[candidate_key])
            resolved.append(updated)
        return resolved

    def _dedupe_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            key = self._candidate_key(candidate)
            if key not in deduped:
                deduped[key] = candidate
        return list(deduped.values())

    def _candidate(
        self,
        scope_month: str,
        *,
        rule_code: str,
        rows: list[dict[str, Any]],
        status: str,
        confidence: str,
        amount: Decimal,
        explanation: str,
        source_versions: dict[str, Any],
        amount_delta: Decimal = ZERO,
        special_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        oa_ids = [self._row_id(row) for row in rows if row.get("type") == "oa"]
        bank_ids = [self._row_id(row) for row in rows if row.get("type") == "bank"]
        invoice_ids = [self._row_id(row) for row in rows if row.get("type") == "invoice"]
        row_ids = sorted([*oa_ids, *bank_ids, *invoice_ids])
        return {
            "scope_month": scope_month,
            "candidate_type": self._candidate_type(oa_ids, bank_ids, invoice_ids),
            "status": status,
            "confidence": confidence,
            "rule_code": rule_code,
            "row_ids": row_ids,
            "oa_row_ids": sorted(oa_ids),
            "bank_row_ids": sorted(bank_ids),
            "invoice_row_ids": sorted(invoice_ids),
            "amount": self._format_amount(amount),
            "amount_delta": self._format_amount(amount_delta),
            "explanation": explanation,
            "conflict_candidate_keys": [],
            "source_versions": deepcopy(source_versions),
            "special_metadata": deepcopy(special_metadata if isinstance(special_metadata, dict) else {}),
        }

    @staticmethod
    def _candidate_type(oa_ids: list[str], bank_ids: list[str], invoice_ids: list[str]) -> str:
        parts: list[str] = []
        if oa_ids:
            parts.append("oa")
        if bank_ids:
            parts.append("bank")
        if invoice_ids:
            parts.append("invoice")
        return "_".join(parts) or "unknown"

    @staticmethod
    def _candidate_key(candidate: dict[str, Any]) -> str:
        return WorkbenchCandidateMatchService.build_candidate_key(
            scope_month=str(candidate["scope_month"]),
            rule_code=str(candidate["rule_code"]),
            row_ids=list(candidate["row_ids"]),
        )

    def _compatible_invoices_for_oa(
        self,
        oa_row: dict[str, Any],
        invoice_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        oa_id = self._row_id(oa_row)
        linked_attachment_invoice_numbers = {
            invoice_no
            for invoice in invoice_rows
            if self._source_kind(invoice) == "oa_attachment_invoice"
            and self._linked_oa_id(invoice) == oa_id
            and (invoice_no := self._string_value(invoice.get("invoice_no"))) is not None
        }
        return [
            invoice
            for invoice in sorted(invoice_rows, key=self._row_id)
            if self._source_kind(invoice) != "oa_attachment_invoice"
            and self._string_value(invoice.get("invoice_no")) not in linked_attachment_invoice_numbers
            and self._direction(invoice) == self._direction(oa_row)
            and self._counterparties_compatible(oa_row, invoice)
        ]

    def _find_unique_sum_match(
        self,
        rows: list[dict[str, Any]],
        target: Decimal,
        *,
        scope_month: str,
        rule_code: str,
    ) -> list[dict[str, Any]] | None:
        target_cents = self._amount_to_cents(target)
        if target_cents is None or target_cents <= 0:
            return None
        candidates = [
            (row, amount)
            for row in sorted(rows, key=self._row_id)
            if (amount := self._amount(row)) is not None and amount > ZERO and amount <= target
        ]
        if len(candidates) < 2:
            return None
        if len(candidates) > MAX_SUM_MATCH_CANDIDATES:
            self._record_skipped_rule(
                scope_month=scope_month,
                rule_code=rule_code,
                reason="sum_match_candidate_cap_exceeded",
                compatible_count=len(candidates),
                target_cents=target_cents,
            )
            return None

        max_size = min(MAX_SUM_MATCH_SIZE, len(candidates))
        amounts_in_cents: list[int] = []
        rows_by_index: list[dict[str, Any]] = []
        for row, amount in candidates:
            amount_cents = self._amount_to_cents(amount)
            if amount_cents is None or amount_cents <= 0 or amount_cents > target_cents:
                continue
            rows_by_index.append(row)
            amounts_in_cents.append(amount_cents)
        if len(rows_by_index) < 2:
            return None

        # Store at most one combination per (size, sum). None means the state is
        # ambiguous, so exact-sum auto matching should not claim a unique group.
        states: list[dict[int, tuple[int, ...] | None]] = [dict() for _ in range(max_size + 1)]
        states[0][0] = ()
        for index, amount_cents in enumerate(amounts_in_cents):
            upper_size = min(max_size - 1, index)
            for size in range(upper_size, -1, -1):
                for current_sum, combo in list(states[size].items()):
                    next_sum = current_sum + amount_cents
                    if next_sum > target_cents:
                        continue
                    next_combo = None if combo is None else (*combo, index)
                    existing = states[size + 1].get(next_sum)
                    if next_sum not in states[size + 1]:
                        states[size + 1][next_sum] = next_combo
                    elif existing is not None:
                        states[size + 1][next_sum] = None
            if sum(len(state) for state in states) > MAX_SUM_MATCH_STATE_COUNT:
                self._record_skipped_rule(
                    scope_month=scope_month,
                    rule_code=rule_code,
                    reason="sum_match_state_cap_exceeded",
                    compatible_count=len(candidates),
                    target_cents=target_cents,
                )
                return None

        matches: list[tuple[int, ...]] = []
        for size in range(2, max_size + 1):
            combo = states[size].get(target_cents)
            if combo is None and target_cents in states[size]:
                return None
            if combo:
                matches.append(combo)
                if len(matches) > 1:
                    return None
        if len(matches) != 1:
            return None
        return [rows_by_index[index] for index in matches[0]]

    def _sum_amounts(self, rows: list[dict[str, Any]]) -> Decimal | None:
        total = ZERO
        for row in rows:
            amount = self._amount(row)
            if amount is None:
                return None
            total += amount
        return total.quantize(CENT)

    def _record_skipped_rule(
        self,
        *,
        scope_month: str,
        rule_code: str,
        reason: str,
        compatible_count: int,
        target_cents: int,
    ) -> None:
        self._skipped_rules.append(
            {
                "scope_month": scope_month,
                "rule_code": rule_code,
                "reason": reason,
                "compatible_count": compatible_count,
                "target_cents": target_cents,
                "max_sum_match_candidates": MAX_SUM_MATCH_CANDIDATES,
                "max_sum_match_size": MAX_SUM_MATCH_SIZE,
                "max_sum_match_state_count": MAX_SUM_MATCH_STATE_COUNT,
            }
        )

    @staticmethod
    def _amount_to_cents(amount: Decimal) -> int | None:
        try:
            return int((amount.quantize(CENT) * 100).to_integral_value())
        except (InvalidOperation, ValueError):
            return None

    def _counterparties_compatible(
        self,
        left: dict[str, Any],
        right: dict[str, Any],
        *,
        require_known: bool = False,
    ) -> bool:
        left_counterparty = self._counterparty(left)
        right_counterparty = self._counterparty(right)
        if left_counterparty is None or right_counterparty is None:
            return not require_known
        return left_counterparty == right_counterparty

    def _counterparty(self, row: dict[str, Any]) -> str | None:
        row_type = str(row.get("type") or "")
        if row_type in {"oa", "bank"}:
            value = self._string_value(row.get("counterparty_name"))
            return normalize_name(value) if value else None
        invoice_type = self._string_value(row.get("invoice_type")) or ""
        party_field = "buyer_name" if "销" in invoice_type else "seller_name"
        value = self._string_value(row.get(party_field))
        return normalize_name(value) if value else None

    def _direction(self, row: dict[str, Any]) -> str | None:
        row_type = str(row.get("type") or "")
        if row_type == "oa":
            apply_type = self._string_value(row.get("apply_type")) or ""
            return "inflow" if ("收" in apply_type and "付" not in apply_type) else "outflow"
        if row_type == "bank":
            debit = self._amount_from_value(row.get("debit_amount"))
            credit = self._amount_from_value(row.get("credit_amount"))
            if debit is not None and debit > ZERO:
                return "outflow"
            if credit is not None and credit > ZERO:
                return "inflow"
            return None
        invoice_type = self._string_value(row.get("invoice_type")) or ""
        return "inflow" if "销" in invoice_type else "outflow"

    def _amount(self, row: dict[str, Any]) -> Decimal | None:
        if row.get("type") == "bank":
            debit = self._amount_from_value(row.get("debit_amount"))
            if debit is not None and debit > ZERO:
                return debit
            return self._amount_from_value(row.get("credit_amount"))
        if row.get("type") == "invoice":
            total_with_tax = self._amount_from_value(row.get("total_with_tax"))
            if total_with_tax is not None:
                return total_with_tax
        return self._amount_from_value(row.get("amount"))

    @staticmethod
    def _amount_from_value(value: Any) -> Decimal | None:
        if value in (None, "", "--", "—"):
            return None
        try:
            return Decimal(str(value).replace(",", "")).quantize(CENT)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _source_kind(row: dict[str, Any]) -> str:
        return str(row.get("source_kind") or "").strip()

    @staticmethod
    def _linked_oa_id(invoice_row: dict[str, Any]) -> str | None:
        for field_name in (
            "derived_from_oa_id",
            "oa_row_id",
            "oa_id",
            "source_oa_row_id",
            "linked_oa_row_id",
            "parent_oa_row_id",
        ):
            value = str(invoice_row.get(field_name) or "").strip()
            if value:
                return value
        metadata = invoice_row.get("metadata")
        if isinstance(metadata, dict):
            for field_name in ("derived_from_oa_id", "oa_row_id", "oa_id", "source_oa_row_id"):
                value = str(metadata.get(field_name) or "").strip()
                if value:
                    return value
        return None

    def _oa_items(self, oa_row: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for field_name in ("expense_items", "payment_items", "items"):
            value = oa_row.get(field_name)
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        detail_fields = oa_row.get("_detail_fields") or oa_row.get("detail_fields")
        if isinstance(detail_fields, dict):
            value = detail_fields.get("items") or detail_fields.get("expense_items")
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        return items

    def _oa_item_counterparties(self, oa_row: dict[str, Any]) -> set[str]:
        counterparties: set[str] = set()
        for item in self._oa_items(oa_row):
            for key in (
                "counterparty_name",
                "counterparty",
                "payee_name",
                "payer_name",
                "receiver_name",
                "付款对象",
                "收款对象",
                "对方户名",
                "户名",
                "名称",
                "name",
            ):
                value = self._string_value(item.get(key))
                if value:
                    counterparties.add(normalize_name(value))
        return counterparties

    def _is_daily_reimbursement(self, oa_row: dict[str, Any]) -> bool:
        apply_type = self._string_value(oa_row.get("apply_type")) or ""
        expense_type = self._string_value(oa_row.get("expense_type")) or ""
        return "日常报销" in apply_type or "日常报销" in expense_type

    def _normalized_applicant(self, oa_row: dict[str, Any]) -> str | None:
        value = self._applicant_text(oa_row)
        return normalize_name(value) if value else None

    def _applicant_text(self, oa_row: dict[str, Any]) -> str | None:
        for key in ("applicant", "applicant_name", "apply_user", "申请人"):
            value = self._string_value(oa_row.get(key))
            if value:
                return value
        return None

    def _is_generic_counterparty(self, value: str | None) -> bool:
        if not value:
            return False
        return value in GENERIC_COUNTERPARTY_NAMES or any(term in value for term in GENERIC_COUNTERPARTY_NAMES)

    def _is_generic_summary(self, text: str) -> bool:
        normalized = normalize_name(text)
        if not normalized:
            return False
        if normalized in GENERIC_SUMMARY_TERMS:
            return True
        tokens = self._significant_keywords(text, include_generic=True)
        return bool(tokens) and all(token in GENERIC_SUMMARY_TERMS for token in tokens)

    def _bank_text(self, bank_row: dict[str, Any]) -> str:
        return self._join_text_values(
            [
                bank_row.get("summary"),
                bank_row.get("remark"),
                bank_row.get("memo"),
                bank_row.get("postscript"),
                bank_row.get("usage"),
                bank_row.get("detail_fields"),
                bank_row.get("_detail_fields"),
            ]
        )

    def _oa_business_text(self, oa_row: dict[str, Any]) -> str:
        return self._join_text_values(
            [
                oa_row.get("project_name"),
                oa_row.get("project"),
                oa_row.get("project_title"),
                oa_row.get("reason"),
                oa_row.get("purpose"),
                oa_row.get("description"),
                oa_row.get("summary"),
                oa_row.get("detail_fields"),
                oa_row.get("_detail_fields"),
                oa_row.get("expense_items"),
                oa_row.get("payment_items"),
                oa_row.get("items"),
            ]
        )

    def _text_from_fields(self, row: dict[str, Any], field_names: tuple[str, ...]) -> str:
        return self._join_text_values([row.get(field_name) for field_name in field_names])

    def _join_text_values(self, values: list[Any]) -> str:
        parts: list[str] = []
        for value in values:
            parts.extend(self._flatten_text_values(value))
        return " ".join(part for part in parts if part)

    def _flatten_text_values(self, value: Any) -> list[str]:
        if value in (None, "", "--", "—"):
            return []
        if isinstance(value, dict):
            parts: list[str] = []
            for nested_value in value.values():
                parts.extend(self._flatten_text_values(nested_value))
            return parts
        if isinstance(value, list):
            parts = []
            for item in value:
                parts.extend(self._flatten_text_values(item))
            return parts
        return [str(value).strip()] if str(value).strip() else []

    def _significant_keywords(self, text: str, *, include_generic: bool = False) -> set[str]:
        keywords: set[str] = set()
        for token in TEXT_SPLIT_RE.split(text):
            normalized = normalize_name(token)
            if len(normalized) < 2:
                continue
            if not include_generic and normalized in GENERIC_SUMMARY_TERMS:
                continue
            keywords.add(normalized)
        normalized_text = normalize_name(text)
        if (
            len(normalized_text) >= 2
            and (include_generic or normalized_text not in GENERIC_SUMMARY_TERMS)
            and len(normalized_text) <= 20
        ):
            keywords.add(normalized_text)
        return keywords

    @staticmethod
    def _contains_any_keyword(text: str, keywords: set[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _row_date(self, row: dict[str, Any]) -> date | None:
        row_type = str(row.get("type") or "")
        if row_type == "oa":
            candidates = [
                row.get("application_date"),
                row.get("apply_date"),
                row.get("pay_receive_time"),
                row.get("date"),
            ]
        elif row_type == "bank":
            candidates = [
                row.get("trade_time"),
                row.get("pay_receive_time"),
                row.get("txn_date"),
                row.get("date"),
            ]
        else:
            candidates = [row.get("date")]
        detail_fields = row.get("_detail_fields") or row.get("detail_fields")
        if isinstance(detail_fields, dict):
            candidates.extend(detail_fields.get(key) for key in ("交易时间", "支付/收款时间", "记账日期", "日期", "申请日期"))
        for value in candidates:
            parsed = self._parse_date(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value in (None, "", "--", "—"):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return None
        match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
        if not match:
            return None
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    @staticmethod
    def _with_type(row: dict[str, Any], row_type: str) -> dict[str, Any]:
        payload = deepcopy(row)
        payload["type"] = row_type
        return payload

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("row_id") or "").strip()

    @staticmethod
    def _string_value(value: Any) -> str | None:
        if value in (None, "", "--", "—"):
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _format_amount(value: Decimal) -> str:
        return f"{value.quantize(CENT):.2f}"
