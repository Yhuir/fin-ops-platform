from __future__ import annotations

from typing import Any


class BankTransactionCategoryMutationWriter:
    def __init__(
        self,
        *,
        connection: Any,
        repository: Any,
    ) -> None:
        self._connection = connection
        self._repository = repository

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
        )
        mutation_results = list(batch_result.pop("mutation_results", []) or [])
        mutation_result = dict(mutation_results[0]) if mutation_results else {}
        return {**mutation_result, **batch_result}

    def persist_many(
        self,
        *,
        mutations: list[dict[str, Any]],
        transaction: Any | None = None,
    ) -> dict[str, object]:
        normalized_mutations = [dict(mutation) for mutation in list(mutations or [])]
        if not normalized_mutations:
            raise ValueError("Bank transaction category mutation batch must not be empty.")
        if transaction is not None:
            return self._persist_many_in_transaction(
                transaction=transaction,
                mutations=normalized_mutations,
            )
        with self._connection.transaction() as durable_transaction:
            return self._persist_many_in_transaction(
                transaction=durable_transaction,
                mutations=normalized_mutations,
            )

    def _persist_many_in_transaction(
        self,
        *,
        transaction: Any,
        mutations: list[dict[str, Any]],
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
        return batch_result
