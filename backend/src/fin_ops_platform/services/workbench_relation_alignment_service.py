from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_linking import oa_attachment_parent_oa_id


MAX_BANK_SUM_ROWS = 6
MAX_BANK_SUM_STATES = 20000
AMBIGUOUS_SUBSET_MATCH: tuple[str, ...] = ("__ambiguous__",)


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
        oa_id_set = set(oa_ids)
        links_by_oa: dict[str, dict[str, Any]] = {}
        diagnostics: list[dict[str, Any]] = []
        unresolved_row_ids: list[str] = []
        used_bank_ids: set[str] = set()
        track_unresolved = len(oa_ids) >= 2

        for invoice_row in invoice_rows:
            invoice_id = self._row_id(invoice_row)
            source_oa_id = self._source_oa_id(invoice_row, oa_id_set)
            if not invoice_id or not source_oa_id:
                continue
            link = self._link_for_oa(links_by_oa, source_oa_id)
            link["invoice_row_ids"].append(invoice_id)
            self._append_evidence(link, "invoice_source_oa")

        oa_amounts = {self._row_id(row): self._money(row.get("amount")) for row in oa_rows}
        bank_amounts = {self._row_id(row): self._bank_amount(row) for row in bank_rows}

        for bank_row in bank_rows:
            bank_id = self._row_id(bank_row)
            bank_amount = bank_amounts.get(bank_id)
            if not bank_id or bank_amount is None:
                continue
            candidate_oa_ids = [
                oa_id
                for oa_id in oa_ids
                if oa_amounts.get(oa_id) is not None and oa_amounts.get(oa_id) == bank_amount
            ]
            if len(candidate_oa_ids) == 1:
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
            oa_ids=oa_ids,
            oa_amounts=oa_amounts,
            bank_rows=remaining_bank_rows,
            bank_amounts=bank_amounts,
        )
        used_subset_bank_ids: set[str] = set()
        for oa_id in oa_ids:
            matches = subset_matches_by_oa.get(oa_id) or []
            if len(matches) != 1:
                continue
            bank_ids = list(matches[0])
            if used_subset_bank_ids.intersection(bank_ids):
                continue
            link = self._link_for_oa(links_by_oa, oa_id)
            link["bank_row_ids"].extend(bank_ids)
            self._append_evidence(link, "unique_bank_sum")
            used_subset_bank_ids.update(bank_ids)

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
    def _source_oa_id(cls, row: dict[str, Any], oa_ids: set[str]) -> str:
        for key in ("derived_from_oa_id", "source_oa_id", "source_oa_row_id", "oa_row_id", "oa_id"):
            value = oa_attachment_parent_oa_id(row.get(key))
            if value in oa_ids:
                return value
        detail_fields = row.get("detail_fields")
        if isinstance(detail_fields, dict):
            for key in ("derived_from_oa_id", "source_oa_id", "source_oa_row_id", "oa_row_id", "oa_id"):
                value = oa_attachment_parent_oa_id(detail_fields.get(key))
                if value in oa_ids:
                    return value
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
            candidate_matches: list[list[str]] = []
            ambiguous = False
            for size in range(2, max_size + 1):
                bank_ids = states_by_size[size].get(target_amount)
                if bank_ids is None:
                    continue
                if bank_ids == AMBIGUOUS_SUBSET_MATCH:
                    ambiguous = True
                    continue
                candidate_matches.append(list(bank_ids))
            if ambiguous or len(candidate_matches) > 1:
                matches[oa_id] = [candidate_matches[0], []] if candidate_matches else [[], []]
            else:
                matches[oa_id] = candidate_matches
        return matches
