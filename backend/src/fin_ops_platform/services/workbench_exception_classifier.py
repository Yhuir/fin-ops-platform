from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from fin_ops_platform.services.workbench_amount_check_service import WorkbenchAmountCheckService
from fin_ops_platform.services.workbench_exception_rules import (
    RULE_VERSION,
    action,
    scenario_label,
    workflow_for_action,
)


class WorkbenchExceptionClassifier:
    def __init__(self, amount_service: WorkbenchAmountCheckService | None = None) -> None:
        self._amount_service = amount_service or WorkbenchAmountCheckService()

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = [self._normalize_row(row) for row in list(payload.get("rows") or []) if isinstance(row, dict)]
        rows_by_type = self._rows_by_type(rows)
        amount_summary = self._amount_service.summarize(rows_by_type)
        candidate_evidence = list(payload.get("candidate_evidence") or [])

        if amount_summary["has_unknown_direction"]:
            return self._result(
                business_line="data_anomaly",
                scenario_code="data_anomaly_unknown_direction",
                amount_summary=amount_summary,
                available_action_codes=["manual_review"],
                warnings=["Selected rows include bank or invoice rows whose direction cannot be determined."],
            )

        if self._contains_income_objects(rows_by_type, amount_summary) and rows_by_type["oa"]:
            return self._result(
                business_line="data_anomaly",
                scenario_code="income_contains_oa_data_anomaly",
                amount_summary=amount_summary,
                available_action_codes=["income_data_anomaly_manual_review"],
                warnings=["Income-side exception handling must not include OA rows."],
            )

        if self._contains_income_objects(rows_by_type, amount_summary):
            return self._income_result(amount_summary)

        return self._expense_result(rows_by_type, amount_summary, candidate_evidence)

    classify = preview

    def _expense_result(
        self,
        rows_by_type: dict[str, list[dict[str, Any]]],
        amount_summary: dict[str, Any],
        candidate_evidence: list[Any],
    ) -> dict[str, Any]:
        relation = str(amount_summary["expense_relation"])
        auto_exemption = self._auto_oa_exemption_payload(rows_by_type["bank"], candidate_evidence)
        if relation == "only_bank_expense" and auto_exemption is not None:
            return self._result(
                business_line="expense",
                scenario_code="expense_only_bank_auto_oa_exempt",
                amount_summary=amount_summary,
                automatic_actions=[action("confirm_oa_exempt_auto", payload=auto_exemption)],
            )
        if self._has_cash_turnover_hint(rows_by_type["bank"], candidate_evidence):
            return self._result(
                business_line="expense",
                scenario_code="expense_only_bank",
                amount_summary=amount_summary,
                available_action_codes=["manual_review"],
                warnings=["Cash turnover evidence is hint-only and cannot close automatically."],
            )

        if relation == "only_oa":
            return self._result(
                business_line="expense",
                scenario_code="expense_only_oa",
                amount_summary=amount_summary,
                available_action_codes=["wait_bank_payment", "wait_input_invoice", "manual_review"],
            )
        if relation == "only_bank_expense":
            return self._result(
                business_line="expense",
                scenario_code="expense_only_bank",
                amount_summary=amount_summary,
                available_action_codes=["request_missing_oa", "confirm_oa_exempt_manual", "wait_input_invoice", "manual_review"],
            )
        if relation == "only_input_invoice":
            return self._result(
                business_line="expense",
                scenario_code="expense_only_input_invoice",
                amount_summary=amount_summary,
                available_action_codes=["wait_bank_payment", "confirm_payable_or_installment", "manual_review"],
            )

        scenario_by_relation: dict[str, tuple[str, list[str], list[dict[str, Any]]]] = {
            "oa_equals_bank_missing_input_invoice": (
                "expense_oa_bank_missing_input_invoice_equal",
                ["wait_input_invoice"],
                [],
            ),
            "oa_greater_than_bank_missing_input_invoice": (
                "expense_oa_bank_missing_input_invoice_oa_more",
                ["confirm_payable_or_installment", "manual_review"],
                [],
            ),
            "oa_less_than_bank_missing_input_invoice": (
                "expense_oa_bank_missing_input_invoice_bank_more",
                ["confirm_overpayment_recovery", "manual_review"],
                [],
            ),
            "oa_equals_input_invoice_missing_bank": (
                "expense_oa_input_invoice_missing_bank_equal",
                ["wait_bank_payment"],
                [],
            ),
            "oa_greater_than_input_invoice_missing_bank": (
                "expense_oa_input_invoice_missing_bank_oa_more",
                ["continue_wait_input_invoice", "wait_bank_payment"],
                [],
            ),
            "oa_less_than_input_invoice_missing_bank": (
                "expense_oa_input_invoice_missing_bank_invoice_more",
                ["confirm_extra_invoice_owner"],
                [],
            ),
            "bank_equals_input_invoice_missing_oa": (
                "expense_bank_input_invoice_missing_oa_equal",
                ["confirm_oa_exempt_manual", "request_missing_oa"],
                [],
            ),
            "bank_greater_than_input_invoice_missing_oa": (
                "expense_bank_input_invoice_missing_oa_bank_more",
                ["continue_wait_input_invoice", "request_missing_oa", "confirm_overpayment_recovery"],
                [],
            ),
            "bank_less_than_input_invoice_missing_oa": (
                "expense_bank_input_invoice_missing_oa_invoice_more",
                ["confirm_payable_or_installment", "request_missing_oa"],
                [],
            ),
            "all_equal": ("expense_all_equal", [], [action("confirm_closed")]),
            "oa_equals_bank_greater_than_input_invoice": (
                "expense_oa_bank_equal_input_invoice_less",
                ["continue_wait_input_invoice"],
                [],
            ),
            "oa_equals_bank_less_than_input_invoice": (
                "expense_oa_bank_equal_input_invoice_more",
                ["confirm_extra_invoice_owner"],
                [],
            ),
            "oa_equals_input_invoice_greater_than_bank": (
                "expense_oa_input_invoice_equal_bank_less",
                ["confirm_payable_or_installment", "wait_bank_payment"],
                [],
            ),
            "oa_equals_input_invoice_less_than_bank": (
                "expense_oa_input_invoice_equal_bank_more",
                ["confirm_overpayment_recovery"],
                [],
            ),
            "bank_equals_input_invoice_greater_than_oa": (
                "expense_bank_input_invoice_equal_oa_less",
                ["request_missing_oa", "confirm_oa_exempt_manual"],
                [],
            ),
            "bank_equals_input_invoice_less_than_oa": (
                "expense_bank_input_invoice_equal_oa_more",
                ["confirm_payable_or_installment"],
                [],
            ),
            "all_different": ("expense_all_different", ["manual_review"], []),
        }
        scenario_code, available_action_codes, automatic_actions = scenario_by_relation.get(
            relation,
            ("expense_all_different", ["manual_review"], []),
        )
        return self._result(
            business_line="expense",
            scenario_code=scenario_code,
            amount_summary=amount_summary,
            available_action_codes=available_action_codes,
            automatic_actions=automatic_actions,
        )

    def _income_result(self, amount_summary: dict[str, Any]) -> dict[str, Any]:
        relation = str(amount_summary["income_relation"])
        if relation == "only_income_bank":
            return self._result(
                business_line="income",
                scenario_code="income_only_bank",
                amount_summary=amount_summary,
                available_action_codes=["wait_output_invoice", "confirm_no_invoice_income"],
            )
        if relation == "only_output_invoice":
            return self._result(
                business_line="income",
                scenario_code="income_only_output_invoice",
                amount_summary=amount_summary,
                available_action_codes=["wait_collection", "confirm_output_invoice_void_or_red"],
            )
        if relation == "income_equals_invoice":
            return self._result(
                business_line="income",
                scenario_code="income_bank_output_invoice_equal",
                amount_summary=amount_summary,
                automatic_actions=[action("confirm_income_closed")],
            )
        if relation == "income_greater_than_invoice":
            return self._result(
                business_line="income",
                scenario_code="income_bank_more_than_output_invoice",
                amount_summary=amount_summary,
                available_action_codes=["confirm_refund_or_more_invoice"],
            )
        if relation == "income_less_than_invoice":
            return self._result(
                business_line="income",
                scenario_code="income_output_invoice_more_than_bank",
                amount_summary=amount_summary,
                available_action_codes=["wait_collection"],
            )
        return self._result(
            business_line="data_anomaly",
            scenario_code="data_anomaly_unknown_direction",
            amount_summary=amount_summary,
            available_action_codes=["manual_review"],
        )

    def _result(
        self,
        *,
        business_line: str,
        scenario_code: str,
        amount_summary: dict[str, Any],
        available_action_codes: list[str] | None = None,
        automatic_actions: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        automatic = deepcopy(automatic_actions or [])
        available = [action(action_code) for action_code in list(available_action_codes or [])]
        primary_action_code = self._primary_action_code(automatic, available)
        return {
            "rule_version": RULE_VERSION,
            "business_line": business_line,
            "scenario_code": scenario_code,
            "scenario_label": scenario_label(scenario_code),
            "amount_summary": deepcopy(amount_summary),
            "automatic_actions": automatic,
            "available_actions": available,
            "warnings": list(warnings or []),
            "workflow_projection": workflow_for_action(primary_action_code),
        }

    @staticmethod
    def _primary_action_code(automatic_actions: list[dict[str, Any]], available_actions: list[dict[str, Any]]) -> str:
        if automatic_actions:
            return str(automatic_actions[0]["action_code"])
        if available_actions:
            return str(available_actions[0]["action_code"])
        return "manual_review"

    def _auto_oa_exemption_payload(
        self,
        bank_rows: list[dict[str, Any]],
        candidate_evidence: list[Any],
    ) -> dict[str, Any] | None:
        evidence_match = self._auto_exemption_from_candidate_evidence(candidate_evidence)
        if evidence_match is not None:
            return self._oa_exemption_payload(**evidence_match)
        for bank_row in bank_rows:
            reason = self._auto_exemption_reason_for_bank_row(bank_row)
            if reason is None:
                continue
            return self._oa_exemption_payload(
                reason_code=reason["reason_code"],
                reason_label=reason["reason_label"],
                rule_code=reason["rule_code"],
                evidence=self._bank_evidence(bank_row),
                display_tags=["自动免OA", reason["reason_label"]],
            )
        return None

    def _auto_exemption_from_candidate_evidence(self, candidate_evidence: list[Any]) -> dict[str, Any] | None:
        reason_by_rule = {
            "auto_bank_fee_v1": ("bank_fee", "银行手续费"),
            "bank_fee": ("bank_fee", "银行手续费"),
            "loan_interest_plan": ("loan_interest_plan", "银行借款计划还利息"),
            "telecom_withholding": ("telecom_withholding", "电信托收"),
            "salary_personal_auto_match": ("salary", "工资"),
            "holiday_bonus": ("holiday_bonus", "过节费"),
            "internal_transfer_pair": ("internal_transfer", "内部转账"),
            "configured_auto_debit": ("configured_auto_debit", "配置自动扣款"),
            "etc_batch": ("etc_batch", "ETC 批次证据"),
            "oa_attachment_invoice_offset_auto_match": ("oa_attachment_invoice_offset", "OA 附件票冲"),
        }
        for item in candidate_evidence:
            if not isinstance(item, dict):
                continue
            rule_code = str(item.get("rule_code") or item.get("special_type") or item.get("reason_code") or "")
            if rule_code in {"cash_turnover_detected", "cash_turnover"}:
                continue
            reason = reason_by_rule.get(rule_code)
            if reason is None:
                continue
            return {
                "reason_code": reason[0],
                "reason_label": reason[1],
                "rule_code": rule_code,
                "evidence": deepcopy(item.get("evidence") if isinstance(item.get("evidence"), dict) else item),
                "display_tags": ["自动免OA", reason[1]],
            }
        return None

    @staticmethod
    def _auto_exemption_reason_for_bank_row(bank_row: dict[str, Any]) -> dict[str, str] | None:
        text = WorkbenchExceptionClassifier._row_text(bank_row)
        if "手续费" in text or "账户管理费" in text:
            return {"reason_code": "bank_fee", "reason_label": "银行手续费", "rule_code": "auto_bank_fee_v1"}
        if "利息" in text and ("贷款" in text or "借款" in text or "还息" in text):
            return {
                "reason_code": "loan_interest_plan",
                "reason_label": "银行借款计划还利息",
                "rule_code": "auto_loan_interest_plan_v1",
            }
        if "电信" in text and ("托收" in text or "代扣" in text):
            return {
                "reason_code": "telecom_withholding",
                "reason_label": "电信托收",
                "rule_code": "auto_telecom_withholding_v1",
            }
        if "过节费" in text:
            return {"reason_code": "holiday_bonus", "reason_label": "过节费", "rule_code": "auto_holiday_bonus_v1"}
        if "工资" in text:
            return {"reason_code": "salary", "reason_label": "工资", "rule_code": "auto_salary_v1"}
        return None

    @staticmethod
    def _oa_exemption_payload(
        *,
        reason_code: str,
        reason_label: str,
        rule_code: str,
        evidence: dict[str, Any],
        display_tags: list[str],
    ) -> dict[str, Any]:
        return {
            "relation_mode": "oa_exempt",
            "oa_exemption": {
                "source": "auto",
                "reason_code": reason_code,
                "reason_label": reason_label,
                "rule_code": rule_code,
                "rule_version": RULE_VERSION,
                "evidence": deepcopy(evidence),
                "confirmed_by": None,
                "confirmed_at": None,
                "note": None,
            },
            "display_tags": display_tags,
        }

    @staticmethod
    def _bank_evidence(bank_row: dict[str, Any]) -> dict[str, Any]:
        return {
            "row_id": str(bank_row.get("id") or bank_row.get("row_id") or ""),
            "summary": str(bank_row.get("summary") or ""),
            "remark": str(bank_row.get("remark") or ""),
            "counterparty": str(bank_row.get("counterparty_name") or ""),
            "amount": WorkbenchExceptionClassifier._bank_amount(bank_row),
        }

    @staticmethod
    def _bank_amount(bank_row: dict[str, Any]) -> str:
        for key in ("debit_amount", "credit_amount", "amount"):
            value = bank_row.get(key)
            if value in (None, ""):
                continue
            return f"{Decimal(str(value).replace(',', '')).quantize(Decimal('0.01')):.2f}"
        return "0.00"

    def _has_cash_turnover_hint(self, bank_rows: list[dict[str, Any]], candidate_evidence: list[Any]) -> bool:
        for item in candidate_evidence:
            if isinstance(item, dict) and str(item.get("rule_code") or item.get("special_type") or "") in {
                "cash_turnover_detected",
                "cash_turnover",
            }:
                return True
        return any("备用金" in self._row_text(row) for row in bank_rows)

    @staticmethod
    def _contains_income_objects(rows_by_type: dict[str, list[dict[str, Any]]], amount_summary: dict[str, Any]) -> bool:
        return (
            bool(rows_by_type["bank"] and amount_summary["bank_income_total"] != "0.00")
            or bool(rows_by_type["invoice"] and amount_summary["output_invoice_total"] != "0.00")
            or str(amount_summary["income_relation"]) != "not_applicable"
        )

    @staticmethod
    def _rows_by_type(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        rows_by_type: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}
        for row in rows:
            row_type = str(row.get("type") or row.get("record_type") or "")
            if row_type in rows_by_type:
                rows_by_type[row_type].append(row)
        return rows_by_type

    @staticmethod
    def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        if "type" not in normalized and "record_type" in normalized:
            normalized["type"] = normalized["record_type"]
        return normalized

    @staticmethod
    def _row_text(row: dict[str, Any]) -> str:
        parts: list[str] = []
        for field in ("summary", "remark", "purpose", "note", "counterparty_name"):
            parts.append(str(row.get(field) or ""))
        for field in ("detail_fields", "_detail_fields", "summary_fields", "_summary_fields"):
            value = row.get(field)
            if isinstance(value, dict):
                parts.extend(str(item) for item in value.values())
        return " ".join(parts)
