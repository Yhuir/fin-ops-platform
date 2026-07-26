from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Iterator

from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BankTransactionAutoCategoryService,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryService,
)
from fin_ops_platform.services.bank_transaction_effective_category_provider import (
    BankTransactionEffectiveCategoryProvider,
)
from fin_ops_platform.services.cost_statistics_bank_tags import bank_tag_context_from_row
from fin_ops_platform.services.postgres_repositories.common import row_payload
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    PostgresOAProjectionRepository,
)


class PostgresCostStatisticsCanonicalRepository:
    """Load every Cost page input from canonical tables in one DB snapshot."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Cost statistics canonical repository requires a PostgreSQL connection.")
        self._connection = connection

    def load_snapshot(self) -> dict[str, Any]:
        with self._snapshot_transaction() as transaction:
            settings = _settings_payload(transaction)
            bank_rows = _postgres_bank_rows(transaction, settings=settings)
            category_provider = _postgres_category_provider(
                transaction,
                settings=settings,
            )
            _apply_bank_tags(bank_rows, category_provider=category_provider)
            relations = _postgres_relations(transaction)
            oa_ids = _relation_member_ids(relations, {"oa"})
            oa_rows = [
                _object_payload(record)
                for record in PostgresOAProjectionRepository(
                    transaction
                ).list_application_records_by_row_ids(oa_ids)
            ]
            return _build_snapshot(
                settings=settings,
                bank_rows=bank_rows,
                oa_rows=oa_rows,
                relations=relations,
            )

    @contextmanager
    def _snapshot_transaction(self) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield transaction


class LocalCostStatisticsCanonicalRepository:
    """Canonical local-state adapter used by tests and non-PostgreSQL development."""

    def __init__(
        self,
        *,
        bank_rows_provider: Callable[[], list[Any]],
        relations_provider: Callable[[], list[dict[str, Any]]],
        oa_rows_by_ids_provider: Callable[[list[str]], list[Any]],
        settings_provider: Callable[[], dict[str, Any]],
        category_provider: Any,
    ) -> None:
        self._bank_rows_provider = bank_rows_provider
        self._relations_provider = relations_provider
        self._oa_rows_by_ids_provider = oa_rows_by_ids_provider
        self._settings_provider = settings_provider
        self._category_provider = category_provider

    def load_snapshot(self) -> dict[str, Any]:
        settings = dict(self._settings_provider() or {})
        bank_rows = [
            _bank_row_from_object(row, settings=settings)
            for row in self._bank_rows_provider()
        ]
        bank_rows = [row for row in bank_rows if row]
        _apply_bank_tags(bank_rows, category_provider=self._category_provider)
        relations = [
            dict(relation)
            for relation in self._relations_provider()
            if isinstance(relation, dict)
            and str(relation.get("status") or "active").strip().lower() == "active"
        ]
        oa_ids = _relation_member_ids(relations, {"oa"})
        oa_rows = [
            _object_payload(row)
            for row in self._oa_rows_by_ids_provider(oa_ids)
        ]
        return _build_snapshot(
            settings=settings,
            bank_rows=bank_rows,
            oa_rows=oa_rows,
            relations=relations,
        )


def _settings_payload(connection: Any) -> dict[str, Any]:
    row = connection.fetch_one(
        """
        select settings_payload
        from app.app_settings
        where settings_key = 'app_settings'
        limit 1
        """
    )
    payload = row.get("settings_payload") if isinstance(row, dict) else None
    return dict(payload) if isinstance(payload, dict) else {}


def _postgres_bank_rows(
    connection: Any,
    *,
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
            coalesce(legacy_mongo_id, id::text) as row_id,
            account_no,
            account_name,
            txn_direction,
            counterparty_name_raw,
            amount,
            signed_amount,
            txn_date,
            trade_time,
            pay_receive_time,
            summary,
            remark,
            project_id,
            bank_text_fields,
            raw_payload
        from app.bank_transactions
        where status <> 'deleted'
        order by coalesce(trade_time, txn_date::timestamptz) desc, row_id
        """
    )
    return [
        bank_payload
        for row in rows
        if (
            bank_payload := _bank_row_from_mapping(
                row,
                settings=settings,
            )
        )
    ]


def _postgres_category_provider(
    connection: Any,
    *,
    settings: dict[str, Any],
) -> BankTransactionEffectiveCategoryProvider:
    categories: dict[str, dict[str, Any]] = {}
    for row in connection.fetch_all(
        """
        select
            coalesce(legacy_transaction_id, bank_transaction_id::text) as transaction_id,
            category,
            source,
            version,
            updated_by,
            updated_at,
            raw_payload
        from app.bank_transaction_categories
        where status = 'active'
        order by updated_at, id
        """
    ):
        transaction_id = _text(row.get("transaction_id"))
        if not transaction_id:
            continue
        payload = row_payload(row, "raw_payload")
        normalized = dict(payload) if isinstance(payload, dict) else {}
        normalized.update(
            {
                "transaction_id": transaction_id,
                "category_code": _text(
                    normalized.get("category_code")
                    or normalized.get("category")
                    or row.get("category")
                ),
                "source": _text(normalized.get("source") or row.get("source")),
                "version": int(normalized.get("version") or row.get("version") or 1),
                "updated_by": _text(
                    normalized.get("updated_by") or row.get("updated_by")
                ),
                "updated_at": _date_text(
                    normalized.get("updated_at") or row.get("updated_at")
                ),
            }
        )
        categories[transaction_id] = normalized
    for row in connection.fetch_all(
        """
        select
            coalesce(legacy_transaction_id, bank_transaction_id::text) as transaction_id,
            category_code,
            candidate_category_codes,
            rule_version,
            version,
            confirmed_by,
            confirmed_at,
            raw_payload
        from app.bank_transaction_category_confirmations
        where status = 'active'
        order by confirmed_at, id
        """
    ):
        transaction_id = _text(row.get("transaction_id"))
        category_code = _text(row.get("category_code"))
        if not transaction_id or not category_code:
            continue
        payload = row_payload(row, "raw_payload")
        normalized = dict(payload) if isinstance(payload, dict) else {}
        normalized.update(
            {
                "transaction_id": transaction_id,
                "category_code": category_code,
                "source": "auto_confirmation",
                "version": int(normalized.get("version") or row.get("version") or 1),
                "updated_by": _text(
                    normalized.get("updated_by") or row.get("confirmed_by")
                ),
                "updated_at": _date_text(
                    normalized.get("updated_at") or row.get("confirmed_at")
                ),
                "candidate_category_codes": [
                    _text(value)
                    for value in list(
                        row.get("candidate_category_codes")
                        or normalized.get("candidate_category_codes")
                        or []
                    )
                    if _text(value)
                ],
                "rule_version": _text(
                    row.get("rule_version") or normalized.get("rule_version")
                ),
            }
        )
        categories[transaction_id] = normalized
    tag_dictionary = (
        settings.get("bank_transaction_tags")
        if isinstance(settings.get("bank_transaction_tags"), dict)
        else {}
    )
    category_service = BankTransactionCategoryService(
        categories=categories,
        tag_dictionary=tag_dictionary,
    )
    auto_category_service = BankTransactionAutoCategoryService(
        category_service=category_service,
    )
    return BankTransactionEffectiveCategoryProvider(
        category_service=category_service,
        auto_category_service=auto_category_service,
    )


def _postgres_relations(connection: Any) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
            case_id,
            relation_mode,
            row_ids,
            row_types,
            month_scope,
            special_metadata,
            raw_payload
        from app.workbench_pair_relations
        where status = 'active'
          and row_types && array['oa']::text[]
          and row_types && array['bank', 'bank_transaction']::text[]
        order by case_id
        """
    )
    relations: list[dict[str, Any]] = []
    for row in rows:
        raw = row_payload(row, "raw_payload")
        relation = dict(raw) if isinstance(raw, dict) else {}
        relation.update(
            {
                "case_id": _text(row.get("case_id")),
                "relation_mode": _text(
                    row.get("relation_mode") or relation.get("relation_mode")
                ),
                "row_ids": [
                    _text(value)
                    for value in list(row.get("row_ids") or relation.get("row_ids") or [])
                    if _text(value)
                ],
                "row_types": [
                    _text(value).lower()
                    for value in list(
                        row.get("row_types") or relation.get("row_types") or []
                    )
                    if _text(value)
                ],
                "month_scope": _text(
                    row.get("month_scope") or relation.get("month_scope")
                ),
                "special_metadata": (
                    dict(row.get("special_metadata"))
                    if isinstance(row.get("special_metadata"), dict)
                    else dict(relation.get("special_metadata") or {})
                ),
                "status": "active",
            }
        )
        relations.append(relation)
    return relations


def _build_snapshot(
    *,
    settings: dict[str, Any],
    bank_rows: list[dict[str, Any]],
    oa_rows: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    banks_by_id = {
        _text(row.get("id") or row.get("transaction_id") or row.get("row_id")): row
        for row in bank_rows
        if _text(row.get("id") or row.get("transaction_id") or row.get("row_id"))
    }
    oa_by_id = {
        _text(row.get("id") or row.get("row_id")): row
        for row in oa_rows
        if _text(row.get("id") or row.get("row_id"))
    }
    groups: list[dict[str, Any]] = []
    for relation in relations:
        row_ids = [
            _text(value)
            for value in list(relation.get("row_ids") or [])
        ]
        row_types = [
            _text(value).lower()
            for value in list(relation.get("row_types") or [])
        ]
        oa_members: list[dict[str, Any]] = []
        bank_members: list[dict[str, Any]] = []
        for index, row_id in enumerate(row_ids):
            row_type = row_types[index] if index < len(row_types) else ""
            if row_type == "oa" and row_id in oa_by_id:
                oa_members.append(oa_by_id[row_id])
            elif row_type in {"bank", "bank_transaction"} and row_id in banks_by_id:
                bank_members.append(banks_by_id[row_id])
        if oa_members and bank_members:
            groups.append(
                {
                    "group_id": _text(
                        relation.get("case_id") or relation.get("group_id")
                    ),
                    "relation_mode": _text(relation.get("relation_mode")),
                    "oa_rows": oa_members,
                    "bank_rows": bank_members,
                    "special_metadata": dict(
                        relation.get("special_metadata") or {}
                    ),
                }
            )
    return {
        "settings": settings,
        "bank_rows": list(banks_by_id.values()),
        "cost_groups": groups,
        "active_relation_count": len(relations),
    }


def _apply_bank_tags(
    bank_rows: list[dict[str, Any]],
    *,
    category_provider: Any,
) -> None:
    categories = category_provider.bulk_get_for_rows(bank_rows)
    for row in bank_rows:
        transaction_id = _text(
            row.get("id") or row.get("transaction_id") or row.get("row_id")
        )
        row.update(bank_tag_context_from_row(categories.get(transaction_id) or {}))


def _bank_row_from_object(
    row: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    return _bank_row_from_mapping(_object_payload(row), settings=settings)


def _bank_row_from_mapping(
    row: dict[str, Any],
    *,
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    row_id = _text(
        row.get("row_id")
        or row.get("id")
        or row.get("transaction_id")
        or row.get("legacy_id")
    )
    if not row_id:
        return None
    direction = _direction(row)
    amount = _decimal(row.get("amount"))
    if amount is None:
        return None
    account_no = _text(row.get("account_no"))
    account_name = _text(row.get("account_name"))
    bank_mapping = {
        _text(item.get("last4")): _text(item.get("bank_name"))
        for item in list(settings.get("bank_account_mappings") or [])
        if isinstance(item, dict)
        and _text(item.get("last4"))
        and _text(item.get("bank_name"))
    }
    resolver = BankAccountResolver(mapping_provider=lambda: bank_mapping)
    trade_time = _date_text(
        row.get("trade_time")
        or row.get("pay_receive_time")
        or row.get("txn_date")
    )
    return {
        **dict(row),
        "id": row_id,
        "row_id": row_id,
        "transaction_id": row_id,
        "type": "bank",
        "txn_direction": direction,
        "direction": "收入" if direction == "inflow" else "支出",
        "amount": amount,
        "debit_amount": amount if direction == "outflow" else None,
        "credit_amount": amount if direction == "inflow" else None,
        "trade_time": trade_time,
        "pay_receive_time": _date_text(
            row.get("pay_receive_time")
            or row.get("trade_time")
            or row.get("txn_date")
        ),
        "counterparty_name": _text(
            row.get("counterparty_name")
            or row.get("counterparty_name_raw")
        ),
        "counterparty_name_raw": _text(
            row.get("counterparty_name_raw")
            or row.get("counterparty_name")
        ),
        "payment_account_label": resolver.resolve_label(
            account_no,
            account_name,
        ),
        "summary": _text(row.get("summary")),
        "remark": _text(row.get("remark")),
    }


def _relation_member_ids(
    relations: list[dict[str, Any]],
    accepted_types: set[str],
) -> list[str]:
    member_ids: list[str] = []
    seen: set[str] = set()
    for relation in relations:
        row_ids = list(relation.get("row_ids") or [])
        row_types = list(relation.get("row_types") or [])
        for index, raw_id in enumerate(row_ids):
            row_id = _text(raw_id)
            row_type = (
                _text(row_types[index]).lower()
                if index < len(row_types)
                else ""
            )
            if row_id and row_type in accepted_types and row_id not in seen:
                seen.add(row_id)
                member_ids.append(row_id)
    return member_ids


def _object_payload(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    return dict(value) if isinstance(value, dict) else {}


def _direction(row: dict[str, Any]) -> str:
    value = row.get("txn_direction") or row.get("direction")
    if hasattr(value, "value"):
        value = value.value
    normalized = _text(value).lower()
    if normalized in {"inflow", "income", "收", "收入", "进"}:
        return "inflow"
    if normalized in {"outflow", "expense", "支", "支出", "出"}:
        return "outflow"
    signed = _decimal(row.get("signed_amount"))
    return "inflow" if signed is not None and signed > 0 else "outflow"


def _date_text(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return _text(value)


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "", "--", "—"):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (ArithmeticError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()
