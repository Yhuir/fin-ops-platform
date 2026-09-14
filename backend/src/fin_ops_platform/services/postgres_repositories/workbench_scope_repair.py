"""Offline, audited correction of relation scope and saved response metadata only."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import jsonb, month_start, serialize_value
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.workbench_relation_scope import validate_relation_scope


class PostgresWorkbenchScopeRepairRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def read_state(self, case_ids: list[str] | None = None) -> dict[str, Any]:
        relations = self.connection.fetch_all('''
            select case_id, relation_mode, status, version, month_scope, row_ids, row_types,
                   raw_payload, updated_at
            from app.workbench_pair_relations
            where (%s::text[] is null or case_id = any(%s::text[]))
            order by case_id
        ''', (case_ids, case_ids))
        responses = self.connection.fetch_all('''
            select tenant_id, actor_id, idempotency_key, request_payload, response_payload,
                   action_name, status
            from app.workbench_idempotency_records
            where status = 'committed' and action_name in ('confirm_link', 'withdraw_link', 'cancel_link')
              and (%s::text[] is null or response_payload->>'case_id' = any(%s::text[]))
            order by created_at, idempotency_key
        ''', (case_ids, case_ids))
        return serialize_value({'relations': [self._relation_state(row) for row in relations], 'responses': responses})

    def apply(self, plan: dict[str, Any], *, actor: str, reason: str, rollback: bool = False) -> dict[str, Any]:
        if not actor.strip() or not reason.strip():
            raise ValueError('Scope repair requires actor and reason.')
        changed = {'relations': 0, 'responses': 0}
        with self.connection.transaction() as tx:
            tx.execute("set local lock_timeout = '5s'")
            tx.execute("set local statement_timeout = '10s'")
            for item in plan.get('relations', []):
                before = item['before']
                new_scope = validate_relation_scope(item['after_scope'])
                current = tx.fetch_one('''select case_id, relation_mode, status, version, month_scope,
                    row_ids, row_types, raw_payload, updated_at from app.workbench_pair_relations
                    where case_id = %s for update''', (before['case_id'],))
                if current is None:
                    raise ValueError('Scope repair relation no longer exists.')
                current = self._relation_state(current)
                after = deepcopy(before)
                after['month_scope'] = month_start(new_scope)
                after['raw_payload']['normalized_payload']['month_scope'] = new_scope
                expected, target = (after, before) if rollback else (before, after)
                # Scope changes do not change topology versions; protect every other fact.
                fields = [key for key in before if key != 'updated_at']
                if all(current[key] == target[key] for key in fields):
                    continue
                if any(current[key] != expected[key] for key in fields) or (not rollback and current['updated_at'] != before['updated_at']):
                    raise ValueError('Scope repair relation changed; inspect a fresh plan.')
                tx.execute('''update app.workbench_pair_relations set month_scope=%s::date,
                    raw_payload=%s, updated_at=now() where case_id=%s''',
                    (target['month_scope'], jsonb(target['raw_payload']), before['case_id']))
                self._audit(tx, actor, reason, 'workbench_relation', before['case_id'], current, target, rollback)
                changed['relations'] += 1
            for item in plan.get('responses', []):
                before = item['before']
                after = item['after_payload']
                allowed = {'affected_months', 'affected_scope_keys', 'changed_scopes'}
                old_payload = before['response_payload']
                if {k: v for k, v in old_payload.items() if k not in allowed} != {k: v for k, v in after.items() if k not in allowed}:
                    raise ValueError('Scope repair cannot change saved business results.')
                if old_payload.keys() != after.keys():
                    raise ValueError('Scope repair cannot change the response shape.')
                for key in allowed & after.keys():
                    for month in after[key]:
                        if validate_relation_scope(month) == 'all':
                            raise ValueError('Affected months must be concrete.')
                identity = (before['tenant_id'], before['actor_id'], before['idempotency_key'])
                current = tx.fetch_one('''select status, response_payload from app.workbench_idempotency_records
                    where tenant_id=%s and actor_id=%s and idempotency_key=%s for update''', identity)
                if current is None or current['status'] != 'committed':
                    raise ValueError('Scope repair committed response is unavailable.')
                expected, target = (after, old_payload) if rollback else (old_payload, after)
                if current['response_payload'] == target:
                    continue
                if current['response_payload'] != expected:
                    raise ValueError('Scope repair response changed; inspect a fresh plan.')
                tx.execute('''update app.workbench_idempotency_records set response_payload=%s
                    where tenant_id=%s and actor_id=%s and idempotency_key=%s''', (jsonb(target), *identity))
                self._audit(tx, actor, reason, 'workbench_idempotency', before['idempotency_key'], expected, target, rollback)
                changed['responses'] += 1
        return changed

    @staticmethod
    def _relation_state(row):
        return serialize_value({**row, 'month_scope': month_start(row['month_scope'])})

    @staticmethod
    def _audit(tx, actor, reason, object_type, object_id, before, after, rollback):
        PostgresOperationsAuditRepository(tx).append_operation_event({
            'event_type': 'workbench.scope_metadata_repaired',
            'action': 'rollback_scope_metadata' if rollback else 'repair_scope_metadata',
            'page_key': 'reconciliation-workbench', 'object_type': object_type,
            'object_id': object_id, 'actor_id': actor, 'reason': reason,
            'payload': {'before': before, 'after': after},
        })
