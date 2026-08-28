from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import jsonb, serialize_value


class PostgresCostStatisticsManualAllocationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_by_case_ids(self, case_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized = list(dict.fromkeys(str(case_id).strip() for case_id in case_ids if str(case_id).strip()))
        if not normalized:
            return {}
        rows = self._connection.fetch_all(
            """
            select
                relation_case_id,
                relation_version,
                source_fingerprint,
                oa_total,
                gross_outflow_total,
                wrong_payment_refund_total,
                net_outflow_total,
                unit_allocations,
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
        relation_version: int,
        source_fingerprint: str,
        oa_total: str,
        gross_outflow_total: str,
        wrong_payment_refund_total: str,
        net_outflow_total: str,
        allocations: list[dict[str, str]],
        non_cost_amount: str,
        non_cost_reason: str,
        expected_version: int,
        actor_id: str,
    ) -> dict[str, Any] | None:
        if expected_version == 0:
            row = self._connection.fetch_one(
                """
                insert into app.cost_statistics_manual_allocations(
                    relation_case_id,
                    relation_version,
                    source_fingerprint,
                    oa_total,
                    gross_outflow_total,
                    wrong_payment_refund_total,
                    net_outflow_total,
                    unit_allocations,
                    non_cost_amount,
                    non_cost_reason,
                    version,
                    created_by,
                    updated_by
                ) values (
                    %s, %s, %s, %s::numeric, %s::numeric, %s::numeric, %s::numeric,
                    %s, %s::numeric, %s, 1, %s, %s
                )
                on conflict (relation_case_id) do nothing
                returning *
                """,
                (
                    relation_case_id,
                    relation_version,
                    source_fingerprint,
                    oa_total,
                    gross_outflow_total,
                    wrong_payment_refund_total,
                    net_outflow_total,
                    jsonb(serialize_value(allocations)),
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
                set relation_version = %s,
                    source_fingerprint = %s,
                    oa_total = %s::numeric,
                    gross_outflow_total = %s::numeric,
                    wrong_payment_refund_total = %s::numeric,
                    net_outflow_total = %s::numeric,
                    unit_allocations = %s,
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
                    relation_version,
                    source_fingerprint,
                    oa_total,
                    gross_outflow_total,
                    wrong_payment_refund_total,
                    net_outflow_total,
                    jsonb(serialize_value(allocations)),
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

    def save(self, **values: Any) -> dict[str, Any] | None:
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


def _record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "relation_case_id": str(row.get("relation_case_id") or ""),
        "relation_version": int(row.get("relation_version") or 1),
        "source_fingerprint": str(row.get("source_fingerprint") or ""),
        "oa_total": str(row.get("oa_total") or "0.00"),
        "gross_outflow_total": str(row.get("gross_outflow_total") or "0.00"),
        "wrong_payment_refund_total": str(
            row.get("wrong_payment_refund_total") or "0.00"
        ),
        "net_outflow_total": str(row.get("net_outflow_total") or "0.00"),
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
