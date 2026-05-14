from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.workbench_special_rule_detectors import (
    INTERNAL_TRANSFER_PAIR,
    SALARY_PERSONAL_AUTO_MATCH,
    WorkbenchSpecialRuleDetector,
)


BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION = "2026-05-bank-auto-category"

_TEXT_FIELDS = ("summary", "remark", "purpose", "note")
_NESTED_TEXT_FIELDS = ("detail_fields", "_detail_fields", "summary_fields", "_summary_fields")
_TEXT_RULES: tuple[dict[str, Any], ...] = (
    {
        "category_code": "fee",
        "rule_code": "fee_text_keyword",
        "keywords": ("手续费", "服务费", "网银手续费", "转账手续费"),
        "reason": "摘要、用途、备注或明细字段包含手续费相关关键词",
    },
    {
        "category_code": "holiday_bonus",
        "rule_code": "holiday_bonus_text_keyword",
        "keywords": ("过节费", "节日费", "慰问金"),
        "reason": "摘要、用途、备注或明细字段包含过节费相关关键词",
    },
    {
        "category_code": "bonus",
        "rule_code": "bonus_text_keyword",
        "keywords": ("奖金", "绩效奖", "年终奖"),
        "reason": "摘要、用途、备注或明细字段包含奖金相关关键词",
    },
)


class BankTransactionAutoCategoryService:
    def __init__(self, *, detector: WorkbenchSpecialRuleDetector | None = None) -> None:
        self._detector = detector or WorkbenchSpecialRuleDetector()

    def suggest_for_rows(self, bank_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        rows = [deepcopy(row) for row in list(bank_rows or []) if isinstance(row, dict)]
        suggestions: dict[str, dict[str, Any]] = {}
        suggestions.update(self._detector_suggestions(rows))
        for row in rows:
            transaction_id = self._transaction_id(row)
            if not transaction_id or transaction_id in suggestions:
                continue
            suggestion = self._text_suggestion(row, transaction_id=transaction_id)
            if suggestion is not None:
                suggestions[transaction_id] = suggestion
        return suggestions

    def suggestions_by_transaction_id(self, bank_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return self.suggest_for_rows(bank_rows)

    def _detector_suggestions(self, bank_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        evaluations = self._detector.evaluate(oa_rows=[], bank_rows=bank_rows, invoice_rows=[])
        suggestions: dict[str, dict[str, Any]] = {}
        for evaluation in evaluations:
            rule_code = str(evaluation.get("rule_code") or "")
            if rule_code == INTERNAL_TRANSFER_PAIR:
                category_code = "internal_transfer"
                reason = "workbench_special_rule_detector 识别为同金额、不同公司账户、时间窗口内匹配"
            elif rule_code == SALARY_PERSONAL_AUTO_MATCH:
                category_code = "salary"
                reason = "workbench_special_rule_detector 识别为个人工资支出"
            else:
                continue
            for transaction_id in self._bank_row_ids(evaluation):
                if transaction_id in suggestions:
                    continue
                suggestions[transaction_id] = self._suggestion(
                    transaction_id=transaction_id,
                    category_code=category_code,
                    rule_code=rule_code,
                    reason=reason,
                    confidence=str(evaluation.get("confidence") or "medium").strip() or "medium",
                )
        return suggestions

    def _text_suggestion(self, row: dict[str, Any], *, transaction_id: str) -> dict[str, Any] | None:
        matches = self._text_matches(row)
        for rule in _TEXT_RULES:
            rule_matches = [
                match
                for match in matches
                if match["matched_keyword"] in set(rule["keywords"])
            ]
            if not rule_matches:
                continue
            matched_fields = sorted({match["matched_field"] for match in rule_matches})
            matched_keywords = sorted({match["matched_keyword"] for match in rule_matches})
            return self._suggestion(
                transaction_id=transaction_id,
                category_code=str(rule["category_code"]),
                rule_code=str(rule["rule_code"]),
                reason=f"{rule['reason']}：{', '.join(matched_keywords)}；字段：{', '.join(matched_fields)}",
                confidence="high",
            )
        return None

    @staticmethod
    def _suggestion(
        *,
        transaction_id: str,
        category_code: str,
        rule_code: str,
        reason: str,
        confidence: str,
    ) -> dict[str, Any]:
        return {
            "transaction_id": transaction_id,
            "category_code": category_code,
            "category_label": BankTransactionCategoryService.label_for(category_code),
            "category_path": BankTransactionCategoryService.path_for(category_code),
            "source": "auto",
            "rule_code": rule_code,
            "reason": reason,
            "confidence": confidence,
            "rule_version": BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION,
        }

    @classmethod
    def _text_matches(cls, row: dict[str, Any]) -> list[dict[str, str]]:
        matches: list[dict[str, str]] = []
        keywords = tuple(
            keyword
            for rule in _TEXT_RULES
            for keyword in tuple(rule["keywords"])
        )
        for field_name in _TEXT_FIELDS:
            cls._append_matches(matches, field_name, row.get(field_name), keywords)
        for field_name in _NESTED_TEXT_FIELDS:
            nested = row.get(field_name)
            if not isinstance(nested, dict):
                continue
            for key, value in nested.items():
                cls._append_matches(matches, f"{field_name}.{key}", value, keywords)
        return cls._dedupe_matches(matches)

    @staticmethod
    def _append_matches(
        matches: list[dict[str, str]],
        field_name: str,
        value: Any,
        keywords: tuple[str, ...],
    ) -> None:
        text = str(value or "")
        if not text:
            return
        for keyword in keywords:
            if keyword in text:
                matches.append(
                    {
                        "matched_field": field_name,
                        "matched_keyword": keyword,
                    }
                )

    @staticmethod
    def _dedupe_matches(matches: list[dict[str, str]]) -> list[dict[str, str]]:
        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for match in matches:
            key = (match["matched_field"], match["matched_keyword"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(match)
        return deduped

    @staticmethod
    def _bank_row_ids(evaluation: dict[str, Any]) -> list[str]:
        bank_row_ids = [
            str(row_id).strip()
            for row_id in list(evaluation.get("bank_row_ids") or [])
            if str(row_id).strip()
        ]
        if bank_row_ids:
            return bank_row_ids
        return [
            str(row_id).strip()
            for row_id in list(evaluation.get("row_ids") or [])
            if str(row_id).strip()
        ]

    @staticmethod
    def _transaction_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()


def resolve_effective_category(
    manual_category: dict[str, Any] | None,
    auto_category: dict[str, Any] | None,
) -> dict[str, Any]:
    manual = manual_category if isinstance(manual_category, dict) else {}
    if str(manual.get("source") or "").strip() == "manual":
        category_code = manual.get("category_code")
        if category_code is None:
            return {
                "effective_category_code": None,
                "effective_category_label": None,
                "effective_category_path": [],
                "effective_category_source": "",
            }
        return {
            "effective_category_code": category_code,
            "effective_category_label": manual.get("category_label"),
            "effective_category_path": list(manual.get("category_path") or []),
            "effective_category_source": "manual",
        }

    auto = auto_category if isinstance(auto_category, dict) else {}
    auto_code = auto.get("category_code")
    if auto_code:
        return {
            "effective_category_code": auto_code,
            "effective_category_label": auto.get("category_label"),
            "effective_category_path": list(auto.get("category_path") or []),
            "effective_category_source": "auto",
        }
    return {
        "effective_category_code": None,
        "effective_category_label": None,
        "effective_category_path": [],
        "effective_category_source": "",
    }
