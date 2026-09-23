from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from fin_ops_platform.services.bank_transaction_split_service import BankTransactionSplitError
from fin_ops_platform.services.workbench_relation_requirements import build_bank_relation_requirement_metadata
from fin_ops_platform.services.workbench_row_identity import canonical_workbench_row_type


class BankTransactionSplitRelationService:
    """Coordinate split consequences through transaction-bound business owners."""

    def __init__(
        self, *, relation_repository_factory: Callable[[Any], Any],
        settings_snapshot_provider: Callable[[Any], dict[str, Any]],
        effective_category_rows: Callable[..., dict[str, dict[str, Any]]],
        relation_delta_publisher: Callable[..., None],
        allocation_repository_factory: Callable[[Any], Any],
        batch_repository_factory: Callable[[Any], Any],
        turnover_split_migrator: Callable[..., dict[str, Any]],
    ) -> None:
        self._relations = relation_repository_factory
        self._settings = settings_snapshot_provider
        self._categories = effective_category_rows
        self._publish = relation_delta_publisher
        self._allocations = allocation_repository_factory
        self._batches = batch_repository_factory
        self._turnover = turnover_split_migrator

    def apply(self, transaction: Any, *, before: dict[str, Any], after: dict[str, Any], actor_id: str) -> dict[str, Any]:
        parent_id = before["transaction_id"]
        old_values = {part["id"]: (part["category_code"], part["amount"]) for part in before["parts"]}
        new_values = {part["id"]: (part["category_code"], part["amount"]) for part in after["parts"]}
        if old_values == new_values:
            return {"changed_case_ids": [], "invalidated_allocation_case_ids": [], "stale_batch_ids": [],
                    "turnover_migration": self._turnover(transaction, before=before, after=after, actor_id=actor_id),
                    "_relation_snapshot_delta": {"pair_relations": {}, "pair_relation_history": []}}
        changed_ids = {key for key in old_values if old_values[key] != new_values.get(key)}
        old_ids = {part["id"] for part in before["parts"]} or {parent_id, before["canonical_transaction_id"]}
        new_ids = [part["id"] for part in after["parts"]] or [parent_id]
        repository = self._relations(transaction)
        repository.acquire_relation_member_locks(sorted(old_ids | set(new_ids)), row_types=["bank"] * len(old_ids | set(new_ids)))
        snapshot = repository.load_active_workbench_pair_relations_for_typed_rows(
            sorted(old_ids), row_types=["bank"] * len(old_ids),
        )
        relations = [
            {**relation, "row_types": [canonical_workbench_row_type(value) for value in relation["row_types"]]}
            for relation in snapshot.get("pair_relations", {}).values()
        ]
        if not after["parts"] and len(relations) > 1:
            raise BankTransactionSplitError("split_members_in_multiple_relations", "子项已属于不同关联，请先撤回相关关联再撤销拆分。", status=409)
        case_ids = sorted(relation["case_id"] for relation in relations)
        repository.acquire_relation_member_locks([], case_ids=case_ids)
        changes: list[tuple[dict[str, Any], list[str], list[str]]] = []
        surviving = set(new_ids)
        for relation in relations:
            owned_ids = {row_id for row_id, row_type in zip(relation["row_ids"], relation["row_types"], strict=True) if row_type == "bank"}
            if before["parts"] and after["parts"] and not (owned_ids & changed_ids) and not (old_ids <= owned_ids and set(new_ids) - old_ids):
                continue
            entries: list[tuple[str, str]] = []
            inserted = False
            for row_id, row_type in zip(relation["row_ids"], relation["row_types"], strict=True):
                if row_type != "bank" or row_id not in old_ids:
                    entries.append((row_id, row_type))
                elif not before["parts"] or not after["parts"]:
                    if not inserted:
                        entries.extend((item_id, "bank") for item_id in new_ids)
                        inserted = True
                elif row_id in surviving:
                    entries.append((row_id, "bank"))
            # New units only retain the existing group intent when every old unit
            # belonged to that one group. Otherwise their ownership is undecided.
            owned = {row_id for row_id, row_type in zip(relation["row_ids"], relation["row_types"], strict=True) if row_type == "bank"}
            if before["parts"] and after["parts"] and old_ids <= owned:
                entries.extend((item_id, "bank") for item_id in new_ids if item_id not in old_ids)
            entries = list(dict.fromkeys(entries))
            changes.append((relation, [item[0] for item in entries], [item[1] for item in entries]))
        case_ids = sorted(relation["case_id"] for relation, _, _ in changes)
        settings = self._settings(transaction) if changes else {}
        bank_ids = sorted({row_id for _, ids, types in changes for row_id, row_type in zip(ids, types, strict=True) if row_type == "bank"})
        categories = self._categories(transaction, settings=settings, transaction_ids=bank_ids) if bank_ids else {}
        delta: dict[str, Any] = {"pair_relations": {}, "pair_relation_history": []}
        for relation, ids, types in changes:
            bank_members = [row_id for row_id, row_type in zip(ids, types, strict=True) if row_type == "bank"]
            tags = [categories[row_id]["effective_category_code"] for row_id in bank_members]
            metadata = deepcopy(relation.get("special_metadata") or {})
            for key in ("paired_requirement_tag_code", "paired_requires_oa", "paired_requires_invoice"):
                metadata.pop(key, None)
            metadata.update(build_bank_relation_requirement_metadata(tag_codes=tags, rules_payload=settings["paired_policy"]))
            metadata.pop("bank_split_requires_cost_confirmation", None)
            versions = deepcopy(metadata.get("bank_split_versions") or {})
            versions[parent_id] = after["version"]
            metadata["bank_split_versions"] = versions
            result = repository.replace_bank_split_members(
                before=relation, row_ids=ids, row_types=types, special_metadata=metadata,
                actor_id=actor_id, parent_id=parent_id,
                source_bank_ids=sorted(old_ids), target_bank_ids=new_ids,
            )
            delta["pair_relations"].update(result["pair_relations"])
            delta["pair_relation_history"].extend(result["pair_relation_history"])
        turnover = self._turnover(transaction, before=before, after=after, actor_id=actor_id)
        revoked = self._allocations(transaction).revoke_for_bank_split(case_ids, actor_id=actor_id, parent_id=parent_id)
        stale = self._batches(transaction).invalidate_bank_split_batches(sorted(changed_ids if before["parts"] else old_ids), actor_id=actor_id, parent_id=parent_id)
        return {"changed_case_ids": case_ids, "invalidated_allocation_case_ids": revoked,
                "stale_batch_ids": stale, "turnover_migration": turnover, "_relation_snapshot_delta": delta}

    def after_commit(self, result: dict[str, Any]) -> None:
        if result["changed_case_ids"]:
            self._publish(result["_relation_snapshot_delta"], changed_case_ids=result["changed_case_ids"], replace_history=False)
