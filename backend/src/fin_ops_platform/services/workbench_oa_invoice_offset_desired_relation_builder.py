from __future__ import annotations

from typing import Callable


class WorkbenchOaInvoiceOffsetDesiredRelationBuilder:
    """Builds desired OA invoice offset auto-pair relations from raw Workbench payloads."""

    def __init__(
        self,
        *,
        applicant_names_provider: Callable[[], list[str]],
        serialize_value: Callable[[object], object],
        attachment_invoice_rows_for_oa: Callable[[dict[str, object], list[dict[str, object]]], list[dict[str, object]]],
        auto_pair_conflicts_with_manual_relation: Callable[[list[str]], bool],
        month_scope_for_relation: Callable[[list[dict[str, object]]], str],
        amount_check_for_rows_by_type: Callable[[dict[str, list[dict[str, object]]]], dict[str, object]] | None = None,
    ) -> None:
        self._applicant_names_provider = applicant_names_provider
        self._serialize_value = serialize_value
        self._attachment_invoice_rows_for_oa = attachment_invoice_rows_for_oa
        self._auto_pair_conflicts_with_manual_relation = auto_pair_conflicts_with_manual_relation
        self._month_scope_for_relation = month_scope_for_relation
        self._amount_check_for_rows_by_type = amount_check_for_rows_by_type

    def build(self, payload: dict[str, object]) -> dict[str, dict[str, object]]:
        applicant_names = self._applicant_names()
        if not applicant_names:
            return {}

        oa_rows: list[dict[str, object]] = []
        invoice_rows: list[dict[str, object]] = []
        for section in ("paired", "open"):
            section_payload = payload.get(section, {})
            if not isinstance(section_payload, dict):
                continue
            oa_rows.extend(
                self._serialized_dict(row)
                for row in list(section_payload.get("oa", []))
                if isinstance(row, dict)
            )
            invoice_rows.extend(
                self._serialized_dict(row)
                for row in list(section_payload.get("invoice", []))
                if isinstance(row, dict)
            )

        desired_relations: dict[str, dict[str, object]] = {}
        for oa_row in oa_rows:
            if str(oa_row.get("applicant", "")).strip() not in applicant_names:
                continue
            attachment_invoice_rows = self._attachment_invoice_rows_for_oa(oa_row, invoice_rows)
            if not attachment_invoice_rows:
                continue
            row_ids = [
                str(oa_row.get("id", "")).strip(),
                *[
                    str(invoice_row.get("id", "")).strip()
                    for invoice_row in attachment_invoice_rows
                    if str(invoice_row.get("id", "")).strip()
                ],
            ]
            row_ids = [row_id for row_id in row_ids if row_id]
            if len(row_ids) < 2 or self._auto_pair_conflicts_with_manual_relation(row_ids):
                continue
            case_id = f"CASE-OA-OFFSET-{row_ids[0]}"
            month_scope = self._month_scope_for_relation([oa_row, *attachment_invoice_rows])
            desired_relations[case_id] = {
                "case_id": case_id,
                "row_ids": row_ids,
                "row_types": ["oa", *(["invoice"] * (len(row_ids) - 1))],
                "month_scope": month_scope,
                "amount_check": self._amount_check(oa_row, attachment_invoice_rows),
            }
        return desired_relations

    def _serialized_dict(self, value: dict[str, object]) -> dict[str, object]:
        serialized = self._serialize_value(value)
        return dict(serialized) if isinstance(serialized, dict) else {}

    def _applicant_names(self) -> set[str]:
        return {
            str(name).strip()
            for name in self._applicant_names_provider()
            if str(name).strip()
        }

    def _amount_check(
        self,
        oa_row: dict[str, object],
        attachment_invoice_rows: list[dict[str, object]],
    ) -> dict[str, object]:
        if self._amount_check_for_rows_by_type is None:
            return {}
        amount_check = self._amount_check_for_rows_by_type(
            {
                "oa": [oa_row],
                "bank": [],
                "invoice": list(attachment_invoice_rows),
            }
        )
        return dict(amount_check) if isinstance(amount_check, dict) else {}
