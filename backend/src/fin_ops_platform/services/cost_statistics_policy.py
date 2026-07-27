from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import cached_property
import re
from typing import Any

from fin_ops_platform.services.app_settings_service import (
    AppSettingsService,
    COST_STATISTICS_UNCATEGORIZED_TAG_CODE,
)
from fin_ops_platform.services.bank_settings import bank_accounts_from_settings_payload
from fin_ops_platform.services.cost_statistics_bank_tags import bank_tag_context_from_row
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    is_completed_workflow_status,
)


ZERO = Decimal("0.00")
MONEY_QUANTUM = Decimal("0.01")
CASH_TICKET_PURCHASE_MODE = "cash_ticket_purchase"
UNATTRIBUTED_PROJECT_NAME = "未归集项目"
UNCATEGORIZED_EXPENSE_TYPE = "未分类"
MULTI_PROJECT_NAME = "多项目"
MULTI_EXPENSE_TYPE = "多费用类型"


class CostStatisticsPolicy:
    """Pure Cost business rules over one canonical database snapshot."""

    def __init__(
        self,
        snapshot: dict[str, Any],
        *,
        project_scope: str,
    ) -> None:
        if project_scope not in {"active", "all"}:
            raise ValueError("project_scope must be active or all")
        self._settings = dict(snapshot.get("settings") or {})
        self._bank_rows = [
            dict(row)
            for row in list(snapshot.get("bank_rows") or [])
            if isinstance(row, dict)
        ]
        self._groups = [
            dict(group)
            for group in list(snapshot.get("cost_groups") or [])
            if isinstance(group, dict)
        ]
        self._active_relation_count = int(snapshot.get("active_relation_count") or 0)
        self._available_years = [
            str(value)
            for value in list(snapshot.get("available_years") or [])
            if re.fullmatch(r"\d{4}", str(value))
        ]
        self._project_scope = project_scope
        self._selected_tag_codes = _selected_tag_codes(self._settings)

    @cached_property
    def bank_flow_rows(self) -> list[dict[str, Any]]:
        return [
            row
            for row in (_serialize_bank_row(row) for row in self._bank_rows)
            if _tag_selected(row, self._selected_tag_codes)
        ]

    @cached_property
    def serialized_cost_rows(self) -> list[dict[str, Any]]:
        return [
            _serialize_cost_entry(entry)
            for entry in _cost_entries(
                self._groups,
                project_scope=self._project_scope,
                settings=self._settings,
            )
            if _tag_selected(entry, self._selected_tag_codes)
        ]

    def explorer_page(
        self,
        *,
        scope_kind: str,
        scope_value: str | None,
        view: str,
        filters: dict[str, str],
        cursor_values: tuple[str, str, str, str] | None,
        page_size: int,
        include_statistics: bool = True,
    ) -> dict[str, Any]:
        bank_flow_view = view in {"time", "bank_tag"}
        base_rows = [
            row
            for row in (
                self.bank_flow_rows if bank_flow_view else self.serialized_cost_rows
            )
            if _row_in_scope(
                row,
                scope_kind=scope_kind,
                scope_value=scope_value,
            )
        ]
        base_rows.sort(key=_row_sort_key, reverse=True)
        project_name = _clean_text(filters.get("project_name"))
        expense_type = _clean_text(filters.get("expense_type"))
        payment_account_label = _clean_text(filters.get("payment_account_label"))
        tag_primary = _clean_text(filters.get("bank_tag_primary_label"))
        tag_sub = _clean_text(filters.get("bank_tag_sub_label"))

        primary_facets: list[dict[str, Any]] = []
        secondary_facets: list[dict[str, Any]] = []
        row_matches: list[dict[str, Any]] = []
        if view == "time":
            row_matches = base_rows
        elif view == "project":
            primary_facets = _project_facets(base_rows)
            if project_name:
                secondary_facets = _expense_facets(
                    [row for row in base_rows if row["project_name"] == project_name]
                )
            if project_name and expense_type:
                row_matches = [
                    row
                    for row in base_rows
                    if row["project_name"] == project_name
                    and row["expense_type"] == expense_type
                ]
        elif view == "bank":
            primary_facets = _bank_facets(base_rows)
            if payment_account_label:
                secondary_facets = _project_facets(
                    [
                        row
                        for row in base_rows
                        if row["payment_account_label"] == payment_account_label
                    ]
                )
            if payment_account_label and project_name:
                row_matches = [
                    row
                    for row in base_rows
                    if row["payment_account_label"] == payment_account_label
                    and row["project_name"] == project_name
                ]
        elif view == "expense_type":
            primary_facets = _expense_facets(base_rows)
            if expense_type:
                row_matches = [
                    row for row in base_rows if row["expense_type"] == expense_type
                ]
        elif view == "bank_tag":
            primary_facets = _bank_tag_primary_facets(base_rows)
            if tag_primary:
                secondary_facets = _bank_tag_sub_facets(
                    [
                        row
                        for row in base_rows
                        if _tag_primary(row) == tag_primary
                    ]
                )
            if tag_primary and tag_sub:
                row_matches = [
                    row
                    for row in base_rows
                    if _tag_primary(row) == tag_primary
                    and _tag_sub(row) == tag_sub
                ]
        else:
            raise ValueError("view must be time, project, bank, expense_type, or bank_tag")

        matched_row_count = len(row_matches)
        if cursor_values is not None:
            row_matches = [
                row
                for row in row_matches
                if _cursor_tuple(row) < cursor_values
            ]
        page_rows = row_matches[: page_size + 1]
        has_more = len(page_rows) > page_size
        page_rows = page_rows[:page_size]
        return {
            "summary": _summary(base_rows),
            "statistics": self.statistics if include_statistics else None,
            "available_years": self._available_years or sorted(
                {
                    str(row.get("month") or "")[:4]
                    for row in self.bank_flow_rows
                    if re.fullmatch(r"\d{4}", str(row.get("month") or "")[:4])
                },
                reverse=True,
            ),
            "primary_facets": primary_facets,
            "secondary_facets": secondary_facets,
            "row_count": matched_row_count,
            "rows": page_rows,
            "next_cursor_values": _cursor_tuple(page_rows[-1])
            if has_more and page_rows
            else None,
            "bank_accounts": bank_accounts_from_settings_payload(self._settings),
            "tag_selection_version": int(
                AppSettingsService.cost_statistics_tag_selection_payload_from_settings(
                    self._settings
                ).get("version")
                or 1
            ),
        }

    def export_page(
        self,
        *,
        month: str,
        start_month: str | None,
        end_month: str | None,
        start_date: str | None,
        end_date: str | None,
        project_names: list[str],
        expense_types: list[str],
        row_shape: str,
        offset: int,
        page_size: int,
        include_summary: bool,
    ) -> dict[str, Any]:
        if row_shape not in {
            "raw_bank",
            "raw_cost",
            "project_month",
            "project_year",
            "month_summary",
        }:
            raise ValueError("invalid cost statistics export row shape")
        source = (
            self.bank_flow_rows
            if row_shape == "raw_bank"
            else self.serialized_cost_rows
        )
        normalized_project_names = {
            _clean_text(value) for value in project_names if _clean_text(value)
        }
        normalized_expense_types = {
            _clean_text(value) for value in expense_types if _clean_text(value)
        }
        rows = [
            row
            for row in source
            if _row_in_export_range(
                row,
                month=month,
                start_month=start_month,
                end_month=end_month,
                start_date=start_date,
                end_date=end_date,
            )
            and (
                not normalized_project_names
                or row["project_name"] in normalized_project_names
            )
            and (
                not normalized_expense_types
                or row["expense_type"] in normalized_expense_types
            )
        ]
        rows.sort(key=_row_sort_key, reverse=True)
        result_rows: list[dict[str, Any]]
        if row_shape in {"project_month", "project_year", "month_summary"}:
            result_rows = _aggregate_export_rows(rows, row_shape=row_shape)
        else:
            result_rows = rows
        summary = _summary(rows) if include_summary else None
        if summary is not None:
            summary.update(
                {
                    "source_row_count": len(rows),
                    "row_count": len(result_rows),
                    "expense_type_count": len(
                        {row["expense_type"] for row in rows}
                    ),
                }
            )
        page_rows = result_rows[offset : offset + page_size]
        return {
            "summary": summary,
            "rows": page_rows,
            "next_offset": (
                offset + len(page_rows)
                if offset + len(page_rows) < len(result_rows)
                else None
            ),
        }

    def transaction(
        self,
        *,
        transaction_id: str,
        bank_flow_view: bool,
        scope_kind: str,
        scope_value: str | None,
    ) -> dict[str, Any] | None:
        source = (
            self.bank_flow_rows
            if bank_flow_view
            else self.serialized_cost_rows
        )
        matches = [
            row
            for row in source
            if row["transaction_id"] == transaction_id
            and _row_in_scope(
                row,
                scope_kind=scope_kind,
                scope_value=scope_value,
            )
        ]
        if not matches:
            return None
        row = dict(matches[0])
        row["cost_allocations"] = (
            []
            if bank_flow_view
            else [
                {
                    "row_key": allocation["row_key"],
                    "project_name": allocation["project_name"],
                    "project_id": allocation["project_id"],
                    "expense_type": allocation["expense_type"],
                    "expense_content": allocation["expense_content"],
                    "oa_applicant": allocation["oa_applicant"],
                    "amount": allocation["amount"],
                }
                for allocation in matches
            ]
        )
        return row

    @property
    def statistics(self) -> dict[str, int]:
        cost_rows = self.serialized_cost_rows
        tagged = [
            row
            for row in self.bank_flow_rows
            if _clean_text(row.get("bank_tag_code"))
        ]
        return {
            "transaction_count": len(
                {row["transaction_id"] for row in self.bank_flow_rows}
            ),
            "expense_transaction_count": len(
                {
                    row["transaction_id"]
                    for row in self.bank_flow_rows
                    if row["direction"] == "支出"
                }
            ),
            "income_transaction_count": len(
                {
                    row["transaction_id"]
                    for row in self.bank_flow_rows
                    if row["direction"] == "收入"
                }
            ),
            "cost_group_count": len(
                {row["group_id"] for row in cost_rows if row["group_id"]}
            ),
            "tagged_transaction_count": len(
                {row["transaction_id"] for row in tagged}
            ),
            "untagged_transaction_count": len(
                {row["transaction_id"] for row in self.bank_flow_rows}
                - {row["transaction_id"] for row in tagged}
            ),
            "project_count": len(
                {row["project_name"] for row in cost_rows}
            ),
            "expense_type_count": len(
                {row["expense_type"] for row in cost_rows}
            ),
            "bank_tag_count": len(
                {
                    _tag_sub(row)
                    for row in self.bank_flow_rows
                    if _clean_text(row.get("bank_tag_code"))
                }
            ),
            "cost_transaction_count": len(
                {row["transaction_id"] for row in cost_rows}
            ),
            "active_relation_count": self._active_relation_count,
        }


def _cost_entries(
    groups: list[dict[str, Any]],
    *,
    project_scope: str,
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    completed_project_ids, completed_project_names = (
        _completed_project_identities(settings)
        if project_scope == "active"
        else (set(), set())
    )
    entries: list[dict[str, Any]] = []
    for group in groups:
        oa_rows = [
            row
            for row in list(group.get("oa_rows") or [])
            if isinstance(row, dict)
        ]
        bank_rows = [
            row
            for row in list(group.get("bank_rows") or [])
            if isinstance(row, dict)
        ]
        if not oa_rows or not bank_rows:
            continue
        tag_contexts = {
            _clean_text(
                row.get("id")
                or row.get("transaction_id")
                or row.get("row_id")
            ): bank_tag_context_from_row(row)
            for row in bank_rows
        }
        special_metadata = (
            dict(group.get("special_metadata") or {})
            if isinstance(group.get("special_metadata"), dict)
            else {}
        )
        if _clean_text(special_metadata.get("cost_policy")) == "include_ticket_cost_only":
            ticket_entry = _cash_ticket_cost_entry(
                group,
                oa_rows=oa_rows,
                bank_rows=bank_rows,
                special_metadata=special_metadata,
                bank_tag_contexts=tag_contexts,
            )
            if ticket_entry is not None and not _is_completed_project_allocation(
                ticket_entry,
                completed_project_ids=completed_project_ids,
                completed_project_names=completed_project_names,
            ):
                entries.append(ticket_entry)
            continue
        for entry in _oa_cost_entries_for_group(
            group,
            oa_rows=oa_rows,
            bank_rows=bank_rows,
            bank_tag_contexts=tag_contexts,
        ):
            if not _is_completed_project_allocation(
                entry,
                completed_project_ids=completed_project_ids,
                completed_project_names=completed_project_names,
            ):
                entries.append(entry)
    return sorted(entries, key=_row_sort_key, reverse=True)


def _serialize_bank_row(row: dict[str, Any]) -> dict[str, Any]:
    transaction_id = _clean_text(
        row.get("id") or row.get("transaction_id") or row.get("row_id")
    )
    amount = abs(_decimal(row.get("amount")) or ZERO)
    direction = str(row.get("direction") or "").strip()
    if direction not in {"收入", "支出"}:
        direction = (
            "收入"
            if str(row.get("txn_direction") or "").strip().lower() == "inflow"
            else "支出"
        )
    trade_time = _clean_text(
        row.get("trade_time")
        or row.get("pay_receive_time")
        or row.get("txn_date")
    )
    return {
        "row_key": transaction_id,
        "group_id": "",
        "transaction_id": transaction_id,
        "month": trade_time[:7],
        "trade_time": trade_time,
        "direction": direction,
        "project_name": "未配对OA",
        "project_id": "",
        "expense_type": UNCATEGORIZED_EXPENSE_TYPE,
        "expense_content": _clean_text(
            row.get("summary") or row.get("remark")
        )
        or UNCATEGORIZED_EXPENSE_TYPE,
        "amount": _money(amount),
        "counterparty_name": _clean_text(
            row.get("counterparty_name")
            or row.get("counterparty_name_raw")
        ),
        "payment_account_label": _clean_text(
            row.get("payment_account_label")
        ),
        "remark": _clean_text(row.get("remark")),
        "oa_applicant": "—",
        **bank_tag_context_from_row(row),
    }


def _oa_cost_entries_for_group(
    group: dict[str, Any],
    *,
    oa_rows: list[dict[str, Any]],
    bank_rows: list[dict[str, Any]],
    bank_tag_contexts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    eligible_oa_rows = [
        row for row in oa_rows if _is_completed_oa_cost_row(row)
    ]
    contexts = [
        _oa_cost_context(row, fallback_index=index)
        for index, row in enumerate(eligible_oa_rows)
    ]
    outflows = [
        (bank_row, amount)
        for bank_row in bank_rows
        if (amount := _outflow_amount(bank_row)) is not None
    ]
    if not contexts or not outflows:
        return []
    project_names = {str(context["project_name"]) for context in contexts}
    expense_types = {str(context["expense_type"]) for context in contexts}
    exact_split = (
        len(outflows) == 1
        and len(contexts) > 1
        and (len(project_names) > 1 or len(expense_types) > 1)
        and all(context["allocation_amount"] is not None for context in contexts)
        and sum(
            (context["allocation_amount"] for context in contexts),
            start=ZERO,
        ).quantize(MONEY_QUANTUM)
        == outflows[0][1].quantize(MONEY_QUANTUM)
    )
    if exact_split:
        bank_row, _bank_amount = outflows[0]
        return [
            _cost_entry(
                group,
                bank_row=bank_row,
                context=context,
                amount=context["allocation_amount"],
                row_key_suffix=f"oa:{context['oa_id']}",
                bank_tag_contexts=bank_tag_contexts,
            )
            for context in contexts
        ]
    context = _fallback_cost_context(contexts)
    return [
        _cost_entry(
            group,
            bank_row=bank_row,
            context=context,
            amount=amount,
            row_key_suffix="full",
            bank_tag_contexts=bank_tag_contexts,
        )
        for bank_row, amount in outflows
    ]


def _oa_cost_context(
    row: dict[str, Any],
    *,
    fallback_index: int,
) -> dict[str, Any]:
    detail_fields = (
        row.get("detail_fields")
        if isinstance(row.get("detail_fields"), dict)
        else {}
    )
    project_name = (
        _clean_text(row.get("project_name"))
        or _clean_text(detail_fields.get("项目名称"))
        or UNATTRIBUTED_PROJECT_NAME
    )
    project_id = _clean_text(
        row.get("project_id") or detail_fields.get("项目编号")
    )
    expense_type = (
        _clean_text(row.get("expense_type"))
        or _clean_text(detail_fields.get("费用类型"))
        or UNCATEGORIZED_EXPENSE_TYPE
    )
    expense_content = (
        _clean_text(row.get("expense_content"))
        or _clean_text(row.get("reason"))
        or _clean_text(detail_fields.get("费用内容"))
        or expense_type
    )
    allocation_amount = _decimal(row.get("reconciliation_amount"))
    if allocation_amount is None or allocation_amount <= ZERO:
        allocation_amount = _decimal(row.get("amount"))
    if allocation_amount is not None and allocation_amount <= ZERO:
        allocation_amount = None
    return {
        "oa_id": _clean_text(row.get("id") or row.get("row_id"))
        or f"index-{fallback_index}",
        "project_name": project_name,
        "project_id": project_id,
        "expense_type": expense_type,
        "expense_content": expense_content,
        "oa_applicant": _clean_text(
            row.get("applicant") or detail_fields.get("申请人")
        )
        or "—",
        "allocation_amount": (
            allocation_amount.quantize(MONEY_QUANTUM)
            if allocation_amount is not None
            else None
        ),
    }


def _fallback_cost_context(
    contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    project_names = {str(context["project_name"]) for context in contexts}
    project_ids = {
        str(context["project_id"])
        for context in contexts
        if str(context["project_id"])
    }
    expense_types = {str(context["expense_type"]) for context in contexts}
    if len(project_names) == 1:
        project_name = next(iter(project_names))
        project_id = next(iter(project_ids)) if len(project_ids) == 1 else ""
    else:
        project_id, project_name = "", MULTI_PROJECT_NAME
    return {
        "project_name": project_name,
        "project_id": project_id,
        "expense_type": (
            next(iter(expense_types))
            if len(expense_types) == 1
            else MULTI_EXPENSE_TYPE
        ),
        "expense_content": _join_unique_text(
            context["expense_content"] for context in contexts
        )
        or UNCATEGORIZED_EXPENSE_TYPE,
        "oa_applicant": _join_unique_text(
            context["oa_applicant"] for context in contexts
        )
        or "—",
        "source_project_contexts": [
            {
                "project_id": context["project_id"],
                "project_name": context["project_name"],
            }
            for context in contexts
        ],
    }


def _cost_entry(
    group: dict[str, Any],
    *,
    bank_row: dict[str, Any],
    context: dict[str, Any],
    amount: Decimal,
    row_key_suffix: str,
    bank_tag_contexts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    transaction_id = _clean_text(
        bank_row.get("id")
        or bank_row.get("transaction_id")
        or bank_row.get("row_id")
    )
    return {
        "row_key": f"{transaction_id}:{row_key_suffix}",
        "group_id": _clean_text(group.get("group_id")),
        "transaction_id": transaction_id,
        "trade_time": _clean_text(
            bank_row.get("trade_time")
            or bank_row.get("pay_receive_time")
            or bank_row.get("date")
        ),
        "counterparty_name": _clean_text(
            bank_row.get("counterparty_name")
        ),
        "payment_account_label": _clean_text(
            bank_row.get("payment_account_label") or bank_row.get("bank_name")
        ),
        "direction": _clean_text(bank_row.get("direction")) or "支出",
        "remark": _clean_text(bank_row.get("remark")),
        "project_name": str(context["project_name"]),
        "project_id": str(context["project_id"]),
        "expense_type": str(context["expense_type"]),
        "expense_content": str(context["expense_content"]),
        "oa_applicant": str(context["oa_applicant"]),
        "amount_decimal": amount.quantize(MONEY_QUANTUM),
        **(
            {"source_project_contexts": list(context["source_project_contexts"])}
            if isinstance(context.get("source_project_contexts"), list)
            else {}
        ),
        **(
            bank_tag_contexts.get(transaction_id)
            or bank_tag_context_from_row({})
        ),
    }


def _cash_ticket_cost_entry(
    group: dict[str, Any],
    *,
    oa_rows: list[dict[str, Any]],
    bank_rows: list[dict[str, Any]],
    special_metadata: dict[str, Any],
    bank_tag_contexts: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if (
        _clean_text(special_metadata.get("special_type"))
        != CASH_TICKET_PURCHASE_MODE
    ):
        return None
    amount = _decimal(special_metadata.get("ticket_cost_amount"))
    if amount in (None, ZERO):
        return None
    bank_row = next(
        (row for row in bank_rows if _outflow_amount(row) is not None),
        None,
    )
    eligible_oa_rows = [
        row for row in oa_rows if _is_completed_oa_cost_row(row)
    ]
    if bank_row is None or not eligible_oa_rows:
        return None
    context = _fallback_cost_context(
        [
            _oa_cost_context(row, fallback_index=index)
            for index, row in enumerate(eligible_oa_rows)
        ]
    )
    transaction_id = _clean_text(
        bank_row.get("id") or bank_row.get("row_id")
    )
    return {
        "row_key": f"{transaction_id}:ticket",
        "group_id": _clean_text(group.get("group_id")),
        "transaction_id": transaction_id,
        "trade_time": _clean_text(
            bank_row.get("trade_time") or bank_row.get("pay_receive_time")
        ),
        "counterparty_name": _clean_text(
            bank_row.get("counterparty_name")
        ),
        "payment_account_label": _clean_text(
            bank_row.get("payment_account_label")
        ),
        "direction": _clean_text(bank_row.get("direction")) or "支出",
        "remark": _clean_text(bank_row.get("remark")),
        "project_name": _clean_text(special_metadata.get("project_name"))
        or str(context["project_name"]),
        "project_id": _clean_text(special_metadata.get("project_id"))
        or str(context.get("project_id") or ""),
        "expense_type": _clean_text(special_metadata.get("expense_type"))
        or str(context.get("expense_type") or "现金往来"),
        "expense_content": _clean_text(
            special_metadata.get("expense_content")
        )
        or "买票成本",
        "oa_applicant": str(context.get("oa_applicant") or "—"),
        "amount_decimal": amount.quantize(MONEY_QUANTUM),
        **(
            {"source_project_contexts": list(context["source_project_contexts"])}
            if isinstance(context.get("source_project_contexts"), list)
            else {}
        ),
        **(
            bank_tag_contexts.get(transaction_id)
            or bank_tag_context_from_row(bank_row)
        ),
    }


def _outflow_amount(bank_row: dict[str, Any]) -> Decimal | None:
    direction = str(
        bank_row.get("direction") or bank_row.get("txn_direction") or ""
    ).strip().lower()
    if direction and not any(
        token in direction for token in ("out", "支出", "付款", "debit")
    ):
        return None
    credit_amount = _decimal(bank_row.get("credit_amount"))
    if credit_amount not in (None, ZERO):
        return None
    amount = _decimal(
        bank_row.get("debit_amount") or bank_row.get("amount")
    )
    if amount in (None, ZERO):
        return None
    return abs(amount)


def _serialize_cost_entry(entry: dict[str, Any]) -> dict[str, Any]:
    trade_time = str(entry["trade_time"])
    return {
        "row_key": entry.get("row_key")
        or f"{entry['transaction_id']}:full",
        "group_id": entry.get("group_id") or "",
        "transaction_id": entry["transaction_id"],
        "month": trade_time[:7],
        "trade_time": trade_time,
        "direction": entry["direction"],
        "project_name": entry["project_name"],
        "project_id": entry.get("project_id") or "",
        "expense_type": entry["expense_type"],
        "expense_content": entry["expense_content"],
        "amount": _money(entry["amount_decimal"]),
        "counterparty_name": entry["counterparty_name"],
        "payment_account_label": entry["payment_account_label"],
        "remark": entry["remark"],
        "oa_applicant": entry["oa_applicant"],
        **bank_tag_context_from_row(entry),
    }


def _completed_project_identities(
    settings: dict[str, Any],
) -> tuple[set[str], set[str]]:
    projects = (
        settings.get("projects")
        if isinstance(settings.get("projects"), dict)
        else {}
    )
    completed_ids = {
        _clean_text(value)
        for value in list(
            projects.get("completed_project_ids")
            or settings.get("completed_project_ids")
            or []
        )
        if _clean_text(value)
    }
    completed_names: set[str] = set()
    candidates = [
        *[
            item
            for item in list(projects.get("completed") or [])
            if isinstance(item, dict)
        ],
        *[
            item
            for item in list(settings.get("manual_projects") or [])
            if isinstance(item, dict)
            and _clean_text(item.get("id")) in completed_ids
        ],
        *[
            item
            for item in list(settings.get("synced_projects") or [])
            if isinstance(item, dict)
            and _clean_text(item.get("id")) in completed_ids
        ],
    ]
    for project in candidates:
        project_id = _clean_text(project.get("id"))
        project_name = _clean_text(
            project.get("project_name") or project.get("name")
        )
        if project_id:
            completed_ids.add(project_id)
        if project_name:
            completed_names.add(project_name)
    return completed_ids, completed_names


def _is_completed_project_allocation(
    context: dict[str, Any],
    *,
    completed_project_ids: set[str],
    completed_project_names: set[str],
) -> bool:
    source_contexts = context.get("source_project_contexts")
    if isinstance(source_contexts, list) and source_contexts:
        return all(
            _is_completed_project_identity(
                item,
                completed_project_ids=completed_project_ids,
                completed_project_names=completed_project_names,
            )
            for item in source_contexts
            if isinstance(item, dict)
        )
    return _is_completed_project_identity(
        context,
        completed_project_ids=completed_project_ids,
        completed_project_names=completed_project_names,
    )


def _is_completed_project_identity(
    context: dict[str, Any],
    *,
    completed_project_ids: set[str],
    completed_project_names: set[str],
) -> bool:
    project_id = _clean_text(context.get("project_id"))
    project_name = _clean_text(context.get("project_name"))
    return bool(
        (project_id and project_id in completed_project_ids)
        or (project_name and project_name in completed_project_names)
    )


def _is_completed_oa_cost_row(row: dict[str, Any]) -> bool:
    return is_completed_workflow_status(row.get("workflow_status"))


def _project_facets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row["project_name"]
        bucket = buckets.setdefault(
            name,
            {
                "project_name": name,
                "total": ZERO,
                "transactions": set(),
                "expense_types": set(),
            },
        )
        bucket["total"] += _decimal(row["amount"]) or ZERO
        bucket["transactions"].add(row["transaction_id"])
        bucket["expense_types"].add(row["expense_type"])
    total = sum((bucket["total"] for bucket in buckets.values()), start=ZERO)
    return [
        {
            "project_name": bucket["project_name"],
            "total_amount": _money(bucket["total"]),
            "transaction_count": len(bucket["transactions"]),
            "expense_type_count": len(bucket["expense_types"]),
            "percentage_label": _percentage(bucket["total"], total),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (-item["total"], item["project_name"]),
        )
    ]


def _expense_facets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row["expense_type"]
        bucket = buckets.setdefault(
            name,
            {
                "expense_type": name,
                "total": ZERO,
                "transactions": set(),
                "projects": set(),
            },
        )
        bucket["total"] += _decimal(row["amount"]) or ZERO
        bucket["transactions"].add(row["transaction_id"])
        bucket["projects"].add(row["project_name"])
    total = sum((bucket["total"] for bucket in buckets.values()), start=ZERO)
    return [
        {
            "expense_type": bucket["expense_type"],
            "total_amount": _money(bucket["total"]),
            "transaction_count": len(bucket["transactions"]),
            "project_count": len(bucket["projects"]),
            "percentage_label": _percentage(bucket["total"], total),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (-item["total"], item["expense_type"]),
        )
    ]


def _bank_facets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = row["payment_account_label"] or "未识别账户"
        bucket = buckets.setdefault(
            label,
            {
                "payment_account_label": label,
                "total": ZERO,
                "transactions": set(),
                "projects": set(),
            },
        )
        bucket["total"] += _decimal(row["amount"]) or ZERO
        bucket["transactions"].add(row["transaction_id"])
        bucket["projects"].add(row["project_name"])
    total = sum((bucket["total"] for bucket in buckets.values()), start=ZERO)
    return [
        {
            "payment_account_label": bucket["payment_account_label"],
            "total_amount": _money(bucket["total"]),
            "transaction_count": len(bucket["transactions"]),
            "project_count": len(bucket["projects"]),
            "percentage_label": _percentage(bucket["total"], total),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (-item["total"], item["payment_account_label"]),
        )
    ]


def _bank_tag_primary_facets(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = _tag_primary(row)
        bucket = buckets.setdefault(
            label,
            {
                "primary_label": label,
                "expense_amount": ZERO,
                "income_amount": ZERO,
                "expense_transactions": set(),
                "income_transactions": set(),
                "sub_tags": set(),
            },
        )
        amount = _decimal(row["amount"]) or ZERO
        if row["direction"] == "收入":
            bucket["income_amount"] += amount
            bucket["income_transactions"].add(row["transaction_id"])
        else:
            bucket["expense_amount"] += amount
            bucket["expense_transactions"].add(row["transaction_id"])
        bucket["sub_tags"].add(_tag_sub(row))
    return [
        {
            "primary_label": bucket["primary_label"],
            "expense_amount": _money(bucket["expense_amount"]),
            "income_amount": _money(bucket["income_amount"]),
            "expense_transaction_count": len(bucket["expense_transactions"]),
            "income_transaction_count": len(bucket["income_transactions"]),
            "sub_tag_count": len(bucket["sub_tags"]),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (
                -(item["expense_amount"] + item["income_amount"]),
                item["primary_label"],
            ),
        )
    ]


def _bank_tag_sub_facets(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (_tag_primary(row), _tag_sub(row))
        bucket = buckets.setdefault(
            key,
            {
                "primary_label": key[0],
                "sub_label": key[1],
                "expense_amount": ZERO,
                "income_amount": ZERO,
                "expense_transactions": set(),
                "income_transactions": set(),
            },
        )
        amount = _decimal(row["amount"]) or ZERO
        if row["direction"] == "收入":
            bucket["income_amount"] += amount
            bucket["income_transactions"].add(row["transaction_id"])
        else:
            bucket["expense_amount"] += amount
            bucket["expense_transactions"].add(row["transaction_id"])
    return [
        {
            "primary_label": bucket["primary_label"],
            "sub_label": bucket["sub_label"],
            "expense_amount": _money(bucket["expense_amount"]),
            "income_amount": _money(bucket["income_amount"]),
            "expense_transaction_count": len(bucket["expense_transactions"]),
            "income_transaction_count": len(bucket["income_transactions"]),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (
                -(item["expense_amount"] + item["income_amount"]),
                item["sub_label"],
            ),
        )
    ]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(
        (_decimal(row.get("amount")) or ZERO for row in rows),
        start=ZERO,
    )
    expense_rows = [row for row in rows if row.get("direction") == "支出"]
    income_rows = [row for row in rows if row.get("direction") == "收入"]
    return {
        "row_count": len(rows),
        "transaction_count": len(
            {str(row["transaction_id"]) for row in rows}
        ),
        "total_amount": _money(total),
        "expense_amount": _money(
            sum(
                (_decimal(row.get("amount")) or ZERO for row in expense_rows),
                start=ZERO,
            )
        ),
        "income_amount": _money(
            sum(
                (_decimal(row.get("amount")) or ZERO for row in income_rows),
                start=ZERO,
            )
        ),
        "expense_transaction_count": len(
            {str(row["transaction_id"]) for row in expense_rows}
        ),
        "income_transaction_count": len(
            {str(row["transaction_id"]) for row in income_rows}
        ),
    }


def _aggregate_export_rows(
    rows: list[dict[str, Any]],
    *,
    row_shape: str,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        period = (
            str(row["month"])[:4]
            if row_shape == "project_year"
            else str(row["month"])
        )
        key = (
            *((period,) if row_shape != "month_summary" else ()),
            row["project_name"],
            row["expense_type"],
            row["expense_content"],
        )
        bucket = buckets.setdefault(
            key,
            {
                **(
                    {"period_label": period}
                    if row_shape != "month_summary"
                    else {}
                ),
                "project_name": row["project_name"],
                "expense_type": row["expense_type"],
                "expense_content": row["expense_content"],
                "amount_decimal": ZERO,
                "transactions": set(),
            },
        )
        bucket["amount_decimal"] += _decimal(row["amount"]) or ZERO
        bucket["transactions"].add(row["transaction_id"])
    return [
        {
            **(
                {"period_label": bucket["period_label"]}
                if "period_label" in bucket
                else {}
            ),
            "project_name": bucket["project_name"],
            "expense_type": bucket["expense_type"],
            "expense_content": bucket["expense_content"],
            "amount": _money(bucket["amount_decimal"]),
            "transaction_count": len(bucket["transactions"]),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (
                str(item.get("period_label") or ""),
                item["project_name"],
                item["expense_type"],
                item["expense_content"],
            ),
        )
    ]


def _selected_tag_codes(
    settings: dict[str, Any],
) -> set[str] | None:
    payload = AppSettingsService.cost_statistics_tag_selection_payload_from_settings(
        settings
    )
    selected = payload.get("effective_selected_tag_codes")
    if selected is None:
        return None
    return {
        _clean_text(value)
        for value in list(selected)
        if _clean_text(value)
    }


def _tag_selected(
    row: dict[str, Any],
    selected: set[str] | None,
) -> bool:
    if selected is None:
        return True
    code = (
        _clean_text(row.get("bank_tag_code"))
        or COST_STATISTICS_UNCATEGORIZED_TAG_CODE
    )
    return code in selected


def _row_in_scope(
    row: dict[str, Any],
    *,
    scope_kind: str,
    scope_value: str | None,
) -> bool:
    month = str(row.get("month") or row.get("trade_time") or "")[:7]
    if scope_kind == "all":
        return True
    if scope_kind == "year":
        return month[:4] == str(scope_value or "")
    if scope_kind == "month":
        return month == str(scope_value or "")
    return False


def _row_in_export_range(
    row: dict[str, Any],
    *,
    month: str,
    start_month: str | None,
    end_month: str | None,
    start_date: str | None,
    end_date: str | None,
) -> bool:
    row_month = str(row.get("month") or row.get("trade_time") or "")[:7]
    row_date = str(row.get("trade_time") or "")[:10]
    if month != "all" and row_month != month:
        return False
    if start_month and row_month < start_month:
        return False
    if end_month and row_month > end_month:
        return False
    if start_date and row_date < start_date:
        return False
    if end_date and row_date > end_date:
        return False
    return True


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    trade_time = str(row.get("trade_time") or "")
    return (
        trade_time[:10],
        trade_time,
        str(row.get("transaction_id") or ""),
        str(row.get("row_key") or ""),
    )


def _cursor_tuple(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return _row_sort_key(row)


def _tag_primary(row: dict[str, Any]) -> str:
    return (
        _clean_text(
            row.get("bank_tag_primary_label")
            or row.get("bank_tag_label")
        )
        or "未标记"
    )


def _tag_sub(row: dict[str, Any]) -> str:
    return (
        _clean_text(
            row.get("bank_tag_sub_label")
            or row.get("bank_tag_label")
        )
        or _tag_primary(row)
    )


def _join_unique_text(values: Any) -> str:
    return "、".join(
        sorted({_clean_text(value) for value in values if _clean_text(value)})
    )


def _percentage(value: Decimal, total: Decimal) -> str:
    if total == ZERO:
        return "0.0%"
    return f"{(value / total * Decimal('100')):.1f}%"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text in {"-", "--", "—", "——"} else text


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "", "—", "--"):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _money(value: Any) -> str:
    amount = _decimal(value) or ZERO
    return f"{amount.quantize(MONEY_QUANTUM):,.2f}"
