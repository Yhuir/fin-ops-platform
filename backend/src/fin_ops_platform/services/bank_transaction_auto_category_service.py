from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService


BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION = "2026-05-bank-auto-category-sms-fee"

_TEXT_FIELDS = ("summary", "remark", "purpose", "note")
_NESTED_TEXT_FIELDS = ("detail_fields", "_detail_fields", "summary_fields", "_summary_fields")
_TEXT_RULES: tuple[dict[str, Any], ...] = (
    {
        "category_code": "fee",
        "rule_code": "fee_text_keyword",
        "keywords": ("手续费", "短信服务费"),
        "fields": ("counterparty_name", "summary", "remark"),
        "nested_fields": (),
        "reason": "对方户名、摘要或备注包含手续费或短信服务费",
    },
    {
        "category_code": "holiday_bonus",
        "rule_code": "holiday_bonus_text_keyword",
        "keywords": ("过节费",),
        "reason": "摘要、用途、备注或明细字段包含过节费",
    },
    {
        "category_code": "salary",
        "rule_code": "salary_text_keyword",
        "keywords": ("工资",),
        "reason": "摘要、用途、备注或明细字段包含工资",
    },
    {
        "category_code": "bonus",
        "rule_code": "bonus_text_keyword",
        "keywords": ("奖金", "绩效奖", "年终奖"),
        "reason": "摘要、用途、备注或明细字段包含奖金相关关键词",
    },
    {
        "category_code": "treasury_tax_collection",
        "rule_code": "treasury_tax_collection_text_keyword",
        "keywords": ("代理国库税收收缴", "国库税收收缴"),
        "reason": "摘要、用途、备注或明细字段包含代理国库税收收缴相关关键词",
    },
    {
        "category_code": "social_security",
        "rule_code": "social_security_text_keyword",
        "keywords": ("社保款", "社保费", "社会保险费", "缴纳社保"),
        "reason": "摘要、用途、备注或明细字段包含社保相关关键词",
    },
    {
        "category_code": "tax_payment",
        "rule_code": "tax_payment_text_keyword",
        "keywords": ("税款", "缴纳税款", "电子缴税", "税库银", "税务局", "完税"),
        "exclude_keywords": ("社保及税款", "社保和税款", "社保税款", "社保、税款"),
        "reason": "摘要、用途、备注或明细字段包含税款相关关键词",
    },
)


class BankTransactionAutoCategoryService:
    def __init__(self) -> None:
        pass

    def suggest_for_rows(self, bank_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        rows = [deepcopy(row) for row in list(bank_rows or []) if isinstance(row, dict)]
        suggestions: dict[str, dict[str, Any]] = {}
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

    def _text_suggestion(self, row: dict[str, Any], *, transaction_id: str) -> dict[str, Any] | None:
        for rule in _TEXT_RULES:
            rule_matches = self._text_matches(
                row,
                keywords=tuple(rule["keywords"]),
                exclude_keywords=tuple(rule.get("exclude_keywords") or ()),
                fields=tuple(rule.get("fields") or _TEXT_FIELDS),
                nested_fields=tuple(rule.get("nested_fields") if "nested_fields" in rule else _NESTED_TEXT_FIELDS),
            )
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
    def _text_matches(
        cls,
        row: dict[str, Any],
        *,
        keywords: tuple[str, ...],
        exclude_keywords: tuple[str, ...],
        fields: tuple[str, ...],
        nested_fields: tuple[str, ...],
    ) -> list[dict[str, str]]:
        matches: list[dict[str, str]] = []
        for field_name in fields:
            cls._append_matches(matches, field_name, row.get(field_name), keywords, exclude_keywords)
        for field_name in nested_fields:
            nested = row.get(field_name)
            if not isinstance(nested, dict):
                continue
            for key, value in nested.items():
                cls._append_matches(matches, f"{field_name}.{key}", value, keywords, exclude_keywords)
        return cls._dedupe_matches(matches)

    @staticmethod
    def _append_matches(
        matches: list[dict[str, str]],
        field_name: str,
        value: Any,
        keywords: tuple[str, ...],
        exclude_keywords: tuple[str, ...],
    ) -> None:
        text = str(value or "")
        if not text:
            return
        if any(exclude_keyword in text for exclude_keyword in exclude_keywords):
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
    def _transaction_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()


def resolve_effective_category(
    manual_category: dict[str, Any] | None,
    auto_category: dict[str, Any] | None,
) -> dict[str, Any]:
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
