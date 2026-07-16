from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, Sequence, TextIO
from urllib.parse import quote

from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report, write_json_report


DEFAULT_LIMIT = 10
STANDARD_SCENARIOS_PER_OPERATION = 1
STANDARD_SCENARIO_ENV = "FIN_OPS_WRITE_E2E_SCENARIO"
STANDARD_SCENARIO_PATH = "/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json"
STANDARD_APPROVAL_TICKET_ENV = "FIN_OPS_WRITE_E2E_APPROVAL_TICKET"
STANDARD_APPROVAL_TICKET = "FINOPS-WRITE-SMOKE-STANDING-20260702"
STANDARD_WRITE_OPERATIONS = (
    "turnover_manual_closure_or_withdraw",
    "workbench_relation_withdraw",
    "pending_invoice_attach_existing_invoice",
    "pending_invoice_attach_existing_invoice_with_oa",
    "bank_flow_rule_batch_submit",
)
STANDARD_PAGE_WRITE_SCENARIO_POLICIES: tuple[dict[str, Any], ...] = (
    {
        "page_key": "turnover-ledger",
        "apply_policy": "standing_apply",
        "scenario_operations": ("turnover_manual_closure_or_withdraw",),
    },
    {
        "page_key": "reconciliation-workbench",
        "apply_policy": "standing_apply",
        "scenario_operations": ("workbench_relation_withdraw",),
    },
    {
        "page_key": "workbench-relations",
        "apply_policy": "standing_apply",
        "scenario_operations": ("workbench_relation_withdraw",),
    },
    {
        "page_key": "bank-flow-rule-batches",
        "apply_policy": "standing_apply",
        "scenario_operations": ("bank_flow_rule_batch_submit",),
    },
    {
        "page_key": "bank-details",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "bank-account-balance",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "pending-invoices",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "input-invoice-usage",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "output-invoice-collections",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "invoice-lifecycle",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "oa-pending-payments",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "tax-offset",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "cost-statistics",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "search",
        "apply_policy": "fanout_evidence",
        "scenario_operations": STANDARD_WRITE_OPERATIONS,
    },
    {
        "page_key": "batch-accounting",
        "apply_policy": "fanout_evidence",
        "scenario_operations": ("workbench_relation_withdraw",),
    },
    {
        "page_key": "imports-bank-transactions",
        "apply_policy": "no_standing_production_apply",
        "scenario_operations": (),
    },
    {
        "page_key": "imports-invoices",
        "apply_policy": "no_standing_production_apply",
        "scenario_operations": (),
    },
    {
        "page_key": "imports-etc-invoices",
        "apply_policy": "no_standing_production_apply",
        "scenario_operations": (),
    },
    {
        "page_key": "settings",
        "apply_policy": "no_standing_production_apply",
        "scenario_operations": (),
    },
    {
        "page_key": "data-safety-reset",
        "apply_policy": "no_standing_production_apply",
        "scenario_operations": (),
    },
)


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
    try:
        connection = PostgresConnection(PostgresSettings.from_env())
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(tool="write_operation_scenario_discovery", message=str(exc))
        write_json_report(report, output=args.output, stdout=stdout)
        return 2
    report = discover_write_operation_scenarios(
        connection,
        tenant_id=str(args.tenant_id or "default"),
        limit=max(1, int(args.limit)),
    )
    if args.scenario_output is not None:
        _write_scenario_output(report, args.scenario_output)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
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
    workbench_withdraw_contexts = _workbench_withdraw_candidates(connection, limit=normalized_limit)
    bank_flow_candidates = _bank_flow_rule_batch_submit_candidates(connection, limit=normalized_limit)
    no_oa_candidates = _no_oa_withdraw_candidates(connection, limit=normalized_limit)
    scenarios = [
        *[
            _bank_flow_rule_batch_submit_scenario(candidate)
            for candidate in bank_flow_candidates[:STANDARD_SCENARIOS_PER_OPERATION]
        ],
    ]
    return {
        "version": 1,
        "status": "ready" if scenarios else "no_candidates",
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "mode": "read_only",
        "standard_inputs": _standard_inputs_payload(),
        "page_write_scenario_policy": _page_write_scenario_policy_payload(),
        "candidate_counts": {
            "turnover_manual_closure_or_withdraw": len(turnover_candidates),
            "workbench_pair_withdraw_context": len(workbench_withdraw_contexts),
            "bank_flow_rule_batch_submit_context": len(bank_flow_candidates),
            "no_oa_bank_batch_withdraw_context": len(no_oa_candidates),
        },
        "scenario_json": {
            "scenarios": scenarios,
            "warning": (
                "Only the current bank-flow owner may emit an executable discovery scenario. "
                "Relation candidates are read-only context and require an explicit test-owned reversible scenario."
            ),
        },
        "reversible_relation_closure": {
            "profile_pair_registry": (
                "fin_ops_platform.tools.write_operation_e2e_smoke.REVERSIBLE_RELATION_SHAPE_CONTRACTS"
            ),
            "generated_scenario_count": 0,
            "candidate_policy": "read_only_context_only",
            "required_scenario_contract": {
                "fixture_ownership": "test_owned",
                "bounded_row_ids": True,
                "approval_required": True,
                "checkpoints": ["confirm", "withdraw"],
                "cleanup": "withdraw",
                "unique_idempotency_key_per_mutation": True,
            },
        },
        "candidates": {
            "turnover_manual_closure_or_withdraw": turnover_candidates,
            "workbench_pair_withdraw_context": workbench_withdraw_contexts,
            "bank_flow_rule_batch_submit_context": bank_flow_candidates,
            "no_oa_bank_batch_withdraw_context": no_oa_candidates,
        },
        "safety": {
            "mutates_data": False,
            "requires_real_auth_to_apply": True,
            "requires_approval_ticket_before_apply": True,
            "approval_ticket_env": STANDARD_APPROVAL_TICKET_ENV,
            "approval_ticket": STANDARD_APPROVAL_TICKET,
            "approval_ticket_policy": "standing_ticket_allowed_for_controlled_reversible_smoke",
            "notes": [
                "Discovery is read-only and does not call mutating HTTP endpoints.",
                "Existing turnover and Workbench relations are context only; discovery never turns ordinary business facts into executable relation mutations.",
                "Only the current bank-flow submit owner may emit an executable discovery scenario.",
                "Reversible relation apply requires an explicit test-owned, bounded confirm-and-withdraw scenario with unique idempotency keys.",
                "Legacy no-OA candidates remain discovery-only context and are not part of current standard page coverage.",
                "Apply remains blocked until real OA/Admin auth and the standard approval ticket are supplied.",
            ],
        },
    }


def _write_scenario_output(report: dict[str, Any], path: Path) -> None:
    scenarios = list((report.get("scenario_json") or {}).get("scenarios") or [])
    if not scenarios:
        report["scenario_output"] = {
            "path": str(path),
            "written": False,
            "reason": "no_candidates",
            "message": "No approved write-operation candidates were discovered; do not run write_operation_e2e_smoke with an empty scenario file.",
        }
        return
    scenario_payload = {
        "version": 1,
        "generated_at": report["generated_at"],
        "standard_inputs": _standard_inputs_payload(),
        "page_write_scenario_policy": _page_write_scenario_policy_payload(),
        "scenarios": scenarios,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(scenario_payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    report["scenario_output"] = {
        "path": str(path),
        "written": True,
        "scenario_count": len(scenarios),
    }


def _turnover_withdraw_candidates(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          turnover.relation_id,
          coalesce(turnover.status, turnover.raw_payload->'normalized_payload'->>'status', turnover.raw_payload->>'status', '') as status,
          coalesce(
            turnover.relation_type,
            turnover.raw_payload->'normalized_payload'->>'relation_type',
            turnover.raw_payload->>'relation_type',
            turnover.raw_payload->'normalized_payload'->>'family',
            turnover.raw_payload->>'family',
            ''
          ) as relation_type,
          coalesce(
            turnover.raw_payload->'normalized_payload'->>'source',
            turnover.raw_payload->>'source',
            turnover.raw_payload->>'relation_source',
            ''
          ) as source,
          coalesce(workbench.month_scope::text, turnover.scope_month::text, left(coalesce(turnover.raw_payload->>'month', turnover.raw_payload->>'scope_month', ''), 10), '') as scope_month,
          turnover.version,
          turnover.updated_at,
          workbench.case_id,
          workbench.row_ids,
          array_length(workbench.row_ids, 1) as row_count,
          workbench.relation_mode
        from app.turnover_relations turnover
        join app.workbench_pair_relations workbench
          on workbench.case_id = 'turnover:' || turnover.relation_id
         and workbench.status = 'active'
         and array_length(workbench.row_ids, 1) between 2 and 6
         and workbench.month_scope is not null
        where turnover.relation_id is not null
          and coalesce(turnover.status, turnover.raw_payload->'normalized_payload'->>'status', turnover.raw_payload->>'status', '') not in ('withdrawn', 'cancelled')
          and coalesce(
            turnover.raw_payload->'normalized_payload'->>'source',
            turnover.raw_payload->>'source',
            turnover.raw_payload->>'relation_source',
            ''
          ) = 'manual'
        order by array_length(workbench.row_ids, 1), turnover.updated_at desc nulls last, turnover.relation_id
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
            "case_id": _text(row.get("case_id")),
            "row_ids": [_text(item) for item in list(row.get("row_ids") or []) if _text(item)],
            "row_count": row.get("row_count"),
            "relation_mode": _text(row.get("relation_mode")),
            "candidate_path": "/api/workbench/actions/withdraw-link",
            "risk": "existing_relation_withdraw_requires_manual_business_approval",
        }
        for row in rows
        if _text(row.get("relation_id")) and _text(row.get("case_id"))
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
          array_length(row_ids, 1) as row_count,
          version,
          updated_at
        from app.workbench_pair_relations
        where status = 'active'
          and relation_mode = 'manual_confirmed'
          and array_length(row_ids, 1) between 2 and 6
          and month_scope is not null
        order by array_length(row_ids, 1), updated_at desc nulls last, case_id
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
            "row_count": row.get("row_count"),
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
          batch.batch_id,
          batch.status,
          batch.status_bucket,
          batch.scope_month::text as scope_month,
          coalesce(cardinality(batch.bank_transaction_ids), 0) as row_count,
          count(*) over (partition by batch.scope_month) as month_batch_count,
          batch.version,
          batch.updated_at
        from app.no_oa_bank_batches batch
        join app.workbench_pair_relations relation
          on relation.case_id = coalesce(
                nullif(batch.raw_payload->'normalized_payload'->>'relation_case_id', ''),
                nullif(batch.raw_payload->>'relation_case_id', ''),
                batch.batch_id
             )
         and relation.status = 'active'
         and relation.relation_mode = 'no_oa_bank_batch'
        where batch.status = 'submitted'
          and batch.scope_month is not null
          and coalesce(
                nullif(batch.raw_payload->'normalized_payload'->>'relation_mode', ''),
                nullif(batch.raw_payload->>'relation_mode', ''),
                'no_oa_bank_batch'
              ) = 'no_oa_bank_batch'
          and coalesce(cardinality(batch.bank_transaction_ids), 0) between 1 and 6
        order by coalesce(cardinality(batch.bank_transaction_ids), 0),
                 count(*) over (partition by batch.scope_month),
                 batch.updated_at desc nulls last,
                 batch.batch_id
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
            "row_count": row.get("row_count"),
            "month_batch_count": row.get("month_batch_count"),
            "version": row.get("version"),
            "updated_at": str(row.get("updated_at") or ""),
            "candidate_path": f"/api/no-oa-bank-batches/{quote(_text(row.get('batch_id')), safe='')}/withdraw",
            "risk": "existing_no_oa_batch_withdraw_requires_manual_business_approval",
        }
        for row in rows
        if _text(row.get("batch_id"))
    ]


def _bank_flow_rule_batch_submit_candidates(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          batch.batch_id,
          batch.status,
          batch.status_bucket,
          batch.scope_month::text as scope_month,
          coalesce(cardinality(batch.bank_transaction_ids), 0) as row_count,
          batch.bank_transaction_ids,
          coalesce(
            nullif(batch.raw_payload->'normalized_payload'->>'batch_type', ''),
            nullif(batch.raw_payload->>'batch_type', ''),
            ''
          ) as batch_type,
          coalesce(
            nullif(batch.raw_payload->'normalized_payload'->>'batch_label', ''),
            nullif(batch.raw_payload->>'batch_label', ''),
            ''
          ) as batch_label,
          batch.version,
          batch.updated_at
        from app.bank_flow_rule_batches batch
        where coalesce(batch.status_bucket, batch.status, '') in ('draft', 'unsubmitted', 'candidate')
          and batch.scope_month is not null
          and coalesce(cardinality(batch.bank_transaction_ids), 0) between 1 and 10
          and not exists (
            select 1
            from app.workbench_pair_relations relation
            where relation.status = 'active'
              and relation.relation_mode = 'bank_flow_rule_batch'
              and relation.row_ids && batch.bank_transaction_ids
          )
        order by
          case
            when coalesce(
              nullif(batch.raw_payload->'normalized_payload'->>'batch_type', ''),
              nullif(batch.raw_payload->>'batch_type', ''),
              ''
            ) = 'fee' and coalesce(cardinality(batch.bank_transaction_ids), 0) = 10 then 0
            when coalesce(
              nullif(batch.raw_payload->'normalized_payload'->>'batch_type', ''),
              nullif(batch.raw_payload->>'batch_type', ''),
              ''
            ) = 'fee' then 1
            else 2
          end,
          coalesce(cardinality(batch.bank_transaction_ids), 0) desc,
          batch.updated_at desc nulls last,
          batch.batch_id
        limit %s
        """,
        (limit,),
    )
    return [
        {
            "operation_context": "bank_flow_rule_batch_submit",
            "batch_id": _text(row.get("batch_id")),
            "status": _text(row.get("status")),
            "status_bucket": _text(row.get("status_bucket")),
            "month": _month_text(row.get("scope_month")) or "all",
            "row_count": row.get("row_count"),
            "row_ids": [_text(item) for item in list(row.get("bank_transaction_ids") or []) if _text(item)],
            "batch_type": _text(row.get("batch_type")),
            "batch_label": _text(row.get("batch_label")),
            "version": row.get("version"),
            "updated_at": str(row.get("updated_at") or ""),
            "candidate_path": "/api/bank-flow-rule-batches/submit-selection",
            "risk": "bank_flow_submit_creates_relation_and_requires_controlled_withdraw_or_reset_after_smoke",
        }
        for row in rows
        if _text(row.get("batch_id")) and list(row.get("bank_transaction_ids") or [])
    ]


def _bank_flow_rule_batch_submit_scenario(candidate: dict[str, Any]) -> dict[str, Any]:
    batch_id = _text(candidate.get("batch_id"))
    month = _month_text(candidate.get("month")) or "all"
    row_ids = [_text(item) for item in list(candidate.get("row_ids") or []) if _text(item)]
    return {
        "name": f"bank-flow-rule-submit-{batch_id}",
        "operation": "bank_flow_rule_batch_submit",
        "steps": [
            {
                "name": "submit_selection",
                "method": "POST",
                "path": "/api/bank-flow-rule-batches/submit-selection",
                "json": {
                    "transaction_ids": row_ids,
                    "note": "controlled runtime sync SLO smoke bank-flow submit under standing ticket",
                },
                "expected_statuses": [200],
            }
        ],
        "post_api_probes": [
            {
                "name": "bank_flow_rule_batches_submitted",
                "path": f"/api/bank-flow-rule-batches?month={quote(month, safe='')}&bucket=submitted&page=1&page_size=50",
                "expected_statuses": [200, 202],
                "target_ms": 1000,
            },
            *_workbench_paired_probes(month),
            *_bank_relation_fanout_probes(month),
            {
                "name": "operations_app_health_dashboard",
                "path": "/api/operations/app-health-dashboard",
                "expected_statuses": [200, 202],
                "target_ms": 1000,
            },
        ],
        "metadata": {
            **_standard_scenario_metadata("bank-flow-rule-batches"),
            "candidate_batch_id": batch_id,
            "candidate_batch_type": candidate.get("batch_type"),
            "candidate_batch_label": candidate.get("batch_label"),
            "candidate_month": month,
            "candidate_row_count": candidate.get("row_count"),
            "risk": candidate.get("risk"),
        },
    }


def _workbench_paired_probes(month: str) -> list[dict[str, Any]]:
    month_scope = _month_text(month) or "all"
    return [
        {
            "name": "workbench_groups_all_paired",
            "path": "/api/workbench/groups?month=all&zone=paired&page=1&page_size=50&detail_level=summary",
            "expected_statuses": [200, 202],
            "target_ms": 1000,
        },
        {
            "name": "workbench_groups_month_paired",
            "path": (
                f"/api/workbench/groups?month={quote(month_scope, safe='')}"
                "&zone=paired&page=1&page_size=50&detail_level=summary"
            ),
            "expected_statuses": [200, 202],
            "target_ms": 1000,
        },
    ]


def _bank_relation_fanout_probes(month: str) -> list[dict[str, Any]]:
    month_scope = _month_text(month) or "all"
    return [
        {
            "name": "bank_details_transactions",
            "path": "/api/bank-details/transactions?date_from=2026-01-01&date_to=2026-12-31&page=1&page_size=50",
            "expected_statuses": [200, 202],
            "target_ms": 1000,
        },
        {
            "name": "pending_invoices_rows",
            "path": "/api/pending-invoices/rows?direction=expense&page=1&page_size=50&sort_field=trade_date&sort_direction=desc",
            "expected_statuses": [200, 202],
            "target_ms": 1000,
        },
        {
            "name": "cost_statistics_explorer",
            "path": f"/api/cost-statistics/explorer?scope={quote(month_scope, safe='')}&view=time&project_scope=active",
            "expected_statuses": [200, 202],
            "target_ms": 1000,
        },
        {
            "name": "search_all",
            "path": "/api/search?q=%E5%85%AC%E5%8F%B8&scope=all&month=all&limit=5",
            "expected_statuses": [200, 202],
            "target_ms": 1000,
        },
    ]


def _standard_inputs_payload() -> dict[str, str]:
    return {
        "scenario_env": STANDARD_SCENARIO_ENV,
        "scenario_path": STANDARD_SCENARIO_PATH,
        "approval_ticket_env": STANDARD_APPROVAL_TICKET_ENV,
        "approval_ticket": STANDARD_APPROVAL_TICKET,
    }


def _page_write_scenario_policy_payload() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for policy in STANDARD_PAGE_WRITE_SCENARIO_POLICIES:
        apply_policy = str(policy["apply_policy"])
        standard_apply = apply_policy in {"standing_apply", "fanout_evidence"}
        payload.append(
            {
                "page_key": policy["page_key"],
                "apply_policy": apply_policy,
                "scenario_operations": list(policy["scenario_operations"]),
                "scenario_env": STANDARD_SCENARIO_ENV if standard_apply else "",
                "scenario_path": STANDARD_SCENARIO_PATH if standard_apply else "",
                "approval_ticket_env": STANDARD_APPROVAL_TICKET_ENV if standard_apply else "",
                "approval_ticket": STANDARD_APPROVAL_TICKET if standard_apply else "",
                "approval_ticket_policy": (
                    "standing_ticket_allowed_for_controlled_reversible_smoke"
                    if standard_apply
                    else "standing_ticket_not_allowed_use_staging_or_single_use_approval"
                ),
            }
        )
    return payload


def _standard_scenario_metadata(page_key: str) -> dict[str, str]:
    return {
        "page_key": page_key,
        "scenario_env": STANDARD_SCENARIO_ENV,
        "scenario_path": STANDARD_SCENARIO_PATH,
        "approval_ticket_env": STANDARD_APPROVAL_TICKET_ENV,
        "approval_ticket": STANDARD_APPROVAL_TICKET,
        "approval_ticket_policy": "standing_ticket_allowed_for_controlled_reversible_smoke",
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
