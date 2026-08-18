from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields, is_dataclass
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
    COMPLETED_WORKFLOW_STATUS_ALIASES,
)


OA_COST_FORM_TYPES = ("支付申请", "日常报销")


class CostStatisticsIntegrityError(ValueError):
    """Canonical OA/bank relation facts are structurally inconsistent."""


class PostgresCostStatisticsCanonicalRepository:
    """Load every Cost page input from canonical tables in one DB snapshot."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Cost statistics canonical repository requires a PostgreSQL connection.")
        self._connection = connection

    def load_snapshot(
        self,
        *,
        scope_kind: str = "all",
        scope_value: str | None = None,
        view: str = "project",
        include_statistics: bool = True,
    ) -> dict[str, Any]:
        with self._snapshot_transaction() as transaction:
            settings = _settings_payload(transaction)
            scoped = not include_statistics and scope_kind != "all"
            bank_rows = _postgres_bank_rows(
                transaction,
                scope_kind=scope_kind if scoped else "all",
                scope_value=scope_value if scoped else None,
                settings=settings,
            )
            available_years = (
                _postgres_bank_available_years(transaction)
                if scoped
                else _bank_available_years(bank_rows)
            )
            bank_ids = _bank_row_ids(bank_rows)
            if view in {"time", "bank_tag"}:
                category_provider = _postgres_category_provider(
                    transaction,
                    settings=settings,
                    transaction_ids=bank_ids if scoped else None,
                )
                _apply_bank_tags(bank_rows, category_provider=category_provider)
                return _build_snapshot(
                    settings=settings,
                    bank_rows=bank_rows,
                    oa_rows=[],
                    relations=[],
                    available_years=available_years,
                )
            relations = _postgres_relations(
                transaction,
                bank_row_ids=bank_ids,
            )
            relation_bank_ids = _relation_member_ids(
                relations,
                {"bank", "bank_transaction"},
            )
            relation_bank_rows = (
                _postgres_bank_rows(
                    transaction,
                    settings=settings,
                    transaction_ids=relation_bank_ids,
                )
                if scoped
                else bank_rows
            )
            category_ids = list(
                dict.fromkeys([*bank_ids, *_bank_row_ids(relation_bank_rows)])
            )
            category_provider = _postgres_category_provider(
                transaction,
                settings=settings,
                transaction_ids=category_ids if scoped else None,
            )
            _apply_bank_tags(bank_rows, category_provider=category_provider)
            if relation_bank_rows is not bank_rows:
                _apply_bank_tags(
                    relation_bank_rows,
                    category_provider=category_provider,
                )
            relation_oa_ids = _relation_member_ids(relations, {"oa"})
            oa_rows = _postgres_oa_rows(transaction, oa_ids=relation_oa_ids)
            return _build_snapshot(
                settings=settings,
                bank_rows=bank_rows,
                relation_bank_rows=relation_bank_rows,
                oa_rows=oa_rows,
                relations=relations,
                available_years=available_years,
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

    def load_snapshot(
        self,
        *,
        scope_kind: str = "all",
        scope_value: str | None = None,
        view: str = "project",
        include_statistics: bool = True,
    ) -> dict[str, Any]:
        settings = dict(self._settings_provider() or {})
        account_resolver = _bank_account_resolver(settings)
        all_bank_rows = [
            _bank_row_from_object(row, account_resolver=account_resolver)
            for row in self._bank_rows_provider()
        ]
        all_bank_rows = [row for row in all_bank_rows if row]
        bank_available_years = _bank_available_years(all_bank_rows)
        scoped_bank_rows = [
            row
            for row in all_bank_rows
            if _bank_row_in_scope(
                row,
                scope_kind=scope_kind if not include_statistics else "all",
                scope_value=scope_value if not include_statistics else None,
            )
        ]
        all_relations = [
            dict(relation)
            for relation in self._relations_provider()
            if isinstance(relation, dict)
            and str(relation.get("status") or "active").strip().lower() == "active"
        ]
        _apply_bank_tags(scoped_bank_rows, category_provider=self._category_provider)
        if view in {"time", "bank_tag"}:
            return _build_snapshot(
                settings=settings,
                bank_rows=scoped_bank_rows,
                oa_rows=[],
                relations=[],
                available_years=bank_available_years,
            )
        scoped_bank_ids = set(_bank_row_ids(scoped_bank_rows))
        relations = [
            relation
            for relation in all_relations
            if scoped_bank_ids.intersection(
                _relation_member_ids([relation], {"bank", "bank_transaction"})
            )
            and _relation_member_ids([relation], {"oa"})
        ]
        relation_oa_ids = _relation_member_ids(relations, {"oa"})
        relation_bank_ids = set(
            _relation_member_ids(relations, {"bank", "bank_transaction"})
        )
        relation_bank_rows = [
            row
            for row in all_bank_rows
            if _text(row.get("id") or row.get("transaction_id") or row.get("row_id"))
            in relation_bank_ids
        ]
        _apply_bank_tags(relation_bank_rows, category_provider=self._category_provider)
        all_oa_rows = [
            _object_payload(row)
            for row in self._oa_rows_by_ids_provider(relation_oa_ids)
        ]
        relation_oa_id_set = set(relation_oa_ids)
        oa_rows = [
            row
            for row in all_oa_rows
            if _text(row.get("id") or row.get("row_id")) in relation_oa_id_set
        ]
        return _build_snapshot(
            settings=settings,
            bank_rows=scoped_bank_rows,
            relation_bank_rows=relation_bank_rows,
            oa_rows=oa_rows,
            relations=relations,
            available_years=bank_available_years,
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


def _postgres_bank_available_years(connection: Any) -> list[str]:
    return [
        str(int(row["year"]))
        for row in connection.fetch_all(
            """
            select distinct
                extract(year from txn_month)::int as year
            from app.bank_transactions
            where status <> 'deleted'
              and txn_month is not null
            order by year desc
            """
        )
        if row.get("year") is not None
    ]


def _bank_row_filter(
    *,
    scope_kind: str,
    scope_value: str | None,
    transaction_ids: list[str] | None,
) -> tuple[str, tuple[Any, ...]]:
    if transaction_ids is not None:
        return (
            "and (legacy_mongo_id = any(%s::text[]) or id::text = any(%s::text[]))",
            (transaction_ids, transaction_ids),
        )
    if scope_kind == "all":
        return "", ()
    if scope_kind == "year" and scope_value and len(scope_value) == 4:
        start = date(int(scope_value), 1, 1)
        end = date(int(scope_value) + 1, 1, 1)
    elif scope_kind == "month" and scope_value:
        year, month = (int(value) for value in scope_value.split("-", 1))
        start = date(year, month, 1)
        end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    else:
        raise ValueError("scope must be all, year, or month")
    return (
        "and txn_month >= %s and txn_month < %s",
        (start, end),
    )


def _postgres_bank_rows(
    connection: Any,
    *,
    settings: dict[str, Any],
    scope_kind: str = "all",
    scope_value: str | None = None,
    transaction_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    where_sql, params = _bank_row_filter(
        scope_kind=scope_kind,
        scope_value=scope_value,
        transaction_ids=transaction_ids,
    )
    account_resolver = _bank_account_resolver(settings)
    rows = connection.fetch_all(
        f"""
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
            bank_text_fields
        from app.bank_transactions
        where status <> 'deleted'
          {where_sql}
        order by coalesce(trade_time, txn_date::timestamptz) desc, row_id
        """,
        params,
    )
    return [
        bank_payload
        for row in rows
        if (
            bank_payload := _bank_row_from_mapping(
                row,
                account_resolver=account_resolver,
            )
        )
    ]


def _postgres_category_provider(
    connection: Any,
    *,
    settings: dict[str, Any],
    transaction_ids: list[str] | None = None,
) -> BankTransactionEffectiveCategoryProvider:
    categories: dict[str, dict[str, Any]] = {}
    filter_sql = ""
    params: tuple[Any, ...] = ()
    if transaction_ids is not None:
        filter_sql = (
            "and (legacy_transaction_id = any(%s::text[]) "
            "or bank_transaction_id::text = any(%s::text[]))"
        )
        params = (transaction_ids, transaction_ids)
    for row in connection.fetch_all(
        f"""
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
          {filter_sql}
        order by updated_at, id
        """,
        params,
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
        f"""
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
          {filter_sql}
        order by confirmed_at, id
        """,
        params,
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


def _postgres_relations(
    connection: Any,
    *,
    bank_row_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    if bank_row_ids is not None and not bank_row_ids:
        return []
    filter_sql = ""
    params: tuple[Any, ...] = ()
    if bank_row_ids is not None:
        filter_sql = """
          and exists (
              select 1
              from unnest(row_ids, row_types) as member(row_id, row_type)
              where member.row_type in ('bank', 'bank_transaction')
                and member.row_id = any(%s::text[])
          )
        """
        params = (bank_row_ids,)
    rows = connection.fetch_all(
        f"""
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
          {filter_sql}
        order by case_id
        """,
        params,
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


def _postgres_oa_rows(
    connection: Any,
    *,
    oa_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    if oa_ids is not None and not oa_ids:
        return []
    filter_sql = "and row_id = any(%s::text[])" if oa_ids is not None else ""
    filter_params: tuple[Any, ...] = (oa_ids,) if oa_ids is not None else ()
    rows = connection.fetch_all(
        f"""
        select row_id, form_type, workflow_status, approved_at, normalized_payload
        from app.oa_applications
        where form_type = any(%s::text[])
          {filter_sql}
        order by row_id
        """,
        (
            list(OA_COST_FORM_TYPES),
            *filter_params,
        ),
    )
    return [
        payload
        for row in rows
        if (
            payload := _cost_oa_payload(
                row_payload(row, "normalized_payload"),
                row_id=_text(row.get("row_id")),
                apply_type=_text(row.get("form_type")),
                workflow_status=_text(row.get("workflow_status")),
                completed_at=_date_text(row.get("approved_at")),
            )
        )
    ]


def _cost_oa_payload(
    raw: Any,
    *,
    row_id: str,
    apply_type: str = "",
    workflow_status: str = "",
    completed_at: str = "",
) -> dict[str, Any]:
    if not isinstance(raw, dict) or not row_id:
        return {}
    detail_fields = (
        raw.get("detail_fields")
        if isinstance(raw.get("detail_fields"), dict)
        else {}
    )
    expense_items = [
        {
            key: item.get(key)
            for key in (
                "expense_item_id",
                "row_id",
                "item_id",
                "project_id",
                "project_name",
                "expense_type",
                "expense_content",
                "reason",
                "settlement_amount",
                "amount",
                "total_with_tax",
            )
            if item.get(key) is not None
        }
        for item in list(raw.get("expense_items") or [])
        if isinstance(item, dict)
    ]
    return {
        "id": row_id,
        "row_id": row_id,
        "apply_type": apply_type or raw.get("apply_type"),
        "workflow_status": workflow_status or raw.get("workflow_status"),
        "completed_at": completed_at or raw.get("completed_at"),
        **{
            key: raw.get(key)
            for key in (
                "project_id",
                "project_name",
                "expense_type",
                "expense_content",
                "applicant",
                "counterparty_name",
                "amount",
                "reconciliation_amount",
                "reason",
            )
            if raw.get(key) is not None
        },
        "detail_fields": {
            key: detail_fields.get(key)
            for key in (
                "项目名称",
                "项目编号",
                "费用类型",
                "费用内容",
                "申请人",
            )
            if detail_fields.get(key) is not None
        },
        "expense_items": expense_items,
    }


def _build_snapshot(
    *,
    settings: dict[str, Any],
    bank_rows: list[dict[str, Any]],
    relation_bank_rows: list[dict[str, Any]] | None = None,
    oa_rows: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    available_years: list[str] | None = None,
) -> dict[str, Any]:
    banks_by_id = {
        _text(row.get("id") or row.get("transaction_id") or row.get("row_id")): row
        for row in bank_rows
        if _text(row.get("id") or row.get("transaction_id") or row.get("row_id"))
    }
    relation_banks_by_id = {
        _text(row.get("id") or row.get("transaction_id") or row.get("row_id")): row
        for row in list(relation_bank_rows if relation_bank_rows is not None else bank_rows)
        if _text(row.get("id") or row.get("transaction_id") or row.get("row_id"))
    }
    oa_by_id = {
        _text(row.get("id") or row.get("row_id")): row
        for row in oa_rows
        if _text(row.get("id") or row.get("row_id"))
    }
    groups: list[dict[str, Any]] = []
    oa_related_bank_ids: set[str] = set()
    for relation in relations:
        row_ids = [
            _text(value)
            for value in list(relation.get("row_ids") or [])
        ]
        row_types = [
            _text(value).lower()
            for value in list(relation.get("row_types") or [])
        ]
        if len(row_ids) != len(row_types):
            raise CostStatisticsIntegrityError(
                f"relation {_text(relation.get('case_id')) or '<unknown>'} has mismatched row_ids/row_types"
            )
        oa_members: list[dict[str, Any]] = []
        bank_members: list[dict[str, Any]] = []
        declared_oa_ids = {
            row_id
            for index, row_id in enumerate(row_ids)
            if index < len(row_types) and row_types[index] == "oa"
        }
        relation_has_oa = any(
            index < len(row_types) and _text(row_types[index]).lower() == "oa"
            for index in range(len(row_ids))
        )
        for index, row_id in enumerate(row_ids):
            row_type = row_types[index]
            if row_type == "oa" and row_id in oa_by_id:
                oa_members.append(oa_by_id[row_id])
            elif row_type in {"bank", "bank_transaction"} and row_id in relation_banks_by_id:
                bank_members.append(relation_banks_by_id[row_id])
                if relation_has_oa:
                    if row_id in banks_by_id:
                        oa_related_bank_ids.add(row_id)
        if declared_oa_ids and bank_members:
            groups.append(
                {
                    "group_id": _text(
                        relation.get("case_id") or relation.get("group_id")
                    ),
                    "relation_mode": _text(relation.get("relation_mode")),
                    "declared_oa_ids": sorted(declared_oa_ids),
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
        "oa_related_bank_ids": sorted(oa_related_bank_ids),
        "active_relation_count": len(relations),
        "available_years": list(available_years or []),
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
    account_resolver: BankAccountResolver,
) -> dict[str, Any] | None:
    return _bank_row_from_mapping(
        _object_payload(row),
        account_resolver=account_resolver,
    )


def _bank_account_resolver(settings: dict[str, Any]) -> BankAccountResolver:
    bank_mapping = {
        _text(item.get("last4")): _text(item.get("bank_name"))
        for item in list(settings.get("bank_account_mappings") or [])
        if isinstance(item, dict)
        and _text(item.get("last4"))
        and _text(item.get("bank_name"))
    }
    return BankAccountResolver(mapping_provider=lambda: bank_mapping)


def _bank_row_from_mapping(
    row: dict[str, Any],
    *,
    account_resolver: BankAccountResolver,
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
        "payment_account_label": account_resolver.resolve_label(
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


def _bank_row_ids(bank_rows: list[dict[str, Any]]) -> list[str]:
    return [
        row_id
        for row in bank_rows
        if (
            row_id := _text(
                row.get("id") or row.get("transaction_id") or row.get("row_id")
            )
        )
    ]


def _bank_row_in_scope(
    row: dict[str, Any],
    *,
    scope_kind: str,
    scope_value: str | None,
) -> bool:
    if scope_kind == "all":
        return True
    trade_time = _date_text(
        row.get("trade_time") or row.get("pay_receive_time") or row.get("txn_date")
    )
    if scope_kind == "year":
        return bool(scope_value and trade_time[:4] == scope_value)
    if scope_kind == "month":
        return bool(scope_value and trade_time[:7] == scope_value)
    raise ValueError("scope must be all, year, or month")


def _bank_available_years(bank_rows: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            trade_time[:4]
            for row in bank_rows
            if (
                trade_time := _date_text(
                    row.get("trade_time")
                    or row.get("pay_receive_time")
                    or row.get("txn_date")
                )
            )
            and len(trade_time) >= 4
            and trade_time[:4].isdigit()
        },
        reverse=True,
    )


def _oa_row_ids(oa_rows: list[dict[str, Any]]) -> list[str]:
    return [
        row_id
        for row in oa_rows
        if (row_id := _text(row.get("id") or row.get("row_id")))
    ]


def _is_explicit_completed_oa(row: dict[str, Any]) -> bool:
    return bool(
        _date_text(row.get("completed_at"))
        and _text(row.get("apply_type")) in OA_COST_FORM_TYPES
        and _text(row.get("workflow_status")) in COMPLETED_WORKFLOW_STATUS_ALIASES
    )


def _object_payload(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return {field.name: getattr(value, field.name) for field in fields(value)}
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
