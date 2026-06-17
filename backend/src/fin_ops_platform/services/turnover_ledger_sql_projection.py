from __future__ import annotations

from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any, Callable

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.bank_transaction_effective_category_provider import BankTransactionEffectiveCategoryProvider
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.turnover_ledger_extra_service import TurnoverLedgerExtraService
from fin_ops_platform.services.turnover_ledger_service import TurnoverLedgerService
from fin_ops_platform.services.turnover_ledger_source_versions import build_turnover_ledger_source_versions
from fin_ops_platform.services.turnover_relation_service import TurnoverRelationService
from fin_ops_platform.services.workbench_relation_distribution_mapper import relation_dicts_by_row_id_from_distribution_payload
from fin_ops_platform.services.workbench_relation_read_facade import FRESH_WORKBENCH_RELATION_STATUS, WorkbenchRelationReadFacade
from fin_ops_platform.services.state_store import default_data_dir


CENT = Decimal("0.01")
TURNOVER_MANUAL_CLOSURE_RELATION_MODE = "turnover_manual_closure"
_RELATION_DETAILS_KEY = "__workbench_relation_details"


class TurnoverLedgerSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any | None = None,
        read_repository: Any | None = None,
        ledger_service: TurnoverLedgerService | None = None,
        source_versions_provider: Callable[[], dict[str, Any]] | None = None,
        bank_transaction_tag_read_facade: Any | None = None,
        workbench_relation_read_facade: Any | None = None,
    ) -> None:
        self._connection = connection
        self._read_repository = read_repository
        self._ledger_service = ledger_service
        self._source_versions_provider = source_versions_provider
        self._bank_transaction_tag_read_facade = bank_transaction_tag_read_facade
        self._workbench_relation_read_facade = workbench_relation_read_facade

    def rebuild_turnover_ledger_read_model_scope(self, scope_key: str, *, source_version: object = None) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        ledger_service = self._ledger_service
        source_versions_provider = self._source_versions_provider
        read_repository = self._read_repository
        workbench_relation_read_facade = self._workbench_relation_read_facade
        if ledger_service is None or source_versions_provider is None or read_repository is None:
            built = self._build_runtime_dependencies()
            ledger_service = built["ledger_service"]
            source_versions_provider = built["source_versions_provider"]
            read_repository = built["read_repository"]
            workbench_relation_read_facade = workbench_relation_read_facade or built.get("workbench_relation_read_facade")

        rows = self._collect_rows(ledger_service)
        if normalized_scope_key != "all":
            rows = [row for row in rows if self._row_scope_key(row) == normalized_scope_key]
        source_versions = dict(source_versions_provider())
        rows = self._with_workbench_relation_context(
            rows,
            workbench_relation_read_facade=workbench_relation_read_facade,
            source_versions=source_versions,
        )
        rows = [{**row, "source_versions": source_versions} for row in rows]
        payload = {
            "scope_key": normalized_scope_key,
            "rows": rows,
            "source_versions": source_versions,
            "source_version": source_version,
        }
        save_rows = getattr(read_repository, "save_turnover_ledger_rows", None)
        if not callable(save_rows):
            raise RuntimeError("Turnover ledger SQL projection requires save_turnover_ledger_rows.")
        save_rows(payload, scope_key=normalized_scope_key)
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "source_version": source_version}

    @staticmethod
    def _collect_rows(ledger_service: TurnoverLedgerService) -> list[dict[str, Any]]:
        list_grouped = getattr(ledger_service, "list_grouped_ledger", None)
        if callable(list_grouped):
            grouped_rows = TurnoverLedgerSqlProjectionBuilder._collect_grouped_rows(ledger_service)
            if grouped_rows:
                return grouped_rows
        page = 1
        page_size = 200
        rows: list[dict[str, Any]] = []
        while True:
            payload = ledger_service.list_ledger(page=page, page_size=page_size)
            page_rows = [dict(row) for row in list(payload.get("rows") or []) if isinstance(row, dict)]
            rows.extend(page_rows)
            total = int((payload.get("pagination") or {}).get("total") or len(rows))
            if len(rows) >= total or not page_rows:
                break
            page += 1
        return rows

    @staticmethod
    def _collect_grouped_rows(ledger_service: TurnoverLedgerService) -> list[dict[str, Any]]:
        page = 1
        page_size = 200
        rows: list[dict[str, Any]] = []
        while True:
            payload = ledger_service.list_grouped_ledger(page=page, page_size=page_size)
            groups = [dict(group) for group in list(payload.get("groups") or []) if isinstance(group, dict)]
            for group in groups:
                summary = group.get("summary_row")
                row = dict(summary) if isinstance(summary, dict) else dict(group)
                row.setdefault("group_id", group.get("group_id"))
                row.setdefault("counterparty_name", group.get("counterparty_name"))
                row.setdefault("family", group.get("family"))
                row.setdefault("family_label", group.get("family_label"))
                row.setdefault("pending_direction", group.get("pending_direction"))
                row.setdefault("pending_direction_label", group.get("pending_direction_label"))
                row.setdefault("pending_amount", group.get("pending_amount"))
                row.setdefault("pending_repayment_amount", group.get("pending_repayment_amount"))
                row.setdefault("repaid_amount", group.get("repaid_amount"))
                row.setdefault("pending_collection_amount", group.get("pending_collection_amount"))
                row.setdefault("collected_amount", group.get("collected_amount"))
                row.setdefault("closed_amount", group.get("closed_amount"))
                row["flow_rows"] = [dict(item) for item in list(group.get("flow_rows") or []) if isinstance(item, dict)]
                row["allocation_lots"] = [
                    dict(item) for item in list(group.get("allocation_lots") or []) if isinstance(item, dict)
                ]
                row["lot_rows"] = [dict(item) for item in list(group.get("lot_rows") or []) if isinstance(item, dict)]
                rows.append(row)
            total = int((payload.get("pagination") or {}).get("total") or len(rows))
            if len(rows) >= total or not groups:
                break
            page += 1
        return rows

    @staticmethod
    def _row_scope_key(row: dict[str, Any]) -> str:
        value = str(row.get("first_transaction_at") or row.get("borrow_date") or row.get("scope_month") or "").strip()
        return value[:7] if len(value) >= 7 else "all"

    def _build_runtime_dependencies(self) -> dict[str, Any]:
        if self._connection is None:
            raise RuntimeError("Turnover ledger SQL projection requires a PostgreSQL connection.")
        state_store = PostgresStateStore(data_dir=default_data_dir(), connection=self._connection)
        import_service = ImportNormalizationService.from_snapshot(
            None,
            id_registry=state_store,
            fact_repository=state_store.import_fact_repository,
        )
        category_service = BankTransactionCategoryService.from_snapshot(
            state_store.load_bank_transaction_categories(),
            transaction_exists=state_store.transaction_exists,
        )
        auto_category_service = BankTransactionAutoCategoryService(category_service=category_service)
        category_provider = self._bank_transaction_tag_read_facade or BankTransactionEffectiveCategoryProvider(
            category_service=category_service,
            auto_category_service=auto_category_service,
        )
        app_settings_service = AppSettingsService(
            state_store,
            SimpleNamespace(list_projects=lambda: [], restore_manual_projects=lambda _projects: None),
            bank_transaction_category_service=category_service,
            bank_transaction_auto_category_service=auto_category_service,
        )
        relation_service = TurnoverRelationService.from_snapshot(state_store.load_turnover_relations())
        extra_service = TurnoverLedgerExtraService.from_snapshot(state_store.load_turnover_ledger_extras())
        ledger_service = TurnoverLedgerService(
            import_service=import_service,
            category_service=category_service,
            relation_service=relation_service,
            extra_service=extra_service,
            category_provider=category_provider,
            selected_tag_codes_provider=app_settings_service.turnover_ledger_selected_tag_codes,
        )
        return {
            "ledger_service": ledger_service,
            "read_repository": state_store.read_model_repository,
            "workbench_relation_read_facade": WorkbenchRelationReadFacade(
                read_model_repository=state_store.read_model_repository,
            ),
            "source_versions_provider": lambda: _with_bank_detail_source_versions(
                build_turnover_ledger_source_versions(
                    relation_service=relation_service,
                    extra_snapshot_provider=extra_service.snapshot,
                    app_settings_service=app_settings_service,
                    bank_transaction_category_service=category_service,
                ),
                category_provider,
            ),
        }

    @classmethod
    def _with_workbench_relation_context(
        cls,
        rows: list[dict[str, Any]],
        *,
        workbench_relation_read_facade: Any | None,
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if workbench_relation_read_facade is None:
            return rows
        get_by_row_ids = getattr(workbench_relation_read_facade, "get_by_row_ids", None)
        if not callable(get_by_row_ids):
            return rows
        row_ids = _dedupe_preserve_order(row_id for row in rows for row_id in cls._bank_row_ids(row))
        if not row_ids:
            return rows
        scope_keys = _dedupe_preserve_order(cls._row_scope_key(row) for row in rows)
        payload = get_by_row_ids(
            row_ids,
            require_fresh=True,
            reason="turnover_ledger_sql_projection",
            scope_keys_hint=scope_keys,
        )
        if not isinstance(payload, dict) or str(payload.get("status") or "") != FRESH_WORKBENCH_RELATION_STATUS:
            raise RuntimeError("workbench_relation_read_model_not_fresh")
        relation_source_versions = payload.get("source_versions")
        if isinstance(relation_source_versions, dict):
            source_versions["workbench_relation_source_versions"] = dict(relation_source_versions)
        relations_by_row_id = relation_dicts_by_row_id_from_distribution_payload(payload)
        return [cls._apply_workbench_relation_context(row, relations_by_row_id) for row in rows]

    @classmethod
    def _apply_workbench_relation_context(
        cls,
        row: dict[str, Any],
        relations_by_row_id: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        enriched = dict(row)
        flow_rows = [dict(item) for item in list(row.get("flow_rows") or []) if isinstance(item, dict)]
        enriched_flow_rows = [
            cls._apply_workbench_relation_context_to_leaf(flow_row, relations_by_row_id)
            for flow_row in flow_rows
        ]
        if flow_rows:
            enriched_flow_rows = _with_group_cash_closure_context(enriched_flow_rows)
            enriched["flow_rows"] = [_without_internal_relation_details(item) for item in enriched_flow_rows]
        enriched.update(_workbench_relation_summary_for_ids(cls._bank_row_ids(enriched), relations_by_row_id))
        _apply_group_cash_closure_summary(enriched, enriched_flow_rows)
        return _without_internal_relation_details(enriched)

    @staticmethod
    def _apply_workbench_relation_context_to_leaf(
        row: dict[str, Any],
        relations_by_row_id: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        enriched = dict(row)
        enriched.update(_workbench_relation_summary_for_ids(
            _bank_row_ids(row),
            relations_by_row_id,
            include_details=True,
        ))
        return enriched

    @staticmethod
    def _bank_row_ids(row: dict[str, Any]) -> list[str]:
        return _bank_row_ids(row)


def _with_bank_detail_source_versions(source_versions: dict[str, Any], category_provider: Any) -> dict[str, Any]:
    result = dict(source_versions)
    provider_source_versions = getattr(category_provider, "last_source_versions", None)
    if isinstance(provider_source_versions, dict):
        result["bank_detail_source_versions"] = dict(provider_source_versions)
    return result


def _workbench_relation_summary_for_ids(
    row_ids: list[str],
    relations_by_row_id: dict[str, list[dict[str, Any]]],
    *,
    include_details: bool = False,
) -> dict[str, Any]:
    relations: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for row_id in row_ids:
        for relation in list(relations_by_row_id.get(row_id) or []):
            if not isinstance(relation, dict):
                continue
            case_id = _text(relation.get("case_id"))
            if case_id and case_id in seen_case_ids:
                continue
            if case_id:
                seen_case_ids.add(case_id)
            relations.append(relation)
    if not relations:
        result = {
            "workbench_relation_status": "unlinked",
            "workbench_relation_case_ids": [],
            "workbench_relation_mode": "",
            "workbench_relation_source": "",
            "workbench_relation_row_ids": [],
            "linked_oa": False,
            "linked_invoice": False,
            "cash_closure_linked": False,
            "cash_closure_case_id": "",
            "cash_closure_source": "",
            "cash_closure_relation_id": "",
        }
        if include_details:
            result[_RELATION_DETAILS_KEY] = []
        return result
    statuses = _dedupe_preserve_order(_text(relation.get("relation_status") or relation.get("status")) for relation in relations)
    case_ids = _dedupe_preserve_order(_text(relation.get("case_id")) for relation in relations)
    modes = _dedupe_preserve_order(_text(relation.get("relation_mode")) for relation in relations)
    sources = _dedupe_preserve_order(_text(relation.get("relation_source")) for relation in relations)
    relation_row_ids = _dedupe_preserve_order(row_id for relation in relations for row_id in _text_list(relation.get("row_ids")))
    linked_relations = [relation for relation in relations if _is_linked_relation(relation)]
    manual_closure = next(
        (
            relation
            for relation in linked_relations
            if _text(relation.get("relation_mode")) == TURNOVER_MANUAL_CLOSURE_RELATION_MODE
        ),
        None,
    )
    result = {
        "workbench_relation_status": statuses[0] if len(statuses) == 1 else "mixed",
        "workbench_relation_case_ids": case_ids,
        "workbench_relation_mode": modes[0] if len(modes) == 1 else ("multiple" if len(modes) > 1 else ""),
        "workbench_relation_source": sources[0] if len(sources) == 1 else ("multiple" if len(sources) > 1 else ""),
        "workbench_relation_row_ids": relation_row_ids,
        "linked_oa": any(_relation_has_type(relation, "oa") for relation in linked_relations),
        "linked_invoice": any(_relation_has_type(relation, "invoice") for relation in linked_relations),
        "cash_closure_linked": manual_closure is not None,
        "cash_closure_case_id": _text(manual_closure.get("case_id")) if manual_closure is not None else "",
        "cash_closure_source": "turnover_ledger" if manual_closure is not None else "",
        "cash_closure_relation_id": _turnover_relation_id_from_case_id(
            _text(manual_closure.get("case_id")) if manual_closure is not None else ""
        ),
    }
    if include_details:
        result[_RELATION_DETAILS_KEY] = [_relation_detail(relation) for relation in relations]
    return result


def _with_group_cash_closure_context(flow_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in list(flow_rows or [])]
    group_bank_row_ids = {
        bank_row_id
        for row in rows
        for bank_row_id in _bank_row_ids(row)
        if bank_row_id
    }
    cases: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        for relation in list(row.get(_RELATION_DETAILS_KEY) or []):
            if not isinstance(relation, dict) or not _is_linked_relation(relation):
                continue
            case_id = _text(relation.get("case_id"))
            if not case_id:
                continue
            entry = cases.setdefault(case_id, {"relation": relation, "row_indexes": set()})
            entry["relation"] = relation
            entry["row_indexes"].add(index)

    for case_id, entry in cases.items():
        relation = dict(entry.get("relation") or {})
        relation_bank_row_ids = [
            row_id
            for row_id, row_type in zip(
                _text_list(relation.get("row_ids")),
                _relation_row_types(relation),
                strict=False,
            )
            if row_type == "bank"
        ]
        if len(set(relation_bank_row_ids)) < 2:
            continue
        if not set(relation_bank_row_ids).issubset(group_bank_row_ids):
            continue
        row_indexes = {
            int(index)
            for index in set(entry.get("row_indexes") or set())
            if isinstance(index, int) and 0 <= index < len(rows)
        }
        closure_rows = [
            rows[index]
            for index in sorted(row_indexes)
            if set(_bank_row_ids(rows[index])).intersection(relation_bank_row_ids)
        ]
        if not _is_zero_difference_cash_closure(closure_rows):
            continue
        source = (
            "turnover_ledger"
            if _text(relation.get("relation_mode")) == TURNOVER_MANUAL_CLOSURE_RELATION_MODE
            else "workbench_relation"
        )
        for index in row_indexes:
            rows[index]["cash_closure_linked"] = True
            rows[index]["cash_closure_case_id"] = case_id
            rows[index]["cash_closure_source"] = source
            rows[index]["cash_closure_relation_id"] = _turnover_relation_id_from_case_id(case_id)
    return rows


def _apply_group_cash_closure_summary(row: dict[str, Any], flow_rows: list[dict[str, Any]]) -> None:
    closure_rows = [flow for flow in list(flow_rows or []) if bool(flow.get("cash_closure_linked"))]
    if not closure_rows:
        return
    case_ids = _dedupe_preserve_order(_text(flow.get("cash_closure_case_id")) for flow in closure_rows)
    relation_ids = _dedupe_preserve_order(_text(flow.get("cash_closure_relation_id")) for flow in closure_rows)
    sources = _dedupe_preserve_order(_text(flow.get("cash_closure_source")) for flow in closure_rows)
    row["cash_closure_linked"] = True
    row["cash_closure_case_id"] = case_ids[0] if len(case_ids) == 1 else ""
    row["cash_closure_source"] = sources[0] if len(sources) == 1 else "multiple"
    row["cash_closure_relation_id"] = relation_ids[0] if len(relation_ids) == 1 else ""


def _is_zero_difference_cash_closure(rows: list[dict[str, Any]]) -> bool:
    income_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    seen_bank_row_ids: set[str] = set()
    for row in list(rows or []):
        bank_row_ids = _bank_row_ids(row)
        if not bank_row_ids or not set(bank_row_ids).isdisjoint(seen_bank_row_ids):
            continue
        seen_bank_row_ids.update(bank_row_ids)
        direction = _flow_cash_direction(row)
        amount = _flow_cash_amount(row)
        if direction == "income":
            income_total += amount
        elif direction == "expense":
            expense_total += amount
    return (
        len(seen_bank_row_ids) >= 2
        and income_total > Decimal("0.00")
        and expense_total > Decimal("0.00")
        and income_total.quantize(CENT) == expense_total.quantize(CENT)
    )


def _flow_cash_direction(row: dict[str, Any]) -> str:
    direction = _text(row.get("flow_direction") or row.get("direction")).lower()
    if direction in {"income", "inflow", "receipt", "receive", "收", "收入", "收款"}:
        return "income"
    if direction in {"expense", "outflow", "payment", "pay", "支", "支出", "付款"}:
        return "expense"
    borrow_amount = _money(row.get("borrow_amount"))
    repayment_amount = _money(row.get("repayment_amount"))
    if borrow_amount > Decimal("0.00") and repayment_amount <= Decimal("0.00"):
        return "income"
    if repayment_amount > Decimal("0.00") and borrow_amount <= Decimal("0.00"):
        return "expense"
    return ""


def _flow_cash_amount(row: dict[str, Any]) -> Decimal:
    flow_amount = _money(row.get("flow_amount"))
    if flow_amount > Decimal("0.00"):
        return flow_amount
    direction = _flow_cash_direction(row)
    if direction == "income":
        return _money(row.get("borrow_amount"))
    if direction == "expense":
        return _money(row.get("repayment_amount"))
    return Decimal("0.00")


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "").strip() or "0").copy_abs().quantize(CENT)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _without_internal_relation_details(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop(_RELATION_DETAILS_KEY, None)
    for key in ("flow_rows", "allocation_lots", "lot_rows", "rows"):
        children = result.get(key)
        if isinstance(children, list):
            result[key] = [
                _without_internal_relation_details(child)
                if isinstance(child, dict)
                else child
                for child in children
            ]
    return result


def _relation_detail(relation: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": _text(relation.get("case_id")),
        "relation_status": _text(relation.get("relation_status") or relation.get("status")) or "linked",
        "relation_mode": _text(relation.get("relation_mode")),
        "relation_source": _text(relation.get("relation_source")),
        "row_ids": _text_list(relation.get("row_ids")),
        "row_types": _relation_row_types(relation),
    }


def _is_linked_relation(relation: dict[str, Any]) -> bool:
    status = _text(relation.get("relation_status") or relation.get("status")) or "linked"
    return status in {"linked", "active"}


def _relation_has_type(relation: dict[str, Any], expected_type: str) -> bool:
    return expected_type in set(_relation_row_types(relation))


def _relation_row_types(relation: dict[str, Any]) -> list[str]:
    row_ids = _text_list(relation.get("row_ids"))
    raw_row_types = _text_list(relation.get("row_types"))
    row_types: list[str] = []
    for index, row_id in enumerate(row_ids):
        raw_type = raw_row_types[index] if index < len(raw_row_types) else ""
        row_types.append(_normalize_relation_row_type(raw_type, row_id=row_id))
    return row_types


def _normalize_relation_row_type(row_type: str, *, row_id: str) -> str:
    normalized = _text(row_type).lower()
    normalized_row_id = _text(row_id).lower()
    if "oa" in normalized or normalized_row_id.startswith("oa"):
        return "oa"
    if "invoice" in normalized or normalized_row_id.startswith(("invoice", "input_invoice", "output_invoice", "inv")):
        return "invoice"
    if "bank" in normalized:
        return "bank"
    return "bank"


def _turnover_relation_id_from_case_id(case_id: str) -> str:
    normalized_case_id = _text(case_id)
    return normalized_case_id.removeprefix("turnover:") if normalized_case_id.startswith("turnover:") else ""


def _bank_row_ids(row: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("source_bank_row_id", "principal_bank_row_id"):
        ids.append(_text(row.get(key)))
    ids.extend(_text_list(row.get("bank_row_ids")))
    ids.extend(_text_list(row.get("settlement_bank_row_ids")))
    for child_key in ("flow_rows", "allocation_lots", "lot_rows", "rows"):
        for child in list(row.get(child_key) or []):
            if isinstance(child, dict):
                ids.extend(_bank_row_ids(child))
    return _dedupe_preserve_order(ids)


def _dedupe_preserve_order(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _text_list(value: Any) -> list[str]:
    return [_text(item) for item in list(value or []) if _text(item)]


def _text(value: Any) -> str:
    return str(value or "").strip()
