from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_linking import oa_attachment_matches_oa
from fin_ops_platform.services.workbench_invoice_direction import invoice_flow_direction_from_row, normalize_invoice_kind_from_row


CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class WorkbenchAmountCheckService:
    def workbench_anomaly(
        self,
        rows_by_type: dict[str, list[dict[str, Any]]],
        *,
        relation_id: str,
    ) -> dict[str, Any] | None:
        oa_rows = list(rows_by_type.get("oa") or [])
        bank_rows = list(rows_by_type.get("bank") or [])
        invoice_rows = list(rows_by_type.get("invoice") or [])
        if not oa_rows:
            return None

        items = self._expense_item_anomalies(
            oa_rows,
            invoice_rows,
            relation_id=relation_id,
        )
        has_expense_items = items is not None
        items = items or []
        amount_check = self.check(
            {"oa": oa_rows, "bank": bank_rows, "invoice": invoice_rows}
        )
        totals = {
            "oa": self._decimal(amount_check.get("oa_total")),
            "bank": self._decimal(amount_check.get("bank_total")),
            "invoice": self._decimal(amount_check.get("invoice_total")),
        }
        for pane, pane_rows in (
            ("oa", oa_rows),
            ("bank", bank_rows),
            ("invoice", invoice_rows),
        ):
            if any(self._amount(row) is None for row in pane_rows):
                totals[pane] = None
        for left, right, code in (
            ("oa", "bank", "oa_bank_amount_mismatch"),
            ("oa", "invoice", "oa_invoice_amount_mismatch"),
            ("bank", "invoice", "bank_invoice_amount_mismatch"),
        ):
            if has_expense_items and code == "oa_invoice_amount_mismatch":
                continue
            left_total = totals[left]
            right_total = totals[right]
            if left_total is None or right_total is None or left_total == right_total:
                continue
            items.append(
                self._anomaly_item(
                    code=code,
                    relation_id=relation_id,
                    comparison_unit_id=str(relation_id or "").strip(),
                    source_oa_ids=[self._row_id(row) for row in oa_rows],
                    source_expense_item_ids=[],
                    oa_total=totals["oa"],
                    bank_total=totals["bank"],
                    invoice_total=totals["invoice"],
                    invoice_rows=invoice_rows,
                    attachment_file_count=0,
                    mismatch_pair=(left, right),
                )
            )
        if not items:
            return None
        fingerprint_source = "\0".join(
            [str(relation_id or "").strip(), *sorted(str(item["fingerprint"]) for item in items)]
        )
        return {
            "code": "workbench_anomaly",
            "fingerprint": sha256(fingerprint_source.encode("utf-8")).hexdigest(),
            "items": items,
        }

    def _expense_item_anomalies(
        self,
        oa_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        *,
        relation_id: str,
    ) -> list[dict[str, Any]] | None:
        expense_units = [
            (oa_row, item)
            for oa_row in oa_rows
            for item in list(oa_row.get("expense_items") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        if not expense_units:
            return None

        expense_by_id = {
            str(expense_item["id"]).strip(): (oa_row, expense_item)
            for oa_row, expense_item in expense_units
        }
        invoice_by_id = {
            self._row_id(invoice_row): invoice_row
            for invoice_row in invoice_rows
            if self._row_id(invoice_row)
        }
        item_invoice_ids: dict[str, set[str]] = {item_id: set() for item_id in expense_by_id}
        invoice_item_ids: dict[str, set[str]] = {}
        unassigned_invoice_rows: list[dict[str, Any]] = []
        for invoice_id, invoice_row in invoice_by_id.items():
            source_item_ids = {
                item_id
                for item_id in self._source_expense_item_ids(invoice_row)
                if item_id in expense_by_id
            }
            if not source_item_ids:
                unassigned_invoice_rows.append(invoice_row)
                continue
            invoice_item_ids[invoice_id] = source_item_ids
            for item_id in source_item_ids:
                item_invoice_ids[item_id].add(invoice_id)

        anomalies: list[dict[str, Any]] = []
        for expense_item_id, (oa_row, expense_item) in expense_by_id.items():
            if item_invoice_ids[expense_item_id]:
                continue
            attachment_count = self._non_negative_int(expense_item.get("attachment_file_count"))
            if attachment_count <= 0:
                continue
            source_oa_id = self._row_id(oa_row)
            matching_unassigned_invoices = [
                row
                for row in unassigned_invoice_rows
                if self._invoice_matches_oa(row, source_oa_id)
            ]
            parse_failed_count = self._non_negative_int(
                expense_item.get("attachment_parse_failed_count")
            )
            code = (
                "oa_invoice_attachment_unassigned"
                if matching_unassigned_invoices
                else "oa_invoice_attachment_parse_failed"
                if parse_failed_count > 0
                else "oa_invoice_attachment_missing"
            )
            anomalies.append(
                self._anomaly_item(
                    code=code,
                    relation_id=relation_id,
                    comparison_unit_id=expense_item_id,
                    source_oa_ids=[source_oa_id],
                    source_expense_item_ids=[expense_item_id],
                    oa_total=self._decimal(expense_item.get("amount")),
                    bank_total=None,
                    invoice_total=None,
                    invoice_rows=matching_unassigned_invoices,
                    attachment_file_count=attachment_count,
                    mismatch_pair=None,
                )
            )

        remaining_item_ids = {
            item_id for item_id, invoice_ids in item_invoice_ids.items() if invoice_ids
        }
        while remaining_item_ids:
            pending_items = [remaining_item_ids.pop()]
            component_item_ids: set[str] = set()
            component_invoice_ids: set[str] = set()
            while pending_items:
                item_id = pending_items.pop()
                if item_id in component_item_ids:
                    continue
                component_item_ids.add(item_id)
                for invoice_id in item_invoice_ids[item_id]:
                    if invoice_id in component_invoice_ids:
                        continue
                    component_invoice_ids.add(invoice_id)
                    pending_items.extend(
                        linked_item_id
                        for linked_item_id in invoice_item_ids.get(invoice_id, set())
                        if linked_item_id not in component_item_ids
                    )
            remaining_item_ids.difference_update(component_item_ids)

            ordered_item_ids = sorted(component_item_ids)
            component_invoices = [invoice_by_id[invoice_id] for invoice_id in sorted(component_invoice_ids)]
            oa_amounts = [
                self._decimal(expense_by_id[item_id][1].get("amount"))
                for item_id in ordered_item_ids
            ]
            oa_total = (
                None
                if any(amount is None for amount in oa_amounts)
                else sum((amount for amount in oa_amounts if amount is not None), ZERO).quantize(CENT)
            )
            invoice_total = self._strict_sum_amounts(component_invoices)
            if oa_total is None or invoice_total is None or oa_total == invoice_total:
                continue
            source_oa_ids = sorted({
                self._row_id(expense_by_id[item_id][0])
                for item_id in ordered_item_ids
                if self._row_id(expense_by_id[item_id][0])
            })
            comparison_unit_id = (
                ordered_item_ids[0]
                if len(ordered_item_ids) == 1
                else "expense-component:" + sha256("\0".join(ordered_item_ids).encode("utf-8")).hexdigest()[:24]
            )
            anomalies.append(
                self._anomaly_item(
                    code="oa_invoice_amount_mismatch",
                    relation_id=relation_id,
                    comparison_unit_id=comparison_unit_id,
                    source_oa_ids=source_oa_ids,
                    source_expense_item_ids=ordered_item_ids,
                    oa_total=oa_total,
                    bank_total=None,
                    invoice_total=invoice_total,
                    invoice_rows=component_invoices,
                    attachment_file_count=sum(
                        self._non_negative_int(expense_by_id[item_id][1].get("attachment_file_count"))
                        for item_id in ordered_item_ids
                    ),
                    mismatch_pair=("oa", "invoice"),
                )
            )
        return anomalies

    def _anomaly_item(
        self,
        *,
        code: str,
        relation_id: str,
        comparison_unit_id: str,
        source_oa_ids: list[str],
        source_expense_item_ids: list[str],
        oa_total: Decimal | None,
        bank_total: Decimal | None,
        invoice_total: Decimal | None,
        invoice_rows: list[dict[str, Any]],
        attachment_file_count: int,
        mismatch_pair: tuple[str, str] | None,
    ) -> dict[str, Any]:
        invoice_row_ids = sorted(self._row_id(row) for row in invoice_rows if self._row_id(row))
        label = {
            "oa_invoice_attachment_missing": "OA发票附件缺失",
            "oa_invoice_attachment_parse_failed": "OA附件解析失败",
            "oa_invoice_attachment_unassigned": "OA发票待归属",
            "oa_bank_amount_mismatch": "OA流水金额不一致",
            "oa_invoice_amount_mismatch": "OA发票金额不一致",
            "bank_invoice_amount_mismatch": "流水发票金额不一致",
        }[code]
        fingerprint_source = "\0".join(
            [
                str(relation_id or "").strip(),
                code,
                comparison_unit_id,
                self._format_amount(oa_total) or "",
                self._format_amount(bank_total) or "",
                self._format_amount(invoice_total) or "",
                str(attachment_file_count),
                *invoice_row_ids,
            ]
        )
        return {
            "code": code,
            "label": label,
            "fingerprint": sha256(fingerprint_source.encode("utf-8")).hexdigest(),
            "comparison_unit_id": comparison_unit_id,
            "source_oa_ids": [value for value in source_oa_ids if value],
            "source_expense_item_ids": [value for value in source_expense_item_ids if value],
            "oa_total": self._format_amount(oa_total),
            "bank_total": self._format_amount(bank_total),
            "invoice_total": self._format_amount(invoice_total),
            "amount_delta": self._mismatch_delta(
                mismatch_pair,
                oa_total=oa_total,
                bank_total=bank_total,
                invoice_total=invoice_total,
            ),
            "mismatch_pair": list(mismatch_pair) if mismatch_pair else None,
            "invoice_row_ids": invoice_row_ids,
            "attachment_file_count": attachment_file_count,
        }

    def _mismatch_delta(
        self,
        mismatch_pair: tuple[str, str] | None,
        *,
        oa_total: Decimal | None,
        bank_total: Decimal | None,
        invoice_total: Decimal | None,
    ) -> str | None:
        if mismatch_pair is None:
            return None
        totals = {"oa": oa_total, "bank": bank_total, "invoice": invoice_total}
        left, right = (totals[value] for value in mismatch_pair)
        if left is None or right is None:
            return None
        return self._format_amount(abs(left - right))

    @staticmethod
    def _source_expense_item_ids(row: dict[str, Any]) -> list[str]:
        values = row.get("source_expense_item_ids")
        source_ids = [
            str(value).strip()
            for value in list(values or [])
            if str(value).strip()
        ] if isinstance(values, (list, tuple, set)) else []
        for source_link in list(row.get("source_links") or []):
            if not isinstance(source_link, dict):
                continue
            if str(source_link.get("source_type") or "").strip() != "oa_attachment_invoice":
                continue
            source_item_id = str(source_link.get("source_expense_item_id") or "").strip()
            if source_item_id:
                source_ids.append(source_item_id)
        return list(dict.fromkeys(source_ids))

    @staticmethod
    def _invoice_matches_oa(invoice_row: dict[str, Any], oa_row_id: str) -> bool:
        if oa_attachment_matches_oa(invoice_row, oa_row_id):
            return True
        return any(
            oa_attachment_matches_oa(source_link, oa_row_id)
            for source_link in list(invoice_row.get("source_links") or [])
            if isinstance(source_link, dict)
            and str(source_link.get("source_type") or "").strip() == "oa_attachment_invoice"
        )

    @staticmethod
    def _non_negative_int(value: Any) -> int:
        try:
            return max(0, int(str(value or "0")))
        except ValueError:
            return 0

    def summarize(self, rows_by_type: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        normalized_rows = {
            "oa": list(rows_by_type.get("oa") or []),
            "bank": list(rows_by_type.get("bank") or []),
            "invoice": list(rows_by_type.get("invoice") or []),
        }
        oa_total = self._sum_amounts(normalized_rows["oa"]) or ZERO
        bank_expense_rows: list[dict[str, Any]] = []
        bank_income_rows: list[dict[str, Any]] = []
        input_invoice_rows: list[dict[str, Any]] = []
        output_invoice_rows: list[dict[str, Any]] = []
        unknown_direction_row_ids: list[str] = []

        for row in normalized_rows["bank"]:
            direction = self._bank_direction(row)
            if direction == "expense":
                bank_expense_rows.append(row)
            elif direction == "income":
                bank_income_rows.append(row)
            else:
                unknown_direction_row_ids.append(self._row_id(row))

        for row in normalized_rows["invoice"]:
            direction = self._invoice_direction(row)
            if direction == "input":
                input_invoice_rows.append(row)
            elif direction == "output":
                output_invoice_rows.append(row)
            else:
                unknown_direction_row_ids.append(self._row_id(row))

        bank_expense_total = self._sum_amounts(bank_expense_rows) or ZERO
        bank_income_total = self._sum_amounts(bank_income_rows) or ZERO
        input_invoice_total = self._sum_amounts(input_invoice_rows) or ZERO
        output_invoice_total = self._sum_amounts(output_invoice_rows) or ZERO
        has_unknown_direction = bool(unknown_direction_row_ids)

        expense_relation = (
            "unknown_direction"
            if has_unknown_direction
            else self._expense_relation(
                has_oa=bool(normalized_rows["oa"]),
                has_bank=bool(bank_expense_rows),
                has_invoice=bool(input_invoice_rows),
                oa_total=oa_total,
                bank_total=bank_expense_total,
                invoice_total=input_invoice_total,
            )
        )
        income_relation = (
            "unknown_direction"
            if has_unknown_direction
            else self._income_relation(
                has_bank=bool(bank_income_rows),
                has_invoice=bool(output_invoice_rows),
                bank_total=bank_income_total,
                invoice_total=output_invoice_total,
            )
        )

        return {
            "oa_total": self._format_amount(oa_total),
            "bank_expense_total": self._format_amount(bank_expense_total),
            "bank_income_total": self._format_amount(bank_income_total),
            "input_invoice_total": self._format_amount(input_invoice_total),
            "output_invoice_total": self._format_amount(output_invoice_total),
            "expense_relation": expense_relation,
            "income_relation": income_relation,
            "has_unknown_direction": has_unknown_direction,
            "unknown_direction_row_ids": unknown_direction_row_ids,
        }

    def check(self, rows_by_type: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        normalized_rows = {
            "oa": list(rows_by_type.get("oa") or []),
            "bank": list(rows_by_type.get("bank") or []),
            "invoice": list(rows_by_type.get("invoice") or []),
        }
        direction, has_direction_conflict = self._check_direction(normalized_rows)
        bank_totals = self._bank_totals_for_direction(
            normalized_rows["bank"],
            direction,
        )
        totals = {
            "oa_total": self._sum_amounts(normalized_rows["oa"]),
            "bank_total": bank_totals["net"],
            "invoice_total": self._pane_total_for_direction(normalized_rows["invoice"], direction),
        }
        directions = self._directions(normalized_rows)
        has_direction_gap = any(
            self._row_direction(row) is None
            for rows in normalized_rows.values()
            for row in rows
        )
        comparable = {key: value for key, value in totals.items() if value is not None}
        mismatch_fields: list[str] = []
        status = "matched"
        requires_note = False

        if has_direction_gap or has_direction_conflict or (direction == "unknown" and not directions):
            status = "unknown"
            requires_note = True
        elif direction != "unknown" and len(comparable) >= 2:
            mismatch_fields = self._mismatch_fields_for_totals(comparable)
            if mismatch_fields:
                status = "mismatch"
                requires_note = True

        return {
            "status": status,
            "direction": direction,
            "oa_total": self._format_amount(totals["oa_total"]),
            "bank_total": self._format_amount(totals["bank_total"]),
            "bank_gross_total": self._format_amount(bank_totals["gross"]),
            "bank_contra_total": self._format_amount(bank_totals["contra"]),
            "bank_net_total": self._format_amount(bank_totals["net"]),
            "invoice_total": self._format_amount(totals["invoice_total"]),
            "oa_amount": self._format_amount(totals["oa_total"]),
            "bank_amount": self._format_amount(totals["bank_total"]),
            "amount_delta": self._format_amount(self._amount_delta(comparable)),
            "mismatch_fields": mismatch_fields,
            "requires_note": requires_note,
        }

    def _check_direction(self, rows_by_type: dict[str, list[dict[str, Any]]]) -> tuple[str, bool]:
        non_bank_directions = {
            direction
            for row_type in ("oa", "invoice")
            for row in rows_by_type.get(row_type, [])
            for direction in (self._row_direction(row),)
            if direction is not None
        }
        if len(non_bank_directions) == 1:
            return next(iter(non_bank_directions)), False
        if len(non_bank_directions) > 1:
            return "unknown", True

        directions = self._directions(rows_by_type)
        if len(directions) == 1:
            return next(iter(directions)), False
        return "unknown", False

    def _bank_totals_for_direction(
        self,
        rows: list[dict[str, Any]],
        direction: str,
    ) -> dict[str, Decimal | None]:
        if not rows:
            return {"gross": None, "contra": None, "net": None}
        if direction not in {"payment", "receipt"}:
            total = self._sum_amounts(rows)
            return {"gross": total, "contra": ZERO, "net": total}

        directed_rows = [
            (row, row_direction)
            for row in rows
            for row_direction in (self._row_direction(row),)
            if row_direction in {"payment", "receipt"}
        ]
        if not directed_rows:
            total = self._sum_amounts(rows)
            return {"gross": total, "contra": ZERO, "net": total}

        gross_rows = [row for row, row_direction in directed_rows if row_direction == direction]
        contra_rows = [
            row
            for row, row_direction in directed_rows
            if row_direction != direction
        ]
        gross = self._sum_amounts(gross_rows) or ZERO
        contra = self._sum_amounts(contra_rows) or ZERO
        return {
            "gross": gross,
            "contra": contra,
            "net": (gross - contra).quantize(CENT),
        }

    def _pane_total_for_direction(self, rows: list[dict[str, Any]], direction: str) -> Decimal | None:
        if direction not in {"payment", "receipt"}:
            return self._sum_amounts(rows)
        matching_rows = [row for row in rows if self._row_direction(row) == direction]
        if matching_rows:
            return self._sum_amounts(matching_rows)
        known_direction_rows = [row for row in rows if self._row_direction(row) is not None]
        if known_direction_rows:
            return ZERO
        return self._sum_amounts(rows)

    def _amount_delta(self, comparable: dict[str, Decimal]) -> Decimal | None:
        if len(comparable) < 2:
            return None
        values = list(comparable.values())
        return (max(values) - min(values)).quantize(CENT)

    def _mismatch_fields_for_totals(self, comparable: dict[str, Decimal]) -> list[str]:
        if len(comparable) < 2:
            return []

        amount_groups: dict[Decimal, list[str]] = {}
        for key, value in comparable.items():
            amount_groups.setdefault(value, []).append(key)

        if len(amount_groups) == 1:
            return []

        if len(comparable) == 2:
            return list(comparable.keys())

        isolated_groups = [fields for fields in amount_groups.values() if len(fields) == 1]
        if len(isolated_groups) == 1:
            return isolated_groups[0]

        return list(comparable.keys())

    def _sum_amounts(self, rows: list[dict[str, Any]]) -> Decimal | None:
        amounts = [amount for amount in (self._amount(row) for row in rows) if amount is not None]
        if not amounts:
            return None
        return sum(amounts, ZERO).quantize(CENT)

    def _strict_sum_amounts(self, rows: list[dict[str, Any]]) -> Decimal | None:
        amounts = [self._amount(row) for row in rows]
        if not amounts or any(amount is None for amount in amounts):
            return None
        return sum((amount for amount in amounts if amount is not None), ZERO).quantize(CENT)

    def _directions(self, rows_by_type: dict[str, list[dict[str, Any]]]) -> set[str]:
        return {
            direction
            for rows in rows_by_type.values()
            for direction in (self._row_direction(row) for row in rows)
            if direction is not None
        }

    def _row_direction(self, row: dict[str, Any]) -> str | None:
        row_type = str(row.get("type", ""))
        if row_type == "oa":
            apply_type = str(row.get("apply_type") or "")
            return "receipt" if ("收" in apply_type and "付" not in apply_type) else "payment"
        if row_type == "bank":
            debit_amount = self._decimal(row.get("debit_amount"))
            credit_amount = self._decimal(row.get("credit_amount"))
            if debit_amount is not None and debit_amount > ZERO:
                return "payment"
            if credit_amount is not None and credit_amount > ZERO:
                return "receipt"
            txn_direction = str(row.get("txn_direction") or "").lower()
            if txn_direction in {"outflow", "expense", "payment"}:
                return "payment"
            if txn_direction in {"inflow", "income", "receipt"}:
                return "receipt"
            return None
        if row_type == "invoice":
            direction = invoice_flow_direction_from_row(row)
            if direction == "inflow":
                return "receipt"
            if direction == "outflow":
                return "payment"
            return None
        return None

    def _bank_direction(self, row: dict[str, Any]) -> str | None:
        debit_amount = self._decimal(row.get("debit_amount"))
        credit_amount = self._decimal(row.get("credit_amount"))
        if debit_amount is not None and debit_amount > ZERO:
            return "expense"
        if credit_amount is not None and credit_amount > ZERO:
            return "income"
        txn_direction = str(row.get("txn_direction") or row.get("direction") or "").lower()
        if txn_direction in {"outflow", "expense", "payment", "pay", "支出", "付款"}:
            return "expense"
        if txn_direction in {"inflow", "income", "receipt", "receive", "收入", "收款"}:
            return "income"
        return None

    def _invoice_direction(self, row: dict[str, Any]) -> str | None:
        invoice_direction = str(row.get("invoice_direction") or "").lower()
        invoice_kind = normalize_invoice_kind_from_row(row)
        if invoice_direction in {"input", "expense"} or invoice_kind == "input":
            return "input"
        if invoice_direction in {"output", "income"} or invoice_kind == "output":
            return "output"
        return None

    def _expense_relation(
        self,
        *,
        has_oa: bool,
        has_bank: bool,
        has_invoice: bool,
        oa_total: Decimal,
        bank_total: Decimal,
        invoice_total: Decimal,
    ) -> str:
        if has_oa and has_bank and has_invoice:
            if oa_total == bank_total == invoice_total:
                return "all_equal"
            if oa_total == bank_total:
                return (
                    "oa_equals_bank_greater_than_input_invoice"
                    if oa_total > invoice_total
                    else "oa_equals_bank_less_than_input_invoice"
                )
            if oa_total == invoice_total:
                return (
                    "oa_equals_input_invoice_greater_than_bank"
                    if oa_total > bank_total
                    else "oa_equals_input_invoice_less_than_bank"
                )
            if bank_total == invoice_total:
                return (
                    "bank_equals_input_invoice_greater_than_oa"
                    if bank_total > oa_total
                    else "bank_equals_input_invoice_less_than_oa"
                )
            return "all_different"
        if has_oa and has_bank:
            if oa_total == bank_total:
                return "oa_equals_bank_missing_input_invoice"
            return "oa_greater_than_bank_missing_input_invoice" if oa_total > bank_total else "oa_less_than_bank_missing_input_invoice"
        if has_oa and has_invoice:
            if oa_total == invoice_total:
                return "oa_equals_input_invoice_missing_bank"
            return "oa_greater_than_input_invoice_missing_bank" if oa_total > invoice_total else "oa_less_than_input_invoice_missing_bank"
        if has_bank and has_invoice:
            if bank_total == invoice_total:
                return "bank_equals_input_invoice_missing_oa"
            return "bank_greater_than_input_invoice_missing_oa" if bank_total > invoice_total else "bank_less_than_input_invoice_missing_oa"
        if has_oa:
            return "only_oa"
        if has_bank:
            return "only_bank_expense"
        if has_invoice:
            return "only_input_invoice"
        return "not_applicable"

    def _income_relation(
        self,
        *,
        has_bank: bool,
        has_invoice: bool,
        bank_total: Decimal,
        invoice_total: Decimal,
    ) -> str:
        if has_bank and has_invoice:
            if bank_total == invoice_total:
                return "income_equals_invoice"
            return "income_greater_than_invoice" if bank_total > invoice_total else "income_less_than_invoice"
        if has_bank:
            return "only_income_bank"
        if has_invoice:
            return "only_output_invoice"
        return "not_applicable"

    def _amount(self, row: dict[str, Any]) -> Decimal | None:
        row_type = str(row.get("type", ""))
        if row_type == "bank":
            debit_amount = self._decimal(row.get("debit_amount"))
            if debit_amount is not None and debit_amount > ZERO:
                return debit_amount
            return self._decimal(row.get("credit_amount") or row.get("amount"))
        if row_type == "invoice":
            return self._decimal(row.get("total_with_tax") or row.get("amount"))
        if row_type == "oa":
            reconciliation_amount = self._oa_reconciliation_amount(row)
            if reconciliation_amount is not None:
                return reconciliation_amount
        return self._decimal(
            row.get("amount")
            or row.get("reimbursement_amount")
            or row.get("payment_amount")
            or row.get("apply_amount")
        )

    def _oa_reconciliation_amount(self, row: dict[str, Any]) -> Decimal | None:
        explicit_amount = self._decimal(row.get("reconciliation_amount"))
        if explicit_amount is not None:
            return explicit_amount

        detail_fields = row.get("detail_fields") or row.get("_detail_fields")
        if not isinstance(detail_fields, dict):
            return None
        amount_source = str(row.get("amount_source") or detail_fields.get("金额来源") or "").strip()
        if amount_source not in {"header", "主表总金额"}:
            return None
        if "金额差异" not in detail_fields and not isinstance(row.get("amount_mismatch"), dict):
            return None
        detail_sum = self._decimal(detail_fields.get("明细金额合计"))
        if detail_sum is None:
            return None
        return detail_sum

    @staticmethod
    def _format_amount(value: Decimal | None) -> str | None:
        if value is None:
            return None
        return f"{value.quantize(CENT):.2f}"

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("row_id") or "")

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value in (None, "", "--", "—"):
            return None
        try:
            return Decimal(str(value).replace(",", "")).quantize(CENT)
        except (InvalidOperation, ValueError):
            return None
