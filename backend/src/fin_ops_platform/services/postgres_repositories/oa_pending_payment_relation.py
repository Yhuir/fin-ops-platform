from __future__ import annotations

from copy import deepcopy
from hashlib import sha1
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import (
    event_uuid,
    int_value,
    jsonb,
    month_start,
    row_payload,
    run_in_transaction,
    text,
    text_list,
)


class OaPendingPaymentRelationRepositoryError(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.payload = dict(payload or {})


class PostgresOaPendingPaymentRelationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def create_active_relation(
        self,
        *,
        oa_row_ids: list[str],
        bank_transaction_ids: list[str],
        actor_id: str,
        month_scope: str,
        note: str | None = None,
        amount_check: dict[str, Any] | None = None,
        source_action: str = "oa_pending_payment_relation",
        idempotency_key: str | None = None,
        relation_id: str | None = None,
        writeback_status: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_oa_ids = _dedupe_text(oa_row_ids)
        normalized_bank_ids = _dedupe_text(bank_transaction_ids)
        if not normalized_oa_ids:
            raise OaPendingPaymentRelationRepositoryError(
                "oa_row_ids_required",
                "At least one OA row is required.",
            )
        if not normalized_bank_ids:
            raise OaPendingPaymentRelationRepositoryError(
                "bank_transaction_ids_required",
                "At least one bank transaction is required.",
            )
        resolved_relation_id = text(relation_id) or _relation_id(normalized_oa_ids, normalized_bank_ids, idempotency_key)
        resolved_month = month_start(month_scope) or month_start((amount_check or {}).get("scope_month")) or None
        normalized_month_scope = (resolved_month or "all")[:7] if resolved_month else "all"
        actor = text(actor_id) or "system"
        payload = {
            "relation_id": resolved_relation_id,
            "status": "active",
            "month_scope": normalized_month_scope,
            "oa_row_ids": normalized_oa_ids,
            "bank_transaction_ids": normalized_bank_ids,
            "source_action": text(source_action) or "oa_pending_payment_relation",
            "note": text(note),
            "amount_check": deepcopy(amount_check or {}),
            "writeback_status": deepcopy(writeback_status or {}),
            **(deepcopy(raw_payload or {})),
        }

        def write(connection: Any) -> dict[str, Any]:
            existing = self._load_relation_by_id(connection, resolved_relation_id)
            if isinstance(existing, dict) and text(existing.get("status")) == "active":
                relation = _public_relation(existing)
                return {
                    "status": "confirmed",
                    "relation": relation,
                    "changed_relation_ids": [resolved_relation_id],
                    "affected_months": [normalized_month_scope] if normalized_month_scope else [],
                    "idempotent_replay": True,
                }

            self._assert_no_pending_oa_conflict(connection, normalized_oa_ids, resolved_relation_id)
            self._assert_no_workbench_bank_conflict(connection, normalized_bank_ids)
            self._assert_no_claim_conflict(connection, normalized_bank_ids, resolved_relation_id)
            row = connection.fetch_one(
                """
                insert into app.oa_pending_payment_bank_relations(
                    relation_id, status, version, scope_month, oa_row_ids, bank_transaction_ids,
                    source_action, note, amount_check, writeback_status, created_by, raw_payload
                )
                values (%s, 'active', 1, %s::date, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (relation_id) do update set
                    status = 'active',
                    version = app.oa_pending_payment_bank_relations.version + 1,
                    scope_month = excluded.scope_month,
                    oa_row_ids = excluded.oa_row_ids,
                    bank_transaction_ids = excluded.bank_transaction_ids,
                    source_action = excluded.source_action,
                    note = excluded.note,
                    amount_check = excluded.amount_check,
                    writeback_status = excluded.writeback_status,
                    raw_payload = excluded.raw_payload,
                    updated_at = now()
                returning
                    relation_id,
                    status,
                    version,
                    scope_month,
                    oa_row_ids,
                    bank_transaction_ids,
                    source_action,
                    note,
                    amount_check,
                    writeback_status,
                    migrated_from_workbench_case_id,
                    promoted_workbench_case_id,
                    created_by,
                    created_at,
                    updated_at,
                    raw_payload
                """,
                (
                    resolved_relation_id,
                    resolved_month,
                    normalized_oa_ids,
                    normalized_bank_ids,
                    payload["source_action"],
                    payload["note"],
                    jsonb(payload["amount_check"]),
                    jsonb(payload["writeback_status"]),
                    actor,
                    jsonb({"normalized_payload": payload}),
                ),
            )
            relation_payload = self._row_payload(row)
            self._replace_claims(
                connection,
                relation_id=resolved_relation_id,
                bank_transaction_ids=normalized_bank_ids,
                scope_month=resolved_month,
                actor_id=actor,
            )
            self._record_event(
                connection,
                relation_id=resolved_relation_id,
                event_type="create_active_relation",
                actor_id=actor,
                before_payload={},
                after_payload=relation_payload,
            )
            relation = _public_relation(relation_payload)
            return {
                "status": "confirmed",
                "relation": relation,
                "changed_relation_ids": [resolved_relation_id],
                "affected_months": [normalized_month_scope] if normalized_month_scope else [],
                "idempotent_replay": False,
            }

        return run_in_transaction(self._connection, write)

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        normalized_row_ids = _dedupe_text(row_ids)
        if not normalized_row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select
                relation_id,
                status,
                version,
                scope_month,
                oa_row_ids,
                bank_transaction_ids,
                source_action,
                note,
                amount_check,
                writeback_status,
                migrated_from_workbench_case_id,
                promoted_workbench_case_id,
                created_by,
                created_at,
                updated_at,
                raw_payload
            from app.oa_pending_payment_bank_relations
            where status = 'active'
              and (oa_row_ids && %s or bank_transaction_ids && %s)
            order by updated_at desc, relation_id
            """,
            (normalized_row_ids, normalized_row_ids),
        )
        return [_public_relation(self._row_payload(row)) for row in rows]

    def active_relation_status_by_bank_ids(self, bank_transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized_bank_ids = _dedupe_text(bank_transaction_ids)
        if not normalized_bank_ids:
            return {}
        rows = self._connection.fetch_all(
            """
            select
                relation_id,
                status,
                version,
                scope_month,
                oa_row_ids,
                bank_transaction_ids,
                source_action,
                note,
                amount_check,
                writeback_status,
                migrated_from_workbench_case_id,
                promoted_workbench_case_id,
                created_by,
                created_at,
                updated_at,
                raw_payload
            from app.oa_pending_payment_bank_relations
            where status = 'active'
              and bank_transaction_ids && %s
            order by updated_at desc, relation_id
            """,
            (normalized_bank_ids,),
        )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            relation = _public_relation(self._row_payload(row))
            for bank_id in text_list(relation.get("bank_transaction_ids")) + text_list(relation.get("bankTransactionIds")):
                if bank_id in normalized_bank_ids:
                    result[bank_id] = {
                        "status": "linked_in_progress",
                        "caseId": text(relation.get("case_id") or relation.get("relation_id")) or "",
                        "relationId": text(relation.get("relation_id") or relation.get("case_id")) or "",
                        "oaRowIds": text_list(relation.get("oa_row_ids")) or text_list(relation.get("oaRowIds")),
                    }
        return result

    def mark_relation_promoted(
        self,
        *,
        relation_id: str,
        workbench_case_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        resolved_relation_id = text(relation_id)
        resolved_case_id = text(workbench_case_id)
        if not resolved_relation_id:
            raise OaPendingPaymentRelationRepositoryError(
                "oa_pending_payment_relation_id_required",
                "Pending payment relation id is required.",
            )
        if not resolved_case_id:
            raise OaPendingPaymentRelationRepositoryError(
                "workbench_case_id_required",
                "Workbench case id is required for pending payment relation promotion.",
            )
        actor = text(actor_id) or "system"

        def write(connection: Any) -> dict[str, Any]:
            before = self._load_relation_by_id(connection, resolved_relation_id)
            if not before:
                raise OaPendingPaymentRelationRepositoryError(
                    "oa_pending_payment_relation_not_found",
                    "Pending payment relation was not found.",
                    payload={"relation_id": resolved_relation_id},
                )
            if text(before.get("status")) == "promoted":
                return {
                    "status": "promoted",
                    "relation": _public_relation(before),
                    "changed_relation_ids": [resolved_relation_id],
                    "affected_months": [text(before.get("month_scope"))] if text(before.get("month_scope")) else [],
                    "idempotent_replay": True,
                }
            if text(before.get("status")) != "active":
                raise OaPendingPaymentRelationRepositoryError(
                    "oa_pending_payment_relation_not_active",
                    "Pending payment relation is not active.",
                    payload={"relation_id": resolved_relation_id, "status": text(before.get("status"))},
                )
            row = connection.fetch_one(
                """
                update app.oa_pending_payment_bank_relations
                set status = 'promoted',
                    version = version + 1,
                    promoted_workbench_case_id = %s,
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        jsonb_set(
                            coalesce(raw_payload, '{}'::jsonb),
                            '{normalized_payload,status}',
                            to_jsonb('promoted'::text),
                            true
                        ),
                        '{normalized_payload,promoted_workbench_case_id}',
                        to_jsonb(%s::text),
                        true
                    )
                where relation_id = %s
                  and status = 'active'
                returning
                    relation_id,
                    status,
                    version,
                    scope_month,
                    oa_row_ids,
                    bank_transaction_ids,
                    source_action,
                    note,
                    amount_check,
                    writeback_status,
                    migrated_from_workbench_case_id,
                    promoted_workbench_case_id,
                    created_by,
                    created_at,
                    updated_at,
                    raw_payload
                """,
                (resolved_case_id, resolved_case_id, resolved_relation_id),
            )
            after = self._row_payload(row)
            if not after:
                after = self._load_relation_by_id(connection, resolved_relation_id) or before
            self._release_claims(
                connection,
                relation_id=resolved_relation_id,
                actor_id=actor,
                release_reason="promoted_to_workbench_relation",
            )
            self._record_event(
                connection,
                relation_id=resolved_relation_id,
                event_type="promote_to_workbench_relation",
                actor_id=actor,
                before_payload=before,
                after_payload=after,
            )
            return {
                "status": "promoted",
                "relation": _public_relation(after),
                "changed_relation_ids": [resolved_relation_id],
                "affected_months": [text(after.get("month_scope"))] if text(after.get("month_scope")) else [],
                "idempotent_replay": False,
            }

        return run_in_transaction(self._connection, write)

    def _load_relation_by_id(self, connection: Any, relation_id: str) -> dict[str, Any] | None:
        row = connection.fetch_one(
            """
            select
                relation_id,
                status,
                version,
                scope_month,
                oa_row_ids,
                bank_transaction_ids,
                source_action,
                note,
                amount_check,
                writeback_status,
                migrated_from_workbench_case_id,
                promoted_workbench_case_id,
                created_by,
                created_at,
                updated_at,
                raw_payload
            from app.oa_pending_payment_bank_relations
            where relation_id = %s
            """,
            (relation_id,),
        )
        return self._row_payload(row) if row else None

    def _assert_no_pending_oa_conflict(self, connection: Any, oa_row_ids: list[str], relation_id: str) -> None:
        rows = connection.fetch_all(
            """
            select relation_id, oa_row_ids
            from app.oa_pending_payment_bank_relations
            where status = 'active'
              and relation_id <> %s
              and oa_row_ids && %s
            order by relation_id
            """,
            (relation_id, oa_row_ids),
        )
        if rows:
            raise OaPendingPaymentRelationRepositoryError(
                "oa_pending_payment_relation_active_oa_conflict",
                "One or more OA rows already have an active pending payment relation.",
                payload={
                    "conflicting_relation_ids": [text(row.get("relation_id")) or "" for row in rows],
                    "oa_row_ids": oa_row_ids,
                },
            )

    def _assert_no_workbench_bank_conflict(self, connection: Any, bank_transaction_ids: list[str]) -> None:
        rows = connection.fetch_all(
            """
            select case_id, row_ids
            from app.workbench_pair_relations
            where status = 'active'
              and row_ids && %s
            order by case_id
            """,
            (bank_transaction_ids,),
        )
        if rows:
            raise OaPendingPaymentRelationRepositoryError(
                "bank_transaction_active_workbench_relation_conflict",
                "One or more bank transactions are already active in a Workbench relation.",
                payload={
                    "conflicting_case_ids": [text(row.get("case_id")) or "" for row in rows],
                    "bank_transaction_ids": bank_transaction_ids,
                },
            )

    def _assert_no_claim_conflict(self, connection: Any, bank_transaction_ids: list[str], relation_id: str) -> None:
        rows = connection.fetch_all(
            """
            select bank_transaction_id, owner_type, owner_id
            from app.bank_transaction_relation_claims
            where status = 'active'
              and bank_transaction_id = any(%s)
              and not (owner_type = 'oa_pending_payment_relation' and owner_id = %s)
            order by bank_transaction_id, owner_type, owner_id
            """,
            (bank_transaction_ids, relation_id),
        )
        if rows:
            raise OaPendingPaymentRelationRepositoryError(
                "bank_transaction_active_relation_claim_conflict",
                "One or more bank transactions are already claimed by another relation.",
                payload={
                    "conflicts": [
                        {
                            "bank_transaction_id": text(row.get("bank_transaction_id")) or "",
                            "owner_type": text(row.get("owner_type")) or "",
                            "owner_id": text(row.get("owner_id")) or "",
                        }
                        for row in rows
                    ],
                    "bank_transaction_ids": bank_transaction_ids,
                },
            )

    def _replace_claims(
        self,
        connection: Any,
        *,
        relation_id: str,
        bank_transaction_ids: list[str],
        scope_month: str | None,
        actor_id: str,
    ) -> None:
        connection.execute(
            """
            update app.bank_transaction_relation_claims
            set status = 'released',
                released_by = %s,
                released_at = now(),
                release_reason = 'replace_pending_payment_relation_claims',
                updated_at = now()
            where owner_type = 'oa_pending_payment_relation'
              and owner_id = %s
              and status = 'active'
              and not (bank_transaction_id = any(%s))
            """,
            (actor_id, relation_id, bank_transaction_ids),
        )
        for bank_id in bank_transaction_ids:
            connection.execute(
                """
                insert into app.bank_transaction_relation_claims(
                    bank_transaction_id, owner_type, owner_id, status, scope_month,
                    created_by, raw_payload
                )
                values (%s, 'oa_pending_payment_relation', %s, 'active', %s::date, %s, %s)
                on conflict (bank_transaction_id) where status = 'active'
                do update set
                    owner_type = excluded.owner_type,
                    owner_id = excluded.owner_id,
                    scope_month = excluded.scope_month,
                    raw_payload = excluded.raw_payload,
                    updated_at = now()
                where app.bank_transaction_relation_claims.owner_type = 'oa_pending_payment_relation'
                  and app.bank_transaction_relation_claims.owner_id = %s
                """,
                (
                    bank_id,
                    relation_id,
                    scope_month,
                    actor_id,
                    jsonb(
                        {
                            "normalized_payload": {
                                "bank_transaction_id": bank_id,
                                "owner_type": "oa_pending_payment_relation",
                                "owner_id": relation_id,
                                "status": "active",
                            }
                        }
                    ),
                    relation_id,
                ),
            )
        rows = connection.fetch_all(
            """
            select bank_transaction_id, owner_type, owner_id
            from app.bank_transaction_relation_claims
            where status = 'active'
              and bank_transaction_id = any(%s)
            order by bank_transaction_id
            """,
            (bank_transaction_ids,),
        )
        conflicts = [
            row
            for row in rows
            if text(row.get("owner_type")) != "oa_pending_payment_relation"
            or text(row.get("owner_id")) != relation_id
        ]
        claimed_ids = {text(row.get("bank_transaction_id")) for row in rows if text(row.get("bank_transaction_id"))}
        missing_ids = [bank_id for bank_id in bank_transaction_ids if bank_id not in claimed_ids]
        if conflicts or missing_ids:
            raise OaPendingPaymentRelationRepositoryError(
                "bank_transaction_active_relation_claim_conflict",
                "One or more bank transactions could not be claimed by the pending payment relation.",
                payload={
                    "conflicts": [
                        {
                            "bank_transaction_id": text(row.get("bank_transaction_id")) or "",
                            "owner_type": text(row.get("owner_type")) or "",
                            "owner_id": text(row.get("owner_id")) or "",
                        }
                        for row in conflicts
                    ],
                    "missing_bank_transaction_ids": missing_ids,
                },
            )

    def _release_claims(
        self,
        connection: Any,
        *,
        relation_id: str,
        actor_id: str,
        release_reason: str,
    ) -> None:
        connection.execute(
            """
            update app.bank_transaction_relation_claims
            set status = 'released',
                released_by = %s,
                released_at = now(),
                release_reason = %s,
                updated_at = now()
            where owner_type = 'oa_pending_payment_relation'
              and owner_id = %s
              and status = 'active'
            """,
            (actor_id, release_reason, relation_id),
        )

    def _record_event(
        self,
        connection: Any,
        *,
        relation_id: str,
        event_type: str,
        actor_id: str,
        before_payload: dict[str, Any],
        after_payload: dict[str, Any],
    ) -> None:
        event_payload = {
            "relation_id": relation_id,
            "event_type": event_type,
            "actor_id": actor_id,
            "before_payload": before_payload,
            "after_payload": after_payload,
        }
        connection.execute(
            """
            insert into app.oa_pending_payment_bank_relation_events(
                id, relation_id, event_type, actor_id, before_payload, after_payload, raw_payload
            )
            values (%s::uuid, %s, %s, %s, %s, %s, %s)
            on conflict (id) do nothing
            """,
            (
                event_uuid("oa_pending_payment_bank_relation_events", relation_id, event_payload),
                relation_id,
                event_type,
                actor_id,
                jsonb(before_payload),
                jsonb(after_payload),
                jsonb({"normalized_payload": event_payload}),
            ),
        )

    @staticmethod
    def _row_payload(row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        payload = row_payload(row, "raw_payload")
        base = dict(payload if isinstance(payload, dict) else {})
        relation_id = text(row.get("relation_id") or base.get("relation_id")) or ""
        scope_month = month_start(row.get("scope_month")) or month_start(base.get("month_scope"))
        return {
            **base,
            "relation_id": relation_id,
            "status": text(row.get("status") or base.get("status")) or "active",
            "version": int_value(row.get("version") or base.get("version"), 1),
            "month_scope": scope_month[:7] if scope_month else text(base.get("month_scope")) or "all",
            "oa_row_ids": text_list(row.get("oa_row_ids") or base.get("oa_row_ids")),
            "bank_transaction_ids": text_list(row.get("bank_transaction_ids") or base.get("bank_transaction_ids")),
            "source_action": text(row.get("source_action") or base.get("source_action")) or "",
            "note": text(row.get("note") or base.get("note")),
            "amount_check": row.get("amount_check") if isinstance(row.get("amount_check"), dict) else base.get("amount_check") or {},
            "writeback_status": row.get("writeback_status") if isinstance(row.get("writeback_status"), dict) else base.get("writeback_status") or {},
            "migrated_from_workbench_case_id": text(row.get("migrated_from_workbench_case_id") or base.get("migrated_from_workbench_case_id")),
            "promoted_workbench_case_id": text(row.get("promoted_workbench_case_id") or base.get("promoted_workbench_case_id")),
            "created_by": text(row.get("created_by") or base.get("created_by")),
            "created_at": str(row.get("created_at") or base.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or base.get("updated_at") or ""),
        }


def _public_relation(payload: dict[str, Any]) -> dict[str, Any]:
    relation_id = text(payload.get("relation_id")) or ""
    oa_ids = text_list(payload.get("oa_row_ids"))
    bank_ids = text_list(payload.get("bank_transaction_ids"))
    amount_check = payload.get("amount_check") if isinstance(payload.get("amount_check"), dict) else {}
    source_action = text(payload.get("source_action")) or "oa_pending_payment_relation"
    return {
        "case_id": relation_id,
        "caseId": relation_id,
        "relation_id": relation_id,
        "relationId": relation_id,
        "status": text(payload.get("status")) or "active",
        "version": int_value(payload.get("version"), 1),
        "relation_mode": "oa_pending_payment_in_progress",
        "relationMode": "oa_pending_payment_in_progress",
        "relation_source": "oa_pending_payment_bank_relations",
        "relationSource": "oa_pending_payment_bank_relations",
        "month_scope": text(payload.get("month_scope")) or "all",
        "monthScope": text(payload.get("month_scope")) or "all",
        "row_ids": [*oa_ids, *bank_ids],
        "rowIds": [*oa_ids, *bank_ids],
        "row_types": [*(["oa"] * len(oa_ids)), *(["bank"] * len(bank_ids))],
        "rowTypes": [*(["oa"] * len(oa_ids)), *(["bank"] * len(bank_ids))],
        "oa_row_ids": oa_ids,
        "oaRowIds": oa_ids,
        "bank_transaction_ids": bank_ids,
        "bankTransactionIds": bank_ids,
        "note": text(payload.get("note")),
        "amount_check": deepcopy(amount_check),
        "amountCheck": deepcopy(amount_check),
        "special_metadata": {
            "origin": "oa_pending_payment_in_progress",
            "source": "oa_pending_payment_bank_relations",
            "source_action": source_action,
        },
        "specialMetadata": {
            "origin": "oa_pending_payment_in_progress",
            "source": "oa_pending_payment_bank_relations",
            "sourceAction": source_action,
        },
        "source_action": source_action,
        "sourceAction": source_action,
        "migrated_from_workbench_case_id": text(payload.get("migrated_from_workbench_case_id")),
        "promoted_workbench_case_id": text(payload.get("promoted_workbench_case_id")),
        "created_by": text(payload.get("created_by")),
        "created_at": text(payload.get("created_at")) or "",
        "updated_at": text(payload.get("updated_at")) or "",
    }


class SnapshotOaPendingPaymentRelationRepository:
    def __init__(self, *, load_snapshot: Any, save_snapshot: Any) -> None:
        self._load_snapshot = load_snapshot
        self._save_snapshot = save_snapshot

    def create_active_relation(
        self,
        *,
        oa_row_ids: list[str],
        bank_transaction_ids: list[str],
        actor_id: str,
        month_scope: str,
        note: str | None = None,
        amount_check: dict[str, Any] | None = None,
        source_action: str = "oa_pending_payment_relation",
        idempotency_key: str | None = None,
        relation_id: str | None = None,
        writeback_status: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_oa_ids = _dedupe_text(oa_row_ids)
        normalized_bank_ids = _dedupe_text(bank_transaction_ids)
        if not normalized_oa_ids:
            raise OaPendingPaymentRelationRepositoryError("oa_row_ids_required", "At least one OA row is required.")
        if not normalized_bank_ids:
            raise OaPendingPaymentRelationRepositoryError(
                "bank_transaction_ids_required",
                "At least one bank transaction is required.",
            )
        resolved_relation_id = text(relation_id) or _relation_id(normalized_oa_ids, normalized_bank_ids, idempotency_key)
        snapshot = self._normalized_snapshot()
        relations = snapshot.setdefault("relations", {})
        claims = snapshot.setdefault("claims", {})
        existing = relations.get(resolved_relation_id)
        if isinstance(existing, dict) and text(existing.get("status")) == "active":
            return {
                "status": "confirmed",
                "relation": _public_relation(existing),
                "changed_relation_ids": [resolved_relation_id],
                "affected_months": [text(existing.get("month_scope")) or "all"],
                "idempotent_replay": True,
            }
        oa_conflicts = [
            relation_id
            for relation_id, relation in relations.items()
            if isinstance(relation, dict)
            and text(relation.get("status")) == "active"
            and relation_id != resolved_relation_id
            and set(text_list(relation.get("oa_row_ids"))) & set(normalized_oa_ids)
        ]
        if oa_conflicts:
            raise OaPendingPaymentRelationRepositoryError(
                "oa_pending_payment_relation_active_oa_conflict",
                "One or more OA rows already have an active pending payment relation.",
                payload={"conflicting_relation_ids": oa_conflicts, "oa_row_ids": normalized_oa_ids},
            )
        claim_conflicts = [
            {
                "bank_transaction_id": bank_id,
                "owner_type": text((claim := claims.get(bank_id) or {}).get("owner_type")) or "",
                "owner_id": text(claim.get("owner_id")) or "",
            }
            for bank_id in normalized_bank_ids
            if isinstance(claim := claims.get(bank_id), dict)
            and text(claim.get("status")) == "active"
            and not (
                text(claim.get("owner_type")) == "oa_pending_payment_relation"
                and text(claim.get("owner_id")) == resolved_relation_id
            )
        ]
        if claim_conflicts:
            raise OaPendingPaymentRelationRepositoryError(
                "bank_transaction_active_relation_claim_conflict",
                "One or more bank transactions are already claimed by another relation.",
                payload={"conflicts": claim_conflicts, "bank_transaction_ids": normalized_bank_ids},
            )
        normalized_month = (month_start(month_scope) or "")[:7] or text(month_scope) or "all"
        relation_payload = {
            **(deepcopy(raw_payload or {})),
            "relation_id": resolved_relation_id,
            "status": "active",
            "version": int_value((existing or {}).get("version") if isinstance(existing, dict) else None, 0) + 1,
            "month_scope": normalized_month,
            "oa_row_ids": normalized_oa_ids,
            "bank_transaction_ids": normalized_bank_ids,
            "source_action": text(source_action) or "oa_pending_payment_relation",
            "note": text(note),
            "amount_check": deepcopy(amount_check or {}),
            "writeback_status": deepcopy(writeback_status or {}),
            "created_by": text(actor_id) or "system",
        }
        relations[resolved_relation_id] = relation_payload
        for bank_id, claim in list(claims.items()):
            if isinstance(claim, dict) and text(claim.get("owner_id")) == resolved_relation_id and bank_id not in normalized_bank_ids:
                claim["status"] = "released"
        for bank_id in normalized_bank_ids:
            claims[bank_id] = {
                "bank_transaction_id": bank_id,
                "owner_type": "oa_pending_payment_relation",
                "owner_id": resolved_relation_id,
                "status": "active",
                "scope_month": normalized_month,
            }
        self._save_snapshot(deepcopy(snapshot))
        return {
            "status": "confirmed",
            "relation": _public_relation(relation_payload),
            "changed_relation_ids": [resolved_relation_id],
            "affected_months": [normalized_month],
            "idempotent_replay": False,
        }

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        normalized_row_ids = set(_dedupe_text(row_ids))
        if not normalized_row_ids:
            return []
        relations = self._normalized_snapshot().get("relations", {})
        return [
            _public_relation(relation)
            for relation in relations.values()
            if isinstance(relation, dict)
            and text(relation.get("status")) == "active"
            and (
                set(text_list(relation.get("oa_row_ids"))) & normalized_row_ids
                or set(text_list(relation.get("bank_transaction_ids"))) & normalized_row_ids
            )
        ]

    def active_relation_status_by_bank_ids(self, bank_transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized_bank_ids = _dedupe_text(bank_transaction_ids)
        if not normalized_bank_ids:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for relation in self.active_relations_for_row_ids(normalized_bank_ids):
            for bank_id in text_list(relation.get("bank_transaction_ids")) or text_list(relation.get("bankTransactionIds")):
                if bank_id in normalized_bank_ids:
                    result[bank_id] = {
                        "status": "linked_in_progress",
                        "caseId": text(relation.get("case_id") or relation.get("relation_id")) or "",
                        "relationId": text(relation.get("relation_id") or relation.get("case_id")) or "",
                        "oaRowIds": text_list(relation.get("oa_row_ids")) or text_list(relation.get("oaRowIds")),
                    }
        return result

    def mark_relation_promoted(
        self,
        *,
        relation_id: str,
        workbench_case_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        resolved_relation_id = text(relation_id)
        resolved_case_id = text(workbench_case_id)
        if not resolved_relation_id:
            raise OaPendingPaymentRelationRepositoryError(
                "oa_pending_payment_relation_id_required",
                "Pending payment relation id is required.",
            )
        if not resolved_case_id:
            raise OaPendingPaymentRelationRepositoryError(
                "workbench_case_id_required",
                "Workbench case id is required for pending payment relation promotion.",
            )
        snapshot = self._normalized_snapshot()
        relations = snapshot.setdefault("relations", {})
        claims = snapshot.setdefault("claims", {})
        relation = relations.get(resolved_relation_id)
        if not isinstance(relation, dict):
            raise OaPendingPaymentRelationRepositoryError(
                "oa_pending_payment_relation_not_found",
                "Pending payment relation was not found.",
                payload={"relation_id": resolved_relation_id},
            )
        if text(relation.get("status")) == "promoted":
            return {
                "status": "promoted",
                "relation": _public_relation(relation),
                "changed_relation_ids": [resolved_relation_id],
                "affected_months": [text(relation.get("month_scope"))] if text(relation.get("month_scope")) else [],
                "idempotent_replay": True,
            }
        if text(relation.get("status")) != "active":
            raise OaPendingPaymentRelationRepositoryError(
                "oa_pending_payment_relation_not_active",
                "Pending payment relation is not active.",
                payload={"relation_id": resolved_relation_id, "status": text(relation.get("status"))},
            )
        promoted = {
            **deepcopy(relation),
            "status": "promoted",
            "version": int_value(relation.get("version"), 1) + 1,
            "promoted_workbench_case_id": resolved_case_id,
            "updated_by": text(actor_id) or "system",
        }
        relations[resolved_relation_id] = promoted
        for claim in claims.values():
            if (
                isinstance(claim, dict)
                and text(claim.get("owner_type")) == "oa_pending_payment_relation"
                and text(claim.get("owner_id")) == resolved_relation_id
                and text(claim.get("status")) == "active"
            ):
                claim["status"] = "released"
                claim["release_reason"] = "promoted_to_workbench_relation"
                claim["released_by"] = text(actor_id) or "system"
        self._save_snapshot(deepcopy(snapshot))
        return {
            "status": "promoted",
            "relation": _public_relation(promoted),
            "changed_relation_ids": [resolved_relation_id],
            "affected_months": [text(promoted.get("month_scope"))] if text(promoted.get("month_scope")) else [],
            "idempotent_replay": False,
        }

    def _normalized_snapshot(self) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        if not isinstance(snapshot, dict):
            return {"relations": {}, "claims": {}}
        relations = snapshot.get("relations")
        claims = snapshot.get("claims")
        return {
            **snapshot,
            "relations": dict(relations) if isinstance(relations, dict) else {},
            "claims": dict(claims) if isinstance(claims, dict) else {},
        }


def _dedupe_text(values: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    result: list[str] = []
    for item in list(values or []):
        normalized = text(item)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _relation_id(oa_row_ids: list[str], bank_transaction_ids: list[str], idempotency_key: str | None) -> str:
    seed = "|".join(
        [
            text(idempotency_key) or "",
            ",".join(sorted(oa_row_ids)),
            ",".join(sorted(bank_transaction_ids)),
        ]
    )
    return f"oa-pending-{sha1(seed.encode('utf-8')).hexdigest()[:20]}"
