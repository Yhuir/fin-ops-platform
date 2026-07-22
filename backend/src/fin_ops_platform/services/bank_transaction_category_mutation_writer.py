from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.bank_transaction_category_refresh import (
    bank_transaction_category_refreshes,
)
from fin_ops_platform.services.workbench_reconciliation_dirty_queue import expand_scope_month_window


class BankTransactionCategoryMutationWriter:
    def __init__(
        self,
        *,
        connection: Any,
        repository: Any,
        queue_repository: Any,
        workbench_matching_repository: Any,
        workbench_matching_source_versions_provider: Callable[[], dict[str, object]] | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._connection = connection
        self._repository = repository
        self._queue_repository = queue_repository
        self._workbench_matching_repository = workbench_matching_repository
        self._workbench_matching_source_versions_provider = workbench_matching_source_versions_provider
        self._tenant_id = str(tenant_id or "default")

    def persist(
        self,
        *,
        transaction_id: str,
        mutation_type: str,
        record: dict[str, Any],
        actor_id: str,
        action: str,
        metadata: dict[str, object],
        transaction: Any | None = None,
        enqueue_refreshes: bool = True,
    ) -> dict[str, object]:
        batch_result = self.persist_many(
            mutations=[
                {
                    "transaction_id": transaction_id,
                    "mutation_type": mutation_type,
                    "record": dict(record),
                    "actor_id": actor_id,
                    "action": action,
                    "metadata": dict(metadata),
                }
            ],
            transaction=transaction,
            enqueue_refreshes=enqueue_refreshes,
        )
        mutation_results = list(batch_result.pop("mutation_results", []) or [])
        mutation_result = dict(mutation_results[0]) if mutation_results else {}
        return {**mutation_result, **batch_result}

    def persist_many(
        self,
        *,
        mutations: list[dict[str, Any]],
        transaction: Any | None = None,
        enqueue_refreshes: bool = True,
    ) -> dict[str, object]:
        normalized_mutations = [dict(mutation) for mutation in list(mutations or [])]
        if not normalized_mutations:
            raise ValueError("Bank transaction category mutation batch must not be empty.")
        if transaction is not None:
            return self._persist_many_in_transaction(
                transaction=transaction,
                mutations=normalized_mutations,
                enqueue_refreshes=enqueue_refreshes,
            )
        with self._connection.transaction() as durable_transaction:
            return self._persist_many_in_transaction(
                transaction=durable_transaction,
                mutations=normalized_mutations,
                enqueue_refreshes=enqueue_refreshes,
            )

    def _persist_many_in_transaction(
        self,
        *,
        transaction: Any,
        mutations: list[dict[str, Any]],
        enqueue_refreshes: bool,
    ) -> dict[str, object]:
        results = [
            self._repository.apply_mutation(
                transaction=transaction,
                transaction_id=str(mutation.get("transaction_id") or "").strip(),
                mutation_type=str(mutation.get("mutation_type") or "").strip(),
                record=dict(mutation.get("record") or {}),
                actor_id=str(mutation.get("actor_id") or "").strip(),
                action=str(mutation.get("action") or "").strip(),
                metadata=dict(mutation.get("metadata") or {}),
            )
            for mutation in mutations
        ]
        changed_results = [result for result in results if bool(result.get("changed"))]
        months = sorted(
            {
                str(month)
                for result in changed_results
                for month in list(result.get("affected_months") or [])
                if str(month).strip()
            }
        )
        batch_result: dict[str, object] = {
            "changed": bool(changed_results),
            "affected_months": months,
            "mutation_results": results,
        }
        if not changed_results:
            return batch_result
        action_names = sorted(
            {
                str(mutation.get("action") or "").strip()
                for mutation, result in zip(mutations, results, strict=True)
                if bool(result.get("changed")) and str(mutation.get("action") or "").strip()
            }
        )
        transaction_ids = sorted(
            {
                str(result.get("transaction_id") or "").strip()
                for result in changed_results
                if str(result.get("transaction_id") or "").strip()
            }
        )
        if enqueue_refreshes:
            refreshes = bank_transaction_category_refreshes(
                months,
                metadata={
                    "action_names": action_names,
                    "transaction_ids": transaction_ids,
                },
            )
            events = self._queue_repository.enqueue_read_model_refreshes_in_transaction(
                transaction=transaction,
                refreshes=refreshes,
                tenant_id=self._tenant_id,
                priority="high",
            )
            batch_result["outbox_event_ids"] = [
                str(getattr(event, "event_id", None) or (event.get("event_id") if isinstance(event, dict) else ""))
                for event in list(events or [])
                if getattr(event, "event_id", None) or (isinstance(event, dict) and event.get("event_id"))
            ]
        if enqueue_refreshes:
            source_versions = (
                dict(self._workbench_matching_source_versions_provider() or {})
                if callable(self._workbench_matching_source_versions_provider)
                else {}
            )
            self._workbench_matching_repository.mark_workbench_matching_dirty_scopes_in_transaction(
                transaction=transaction,
                tenant_id=self._tenant_id,
                scope_months=sorted({item for month in months for item in expand_scope_month_window(month)}),
                reason="bank_transaction_category_changed",
                source_versions=source_versions,
                debounce_seconds=0,
            )
            batch_result["operation_barrier_targets"] = [
                {
                    "read_model_key": str(item["scope_type"]),
                    "scope_type": str(item["scope_type"]),
                    "scope_key": str(item["scope_key"]),
                }
                for item in refreshes
            ]
        return batch_result
