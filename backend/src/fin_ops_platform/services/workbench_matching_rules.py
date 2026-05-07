from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from itertools import combinations
from typing import Any

from fin_ops_platform.services.import_file_service import is_company_identity
from fin_ops_platform.services.imports import normalize_name
from fin_ops_platform.services.live_workbench_service import INTERNAL_TRANSFER_MATCH_WINDOW, clean_account_no
from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MAX_SUM_COMBINATION_SIZE = 6


class WorkbenchMatchingRules:
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
        resolved_settings = settings if isinstance(settings, dict) else {}
        resolved_versions = deepcopy(source_versions if isinstance(source_versions, dict) else {})
        oa = [self._with_type(row, "oa") for row in oa_rows]
        bank = [self._with_type(row, "bank") for row in bank_rows]
        invoices = [self._with_type(row, "invoice") for row in invoice_rows]

        candidates: list[dict[str, Any]] = []
        candidates.extend(self._oa_bank_exact_amount(scope_month, oa, bank, resolved_versions))
        candidates.extend(self._oa_multi_invoice_exact_sum(scope_month, oa, invoices, resolved_versions))
        candidates.extend(self._oa_bank_multi_invoice_exact_sum(scope_month, oa, bank, invoices, resolved_versions))
        candidates.extend(self._oa_item_invoice_exact_amount(scope_month, oa, invoices, resolved_versions))
        candidates.extend(self._bank_invoice_exact_amount(scope_month, bank, invoices, resolved_versions))
        candidates.extend(self._salary_personal_auto_match(scope_month, bank, resolved_versions))
        candidates.extend(self._internal_transfer_pair(scope_month, bank, resolved_versions))
        candidates.extend(
            self._oa_invoice_offset_auto_match(scope_month, oa, invoices, resolved_settings, resolved_versions)
        )
        candidates.extend(self._matching_engine_compatibility(scope_month, bank, invoices, resolved_versions))
        return self._mark_conflicts(self._dedupe_candidates(candidates))

    def _oa_bank_exact_amount(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for oa_row in sorted(oa_rows, key=self._row_id):
            oa_amount = self._amount(oa_row)
            if oa_amount is None:
                continue
            for bank_row in sorted(bank_rows, key=self._row_id):
                if self._direction(oa_row) != self._direction(bank_row):
                    continue
                if oa_amount != self._amount(bank_row):
                    continue
                candidates.append(
                    self._candidate(
                        scope_month,
                        rule_code="oa_bank_exact_amount",
                        rows=[oa_row, bank_row],
                        status="incomplete",
                        confidence="medium",
                        amount=oa_amount,
                        explanation="OA and one bank transaction have the same amount; invoice evidence is missing.",
                        source_versions=source_versions,
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
            match = self._find_unique_sum_match(invoices, target)
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
                match = self._find_unique_sum_match(invoices, target)
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
                rule_code = "exact_counterparty_amount_one_to_one" if same_counterparty else "bank_invoice_exact_amount"
                candidates.append(
                    self._candidate(
                        scope_month,
                        rule_code=rule_code,
                        rows=[bank_row, invoice_row],
                        status="auto_closed" if same_counterparty else "needs_review",
                        confidence="high" if same_counterparty else "medium",
                        amount=bank_amount,
                        explanation=(
                            "Counterparty, direction, and amount matched exactly."
                            if same_counterparty
                            else "Bank transaction and invoice amount matched exactly."
                        ),
                        source_versions=source_versions,
                    )
                )
        return candidates

    def _salary_personal_auto_match(
        self,
        scope_month: str,
        bank_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for bank_row in sorted(bank_rows, key=self._row_id):
            if self._direction(bank_row) != "outflow":
                continue
            remark = " ".join(str(bank_row.get(field) or "").strip() for field in ("summary", "remark"))
            counterparty = str(bank_row.get("counterparty_name") or "").strip()
            if "工资" not in remark or not counterparty or is_company_identity(None, counterparty):
                continue
            amount = self._amount(bank_row)
            if amount is None:
                continue
            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code="salary_personal_auto_match",
                    rows=[bank_row],
                    status="auto_closed",
                    confidence="high",
                    amount=amount,
                    explanation="Detected salary payment to an individual counterparty from bank summary or remark.",
                    source_versions=source_versions,
                )
            )
        return candidates

    def _internal_transfer_pair(
        self,
        scope_month: str,
        bank_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        outflows = sorted((row for row in bank_rows if self._direction(row) == "outflow"), key=self._bank_time_sort_key)
        inflows = sorted((row for row in bank_rows if self._direction(row) == "inflow"), key=self._bank_time_sort_key)
        candidates: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for outflow in outflows:
            if self._row_id(outflow) in used_ids or not self._is_company_bank_row(outflow):
                continue
            outflow_time = self._parse_row_time(outflow)
            outflow_amount = self._amount(outflow)
            if outflow_time is None or outflow_amount is None:
                continue
            best_match: tuple[timedelta, dict[str, Any]] | None = None
            for inflow in inflows:
                if self._row_id(inflow) in used_ids or not self._is_company_bank_row(inflow):
                    continue
                if outflow_amount != self._amount(inflow):
                    continue
                if not self._bank_accounts_distinct(outflow, inflow):
                    continue
                inflow_time = self._parse_row_time(inflow)
                if inflow_time is None:
                    continue
                delta = abs(inflow_time - outflow_time)
                if delta > INTERNAL_TRANSFER_MATCH_WINDOW:
                    continue
                if best_match is None or delta < best_match[0]:
                    best_match = (delta, inflow)
            if best_match is None:
                continue
            inflow = best_match[1]
            used_ids.update({self._row_id(outflow), self._row_id(inflow)})
            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code="internal_transfer_pair",
                    rows=[outflow, inflow],
                    status="auto_closed",
                    confidence="high",
                    amount=outflow_amount,
                    explanation="Detected equal internal transfer between different company bank accounts within the time window.",
                    source_versions=source_versions,
                )
            )
        return candidates

    def _oa_invoice_offset_auto_match(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        settings: dict[str, Any],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        applicant_names = {
            str(name).strip()
            for name in list(settings.get("offset_applicant_names") or settings.get("offset_applicants") or [])
            if str(name).strip()
        }
        if not applicant_names:
            return []
        candidates: list[dict[str, Any]] = []
        oa_by_id = {self._row_id(row): row for row in oa_rows}
        for invoice_row in sorted(invoice_rows, key=self._row_id):
            if str(invoice_row.get("source_kind") or "") != "oa_attachment_invoice":
                continue
            linked_oa_id = self._linked_oa_id(invoice_row)
            oa_row = oa_by_id.get(linked_oa_id or "")
            if oa_row is None:
                continue
            applicant_name = self._oa_applicant_name(oa_row)
            if applicant_name not in applicant_names:
                continue
            amount = self._amount(invoice_row) or self._amount(oa_row)
            if amount is None:
                continue
            versions = {**source_versions, "offset_display_tag": "冲", "offset_relation_mode": "oa_attachment_invoice"}
            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code="oa_invoice_offset_auto_match",
                    rows=[oa_row, invoice_row],
                    status="auto_closed",
                    confidence="high",
                    amount=amount,
                    explanation="Configured applicant OA attachment invoice auto matched for 冲 display.",
                    source_versions=versions,
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
            match = self._find_unique_sum_match(invoices, bank_amount)
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
            match = self._find_unique_sum_match(banks, invoice_amount)
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
        return [
            invoice
            for invoice in sorted(invoice_rows, key=self._row_id)
            if self._direction(invoice) == self._direction(oa_row)
            and self._counterparties_compatible(oa_row, invoice)
        ]

    def _find_unique_sum_match(
        self,
        rows: list[dict[str, Any]],
        target: Decimal,
    ) -> list[dict[str, Any]] | None:
        candidates = [
            (row, amount)
            for row in sorted(rows, key=self._row_id)
            if (amount := self._amount(row)) is not None and amount > ZERO
        ]
        if len(candidates) < 2:
            return None

        matches: list[list[dict[str, Any]]] = []
        max_size = min(MAX_SUM_COMBINATION_SIZE, len(candidates))
        for size in range(2, max_size + 1):
            for combo in combinations(candidates, size):
                total = sum((amount for _, amount in combo), ZERO).quantize(CENT)
                if total == target:
                    matches.append([row for row, _ in combo])
                    if len(matches) > 1:
                        return None
        return matches[0] if len(matches) == 1 else None

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

    def _is_company_bank_row(self, row: dict[str, Any]) -> bool:
        return is_company_identity(None, row.get("account_name")) and is_company_identity(
            None, row.get("counterparty_name")
        )

    @staticmethod
    def _bank_accounts_distinct(left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_account = clean_account_no(str(left.get("account_no") or ""))
        right_account = clean_account_no(str(right.get("account_no") or ""))
        return bool(left_account and right_account and left_account != right_account)

    def _bank_time_sort_key(self, row: dict[str, Any]) -> tuple[datetime, str]:
        parsed = self._parse_row_time(row) or datetime.min
        return parsed, self._row_id(row)

    def _parse_row_time(self, row: dict[str, Any]) -> datetime | None:
        for field_name in ("pay_receive_time", "trade_time", "txn_date", "issue_date"):
            parsed = self._parse_datetime(row.get(field_name))
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip().replace("/", "-")
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19] if "%S" in pattern else text[:16 if "%H" in pattern else 10], pattern)
            except ValueError:
                continue
        return None

    @staticmethod
    def _linked_oa_id(invoice_row: dict[str, Any]) -> str | None:
        for field_name in ("oa_row_id", "oa_id", "source_oa_row_id", "linked_oa_row_id", "parent_oa_row_id"):
            value = str(invoice_row.get(field_name) or "").strip()
            if value:
                return value
        metadata = invoice_row.get("metadata")
        if isinstance(metadata, dict):
            for field_name in ("oa_row_id", "oa_id", "source_oa_row_id"):
                value = str(metadata.get(field_name) or "").strip()
                if value:
                    return value
        return None

    @staticmethod
    def _oa_applicant_name(oa_row: dict[str, Any]) -> str:
        for field_name in ("applicant_name", "applicant", "submitter_name", "created_by_name"):
            value = str(oa_row.get(field_name) or "").strip()
            if value:
                return value
        detail_fields = oa_row.get("_detail_fields") or oa_row.get("detail_fields")
        if isinstance(detail_fields, dict):
            for field_name in ("申请人", "报销人", "提交人"):
                value = str(detail_fields.get(field_name) or "").strip()
                if value:
                    return value
        return ""
