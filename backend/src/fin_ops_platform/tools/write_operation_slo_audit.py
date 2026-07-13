from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from math import ceil
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence, TextIO

from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report, write_json_report


DEFAULT_TARGET_MS = 1_000.0
DEFAULT_P99_TARGET_MS = 3_000.0
DEFAULT_LOOKBACK_HOURS = 24.0
DEFAULT_LIMIT = 2_000
_REASON_SQL = "coalesce(e.payload->>'reason', e.raw_payload->>'reason', d.reason)"
_ACTION_NAME_SQL = """coalesce(
            e.payload->>'action_name',
            e.payload->'metadata'->>'action_name',
            e.raw_payload->>'action_name',
            e.raw_payload->'metadata'->>'action_name'
          )"""


@dataclass(frozen=True)
class OperationExpectation:
    operation: str
    scope_type: str
    reason: str
    action_names: tuple[str, ...] = ()
    required: bool = True
    event_type: str | None = None


@dataclass(frozen=True)
class OperationExpectationResult:
    operation: str
    event_type: str
    scope_type: str
    reason: str
    action_names: tuple[str, ...]
    required: bool
    status: str
    sample_count: int
    failed_sample_count: int
    p95_enqueue_to_done_ms: float | None
    p99_enqueue_to_done_ms: float | None
    max_enqueue_to_done_ms: float | None
    latest_scope_key: str | None
    latest_event_id: str | None
    latest_action_name: str | None
    latest_event_status: str | None
    latest_dirty_status: str | None
    latest_error: str | None = None


DEFAULT_OPERATION_EXPECTATIONS: tuple[OperationExpectation, ...] = (
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "turnover_ledger",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "workbench",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "workbench_relation",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "cost_statistics",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "search",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_relation_extra",
        "turnover_ledger",
        "turnover_relation_extra_changed",
        ("relation_extra_update", "turnover_relation_extra_update"),
    ),
    OperationExpectation(
        "turnover_tag_selection",
        "turnover_ledger",
        "turnover_ledger_tag_selection_changed",
        ("turnover_ledger_tag_selection_changed", "turnover_ledger_tag_selection_update"),
    ),
    OperationExpectation(
        "bank_row_tags_batch",
        "bank_detail",
        "bank_transaction_category_changed",
        ("bank_row_tags_batch", "turnover_bank_row_tags_batch"),
    ),
    OperationExpectation(
        "bank_row_tags_batch",
        "workbench",
        "workbench_scope_invalidated",
        ("bank_row_tags_batch", "turnover_bank_row_tags_batch"),
    ),
    OperationExpectation(
        "bank_row_tags_batch",
        "turnover_ledger",
        "turnover_relation_changed",
        ("bank_row_tags_batch", "turnover_bank_row_tags_batch"),
    ),
    OperationExpectation("bank_auto_tag_rules", "bank_detail", "bank_auto_tag_rules_changed_priority"),
    OperationExpectation("bank_category_confirmation", "bank_detail", "bank_detail_category_confirmation_changed"),
    OperationExpectation("no_oa_tag_selection", "no_oa_bank_batch", "no_oa_bank_batch_tag_selection_changed"),
    OperationExpectation("workbench_relation_confirm", "workbench", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_confirm", "workbench_relation", "workbench_pair_relation_changed"),
    OperationExpectation("workbench_relation_withdraw", "workbench", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_withdraw", "workbench_relation", "workbench_pair_relation_changed"),
    OperationExpectation("workbench_relation_confirm_bank_invoice", "workbench", "workbench_relation_changed"),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice", "workbench_relation", "workbench_pair_relation_changed"
    ),
    OperationExpectation("workbench_relation_withdraw_bank_invoice", "workbench", "workbench_relation_changed"),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice", "workbench_relation", "workbench_pair_relation_changed"
    ),
    OperationExpectation("workbench_relation_confirm_cross_page", "workbench", "workbench_relation_changed"),
    OperationExpectation(
        "workbench_relation_confirm_cross_page", "workbench_relation", "workbench_pair_relation_changed"
    ),
    OperationExpectation("workbench_relation_confirm_cross_page", "bank_detail", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_confirm_cross_page", "invoice_lifecycle", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_confirm_cross_page", "pending_invoice", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_confirm_cross_page", "input_invoice_usage", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_confirm_cross_page", "output_invoice_collection", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_confirm_cross_page", "oa_pending_payment", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_confirm_cross_page", "cost_statistics", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_confirm_cross_page", "search", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_withdraw_cross_page", "workbench", "workbench_relation_changed"),
    OperationExpectation(
        "workbench_relation_withdraw_cross_page", "workbench_relation", "workbench_pair_relation_changed"
    ),
    OperationExpectation("workbench_relation_withdraw_cross_page", "bank_detail", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_withdraw_cross_page", "invoice_lifecycle", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_withdraw_cross_page", "pending_invoice", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_withdraw_cross_page", "input_invoice_usage", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_withdraw_cross_page", "output_invoice_collection", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_withdraw_cross_page", "oa_pending_payment", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_withdraw_cross_page", "cost_statistics", "workbench_relation_changed"),
    OperationExpectation("workbench_relation_withdraw_cross_page", "search", "workbench_relation_changed"),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice_cross_page", "workbench", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice_cross_page", "workbench_relation", "workbench_pair_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice_cross_page", "bank_detail", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice_cross_page", "invoice_lifecycle", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice_cross_page", "pending_invoice", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice_cross_page", "input_invoice_usage", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice_cross_page", "output_invoice_collection", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice_cross_page", "oa_pending_payment", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_confirm_bank_invoice_cross_page", "cost_statistics", "workbench_relation_changed"
    ),
    OperationExpectation("workbench_relation_confirm_bank_invoice_cross_page", "search", "workbench_relation_changed"),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice_cross_page", "workbench", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice_cross_page", "workbench_relation", "workbench_pair_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice_cross_page", "bank_detail", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice_cross_page", "invoice_lifecycle", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice_cross_page", "pending_invoice", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice_cross_page", "input_invoice_usage", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice_cross_page", "output_invoice_collection", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice_cross_page", "oa_pending_payment", "workbench_relation_changed"
    ),
    OperationExpectation(
        "workbench_relation_withdraw_bank_invoice_cross_page", "cost_statistics", "workbench_relation_changed"
    ),
    OperationExpectation("workbench_relation_withdraw_bank_invoice_cross_page", "search", "workbench_relation_changed"),
    OperationExpectation(
        "turnover_relation_confirm_cross_page",
        "turnover_ledger",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure",),
    ),
    OperationExpectation(
        "turnover_relation_confirm_cross_page",
        "workbench",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure",),
    ),
    OperationExpectation(
        "turnover_relation_confirm_cross_page",
        "workbench_relation",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure",),
    ),
    OperationExpectation(
        "turnover_relation_confirm_cross_page",
        "cost_statistics",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure",),
    ),
    OperationExpectation(
        "turnover_relation_confirm_cross_page",
        "search",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure",),
    ),
    OperationExpectation(
        "turnover_relation_withdraw_cross_page",
        "turnover_ledger",
        "turnover_relation_changed",
        ("turnover_relation_withdraw",),
    ),
    OperationExpectation(
        "turnover_relation_withdraw_cross_page",
        "workbench",
        "turnover_relation_changed",
        ("turnover_relation_withdraw",),
    ),
    OperationExpectation(
        "turnover_relation_withdraw_cross_page",
        "workbench_relation",
        "turnover_relation_changed",
        ("turnover_relation_withdraw",),
    ),
    OperationExpectation(
        "turnover_relation_withdraw_cross_page",
        "cost_statistics",
        "turnover_relation_changed",
        ("turnover_relation_withdraw",),
    ),
    OperationExpectation(
        "turnover_relation_withdraw_cross_page",
        "search",
        "turnover_relation_changed",
        ("turnover_relation_withdraw",),
    ),
    OperationExpectation("pending_invoice_attach_existing_invoice", "workbench", "workbench_relation_changed"),
    OperationExpectation(
        "pending_invoice_attach_existing_invoice", "workbench_relation", "workbench_pair_relation_changed"
    ),
    OperationExpectation("pending_invoice_attach_existing_invoice", "bank_detail", "workbench_relation_changed"),
    OperationExpectation("pending_invoice_attach_existing_invoice", "invoice_lifecycle", "workbench_relation_changed"),
    OperationExpectation("pending_invoice_attach_existing_invoice", "pending_invoice", "workbench_relation_changed"),
    OperationExpectation(
        "pending_invoice_attach_existing_invoice", "input_invoice_usage", "workbench_relation_changed"
    ),
    OperationExpectation("pending_invoice_attach_existing_invoice", "search", "workbench_relation_changed"),
    OperationExpectation("pending_invoice_attach_existing_invoice_with_oa", "workbench", "workbench_relation_changed"),
    OperationExpectation(
        "pending_invoice_attach_existing_invoice_with_oa", "workbench_relation", "workbench_pair_relation_changed"
    ),
    OperationExpectation(
        "pending_invoice_attach_existing_invoice_with_oa", "bank_detail", "workbench_relation_changed"
    ),
    OperationExpectation(
        "pending_invoice_attach_existing_invoice_with_oa", "invoice_lifecycle", "workbench_relation_changed"
    ),
    OperationExpectation(
        "pending_invoice_attach_existing_invoice_with_oa", "pending_invoice", "workbench_relation_changed"
    ),
    OperationExpectation(
        "pending_invoice_attach_existing_invoice_with_oa", "input_invoice_usage", "workbench_relation_changed"
    ),
    OperationExpectation(
        "pending_invoice_attach_existing_invoice_with_oa", "oa_pending_payment", "workbench_relation_changed"
    ),
    OperationExpectation(
        "pending_invoice_attach_existing_invoice_with_oa", "cost_statistics", "workbench_relation_changed"
    ),
    OperationExpectation("pending_invoice_attach_existing_invoice_with_oa", "search", "workbench_relation_changed"),
    OperationExpectation("bank_flow_rule_batch_submit", "bank_flow_rule_batch", "workbench_relation_changed"),
    OperationExpectation("bank_flow_rule_batch_submit", "workbench", "workbench_relation_changed"),
    OperationExpectation("bank_flow_rule_batch_submit", "workbench_relation", "workbench_pair_relation_changed"),
    OperationExpectation("bank_flow_rule_batch_submit", "bank_detail", "workbench_relation_changed"),
    OperationExpectation("bank_flow_rule_batch_submit", "pending_invoice", "workbench_relation_changed"),
    OperationExpectation("bank_flow_rule_batch_submit", "cost_statistics", "workbench_relation_changed"),
    OperationExpectation("bank_flow_rule_batch_submit", "search", "workbench_relation_changed"),
    OperationExpectation("invoice_import_confirmed", "workbench", "import_state_changed"),
    OperationExpectation("invoice_import_confirmed", "workbench_relation", "import_state_changed"),
    OperationExpectation("invoice_import_confirmed", "invoice_lifecycle", "import_state_changed"),
    OperationExpectation("invoice_import_confirmed", "search", "import_state_changed"),
    OperationExpectation("invoice_import_confirmed", "pending_invoice", "import_state_changed"),
    OperationExpectation("invoice_import_confirmed", "input_invoice_usage", "import_state_changed", required=False),
    OperationExpectation(
        "invoice_import_confirmed", "output_invoice_collection", "import_state_changed", required=False
    ),
    OperationExpectation("invoice_import_confirmed", "oa_pending_payment", "import_state_changed"),
    OperationExpectation("invoice_import_confirmed", "cost_statistics", "import_state_changed"),
    OperationExpectation("invoice_import_confirmed", "tax_offset", "invoice_file_import_confirm"),
    OperationExpectation("bank_import_confirmed", "workbench", "import_state_changed"),
    OperationExpectation("bank_import_confirmed", "workbench_relation", "import_state_changed"),
    OperationExpectation("bank_import_confirmed", "invoice_lifecycle", "import_state_changed"),
    OperationExpectation("bank_import_confirmed", "search", "import_state_changed"),
    OperationExpectation("bank_import_confirmed", "pending_invoice", "import_state_changed"),
    OperationExpectation("bank_import_confirmed", "input_invoice_usage", "import_state_changed", required=False),
    OperationExpectation("bank_import_confirmed", "output_invoice_collection", "import_state_changed", required=False),
    OperationExpectation("bank_import_confirmed", "oa_pending_payment", "import_state_changed"),
    OperationExpectation("bank_import_confirmed", "bank_account_balance", "import_state_changed"),
    OperationExpectation("bank_import_confirmed", "cost_statistics", "import_state_changed"),
    OperationExpectation("bank_import_confirmed", "bank_detail", "import_facts_changed"),
    OperationExpectation("etc_import_confirmed", "workbench", "etc_invoice_import_confirm"),
    OperationExpectation("etc_import_confirmed", "workbench_relation", "etc_invoice_import_confirm"),
    OperationExpectation("etc_import_confirmed", "invoice_lifecycle", "etc_invoice_import_confirm"),
    OperationExpectation("etc_import_confirmed", "tax_offset", "etc_invoice_import_confirm"),
    OperationExpectation("etc_import_confirmed", "cost_statistics", "etc_invoice_import_confirm"),
    OperationExpectation(
        "no_oa_bank_batch_withdraw", "no_oa_bank_batch", "no_oa_bank_batch_changed", ("no_oa_bank_batch_withdraw",)
    ),
    OperationExpectation(
        "no_oa_bank_batch_withdraw", "workbench", "workbench_scope_invalidated", ("no_oa_bank_batch_withdraw",)
    ),
    OperationExpectation(
        "no_oa_bank_batch_withdraw", "workbench_relation", "no_oa_bank_batch_changed", ("no_oa_bank_batch_withdraw",)
    ),
    OperationExpectation(
        "no_oa_bank_batch_withdraw", "cost_statistics", "no_oa_bank_batch_changed", ("no_oa_bank_batch_withdraw",)
    ),
    OperationExpectation(
        "no_oa_bank_batch_withdraw", "search", "no_oa_bank_batch_changed", ("no_oa_bank_batch_withdraw",)
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit recent real write-operation read model refresh SLO from durable outbox events.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    parser.add_argument("--output", type=Path, help="Optional path to write the JSON report.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--lookback-hours", type=float, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument(
        "--since",
        help="Optional ISO timestamp lower bound for event created_at. When set, it overrides --lookback-hours.",
    )
    parser.add_argument("--target-ms", type=float, default=DEFAULT_TARGET_MS)
    parser.add_argument(
        "--p99-target-ms",
        type=float,
        help=(
            "P99 enqueue-to-done target. Defaults to max(--target-ms, 3000) so one-second "
            "P95 gates still enforce a three-second long-tail ceiling."
        ),
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--operation",
        action="append",
        default=[],
        help="Limit audit to one operation profile. Repeatable. Defaults to all built-in profiles.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        connection = PostgresConnection(PostgresSettings.from_env())
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(tool="write_operation_slo_audit", message=str(exc))
        write_json_report(report, output=args.output, stdout=stdout)
        return 2
    report = audit_write_operation_slo(
        connection,
        tenant_id=str(args.tenant_id or "default"),
        lookback_hours=max(0.1, float(args.lookback_hours)),
        since=_parse_since(args.since),
        target_ms=max(1.0, float(args.target_ms)),
        p99_target_ms=None if args.p99_target_ms is None else max(1.0, float(args.p99_target_ms)),
        limit=max(1, int(args.limit)),
        operations=args.operation,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    return 0 if report["status"] == "pass" else 1


def audit_write_operation_slo(
    connection: Any,
    *,
    tenant_id: str = "default",
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    since: datetime | None = None,
    target_ms: float = DEFAULT_TARGET_MS,
    p99_target_ms: float | None = None,
    limit: int = DEFAULT_LIMIT,
    operations: Sequence[str] | None = None,
) -> dict[str, Any]:
    expectations = _selected_expectations(operations)
    effective_p99_target_ms = effective_p99_target_ms_for(target_ms, p99_target_ms)
    rows = (
        recent_read_model_refresh_events_since(
            connection,
            tenant_id=tenant_id,
            started_at=since,
            limit=limit,
        )
        if since is not None
        else _recent_read_model_refresh_events(
            connection,
            tenant_id=tenant_id,
            lookback_hours=lookback_hours,
            limit=limit,
        )
    )
    results = evaluate_operation_expectations(
        rows,
        expectations=expectations,
        target_ms=target_ms,
        p99_target_ms=effective_p99_target_ms,
    )
    failures = [result for result in results if result.status not in {"pass", "skipped"}]
    missing = [result for result in results if result.status == "missing"]
    return {
        "version": 1,
        "status": "pass" if not failures else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "lookback_hours": lookback_hours,
        "since": since.isoformat() if since is not None else None,
        "target_ms": target_ms,
        "p99_target_ms": effective_p99_target_ms,
        "event_sample_count": len(rows),
        "expectation_count": len(expectations),
        "failed_expectation_count": len(failures),
        "missing_expectation_count": len(missing),
        "operations": sorted({expectation.operation for expectation in expectations}),
        "results": [asdict(result) for result in results],
    }


def evaluate_operation_expectations(
    rows: Sequence[dict[str, Any]],
    *,
    expectations: Sequence[OperationExpectation],
    target_ms: float,
    p99_target_ms: float | None = None,
    match_metadata: bool = True,
) -> list[OperationExpectationResult]:
    effective_p99_target_ms = effective_p99_target_ms_for(target_ms, p99_target_ms)
    return [
        _evaluate_expectation(
            expectation,
            rows,
            target_ms=target_ms,
            p99_target_ms=effective_p99_target_ms,
            match_metadata=match_metadata,
        )
        for expectation in expectations
    ]


def selected_expectations_for_operations(operations: Sequence[str] | None) -> list[OperationExpectation]:
    return _selected_expectations(operations)


def committed_workbench_outbox_event_ids(
    connection: Any,
    *,
    tenant_id: str,
    idempotency_key: str,
) -> list[str]:
    evidence = workbench_idempotency_evidence(
        connection,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
    )
    if evidence["status"] != "committed":
        raise ValueError("Workbench idempotency record is not committed")
    return list(evidence["outbox_event_ids"])


def workbench_idempotency_evidence(
    connection: Any,
    *,
    tenant_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    normalized_tenant_id = str(tenant_id or "").strip()
    normalized_idempotency_key = str(idempotency_key or "").strip()
    if not normalized_tenant_id or not normalized_idempotency_key:
        raise ValueError("tenant_id and idempotency_key are required")
    rows = connection.fetch_all(
        """
        select status, outbox_event_ids, response_payload
        from app.workbench_idempotency_records
        where tenant_id = %s
          and idempotency_key = %s
        """,
        (normalized_tenant_id, normalized_idempotency_key),
    )
    if len(rows) != 1:
        raise ValueError("expected exactly one Workbench idempotency record")
    row = rows[0]
    status = str(row.get("status") or "").strip()
    if status not in {"reserved", "committed", "failed"}:
        raise ValueError("Workbench idempotency record has invalid status")
    raw_event_ids = row.get("outbox_event_ids")
    if status == "committed" and not isinstance(raw_event_ids, list):
        raise ValueError("committed Workbench idempotency record has invalid outbox_event_ids")
    event_ids = _exact_event_ids(raw_event_ids) if status == "committed" else []
    response_payload = row.get("response_payload")
    if response_payload is None:
        response_payload = {}
    if not isinstance(response_payload, dict):
        raise ValueError("Workbench idempotency record has invalid response_payload")
    return {
        "status": status,
        "outbox_event_ids": event_ids,
        "response_payload": dict(response_payload),
    }


def recent_read_model_refresh_events_since(
    connection: Any,
    *,
    tenant_id: str,
    started_at: Any,
    limit: int,
    expectations: Sequence[OperationExpectation] | None = None,
    event_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    expectation_filter_sql, expectation_params = _expectation_filter_sql(expectations)
    event_filter_sql = ""
    event_params: tuple[Any, ...] = ()
    time_filter_sql = "and e.created_at >= %s"
    time_params: tuple[Any, ...] = (started_at,)
    if event_ids is not None:
        exact_event_ids = _exact_event_ids(event_ids)
        event_filter_sql = "and e.id::text = any(%s)"
        event_params = (exact_event_ids,)
        # The transactional receipt is the causal boundary. A refresh enqueue may
        # deduplicate onto an already-pending durable event created before the HTTP
        # request, so applying the fallback time window would discard valid receipt
        # evidence even though the exact event id is known.
        time_filter_sql = ""
        time_params = ()
        # Exact receipt ids already provide the causal selector. Metadata on an
        # active event can predate the current request when the durable queue
        # deduplicates onto that event, so reason/action filtering is only valid
        # for the fallback time-window query.
        expectation_filter_sql = ""
        expectation_params = ()
    rows = connection.fetch_all(
        f"""
        select
          e.id::text as event_id,
          e.tenant_id,
          e.event_type,
          e.scope_type,
          e.scope_key,
          {_REASON_SQL} as reason,
          {_ACTION_NAME_SQL} as action_name,
          e.status as event_status,
          e.source_version,
          e.created_at,
          e.available_at,
          e.processed_at,
          e.updated_at,
          e.last_error as event_last_error,
          e.raw_payload,
          d.status as dirty_status,
          d.last_error as dirty_last_error
        from job.outbox_events e
        left join job.read_model_dirty_scopes d
         on d.tenant_id = e.tenant_id
         and d.scope_type = e.scope_type
         and d.scope_key = e.scope_key
         and d.source_version = coalesce(e.source_version, 0)
        where e.tenant_id = %s
          and (e.event_type like '%%.read_model.refresh' or e.event_type = 'import.fact.changed')
          {time_filter_sql}
          {expectation_filter_sql}
          {event_filter_sql}
        order by e.created_at desc, e.id desc
        limit %s
        """,
        (tenant_id, *time_params, *expectation_params, *event_params, limit),
    )
    return [dict(row) for row in rows]


def _exact_event_ids(values: Sequence[Any]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError("outbox_event_ids must be a sequence of strings")
    event_ids = [str(value).strip() if isinstance(value, str) else "" for value in values]
    if not event_ids or any(not event_id for event_id in event_ids):
        raise ValueError("outbox_event_ids must contain non-empty strings")
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("outbox_event_ids must not contain duplicates")
    return event_ids


def _selected_expectations(operations: Sequence[str] | None) -> list[OperationExpectation]:
    requested = {str(operation or "").strip() for operation in list(operations or []) if str(operation or "").strip()}
    available = {expectation.operation for expectation in DEFAULT_OPERATION_EXPECTATIONS}
    unknown = sorted(requested - available)
    if unknown:
        raise ValueError(f"Unknown write-operation SLO profiles: {', '.join(unknown)}")
    return [
        expectation
        for expectation in DEFAULT_OPERATION_EXPECTATIONS
        if not requested or expectation.operation in requested
    ]


def _recent_read_model_refresh_events(
    connection: Any,
    *,
    tenant_id: str,
    lookback_hours: float,
    limit: int,
) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          e.id::text as event_id,
          e.tenant_id,
          e.event_type,
          e.scope_type,
          e.scope_key,
          coalesce(e.payload->>'reason', e.raw_payload->>'reason', d.reason) as reason,
          coalesce(
            e.payload->>'action_name',
            e.payload->'metadata'->>'action_name',
            e.raw_payload->>'action_name',
            e.raw_payload->'metadata'->>'action_name'
          ) as action_name,
          e.status as event_status,
          e.source_version,
          e.created_at,
          e.available_at,
          e.processed_at,
          e.updated_at,
          e.last_error as event_last_error,
          e.raw_payload,
          d.status as dirty_status,
          d.last_error as dirty_last_error
        from job.outbox_events e
        left join job.read_model_dirty_scopes d
         on d.tenant_id = e.tenant_id
         and d.scope_type = e.scope_type
         and d.scope_key = e.scope_key
         and d.source_version = coalesce(e.source_version, 0)
        where e.tenant_id = %s
          and (e.event_type like '%%.read_model.refresh' or e.event_type = 'import.fact.changed')
          and e.created_at >= now() - (%s * interval '1 hour')
        order by e.created_at desc, e.id desc
        limit %s
        """,
        (tenant_id, lookback_hours, limit),
    )
    return [dict(row) for row in rows]


def _expectation_filter_sql(expectations: Sequence[OperationExpectation] | None) -> tuple[str, tuple[Any, ...]]:
    if not expectations:
        return "", ()
    clauses: list[str] = []
    params: list[Any] = []
    for expectation in expectations:
        expected_event_type = expectation.event_type or f"{expectation.scope_type}.read_model.refresh"
        clause = f"(e.event_type = %s and e.scope_type = %s and {_REASON_SQL} = %s"
        params.extend([expected_event_type, expectation.scope_type, expectation.reason])
        action_names = [name for name in expectation.action_names if str(name or "").strip()]
        if action_names:
            clause += f" and {_ACTION_NAME_SQL} = any(%s)"
            params.append(action_names)
        clause += ")"
        clauses.append(clause)
    return f"and ({' or '.join(clauses)})", tuple(params)


def _evaluate_expectation(
    expectation: OperationExpectation,
    rows: Sequence[dict[str, Any]],
    *,
    target_ms: float,
    p99_target_ms: float,
    match_metadata: bool = True,
) -> OperationExpectationResult:
    expected_event_type = expectation.event_type or f"{expectation.scope_type}.read_model.refresh"
    samples = [row for row in rows if event_matches_expectation(row, expectation, match_metadata=match_metadata)]
    latest = samples[0] if samples else {}
    if not samples:
        return OperationExpectationResult(
            operation=expectation.operation,
            event_type=expected_event_type,
            scope_type=expectation.scope_type,
            reason=expectation.reason,
            action_names=expectation.action_names,
            required=expectation.required,
            status="missing" if expectation.required else "skipped",
            sample_count=0,
            failed_sample_count=0,
            p95_enqueue_to_done_ms=None,
            p99_enqueue_to_done_ms=None,
            max_enqueue_to_done_ms=None,
            latest_scope_key=None,
            latest_event_id=None,
            latest_action_name=None,
            latest_event_status=None,
            latest_dirty_status=None,
            latest_error="no_recent_required_write_refresh_event" if expectation.required else None,
        )
    durations = [
        duration
        for duration in (
            _duration_ms(row.get("available_at") or row.get("created_at"), row.get("processed_at")) for row in samples
        )
        if duration is not None
    ]
    failed_samples = [
        row
        for row in samples
        if str(row.get("event_status") or "") != "done" or str(row.get("dirty_status") or "") not in {"", "done"}
    ]
    p95 = _percentile(durations, 0.95)
    p99 = _percentile(durations, 0.99)
    max_duration = max(durations) if durations else None
    latest_error = str(latest.get("event_last_error") or latest.get("dirty_last_error") or "").strip() or None
    if failed_samples:
        status = "fail"
    elif p95 is None:
        status = "fail"
        latest_error = latest_error or "missing_processed_at"
    elif p95 > target_ms:
        status = "fail"
        latest_error = latest_error or f"p95_enqueue_to_done_ms_exceeded_target:{p95}>{target_ms}"
    elif p99 is not None and p99 > p99_target_ms:
        status = "fail"
        latest_error = latest_error or f"p99_enqueue_to_done_ms_exceeded_target:{p99}>{p99_target_ms}"
    else:
        status = "pass"
    return OperationExpectationResult(
        operation=expectation.operation,
        event_type=expected_event_type,
        scope_type=expectation.scope_type,
        reason=expectation.reason,
        action_names=expectation.action_names,
        required=expectation.required,
        status=status,
        sample_count=len(samples),
        failed_sample_count=len(failed_samples),
        p95_enqueue_to_done_ms=p95,
        p99_enqueue_to_done_ms=p99,
        max_enqueue_to_done_ms=round(max_duration, 3) if max_duration is not None else None,
        latest_scope_key=str(latest.get("scope_key") or "") or None,
        latest_event_id=str(latest.get("event_id") or "") or None,
        latest_action_name=str(latest.get("action_name") or "") or None,
        latest_event_status=str(latest.get("event_status") or "") or None,
        latest_dirty_status=str(latest.get("dirty_status") or "") or None,
        latest_error=latest_error,
    )


def event_matches_expectation(
    row: Mapping[str, Any],
    expectation: OperationExpectation,
    *,
    match_metadata: bool = True,
) -> bool:
    expected_event_type = expectation.event_type or f"{expectation.scope_type}.read_model.refresh"
    if str(row.get("event_type") or "") != expected_event_type:
        return False
    if str(row.get("scope_type") or "") != expectation.scope_type:
        return False
    if not match_metadata:
        return True
    if str(row.get("reason") or "") != expectation.reason:
        return False
    return not expectation.action_names or str(row.get("action_name") or "") in set(expectation.action_names)


def _duration_ms(start: Any, end: Any) -> float | None:
    started = _coerce_datetime(start)
    ended = _coerce_datetime(end)
    if started is None or ended is None:
        return None
    return round(max(0.0, (ended - started).total_seconds() * 1000), 3)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if not value:
        return None
    text = str(value).strip().replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_since(value: str | None) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = _coerce_datetime(str(value).strip())
    if parsed is None:
        raise ValueError(f"Invalid --since timestamp: {value}")
    return parsed


def effective_p99_target_ms_for(target_ms: float, p99_target_ms: float | None) -> float:
    if p99_target_ms is not None:
        return max(1.0, float(p99_target_ms))
    return max(float(target_ms), DEFAULT_P99_TARGET_MS)


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 3)


if __name__ == "__main__":
    raise SystemExit(main())
