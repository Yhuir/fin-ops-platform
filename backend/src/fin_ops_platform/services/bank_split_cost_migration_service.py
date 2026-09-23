from __future__ import annotations

from typing import Any, Callable


class BankSplitCostMigrationService:
    """One-time revocation of the superseded external-turnover cost workaround."""

    def __init__(self, *, allocation_repository_factory: Callable[[Any], Any],
                 settings_snapshot_provider: Callable[[Any], dict[str, Any]],
                 effective_category_rows: Callable[..., dict[str, dict[str, Any]]]) -> None:
        self._allocations = allocation_repository_factory
        self._settings = settings_snapshot_provider
        self._categories = effective_category_rows

    def run(self, transaction: Any, *, actor_id: str, apply: bool = False) -> dict[str, Any]:
        repository = self._allocations(transaction)
        candidates = repository.list_bank_split_migration_candidates()
        bank_ids_by_case: dict[str, set[str]] = {}
        for item in candidates:
            ids = {str(row_id) for row_id, row_type in zip(item["row_ids"] or [], item["row_types"] or [], strict=True)
                   if row_type in {"bank", "bank_transaction"}}
            source = item["source_allocations"]
            if isinstance(source, dict):
                for lines in source.values():
                    if isinstance(lines, list):
                        for line in lines:
                            if isinstance(line, dict) and line.get("bank_transaction_id"):
                                ids.add(str(line["bank_transaction_id"]))
            bank_ids_by_case[item["relation_case_id"]] = ids
        all_ids = sorted(set().union(*bank_ids_by_case.values())) if bank_ids_by_case else []
        categories = self._categories(transaction, settings=self._settings(transaction), transaction_ids=all_ids) if all_ids else {}
        external_ids = {row_id for row_id, category in categories.items() if category.get("turnover_role") == "external_turnover"}
        affected = sorted(case_id for case_id, ids in bank_ids_by_case.items() if ids & external_ids)
        mixed = sorted(case_id for case_id in affected if bank_ids_by_case[case_id] - external_ids)
        revoked = repository.revoke_for_bank_split(affected, actor_id=actor_id, parent_id="migration:external-turnover") if apply else []
        return {"affected_case_ids": affected, "mixed_case_ids": mixed, "revoked_case_ids": revoked,
                "affected_count": len(affected), "applied": apply}
