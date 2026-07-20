from __future__ import annotations

import json
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
from fin_ops_platform.services.runtime_paths import default_data_dir


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
        workbench_relation_source_repository: Any | None = None,
    ) -> None:
        self._connection = connection
        self._read_repository = read_repository
        self._ledger_service = ledger_service
        self._source_versions_provider = source_versions_provider
        self._bank_transaction_tag_read_facade = bank_transaction_tag_read_facade
        self._workbench_relation_source_repository = workbench_relation_source_repository
        self._base_rows_cache_key = ""
        self._base_rows_cache: list[dict[str, Any]] = []

    def rebuild_turnover_ledger_relation_delta(
        self,
        scope_key: str,
        *,
        row_ids: list[str],
        source_version: object = None,
    ) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "").strip()
        normalized_row_ids = _dedupe_preserve_order(str(row_id).strip() for row_id in list(row_ids or []))
        if not normalized_scope_key or normalized_scope_key == "all" or not normalized_row_ids:
            raise ValueError("Turnover relation delta requires one month scope and affected row ids.")
        read_repository = self._read_repository
        workbench_relation_source_repository = self._workbench_relation_source_repository
        if read_repository is None or workbench_relation_source_repository is None:
            built = self._build_runtime_dependencies()
            read_repository = read_repository or built["read_repository"]
            workbench_relation_source_repository = (
                workbench_relation_source_repository or built.get("workbench_relation_source_repository")
            )
        load_delta = getattr(read_repository, "load_turnover_ledger_relation_delta", None)
        save_delta = getattr(read_repository, "save_turnover_ledger_relation_delta", None)
        if not callable(load_delta) or not callable(save_delta):
            raise RuntimeError("Turnover ledger relation delta requires explicit repository I/O.")
        existing = load_delta(scope_key=normalized_scope_key, row_ids=normalized_row_ids)
        if not isinstance(existing, dict) or not bool(existing.get("scope_exists")):
            result = self.rebuild_turnover_ledger_read_model_scope(
                normalized_scope_key,
                source_version=source_version,
            )
            return {**result, "relation_delta": False, "relation_delta_reason": "scope_missing"}
        if bool(existing.get("source_versions_mixed")):
            result = self.rebuild_turnover_ledger_read_model_scope(
                normalized_scope_key,
                source_version=source_version,
            )
            return {**result, "relation_delta": False, "relation_delta_reason": "source_versions_mixed"}
        source_versions = (
            dict(existing.get("source_versions"))
            if isinstance(existing.get("source_versions"), dict)
            else {}
        )
        rows = [dict(row) for row in list(existing.get("rows") or []) if isinstance(row, dict)]
        rows = self._with_workbench_relation_context(
            rows,
            workbench_relation_source_repository=workbench_relation_source_repository,
            scope_key=normalized_scope_key,
            source_versions=source_versions,
        )
        if not rows:
            relation_source_versions = self._workbench_relation_source_versions(
                workbench_relation_source_repository,
                scope_key=normalized_scope_key,
                row_ids=normalized_row_ids,
            )
            if relation_source_versions:
                source_versions["workbench_relation_source_versions"] = relation_source_versions
        rows = [{**row, "source_versions": source_versions} for row in rows]
        save_delta(
            {
                "scope_key": normalized_scope_key,
                "rows": rows,
                "source_versions": source_versions,
                "source_version": source_version,
            },
            scope_key=normalized_scope_key,
        )
        return {
            "scope_key": normalized_scope_key,
            "row_count": len(rows),
            "affected_row_count": len(normalized_row_ids),
            "source_version": source_version,
            "source_versions": source_versions,
            "relation_delta": True,
        }

    def rebuild_turnover_ledger_read_model_scope(self, scope_key: str, *, source_version: object = None) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        ledger_service = self._ledger_service
        source_versions_provider = self._source_versions_provider
        read_repository = self._read_repository
        workbench_relation_source_repository = self._workbench_relation_source_repository
        if ledger_service is None or source_versions_provider is None or read_repository is None:
            built = self._build_runtime_dependencies()
            ledger_service = built["ledger_service"]
            source_versions_provider = built["source_versions_provider"]
            read_repository = built["read_repository"]
            workbench_relation_source_repository = (
                workbench_relation_source_repository or built.get("workbench_relation_source_repository")
            )

        source_versions = dict(source_versions_provider())
        existing_payload = self._existing_scope_first_page(
            read_repository=read_repository,
            scope_key=normalized_scope_key,
        )
        unchanged = self._unchanged_scope_result(
            payload=existing_payload,
            workbench_relation_source_repository=workbench_relation_source_repository,
            scope_key=normalized_scope_key,
            source_versions=source_versions,
        )
        if unchanged is not None:
            return unchanged
        refreshed_existing = self._refresh_existing_scope_rows(
            read_repository=read_repository,
            workbench_relation_source_repository=workbench_relation_source_repository,
            scope_key=normalized_scope_key,
            source_versions=source_versions,
            source_version=source_version,
            initial_payload=existing_payload,
        )
        if refreshed_existing is not None:
            return refreshed_existing
        rows = self._collect_rows_cached(ledger_service, source_versions=source_versions)
        if normalized_scope_key != "all":
            rows = [row for row in rows if self._row_scope_key(row) == normalized_scope_key]
        rows = self._with_workbench_relation_context(
            rows,
            workbench_relation_source_repository=workbench_relation_source_repository,
            scope_key=normalized_scope_key,
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

    @classmethod
    def _unchanged_scope_result(
        cls,
        *,
        payload: dict[str, Any] | None,
        workbench_relation_source_repository: Any | None,
        scope_key: str,
        source_versions: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        existing_source_versions = payload.get("source_versions")
        if not isinstance(existing_source_versions, dict):
            return None
        current_source_versions = dict(source_versions)
        if any(existing_source_versions.get(key) != value for key, value in current_source_versions.items()):
            return None
        rows = [dict(row) for row in list(payload.get("rows") or []) if isinstance(row, dict)]
        if workbench_relation_source_repository is not None:
            row_ids = _dedupe_preserve_order(row_id for row in rows for row_id in cls._bank_row_ids(row))
            if row_ids:
                relation_source_versions = cls._workbench_relation_source_versions(
                    workbench_relation_source_repository,
                    scope_key=scope_key,
                    row_ids=row_ids,
                )
                if relation_source_versions:
                    current_source_versions["workbench_relation_source_versions"] = dict(relation_source_versions)
        if existing_source_versions != current_source_versions:
            return None
        pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
        return {
            "scope_key": scope_key,
            "row_count": int(pagination.get("total") or len(rows)),
            "source_versions": current_source_versions,
            "skipped": True,
            "skip_reason": "source_versions_unchanged",
        }

    @classmethod
    def _refresh_existing_scope_rows(
        cls,
        *,
        read_repository: Any,
        workbench_relation_source_repository: Any | None,
        scope_key: str,
        source_versions: dict[str, Any],
        source_version: object,
        initial_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        rows, existing_source_versions = cls._existing_scope_rows(
            read_repository=read_repository,
            scope_key=scope_key,
            initial_payload=initial_payload,
        )
        if not rows or not isinstance(existing_source_versions, dict):
            return None
        if any(existing_source_versions.get(key) != value for key, value in source_versions.items()):
            return None
        refreshed_source_versions = dict(source_versions)
        rows = cls._with_workbench_relation_context(
            rows,
            workbench_relation_source_repository=workbench_relation_source_repository,
            scope_key=scope_key,
            source_versions=refreshed_source_versions,
        )
        rows = [{**row, "source_versions": refreshed_source_versions} for row in rows]
        save_rows = getattr(read_repository, "save_turnover_ledger_rows", None)
        if not callable(save_rows):
            return None
        save_rows(
            {
                "scope_key": scope_key,
                "rows": rows,
                "source_versions": refreshed_source_versions,
                "source_version": source_version,
            },
            scope_key=scope_key,
        )
        return {
            "scope_key": scope_key,
            "row_count": len(rows),
            "source_version": source_version,
            "source_versions": refreshed_source_versions,
            "refreshed_from_existing_scope": True,
        }

    @staticmethod
    def _existing_scope_rows(
        *,
        read_repository: Any,
        scope_key: str,
        initial_payload: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        list_view = getattr(read_repository, "list_turnover_ledger_view", None)
        if not callable(list_view):
            return [], None
        page = 1
        page_size = 200
        rows: list[dict[str, Any]] = []
        source_versions: dict[str, Any] | None = None
        while True:
            payload = initial_payload if page == 1 and isinstance(initial_payload, dict) else list_view(
                scope_key=scope_key,
                page=page,
                page_size=page_size,
            )
            if not isinstance(payload, dict):
                return [], None
            if source_versions is None and isinstance(payload.get("source_versions"), dict):
                source_versions = dict(payload["source_versions"])
            page_rows = [dict(row) for row in list(payload.get("rows") or []) if isinstance(row, dict)]
            rows.extend(page_rows)
            pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
            total = int(pagination.get("total") or len(rows))
            if len(rows) >= total or not page_rows:
                break
            page += 1
        return rows, source_versions

    @staticmethod
    def _existing_scope_first_page(
        *,
        read_repository: Any,
        scope_key: str,
    ) -> dict[str, Any] | None:
        list_view = getattr(read_repository, "list_turnover_ledger_view", None)
        if not callable(list_view):
            return None
        payload = list_view(scope_key=scope_key, page=1, page_size=200)
        return dict(payload) if isinstance(payload, dict) else None

    def _collect_rows_cached(
        self,
        ledger_service: TurnoverLedgerService,
        *,
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        cache_key = json.dumps(source_versions, ensure_ascii=False, sort_keys=True, default=str)
        if cache_key == self._base_rows_cache_key:
            return [dict(row) for row in self._base_rows_cache]
        rows = self._collect_rows(ledger_service)
        self._base_rows_cache_key = cache_key
        self._base_rows_cache = [dict(row) for row in rows]
        return [dict(row) for row in rows]

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
            "workbench_relation_source_repository": state_store.read_model_repository,
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
        workbench_relation_source_repository: Any | None,
        scope_key: str,
        source_versions: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if workbench_relation_source_repository is None:
            return rows
        bundle_reader = getattr(
            workbench_relation_source_repository,
            "workbench_relation_source_bundle_from_source",
            None,
        )
        if not callable(bundle_reader):
            return rows
        row_ids = _dedupe_preserve_order(row_id for row in rows for row_id in cls._bank_row_ids(row))
        if not row_ids:
            return rows
        bundle = bundle_reader(
            scope_key=scope_key,
            row_ids=row_ids,
        )
        if not isinstance(bundle, dict):
            raise RuntimeError("workbench_relation_source_bundle_unavailable")
        source_rows = bundle.get("rows") if isinstance(bundle.get("rows"), list) else []
        relation_source_versions = (
            bundle.get("source_versions")
            if isinstance(bundle.get("source_versions"), dict)
            else {}
        )
        if relation_source_versions:
            source_versions["workbench_relation_source_versions"] = dict(relation_source_versions)
        relations_by_row_id = _relations_by_row_id_from_source_rows(source_rows)
        return [cls._apply_workbench_relation_context(row, relations_by_row_id) for row in rows]

    @staticmethod
    def _workbench_relation_source_versions(
        repository: Any,
        *,
        scope_key: str,
        row_ids: list[str],
    ) -> dict[str, Any]:
        summary_reader = getattr(repository, "workbench_relation_source_summary_from_source", None)
        if not callable(summary_reader):
            return {}
        payload = summary_reader(
            scope_key=scope_key,
            row_ids=row_ids,
            include_row_ids=True,
        )
        return dict(payload) if isinstance(payload, dict) else {}

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
            "workbench_relations": [],
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
        "workbench_relations": [_relation_detail(relation) for relation in relations],
        "linked_oa": any(_relation_has_type(relation, "oa") for relation in linked_relations),
        "linked_invoice": any(_relation_has_type(relation, "invoice") for relation in linked_relations),
        "cash_closure_linked": manual_closure is not None,
        "cash_closure_case_id": _text(manual_closure.get("case_id")) if manual_closure is not None else "",
        "cash_closure_source": "turnover_ledger" if manual_closure is not None else "",
        "cash_closure_relation_id": _turnover_relation_id_from_relation(manual_closure),
    }
    if include_details:
        result[_RELATION_DETAILS_KEY] = [_relation_detail(relation) for relation in relations]
    return result


def _relations_by_row_id_from_source_rows(
    source_rows: list[dict[str, Any]] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Map canonical active relations without depending on another read model."""
    result: dict[str, list[dict[str, Any]]] = {}
    for source_row in list(source_rows or []):
        if not isinstance(source_row, dict) or _text(source_row.get("status")) != "active":
            continue
        raw_payload = source_row.get("raw_payload") if isinstance(source_row.get("raw_payload"), dict) else {}
        normalized_payload = (
            raw_payload.get("normalized_payload")
            if isinstance(raw_payload.get("normalized_payload"), dict)
            else raw_payload
        )
        case_id = _text(source_row.get("case_id") or normalized_payload.get("case_id"))
        row_ids = _text_list(source_row.get("row_ids") or normalized_payload.get("row_ids"))
        if not case_id or not row_ids:
            continue
        relation = {
            "case_id": case_id,
            "relation_mode": _text(
                source_row.get("relation_mode") or normalized_payload.get("relation_mode")
            ),
            "status": "active",
            "relation_status": "linked",
            "relationStatus": "linked",
            "relation_source": _text(normalized_payload.get("relation_source")) or "manual",
            "month_scope": _text(normalized_payload.get("month_scope")),
            "row_ids": row_ids,
            "row_types": _text_list(source_row.get("row_types") or normalized_payload.get("row_types")),
            "amount_check": dict(
                source_row.get("amount_check")
                if isinstance(source_row.get("amount_check"), dict)
                else normalized_payload.get("amount_check")
                if isinstance(normalized_payload.get("amount_check"), dict)
                else {}
            ),
            "special_metadata": dict(
                normalized_payload.get("special_metadata")
                if isinstance(normalized_payload.get("special_metadata"), dict)
                else {}
            ),
            "source_versions": dict(
                normalized_payload.get("source_versions")
                if isinstance(normalized_payload.get("source_versions"), dict)
                else {}
            ),
            "note": _text(normalized_payload.get("note")),
            "raw_payload": dict(normalized_payload),
        }
        for row_id in row_ids:
            result.setdefault(row_id, []).append(relation)
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
            rows[index]["cash_closure_relation_id"] = _turnover_relation_id_from_relation(relation)
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


def _turnover_relation_id_from_relation(relation: dict[str, Any] | None) -> str:
    """Expose the legacy relation id only when the canonical relation records it."""
    if not isinstance(relation, dict):
        return ""
    metadata = relation.get("special_metadata")
    if not isinstance(metadata, dict):
        raw_payload = relation.get("raw_payload")
        metadata = raw_payload.get("special_metadata") if isinstance(raw_payload, dict) else None
    return _text(metadata.get("turnover_relation_id")) if isinstance(metadata, dict) else ""


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
