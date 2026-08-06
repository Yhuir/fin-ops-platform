from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from fin_ops_platform.services.workbench_pair_relation_service import (
    WorkbenchPairRelationService,
)
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandService,
)
from fin_ops_platform.services.workbench_relation_requirements import (
    build_bank_relation_requirement_metadata,
)


_REQUIREMENT_KEYS = frozenset(
    {
        "paired_requirement_source",
        "paired_requirement_tag_codes",
        "paired_requirement_tag_code",
        "paired_requirement_version",
        "requires_oa",
        "requires_invoice",
        "paired_requires_oa",
        "paired_requires_invoice",
    }
)


class BankCategoryRelationClosureService:
    """Atomically persist bank categories and re-freeze active relation requirements."""

    def __init__(
        self,
        *,
        connection: Any,
        category_writer: Any,
        relation_repository_factory: Callable[[Any], Any],
        effective_category_rows: Callable[..., dict[str, dict[str, Any]]],
        settings_snapshot_provider: Callable[[Any], dict[str, Any]],
        relation_delta_publisher: Callable[..., None],
    ) -> None:
        self._connection = connection
        self._category_writer = category_writer
        self._relation_repository_factory = relation_repository_factory
        self._effective_category_rows = effective_category_rows
        self._settings_snapshot_provider = settings_snapshot_provider
        self._relation_delta_publisher = relation_delta_publisher

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
        result = self.persist_many(
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
        mutation_results = list(result.pop("mutation_results", []) or [])
        mutation_result = dict(mutation_results[0]) if mutation_results else {}
        return {**mutation_result, **result}

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
            result = self._persist_many_in_transaction(
                transaction=durable_transaction,
                mutations=normalized_mutations,
            )
        self.apply_committed_relation_delta(result)
        return self._without_relation_delta(result)

    def apply_committed_relation_delta(self, result: dict[str, object]) -> None:
        delta = result.get("_relation_snapshot_delta")
        changed_case_ids = list(result.get("changed_case_ids") or [])
        if not isinstance(delta, dict) or not changed_case_ids:
            return
        self._relation_delta_publisher(
            delta,
            changed_case_ids=changed_case_ids,
            replace_history=False,
        )

    @staticmethod
    def public_result(result: dict[str, object]) -> dict[str, object]:
        return BankCategoryRelationClosureService._without_relation_delta(result)

    def _persist_many_in_transaction(
        self,
        *,
        transaction: Any,
        mutations: list[dict[str, Any]],
    ) -> dict[str, object]:
        requested_ids = self._normalized_ids(
            mutation.get("transaction_id") for mutation in mutations
        )
        relation_repository = self._relation_repository_factory(transaction)
        relation_repository.acquire_relation_member_locks(
            requested_ids,
            row_types=["bank"] * len(requested_ids),
        )
        category_result = dict(
            self._category_writer.persist_many(
                mutations=mutations,
                transaction=transaction,
            )
            or {}
        )
        changed_results = [
            dict(item)
            for item in list(category_result.get("mutation_results") or [])
            if isinstance(item, dict) and bool(item.get("changed"))
        ]
        if not changed_results:
            return {
                **category_result,
                "changed_case_ids": [],
                "updated_relation_count": 0,
            }

        changed_bank_ids = self._normalized_ids(
            value
            for item in changed_results
            for value in (item.get("transaction_id"), item.get("bank_transaction_id"))
        )
        relation_repository.acquire_relation_member_locks(
            changed_bank_ids,
            row_types=["bank"] * len(changed_bank_ids),
        )
        relation_snapshot = relation_repository.load_active_workbench_pair_relations_for_row_ids(
            changed_bank_ids
        )
        relations = relation_snapshot.get("pair_relations") if isinstance(relation_snapshot, dict) else None
        active_relations = [
            deepcopy(relation)
            for relation in dict(relations or {}).values()
            if isinstance(relation, dict) and not self._is_exempt_relation(relation)
        ]
        if not active_relations:
            return {
                **category_result,
                "changed_case_ids": [],
                "updated_relation_count": 0,
            }

        settings_snapshot = self._settings_snapshot_provider(transaction)
        if not isinstance(settings_snapshot, dict):
            raise RuntimeError("Bank category relation settings snapshot is unavailable.")

        case_ids = self._normalized_ids(relation.get("case_id") for relation in active_relations)
        relation_repository.acquire_relation_member_locks([], case_ids=case_ids)
        bank_row_ids = self._normalized_ids(
            row_id
            for relation in active_relations
            for row_id in self._bank_row_ids(relation)
        )
        category_rows = self._effective_category_rows(
            transaction,
            settings={
                "bank_transaction_tags": deepcopy(
                    settings_snapshot.get("bank_transaction_tags") or {}
                )
            },
            transaction_ids=bank_row_ids,
        )
        if not isinstance(category_rows, dict):
            raise RuntimeError("Canonical effective bank categories are unavailable.")
        rules_payload = settings_snapshot.get("paired_policy")
        if not isinstance(rules_payload, dict):
            raise RuntimeError("Bank transaction paired policy is unavailable.")

        command_service = WorkbenchRelationCommandService(
            relation_repository=WorkbenchRelationCommandRepositoryAdapter(
                pair_relation_service=WorkbenchPairRelationService(),
                repository=relation_repository,
            ),
            require_fresh_relations=False,
        )
        changed_case_ids: list[str] = []
        relation_delta: dict[str, Any] = {
            "pair_relations": {},
            "pair_relation_history": [],
        }
        mutation_types = sorted(
            {
                str(mutation.get("mutation_type") or "").strip()
                for mutation in mutations
                if str(mutation.get("mutation_type") or "").strip()
            }
        )
        actor_id = str(mutations[0].get("actor_id") or "system").strip() or "system"
        for relation in sorted(
            active_relations,
            key=lambda item: str(item.get("case_id") or ""),
        ):
            case_id = str(relation.get("case_id") or "").strip()
            raw_tag_codes = [
                str(
                    (
                        category_rows.get(row_id)
                        if isinstance(category_rows.get(row_id), dict)
                        else {}
                    ).get("effective_category_code")
                    or ""
                ).strip()
                for row_id in self._bank_row_ids(relation)
            ]
            requirement = build_bank_relation_requirement_metadata(
                tag_codes=raw_tag_codes,
                rules_payload=rules_payload,
            )
            existing = relation.get("special_metadata")
            existing_metadata = deepcopy(existing) if isinstance(existing, dict) else {}
            intended_metadata = {
                key: value
                for key, value in existing_metadata.items()
                if key not in _REQUIREMENT_KEYS
            }
            intended_metadata.update(deepcopy(requirement))
            if intended_metadata == existing_metadata:
                continue
            result = command_service.update_relation_metadata_for_case_id(
                case_id=case_id,
                special_metadata=intended_metadata,
                replace_special_metadata=True,
                actor_id=actor_id,
                note=(
                    "Bank category mutation re-froze relation requirements: "
                    + ",".join(mutation_types)
                ),
                history_operation_type="bank_category_requirement_rebind",
            )
            relation_payload = result.get("relation")
            history_payload = result.get("history")
            if isinstance(relation_payload, dict):
                relation_delta["pair_relations"][case_id] = deepcopy(relation_payload)
            if isinstance(history_payload, dict):
                relation_delta["pair_relation_history"].append(deepcopy(history_payload))
            changed_case_ids.append(case_id)

        return {
            **category_result,
            "changed_case_ids": changed_case_ids,
            "updated_relation_count": len(changed_case_ids),
            "_relation_snapshot_delta": relation_delta if changed_case_ids else {},
        }

    @staticmethod
    def _bank_row_ids(relation: dict[str, Any]) -> list[str]:
        row_ids = list(relation.get("row_ids") or [])
        row_types = list(relation.get("row_types") or [])
        return [
            str(row_id or "").strip()
            for index, row_id in enumerate(row_ids)
            if str(row_id or "").strip()
            and str(row_types[index] if index < len(row_types) else "").strip().lower()
            == "bank"
        ]

    @staticmethod
    def _is_exempt_relation(relation: dict[str, Any]) -> bool:
        metadata = relation.get("special_metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        amount_check = relation.get("amount_check")
        amount_check = amount_check if isinstance(amount_check, dict) else {}
        return bool(
            str(metadata.get("source") or "").strip() == "batch_accounting"
            or isinstance(metadata.get("etc_batch_link"), dict)
            or str(
                amount_check.get("external_etc_batch_id")
                or amount_check.get("etc_batch_id")
                or ""
            ).strip()
        )

    @staticmethod
    def _normalized_ids(values: Any) -> list[str]:
        return sorted(
            {
                str(value or "").strip()
                for value in values
                if str(value or "").strip()
            }
        )

    @staticmethod
    def _without_relation_delta(result: dict[str, object]) -> dict[str, object]:
        return {
            key: value
            for key, value in dict(result or {}).items()
            if key != "_relation_snapshot_delta"
        }
