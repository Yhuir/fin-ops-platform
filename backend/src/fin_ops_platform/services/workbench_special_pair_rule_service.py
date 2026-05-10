from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.import_file_service import is_company_identity
from fin_ops_platform.services.live_workbench_service import INTERNAL_TRANSFER_MATCH_WINDOW, clean_account_no


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
SALARY_PERSONAL_AUTO_MATCH = "salary_personal_auto_match"
INTERNAL_TRANSFER_PAIR = "internal_transfer_pair"
OA_INVOICE_OFFSET_AUTO_MATCH = "oa_invoice_offset_auto_match"
CASH_TURNOVER_DETECTED = "cash_turnover_detected"
CASH_TURNOVER_TAG = "现金往来"
OFFSET_TAG = "冲"
CASH_COUNTERPARTY_KEYWORDS = ("陈秀云", "太宏", "韦代连")
CASH_FULL_TEXT_KEYWORDS = ("张双文公积金", "陈秀云社保")


class WorkbenchSpecialPairRuleService:
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
        candidates.extend(self._internal_transfer_pair(scope_month, bank, resolved_versions))
        candidates.extend(self._salary_personal_auto_match(scope_month, bank, resolved_versions))
        candidates.extend(self._oa_invoice_offset_auto_match(scope_month, oa, invoices, resolved_settings, resolved_versions))
        candidates.extend(self._cash_turnover_detected(scope_month, bank, resolved_versions))
        return self._dedupe_candidates(candidates)

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
                    rule_code=SALARY_PERSONAL_AUTO_MATCH,
                    rows=[bank_row],
                    status="auto_closed",
                    confidence="high",
                    amount=amount,
                    explanation="Detected salary payment to an individual counterparty from bank summary or remark.",
                    source_versions=source_versions,
                    tags=["工资"],
                    special_metadata={
                        "special_type": SALARY_PERSONAL_AUTO_MATCH,
                        "cost_policy": "normal",
                    },
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
                    rule_code=INTERNAL_TRANSFER_PAIR,
                    rows=[outflow, inflow],
                    status="auto_closed",
                    confidence="high",
                    amount=outflow_amount,
                    explanation="Detected equal internal transfer between different company bank accounts within the time window.",
                    source_versions=source_versions,
                    tags=["内部往来"],
                    special_metadata={
                        "special_type": INTERNAL_TRANSFER_PAIR,
                        "cost_policy": "exclude_all",
                        "match_window_hours": int(INTERNAL_TRANSFER_MATCH_WINDOW.total_seconds() // 3600),
                    },
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
            versions = {**source_versions, "offset_display_tag": OFFSET_TAG, "offset_relation_mode": "oa_attachment_invoice"}
            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code=OA_INVOICE_OFFSET_AUTO_MATCH,
                    rows=[oa_row, invoice_row],
                    status="auto_closed",
                    confidence="high",
                    amount=amount,
                    explanation="Configured applicant OA attachment invoice auto matched for 冲 display.",
                    source_versions=versions,
                    tags=[OFFSET_TAG],
                    special_metadata={
                        "special_type": OA_INVOICE_OFFSET_AUTO_MATCH,
                        "cost_policy": "exclude_all",
                        "cost_excluded": True,
                    },
                )
            )
        return candidates

    def _cash_turnover_detected(
        self,
        scope_month: str,
        bank_rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for bank_row in sorted(bank_rows, key=self._row_id):
            matches = self._cash_turnover_matches(bank_row)
            if not matches:
                continue
            amount = self._amount(bank_row)
            if amount is None:
                amount = ZERO
            candidates.append(
                self._candidate(
                    scope_month,
                    rule_code=CASH_TURNOVER_DETECTED,
                    rows=[bank_row],
                    status="needs_review",
                    confidence="medium",
                    amount=amount,
                    explanation="Detected bank transaction matching cash turnover hint rules.",
                    source_versions=source_versions,
                    tags=[CASH_TURNOVER_TAG],
                    special_metadata={
                        "special_type": CASH_TURNOVER_DETECTED,
                        "cost_policy": "hint_only",
                        "cost_excluded": False,
                        "matches": matches,
                    },
                )
            )
        return candidates

    def _cash_turnover_matches(self, bank_row: dict[str, Any]) -> list[dict[str, str]]:
        matches: list[dict[str, str]] = []
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
        tags: list[str] | None = None,
        special_metadata: dict[str, Any] | None = None,
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
            "tags": [str(tag).strip() for tag in list(tags or []) if str(tag).strip()],
            "special_metadata": deepcopy(special_metadata if isinstance(special_metadata, dict) else {}),
        }

    @classmethod
    def _dedupe_candidates(cls, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
        for candidate in candidates:
            key = (
                str(candidate.get("scope_month") or ""),
                str(candidate.get("rule_code") or ""),
                tuple(str(row_id) for row_id in list(candidate.get("row_ids") or [])),
            )
            if key not in deduped:
                deduped[key] = candidate
        return list(deduped.values())

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
