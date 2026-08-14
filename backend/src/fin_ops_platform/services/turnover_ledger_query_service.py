from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterator

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryService,
)
from fin_ops_platform.services.bank_details_canonical_query import (
    PostgresBankDetailsCanonicalQueryRepository,
)
from fin_ops_platform.services.bank_turnover_tag_semantics import (
    turnover_family_for_third_label,
)
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
        with turnover_ledger_canonical_snapshot(self._connection) as snapshot:
            state_store, transaction = snapshot
            settings_snapshot = state_store.load_app_settings()
            tag_dictionary = settings_snapshot.get("bank_transaction_tags")
            category_service = BankTransactionCategoryService()
            if isinstance(tag_dictionary, dict):
                category_service.configure_tag_dictionary(tag_dictionary)
            selected_tag_codes = AppSettingsService.turnover_ledger_selected_tag_codes_from_settings(
                settings_snapshot
            )
            canonical_rows, canonical_categories = _canonical_turnover_rows(
                PostgresBankDetailsCanonicalQueryRepository.effective_category_rows(
                    transaction,
                    settings=settings_snapshot,
                    category_codes=selected_tag_codes,
                ),
                category_service=category_service,
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
                snapshot = state_store.load_active_workbench_pair_relations_for_row_ids(
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
                import_service=SimpleNamespace(
                    list_transactions=lambda **_kwargs: canonical_rows,
                ),
                category_service=category_service,
                relation_service=relation_service,
                extra_service=extra_service,
                category_provider=SimpleNamespace(
                    bulk_get_for_rows=lambda _rows: canonical_categories,
                ),
                selected_tag_codes_provider=lambda: selected_tag_codes,
                workbench_relation_source_provider=relation_source_rows,
            )


def _canonical_turnover_rows(
    rows: list[dict[str, Any]],
    *,
    category_service: BankTransactionCategoryService,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    transactions: list[dict[str, Any]] = []
    categories: dict[str, dict[str, Any]] = {}
    for source in rows:
        row = dict(source)
        row_id = str(row.get("row_id") or "").strip()
        if not row_id:
            continue
        definition = row.get("effective_definition")
        definition = dict(definition) if isinstance(definition, dict) else {}
        semantics = category_service.category_semantics_for_code(
            row.get("effective_category_code")
        )
        primary = str(row.get("effective_category_primary_label") or "").strip()
        secondary = str(row.get("effective_category_sub_label") or "").strip()
        third = str(row.get("effective_category_third_label") or "").strip()
        label_path = [label for label in (primary, secondary, third) if label]
        category_path = [
            str(item)
            for item in list(definition.get("path") or [])
            if str(item).strip()
        ]
        source_name = str(row.get("effective_category_source") or "").strip()
        category_version = (
            row.get("confirmation_version")
            if source_name == "manual_confirmation"
            else row.get("manual_category_version")
        )
        category_rule_version = str(row.get("confirmation_rule_version") or "").strip()
        if source_name not in {
            "manual",
            "manual_confirmation",
            "auto_confirmation",
            "turnover_ledger",
        }:
            category_rule_version = category_service.auto_tag_rule_version_label()
        transactions.append(
            {
                **row,
                "id": row_id,
                "txn_direction": (
                    "inflow" if str(row.get("direction") or "") == "income" else "outflow"
                ),
            }
        )
        categories[row_id] = {
            "transaction_id": row_id,
            "category_code": row.get("effective_category_code"),
            "category_label": row.get("effective_category_label"),
            "category_path": category_path,
            "category_label_path": label_path,
            "category_primary_label": primary,
            "category_sub_label": secondary,
            "category_third_label": third,
            "category_source": source_name,
            "source": source_name,
            "category_version": int(category_version or 0),
            "manual_category_version": int(row.get("manual_category_version") or 0),
            "category_rule_version": category_rule_version,
            "turnover_role": semantics.get("turnover_role")
            or definition.get("turnover_role"),
            "turnover_action_type": semantics.get("turnover_action_type")
            or definition.get("turnover_action_type"),
            "turnover_family": semantics.get("turnover_family")
            or turnover_family_for_third_label(third)
            or definition.get("turnover_family"),
        }
    return transactions, categories


def canonical_turnover_bank_rows_by_ids(
    transaction: Any,
    transaction_ids: list[str],
    *,
    tenant_id: str = "default",
) -> list[dict[str, Any]]:
    """Load an exact turnover selection from the same canonical facts as the page GET."""
    normalized_ids = list(
        dict.fromkeys(
            str(transaction_id or "").strip()
            for transaction_id in list(transaction_ids or [])
            if str(transaction_id or "").strip()
        )
    )
    if not normalized_ids:
        return []
    settings_snapshot = PostgresBankDetailsCanonicalQueryRepository.settings_payload(
        transaction
    )
    tag_dictionary = settings_snapshot.get("bank_transaction_tags")
    category_service = BankTransactionCategoryService()
    if isinstance(tag_dictionary, dict):
        category_service.configure_tag_dictionary(tag_dictionary)
    canonical_rows, canonical_categories = _canonical_turnover_rows(
        PostgresBankDetailsCanonicalQueryRepository.turnover_bank_row_selection_rows(
            transaction,
            settings=settings_snapshot,
            transaction_ids=normalized_ids,
            tenant_id=tenant_id,
        ),
        category_service=category_service,
    )
    selected_tag_codes = AppSettingsService.turnover_ledger_selected_tag_codes_from_settings(
        settings_snapshot
    )
    return TurnoverLedgerService(
        import_service=SimpleNamespace(
            list_transactions=lambda **_kwargs: canonical_rows,
        ),
        category_service=category_service,
        relation_service=TurnoverRelationService.from_snapshot({}),
        category_provider=SimpleNamespace(
            bulk_get_for_rows=lambda _rows: canonical_categories,
        ),
        selected_tag_codes_provider=lambda: selected_tag_codes,
    ).selected_bank_rows()
