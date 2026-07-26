from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterator

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BankTransactionAutoCategoryService,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryService,
)
from fin_ops_platform.services.bank_transaction_effective_category_provider import (
    BankTransactionEffectiveCategoryProvider,
)
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.postgres_repositories.turnover_ledger_snapshot import (
    turnover_ledger_canonical_snapshot,
)
from fin_ops_platform.services.turnover_ledger_extra_service import TurnoverLedgerExtraService
from fin_ops_platform.services.turnover_ledger_service import TurnoverLedgerService
from fin_ops_platform.services.turnover_relation_service import TurnoverRelationService


class TurnoverLedgerQueryService:
    """Read the Turnover page directly from canonical facts in one DB snapshot."""

    def __init__(
        self,
        *,
        connection: Any | None,
        local_ledger_service: TurnoverLedgerService | None = None,
    ) -> None:
        if connection is None and local_ledger_service is None:
            raise ValueError("Turnover ledger query requires a canonical connection or local service.")
        self._connection = connection
        self._local_ledger_service = local_ledger_service

    def list_ledger(
        self,
        *,
        family: str = "all",
        direction: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
        view: str | None = None,
    ) -> dict[str, Any]:
        with self._ledger_snapshot() as ledger_service:
            if str(view or "").strip().lower() == "grouped":
                payload = ledger_service.list_grouped_ledger(
                    family=family,
                    direction=direction,
                    status=status,
                    page=page,
                    page_size=page_size,
                )
            else:
                payload = ledger_service.list_ledger(
                    family=family,
                    direction=direction,
                    status=status,
                    page=page,
                    page_size=page_size,
                )
        return payload

    def get_relation_detail(self, relation_id: str) -> dict[str, Any]:
        with self._ledger_snapshot() as ledger_service:
            return ledger_service.get_relation_detail(relation_id)

    @contextmanager
    def _ledger_snapshot(self) -> Iterator[TurnoverLedgerService]:
        if self._connection is None:
            assert self._local_ledger_service is not None
            yield self._local_ledger_service
            return
        with turnover_ledger_canonical_snapshot(self._connection) as state_store:
            category_service = BankTransactionCategoryService.from_snapshot(
                state_store.load_bank_transaction_categories(),
                transaction_exists=state_store.transaction_exists,
            )
            auto_category_service = BankTransactionAutoCategoryService(
                category_service=category_service,
            )
            settings_service = AppSettingsService(
                state_store,
                SimpleNamespace(
                    list_projects=lambda: [],
                    restore_manual_projects=lambda _projects: None,
                ),
                bank_transaction_category_service=category_service,
                bank_transaction_auto_category_service=auto_category_service,
            )
            category_provider = BankTransactionEffectiveCategoryProvider(
                category_service=category_service,
                auto_category_service=auto_category_service,
            )
            relation_service = TurnoverRelationService.from_snapshot(
                state_store.load_turnover_relations(),
            )
            extra_service = TurnoverLedgerExtraService.from_snapshot(
                state_store.load_turnover_ledger_extras(),
            )

            def relation_source_rows(row_ids: list[str]) -> list[dict[str, Any]]:
                if not row_ids:
                    return []
                snapshot = state_store.load_workbench_pair_relations_for_row_ids(
                    row_ids,
                )
                if not isinstance(snapshot, dict):
                    raise RuntimeError("turnover_workbench_relation_source_unavailable")
                pair_relations = snapshot.get("pair_relations")
                if not isinstance(pair_relations, dict):
                    return []
                return [
                    dict(relation)
                    for relation in pair_relations.values()
                    if isinstance(relation, dict)
                ]

            yield TurnoverLedgerService(
                import_service=ImportNormalizationService.from_snapshot(
                    None,
                    id_registry=state_store,
                    fact_repository=state_store.import_fact_repository,
                ),
                category_service=category_service,
                relation_service=relation_service,
                extra_service=extra_service,
                category_provider=category_provider,
                selected_tag_codes_provider=settings_service.turnover_ledger_selected_tag_codes,
                workbench_relation_source_provider=relation_source_rows,
            )
