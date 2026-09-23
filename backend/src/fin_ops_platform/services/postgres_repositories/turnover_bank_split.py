from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_details_canonical_query import PostgresBankDetailsCanonicalQueryRepository
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.bank_transaction_split_service import SPLIT_CATEGORY_FIELDS, BankTransactionSplitError
from fin_ops_platform.services.postgres_repositories.common import jsonb, row_payload
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.turnover_ledger_query_service import _canonical_turnover_rows
from fin_ops_platform.services.turnover_ledger_service import TurnoverLedgerService
from fin_ops_platform.services.turnover_relation_service import TurnoverRelationService, TurnoverRelationValidationError


class PostgresTurnoverBankSplitRepository:
    """Move turnover-owned identities in the split writer's existing transaction."""

    def __init__(self, transaction: Any) -> None:
        self._tx = transaction

    def apply(self, *, before: dict[str, Any], after: dict[str, Any], actor_id: str) -> dict[str, Any]:
        owner = PostgresWorkbenchRepository(self._tx)
        parent = self._tx.fetch_one("select * from app.bank_transactions where id=%s::uuid", (before["canonical_transaction_id"],))
        counterparty = " ".join(str(parent["counterparty_name_raw"] or "").split())
        old_ids = {part["id"] for part in before["parts"]} or {before["transaction_id"]}
        stored = self._tx.fetch_all("""select raw_payload from app.turnover_relations
            where regexp_replace(trim(counterparty_name), '\\s+', ' ', 'g')=%s for update""", (counterparty,))
        snapshot = {"relations": [row_payload(row, "raw_payload") for row in stored], "audit_log": []}
        manual = [relation for relation in snapshot["relations"]
                  if (relation.get("source") == "manual" or relation.get("status") == "confirmed")
                  and old_ids.intersection(relation.get("bank_row_ids", []))]
        if not manual and not self._tx.fetch_one("select 1 from app.turnover_ledger_extras limit 1"):
            return {"migrated_extras": [], "migrated_relations": []}
        settings = self._tx.fetch_one("select settings_payload from app.app_settings where settings_key='app_settings'")["settings_payload"]
        category_service = BankTransactionCategoryService()
        category_service.configure_tag_dictionary(settings["bank_transaction_tags"])
        selected = AppSettingsService.turnover_ledger_selected_tag_codes_from_settings(settings)
        peer_ids = [str(row["row_id"]) for row in self._tx.fetch_all(
            """select coalesce(legacy_mongo_id,id::text) row_id from app.bank_transaction_units
            where regexp_replace(trim(counterparty_name_raw), '\\s+', ' ', 'g')=%s""", (counterparty,))]
        source_rows = PostgresBankDetailsCanonicalQueryRepository.effective_category_rows(
            self._tx, settings=settings, category_codes=selected, transaction_ids=peer_ids)
        rows, categories = _canonical_turnover_rows(source_rows, category_service=category_service)
        ledger = TurnoverLedgerService(
            import_service=SimpleNamespace(list_transactions=lambda **kwargs: rows),
            category_service=category_service, relation_service=TurnoverRelationService(),
            category_provider=SimpleNamespace(bulk_get_for_rows=lambda rows: categories),
            selected_tag_codes_provider=lambda: selected,
        )
        current = ledger.selected_bank_rows()
        previous = []
        before_parts = before["parts"] or [{**before, "id": before["transaction_id"]}]
        for part in before_parts:
            code = part["category_code"]
            if code not in selected:
                continue
            semantics = {key: part[key] for key in SPLIT_CATEGORY_FIELDS}
            previous.append({**parent, **semantics, "id": part["id"], "category_code": code,
                "counterparty_name": parent["counterparty_name_raw"],
                "debit_amount": part["amount"] if before["direction"] == "outflow" else "0.00",
                "credit_amount": part["amount"] if before["direction"] == "inflow" else "0.00"})
        new_all_ids = {part["id"] for part in after["parts"]} or {after["transaction_id"]}
        old_rows = [row for row in current if row["id"] not in new_all_ids] + previous
        old_relations = TurnoverRelationService.from_snapshot(snapshot).rebuild_from_bank_rows(old_rows)
        new_ids = {row["id"] for row in current if row["id"] in new_all_ids}
        updated = TurnoverRelationService.from_snapshot(snapshot, bank_rows=current)
        try:
            migrated_manual = updated.replace_bank_split_members(old_ids=old_ids, new_ids=new_ids, actor_id=actor_id,
                whole_replacement=not before["parts"] or not after["parts"])
        except TurnoverRelationValidationError as exc:
            raise BankTransactionSplitError(exc.error_code, str(exc), status=409) from exc
        new_relations = updated.rebuild_from_bank_rows(current)
        affected_ids = [relation["relation_id"] for relation in old_relations
                        if old_ids.intersection(relation["bank_row_ids"])]
        target_ids = [relation["relation_id"] for relation in new_relations
                      if new_ids.intersection(relation["bank_row_ids"])]
        extras = self._tx.fetch_all("""select ledger_key,extra_payload from app.turnover_ledger_extras
            where ledger_key=any(%s::text[]) order by ledger_key for update""", (sorted(set(affected_ids + target_ids)),))
        extra_by_id = {row["ledger_key"]: row["extra_payload"] for row in extras}
        migrations = []
        for relation in old_relations:
            relation_id = relation["relation_id"]
            members = set(relation["bank_row_ids"])
            if relation_id not in extra_by_id or not members.intersection(old_ids):
                continue
            expected = TurnoverRelationService.split_replacement_members(members, old_ids, new_ids,
                whole_replacement=not before["parts"] or not after["parts"])
            candidates = [item for item in new_relations if set(item["bank_row_ids"]) == expected and item["status"] != "withdrawn"]
            if len(candidates) != 1:
                raise BankTransactionSplitError("turnover_split_extra_ambiguous", "拆分后往来补充信息无法唯一归属，请先处理该往来的补充信息。", status=409)
            target = candidates[0]["relation_id"]
            if target == relation_id:
                continue
            if target in extra_by_id:
                raise BankTransactionSplitError("turnover_split_extra_conflict", "拆分后的往来已存在补充信息，请先处理重复信息。", status=409)
            payload = {**deepcopy(extra_by_id[relation_id]), "relation_id": target, "updated_by": actor_id, "updated_at": datetime.now(UTC).isoformat()}
            self._tx.execute("""update app.turnover_ledger_extras set ledger_key=%s, extra_payload=%s,
                raw_payload=%s, updated_by=%s, updated_at=now() where ledger_key=%s""",
                (target, jsonb(payload), jsonb({"normalized_payload": payload}), actor_id, relation_id))
            event = {"relation_id": target, "action": "bank_split_extra_migrated", "actor": actor_id,
                "created_at": payload["updated_at"], "before": extra_by_id[relation_id], "after": payload}
            self._tx.execute("""insert into app.turnover_relation_events(relation_id,event_type,actor_id,payload,raw_payload)
                values (%s,'bank_split_extra_migrated',%s,%s,%s)""", (target,actor_id,jsonb(event),jsonb(event)))
            migrations.append({"before": relation_id, "after": target})
        for change in migrated_manual:
            owner.save_turnover_relation_change(relation=change["before"], audit_event=change["event"])
            owner.save_turnover_relation_change(relation=change["after"], audit_event=change["next_event"])
        return {"migrated_extras": migrations, "migrated_relations": [item["after"]["relation_id"] for item in migrated_manual]}
