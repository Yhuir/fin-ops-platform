from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_details_canonical_query import PostgresBankDetailsCanonicalQueryRepository
from fin_ops_platform.services.bank_transaction_category_service import bank_transaction_tag_dictionary_display_payload
from fin_ops_platform.services.bank_transaction_split_service import SPLIT_CATEGORY_FIELDS, BankTransactionSplitError
from fin_ops_platform.services.bank_turnover_tag_semantics import (
    EXTERNAL_TURNOVER_THIRD_LABEL_OPTIONS,
    is_external_turnover_definition,
)
from fin_ops_platform.services.postgres_repositories.bank_transaction_category import (
    PostgresBankTransactionCategoryRepository,
)
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


class PostgresBankTransactionSplitRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @contextmanager
    def transaction(self, *, read_only: bool) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            if read_only:
                transaction.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            yield transaction

    def load(self, transaction: Any, transaction_id: str, *, for_update: bool) -> dict[str, Any]:
        bank = transaction.fetch_one(
            """
            SELECT b.id::text AS canonical_transaction_id,
                   coalesce(b.legacy_mongo_id, b.id::text) AS transaction_id,
                   b.amount, b.written_off_amount, b.txn_direction AS direction,
                   to_char(coalesce(b.trade_time::date, b.txn_date), 'YYYY-MM') AS month
            FROM app.bank_transactions b
            WHERE b.status <> 'deleted' AND (
                b.id::text = %s OR b.legacy_mongo_id = %s OR b.id = (
                    SELECT bank_transaction_id FROM app.bank_transaction_split_items WHERE id::text = %s
                )
            )
            """,
            (transaction_id, transaction_id, transaction_id),
        )
        if bank is None:
            raise BankTransactionSplitError("unknown_transaction_id", "银行流水不存在。", status=404)
        if for_update:
            relation_repository = PostgresWorkbenchRelationRepository(transaction)
            source_ids = [bank["transaction_id"], bank["canonical_transaction_id"]]
            existing_items = transaction.fetch_all(
                "SELECT id::text AS id FROM app.bank_transaction_split_items WHERE bank_transaction_id=%s::uuid ORDER BY id",
                (bank["canonical_transaction_id"],),
            )
            item_ids = [item["id"] for item in existing_items]
            member_ids = sorted(set(source_ids + item_ids))
            related = relation_repository.load_active_workbench_pair_relations_for_typed_rows(
                member_ids, row_types=["bank"] * len(member_ids),
            )
            case_ids = sorted(related["pair_relations"])
            # Include every affected case member in one ordered advisory lock set.
            # Otherwise two splits in the same case can each hold one parent and
            # wait for the other case member after acquiring their parent row lock.
            relation_repository.acquire_relation_member_locks(
                member_ids, row_types=["bank"] * len(member_ids), case_ids=case_ids,
            )
            current_related = relation_repository.load_active_workbench_pair_relations_for_typed_rows(
                member_ids, row_types=["bank"] * len(member_ids),
            )
            if current_related != related:
                raise BankTransactionSplitError("split_relation_conflict", "流水关联已变化，请重新读取后再保存。", status=409)
            locked = transaction.fetch_one(
                """SELECT id::text AS canonical_transaction_id,
                          coalesce(legacy_mongo_id,id::text) AS transaction_id,
                          amount, written_off_amount, txn_direction AS direction,
                          to_char(coalesce(trade_time::date,txn_date),'YYYY-MM') AS month
                   FROM app.bank_transactions WHERE id=%s::uuid AND status <> 'deleted' FOR UPDATE""",
                (bank["canonical_transaction_id"],),
            )
            if locked is None:
                raise BankTransactionSplitError("unknown_transaction_id", "银行流水不存在。", status=404)
            bank = locked
        settings = PostgresBankDetailsCanonicalQueryRepository.settings_payload(transaction)
        policy = AppSettingsService.bank_category_relation_policy_snapshot(settings)
        definitions = self.tag_definitions(policy["bank_transaction_tags"])
        version_row = transaction.fetch_one(
            "SELECT version FROM app.bank_transaction_split_sets WHERE bank_transaction_id = %s::uuid",
            (bank["canonical_transaction_id"],),
        )
        items = transaction.fetch_all(
            "SELECT id::text AS id, category_code, amount, category_payload FROM app.bank_transaction_split_items WHERE bank_transaction_id = %s::uuid ORDER BY position",
            (bank["canonical_transaction_id"],),
        )
        parts = self.decorate_parts(items, definitions)
        category_rows = PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows(
            transaction, settings=settings, transaction_ids=[bank["transaction_id"]],
        ) if not parts else {}
        category = category_rows.get(bank["transaction_id"], {})
        return {
            "transaction_id": bank["transaction_id"],
            "canonical_transaction_id": bank["canonical_transaction_id"],
            "amount": format(bank["amount"], ".2f"), "written_off_amount": format(bank["written_off_amount"], ".2f"),
            "direction": bank["direction"],
            "version": int(version_row["version"]) if version_row else 0,
            "category_code": category.get("effective_category_code"),
            **self.category_instance(category),
            "turnover_third_label_options": list(EXTERNAL_TURNOVER_THIRD_LABEL_OPTIONS),
            "parts": parts,
            "tag_definitions": definitions,
            "affected_months": [bank["month"]] if bank["month"] else [],
        }

    @staticmethod
    def tag_definitions(dictionary: dict[str, Any]) -> list[dict[str, Any]]:
        definitions = bank_transaction_tag_dictionary_display_payload(dictionary)["definitions"]
        result = []
        for definition in definitions:
            path = [definition[key] for key in ("output_primary_label", "output_sub_label", "output_third_label") if definition.get(key)] if definition.get("output_primary_label") else definition["path"]
            # A flat system tag has an empty taxonomy path and its own label.
            if not path:
                path = [definition["label"]]
            result.append({**definition, "turnover_role": "external_turnover" if is_external_turnover_definition(definition) else "", "path": path, "label": " / ".join(path),
                           "primary_label": path[0], "sub_label": " / ".join(path[1:])})
        return result

    @staticmethod
    def category_instance(category: dict[str, Any]) -> dict[str, Any]:
        return {key: (category.get("effective_" + key) or []) if key == "category_label_path" else
                category.get("effective_" + key) if key.startswith("category_") else category.get(key)
                for key in SPLIT_CATEGORY_FIELDS}

    @staticmethod
    def decorate_parts(parts: list[dict[str, Any]], definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_code = {definition["code"]: definition for definition in definitions}
        result = []
        for part in parts:
            definition = by_code.get(part["category_code"])
            if definition is None:
                raise BankTransactionSplitError("split_category_missing", "流水子项引用的标签不存在，请恢复标签配置。", status=409)
            path = list(definition["path"])
            instance = {"category_label": definition["label"], "category_primary_label": path[0],
                        "category_sub_label": path[1] if len(path) > 1 else None,
                        "category_third_label": path[2] if len(path) > 2 else None, "category_label_path": path,
                        "turnover_role": definition.get("turnover_role", ""),
                        "turnover_action_type": definition.get("turnover_action_type"), "turnover_family": definition.get("turnover_family")}
            instance.update(part.get("category_payload") or {})
            result.append({"id": part["id"], "category_code": part["category_code"], **instance,
                           "category_path": instance["category_label_path"],
                           "amount": format(part["amount"], ".2f") if not isinstance(part["amount"], str) else part["amount"]})
        return result

    def load_many(self, transaction: Any, transaction_ids: list[str]) -> list[dict[str, Any]]:
        """Load a drawer's bank facts in a fixed number of queries, in request order."""
        banks = transaction.fetch_all(
            """SELECT requested.request_id, b.id::text AS canonical_transaction_id,
                      coalesce(b.legacy_mongo_id,b.id::text) AS transaction_id,
                      b.amount,b.written_off_amount,b.txn_direction AS direction,
                      to_char(coalesce(b.trade_time::date,b.txn_date),'YYYY-MM') AS month,
                      coalesce(s.version,0) AS version
               FROM unnest(%s::text[]) WITH ORDINALITY requested(request_id,position)
               LEFT JOIN app.bank_transaction_split_items requested_item ON requested_item.id::text=requested.request_id
               JOIN app.bank_transactions b ON (b.id::text=requested.request_id OR b.legacy_mongo_id=requested.request_id OR b.id=requested_item.bank_transaction_id)
               LEFT JOIN app.bank_transaction_split_sets s ON s.bank_transaction_id=b.id
               WHERE b.status <> 'deleted' ORDER BY requested.position""",
            (transaction_ids,),
        )
        if len(banks) != len(transaction_ids):
            raise BankTransactionSplitError("unknown_transaction_id", "银行流水不存在。", status=404)
        settings = PostgresBankDetailsCanonicalQueryRepository.settings_payload(transaction)
        definitions = self.tag_definitions(AppSettingsService.bank_category_relation_policy_snapshot(settings)["bank_transaction_tags"])
        items = transaction.fetch_all(
            """SELECT bank_transaction_id::text AS parent_id,id::text AS id,category_code,amount,category_payload
               FROM app.bank_transaction_split_items WHERE bank_transaction_id=ANY(%s::uuid[]) ORDER BY position""",
            (list({bank["canonical_transaction_id"] for bank in banks}),),
        )
        by_parent: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            by_parent.setdefault(item["parent_id"], []).append(item)
        unsplit_ids = [bank["transaction_id"] for bank in banks if bank["canonical_transaction_id"] not in by_parent]
        categories = PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows(
            transaction,settings=settings,transaction_ids=unsplit_ids,
        ) if unsplit_ids else {}
        return [{
            "transaction_id": bank["transaction_id"], "canonical_transaction_id": bank["canonical_transaction_id"],
            "amount": format(bank["amount"], ".2f"), "written_off_amount": format(bank["written_off_amount"], ".2f"), "direction": bank["direction"], "version": int(bank["version"]),
            "category_code": categories.get(bank["transaction_id"], {}).get("effective_category_code"),
            **self.category_instance(categories.get(bank["transaction_id"], {})),
            "turnover_third_label_options": list(EXTERNAL_TURNOVER_THIRD_LABEL_OPTIONS),
            "parts": self.decorate_parts(by_parent.get(bank["canonical_transaction_id"], []), definitions),
            "tag_definitions": definitions, "affected_months": [bank["month"]] if bank["month"] else [],
        } for bank in banks]

    def persist(self, transaction: Any, *, before: dict[str, Any], parts: list[dict[str, Any]], category_code: str | None, actor_id: str, category_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        parent_id = before["canonical_transaction_id"]
        version = before["version"] + 1
        transaction.execute(
            """INSERT INTO app.bank_transaction_split_sets(bank_transaction_id,version,updated_by)
               VALUES (%s::uuid,%s,%s) ON CONFLICT(bank_transaction_id) DO UPDATE
               SET version=excluded.version,updated_by=excluded.updated_by,updated_at=now()""",
            (parent_id, version, actor_id),
        )
        transaction.execute(
            "DELETE FROM app.bank_transaction_split_items WHERE bank_transaction_id=%s::uuid AND NOT (id=ANY(%s::uuid[]))",
            (parent_id, [part["id"] for part in parts]),
        )
        if parts:
            transaction.execute_many_values(
                """INSERT INTO app.bank_transaction_split_items(id,bank_transaction_id,category_code,amount,position,category_payload)
                   VALUES (%s::uuid,%s::uuid,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET
                   category_code=excluded.category_code,amount=excluded.amount,position=excluded.position,category_payload=excluded.category_payload""",
                [(part["id"], parent_id, part["category_code"], part["amount"], part["position"], jsonb(part["category_payload"])) for part in parts],
            )
        else:
            if category_payload is None:
                raise ValueError("Unsplit requires an explicit category instance.")
            PostgresBankTransactionCategoryRepository(transaction).apply_mutation(
                transaction=transaction, transaction_id=before["transaction_id"],
                mutation_type="manual_assign", actor_id=actor_id,
                action="bank_transaction_split_removed", metadata={},
                record={"category_code": category_code, **category_payload},
            )
        return {**before, "version": version, "parts": self.decorate_parts(parts, before["tag_definitions"]), "category_code": category_code if not parts else None,
                **(category_payload or {key: [] if key == "category_label_path" else None for key in SPLIT_CATEGORY_FIELDS})}

    @staticmethod
    def audit(transaction: Any, *, before: dict[str, Any], after: dict[str, Any], actor_id: str) -> None:
        payload = {"before": {key: before[key] for key in ("version", "parts", "category_code", *SPLIT_CATEGORY_FIELDS)}, "after": {key: after[key] for key in ("version", "parts", "category_code", *SPLIT_CATEGORY_FIELDS)}}
        transaction.execute(
            """INSERT INTO audit.events(event_type,object_type,object_id,actor_id,payload,raw_payload)
               VALUES ('bank_transaction_splits_saved','bank_transaction',%s,%s,%s,%s)""",
            (before["transaction_id"], actor_id, jsonb(payload), jsonb({"normalized_payload": payload})),
        )
