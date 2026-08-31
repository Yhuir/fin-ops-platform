from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from functools import cached_property
from typing import Any

from fin_ops_platform.services.app_settings_service import (
    COST_STATISTICS_UNCATEGORIZED_TAG_CODE,
    AppSettingsService,
)
from fin_ops_platform.services.cost_statistics_bank_tags import bank_tag_context_from_row
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    COMPLETED_WORKFLOW_STATUS_ALIASES,
)

ZERO = Decimal("0.00")
MONEY_QUANTUM = Decimal("0.01")
DAILY_REIMBURSEMENT_TYPE = "日常报销"
PAYMENT_APPLICATION_TYPE = "支付申请"
MISSING_OA_EXPENSE_TYPE_LABEL = "未填写 OA 费用类型"
NO_OA_EXPENSE_TYPE_LABEL = "无 OA 分类"
VIRTUAL_PROJECT_ID_PREFIX = "cost-statistics:no-oa:"
UNRESOLVED_BANK_ACCOUNT_LABEL = "银行账户未确定"


class CostStatisticsAllocationConflictError(ValueError):
    """One OA allocation unit is owned by more than one active relation."""


class CostStatisticsPolicy:
    """Pure Cost business rules over one canonical database snapshot."""

    def __init__(
        self,
        snapshot: dict[str, Any],
    ) -> None:
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
        self._manual_allocations = {
            _clean_text(case_id): dict(record)
            for case_id, record in dict(snapshot.get("manual_allocations") or {}).items()
            if _clean_text(case_id) and isinstance(record, dict)
        }
        self._active_relation_count = int(snapshot.get("active_relation_count") or 0)
        self._oa_related_bank_ids = {
            _clean_text(value)
            for value in list(snapshot.get("oa_related_bank_ids") or [])
            if _clean_text(value)
        }
        self._oa_related_bank_ids.update(
            _bank_transaction_id(row)
            for group in self._groups
            for row in list(group.get("bank_rows") or [])
            if isinstance(row, dict) and _bank_transaction_id(row)
        )
        self._available_years = [
            str(value)
            for value in list(snapshot.get("available_years") or [])
            if re.fullmatch(r"\d{4}", str(value))
        ]
        self._no_oa_settings = (
            AppSettingsService.cost_statistics_no_oa_projects_payload_from_settings(
                self._settings
            )
        )

    @cached_property
    def bank_flow_rows(self) -> list[dict[str, Any]]:
        return [_serialize_bank_row(row) for row in self._bank_rows]

    @cached_property
    def serialized_cost_rows(self) -> list[dict[str, Any]]:
        return [_serialize_cost_entry(entry) for entry in self._raw_cost_entries]

    @cached_property
    def allocation_quality(self) -> dict[str, Any]:
        return dict(self._allocation_result[1])

    @cached_property
    def manual_allocation_tasks(self) -> list[dict[str, Any]]:
        return [dict(task) for task in self._allocation_result[2]]

    @cached_property
    def pending_manual_allocation_count(self) -> int:
        return int(self.allocation_quality.get("pending_manual_allocation_count") or 0)

    @cached_property
    def stale_manual_allocation_count(self) -> int:
        return int(self.allocation_quality.get("stale_manual_allocation_count") or 0)

    @cached_property
    def _allocation_result(
        self,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
        return _cost_entries(
            self._groups,
            all_bank_rows=self._bank_rows,
            oa_related_bank_ids=self._oa_related_bank_ids,
            settings=self._settings,
            manual_allocations=self._manual_allocations,
        )

    @cached_property
    def _raw_cost_entries(self) -> list[dict[str, Any]]:
        return self._allocation_result[0]

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
        source_rows = self.bank_flow_rows if bank_flow_view else self.serialized_cost_rows
        base_rows = [
            row
            for row in source_rows
            if _row_in_scope(
                row,
                scope_kind=scope_kind,
                scope_value=scope_value,
            )
        ]
        query = _clean_text(filters.get("query")).casefold()
        if query:
            base_rows = [
                row for row in base_rows if _row_matches_query(row, query)
            ]
        base_rows.sort(key=_row_sort_key, reverse=True)
        project_name = _clean_text(filters.get("project_name"))
        expense_type = _clean_text(filters.get("expense_type"))
        bank_account_label = _clean_text(filters.get("bank_account_label"))
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
        elif view == "bank_account":
            primary_facets = _bank_account_facets(base_rows)
            account_rows = (
                [
                    row
                    for row in base_rows
                    if row["bank_account_label"] == bank_account_label
                ]
                if bank_account_label
                else []
            )
            if bank_account_label:
                secondary_facets = _project_facets(account_rows)
            if bank_account_label and project_name:
                row_matches = [
                    row
                    for row in account_rows
                    if row["project_name"] == project_name
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
                primary_rows = [
                    row for row in base_rows if _tag_primary(row) == tag_primary
                ]
                secondary_facets = _bank_tag_sub_facets(primary_rows)
            if tag_primary and tag_sub:
                row_matches = [
                    row
                    for row in base_rows
                    if _tag_primary(row) == tag_primary and _tag_sub(row) == tag_sub
                ]
        else:
            raise ValueError(
                "view must be time, project, expense_type, bank_account, or bank_tag"
            )

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
            "summary": (
                _bank_flow_summary(base_rows) if bank_flow_view else _summary(base_rows)
            ),
            "statistics": (
                self.bank_flow_statistics
                if include_statistics and bank_flow_view
                else {
                    **self.statistics,
                    **self.bank_direction_statistics,
                }
                if include_statistics
                else None
            ),
            "available_years": self._available_years or sorted(
                {
                    str(row.get("month") or "")[:4]
                    for row in source_rows
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
            "allocation_quality": None if bank_flow_view else self.allocation_quality,
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
        bank_account_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        if row_shape not in {
            "raw_bank",
            "raw_cost",
            "project_month",
            "project_year",
            "month_summary",
        }:
            raise ValueError("invalid cost statistics export row shape")
        bank_flow_export = row_shape == "raw_bank"
        source = self.bank_flow_rows if bank_flow_export else self.serialized_cost_rows
        normalized_project_names = {
            _clean_text(value) for value in project_names if _clean_text(value)
        }
        normalized_expense_types = {
            _clean_text(value) for value in expense_types if _clean_text(value)
        }
        normalized_bank_account_labels = {
            _clean_text(value)
            for value in list(bank_account_labels or [])
            if _clean_text(value)
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
            and (
                not normalized_bank_account_labels
                or row["bank_account_label"] in normalized_bank_account_labels
            )
        ]
        rows.sort(key=_row_sort_key, reverse=True)
        result_rows: list[dict[str, Any]]
        if row_shape in {"project_month", "project_year", "month_summary"}:
            result_rows = _aggregate_export_rows(rows, row_shape=row_shape)
        else:
            result_rows = rows
        summary = (
            _bank_flow_summary(rows) if bank_flow_export else _summary(rows)
        ) if include_summary else None
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
            if not bank_flow_export:
                summary.update(
                    {
                        "pending_manual_allocation_count": self.pending_manual_allocation_count,
                        "stale_manual_allocation_count": self.stale_manual_allocation_count,
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

    def bank_transaction(
        self,
        *,
        transaction_id: str,
        scope_kind: str,
        scope_value: str | None,
    ) -> dict[str, Any] | None:
        matches = [
            serialized
            for row in self._bank_rows
            if (serialized := _serialize_bank_row(row)).get("transaction_id")
            == transaction_id
            and _row_in_scope(
                serialized,
                scope_kind=scope_kind,
                scope_value=scope_value,
            )
        ]
        if not matches:
            return None
        return dict(matches[0])

    def allocation(
        self,
        *,
        allocation_id: str,
        scope_kind: str,
        scope_value: str | None,
    ) -> dict[str, Any] | None:
        match = next(
            (
                entry
                for entry in self._raw_cost_entries
                if entry.get("allocation_id") == allocation_id
                and _row_in_scope(
                    entry,
                    scope_kind=scope_kind,
                    scope_value=scope_value,
                )
            ),
            None,
        )
        if match is None:
            return None
        return {
            **_serialize_cost_entry(match),
            "oa_id": match["oa_id"],
            "oa_apply_type": match["oa_apply_type"],
            "expense_item_id": match["expense_item_id"],
            "oa_original_amount": _money(match["oa_original_amount"]),
            "oa_allocation_weight": match["oa_allocation_weight"],
            "bank_event_amount": match["bank_event_amount"],
            "payment_evidence": [dict(row) for row in match["payment_evidence"]],
            "reconciliation": dict(match["reconciliation"]),
        }

    @property
    def statistics(self) -> dict[str, int]:
        cost_rows = self.serialized_cost_rows
        return {
            "project_count": len(
                {row["project_name"] for row in cost_rows}
            ),
            "expense_type_count": len(
                {row["expense_type"] for row in cost_rows}
            ),
            "bank_account_count": len(
                {
                    row["bank_account_label"]
                    for row in cost_rows
                    if row["bank_account_label"] != UNRESOLVED_BANK_ACCOUNT_LABEL
                }
            ),
            "cost_transaction_count": len(
                {_row_identity(row) for row in cost_rows}
            ),
            "active_relation_count": self._active_relation_count,
        }

    @property
    def bank_direction_statistics(self) -> dict[str, int]:
        rows = self._bank_rows
        return {
            "transaction_count": len({_bank_transaction_id(row) for row in rows}),
            "expense_transaction_count": len(
                {
                    _bank_transaction_id(row)
                    for row in rows
                    if _bank_flow_direction(row) == "支出"
                }
            ),
            "income_transaction_count": len(
                {
                    _bank_transaction_id(row)
                    for row in rows
                    if _bank_flow_direction(row) == "收入"
                }
            ),
        }

    @property
    def bank_flow_statistics(self) -> dict[str, int]:
        rows = self.bank_flow_rows
        tagged = [
            row
            for row in rows
            if _clean_text(row.get("bank_tag_code"))
            not in {"", COST_STATISTICS_UNCATEGORIZED_TAG_CODE}
        ]
        return {
            **self.bank_direction_statistics,
            "untagged_transaction_count": len(
                {_row_identity(row) for row in rows}
                - {_row_identity(row) for row in tagged}
            ),
            "bank_tag_count": len({_tag_sub(row) for row in tagged}),
        }

    def no_oa_tag_candidates(self) -> list[dict[str, Any]]:
        candidates: dict[str, dict[str, Any]] = {}
        for bank_row in self._bank_rows:
            transaction_id = _bank_transaction_id(bank_row)
            if (
                not transaction_id
                or transaction_id in self._oa_related_bank_ids
                or _outflow_amount(bank_row) is None
            ):
                continue
            code = _bank_tag_code(bank_row)
            if code == COST_STATISTICS_UNCATEGORIZED_TAG_CODE:
                continue
            context = bank_tag_context_from_row(bank_row)
            label = _clean_text(context.get("bank_tag_label")) or "未分类"
            primary = _clean_text(context.get("bank_tag_primary_label")) or label
            sub = _clean_text(context.get("bank_tag_sub_label")) or label
            path = [
                _clean_text(value)
                for value in list(context.get("bank_tag_label_path") or [])
                if _clean_text(value)
            ]
            candidates.setdefault(
                code,
                {
                    "code": code,
                    "label": label,
                    "path": path or ([primary] if primary == sub else [primary, sub]),
                    "source": "actual_no_oa_outflow",
                    "status": "active",
                    "direction": "expense",
                    "output_primary_label": primary,
                    "output_sub_label": sub,
                },
            )
        return sorted(
            candidates.values(),
            key=lambda item: (
                str(item.get("output_primary_label") or ""),
                str(item.get("output_sub_label") or ""),
                str(item.get("code") or ""),
            ),
        )

def _cost_entries(
    groups: list[dict[str, Any]],
    *,
    all_bank_rows: list[dict[str, Any]],
    oa_related_bank_ids: set[str],
    settings: dict[str, Any],
    manual_allocations: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    manual_tasks: list[dict[str, Any]] = []
    owners: dict[str, str] = {}
    event_owners: dict[str, str] = {}
    protected_bank_ids = set(oa_related_bank_ids)
    excluded_by_reason: dict[str, int] = {}
    refund_tag_codes = _paid_wrong_refund_tag_codes(settings)
    for group in groups:
        oa_rows = [
            row
            for row in list(group.get("oa_rows") or [])
            if isinstance(row, dict)
        ]
        group_bank_rows = [
            row
            for row in list(group.get("bank_rows") or [])
            if isinstance(row, dict)
        ]
        if not group_bank_rows:
            continue
        relation_case_id = _clean_text(group.get("group_id"))
        if not relation_case_id:
            raise CostStatisticsAllocationConflictError(
                "active OA/bank relation is missing case_id"
            )
        group_bank_ids = {
            _bank_transaction_id(row)
            for row in group_bank_rows
            if _bank_transaction_id(row)
        }
        protected_bank_ids.update(group_bank_ids)
        declared_oa_ids = {
            _clean_text(value)
            for value in list(group.get("declared_oa_ids") or [])
            if _clean_text(value)
        }
        loaded_oa_ids = {
            _clean_text(row.get("id") or row.get("row_id"))
            for row in oa_rows
            if _clean_text(row.get("id") or row.get("row_id"))
        }
        if declared_oa_ids and loaded_oa_ids != declared_oa_ids:
            excluded_by_reason["incomplete_oa_members"] = (
                excluded_by_reason.get("incomplete_oa_members", 0) + 1
            )
            continue
        if not oa_rows:
            continue
        if not all(_is_completed_oa_cost_row(row) for row in oa_rows):
            excluded_by_reason["incomplete_oa_relation"] = (
                excluded_by_reason.get("incomplete_oa_relation", 0) + 1
            )
            continue
        outflows = [
            row for row in group_bank_rows if _outflow_amount(row) is not None
        ]
        contexts: list[dict[str, Any]] = []
        group_reasons: list[str] = []
        for oa_row in oa_rows:
            row_contexts, reasons = _oa_allocation_contexts(oa_row)
            contexts.extend(row_contexts)
            group_reasons.extend(reasons)
            for reason in reasons:
                excluded_by_reason[reason] = excluded_by_reason.get(reason, 0) + 1
        if group_reasons:
            continue
        if not outflows:
            if contexts:
                excluded_by_reason["relation_without_outflow"] = (
                    excluded_by_reason.get("relation_without_outflow", 0)
                    + len(contexts)
                )
            continue
        bank_account_label = _resolve_cost_bank_account_label(outflows)
        if len(contexts) == 0:
            continue
        for context in contexts:
            allocation_id = _allocation_id(context)
            existing_owner = owners.get(allocation_id)
            if existing_owner is not None and existing_owner != relation_case_id:
                raise CostStatisticsAllocationConflictError(
                    f"allocation {allocation_id} belongs to multiple active relations: "
                    f"{existing_owner}, {relation_case_id}"
                )
            owners[allocation_id] = relation_case_id
        oa_total = sum(
            (context["allocation_amount"] for context in contexts),
            start=ZERO,
        ).quantize(MONEY_QUANTUM)
        if oa_total <= ZERO:
            excluded_by_reason["invalid_oa_weight_total"] = (
                excluded_by_reason.get("invalid_oa_weight_total", 0) + 1
            )
            continue
        gross_outflow_total = sum(
            (_outflow_amount(row) or ZERO for row in outflows),
            start=ZERO,
        ).quantize(MONEY_QUANTUM)
        refunds = [
            row
            for row in group_bank_rows
            if _inflow_amount(row) is not None
            and _is_paid_wrong_refund(row, refund_tag_codes)
        ]
        wrong_payment_refund_total = sum(
            (_inflow_amount(row) or ZERO for row in refunds),
            start=ZERO,
        ).quantize(MONEY_QUANTUM)
        net_outflow_total = (
            gross_outflow_total - wrong_payment_refund_total
        ).quantize(MONEY_QUANTUM)
        if net_outflow_total < ZERO:
            raise CostStatisticsAllocationConflictError(
                f"relation {relation_case_id} has paid-wrong refunds exceeding outflows"
            )
        if net_outflow_total == ZERO:
            continue
        difference = (net_outflow_total - oa_total).quantize(MONEY_QUANTUM)
        evidence = [_payment_evidence(row) for row in [*outflows, *refunds]]
        reconciliation = {
            "relation_case_id": relation_case_id,
            "oa_total": _money(oa_total),
            "gross_outflow_total": _money(gross_outflow_total),
            "wrong_payment_refund_total": _money(wrong_payment_refund_total),
            "net_outflow_total": _money(net_outflow_total),
            "difference": _money(difference),
            "cash_payment_ratio": _ratio(net_outflow_total, oa_total),
            "status": "balanced" if difference == ZERO else "mismatch",
        }
        for bank_row in [*outflows, *refunds]:
            transaction_id = _bank_transaction_id(bank_row)
            if not transaction_id:
                continue
            existing_event_owner = event_owners.get(transaction_id)
            if existing_event_owner and existing_event_owner != relation_case_id:
                raise CostStatisticsAllocationConflictError(
                    f"bank transaction {transaction_id} belongs to multiple active OA relations: "
                    f"{existing_event_owner}, {relation_case_id}"
                )
            event_owners[transaction_id] = relation_case_id

        is_automatic = oa_total == net_outflow_total
        if not is_automatic:
            task = _manual_allocation_task(
                group=group,
                contexts=contexts,
                outflows=outflows,
                refunds=refunds,
                reconciliation=reconciliation,
                manual_record=manual_allocations.get(relation_case_id),
            )
            manual_tasks.append(task)
            if task["status"] != "allocated":
                reason = (
                    "stale_manual_allocation"
                    if task["status"] == "stale"
                    else "pending_manual_allocation"
                )
                excluded_by_reason[reason] = excluded_by_reason.get(reason, 0) + 1
                continue
            manual_amounts = {
                _clean_text(line.get("unit_id")): _required_nonnegative_money(
                    line.get("amount")
                )
                for line in list(task.get("allocations") or [])
                if isinstance(line, dict)
            }
            _append_unit_allocation_entries(
                entries,
                contexts=contexts,
                unit_amounts=manual_amounts,
                outflows=outflows,
                oa_total=oa_total,
                relation_case_id=relation_case_id,
                bank_account_label=bank_account_label,
                payment_evidence=evidence,
                reconciliation=reconciliation,
            )
            continue

        _append_unit_allocation_entries(
            entries,
            contexts=contexts,
            unit_amounts={
                _allocation_id(context): context["allocation_amount"]
                for context in contexts
            },
            outflows=outflows,
            oa_total=oa_total,
            relation_case_id=relation_case_id,
            bank_account_label=bank_account_label,
            payment_evidence=evidence,
            reconciliation=reconciliation,
        )

    no_oa_payload = AppSettingsService.cost_statistics_no_oa_projects_payload_from_settings(
        settings
    )
    project_by_tag = {
        _clean_text(code): {
            "id": _clean_text(project.get("id")),
            "display_name": _clean_text(project.get("display_name")),
        }
        for project in list(no_oa_payload.get("projects") or [])
        if isinstance(project, dict)
        and _clean_text(project.get("id"))
        and _clean_text(project.get("display_name"))
        for code in list(project.get("tag_codes") or [])
        if _clean_text(code)
    }
    if project_by_tag:
        for bank_row in all_bank_rows:
            transaction_id = _bank_transaction_id(bank_row)
            amount = _outflow_amount(bank_row)
            project = project_by_tag.get(_bank_tag_code(bank_row))
            if (
                not transaction_id
                or transaction_id in protected_bank_ids
                or amount is None
                or project is None
            ):
                continue
            event = _cost_event(
                bank_row,
                relation_case_id="",
                amount=amount,
                source_kind="no_oa",
                project_name=project["display_name"],
                project_id=project["id"],
            )
            entries.append(
                _no_oa_entry(
                    event,
                    project_name=project["display_name"],
                    project_id=project["id"],
                )
            )
    pending_count = sum(1 for task in manual_tasks if task.get("status") == "pending")
    stale_count = sum(1 for task in manual_tasks if task.get("status") == "stale")
    return (
        sorted(entries, key=_row_sort_key, reverse=True),
        {
            "excluded_allocation_count": sum(excluded_by_reason.values()),
            "excluded_by_reason": [
                {"reason": reason, "count": count}
                for reason, count in sorted(excluded_by_reason.items())
            ],
            "pending_manual_allocation_count": pending_count,
            "stale_manual_allocation_count": stale_count,
        },
        sorted(manual_tasks, key=lambda task: str(task.get("relation_case_id") or "")),
    )


def _cost_event(
    bank_row: dict[str, Any],
    *,
    relation_case_id: str,
    amount: Decimal,
    source_kind: str,
    project_name: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    return {
        **dict(bank_row),
        "group_id": relation_case_id,
        "relation_case_id": relation_case_id,
        "source_kind": source_kind,
        "cost_amount_decimal": amount.quantize(MONEY_QUANTUM),
        "project_name": project_name,
        "project_id": (
            f"{VIRTUAL_PROJECT_ID_PREFIX}{project_id}"
            if source_kind == "no_oa"
            else ""
        ),
        "expense_type": NO_OA_EXPENSE_TYPE_LABEL if source_kind == "no_oa" else "",
    }


def _no_oa_entry(
    event: dict[str, Any],
    *,
    project_name: str,
    project_id: str,
) -> dict[str, Any]:
    transaction_id = _bank_transaction_id(event)
    occurred_at = _clean_text(
        event.get("trade_time") or event.get("pay_receive_time") or event.get("txn_date")
    )
    return {
        **dict(event),
        "row_key": transaction_id,
        "entry_id": transaction_id,
        "row_kind": "bank_transaction",
        "allocation_id": "",
        "transaction_id": transaction_id,
        "group_id": "",
        "relation_case_id": "",
        "oa_id": "",
        "oa_apply_type": "",
        "expense_item_id": "",
        "oa_completed_at": "",
        "occurred_at": occurred_at,
        "direction": "支出",
        "project_name": project_name,
        "project_id": f"{VIRTUAL_PROJECT_ID_PREFIX}{project_id}",
        "expense_type": NO_OA_EXPENSE_TYPE_LABEL,
        "expense_content": _clean_text(event.get("summary") or event.get("remark")) or "—",
        "oa_applicant": "",
        "amount_decimal": _decimal(event.get("cost_amount_decimal")) or ZERO,
        "bank_account_label": (
            _clean_text(event.get("payment_account_label"))
            or UNRESOLVED_BANK_ACCOUNT_LABEL
        ),
        "payment_evidence": [],
        "reconciliation": {},
    }


def _append_unit_allocation_entries(
    entries: list[dict[str, Any]],
    *,
    contexts: list[dict[str, Any]],
    unit_amounts: dict[str, Decimal],
    outflows: list[dict[str, Any]],
    oa_total: Decimal,
    relation_case_id: str,
    bank_account_label: str,
    payment_evidence: list[dict[str, Any]],
    reconciliation: dict[str, Any],
) -> None:
    context_by_unit_id = {
        _allocation_id(context): context for context in contexts
    }
    if set(unit_amounts) != set(context_by_unit_id):
        raise CostStatisticsAllocationConflictError(
            f"manual allocation {relation_case_id} does not match current units"
        )
    anchor_outflow = max(
        outflows,
        key=lambda row: (
            _serialize_bank_row(row)["trade_time"],
            _bank_transaction_id(row),
        ),
    )
    for unit_id, context in context_by_unit_id.items():
        unit_amount = _required_nonnegative_money(unit_amounts[unit_id])
        if unit_amount == ZERO:
            continue
        entries.append(
            _allocation_entry(
                context,
                bank_row=anchor_outflow,
                allocated_amount=unit_amount,
                oa_total=oa_total,
                relation_case_id=relation_case_id,
                bank_account_label=bank_account_label,
                payment_evidence=payment_evidence,
                reconciliation=reconciliation,
            )
        )


def _manual_allocation_task(
    *,
    group: dict[str, Any],
    contexts: list[dict[str, Any]],
    outflows: list[dict[str, Any]],
    refunds: list[dict[str, Any]],
    reconciliation: dict[str, Any],
    manual_record: dict[str, Any] | None,
) -> dict[str, Any]:
    relation_case_id = _clean_text(group.get("group_id"))
    relation_version = int(group.get("relation_version") or 1)
    units = [
        {
            "unit_id": _allocation_id(context),
            "oa_id": context["oa_id"],
            "expense_item_id": context["expense_item_id"],
            "project_id": context["project_id"],
            "project_name": context["project_name"],
            "expense_type": context["expense_type"],
            "expense_content": context["expense_content"],
            "oa_applicant": context["oa_applicant"],
            "oa_apply_type": context["oa_apply_type"],
            "oa_original_amount": _money(context["allocation_amount"]),
        }
        for context in contexts
    ]
    bank_events = [
        _manual_allocation_bank_event(row, event_kind="outflow") for row in outflows
    ]
    bank_events.extend(
        _manual_allocation_bank_event(row, event_kind="wrong_payment_refund")
        for row in refunds
    )
    bank_events = sorted(
        bank_events,
        key=lambda event: (
            str(event["event_kind"]),
            str(event["transaction_id"]),
        ),
    )
    source_fingerprint = _manual_allocation_source_fingerprint(
        group=group,
        relation_case_id=relation_case_id,
        relation_version=relation_version,
        units=units,
        outflows=outflows,
        refunds=refunds,
        reconciliation=reconciliation,
    )
    task: dict[str, Any] = {
        "relation_case_id": relation_case_id,
        "relation_version": relation_version,
        "source_fingerprint": source_fingerprint,
        "status": "pending",
        "oa_total": reconciliation["oa_total"],
        "gross_outflow_total": reconciliation["gross_outflow_total"],
        "wrong_payment_refund_total": reconciliation[
            "wrong_payment_refund_total"
        ],
        "net_outflow_total": reconciliation["net_outflow_total"],
        "difference": reconciliation["difference"],
        "units": units,
        "bank_events": bank_events,
        "allocations": [],
        "non_cost_amount": "0.00",
        "non_cost_reason": "",
        "version": 0,
        "updated_by": "",
        "updated_at": "",
    }
    if manual_record is None:
        return task
    task.update(
        {
            "version": int(manual_record.get("version") or 0),
            "updated_by": _clean_text(manual_record.get("updated_by")),
            "updated_at": _clean_text(manual_record.get("updated_at")),
            "non_cost_amount": _money(
                _required_nonnegative_money(
                    manual_record.get("non_cost_amount") or "0.00"
                )
            ),
            "non_cost_reason": _clean_text(manual_record.get("non_cost_reason")),
        }
    )
    if _clean_text(manual_record.get("source_fingerprint")) != source_fingerprint:
        task["status"] = "stale"
        return task
    raw_allocations = [
        dict(line)
        for line in list(manual_record.get("allocations") or [])
        if isinstance(line, dict)
    ]
    expected_unit_ids = [str(unit["unit_id"]) for unit in units]
    allocations_by_unit: dict[str, Decimal] = {}
    for line in raw_allocations:
        unit_id = _clean_text(line.get("unit_id"))
        if unit_id in allocations_by_unit:
            raise CostStatisticsAllocationConflictError(
                f"manual allocation {relation_case_id} contains duplicate units"
            )
        allocations_by_unit[unit_id] = _required_nonnegative_money(
            line.get("amount")
        )
    if set(allocations_by_unit) != set(expected_unit_ids):
        raise CostStatisticsAllocationConflictError(
            f"manual allocation {relation_case_id} does not match current units"
        )
    ordered_allocations = [
        {
            "unit_id": unit_id,
            "amount": _money(allocations_by_unit[unit_id]),
        }
        for unit_id in expected_unit_ids
    ]
    allocated_total = sum(allocations_by_unit.values(), start=ZERO).quantize(
        MONEY_QUANTUM
    )
    non_cost_amount = _required_nonnegative_money(task["non_cost_amount"])
    net_outflow_total = _required_nonnegative_money(task["net_outflow_total"])
    if allocated_total + non_cost_amount != net_outflow_total:
        raise CostStatisticsAllocationConflictError(
            f"manual allocation {relation_case_id} does not close net outflow"
        )
    if (non_cost_amount > ZERO) != bool(task["non_cost_reason"]):
        raise CostStatisticsAllocationConflictError(
            f"manual allocation {relation_case_id} has invalid non-cost reason"
        )
    task["status"] = "allocated"
    task["allocations"] = ordered_allocations
    return task


def _manual_allocation_bank_event(
    row: dict[str, Any],
    *,
    event_kind: str,
) -> dict[str, Any]:
    transaction_id = _bank_transaction_id(row)
    if not transaction_id:
        raise CostStatisticsAllocationConflictError(
            "manual allocation bank event is missing transaction id"
        )
    amount = (
        _outflow_amount(row)
        if event_kind == "outflow"
        else _inflow_amount(row)
    )
    if amount is None or amount <= ZERO:
        raise CostStatisticsAllocationConflictError(
            f"manual allocation bank event {transaction_id} has an invalid amount"
        )
    serialized = _serialize_bank_row(row)
    tag_path = [
        _clean_text(value)
        for value in list(serialized.get("bank_tag_label_path") or [])
        if _clean_text(value) and _clean_text(value) != "未标记"
    ]
    return {
        "transaction_id": transaction_id,
        "event_kind": event_kind,
        "amount": _money(amount),
        "trade_time": serialized["trade_time"],
        "counterparty_name": serialized["counterparty_name"],
        "tags": list(dict.fromkeys(tag_path)),
    }


def _manual_allocation_source_fingerprint(
    *,
    group: dict[str, Any],
    relation_case_id: str,
    relation_version: int,
    units: list[dict[str, Any]],
    outflows: list[dict[str, Any]],
    refunds: list[dict[str, Any]],
    reconciliation: dict[str, Any],
) -> str:
    """Hash canonical relation facts without coupling the hash to the UI DTO.

    This persisted identity contract intentionally remains byte-for-byte stable
    across the 0162 source-matrix removal.  Existing valid decisions therefore
    stay valid after their allocation rows are reduced to one amount per OA
    unit, while any member, unit, bank event, amount, or relation-version change
    still invalidates the decision.
    """
    fingerprint_units = [
        {
            key: value
            for key, value in unit.items()
            if key != "oa_apply_type"
        }
        for unit in units
    ]
    fingerprint_sources = [
        _manual_allocation_fingerprint_bank_source(row, source_kind="outflow")
        for row in outflows
    ]
    fingerprint_sources.extend(
        _manual_allocation_fingerprint_bank_source(
            row,
            source_kind="paid_wrong_refund",
        )
        for row in refunds
    )
    payload = {
        "relation_case_id": relation_case_id,
        "relation_version": relation_version,
        "members": sorted(
            zip(
                [str(value) for value in list(group.get("row_types") or [])],
                [str(value) for value in list(group.get("row_ids") or [])],
                strict=False,
            )
        ),
        "units": sorted(
            fingerprint_units,
            key=lambda unit: str(unit["unit_id"]),
        ),
        "sources": sorted(
            fingerprint_sources,
            key=lambda source: (
                str(source["source_kind"]),
                str(source["source_id"]),
            ),
        ),
        "reconciliation": {
            "relation_case_id": relation_case_id,
            "oa_allocation_total": reconciliation["oa_total"],
            "bank_outflow_total": reconciliation["gross_outflow_total"],
            "paid_wrong_refund_total": reconciliation[
                "wrong_payment_refund_total"
            ],
            "net_cash_cost": reconciliation["net_outflow_total"],
            "difference": reconciliation["difference"],
            "cash_payment_ratio": reconciliation["cash_payment_ratio"],
            "status": reconciliation["status"],
        },
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _manual_allocation_fingerprint_bank_source(
    row: dict[str, Any],
    *,
    source_kind: str,
) -> dict[str, Any]:
    source_id = _bank_transaction_id(row)
    if not source_id:
        raise CostStatisticsAllocationConflictError(
            "manual allocation bank event is missing transaction id"
        )
    amount = (
        _outflow_amount(row)
        if source_kind == "outflow"
        else _inflow_amount(row)
    )
    if amount is None or amount <= ZERO:
        raise CostStatisticsAllocationConflictError(
            f"manual allocation bank event {source_id} has an invalid amount"
        )
    serialized = _serialize_bank_row(row)
    return {
        "source_id": source_id,
        "source_kind": source_kind,
        "amount": _money(amount),
        "trade_time": serialized["trade_time"],
        "counterparty_name": serialized["counterparty_name"],
        "payment_account_label": serialized["payment_account_label"],
        "remark": serialized["remark"],
    }


def _required_nonnegative_money(value: Any) -> Decimal:
    amount = _decimal(value)
    if amount is None or amount < ZERO or amount != amount.quantize(MONEY_QUANTUM):
        raise CostStatisticsAllocationConflictError(
            "manual allocation amounts must be nonnegative two-decimal values"
        )
    return amount.quantize(MONEY_QUANTUM)


def _paid_wrong_refund_tag_codes(settings: dict[str, Any]) -> set[str]:
    tag_dictionary = (
        settings.get("bank_transaction_tags")
        if isinstance(settings.get("bank_transaction_tags"), dict)
        else {}
    )
    return {
        _clean_text(tag.get("code"))
        for tag in list(tag_dictionary.get("definitions") or [])
        if isinstance(tag, dict)
        and "付错退款"
        in {
            _clean_text(tag.get("label")),
            _clean_text(tag.get("output_primary_label")),
            _clean_text(tag.get("output_sub_label")),
            *{
                _clean_text(value)
                for value in list(tag.get("path") or [])
                if _clean_text(value)
            },
        }
        and _clean_text(tag.get("code"))
    }


def _is_paid_wrong_refund(
    row: dict[str, Any],
    configured_codes: set[str],
) -> bool:
    if _bank_tag_code(row) in configured_codes:
        return True
    context = bank_tag_context_from_row(row)
    return "付错退款" in {
        _clean_text(context.get("bank_tag_label")),
        _clean_text(context.get("bank_tag_primary_label")),
        _clean_text(context.get("bank_tag_sub_label")),
        *{
            _clean_text(value)
            for value in list(context.get("bank_tag_label_path") or [])
            if _clean_text(value)
        },
    }


def _bank_transaction_id(row: dict[str, Any]) -> str:
    return _clean_text(row.get("id") or row.get("transaction_id") or row.get("row_id"))


def _bank_tag_code(row: dict[str, Any]) -> str:
    return _clean_text(row.get("bank_tag_code")) or COST_STATISTICS_UNCATEGORIZED_TAG_CODE


def _ratio(numerator: Decimal, denominator: Decimal) -> str:
    if denominator <= ZERO:
        return "0.00%"
    return f"{(numerator / denominator * Decimal('100')).quantize(Decimal('0.01'))}%"


def _serialize_bank_row(row: dict[str, Any]) -> dict[str, Any]:
    transaction_id = _clean_text(
        row.get("id") or row.get("transaction_id") or row.get("row_id")
    )
    amount = _decimal(row.get("cost_amount_decimal"))
    if amount is None:
        amount = abs(_decimal(row.get("amount")) or ZERO)
    direction = _bank_flow_direction(row)
    trade_time = _clean_text(
        row.get("trade_time")
        or row.get("pay_receive_time")
        or row.get("txn_date")
    )
    return {
        "entry_id": transaction_id,
        "row_kind": "bank_transaction",
        "row_key": transaction_id,
        "group_id": _clean_text(row.get("group_id")),
        "transaction_id": transaction_id,
        "month": trade_time[:7],
        "occurred_at": trade_time,
        "trade_time": trade_time,
        "direction": direction,
        "project_name": _clean_text(row.get("project_name")),
        "project_id": _clean_text(row.get("project_id")),
        "expense_type": _clean_text(row.get("expense_type")),
        "expense_content": _clean_text(
            row.get("summary") or row.get("remark")
        )
        or "—",
        "amount": _money(amount),
        "counterparty_name": _clean_text(
            row.get("counterparty_name")
            or row.get("counterparty_name_raw")
        ),
        "payment_account_label": _clean_text(
            row.get("payment_account_label")
        ),
        "remark": _clean_text(row.get("remark")),
        "oa_applicant": "",
        **bank_tag_context_from_row(row),
    }


def _bank_flow_direction(row: dict[str, Any]) -> str:
    direction = str(row.get("direction") or "").strip()
    if direction in {"收入", "支出"}:
        return direction
    return (
        "收入"
        if str(row.get("txn_direction") or "").strip().lower() == "inflow"
        else "支出"
    )


def _resolve_cost_bank_account_label(outflows: list[dict[str, Any]]) -> str:
    labels = {
        _clean_text(_serialize_bank_row(row).get("payment_account_label"))
        for row in outflows
    }
    labels.discard("")
    if len(labels) == 1:
        return next(iter(labels))
    return UNRESOLVED_BANK_ACCOUNT_LABEL


def _oa_allocation_contexts(
    row: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not _is_completed_oa_cost_row(row):
        return [], ["ineligible_oa"]
    apply_type = _clean_text(row.get("apply_type"))
    parent, parent_reason = _oa_cost_context(row)
    if apply_type == PAYMENT_APPLICATION_TYPE:
        return ([parent], []) if parent is not None else ([], [parent_reason])
    if apply_type != DAILY_REIMBURSEMENT_TYPE:
        return [], ["unsupported_oa_type"]

    raw_items = row.get("expense_items")
    if not isinstance(raw_items, list) or not raw_items:
        return [], ["daily_reimbursement_without_items"]

    contexts: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    reasons: list[str] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            reasons.append("invalid_expense_item")
            continue
        context, reason = _oa_expense_item_cost_context(row, raw_item)
        if context is None:
            reasons.append(reason)
            continue
        item_id = context["expense_item_id"]
        if item_id in seen_item_ids:
            raise CostStatisticsAllocationConflictError(
                f"duplicate expense item {item_id} in OA {context['oa_id']}"
            )
        seen_item_ids.add(item_id)
        contexts.append(context)
    return contexts, reasons


def _oa_cost_context(
    row: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    detail_fields = (
        row.get("detail_fields")
        if isinstance(row.get("detail_fields"), dict)
        else {}
    )
    project_name = (
        _clean_text(row.get("project_name"))
        or _clean_text(detail_fields.get("项目名称"))
        or ""
    )
    if project_name in {"--", "—", "多项目", "多个项目"}:
        project_name = ""
    project_id = _clean_text(
        row.get("project_id") or detail_fields.get("项目编号")
    )
    expense_type = (
        _clean_text(row.get("expense_type"))
        or _clean_text(detail_fields.get("费用类型"))
        or ""
    )
    if expense_type in {"--", "—", "多费用类型"}:
        expense_type = ""
    expense_content = (
        _clean_text(row.get("expense_content"))
        or _clean_text(row.get("reason"))
        or _clean_text(detail_fields.get("费用内容"))
        or expense_type
    )
    allocation_amount = _positive_money(row.get("amount"))
    oa_id = _clean_text(row.get("id") or row.get("row_id"))
    completed_at = _clean_text(row.get("completed_at"))
    if not oa_id:
        return None, "missing_oa_id"
    if not completed_at:
        return None, "missing_oa_completed_at"
    if not project_name:
        return None, "missing_project"
    if allocation_amount is None:
        return None, "invalid_oa_amount"
    return {
        "oa_id": oa_id,
        "oa_apply_type": PAYMENT_APPLICATION_TYPE,
        "oa_completed_at": completed_at,
        "source_kind": "oa",
        "expense_item_id": "",
        "project_name": project_name,
        "project_id": project_id,
        "expense_type": expense_type or MISSING_OA_EXPENSE_TYPE_LABEL,
        "expense_content": expense_content,
        "oa_applicant": _clean_text(
            row.get("applicant") or detail_fields.get("申请人")
        ),
        "counterparty_name": _clean_text(row.get("counterparty_name")),
        "allocation_amount": allocation_amount,
    }, ""


def _oa_expense_item_cost_context(
    row: dict[str, Any],
    item: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    amount = _positive_money(
        _first_present(
            item.get("settlement_amount"),
            item.get("amount"),
            item.get("total_with_tax"),
        )
    )
    expense_type = (
        _clean_text(item.get("expense_type"))
        or ""
    )
    if expense_type in {"--", "—", "多费用类型"}:
        expense_type = ""
    project_name = (
        _clean_text(item.get("project_name"))
        or ""
    )
    if project_name in {"--", "—", "多项目", "多个项目"}:
        project_name = ""
    oa_id = _clean_text(row.get("id") or row.get("row_id"))
    completed_at = _clean_text(row.get("completed_at"))
    item_id = _clean_text(
        item.get("expense_item_id") or item.get("row_id") or item.get("item_id")
    )
    if not oa_id or not completed_at:
        return None, "missing_oa_identity"
    if not item_id:
        return None, "missing_expense_item_id"
    if not project_name:
        return None, "missing_project"
    if amount is None:
        return None, "invalid_expense_item_amount"
    detail_fields = row.get("detail_fields") if isinstance(row.get("detail_fields"), dict) else {}
    return {
        "oa_id": oa_id,
        "oa_apply_type": DAILY_REIMBURSEMENT_TYPE,
        "oa_completed_at": completed_at,
        "source_kind": "expense_item",
        "expense_item_id": item_id,
        "project_name": project_name,
        "project_id": _clean_text(item.get("project_id")),
        "expense_type": expense_type or MISSING_OA_EXPENSE_TYPE_LABEL,
        "expense_content": (
            _clean_text(item.get("expense_content"))
            or _clean_text(item.get("reason"))
            or expense_type
        ),
        "oa_applicant": _clean_text(
            row.get("applicant") or detail_fields.get("申请人")
        ),
        "counterparty_name": _clean_text(row.get("counterparty_name")),
        "allocation_amount": amount,
    }, ""


def _allocation_id(context: dict[str, Any]) -> str:
    if context["source_kind"] == "expense_item":
        return f"oa:{context['oa_id']}:item:{context['expense_item_id']}"
    return f"oa:{context['oa_id']}"


def _allocation_entry(
    context: dict[str, Any],
    *,
    bank_row: dict[str, Any],
    allocated_amount: Decimal,
    oa_total: Decimal,
    relation_case_id: str,
    bank_account_label: str,
    payment_evidence: list[dict[str, Any]],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    unit_id = _allocation_id(context)
    allocation_id = f"relation:{relation_case_id}:unit:{unit_id}"
    occurred_at = _serialize_bank_row(bank_row)["trade_time"]
    return {
        "row_key": allocation_id,
        "entry_id": allocation_id,
        "row_kind": "oa_allocation",
        "allocation_id": allocation_id,
        "group_id": relation_case_id,
        "relation_case_id": relation_case_id,
        "oa_id": context["oa_id"],
        "oa_apply_type": context["oa_apply_type"],
        "expense_item_id": context["expense_item_id"],
        "oa_completed_at": context["oa_completed_at"],
        "transaction_id": "",
        "occurred_at": occurred_at,
        "counterparty_name": context["counterparty_name"],
        "payment_account_label": "",
        "bank_account_label": bank_account_label,
        "direction": "支出",
        "remark": "",
        "project_name": str(context["project_name"]),
        "project_id": str(context["project_id"]),
        "expense_type": str(context["expense_type"]),
        "expense_content": str(context["expense_content"]),
        "oa_applicant": str(context["oa_applicant"]),
        "amount_decimal": allocated_amount,
        "oa_original_amount": context["allocation_amount"],
        "oa_allocation_weight": _ratio(context["allocation_amount"], oa_total),
        "bank_event_amount": "",
        "payment_evidence": payment_evidence,
        "reconciliation": reconciliation,
    }


def _payment_evidence(bank_row: dict[str, Any]) -> dict[str, Any]:
    row = _serialize_bank_row(bank_row)
    return {
        "transaction_id": row["transaction_id"],
        "trade_time": row["trade_time"],
        "amount": row["amount"],
        "direction": row["direction"],
        "counterparty_name": row["counterparty_name"],
        "payment_account_label": row["payment_account_label"],
        "remark": row["remark"],
        "bank_tag_code": row.get("bank_tag_code") or "",
        "bank_tag_label": row.get("bank_tag_label") or "",
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


def _inflow_amount(bank_row: dict[str, Any]) -> Decimal | None:
    direction = str(
        bank_row.get("direction") or bank_row.get("txn_direction") or ""
    ).strip().lower()
    if direction and not any(
        token in direction for token in ("in", "收入", "收款", "credit")
    ):
        return None
    debit_amount = _decimal(bank_row.get("debit_amount"))
    if debit_amount not in (None, ZERO):
        return None
    amount = _decimal(bank_row.get("credit_amount") or bank_row.get("amount"))
    if amount in (None, ZERO):
        return None
    return abs(amount)


def _serialize_cost_entry(entry: dict[str, Any]) -> dict[str, Any]:
    occurred_at = str(entry["occurred_at"])
    return {
        "entry_id": entry["entry_id"],
        "row_kind": entry["row_kind"],
        "row_key": entry["row_key"],
        "allocation_id": entry.get("allocation_id") or "",
        "transaction_id": entry.get("transaction_id") or "",
        "group_id": entry.get("group_id") or "",
        "relation_case_id": entry.get("relation_case_id") or "",
        "oa_id": entry.get("oa_id") or "",
        "oa_apply_type": entry.get("oa_apply_type") or "",
        "expense_item_id": entry.get("expense_item_id") or "",
        "month": occurred_at[:7],
        "occurred_at": occurred_at,
        "oa_completed_at": entry.get("oa_completed_at") or "",
        "direction": entry["direction"],
        "project_name": entry["project_name"],
        "project_id": entry.get("project_id") or "",
        "expense_type": entry["expense_type"],
        "expense_content": entry["expense_content"],
        "amount": _money(entry["amount_decimal"]),
        "counterparty_name": entry["counterparty_name"],
        "payment_account_label": entry["payment_account_label"],
        "bank_account_label": entry["bank_account_label"],
        "remark": entry["remark"],
        "oa_applicant": entry["oa_applicant"],
        "linked_bank_transaction_count": len(entry.get("payment_evidence") or []),
        "reconciliation_status": str((entry.get("reconciliation") or {}).get("status") or ""),
    }


def _positive_money(value: Any) -> Decimal | None:
    amount = _decimal(value)
    if amount is None or amount <= ZERO:
        return None
    return amount.quantize(MONEY_QUANTUM)


def _first_present(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _is_completed_oa_cost_row(row: dict[str, Any]) -> bool:
    return bool(
        _clean_text(row.get("completed_at"))
        and _clean_text(row.get("apply_type"))
        in {PAYMENT_APPLICATION_TYPE, DAILY_REIMBURSEMENT_TYPE}
        and _clean_text(row.get("workflow_status"))
        in COMPLETED_WORKFLOW_STATUS_ALIASES
    )


def _project_facets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row["project_name"]
        bucket = buckets.setdefault(
            name,
            {
                "project_name": name,
                "total": ZERO,
                "expense_types": set(),
            },
        )
        bucket["total"] += _decimal(row["amount"]) or ZERO
        bucket["expense_types"].add(row["expense_type"])
    return [
        {
            "project_name": bucket["project_name"],
            "total_amount": _money(bucket["total"]),
            "expense_type_count": len(bucket["expense_types"]),
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
        bucket["transactions"].add(_row_identity(row))
        bucket["projects"].add(row["project_name"])
    return [
        {
            "expense_type": bucket["expense_type"],
            "total_amount": _money(bucket["total"]),
            "transaction_count": len(bucket["transactions"]),
            "project_count": len(bucket["projects"]),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (-item["total"], item["expense_type"]),
        )
    ]


def _bank_account_facets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = row["bank_account_label"]
        bucket = buckets.setdefault(
            label,
            {
                "bank_account_label": label,
                "total": ZERO,
                "projects": set(),
            },
        )
        bucket["total"] += _decimal(row["amount"]) or ZERO
        bucket["projects"].add(row["project_name"])
    return [
        {
            "bank_account_label": bucket["bank_account_label"],
            "total_amount": _money(bucket["total"]),
            "project_count": len(bucket["projects"]),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (
                item["bank_account_label"] == UNRESOLVED_BANK_ACCOUNT_LABEL,
                -item["total"],
                item["bank_account_label"],
            ),
        )
    ]


def _bank_tag_primary_facets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        amount = abs(_decimal(row.get("amount")) or ZERO)
        if row.get("direction") == "收入":
            bucket["income_amount"] += amount
            bucket["income_transactions"].add(_row_identity(row))
        else:
            bucket["expense_amount"] += amount
            bucket["expense_transactions"].add(_row_identity(row))
        bucket["sub_tags"].add(_tag_sub(row))
    return [
        {
            "primary_label": bucket["primary_label"],
            "expense_amount": _money(bucket["expense_amount"]),
            "income_amount": _money(bucket["income_amount"]),
            "net_outflow_amount": _money(
                bucket["expense_amount"] - bucket["income_amount"]
            ),
            "expense_transaction_count": len(bucket["expense_transactions"]),
            "income_transaction_count": len(bucket["income_transactions"]),
            "transaction_count": len(
                bucket["expense_transactions"] | bucket["income_transactions"]
            ),
            "sub_tag_count": len(bucket["sub_tags"]),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: _bank_tag_facet_sort_key(
                item,
                label_key="primary_label",
            ),
        )
    ]


def _bank_tag_sub_facets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        amount = abs(_decimal(row.get("amount")) or ZERO)
        if row.get("direction") == "收入":
            bucket["income_amount"] += amount
            bucket["income_transactions"].add(_row_identity(row))
        else:
            bucket["expense_amount"] += amount
            bucket["expense_transactions"].add(_row_identity(row))
    return [
        {
            "primary_label": bucket["primary_label"],
            "sub_label": bucket["sub_label"],
            "expense_amount": _money(bucket["expense_amount"]),
            "income_amount": _money(bucket["income_amount"]),
            "net_outflow_amount": _money(
                bucket["expense_amount"] - bucket["income_amount"]
            ),
            "expense_transaction_count": len(bucket["expense_transactions"]),
            "income_transaction_count": len(bucket["income_transactions"]),
            "transaction_count": len(
                bucket["expense_transactions"] | bucket["income_transactions"]
            ),
        }
        for bucket in sorted(
            buckets.values(),
            key=lambda item: _bank_tag_facet_sort_key(item, label_key="sub_label"),
        )
    ]


def _bank_tag_facet_sort_key(
    item: dict[str, Any],
    *,
    label_key: str,
) -> tuple[int, Decimal, int, str]:
    expense_amount = item["expense_amount"]
    income_amount = item["income_amount"]
    if expense_amount > ZERO and income_amount == ZERO:
        direction_rank = 0
    elif expense_amount > ZERO and income_amount > ZERO:
        direction_rank = 1
    elif income_amount > ZERO:
        direction_rank = 2
    else:
        direction_rank = 3
    transaction_count = len(item["expense_transactions"]) + len(
        item["income_transactions"]
    )
    return (
        direction_rank,
        -(expense_amount + income_amount),
        -transaction_count,
        str(item[label_key]),
    )


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(
        (abs(_decimal(row.get("amount")) or ZERO) for row in rows),
        start=ZERO,
    )
    return {
        "row_count": len(rows),
        "transaction_count": len(
            {_row_identity(row) for row in rows}
        ),
        "total_amount": _money(total),
    }


def _bank_flow_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expense_rows = [row for row in rows if row.get("direction") == "支出"]
    income_rows = [row for row in rows if row.get("direction") == "收入"]
    expense_total = sum(
        (abs(_decimal(row.get("amount")) or ZERO) for row in expense_rows),
        start=ZERO,
    )
    income_total = sum(
        (abs(_decimal(row.get("amount")) or ZERO) for row in income_rows),
        start=ZERO,
    )
    return {
        "row_count": len(rows),
        "transaction_count": len({_row_identity(row) for row in rows}),
        "total_amount": _money(expense_total - income_total),
        "expense_amount": _money(expense_total),
        "income_amount": _money(income_total),
        "expense_transaction_count": len(
            {_row_identity(row) for row in expense_rows}
        ),
        "income_transaction_count": len(
            {_row_identity(row) for row in income_rows}
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
        bucket["transactions"].add(_row_identity(row))
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


def _row_in_scope(
    row: dict[str, Any],
    *,
    scope_kind: str,
    scope_value: str | None,
) -> bool:
    month = str(
        row.get("month") or row.get("occurred_at") or row.get("trade_time") or ""
    )[:7]
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
    occurred_at = str(row.get("occurred_at") or row.get("trade_time") or "")
    row_month = str(row.get("month") or occurred_at)[:7]
    row_date = occurred_at[:10]
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
    trade_time = str(row.get("occurred_at") or row.get("trade_time") or "")
    return (
        trade_time[:10],
        trade_time,
        _row_identity(row),
        str(row.get("row_key") or ""),
    )


def _cursor_tuple(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return _row_sort_key(row)


def _tag_primary(row: dict[str, Any]) -> str:
    return (
        _clean_text(row.get("bank_tag_primary_label") or row.get("bank_tag_label"))
        or "未标记"
    )


def _tag_sub(row: dict[str, Any]) -> str:
    return (
        _clean_text(row.get("bank_tag_sub_label") or row.get("bank_tag_label"))
        or _tag_primary(row)
    )


def _row_identity(row: dict[str, Any]) -> str:
    return _clean_text(
        row.get("entry_id")
        or row.get("allocation_id")
        or row.get("transaction_id")
        or row.get("row_key")
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text in {"-", "--", "—", "——"} else text


def _row_matches_query(row: dict[str, Any], query: str) -> bool:
    searchable_fields = (
        "occurred_at",
        "trade_time",
        "allocation_id",
        "oa_id",
        "oa_apply_type",
        "counterparty_name",
        "payment_account_label",
        "bank_account_label",
        "direction",
        "amount",
        "expense_content",
        "remark",
        "project_name",
        "expense_type",
        "oa_applicant",
        "bank_tag_primary_label",
        "bank_tag_sub_label",
        "bank_tag_label",
    )
    return query in "\n".join(
        _clean_text(row.get(field)) for field in searchable_fields
    ).casefold()


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "", "—", "--"):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _money(value: Any) -> str:
    amount = _decimal(value) or ZERO
    return f"{amount.quantize(MONEY_QUANTUM):.2f}"
