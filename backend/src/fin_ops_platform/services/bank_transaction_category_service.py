from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import re
from threading import RLock
from typing import Any, Callable


BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION = "2026-05-bank-transaction-category-taxonomy"
BANK_TRANSACTION_CATEGORY_TAXONOMY: list[dict[str, Any]] = [
    {
        "root": "借入",
        "groups": [
            {
                "name": "个人往来款",
                "display_name": "个人暂借款",
                "items": [
                    ("borrow_in_personal_pending_repayment", "待还款"),
                    ("borrow_in_personal_repaid", "已还款"),
                ],
            },
            {
                "name": "公司往来款",
                "display_name": "公司暂借款",
                "items": [
                    ("borrow_in_company_pending_repayment", "待还款"),
                    ("borrow_in_company_repaid", "已还款"),
                ],
            },
            {
                "name": "银行往来款",
                "display_name": "银行往来款",
                "items": [
                    ("borrow_in_bank_pending_repayment", "待还款"),
                    ("borrow_in_bank_repaid", "已还款"),
                ],
            },
        ],
    },
    {
        "root": "借出",
        "groups": [
            {
                "name": "个人往来款",
                "display_name": "个人往来款",
                "items": [
                    ("borrow_out_personal_lent", "已借款"),
                    ("borrow_out_personal_pending_collection", "待收款"),
                ],
            },
            {
                "name": "公司往来款",
                "display_name": "公司往来款",
                "items": [
                    ("borrow_out_company_lent", "已借款"),
                    ("borrow_out_company_pending_collection", "待收款"),
                ],
            },
            {
                "name": "货款往来款",
                "display_name": "货款往来款",
                "items": [
                    ("borrow_out_goods_lent", "已借款"),
                    ("borrow_out_goods_pending_collection", "待收款"),
                ],
            },
        ],
    },
    {
        "root": "业务往来",
        "groups": [
            {
                "name": "质保金",
                "display_name": "质保金",
                "items": [("business_warranty_pending_collection", "待收款")],
            },
            {
                "name": "投标保证金",
                "display_name": "投标保证金",
                "items": [("business_bid_bond_pending_collection", "待收款")],
            },
            {
                "name": "履约保证金",
                "display_name": "履约保证金",
                "items": [("business_performance_bond_pending_collection", "待收款")],
            },
            {
                "name": "已开发票未收款",
                "display_name": "已开发票未收款",
                "items": [("business_invoiced_pending_collection", "待收款")],
            },
        ],
    },
]


def _build_category_definitions() -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}
    for root_node in BANK_TRANSACTION_CATEGORY_TAXONOMY:
        root = str(root_node["root"])
        for group in list(root_node["groups"]):
            group_name = str(group["name"])
            display_name = str(group["display_name"])
            for code, status in list(group["items"]):
                definitions[str(code)] = {
                    "category_code": str(code),
                    "category_label": f"{display_name}：{status}",
                    "category_path": [root, group_name, str(status)],
                    "category_root": root,
                    "category_group": group_name,
                    "category_status": str(status),
                }
    return definitions


BANK_TRANSACTION_CATEGORY_DEFINITIONS = _build_category_definitions()
BANK_TRANSACTION_AUTO_CATEGORY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "fee": {
        "category_code": "fee",
        "category_label": "手续费",
        "category_path": ["自动识别", "手续费"],
    },
    "salary": {
        "category_code": "salary",
        "category_label": "工资",
        "category_path": ["自动识别", "工资"],
    },
    "holiday_bonus": {
        "category_code": "holiday_bonus",
        "category_label": "过节费",
        "category_path": ["自动识别", "过节费"],
    },
    "bonus": {
        "category_code": "bonus",
        "category_label": "奖金",
        "category_path": ["自动识别", "奖金"],
    },
    "tax_payment": {
        "category_code": "tax_payment",
        "category_label": "税款",
        "category_path": ["自动识别", "税款"],
    },
    "treasury_tax_collection": {
        "category_code": "treasury_tax_collection",
        "category_label": "代理国库税收收缴",
        "category_path": ["自动识别", "代理国库税收收缴"],
    },
    "social_security": {
        "category_code": "social_security",
        "category_label": "社保款",
        "category_path": ["自动识别", "社保款"],
    },
}
BANK_TRANSACTION_LEGACY_CATEGORY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "external_turnover": {
        "category_code": "external_turnover",
        "category_label": "外部往来款",
        "category_path": [],
    },
    "internal_transfer": {
        "category_code": "internal_transfer",
        "category_label": "内部往来款",
        "category_path": ["自动识别", "内部往来款"],
    },
    "offset": {
        "category_code": "offset",
        "category_label": "冲",
        "category_path": [],
    },
    "cash_turnover": {
        "category_code": "cash_turnover",
        "category_label": "现金往来",
        "category_path": [],
    },
}
BANK_TRANSACTION_LEGACY_CATEGORY_LABELS: dict[str, str] = {
    code: str(definition["category_label"])
    for code, definition in BANK_TRANSACTION_LEGACY_CATEGORY_DEFINITIONS.items()
}
BANK_TRANSACTION_CATEGORY_LABELS: dict[str, str] = {
    **{
        code: str(definition["category_label"])
        for code, definition in BANK_TRANSACTION_CATEGORY_DEFINITIONS.items()
    },
    **{
        code: str(definition["category_label"])
        for code, definition in BANK_TRANSACTION_AUTO_CATEGORY_DEFINITIONS.items()
    },
    **BANK_TRANSACTION_LEGACY_CATEGORY_LABELS,
}
BANK_TRANSACTION_CATEGORY_COUNT_KEYS = [
    *BANK_TRANSACTION_CATEGORY_DEFINITIONS.keys(),
    *BANK_TRANSACTION_AUTO_CATEGORY_DEFINITIONS.keys(),
    *BANK_TRANSACTION_LEGACY_CATEGORY_LABELS.keys(),
    "uncategorized",
]
BANK_TRANSACTION_TAG_DICTIONARY_INITIAL_VERSION = 1
BANK_TRANSACTION_TAG_CODE_RE = re.compile(r"^[A-Za-z0-9_:-]+$")


def build_system_bank_transaction_tag_definitions() -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for source in (
        BANK_TRANSACTION_CATEGORY_DEFINITIONS,
        BANK_TRANSACTION_AUTO_CATEGORY_DEFINITIONS,
        BANK_TRANSACTION_LEGACY_CATEGORY_DEFINITIONS,
    ):
        for code, definition in source.items():
            definitions.append(
                {
                    "code": str(code),
                    "label": str(definition.get("category_label") or code),
                    "path": [
                        str(item)
                        for item in list(definition.get("category_path") or [])
                        if str(item).strip()
                    ],
                    "source": "system",
                    "status": "active",
                }
            )
    return definitions


def default_bank_transaction_tag_dictionary_payload() -> dict[str, Any]:
    return {
        "version": BANK_TRANSACTION_TAG_DICTIONARY_INITIAL_VERSION,
        "definitions": build_system_bank_transaction_tag_definitions(),
    }


class BankTransactionCategoryError(ValueError):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        transaction_id: str | None = None,
        expected_version: int | None = None,
        actual_version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.transaction_id = transaction_id
        self.expected_version = expected_version
        self.actual_version = actual_version


class BankTransactionCategoryValidationError(BankTransactionCategoryError):
    pass


class BankTransactionCategoryConflictError(BankTransactionCategoryError):
    pass


class BankTransactionCategoryService:
    def __init__(
        self,
        *,
        categories: dict[str, dict[str, Any]] | None = None,
        audit_log: list[dict[str, Any]] | None = None,
        tag_dictionary: dict[str, Any] | None = None,
        transaction_exists: Callable[[str], bool] | None = None,
    ) -> None:
        self._lock = RLock()
        self._transaction_exists = transaction_exists
        self._tag_dictionary_payload = self._normalize_tag_dictionary_payload(tag_dictionary)
        self._tag_definitions_by_code = self._build_tag_definition_index(self._tag_dictionary_payload)
        self._categories = self._normalize_categories(categories or {})
        self._audit_log = [
            deepcopy(entry)
            for entry in list(audit_log or [])
            if isinstance(entry, dict)
        ]

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any] | None,
        *,
        transaction_exists: Callable[[str], bool] | None = None,
    ) -> "BankTransactionCategoryService":
        if not snapshot:
            return cls(transaction_exists=transaction_exists)
        categories = snapshot.get("categories")
        audit_log = snapshot.get("audit_log")
        tag_dictionary = snapshot.get("tag_dictionary")
        return cls(
            categories=categories if isinstance(categories, dict) else {},
            audit_log=audit_log if isinstance(audit_log, list) else [],
            tag_dictionary=tag_dictionary if isinstance(tag_dictionary, dict) else None,
            transaction_exists=transaction_exists,
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION,
                "categories": deepcopy(self._categories),
                "audit_log": deepcopy(self._audit_log),
                "tag_dictionary": deepcopy(self._tag_dictionary_payload),
            }

    def tag_dictionary_payload(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._tag_dictionary_payload)

    def configure_tag_dictionary(self, payload: dict[str, Any] | None) -> None:
        normalized_payload = self._normalize_tag_dictionary_payload(payload)
        with self._lock:
            self._tag_dictionary_payload = normalized_payload
            self._tag_definitions_by_code = self._build_tag_definition_index(normalized_payload)

    def get(self, transaction_id: str) -> dict[str, Any]:
        transaction_key = self._normalize_transaction_id(transaction_id)
        with self._lock:
            return self._public_record(transaction_key, self._categories.get(transaction_key))

    def bulk_get(self, transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized_ids = [
            self._normalize_transaction_id(transaction_id)
            for transaction_id in list(transaction_ids or [])
            if str(transaction_id or "").strip()
        ]
        with self._lock:
            return {
                transaction_id: self._public_record(transaction_id, self._categories.get(transaction_id))
                for transaction_id in normalized_ids
            }

    def apply_updates(self, updates: list[dict[str, Any]], *, actor: str) -> dict[str, Any]:
        normalized_actor = str(actor or "").strip()
        if not normalized_actor:
            raise BankTransactionCategoryValidationError(
                "permission_denied",
                "actor is required to update bank transaction categories.",
            )
        if not isinstance(updates, list) or not updates:
            raise BankTransactionCategoryValidationError(
                "invalid_category_update",
                "updates must be a non-empty array.",
            )

        timestamp = datetime.now(UTC).isoformat()
        with self._lock:
            normalized_updates = [self._normalize_update(update) for update in updates]
            transaction_ids = [update["transaction_id"] for update in normalized_updates]
            if len(set(transaction_ids)) != len(transaction_ids):
                raise BankTransactionCategoryValidationError(
                    "invalid_category_update",
                    "duplicate transaction_id in updates.",
                )

            for update in normalized_updates:
                transaction_id = update["transaction_id"]
                if self._transaction_exists is not None and not self._transaction_exists(transaction_id):
                    raise BankTransactionCategoryValidationError(
                        "unknown_transaction_id",
                        f"Unknown bank transaction id: {transaction_id}",
                        transaction_id=transaction_id,
                    )
                actual_version = self._current_version(transaction_id)
                expected_version = update.get("expected_version")
                if expected_version is not None and expected_version != actual_version:
                    raise BankTransactionCategoryConflictError(
                        "category_version_conflict",
                        "Bank transaction category version conflict.",
                        transaction_id=transaction_id,
                        expected_version=expected_version,
                        actual_version=actual_version,
                    )

            updated_categories: list[dict[str, Any]] = []
            audit_entries: list[dict[str, Any]] = []
            for update in normalized_updates:
                transaction_id = update["transaction_id"]
                category_code = update["category_code"]
                existing = self._categories.get(transaction_id)
                previous_code = existing.get("category_code") if isinstance(existing, dict) else None
                if existing is not None and previous_code == category_code:
                    updated_categories.append(self._public_record(transaction_id, existing))
                    continue

                next_version = self._current_version(transaction_id) + 1
                record = {
                    "transaction_id": transaction_id,
                    "category_code": category_code,
                    "category_label": self._label_for(category_code),
                    "category_path": self._path_for(category_code),
                    "source": "manual",
                    "updated_by": normalized_actor,
                    "updated_at": timestamp,
                    "version": next_version,
                }
                self._categories[transaction_id] = record
                updated_categories.append(self._public_record(transaction_id, record))
                audit_entries.append(
                    {
                        "transaction_id": transaction_id,
                        "previous_category_code": previous_code,
                        "category_code": category_code,
                        "updated_by": normalized_actor,
                        "updated_at": timestamp,
                        "version": next_version,
                    }
                )

            self._audit_log.extend(audit_entries)
            return {
                "updated_transaction_ids": [entry["transaction_id"] for entry in updated_categories],
                "updated_categories": [
                    {
                        "transaction_id": entry["transaction_id"],
                        "category_code": entry["category_code"],
                        "category_label": entry["category_label"],
                        "category_path": entry["category_path"],
                        "version": entry["category_version"],
                    }
                    for entry in updated_categories
                ],
            }

    def category_counts(self, transaction_ids: list[str]) -> dict[str, int]:
        counts = {key: 0 for key in self.tag_count_keys()}
        normalized_ids = [
            self._normalize_transaction_id(transaction_id)
            for transaction_id in list(transaction_ids or [])
            if str(transaction_id or "").strip()
        ]
        with self._lock:
            for transaction_id in normalized_ids:
                category_code = self._categories.get(transaction_id, {}).get("category_code")
                if self.has_tag_definition(category_code):
                    counts.setdefault(str(category_code), 0)
                    counts[str(category_code)] += 1
                else:
                    counts["uncategorized"] += 1
        return counts

    @staticmethod
    def label_for(category_code: str | None) -> str | None:
        if category_code is None:
            return None
        return BANK_TRANSACTION_CATEGORY_LABELS.get(category_code)

    @staticmethod
    def path_for(category_code: str | None) -> list[str]:
        if category_code is None:
            return []
        definition = BANK_TRANSACTION_CATEGORY_DEFINITIONS.get(category_code)
        if definition is None:
            definition = BANK_TRANSACTION_AUTO_CATEGORY_DEFINITIONS.get(category_code)
        if definition is None:
            definition = BANK_TRANSACTION_LEGACY_CATEGORY_DEFINITIONS.get(category_code)
        if definition is None:
            return []
        return list(definition["category_path"])

    @classmethod
    def _build_tag_definition_index(cls, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(definition["code"]): dict(definition)
            for definition in list(payload.get("definitions") or [])
            if isinstance(definition, dict) and str(definition.get("code") or "").strip()
        }

    @classmethod
    def _normalize_tag_dictionary_payload(cls, payload: dict[str, Any] | None) -> dict[str, Any]:
        raw_payload = payload if isinstance(payload, dict) else {}
        version = cls._normalize_version(
            raw_payload.get("version", BANK_TRANSACTION_TAG_DICTIONARY_INITIAL_VERSION)
        )
        if version <= 0:
            version = BANK_TRANSACTION_TAG_DICTIONARY_INITIAL_VERSION

        definitions_by_code: dict[str, dict[str, Any]] = {
            definition["code"]: definition
            for definition in build_system_bank_transaction_tag_definitions()
        }
        for item in list(raw_payload.get("definitions") or []):
            if not isinstance(item, dict):
                continue
            definition = cls._normalize_tag_definition(item)
            code = definition["code"]
            if definition["source"] == "system" and code in definitions_by_code:
                definitions_by_code[code] = {
                    **definitions_by_code[code],
                    "status": definition["status"],
                }
                continue
            if code in definitions_by_code and definitions_by_code[code]["source"] == "system":
                continue
            definitions_by_code[code] = definition
        return {
            "version": version,
            "definitions": sorted(definitions_by_code.values(), key=lambda item: (item["source"] != "system", item["code"])),
        }

    @classmethod
    def _normalize_tag_definition(cls, item: dict[str, Any]) -> dict[str, Any]:
        label = str(item.get("label") or item.get("category_label") or "").strip()
        path = [
            str(value).strip()
            for value in list(item.get("path") or item.get("category_path") or [])
            if str(value).strip()
        ]
        code = str(item.get("code") or item.get("category_code") or "").strip()
        if not code:
            seed = json.dumps({"label": label, "path": path}, ensure_ascii=False, sort_keys=True)
            code = f"custom_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}"
        if not BANK_TRANSACTION_TAG_CODE_RE.match(code):
            code = f"custom_{hashlib.sha1(code.encode('utf-8')).hexdigest()[:12]}"
        source = str(item.get("source") or "custom").strip()
        if source not in {"system", "custom"}:
            source = "custom"
        status = str(item.get("status") or "active").strip()
        if status not in {"active", "archived"}:
            status = "active"
        return {
            "code": code,
            "label": label or code,
            "path": path,
            "source": source,
            "status": status,
        }

    def _normalize_categories(self, categories: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for transaction_id, record in categories.items():
            if not isinstance(record, dict):
                continue
            normalized_id = self._normalize_transaction_id(transaction_id or record.get("transaction_id"))
            if not normalized_id:
                continue
            category_code = self._normalize_category_code_current(record.get("category_code"))
            normalized[normalized_id] = {
                "transaction_id": normalized_id,
                "category_code": category_code,
                "category_label": self._label_for(category_code),
                "category_path": self._path_for(category_code),
                "source": str(record.get("source") or "manual").strip() or "manual",
                "updated_by": str(record.get("updated_by") or "").strip(),
                "updated_at": str(record.get("updated_at") or "").strip(),
                "version": self._normalize_version(record.get("version")),
            }
        return normalized

    def _normalize_update(self, update: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(update, dict):
            raise BankTransactionCategoryValidationError(
                "invalid_category_update",
                "each update must be an object.",
            )
        transaction_id = self._normalize_transaction_id(update.get("transaction_id"))
        if not transaction_id:
            raise BankTransactionCategoryValidationError(
                "unknown_transaction_id",
                "transaction_id is required.",
            )
        raw_code = update.get("category_code")
        category_code = None if raw_code is None else str(raw_code).strip()
        if category_code == "":
            category_code = None
        if category_code is not None:
            definition = self._tag_definitions_by_code.get(category_code)
            if not isinstance(definition, dict):
                raise BankTransactionCategoryValidationError(
                    "invalid_category_code",
                    f"Invalid bank transaction category code: {category_code}",
                    transaction_id=transaction_id,
                )
            if definition.get("status") == "archived":
                raise BankTransactionCategoryValidationError(
                    "archived_category_code",
                    f"Archived bank transaction category code cannot be selected: {category_code}",
                    transaction_id=transaction_id,
                )
        expected_version = update.get("expected_version")
        if expected_version is not None:
            expected_version = self._normalize_version(expected_version)
        return {
            "transaction_id": transaction_id,
            "category_code": category_code,
            "expected_version": expected_version,
        }

    @staticmethod
    def _normalize_transaction_id(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _normalize_category_code(value: Any) -> str | None:
        if value is None:
            return None
        category_code = str(value or "").strip()
        if not category_code:
            return None
        if category_code not in BANK_TRANSACTION_CATEGORY_LABELS:
            return None
        return category_code

    def _normalize_category_code_current(self, value: Any) -> str | None:
        if value is None:
            return None
        category_code = str(value or "").strip()
        if not category_code:
            return None
        if category_code not in self._tag_definitions_by_code:
            return category_code if category_code.startswith("custom_") else None
        return category_code

    @staticmethod
    def _normalize_version(value: Any) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0

    def _current_version(self, transaction_id: str) -> int:
        return self._normalize_version(self._categories.get(transaction_id, {}).get("version"))

    def _label_for(self, category_code: str | None) -> str | None:
        if category_code is None:
            return None
        definition = self._tag_definitions_by_code.get(category_code)
        if isinstance(definition, dict):
            return str(definition.get("label") or category_code)
        return self.label_for(category_code)

    def _path_for(self, category_code: str | None) -> list[str]:
        if category_code is None:
            return []
        definition = self._tag_definitions_by_code.get(category_code)
        if isinstance(definition, dict):
            return [
                str(item)
                for item in list(definition.get("path") or [])
                if str(item).strip()
            ]
        return self.path_for(category_code)

    def tag_count_keys(self) -> list[str]:
        with self._lock:
            active_codes = [
                str(code)
                for code, definition in self._tag_definitions_by_code.items()
                if definition.get("status") == "active"
            ]
        return [*active_codes, "uncategorized"]

    def has_tag_definition(self, category_code: str | None) -> bool:
        if category_code is None:
            return False
        with self._lock:
            return str(category_code) in self._tag_definitions_by_code

    def _public_record(self, transaction_id: str, record: dict[str, Any] | None) -> dict[str, Any]:
        category_code = record.get("category_code") if isinstance(record, dict) else None
        version = self._normalize_version(record.get("version")) if isinstance(record, dict) else 0
        return {
            "transaction_id": transaction_id,
            "category_code": category_code,
            "category_label": self._label_for(category_code),
            "category_path": self._path_for(category_code),
            "category_version": version,
            "source": str(record.get("source") or "") if isinstance(record, dict) else "",
            "updated_by": str(record.get("updated_by") or "") if isinstance(record, dict) else "",
            "updated_at": str(record.get("updated_at") or "") if isinstance(record, dict) else "",
        }
