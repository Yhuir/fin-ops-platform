from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_linking import (
    oa_attachment_parent_oa_id,
    oa_row_source_alias_map,
)
from fin_ops_platform.services.workbench_text_normalization import normalize_match_text

MAX_BANK_SUM_ROWS = 6
MAX_BANK_SUM_STATES = 20000
AMBIGUOUS_SUBSET_MATCH: tuple[str, ...] = ("__ambiguous__",)


def payment_phase(value: object) -> str:
    """Only unambiguous descriptions of this payment supply phase evidence."""
    text = str(value or "")
    matches = list(re.finditer(r"预付款?|首付款?|尾款", text))
    if any(re.search(r"(?:未|不|无|待|非)[^，。；,;]{0,4}$", text[:m.start()]) for m in matches):
        return ""
    phases = {"final" if m.group() == "尾款" else "advance" for m in matches}
    return next(iter(phases)) if len(phases) == 1 else ""


@dataclass(frozen=True, slots=True)
class PaymentEvidence:
    identity: str
    amount: Decimal
    payee: str = ""
    account: str = ""
    currency: str = "CNY"
    direction: str = "expenditure"
    day: date | None = None
    phase: str = ""


@dataclass(frozen=True, slots=True)
class PaymentPairing:
    pairs: dict[str, str]
    resource_limited: bool = False


def payment_conflicts(left: PaymentEvidence, right: PaymentEvidence) -> bool:
    return any(a and b and a != b for a, b in (
        (left.currency, right.currency), (left.direction, right.direction),
        (left.payee, right.payee), (left.account, right.account), (left.phase, right.phase),
    ))


def evidenced_payment_pairs(
    oa: list[PaymentEvidence], banks: list[PaymentEvidence],
) -> PaymentPairing:
    """Mutually unique business-evidence choices; no ordering or nearest-date guesses."""
    days: dict[tuple[Decimal, str, date], list[PaymentEvidence]] = {}
    phases: dict[tuple[Decimal, str, str], list[PaymentEvidence]] = {}
    for bank in banks:
        if bank.amount > 0 and bank.payee and bank.day is not None:
            days.setdefault((bank.amount, bank.payee, bank.day), []).append(bank)
            if bank.phase:
                phases.setdefault((bank.amount, bank.payee, bank.phase), []).append(bank)
    candidates: list[tuple[str, str, tuple[bool, bool]]] = []
    inspected = 0
    for item in oa:
        if item.day is None:
            continue
        same_day_banks = days.get((item.amount, item.payee, item.day), ())
        same_phase_banks = phases.get((item.amount, item.payee, item.phase), ())
        inspected += len(same_day_banks) + len(same_phase_banks)
        if inspected > MAX_BANK_SUM_STATES:
            return PaymentPairing({}, resource_limited=True)
        eligible = {b.identity: b for b in [*same_day_banks, *same_phase_banks]}
        for bank in eligible.values():
            if payment_conflicts(item, bank) or item.day is None or bank.day is None:
                continue
            same_day = item.day == bank.day
            same_phase = bool(item.phase and item.phase == bank.phase)
            if not (same_day or same_phase and abs((item.day - bank.day).days) <= 30):
                continue
            candidates.append((item.identity, bank.identity, (same_phase, same_day)))
    best_oa: dict[str, tuple[bool, bool]] = {}
    best_bank: dict[str, tuple[bool, bool]] = {}
    for oid, bid, rank in candidates:
        best_oa[oid] = max(best_oa.get(oid, rank), rank)
        best_bank[bid] = max(best_bank.get(bid, rank), rank)
    oa_counts = Counter(oid for oid, _bid, rank in candidates if rank == best_oa[oid])
    bank_counts = Counter(bid for _oid, bid, rank in candidates if rank == best_bank[bid])
    return PaymentPairing({
        oid: bid for oid, bid, rank in candidates
        if rank == best_oa[oid] == best_bank[bid] and oa_counts[oid] == bank_counts[bid] == 1
    })


def row_payment_evidence(row: dict[str, Any]) -> PaymentEvidence:
    """Adapt canonical Workbench rows, also used by Cost's relation display."""
    is_oa = row.get("type") == "oa"
    detail = row.get("detail_fields") or {}
    day_value = row.get("application_date") if is_oa else detail.get("txn_date") or row.get("trade_time")
    day = date.fromisoformat(str(day_value)[:10]) if day_value else None
    currency = str(row.get("currency") or "CNY").upper()
    if currency in {"RMB", "人民币", "人民币元", "元"}:
        currency = "CNY"
    direction = str(row.get("txn_direction") or "")
    if is_oa:
        apply_type = str(row.get("apply_type") or "")
        direction = "income" if "收" in apply_type and "付" not in apply_type else "expenditure"
    elif direction in {"out", "outflow", "expenditure", "debit", "expense", "支出", "付款"}:
        direction = "expenditure"
    elif direction in {"in", "inflow", "income", "credit", "收入", "收款"}:
        direction = "income"
    amount = (WorkbenchRelationAlignmentService._money(row.get("amount")) if is_oa
              else WorkbenchRelationAlignmentService._bank_amount(row))
    return PaymentEvidence(
        identity=row["id"], amount=amount if amount is not None else Decimal(0),
        payee=normalize_match_text(row.get("counterparty_name")),
        account=normalize_match_text(detail.get("收款账号") if is_oa else detail.get("counterparty_account_no") or detail.get("counterparty_account")),
        currency=currency, direction=direction, day=day,
        phase=payment_phase(row.get("reason") if is_oa else row.get("remark")),
    )


class WorkbenchRelationAlignmentService:
    def align_relation(
        self,
        *,
        rows_by_id: dict[str, dict[str, Any]],
        relation: dict[str, Any],
    ) -> dict[str, Any]:
        relation_row_ids = [
            str(row_id).strip()
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip() and str(row_id).strip() in rows_by_id
        ]
        scoped_rows = [rows_by_id[row_id] for row_id in relation_row_ids]
        oa_rows = [row for row in scoped_rows if self._row_type(row) == "oa"]
        bank_rows = [row for row in scoped_rows if self._row_type(row) == "bank"]
        invoice_rows = [row for row in scoped_rows if self._row_type(row) == "invoice"]
        oa_ids = [self._row_id(row) for row in oa_rows if self._row_id(row)]
        oa_aliases = oa_row_source_alias_map(oa_rows)
        links_by_oa: dict[str, dict[str, Any]] = {}
        diagnostics: list[dict[str, Any]] = []
        unresolved_row_ids: list[str] = []
        used_bank_ids: set[str] = set()
        track_unresolved = len(oa_ids) >= 2

        for invoice_row in invoice_rows:
            invoice_id = self._row_id(invoice_row)
            source_oa_id = self._source_oa_id(invoice_row, oa_aliases)
            if not invoice_id or not source_oa_id:
                continue
            link = self._link_for_oa(links_by_oa, source_oa_id)
            link["invoice_row_ids"].append(invoice_id)
            self._append_evidence(link, "invoice_source_oa")

        oa_amounts = {self._row_id(row): self._money(row.get("amount")) for row in oa_rows}
        bank_amounts = {self._row_id(row): self._bank_amount(row) for row in bank_rows}
        oa_evidence = {row["id"]: row_payment_evidence(row) for row in oa_rows}
        bank_evidence = {row["id"]: row_payment_evidence(row) for row in bank_rows}
        for bank_row in bank_rows:
            source_oa_id = self.bank_source_oa_id(bank_row, oa_aliases)
            if source_oa_id:
                link = self._link_for_oa(links_by_oa, source_oa_id)
                link["bank_row_ids"].append(bank_row["id"])
                self._append_evidence(link, "bank_source_oa")
                used_bank_ids.add(bank_row["id"])
        pairing = evidenced_payment_pairs(
            [e for oid, e in oa_evidence.items() if not links_by_oa.get(oid, {}).get("bank_row_ids")],
            [e for bid, e in bank_evidence.items() if bid not in used_bank_ids],
        )
        if pairing.resource_limited:
            diagnostics.append({"code": "payment_evidence_resource_limited"})
        for oa_id, bank_id in pairing.pairs.items():
            link = self._link_for_oa(links_by_oa, oa_id)
            link["bank_row_ids"].append(bank_id)
            self._append_evidence(link, "payment_business_evidence")
            used_bank_ids.add(bank_id)

        bank_amount_counts = Counter(amount for bid, amount in bank_amounts.items() if bid not in used_bank_ids)
        for bank_row in bank_rows:
            bank_id = self._row_id(bank_row)
            bank_amount = bank_amounts.get(bank_id)
            if not bank_id or bank_amount is None or bank_id in used_bank_ids:
                continue
            candidate_oa_ids = [
                oa_id
                for oa_id in oa_ids
                if oa_amounts.get(oa_id) is not None and oa_amounts.get(oa_id) == bank_amount
                and not links_by_oa.get(oa_id, {}).get("bank_row_ids")
                and not payment_conflicts(oa_evidence[oa_id], bank_evidence[bank_id])
            ]
            if len(candidate_oa_ids) == 1 and bank_amount_counts[bank_amount] == 1:
                link = self._link_for_oa(links_by_oa, candidate_oa_ids[0])
                link["bank_row_ids"].append(bank_id)
                self._append_evidence(link, "exact_amount")
                used_bank_ids.add(bank_id)
            elif track_unresolved and len(candidate_oa_ids) > 1:
                diagnostics.append(
                    {
                        "code": "ambiguous_bank_exact_amount",
                        "row_id": bank_id,
                        "candidate_oa_row_ids": candidate_oa_ids,
                    }
                )
                unresolved_row_ids.append(bank_id)

        remaining_bank_rows = [
            row
            for row in bank_rows
            if (bank_id := self._row_id(row)) and bank_id not in used_bank_ids and bank_id not in unresolved_row_ids
        ]
        subset_matches_by_oa = self._unique_subset_matches(
            oa_ids=[oa_id for oa_id in oa_ids if not links_by_oa.get(oa_id, {}).get("bank_row_ids")],
            oa_amounts=oa_amounts,
            bank_rows=remaining_bank_rows,
            bank_amounts=bank_amounts,
        )
        subset_usage = Counter(
            bank_id
            for matches in subset_matches_by_oa.values()
            if len(matches) == 1
            for bank_id in matches[0]
        )
        for oa_id in oa_ids:
            matches = subset_matches_by_oa.get(oa_id) or []
            if len(matches) != 1:
                continue
            bank_ids = list(matches[0])
            if any(subset_usage[bank_id] > 1 for bank_id in bank_ids):
                continue
            if any(payment_conflicts(oa_evidence[oa_id], bank_evidence[bid]) for bid in bank_ids):
                continue
            link = self._link_for_oa(links_by_oa, oa_id)
            link["bank_row_ids"].extend(bank_ids)
            self._append_evidence(link, "unique_bank_sum")

        for link in links_by_oa.values():
            self._append_evidence(link, "same_active_relation")

        linked_bank_ids = {
            bank_id
            for link in links_by_oa.values()
            for bank_id in list(link.get("bank_row_ids") or [])
        }
        for bank_row in bank_rows:
            bank_id = self._row_id(bank_row)
            if track_unresolved and bank_id and bank_id not in linked_bank_ids and bank_id not in unresolved_row_ids:
                unresolved_row_ids.append(bank_id)

        return {
            "version": 1,
            "source": "deterministic_relation_alignment",
            "links": [links_by_oa[oa_id] for oa_id in oa_ids if oa_id in links_by_oa],
            "unresolved_row_ids": unresolved_row_ids,
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _row_type(row: dict[str, Any]) -> str:
        return str(row.get("type") or "").strip()

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("row_id") or "").strip()

    @classmethod
    def bank_source_oa_id(cls, row: dict[str, Any], oa_aliases: dict[str, str]) -> str:
        # Bank top-level source_oa_* is also populated by display alignment.
        # Only persisted payload references can establish an explicit binding.
        detail = row.get("detail_fields") or {}
        for key in ("source_oa_row_id", "oa_row_id", "derived_from_oa_id", "source_workbench_row_id"):
            value = oa_attachment_parent_oa_id(detail.get(key))
            if value in oa_aliases:
                return oa_aliases[value]
        return ""

    @classmethod
    def _source_oa_id(cls, row: dict[str, Any], oa_aliases: dict[str, str]) -> str:
        for key in ("derived_from_oa_id", "source_oa_id", "source_oa_row_id", "oa_row_id", "oa_id"):
            value = oa_attachment_parent_oa_id(row.get(key))
            if value in oa_aliases:
                return oa_aliases[value]
        detail_fields = row.get("detail_fields")
        if isinstance(detail_fields, dict):
            for key in ("derived_from_oa_id", "source_oa_id", "source_oa_row_id", "oa_row_id", "oa_id"):
                value = oa_attachment_parent_oa_id(detail_fields.get(key))
                if value in oa_aliases:
                    return oa_aliases[value]
        return ""

    @classmethod
    def _bank_amount(cls, row: dict[str, Any]) -> Decimal | None:
        for key in ("amount", "debit_amount", "credit_amount"):
            amount = cls._money(row.get(key))
            if amount is not None and amount != Decimal("0.00"):
                return abs(amount)
        return None

    @staticmethod
    def _money(value: object) -> Decimal | None:
        normalized = str(value or "").strip().replace(",", "")
        if not normalized:
            return None
        try:
            return Decimal(normalized).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _link_for_oa(links_by_oa: dict[str, dict[str, Any]], oa_id: str) -> dict[str, Any]:
        return links_by_oa.setdefault(
            oa_id,
            {
                "oa_row_id": oa_id,
                "bank_row_ids": [],
                "invoice_row_ids": [],
                "evidence": [],
            },
        )

    @staticmethod
    def _append_evidence(link: dict[str, Any], evidence: str) -> None:
        if evidence not in link["evidence"]:
            link["evidence"].append(evidence)

    def _unique_subset_matches(
        self,
        *,
        oa_ids: list[str],
        oa_amounts: dict[str, Decimal | None],
        bank_rows: list[dict[str, Any]],
        bank_amounts: dict[str, Decimal | None],
    ) -> dict[str, list[list[str]]]:
        matches: dict[str, list[list[str]]] = {oa_id: [] for oa_id in oa_ids}
        target_amounts = {
            amount
            for oa_id in oa_ids
            if (amount := oa_amounts.get(oa_id)) is not None and amount > Decimal("0.00")
        }
        if not target_amounts:
            return matches
        max_target_amount = max(target_amounts)
        indexed_bank_rows = [
            (self._row_id(row), bank_amounts.get(self._row_id(row)))
            for row in bank_rows
            if self._row_id(row) and bank_amounts.get(self._row_id(row)) is not None
        ]
        max_size = min(MAX_BANK_SUM_ROWS, len(indexed_bank_rows))
        states_by_size: list[dict[Decimal, tuple[str, ...]]] = [dict() for _ in range(max_size + 1)]
        states_by_size[0][Decimal("0.00")] = ()
        state_count = 1
        overflowed = False

        for bank_id, amount in indexed_bank_rows:
            if amount is None or amount <= Decimal("0.00"):
                continue
            for size in range(max_size - 1, -1, -1):
                if not states_by_size[size]:
                    continue
                for subtotal, existing_bank_ids in list(states_by_size[size].items()):
                    new_total = subtotal + amount
                    if new_total > max_target_amount:
                        continue
                    new_bank_ids = (
                        AMBIGUOUS_SUBSET_MATCH
                        if existing_bank_ids == AMBIGUOUS_SUBSET_MATCH
                        else (*existing_bank_ids, bank_id)
                    )
                    bucket = states_by_size[size + 1]
                    previous = bucket.get(new_total)
                    if previous is None:
                        bucket[new_total] = new_bank_ids
                        state_count += 1
                    elif previous != new_bank_ids:
                        bucket[new_total] = AMBIGUOUS_SUBSET_MATCH
                    if state_count > MAX_BANK_SUM_STATES:
                        overflowed = True
                        break
                if overflowed:
                    break
            if overflowed:
                break

        if overflowed:
            return {oa_id: [[], []] for oa_id in oa_ids}

        for oa_id in oa_ids:
            target_amount = oa_amounts.get(oa_id)
            if target_amount is None:
                continue
            exact_matches: list[list[str]] = []
            ambiguous = False
            for size in range(2, max_size + 1):
                bank_ids = states_by_size[size].get(target_amount)
                if bank_ids is None:
                    continue
                if bank_ids == AMBIGUOUS_SUBSET_MATCH:
                    ambiguous = True
                    continue
                exact_matches.append(list(bank_ids))
            if ambiguous or len(exact_matches) > 1:
                matches[oa_id] = [exact_matches[0], []] if exact_matches else [[], []]
            else:
                matches[oa_id] = exact_matches
        return matches
