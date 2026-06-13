from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, Sequence, TextIO
from urllib.parse import quote

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


DEFAULT_LIMIT = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover read-only candidate write-operation E2E smoke scenarios from PostgreSQL facts.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--output", type=Path, help="Optional path to write the discovery report.")
    parser.add_argument(
        "--scenario-output",
        type=Path,
        help="Optional path to write a write_operation_e2e_smoke scenario JSON for discovered approved operations.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    report = discover_write_operation_scenarios(
        connection,
        tenant_id=str(args.tenant_id or "default"),
        limit=max(1, int(args.limit)),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    if args.scenario_output is not None:
        scenario_payload = {
            "version": 1,
            "generated_at": report["generated_at"],
            "scenarios": report["scenario_json"]["scenarios"],
        }
        args.scenario_output.parent.mkdir(parents=True, exist_ok=True)
        args.scenario_output.write_text(
            json.dumps(scenario_payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    print(encoded, file=stdout)
    return 0


def discover_write_operation_scenarios(
    connection: Any,
    *,
    tenant_id: str = "default",
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    normalized_limit = max(1, int(limit))
    turnover_candidates = _turnover_withdraw_candidates(connection, limit=normalized_limit)
    workbench_candidates = _workbench_withdraw_candidates(connection, limit=normalized_limit)
    no_oa_candidates = _no_oa_withdraw_candidates(connection, limit=normalized_limit)
    scenarios = [
        *[_turnover_withdraw_scenario(candidate) for candidate in turnover_candidates],
        *[_workbench_withdraw_scenario(candidate) for candidate in workbench_candidates],
        *[_no_oa_withdraw_scenario(candidate) for candidate in no_oa_candidates],
    ]
    return {
        "version": 1,
        "status": "ready" if scenarios else "no_candidates",
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "mode": "read_only",
        "candidate_counts": {
            "turnover_manual_closure_or_withdraw": len(turnover_candidates),
            "workbench_pair_withdraw_context": len(workbench_candidates),
            "no_oa_bank_batch_withdraw_context": len(no_oa_candidates),
        },
        "scenario_json": {
            "scenarios": scenarios,
            "warning": "Review every scenario and its rollback path before running write_operation_e2e_smoke --apply.",
        },
        "candidates": {
            "turnover_manual_closure_or_withdraw": turnover_candidates,
            "workbench_pair_withdraw_context": workbench_candidates,
            "no_oa_bank_batch_withdraw_context": no_oa_candidates,
        },
        "safety": {
            "mutates_data": False,
            "requires_real_auth_to_apply": True,
            "requires_manual_approval_before_apply": True,
            "notes": [
                "Discovery is read-only and does not call mutating HTTP endpoints.",
                "Generated scenarios withdraw existing turnover, Workbench, or no-OA relations; use only on reviewed test or reversible objects.",
                "Every generated scenario remains blocked for --apply until real OA/Admin auth and manual approval are supplied.",
            ],
        },
    }


def _turnover_withdraw_candidates(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          relation_id,
          coalesce(status, raw_payload->>'status', '') as status,
          coalesce(relation_type, raw_payload->>'relation_type', raw_payload->>'family', '') as relation_type,
          coalesce(raw_payload->>'source', raw_payload->>'relation_source', '') as source,
          coalesce(scope_month::text, left(coalesce(raw_payload->>'month', raw_payload->>'scope_month', ''), 10), '') as scope_month,
          version,
          updated_at
        from app.turnover_relations
        where relation_id is not null
          and coalesce(status, raw_payload->>'status', '') not in ('withdrawn', 'cancelled')
          and coalesce(raw_payload->>'source', raw_payload->>'relation_source', '') <> 'system'
        order by updated_at desc nulls last, relation_id
        limit %s
        """,
        (limit,),
    )
    return [
        {
            "operation": "turnover_manual_closure_or_withdraw",
            "relation_id": _text(row.get("relation_id")),
            "status": _text(row.get("status")),
            "relation_type": _text(row.get("relation_type")),
            "source": _text(row.get("source")),
            "scope_month": _month_text(row.get("scope_month")),
            "version": row.get("version"),
            "updated_at": str(row.get("updated_at") or ""),
            "risk": "existing_relation_withdraw_requires_manual_business_approval",
        }
        for row in rows
        if _text(row.get("relation_id"))
    ]


def _workbench_withdraw_candidates(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          case_id,
          relation_mode,
          status,
          month_scope::text as month_scope,
          row_ids,
          version,
          updated_at
        from app.workbench_pair_relations
        where status = 'active'
          and array_length(row_ids, 1) > 0
        order by updated_at desc nulls last, case_id
        limit %s
        """,
        (limit,),
    )
    return [
        {
            "operation_context": "workbench_pair_withdraw",
            "case_id": _text(row.get("case_id")),
            "status": _text(row.get("status")),
            "relation_mode": _text(row.get("relation_mode")),
            "month": _month_text(row.get("month_scope")) or "all",
            "row_ids": [_text(item) for item in list(row.get("row_ids") or []) if _text(item)],
            "version": row.get("version"),
            "updated_at": str(row.get("updated_at") or ""),
            "candidate_path": "/api/workbench/actions/withdraw-link",
            "risk": "existing_workbench_relation_withdraw_requires_manual_business_approval",
        }
        for row in rows
        if _text(row.get("case_id"))
    ]


def _no_oa_withdraw_candidates(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          batch_id,
          status,
          status_bucket,
          scope_month::text as scope_month,
          version,
          updated_at
        from app.no_oa_bank_batches
        where status = 'submitted'
        order by updated_at desc nulls last, batch_id
        limit %s
        """,
        (limit,),
    )
    return [
        {
            "operation_context": "no_oa_bank_batch_withdraw",
            "batch_id": _text(row.get("batch_id")),
            "status": _text(row.get("status")),
            "status_bucket": _text(row.get("status_bucket")),
            "month": _month_text(row.get("scope_month")) or "all",
            "version": row.get("version"),
            "updated_at": str(row.get("updated_at") or ""),
            "candidate_path": f"/api/no-oa-bank-batches/{quote(_text(row.get('batch_id')), safe='')}/withdraw",
            "risk": "existing_no_oa_batch_withdraw_requires_manual_business_approval",
        }
        for row in rows
        if _text(row.get("batch_id"))
    ]


def _turnover_withdraw_scenario(candidate: dict[str, Any]) -> dict[str, Any]:
    relation_id = _text(candidate.get("relation_id"))
    return {
        "name": f"turnover-withdraw-{relation_id}",
        "operation": "turnover_manual_closure_or_withdraw",
        "steps": [
            {
                "name": "withdraw",
                "method": "POST",
                "path": f"/api/turnover-ledger/relations/{quote(relation_id, safe='')}/withdraw",
                "json": {
                    "note": "controlled runtime sync SLO smoke withdraw; review rollback before apply",
                    "idempotency_key": f"runtime-sync-slo-withdraw-{relation_id}",
                },
                "expected_statuses": [200],
            }
        ],
        "post_api_probes": [
            {
                "name": "turnover_ledger_grouped",
                "path": "/api/turnover-ledger?view=grouped&page=1&page_size=50",
                "expected_statuses": [200, 202],
                "target_ms": 1000,
            },
            {
                "name": "operations_app_health_dashboard",
                "path": "/api/operations/app-health-dashboard",
                "expected_statuses": [200, 202],
                "target_ms": 1000,
            },
        ],
        "metadata": {
            "requires_manual_approval_before_apply": True,
            "candidate_status": candidate.get("status"),
            "candidate_scope_month": candidate.get("scope_month"),
            "risk": candidate.get("risk"),
        },
    }


def _workbench_withdraw_scenario(candidate: dict[str, Any]) -> dict[str, Any]:
    case_id = _text(candidate.get("case_id"))
    row_ids = [_text(item) for item in list(candidate.get("row_ids") or []) if _text(item)]
    month = _month_text(candidate.get("month")) or "all"
    return {
        "name": f"workbench-withdraw-{case_id}",
        "operation": "workbench_relation_withdraw",
        "steps": [
            {
                "name": "withdraw",
                "method": "POST",
                "path": "/api/workbench/actions/withdraw-link",
                "json": {
                    "month": month,
                    "row_ids": row_ids,
                    "note": "controlled runtime sync SLO smoke withdraw; review rollback before apply",
                },
                "expected_statuses": [200],
            }
        ],
        "post_api_probes": [
            {
                "name": "workbench_groups",
                "path": f"/api/workbench/groups?month={quote(month, safe='')}&zone=paired&page=1&page_size=20",
                "expected_statuses": [200, 202],
                "target_ms": 1000,
            },
            {
                "name": "operations_app_health_dashboard",
                "path": "/api/operations/app-health-dashboard",
                "expected_statuses": [200, 202],
                "target_ms": 1000,
            },
        ],
        "metadata": {
            "requires_manual_approval_before_apply": True,
            "candidate_case_id": case_id,
            "candidate_relation_mode": candidate.get("relation_mode"),
            "candidate_month": month,
            "risk": candidate.get("risk"),
        },
    }


def _no_oa_withdraw_scenario(candidate: dict[str, Any]) -> dict[str, Any]:
    batch_id = _text(candidate.get("batch_id"))
    month = _month_text(candidate.get("month")) or "all"
    version = candidate.get("version")
    return {
        "name": f"no-oa-withdraw-{batch_id}",
        "operation": "no_oa_bank_batch_withdraw",
        "steps": [
            {
                "name": "withdraw",
                "method": "POST",
                "path": f"/api/no-oa-bank-batches/{quote(batch_id, safe='')}/withdraw",
                "json": {
                    "expected_version": version,
                    "reason": "controlled runtime sync SLO smoke withdraw; review rollback before apply",
                },
                "expected_statuses": [200],
            }
        ],
        "post_api_probes": [
            {
                "name": "no_oa_bank_batches",
                "path": f"/api/no-oa-bank-batches?month={quote(month, safe='')}&bucket=submitted",
                "expected_statuses": [200, 202],
                "target_ms": 1000,
            },
            {
                "name": "operations_app_health_dashboard",
                "path": "/api/operations/app-health-dashboard",
                "expected_statuses": [200, 202],
                "target_ms": 1000,
            },
        ],
        "metadata": {
            "requires_manual_approval_before_apply": True,
            "candidate_batch_id": batch_id,
            "candidate_month": month,
            "candidate_version": version,
            "risk": candidate.get("risk"),
        },
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _month_text(value: Any) -> str:
    text = _text(value)
    if len(text) >= 7 and text[4:5] == "-":
        return text[:7]
    return text


if __name__ == "__main__":
    raise SystemExit(main())
