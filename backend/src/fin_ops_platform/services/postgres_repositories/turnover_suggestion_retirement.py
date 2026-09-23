from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import jsonb


class PostgresTurnoverSuggestionRetirementRepository:
    """Retire stored system suggestions invalidated by a completed bank split."""

    def __init__(self, transaction: Any) -> None:
        self._transaction = transaction

    def run(self, *, apply: bool, actor_id: str = "") -> dict[str, Any]:
        if apply and not actor_id.strip():
            raise ValueError("Retiring suggestions requires an operator.")
        candidates = self._transaction.fetch_all(
            """SELECT relation.relation_id, relation.version,
                      obsolete.parent_ids
               FROM app.turnover_relations relation
               JOIN LATERAL (
                   SELECT array_agg(DISTINCT member.row_id ORDER BY member.row_id) AS parent_ids
                   FROM jsonb_array_elements_text(
                       CASE WHEN jsonb_typeof(relation.raw_payload->'normalized_payload'->'bank_row_ids')='array'
                            THEN relation.raw_payload->'normalized_payload'->'bank_row_ids'
                            ELSE '[]'::jsonb END
                   ) member(row_id)
                   JOIN app.bank_transactions parent
                     ON (parent.id::text=member.row_id OR parent.legacy_mongo_id=member.row_id)
                    AND parent.status <> 'deleted'
                   JOIN app.bank_transaction_split_sets split ON split.bank_transaction_id=parent.id
                   WHERE (SELECT count(*) >= 2 AND sum(item.amount)=parent.amount
                          FROM app.bank_transaction_split_items item
                          WHERE item.bank_transaction_id=parent.id)
                     AND NOT EXISTS (
                         SELECT 1 FROM app.bank_transaction_units unit
                         WHERE unit.id::text=member.row_id OR unit.legacy_mongo_id=member.row_id
                     )
               ) obsolete ON cardinality(obsolete.parent_ids)>0
               WHERE relation.status='suggested'
                 AND relation.raw_payload->'normalized_payload'->>'status'='suggested'
                 AND relation.raw_payload->'normalized_payload'->>'source'='system'
                 AND NOT EXISTS (SELECT 1 FROM app.turnover_ledger_extras extra
                                 WHERE extra.ledger_key=relation.relation_id)
                 AND NOT EXISTS (SELECT 1 FROM app.turnover_relation_events event
                                 WHERE event.turnover_relation_id=relation.id)
               ORDER BY relation.relation_id
            """ + (" FOR UPDATE OF relation" if apply else ""),
        )
        retired = []
        if apply:
            for row in candidates:
                removed = self._transaction.fetch_one(
                    """DELETE FROM app.turnover_relations
                       WHERE relation_id=%s AND version=%s AND status='suggested'
                       RETURNING to_jsonb(turnover_relations) AS fact""",
                    (row["relation_id"], row["version"]),
                )
                if removed is None:
                    raise RuntimeError("Turnover suggestion changed during retirement.")
                event = {"relation_id": row["relation_id"], "action": "obsolete_split_suggestion_retired",
                         "actor": actor_id, "obsolete_parent_ids": row["parent_ids"],
                         "before": removed["fact"], "after": {"retired": True, "relation_id": row["relation_id"]}}
                self._transaction.execute(
                    """INSERT INTO audit.events(event_type,object_type,object_id,actor_id,payload,raw_payload)
                       VALUES ('turnover_obsolete_split_suggestion_retired','turnover_relation',%s,%s,%s,%s)""",
                    (row["relation_id"], actor_id, jsonb(event), jsonb({"normalized_payload": event})),
                )
                retired.append(row["relation_id"])
        return {"mode": "apply" if apply else "preview", "affected_count": len(candidates),
                "candidates": [{"relation_id": row["relation_id"], "version": row["version"],
                                "obsolete_parent_ids": row["parent_ids"]} for row in candidates],
                "retired_relation_ids": retired}
