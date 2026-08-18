from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryValidationError,
)
from fin_ops_platform.services.postgres_repositories.common import (
    event_uuid,
    int_value,
    jsonb,
    row_payload,
    text,
    text_list,
)
from fin_ops_platform.services.postgres_snapshot_contracts import normalize_bank_transaction_categories


class PostgresBankTransactionCategoryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def turnover_bank_row_selection_proofs(
        self,
        transaction_ids: list[str],
        *,
        transaction: Any | None = None,
        tenant_id: str = "default",
    ) -> dict[str, dict[str, object]]:
        normalized_ids = list(
            dict.fromkeys(
                str(transaction_id or "").strip()
                for transaction_id in list(transaction_ids or [])
                if str(transaction_id or "").strip()
            )
        )
        if not normalized_ids:
            return {}
        rows = (transaction or self._connection).fetch_all(
            """
            select
                b.id::text as canonical_transaction_id,
                coalesce(b.legacy_mongo_id, b.id::text) as transaction_id,
                b.updated_at::text as bank_transaction_updated_at,
                coalesce(confirmation.category_code, manual.category) as category_code,
                case
                    when confirmation.id is not null then 'auto_confirmation'
                    else coalesce(manual.source, '')
                end as category_source,
                coalesce(confirmation.version, manual.version, 0)::integer as category_version
            from app.bank_transactions b
            left join lateral (
                select c.id, c.category, c.source, c.version
                from app.bank_transaction_categories c
                where c.status = 'active'
                  and (
                    c.bank_transaction_id = b.id
                    or c.legacy_transaction_id in (coalesce(b.legacy_mongo_id, b.id::text), b.id::text)
                  )
                order by c.updated_at desc, c.id desc
                limit 1
            ) manual on true
            left join lateral (
                select c.id, c.category_code, c.version
                from app.bank_transaction_category_confirmations c
                where c.tenant_id = %s
                  and c.status = 'active'
                  and (
                    c.bank_transaction_id = b.id
                    or c.legacy_transaction_id in (coalesce(b.legacy_mongo_id, b.id::text), b.id::text)
                  )
                order by c.confirmed_at desc, c.id desc
                limit 1
            ) confirmation on true
            where b.status <> 'deleted'
              and (b.id::text = any(%s::text[]) or b.legacy_mongo_id = any(%s::text[]))
            order by b.created_at, b.id
            for share of b
            """,
            (tenant_id, normalized_ids, normalized_ids),
        )
        proofs: dict[str, dict[str, object]] = {}
        for row in rows:
            proof = {
                "transaction_id": text(row.get("transaction_id")) or "",
                "canonical_transaction_id": text(row.get("canonical_transaction_id")) or "",
                "bank_transaction_updated_at": text(row.get("bank_transaction_updated_at")) or "",
                "category_code": text(row.get("category_code")) or "",
                "category_source": text(row.get("category_source")) or "",
                "category_version": int_value(row.get("category_version"), 0),
            }
            for identity in (proof["transaction_id"], proof["canonical_transaction_id"]):
                if identity:
                    proofs[str(identity)] = proof
        return proofs

    def load_snapshot(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            """
            select
                coalesce(
                    bank.legacy_mongo_id,
                    category.legacy_transaction_id,
                    category.bank_transaction_id::text
                ) as key,
                category.raw_payload
            from app.bank_transaction_categories category
            left join app.bank_transactions bank
              on bank.id = category.bank_transaction_id
            where category.status = 'active'
            order by key
            """
        )
        event_rows = self._connection.fetch_all(
            "select raw_payload from app.bank_transaction_category_events order by occurred_at"
        )
        confirmation_rows = self._connection.fetch_all(
            """
            select
                coalesce(
                    bank.legacy_mongo_id,
                    confirmation.legacy_transaction_id,
                    confirmation.bank_transaction_id::text
                ) as key,
                confirmation.category_code,
                confirmation.candidate_category_codes,
                confirmation.rule_version,
                confirmation.version,
                confirmation.confirmed_by,
                confirmation.confirmed_at,
                confirmation.raw_payload
            from app.bank_transaction_category_confirmations confirmation
            left join app.bank_transactions bank
              on bank.id = confirmation.bank_transaction_id
            where confirmation.status = 'active'
            order by key
            """
        )
        confirmation_audit_rows = self._connection.fetch_all(
            "select raw_payload from app.bank_transaction_category_confirmations order by confirmed_at, id"
        )
        categories = {str(row.get("key")): row_payload(row, "raw_payload") for row in rows}
        for row in confirmation_rows:
            transaction_id = text(row.get("key"))
            category_code = text(row.get("category_code"))
            if not transaction_id or not category_code:
                continue
            payload = row_payload(row, "raw_payload")
            normalized_payload = dict(payload) if isinstance(payload, dict) else {}
            normalized_payload.update(
                {
                    "transaction_id": transaction_id,
                    "category_code": category_code,
                    "source": "auto_confirmation",
                    "updated_by": text(row.get("confirmed_by")) or normalized_payload.get("updated_by") or "",
                    "updated_at": (
                        row.get("confirmed_at").isoformat()
                        if hasattr(row.get("confirmed_at"), "isoformat")
                        else text(row.get("confirmed_at")) or normalized_payload.get("updated_at") or ""
                    ),
                    "version": int_value(row.get("version"), int_value(normalized_payload.get("version"), 1)),
                    "candidate_category_codes": text_list(
                        row.get("candidate_category_codes") or normalized_payload.get("candidate_category_codes")
                    ),
                    "rule_version": text(row.get("rule_version")) or normalized_payload.get("rule_version") or "",
                }
            )
            categories[transaction_id] = normalized_payload
        return normalize_bank_transaction_categories(
            categories,
            [
                payload
                for source_rows in (event_rows, confirmation_audit_rows)
                for row in source_rows
                if isinstance((payload := row_payload(row, "raw_payload")), dict)
            ],
        )

    def inspect_unknown_manual_clear_candidates(self, *, reader: Any | None = None) -> dict[str, object]:
        active_reader = reader or self._connection
        rows = active_reader.fetch_all(
            """
            select c.id::text as category_id,
                   coalesce(b.legacy_mongo_id, b.id::text, c.legacy_transaction_id) as transaction_id,
                   b.id::text as bank_transaction_id,
                   to_char(coalesce(b.txn_month, date_trunc('month', b.txn_date)), 'YYYY-MM') as scope_month,
                   c.version,
                   c.updated_at,
                   c.raw_payload,
                   exists (
                       select 1
                       from app.bank_transaction_category_events e
                       where e.category_id = c.id
                         and (
                             (
                                 e.payload @> '{"source":"manual","manual_assignment":true}'::jsonb
                                 and e.payload->'category_code' = 'null'::jsonb
                                 and nullif(e.payload->>'previous_category_code', '') is not null
                             )
                             or (
                                 e.raw_payload->'normalized_payload'
                                     @> '{"source":"manual","manual_assignment":true}'::jsonb
                                 and e.raw_payload->'normalized_payload'->'category_code' = 'null'::jsonb
                                 and nullif(
                                     e.raw_payload->'normalized_payload'->>'previous_category_code',
                                     ''
                                 ) is not null
                             )
                         )
                   ) as clear_event_evidence
            from app.bank_transaction_categories c
            left join app.bank_transactions b
              on b.id = c.bank_transaction_id
              or (c.bank_transaction_id is null and b.legacy_mongo_id = c.legacy_transaction_id)
            where c.status = 'active'
              and lower(c.category) = 'unknown'
              and c.source = 'manual'
            order by c.updated_at, c.id
            """
        )
        strict_candidates: list[dict[str, object]] = []
        manual_review_candidates: list[dict[str, object]] = []
        for row in rows:
            raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
            normalized = (
                raw_payload.get("normalized_payload")
                if isinstance(raw_payload.get("normalized_payload"), dict)
                else raw_payload
            )
            candidate = {
                "category_id": text(row.get("category_id")) or "",
                "transaction_id": text(row.get("transaction_id")) or "",
                "bank_transaction_id": text(row.get("bank_transaction_id")) or "",
                "scope_month": text(row.get("scope_month")) or "",
                "version": int_value(row.get("version"), 1),
                "updated_at": str(row.get("updated_at") or ""),
                "manual_assignment_evidence": bool(normalized.get("manual_assignment")),
                "clear_event_evidence": bool(row.get("clear_event_evidence")),
            }
            if (
                candidate["transaction_id"]
                and candidate["bank_transaction_id"]
                and len(str(candidate["scope_month"])) == 7
                and candidate["manual_assignment_evidence"]
                and candidate["clear_event_evidence"]
            ):
                strict_candidates.append(candidate)
            else:
                manual_review_candidates.append(candidate)
        return {
            "strict_candidates": strict_candidates,
            "manual_review_candidates": manual_review_candidates,
        }

    def apply_mutation(
        self,
        *,
        transaction: Any,
        transaction_id: str,
        mutation_type: str,
        record: dict[str, Any],
        actor_id: str,
        action: str,
        metadata: dict[str, object],
    ) -> dict[str, object]:
        target = transaction.fetch_one(
            """
            select id::text as bank_transaction_id,
                   coalesce(legacy_mongo_id, id::text) as public_transaction_id,
                   to_char(coalesce(txn_month, date_trunc('month', txn_date)), 'YYYY-MM') as scope_month
            from app.bank_transactions
            where status <> 'deleted'
              and (id::text = %s or legacy_mongo_id = %s)
            limit 1
            for update
            """,
            (transaction_id, transaction_id),
        )
        if not isinstance(target, dict):
            raise BankTransactionCategoryValidationError(
                "unknown_transaction_id",
                f"Unknown bank transaction id: {transaction_id}",
                transaction_id=transaction_id,
            )
        bank_transaction_id = str(target["bank_transaction_id"])
        public_transaction_id = str(target["public_transaction_id"])
        scope_month = str(target.get("scope_month") or "").strip()
        if len(scope_month) != 7:
            raise RuntimeError("Bank transaction category mutation requires a transaction month.")

        if mutation_type == "confirmation_confirm":
            change = self._confirm(
                transaction,
                bank_transaction_id=bank_transaction_id,
                public_transaction_id=public_transaction_id,
                record=record,
                actor_id=actor_id,
            )
        elif mutation_type == "confirmation_revoke":
            change = self._revoke_confirmation(
                transaction,
                bank_transaction_id=bank_transaction_id,
                public_transaction_id=public_transaction_id,
                actor_id=actor_id,
                record=record,
            )
        elif mutation_type == "manual_assign":
            change = self._assign_manual(
                transaction,
                bank_transaction_id=bank_transaction_id,
                public_transaction_id=public_transaction_id,
                record=record,
                actor_id=actor_id,
            )
        elif mutation_type == "manual_clear":
            change = self._clear_manual(
                transaction,
                bank_transaction_id=bank_transaction_id,
                public_transaction_id=public_transaction_id,
                actor_id=actor_id,
                record=record,
            )
        elif mutation_type == "turnover_update":
            change = self._assign_turnover(
                transaction,
                bank_transaction_id=bank_transaction_id,
                public_transaction_id=public_transaction_id,
                record=record,
                actor_id=actor_id,
            )
        else:
            raise ValueError(f"Unsupported bank transaction category mutation: {mutation_type}")

        if bool(change.get("changed")):
            audit_payload = {
                "transaction_id": public_transaction_id,
                "bank_transaction_id": bank_transaction_id,
                "action": action,
                "mutation_type": mutation_type,
                "version": change.get("version"),
                "affected_months": [scope_month],
                **dict(metadata),
            }
            transaction.execute(
                """
                insert into audit.events(
                    event_type, object_type, object_id, actor_id, scope, payload, raw_payload
                ) values (%s, 'bank_transaction_category', %s, %s, %s, %s, %s)
                """,
                (
                    action,
                    public_transaction_id,
                    actor_id,
                    scope_month,
                    jsonb(audit_payload),
                    jsonb({"normalized_payload": audit_payload}),
                ),
            )
        return {
            **change,
            "transaction_id": public_transaction_id,
            "bank_transaction_id": bank_transaction_id,
            "affected_months": [scope_month],
        }

    @staticmethod
    def _active_manual(transaction: Any, *, bank_transaction_id: str, public_transaction_id: str) -> dict[str, Any] | None:
        return transaction.fetch_one(
            """
            select id::text as id, category, source, version, raw_payload
            from app.bank_transaction_categories
            where status = 'active'
              and (bank_transaction_id = %s::uuid or legacy_transaction_id in (%s, %s))
            order by updated_at desc, id desc
            limit 1
            for update
            """,
            (bank_transaction_id, public_transaction_id, bank_transaction_id),
        )

    @staticmethod
    def _active_confirmation(transaction: Any, *, bank_transaction_id: str, public_transaction_id: str) -> dict[str, Any] | None:
        return transaction.fetch_one(
            """
            select id::text as id, category_code, candidate_category_codes, rule_version, version, raw_payload
            from app.bank_transaction_category_confirmations
            where tenant_id = 'default'
              and status = 'active'
              and (bank_transaction_id = %s::uuid or legacy_transaction_id in (%s, %s))
            order by confirmed_at desc, id desc
            limit 1
            for update
            """,
            (bank_transaction_id, public_transaction_id, bank_transaction_id),
        )

    @classmethod
    def _assign_manual(
        cls,
        transaction: Any,
        *,
        bank_transaction_id: str,
        public_transaction_id: str,
        record: dict[str, Any],
        actor_id: str,
    ) -> dict[str, object]:
        current = cls._active_manual(
            transaction,
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
        )
        confirmation = cls._active_confirmation(
            transaction,
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
        )
        payload = cls._normalized_record(record, source="manual", actor_id=actor_id, manual_assignment=True)
        current_payload = cls._normalized_payload(current)
        semantic_fields = (
            "category_code",
            "category_primary_label",
            "category_sub_label",
            "category_third_label",
            "category_label_path",
            "turnover_action_type",
            "turnover_family",
        )
        if (
            isinstance(current, dict)
            and text(current.get("source")) == "manual"
            and bool(current_payload.get("manual_assignment"))
            and confirmation is None
            and all(current_payload.get(field) == payload.get(field) for field in semantic_fields)
        ):
            return {"changed": False, "version": int_value(current.get("version"), 1)}
        if isinstance(current, dict):
            transaction.execute(
                """
                update app.bank_transaction_categories
                set status = 'superseded', updated_at = now()
                where id = %s::uuid
                """,
                (current["id"],),
            )
        if isinstance(confirmation, dict):
            transaction.execute(
                """
                update app.bank_transaction_category_confirmations
                set status = 'revoked', revoked_by = %s, revoked_at = now(), version = version + 1
                where id = %s::uuid
                """,
                (actor_id, confirmation["id"]),
            )
        payload["version"] = max(
            int_value(current.get("version") if current else None, 0),
            int_value(confirmation.get("version") if confirmation else None, 0),
        ) + 1
        return cls._insert_category(
            transaction,
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
            payload=payload,
            event_type="manual_assignment",
        )

    @staticmethod
    def _normalized_payload(record: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(record, dict):
            return {}
        raw_payload = record.get("raw_payload")
        if not isinstance(raw_payload, dict):
            return {}
        normalized = raw_payload.get("normalized_payload")
        return dict(normalized) if isinstance(normalized, dict) else dict(raw_payload)

    @classmethod
    def _assign_turnover(
        cls,
        transaction: Any,
        *,
        bank_transaction_id: str,
        public_transaction_id: str,
        record: dict[str, Any],
        actor_id: str,
    ) -> dict[str, object]:
        current = cls._active_manual(
            transaction,
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
        )
        payload = cls._normalized_record(record, source="turnover_ledger", actor_id=actor_id)
        if (
            isinstance(current, dict)
            and text(current.get("category")) == text(payload.get("category_code"))
            and text(current.get("source")) == "turnover_ledger"
        ):
            return {"changed": False, "version": int_value(current.get("version"), 1)}
        transaction.execute(
            """
            update app.bank_transaction_categories
            set status = 'superseded', updated_at = now()
            where status = 'active'
              and (bank_transaction_id = %s::uuid or legacy_transaction_id in (%s, %s))
            """,
            (bank_transaction_id, public_transaction_id, bank_transaction_id),
        )
        return cls._insert_category(
            transaction,
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
            payload=payload,
            event_type="turnover_category_updated",
        )

    @classmethod
    def _clear_manual(
        cls,
        transaction: Any,
        *,
        bank_transaction_id: str,
        public_transaction_id: str,
        actor_id: str,
        record: dict[str, Any],
    ) -> dict[str, object]:
        current = cls._active_manual(
            transaction,
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
        )
        if not isinstance(current, dict):
            latest = transaction.fetch_one(
                """
                select version, source, status, raw_payload
                from app.bank_transaction_categories
                where (bank_transaction_id = %s::uuid or legacy_transaction_id in (%s, %s))
                order by updated_at desc, id desc
                limit 1
                """,
                (bank_transaction_id, public_transaction_id, bank_transaction_id),
            )
            if isinstance(latest, dict) and text(latest.get("source")) == "manual" and text(latest.get("status")) == "cleared":
                return {"changed": False, "version": int_value(latest.get("version"), 1)}
            raise BankTransactionCategoryValidationError(
                "invalid_manual_category_clear_target",
                "当前流水没有可撤销的人工标签。",
                transaction_id=public_transaction_id,
            )
        raw_payload = current.get("raw_payload") if isinstance(current.get("raw_payload"), dict) else {}
        normalized = raw_payload.get("normalized_payload") if isinstance(raw_payload.get("normalized_payload"), dict) else raw_payload
        if text(current.get("source")) != "manual" or not bool(normalized.get("manual_assignment")):
            raise BankTransactionCategoryValidationError(
                "invalid_manual_category_clear_target",
                "只能撤销从待分类状态人工添加的标签。",
                transaction_id=public_transaction_id,
            )
        version = max(int_value(current.get("version"), 1) + 1, int_value(record.get("category_version"), 0))
        transaction.execute(
            """
            update app.bank_transaction_categories
            set status = 'cleared', version = %s, updated_by = %s, updated_at = now(),
                raw_payload = jsonb_set(
                    coalesce(raw_payload, '{}'::jsonb),
                    '{normalized_payload}',
                    coalesce(raw_payload->'normalized_payload', '{}'::jsonb)
                        || jsonb_build_object(
                            'category_code', null,
                            'source', 'manual',
                            'manual_assignment', true,
                            'updated_by', %s::text,
                            'version', %s::integer
                        ),
                    true
                )
            where id = %s::uuid
            """,
            (version, actor_id, actor_id, version, current["id"]),
        )
        cls._insert_category_event(
            transaction,
            category_id=str(current["id"]),
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
            actor_id=actor_id,
            event_type="manual_assignment_cleared",
            payload={"category_code": None, "source": "manual", "manual_assignment": True, "version": version},
        )
        return {"changed": True, "version": version}

    @classmethod
    def _confirm(
        cls,
        transaction: Any,
        *,
        bank_transaction_id: str,
        public_transaction_id: str,
        record: dict[str, Any],
        actor_id: str,
    ) -> dict[str, object]:
        current = cls._active_confirmation(
            transaction,
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
        )
        category_code = text(record.get("category_code"))
        candidate_codes = text_list(record.get("candidate_category_codes"))
        rule_version = text(record.get("rule_version")) or ""
        if not category_code:
            raise ValueError("Category confirmation requires category_code.")
        if (
            isinstance(current, dict)
            and text(current.get("category_code")) == category_code
            and text_list(current.get("candidate_category_codes")) == candidate_codes
            and (text(current.get("rule_version")) or "") == rule_version
        ):
            return {"changed": False, "version": int_value(current.get("version"), 1)}
        if isinstance(current, dict):
            transaction.execute(
                """
                update app.bank_transaction_category_confirmations
                set status = 'revoked', revoked_by = %s, revoked_at = now(), version = version + 1
                where id = %s::uuid
                """,
                (actor_id, current["id"]),
            )
        version = max(int_value(record.get("category_version"), 0), int_value(current.get("version") if current else None, 0) + 1, 1)
        payload = cls._normalized_record(record, source="auto_confirmation", actor_id=actor_id)
        payload.update(
            {
                "category_code": category_code,
                "candidate_category_codes": candidate_codes,
                "rule_version": rule_version,
                "version": version,
            }
        )
        transaction.execute(
            """
            insert into app.bank_transaction_category_confirmations(
                tenant_id, bank_transaction_id, category_code, candidate_category_codes,
                rule_version, status, version, confirmed_by, raw_payload
            ) values ('default', %s::uuid, %s, %s, %s, 'active', %s, %s, %s)
            """,
            (
                bank_transaction_id,
                category_code,
                jsonb(candidate_codes),
                rule_version,
                version,
                actor_id,
                jsonb({"normalized_payload": payload}),
            ),
        )
        return {"changed": True, "version": version}

    @classmethod
    def _revoke_confirmation(
        cls,
        transaction: Any,
        *,
        bank_transaction_id: str,
        public_transaction_id: str,
        actor_id: str,
        record: dict[str, Any],
    ) -> dict[str, object]:
        current = cls._active_confirmation(
            transaction,
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
        )
        if not isinstance(current, dict):
            latest = transaction.fetch_one(
                """
                select version, status
                from app.bank_transaction_category_confirmations
                where tenant_id = 'default'
                  and (bank_transaction_id = %s::uuid or legacy_transaction_id in (%s, %s))
                order by confirmed_at desc, id desc
                limit 1
                """,
                (bank_transaction_id, public_transaction_id, bank_transaction_id),
            )
            if isinstance(latest, dict) and text(latest.get("status")) == "revoked":
                return {"changed": False, "version": int_value(latest.get("version"), 1)}
            raise BankTransactionCategoryValidationError(
                "invalid_category_confirmation_revoke_target",
                "当前流水没有可撤销的标签确认。",
                transaction_id=public_transaction_id,
            )
        version = max(int_value(current.get("version"), 1) + 1, int_value(record.get("category_version"), 0))
        payload = cls._normalized_record(record, source="auto_confirmation_revoked", actor_id=actor_id)
        payload["version"] = version
        transaction.execute(
            """
            update app.bank_transaction_category_confirmations
            set status = 'revoked', revoked_by = %s, revoked_at = now(), version = %s,
                raw_payload = %s
            where id = %s::uuid
            """,
            (actor_id, version, jsonb({"normalized_payload": payload}), current["id"]),
        )
        return {"changed": True, "version": version}

    @classmethod
    def _insert_category(
        cls,
        transaction: Any,
        *,
        bank_transaction_id: str,
        public_transaction_id: str,
        payload: dict[str, Any],
        event_type: str,
    ) -> dict[str, object]:
        category_code = text(payload.get("category_code"))
        if not category_code:
            raise ValueError("Active bank transaction category requires category_code.")
        latest = transaction.fetch_one(
            """
            select coalesce(max(version), 0) as version
            from app.bank_transaction_categories
            where bank_transaction_id = %s::uuid or legacy_transaction_id in (%s, %s)
            """,
            (bank_transaction_id, public_transaction_id, bank_transaction_id),
        )
        version = max(int_value((latest or {}).get("version"), 0) + 1, int_value(payload.get("version"), 0), 1)
        payload["version"] = version
        inserted = transaction.fetch_one(
            """
            insert into app.bank_transaction_categories(
                bank_transaction_id, legacy_transaction_id, category, source, confidence,
                status, version, updated_by, raw_payload
            ) values (%s::uuid, %s, %s, %s, %s, 'active', %s, %s, %s)
            returning id::text as id
            """,
            (
                bank_transaction_id,
                public_transaction_id,
                category_code,
                text(payload.get("source")) or "manual",
                payload.get("confidence"),
                version,
                text(payload.get("updated_by")),
                jsonb({"normalized_payload": payload}),
            ),
        )
        category_id = str((inserted or {}).get("id") or "")
        if not category_id:
            raise RuntimeError("Bank transaction category insert did not return an id.")
        cls._insert_category_event(
            transaction,
            category_id=category_id,
            bank_transaction_id=bank_transaction_id,
            public_transaction_id=public_transaction_id,
            actor_id=text(payload.get("updated_by")) or "",
            event_type=event_type,
            payload=payload,
        )
        return {"changed": True, "version": version}

    @staticmethod
    def _insert_category_event(
        transaction: Any,
        *,
        category_id: str,
        bank_transaction_id: str,
        public_transaction_id: str,
        actor_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        transaction.execute(
            """
            insert into app.bank_transaction_category_events(
                id, category_id, bank_transaction_id, event_type, actor_id, payload, raw_payload
            ) values (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s)
            on conflict (id) do nothing
            """,
            (
                event_uuid("bank_transaction_category_events", public_transaction_id, payload),
                category_id,
                bank_transaction_id,
                event_type,
                actor_id,
                jsonb(payload),
                jsonb({"normalized_payload": payload}),
            ),
        )

    @staticmethod
    def _normalized_record(
        record: dict[str, Any],
        *,
        source: str,
        actor_id: str,
        manual_assignment: bool = False,
    ) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in dict(record or {}).items()
            if key not in {"category_version", "effective_category_code"}
        }
        payload.update(
            {
                "category_code": text(record.get("category_code")),
                "source": source,
                "updated_by": actor_id,
                "manual_assignment": bool(manual_assignment or record.get("manual_assignment")),
            }
        )
        return payload
