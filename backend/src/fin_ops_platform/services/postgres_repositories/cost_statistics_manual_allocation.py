from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import jsonb, serialize_value


class PostgresCostStatisticsManualAllocationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def revoke_for_bank_split(self, case_ids: list[str], *, actor_id: str, parent_id: str) -> list[str]:
        """Retire obsolete decisions without resetting their CAS version."""
        from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository

        if not case_ids:
            return []
        rows = self._connection.fetch_all(
            """
            with before as materialized (
                select * from app.cost_statistics_manual_allocations
                where relation_case_id = any(%s::text[]) and decision_mode = 'manual'
                order by relation_case_id for update
            ), changed as (
                update app.cost_statistics_manual_allocations allocation
                set decision_mode = 'automatic', version = allocation.version + 1,
                    updated_by = %s, updated_at = now()
                from before where allocation.relation_case_id = before.relation_case_id
                returning before.*
            ) select * from changed
            """,
            (sorted(set(case_ids)), actor_id),
        )
        audit = PostgresOperationsAuditRepository(self._connection)
        for row in rows:
            audit.append_operation_event({
                "event_type": "operation.completed", "object_type": "cost_statistics_manual_allocation",
                "object_id": row["relation_case_id"], "actor_id": actor_id, "scope": "all",
                "action": "cost_statistics.manual_allocation.revoke_bank_split",
                "page_key": "cost-statistics", "operation_location": "流水拆分/成本分配撤销",
                "payload": {
                    "parent_transaction_id": parent_id,
                    "before": {**serialize_value(row), "id": str(row["id"])},
                    "after": {"decision_mode": "automatic", "version": int(row["version"]) + 1},
                },
            })
        return sorted(row["relation_case_id"] for row in rows)

    def list_bank_split_migration_candidates(self) -> list[dict[str, Any]]:
        """Read historical and active decisions, without limiting to a UI page."""
        return self._connection.fetch_all("""
            select allocation.relation_case_id, allocation.version,
                   allocation.source_allocations, relation.row_ids, relation.row_types
            from app.cost_statistics_manual_allocations allocation
            left join app.workbench_pair_relations relation
              on relation.case_id = allocation.relation_case_id
            where allocation.decision_mode = 'manual'
            order by allocation.relation_case_id
        """)

    def list_decision_candidates(self) -> list[dict[str, Any]]:
        """List every live manual decision, including inactive/missing relations."""
        return self._connection.fetch_all("""
            select allocation.relation_case_id, allocation.decision_mode,
                   allocation.version, relation.status as relation_status
            from app.cost_statistics_manual_allocations allocation
            left join app.workbench_pair_relations relation
              on relation.case_id = allocation.relation_case_id
            where allocation.decision_mode = 'manual'
            order by allocation.relation_case_id
        """)

    def retire_to_automatic(
        self, *, relation_case_id: str, expected_version: int, actor_id: str,
    ) -> dict[str, Any] | None:
        """CAS transition; the caller writes the full audit in the same transaction."""
        row = self._connection.fetch_one("""
            update app.cost_statistics_manual_allocations
            set decision_mode = 'automatic', version = version + 1,
                updated_by = %s, updated_at = now()
            where relation_case_id = %s and version = %s and decision_mode = 'manual'
            returning *
        """, (actor_id, relation_case_id, expected_version))
        return _record(row) if isinstance(row, dict) else None

    def list_by_case_ids(self, case_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized = list(dict.fromkeys(str(case_id).strip() for case_id in case_ids if str(case_id).strip()))
        if not normalized:
            return {}
        rows = self._connection.fetch_all(
            """
            select
                relation_case_id,
                decision_mode,
                relation_version,
                source_fingerprint,
                oa_total,
                gross_outflow_total,
                wrong_payment_refund_total,
                net_outflow_total,
                unit_allocations,
                source_allocations,
                manual_items,
                oa_amount_locks,
                oa_cost_tag_overrides,
                non_cost_amount,
                non_cost_reason,
                version,
                created_by,
                created_at,
                updated_by,
                updated_at
            from app.cost_statistics_manual_allocations
            where relation_case_id = any(%s::text[])
            order by relation_case_id
            """,
            (normalized,),
        )
        return {
            str(row["relation_case_id"]): _record(row)
            for row in rows
            if row.get("relation_case_id")
        }

    def save(
        self,
        *,
        relation_case_id: str,
        decision_mode: str,
        relation_version: int,
        source_fingerprint: str,
        oa_total: str,
        gross_outflow_total: str,
        wrong_payment_refund_total: str,
        net_outflow_total: str,
        allocations: list[dict[str, str]],
        source_allocations: dict[str, Any],
        manual_items: list[dict[str, Any]],
        oa_amount_locks: dict[str, bool],
        oa_cost_tag_overrides: list[dict[str, str]],
        non_cost_amount: str,
        non_cost_reason: str,
        expected_version: int,
        actor_id: str,
    ) -> dict[str, Any] | None:
        _validate_decision_mode(decision_mode)
        if expected_version == 0:
            row = self._connection.fetch_one(
                """
                insert into app.cost_statistics_manual_allocations(
                    relation_case_id,
                    decision_mode,
                    relation_version,
                    source_fingerprint,
                    oa_total,
                    gross_outflow_total,
                    wrong_payment_refund_total,
                    net_outflow_total,
                    unit_allocations,
                    source_allocations,
                    manual_items,
                    oa_amount_locks,
                    oa_cost_tag_overrides,
                    non_cost_amount,
                    non_cost_reason,
                    version,
                    created_by,
                    updated_by
                ) values (
                    %s, %s, %s, %s, %s::numeric, %s::numeric, %s::numeric, %s::numeric,
                    %s, %s, %s, %s, %s, %s::numeric, %s, 1, %s, %s
                )
                on conflict (relation_case_id) do nothing
                returning *
                """,
                (
                    relation_case_id,
                    decision_mode,
                    relation_version,
                    source_fingerprint,
                    oa_total,
                    gross_outflow_total,
                    wrong_payment_refund_total,
                    net_outflow_total,
                    jsonb(serialize_value(allocations)),
                    jsonb(serialize_value(source_allocations)),
                    jsonb(serialize_value(manual_items)),
                    jsonb(oa_amount_locks),
                    jsonb(oa_cost_tag_overrides),
                    non_cost_amount,
                    non_cost_reason,
                    actor_id,
                    actor_id,
                ),
            )
        else:
            row = self._connection.fetch_one(
                """
                update app.cost_statistics_manual_allocations
                set decision_mode = %s,
                    relation_version = %s,
                    source_fingerprint = %s,
                    oa_total = %s::numeric,
                    gross_outflow_total = %s::numeric,
                    wrong_payment_refund_total = %s::numeric,
                    net_outflow_total = %s::numeric,
                    unit_allocations = %s,
                    source_allocations = %s,
                    manual_items = %s,
                    oa_amount_locks = %s,
                    oa_cost_tag_overrides = %s,
                    non_cost_amount = %s::numeric,
                    non_cost_reason = %s,
                    version = version + 1,
                    updated_by = %s,
                    updated_at = now()
                where relation_case_id = %s
                  and version = %s
                returning *
                """,
                (
                    decision_mode,
                    relation_version,
                    source_fingerprint,
                    oa_total,
                    gross_outflow_total,
                    wrong_payment_refund_total,
                    net_outflow_total,
                    jsonb(serialize_value(allocations)),
                    jsonb(serialize_value(source_allocations)),
                    jsonb(serialize_value(manual_items)),
                    jsonb(oa_amount_locks),
                    jsonb(oa_cost_tag_overrides),
                    non_cost_amount,
                    non_cost_reason,
                    actor_id,
                    relation_case_id,
                    expected_version,
                ),
            )
        return _record(row) if isinstance(row, dict) else None


class InMemoryCostStatisticsManualAllocationRepository:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def list_by_case_ids(self, case_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {
            case_id: dict(self._records[case_id])
            for case_id in case_ids
            if case_id in self._records
        }

    def retire_to_automatic(
        self, *, relation_case_id: str, expected_version: int, actor_id: str,
    ) -> dict[str, Any] | None:
        current = self._records.get(relation_case_id)
        if current is None or current["version"] != expected_version or current["decision_mode"] != "manual":
            return None
        record = {**current, "decision_mode": "automatic", "version": expected_version + 1,
                  "updated_by": actor_id, "updated_at": ""}
        self._records[relation_case_id] = record
        return dict(record)

    def save(self, **values: Any) -> dict[str, Any] | None:
        _validate_decision_mode(values["decision_mode"])
        case_id = str(values["relation_case_id"])
        expected_version = int(values["expected_version"])
        current = self._records.get(case_id)
        current_version = int(current.get("version") or 0) if current else 0
        if current_version != expected_version:
            return None
        record = {
            **{key: value for key, value in values.items() if key != "expected_version"},
            "version": current_version + 1,
            "updated_by": str(values["actor_id"]),
            "updated_at": "",
        }
        self._records[case_id] = record
        return dict(record)


def _validate_decision_mode(mode: str) -> None:
    if mode not in {"manual", "automatic"}:
        raise ValueError("Invalid cost allocation decision mode.")


def _record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "relation_case_id": str(row.get("relation_case_id") or ""),
        "decision_mode": row["decision_mode"],
        "relation_version": int(row.get("relation_version") or 1),
        "source_fingerprint": str(row.get("source_fingerprint") or ""),
        "oa_total": str(row.get("oa_total") or "0.00"),
        "gross_outflow_total": str(row.get("gross_outflow_total") or "0.00"),
        "wrong_payment_refund_total": str(
            row.get("wrong_payment_refund_total") or "0.00"
        ),
        "net_outflow_total": str(row.get("net_outflow_total") or "0.00"),
        "source_allocations": row.get("source_allocations"),
        "manual_items": row["manual_items"],
        "oa_amount_locks": row["oa_amount_locks"],
        "oa_cost_tag_overrides": row["oa_cost_tag_overrides"],
        "allocations": [
            dict(line)
            for line in list(row.get("unit_allocations") or [])
            if isinstance(line, dict)
        ],
        "non_cost_amount": str(row.get("non_cost_amount") or "0.00"),
        "non_cost_reason": str(row.get("non_cost_reason") or ""),
        "version": int(row.get("version") or 0),
        "created_by": str(row.get("created_by") or ""),
        "created_at": str(row.get("created_at") or ""),
        "updated_by": str(row.get("updated_by") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }
