from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import BANK_TRANSACTION_CATEGORY_DEFINITIONS
from fin_ops_platform.services.import_file_service import is_company_identity
from fin_ops_platform.services.live_workbench_service import INTERNAL_TRANSFER_MATCH_WINDOW, clean_account_no


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
WORKBENCH_SPECIAL_RULES_VERSION = "2026-05-exception-special-rule-detectors"
SALARY_PERSONAL_AUTO_MATCH = "salary_personal_auto_match"
INTERNAL_TRANSFER_PAIR = "internal_transfer_pair"
OA_INVOICE_OFFSET_AUTO_MATCH = "oa_invoice_offset_auto_match"
CASH_TURNOVER_DETECTED = "cash_turnover_detected"
EXTERNAL_TURNOVER_EVIDENCE = "external_turnover_evidence"
CASH_TURNOVER_TAG = "现金往来"
EXTERNAL_TURNOVER_TAG = "外部往来款"
MANUAL_TURNOVER_CATEGORY_CODES = {*BANK_TRANSACTION_CATEGORY_DEFINITIONS.keys(), "external_turnover"}
OFFSET_TAG = "冲"
CASH_COUNTERPARTY_KEYWORDS = ("陈秀云", "太宏", "韦代连")
CASH_FULL_TEXT_KEYWORDS = ("张双文公积金", "陈秀云社保")


class WorkbenchSpecialRuleDetector:
    def evaluate(
        self,
        *,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        resolved_settings = settings if isinstance(settings, dict) else {}
        oa = [self._with_type(row, "oa") for row in oa_rows]
        bank = [self._with_type(row, "bank") for row in bank_rows]
        invoices = [self._with_type(row, "invoice") for row in invoice_rows]

        evaluations: list[dict[str, Any]] = []
        evaluations.extend(self._internal_transfer_pair(bank))
        evaluations.extend(self._salary_personal_auto_match(bank))
        evaluations.extend(self._oa_invoice_offset_auto_match(oa, invoices, resolved_settings))
        evaluations.extend(self._offset_category_evidence(bank))
        evaluations.extend(self._cash_turnover_detected(bank))
        evaluations.extend(self._external_turnover_evidence(bank))
        return self._dedupe_evaluations(evaluations)

    def _salary_personal_auto_match(self, bank_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evaluations: list[dict[str, Any]] = []
        for bank_row in sorted(bank_rows, key=self._row_id):
            if self._direction(bank_row) != "outflow":
                continue
            summary = str(bank_row.get("summary") or "").strip()
            remark = str(bank_row.get("remark") or "").strip()
            text = " ".join(value for value in (summary, remark) if value)
            counterparty = str(bank_row.get("counterparty_name") or "").strip()
            matched_fields = [
                field_name
                for field_name, value in (("summary", summary), ("remark", remark))
                if "工资" in value
            ]
            if not matched_fields or not counterparty or is_company_identity(None, counterparty):
                continue
            amount = self._amount(bank_row)
            if amount is None:
                continue
            evaluations.append(
                self._evaluation(
                    rule_code=SALARY_PERSONAL_AUTO_MATCH,
                    confidence="high",
                    suggested_action_code="auto_close_salary_payment",
                    rows=[bank_row],
                    amount=amount,
                    status="auto_closed",
                    evidence={
                        "matched_fields": matched_fields,
                        "amount": self._format_amount(amount),
                        "counterparty_name": counterparty,
                        "summary": text,
                    },
                    display_tags=["工资"],
                    cost_policy="normal",
                )
            )
        return evaluations

    def _internal_transfer_pair(self, bank_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        outflows = sorted((row for row in bank_rows if self._direction(row) == "outflow"), key=self._bank_time_sort_key)
        inflows = sorted((row for row in bank_rows if self._direction(row) == "inflow"), key=self._bank_time_sort_key)
        evaluations: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for outflow in outflows:
            if self._row_id(outflow) in used_ids or not self._is_internal_transfer_candidate_row(outflow):
                continue
            outflow_time = self._parse_row_time(outflow)
            outflow_amount = self._amount(outflow)
            if outflow_time is None or outflow_amount is None:
                continue
            best_match: tuple[timedelta, dict[str, Any]] | None = None
            for inflow in inflows:
                if self._row_id(inflow) in used_ids or not self._is_internal_transfer_candidate_row(inflow):
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
            delta, inflow = best_match
            used_ids.update({self._row_id(outflow), self._row_id(inflow)})
            evaluations.append(
                self._evaluation(
                    rule_code=INTERNAL_TRANSFER_PAIR,
                    confidence="high",
                    suggested_action_code="auto_close_internal_transfer",
                    rows=[outflow, inflow],
                    amount=outflow_amount,
                    status="auto_closed",
                    evidence={
                        "matched_fields": self._internal_transfer_matched_fields(outflow, inflow),
                        "amount": self._format_amount(outflow_amount),
                        "outflow_row_id": self._row_id(outflow),
                        "inflow_row_id": self._row_id(inflow),
                        "time_delta_seconds": int(delta.total_seconds()),
                        "match_window_hours": int(INTERNAL_TRANSFER_MATCH_WINDOW.total_seconds() // 3600),
                    },
                    display_tags=["内部往来"],
                    cost_policy="exclude_all",
                )
            )
        return evaluations

    def _oa_invoice_offset_auto_match(
        self,
        oa_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        settings: dict[str, Any],
    ) -> list[dict[str, Any]]:
        applicant_names = {
            str(name).strip()
            for name in list(settings.get("offset_applicant_names") or settings.get("offset_applicants") or [])
            if str(name).strip()
        }
        if not applicant_names:
            return []
        evaluations: list[dict[str, Any]] = []
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
            evaluations.append(
                self._evaluation(
                    rule_code=OA_INVOICE_OFFSET_AUTO_MATCH,
                    confidence="high",
                    suggested_action_code="auto_close_oa_invoice_offset",
                    rows=[oa_row, invoice_row],
                    amount=amount,
                    status="auto_closed",
                    evidence={
                        "matched_fields": ["source_kind", "linked_oa_id", "applicant_name"],
                        "amount": self._format_amount(amount),
                        "linked_oa_id": linked_oa_id,
                        "applicant_name": applicant_name,
                    },
                    display_tags=[OFFSET_TAG],
                    cost_policy="exclude_all",
                )
            )
        return evaluations

    def _offset_category_evidence(self, bank_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evaluations: list[dict[str, Any]] = []
        for bank_row in sorted(bank_rows, key=self._row_id):
            if self._category_code(bank_row) != "offset":
                continue
            amount = self._amount(bank_row) or ZERO
            evaluations.append(
                self._evaluation(
                    rule_code=OA_INVOICE_OFFSET_AUTO_MATCH,
                    confidence="medium",
                    suggested_action_code="review_oa_invoice_offset",
                    rows=[bank_row],
                    amount=amount,
                    status="needs_review",
                    evidence={
                        "matched_fields": ["category_code"],
                        "amount": self._format_amount(amount),
                        "category_code": "offset",
                        "category_label": OFFSET_TAG,
                    },
                    display_tags=[OFFSET_TAG],
                    cost_policy="hint_only",
                )
            )
        return evaluations

    def _cash_turnover_detected(self, bank_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evaluations: list[dict[str, Any]] = []
        for bank_row in sorted(bank_rows, key=self._row_id):
            matches = self._cash_turnover_matches(bank_row)
            if not matches:
                continue
            amount = self._amount(bank_row) or ZERO
            evaluations.append(
                self._evaluation(
                    rule_code=CASH_TURNOVER_DETECTED,
                    confidence="medium",
                    suggested_action_code="review_cash_turnover",
                    rows=[bank_row],
                    amount=amount,
                    status="needs_review",
                    evidence={
                        "matched_fields": sorted({match["matched_field"] for match in matches}),
                        "amount": self._format_amount(amount),
                        "matches": matches,
                        **self._category_evidence(bank_row, expected_code="cash_turnover"),
                    },
                    display_tags=[CASH_TURNOVER_TAG],
                    cost_policy="hint_only",
                )
            )
        return evaluations

    def _external_turnover_evidence(self, bank_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evaluations: list[dict[str, Any]] = []
        for bank_row in sorted(bank_rows, key=self._row_id):
            category_code = self._category_code(bank_row)
            if category_code not in MANUAL_TURNOVER_CATEGORY_CODES:
                continue
            amount = self._amount(bank_row) or ZERO
            direction = self._direction(bank_row) or "unknown"
            category_label = str(bank_row.get("category_label") or "").strip() or EXTERNAL_TURNOVER_TAG
            category_path = [
                str(item).strip()
                for item in list(bank_row.get("category_path") or [])
                if str(item).strip()
            ]
            evaluations.append(
                self._evaluation(
                    rule_code=EXTERNAL_TURNOVER_EVIDENCE,
                    confidence="medium",
                    suggested_action_code="review_external_turnover",
                    rows=[bank_row],
                    amount=amount,
                    status="needs_review",
                    evidence={
                        "matched_fields": ["category_code"],
                        "amount": self._format_amount(amount),
                        "category_code": category_code,
                        "category_label": category_label,
                        "category_path": category_path,
                        "direction": direction,
                    },
                    display_tags=[category_label],
                    cost_policy="hint_only",
                )
            )
        return evaluations

    def _evaluation(
        self,
        *,
        rule_code: str,
        confidence: str,
        suggested_action_code: str,
        rows: list[dict[str, Any]],
        amount: Decimal,
        status: str,
        evidence: dict[str, Any],
        display_tags: list[str],
        cost_policy: str,
    ) -> dict[str, Any]:
        oa_ids = [self._row_id(row) for row in rows if row.get("type") == "oa"]
        bank_ids = [self._row_id(row) for row in rows if row.get("type") == "bank"]
        invoice_ids = [self._row_id(row) for row in rows if row.get("type") == "invoice"]
        return {
            "rule_code": rule_code,
            "confidence": confidence,
            "suggested_action_code": suggested_action_code,
            "row_ids": sorted([*oa_ids, *bank_ids, *invoice_ids]),
            "oa_row_ids": sorted(oa_ids),
            "bank_row_ids": sorted(bank_ids),
            "invoice_row_ids": sorted(invoice_ids),
            "amount": self._format_amount(amount),
            "status": status,
            "evidence": deepcopy(evidence),
            "display_tags": [tag for tag in display_tags if tag],
            "cost_policy": cost_policy,
        }

    @classmethod
    def _dedupe_evaluations(cls, evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
        for evaluation in evaluations:
            key = (
                str(evaluation.get("rule_code") or ""),
                tuple(str(row_id) for row_id in list(evaluation.get("row_ids") or [])),
            )
            if key not in deduped:
                deduped[key] = evaluation
        return list(deduped.values())

    def _cash_turnover_matches(self, bank_row: dict[str, Any]) -> list[dict[str, str]]:
        matches: list[dict[str, str]] = []
        if self._category_code(bank_row) == "cash_turnover":
            matches.append(
                {
                    "matched_field": "category_code",
                    "matched_keyword": "cash_turnover",
                    "matched_rule": "manual_category",
                }
            )
        text_fields = ("summary", "remark", "purpose", "note")
        for field_name in text_fields:
            value = str(bank_row.get(field_name) or "")
            if "备用金" in value:
                matches.append(
                    {
                        "matched_field": field_name,
                        "matched_keyword": "备用金",
                        "matched_rule": "text_contains",
                    }
                )
        for field_name in ("detail_fields", "_detail_fields", "summary_fields", "_summary_fields"):
            fields = bank_row.get(field_name)
            if not isinstance(fields, dict):
                continue
            for key, value in fields.items():
                text = str(value or "")
                if "备用金" in text:
                    matches.append(
                        {
                            "matched_field": f"{field_name}.{key}",
                            "matched_keyword": "备用金",
                            "matched_rule": "text_contains",
                        }
                    )
        counterparty = str(bank_row.get("counterparty_name") or "")
        for keyword in CASH_COUNTERPARTY_KEYWORDS:
            if keyword in counterparty:
                matches.append(
                    {
                        "matched_field": "counterparty_name",
                        "matched_keyword": keyword,
                        "matched_rule": "counterparty_contains",
                    }
                )
        full_text = self._row_full_text(bank_row)
        for keyword in CASH_FULL_TEXT_KEYWORDS:
            if keyword in full_text:
                matches.append(
                    {
                        "matched_field": "full_text",
                        "matched_keyword": keyword,
                        "matched_rule": "full_text_contains",
                    }
                )
        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for match in matches:
            key = (match["matched_field"], match["matched_keyword"], match["matched_rule"])
            if key not in seen:
                seen.add(key)
                deduped.append(match)
        return deduped

    def _is_internal_transfer_candidate_row(self, row: dict[str, Any]) -> bool:
        if self._is_company_bank_row(row):
            return True
        return self._category_code(row) == "internal_transfer" and is_company_identity(None, self._bank_account_name(row))

    def _internal_transfer_matched_fields(self, outflow: dict[str, Any], inflow: dict[str, Any]) -> list[str]:
        fields = ["amount", "account_no", "pay_receive_time"]
        if self._category_code(outflow) == "internal_transfer" or self._category_code(inflow) == "internal_transfer":
            fields.append("category_code")
        return fields

    def _category_evidence(self, row: dict[str, Any], *, expected_code: str) -> dict[str, str]:
        if self._category_code(row) != expected_code:
            return {}
        return {
            "category_code": expected_code,
            "category_label": str(row.get("category_label") or "").strip(),
        }

    @staticmethod
    def _category_code(row: dict[str, Any]) -> str:
        return str(row.get("category_code") or "").strip()

    def _direction(self, row: dict[str, Any]) -> str | None:
        row_type = str(row.get("type") or "")
        if row_type == "bank":
            debit = self._amount_from_value(row.get("debit_amount"))
            credit = self._amount_from_value(row.get("credit_amount"))
            if debit is not None and debit > ZERO:
                return "outflow"
            if credit is not None and credit > ZERO:
                return "inflow"
            return None
        if row_type == "invoice":
            invoice_type = self._string_value(row.get("invoice_type")) or ""
            return "inflow" if "销" in invoice_type else "outflow"
        apply_type = self._string_value(row.get("apply_type")) or ""
        return "inflow" if ("收" in apply_type and "付" not in apply_type) else "outflow"

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
        return is_company_identity(None, self._bank_account_name(row)) and is_company_identity(
            None, row.get("counterparty_name")
        )

    def _bank_accounts_distinct(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_account = clean_account_no(self._bank_account_no(left))
        right_account = clean_account_no(self._bank_account_no(right))
        return bool(left_account and right_account and left_account != right_account)

    @staticmethod
    def _bank_account_name(row: dict[str, Any]) -> str:
        value = row.get("account_name")
        if value not in (None, "", "--", "—"):
            return str(value)
        detail_fields = row.get("detail_fields")
        if isinstance(detail_fields, dict):
            value = detail_fields.get("账户名称")
            if value not in (None, "", "--", "—"):
                return str(value)
        summary_fields = row.get("summary_fields")
        if isinstance(summary_fields, dict):
            value = summary_fields.get("账户名称")
            if value not in (None, "", "--", "—"):
                return str(value)
        return ""

    @staticmethod
    def _bank_account_no(row: dict[str, Any]) -> str:
        value = row.get("account_no")
        if value not in (None, "", "--", "—"):
            return str(value)
        detail_fields = row.get("detail_fields")
        if isinstance(detail_fields, dict):
            value = detail_fields.get("账号")
            if value not in (None, "", "--", "—"):
                return str(value)
        return ""

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

    @classmethod
    def _row_full_text(cls, row: dict[str, Any]) -> str:
        parts: list[str] = []
        for value in row.values():
            cls._append_text_value(parts, value)
        return " ".join(parts)

    @classmethod
    def _append_text_value(cls, parts: list[str], value: Any) -> None:
        if value in (None, "", "--", "—"):
            return
        if isinstance(value, dict):
            for nested in value.values():
                cls._append_text_value(parts, nested)
            return
        if isinstance(value, list):
            for nested in value:
                cls._append_text_value(parts, nested)
            return
        parts.append(str(value))
