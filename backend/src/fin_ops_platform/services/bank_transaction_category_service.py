from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
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
        transaction_exists: Callable[[str], bool] | None = None,
    ) -> None:
        self._lock = RLock()
        self._transaction_exists = transaction_exists
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
        return cls(
            categories=categories if isinstance(categories, dict) else {},
            audit_log=audit_log if isinstance(audit_log, list) else [],
            transaction_exists=transaction_exists,
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION,
                "categories": deepcopy(self._categories),
                "audit_log": deepcopy(self._audit_log),
            }

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
                    "category_label": self.label_for(category_code),
                    "category_path": self.path_for(category_code),
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
        counts = {key: 0 for key in BANK_TRANSACTION_CATEGORY_COUNT_KEYS}
        normalized_ids = [
            self._normalize_transaction_id(transaction_id)
            for transaction_id in list(transaction_ids or [])
            if str(transaction_id or "").strip()
        ]
        with self._lock:
            for transaction_id in normalized_ids:
                category_code = self._categories.get(transaction_id, {}).get("category_code")
                if category_code in BANK_TRANSACTION_CATEGORY_LABELS:
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
    def _normalize_categories(cls, categories: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for transaction_id, record in categories.items():
            if not isinstance(record, dict):
                continue
            normalized_id = cls._normalize_transaction_id(transaction_id or record.get("transaction_id"))
            if not normalized_id:
                continue
            category_code = cls._normalize_category_code(record.get("category_code"))
            normalized[normalized_id] = {
                "transaction_id": normalized_id,
                "category_code": category_code,
                "category_label": cls.label_for(category_code),
                "category_path": cls.path_for(category_code),
                "source": str(record.get("source") or "manual").strip() or "manual",
                "updated_by": str(record.get("updated_by") or "").strip(),
                "updated_at": str(record.get("updated_at") or "").strip(),
                "version": cls._normalize_version(record.get("version")),
            }
        return normalized

    @classmethod
    def _normalize_update(cls, update: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(update, dict):
            raise BankTransactionCategoryValidationError(
                "invalid_category_update",
                "each update must be an object.",
            )
        transaction_id = cls._normalize_transaction_id(update.get("transaction_id"))
        if not transaction_id:
            raise BankTransactionCategoryValidationError(
                "unknown_transaction_id",
                "transaction_id is required.",
            )
        raw_code = update.get("category_code")
        category_code = None if raw_code is None else str(raw_code).strip()
        if category_code == "":
            category_code = None
        if category_code is not None and category_code not in BANK_TRANSACTION_CATEGORY_LABELS:
            raise BankTransactionCategoryValidationError(
                "invalid_category_code",
                f"Invalid bank transaction category code: {category_code}",
                transaction_id=transaction_id,
            )
        expected_version = update.get("expected_version")
        if expected_version is not None:
            expected_version = cls._normalize_version(expected_version)
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

    @staticmethod
    def _normalize_version(value: Any) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0

    def _current_version(self, transaction_id: str) -> int:
        return self._normalize_version(self._categories.get(transaction_id, {}).get("version"))

    @classmethod
    def _public_record(cls, transaction_id: str, record: dict[str, Any] | None) -> dict[str, Any]:
        category_code = record.get("category_code") if isinstance(record, dict) else None
        version = cls._normalize_version(record.get("version")) if isinstance(record, dict) else 0
        return {
            "transaction_id": transaction_id,
            "category_code": category_code,
            "category_label": cls.label_for(category_code),
            "category_path": cls.path_for(category_code),
            "category_version": version,
            "source": str(record.get("source") or "") if isinstance(record, dict) else "",
            "updated_by": str(record.get("updated_by") or "") if isinstance(record, dict) else "",
            "updated_at": str(record.get("updated_at") or "") if isinstance(record, dict) else "",
        }
