from __future__ import annotations

from copy import deepcopy
import re
from typing import Any
import unicodedata

from fin_ops_platform.services.bank_internal_transfer_detector import BankInternalTransferDetector
from fin_ops_platform.services.bank_transaction_category_service import (
    BANK_AUTO_TAG_FIELD_LABELS,
    BANK_TRANSACTION_CATEGORY_DEFINITIONS,
    BankTransactionCategoryService,
    default_bank_transaction_tag_dictionary_payload,
)


BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION = "2026-05-bank-auto-category-internal-transfer-first"

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
    def __init__(
        self,
        *,
        internal_transfer_detector: BankInternalTransferDetector | None = None,
        category_service: BankTransactionCategoryService | None = None,
        tag_dictionary: dict[str, Any] | None = None,
    ) -> None:
        self._internal_transfer_detector = internal_transfer_detector or BankInternalTransferDetector()
        self._category_service = category_service or BankTransactionCategoryService(tag_dictionary=tag_dictionary)
        if category_service is not None and tag_dictionary is not None:
            self._category_service.configure_tag_dictionary(tag_dictionary)

    def configure_tag_dictionary(self, payload: dict[str, Any] | None) -> None:
        self._category_service.configure_tag_dictionary(
            payload if isinstance(payload, dict) else default_bank_transaction_tag_dictionary_payload()
        )

    def suggest_for_rows(self, bank_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        rows = [deepcopy(row) for row in list(bank_rows or []) if isinstance(row, dict)]
        suggestions = self._internal_transfer_detector.detect(rows)
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
        semantic_fields = self._semantic_text_fields(row)
        rules = [
            dict(definition)
            for definition in list(self._category_service.tag_dictionary_payload().get("definitions") or [])
            if isinstance(definition, dict)
            and str(definition.get("status") or "active") == "active"
            and isinstance(definition.get("rules"), dict)
        ]
        rules.sort(key=lambda definition: (int(definition.get("priority") or 10_000), str(definition.get("code") or "")))
        for rule in rules:
            match = self._rule_match(semantic_fields, rule)
            if match is None:
                continue
            return self._suggestion(
                transaction_id=transaction_id,
                category_code=str(rule["code"]),
                rule_code=str(rule.get("rule_code") or rule["code"]),
                reason=self._rule_reason(rule, match),
                confidence="high",
                evidence=match,
            )
        return None

    @classmethod
    def _semantic_text_fields(cls, row: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        fields: dict[str, list[dict[str, Any]]] = {
            "counterparty_name": cls._semantic_values(row, "counterparty_name", ("counterparty_name",)),
            "counterparty_account": cls._semantic_values(
                row,
                "counterparty_account",
                ("counterparty_account", "counterparty_account_no", "counterparty_account_number", "counterparty_no"),
            ),
            "counterparty_bank": cls._semantic_values(
                row,
                "counterparty_bank",
                ("counterparty_bank", "counterparty_bank_name", "counterparty_opening_bank"),
            ),
            "purpose_text": cls._semantic_values(row, "purpose_text", ("purpose_text", "purpose")),
            "summary_text": cls._semantic_values(row, "summary_text", ("summary_text", "summary")),
            "note_text": cls._semantic_values(row, "note_text", ("note_text", "remark", "note", "customer_note")),
            "detail_text": cls._detail_semantic_values(row),
            "__direction__": [{"text": cls._row_direction(row), "semantic_field": "__direction__"}],
            "__account_key__": cls._semantic_values(row, "__account_key__", ("account_key", "account_no", "account_number")),
            "__account_type__": cls._semantic_values(row, "__account_type__", ("account_type",)),
            "__bank_name__": cls._semantic_values(row, "__bank_name__", ("bank_name", "bank")),
        }
        all_values: list[dict[str, Any]] = []
        seen_texts: set[str] = set()
        for field in (
            "counterparty_name",
            "counterparty_account",
            "counterparty_bank",
            "purpose_text",
            "summary_text",
            "note_text",
            "detail_text",
        ):
            for entry in fields[field]:
                text = str(entry.get("text") or "").strip()
                if not text or text in seen_texts:
                    continue
                seen_texts.add(text)
                all_values.append({**entry, "semantic_field": "all_text"})
        fields["all_text"] = all_values
        return fields

    @staticmethod
    def _row_direction(row: dict[str, Any]) -> str:
        def amount(value: Any) -> float:
            try:
                return float(str(value or "").replace(",", ""))
            except ValueError:
                return 0.0

        if amount(row.get("credit_amount") or row.get("income_amount") or row.get("income")) > 0:
            return "income"
        if amount(row.get("debit_amount") or row.get("expense_amount") or row.get("expense")) > 0:
            return "expense"
        raw = str(row.get("direction") or row.get("income_expense_type") or "").strip()
        if raw in {"收入", "收款", "贷方", "income", "credit"}:
            return "income"
        if raw in {"支出", "付款", "借方", "expense", "debit"}:
            return "expense"
        return "any"

    @staticmethod
    def _semantic_values(row: dict[str, Any], semantic_field: str, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        seen: set[str] = set()
        for key in keys:
            text = str(row.get(key) or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            values.append(
                {
                    "text": text,
                    "semantic_field": semantic_field,
                    "raw_field_key": key,
                    "raw_field_label": None,
                }
            )
        return values

    @classmethod
    def _detail_semantic_values(cls, row: dict[str, Any]) -> list[dict[str, Any]]:
        values = cls._semantic_values(row, "detail_text", ("detail_text",))
        seen = {str(value.get("text") or "") for value in values}
        for field_name in _NESTED_TEXT_FIELDS:
            nested = row.get(field_name)
            if not isinstance(nested, dict):
                continue
            for key, value in nested.items():
                text = str(value or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                values.append(
                    {
                        "text": text,
                        "semantic_field": "detail_text",
                        "raw_field_key": str(key),
                        "raw_field_label": str(key),
                    }
                )
        return values

    @staticmethod
    def _rule_match(
        semantic_fields: dict[str, list[dict[str, Any]]],
        rule: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not BankTransactionAutoCategoryService._direction_matches(rule, semantic_fields):
            return None
        if not BankTransactionAutoCategoryService._account_scope_matches(rule, semantic_fields):
            return None
        conditions = rule.get("rules") if isinstance(rule.get("rules"), dict) else {}
        match_fields = [
            str(field)
            for field in list(conditions.get("match_fields") or [])
            if str(field)
        ]
        candidates = [
            entry
            for field in match_fields
            for entry in list(semantic_fields.get(field) or [])
        ]
        if not candidates:
            return None
        normalized_entries = [
            {
                **entry,
                "normalized_text": BankTransactionAutoCategoryService._normalize_match_text(entry.get("text")),
            }
            for entry in candidates
        ]
        none_of = [
            BankTransactionAutoCategoryService._normalize_match_text(item)
            for item in list(conditions.get("none_of") or conditions.get("excludes") or [])
            if str(item)
        ]
        for entry in normalized_entries:
            text = str(entry.get("normalized_text") or "")
            if any(exclude and exclude in text for exclude in none_of):
                return None
        contains_all_tokens = [
            str(item)
            for item in list(conditions.get("contains_all") or [])
            if str(item)
        ]
        contains_all = [
            BankTransactionAutoCategoryService._normalize_match_text(item)
            for item in contains_all_tokens
        ]
        if contains_all:
            joined_text = " ".join(str(entry.get("normalized_text") or "") for entry in normalized_entries)
            if any(token not in joined_text for token in contains_all):
                return None
        for token in [str(item) for item in list(conditions.get("exact_any") or conditions.get("exact") or []) if str(item)]:
            normalized_token = BankTransactionAutoCategoryService._normalize_match_text(token)
            for entry in candidates:
                if BankTransactionAutoCategoryService._normalize_match_text(entry.get("text")) == normalized_token:
                    return BankTransactionAutoCategoryService._evidence("exact_any", token, entry, rule=rule)
        for token in [str(item) for item in list(conditions.get("contains_any") or conditions.get("contains") or []) if str(item)]:
            normalized_token = BankTransactionAutoCategoryService._normalize_match_text(token)
            for entry in candidates:
                if normalized_token in BankTransactionAutoCategoryService._normalize_match_text(entry.get("text")):
                    return BankTransactionAutoCategoryService._evidence("contains_any", token, entry, rule=rule)
        for pattern in [str(item) for item in list(conditions.get("regex_any") or []) if str(item)]:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error:
                continue
            for entry in candidates:
                text = BankTransactionAutoCategoryService._normalize_regex_text(entry.get("text"))
                if compiled.search(text):
                    return BankTransactionAutoCategoryService._evidence("regex_any", pattern, entry, rule=rule)
        if contains_all_tokens:
            matched_entry = BankTransactionAutoCategoryService._contains_all_evidence_entry(
                normalized_entries,
                contains_all,
            )
            return BankTransactionAutoCategoryService._evidence(
                "contains_all",
                "、".join(contains_all_tokens),
                matched_entry,
                rule=rule,
            )
        return None

    @staticmethod
    def _evidence(
        condition_type: str,
        matched_text: str,
        entry: dict[str, Any],
        *,
        rule: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        semantic_field = str(entry.get("semantic_field") or "")
        evidence = {
            "condition_type": condition_type,
            "semantic_field": semantic_field,
            "semantic_field_label": BANK_AUTO_TAG_FIELD_LABELS.get(semantic_field, semantic_field),
            "raw_field_key": entry.get("raw_field_key"),
            "raw_field_label": entry.get("raw_field_label"),
            "matched_text": matched_text,
        }
        if isinstance(rule, dict):
            if "review_required" in rule:
                evidence["review_required"] = bool(rule.get("review_required"))
            if rule.get("route_to"):
                evidence["route_to"] = str(rule.get("route_to"))
        return evidence

    @staticmethod
    def _contains_all_evidence_entry(
        normalized_entries: list[dict[str, Any]],
        contains_all: list[str],
    ) -> dict[str, Any]:
        for entry in normalized_entries:
            text = str(entry.get("normalized_text") or "")
            if any(token and token in text for token in contains_all):
                return entry
        return normalized_entries[0] if normalized_entries else {"semantic_field": "all_text"}

    @staticmethod
    def _rule_reason(rule: dict[str, Any], evidence: dict[str, Any]) -> str:
        label = str(evidence.get("semantic_field_label") or evidence.get("semantic_field") or "文本")
        condition_labels = {
            "exact_any": "精确命中",
            "contains_any": "包含",
            "contains_all": "同时包含",
            "regex_any": "正则命中",
        }
        condition = condition_labels.get(str(evidence.get("condition_type") or ""), "命中")
        return f"{label}{condition}{evidence.get('matched_text')}，命中标签 {rule.get('label')}"

    @staticmethod
    def _direction_matches(rule: dict[str, Any], semantic_fields: dict[str, list[dict[str, Any]]]) -> bool:
        direction = str(rule.get("direction") or "any").strip()
        if direction in ("", "any"):
            return True
        row_direction = str((semantic_fields.get("__direction__") or [{}])[0].get("text") or "any")
        if row_direction == "any":
            return True
        return row_direction == direction

    @staticmethod
    def _account_scope_matches(rule: dict[str, Any], semantic_fields: dict[str, list[dict[str, Any]]]) -> bool:
        scope = rule.get("account_scope") if isinstance(rule.get("account_scope"), dict) else {}
        scope_type = str(scope.get("type") or "any")
        if scope_type == "any":
            return True
        values = [
            BankTransactionAutoCategoryService._normalize_match_text(item)
            for item in list(scope.get("values") or [])
            if str(item)
        ]
        if not values:
            return True
        field_by_scope = {
            "bank_account": "__account_key__",
            "account_type": "__account_type__",
            "bank": "__bank_name__",
        }.get(scope_type)
        if not field_by_scope:
            return True
        row_values = [
            BankTransactionAutoCategoryService._normalize_match_text(entry.get("text"))
            for entry in list(semantic_fields.get(field_by_scope) or [])
        ]
        return any(value in row_values for value in values)

    @staticmethod
    def _normalize_match_text(value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        if text in {"--", "_"}:
            return ""
        text = text.replace("帐户", "账户")
        text = text.replace("（", "(").replace("）", ")")
        text = re.sub(r"\s+", "", text)
        return text.casefold()

    @staticmethod
    def _normalize_regex_text(value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        if text in {"--", "_"}:
            return ""
        text = text.replace("帐户", "账户")
        text = text.replace("（", "(").replace("）", ")")
        text = re.sub(r"\s+", " ", text)
        return text.casefold()

    def _suggestion(
        self,
        *,
        transaction_id: str,
        category_code: str,
        rule_code: str,
        reason: str,
        confidence: str,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "transaction_id": transaction_id,
            "category_code": category_code,
            "category_label": self._category_service._label_for(category_code),
            **self._category_service._label_fields_for(category_code),
            "category_path": self._category_service._path_for(category_code),
            "source": "auto",
            "rule_code": rule_code,
            "reason": reason,
            "confidence": confidence,
            "rule_version": BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION,
        }
        if evidence is not None:
            evidence_payload = dict(evidence)
            evidence_payload["tag_code"] = category_code
            evidence_payload["tag_label"] = payload["category_label"]
            evidence_payload["rule_code"] = rule_code
            evidence_payload["rule_version"] = BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION
            payload["auto_category_evidence"] = evidence_payload
        return payload

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
    manual = manual_category if isinstance(manual_category, dict) else {}
    manual_code = manual.get("category_code")
    manual_source = str(manual.get("source") or "").strip()
    auto = auto_category if isinstance(auto_category, dict) else {}
    auto_code = auto.get("category_code")
    if manual_code in BANK_TRANSACTION_CATEGORY_DEFINITIONS and (
        manual_source == "turnover_ledger" or auto_code == "external_turnover"
    ):
        return {
            "effective_category_code": manual_code,
            "effective_category_label": manual.get("category_label"),
            "effective_category_primary_label": manual.get("category_primary_label"),
            "effective_category_sub_label": manual.get("category_sub_label"),
            "effective_category_label_path": list(manual.get("category_label_path") or []),
            "effective_category_path": list(manual.get("category_path") or []),
            "effective_category_source": manual_source or "manual",
        }
    if auto_code:
        return {
            "effective_category_code": auto_code,
            "effective_category_label": auto.get("category_label"),
            "effective_category_primary_label": auto.get("category_primary_label"),
            "effective_category_sub_label": auto.get("category_sub_label"),
            "effective_category_label_path": list(auto.get("category_label_path") or []),
            "effective_category_path": list(auto.get("category_path") or []),
            "effective_category_source": "auto",
        }
    return {
        "effective_category_code": None,
        "effective_category_label": None,
        "effective_category_primary_label": None,
        "effective_category_sub_label": None,
        "effective_category_label_path": [],
        "effective_category_path": [],
        "effective_category_source": "",
    }
