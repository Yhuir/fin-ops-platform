from __future__ import annotations

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
from fin_ops_platform.services.state_store import default_data_dir


class TurnoverLedgerSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any | None = None,
        read_repository: Any | None = None,
        ledger_service: TurnoverLedgerService | None = None,
        source_versions_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._connection = connection
        self._read_repository = read_repository
        self._ledger_service = ledger_service
        self._source_versions_provider = source_versions_provider

    def rebuild_turnover_ledger_read_model_scope(self, scope_key: str, *, source_version: object = None) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        ledger_service = self._ledger_service
        source_versions_provider = self._source_versions_provider
        read_repository = self._read_repository
        if ledger_service is None or source_versions_provider is None or read_repository is None:
            built = self._build_runtime_dependencies()
            ledger_service = built["ledger_service"]
            source_versions_provider = built["source_versions_provider"]
            read_repository = built["read_repository"]

        rows = self._collect_rows(ledger_service)
        if normalized_scope_key != "all":
            rows = [row for row in rows if self._row_scope_key(row) == normalized_scope_key]
        source_versions = dict(source_versions_provider())
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
        category_provider = BankTransactionEffectiveCategoryProvider(
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
            "source_versions_provider": lambda: build_turnover_ledger_source_versions(
                relation_service=relation_service,
                extra_snapshot_provider=extra_service.snapshot,
                app_settings_service=app_settings_service,
                bank_transaction_category_service=category_service,
            ),
        }
