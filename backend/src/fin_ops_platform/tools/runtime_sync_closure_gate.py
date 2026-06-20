from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConfigurationError, PostgresConnection, PostgresSettings
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository
from fin_ops_platform.tools import (
    health_ready_payload_probe,
    http_slo_probe,
    read_model_slo_smoke,
    sse_smoke_probe,
    write_operation_e2e_smoke,
    write_operation_slo_audit,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report, write_json_report


PASS = "pass"
FAIL = "fail"
SKIP = "skip"
WRITE_E2E_REQUIRED_ARGS = ("--write-scenario", "--apply-write-scenarios", "--write-approval-ticket")
RUNTIME_HEALTH_REQUIRED_FIELDS = (
    "queue_backlog",
    "dirty_scopes",
    "failed_jobs",
    "stale_dirty_scope_count",
    "missing_required_worker_count",
    "stale_required_worker_count",
    "mismatched_required_worker_count",
    "read_model_refresh_failure_rate",
    "worker_metrics",
)


@dataclass(frozen=True)
class ClosureCheck:
    name: str
    status: str
    detail: str
    payload: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the production runtime sync closure gate for all-page true freshness SLO.",
    )
    parser.add_argument("--base-url", default=os.getenv("FIN_OPS_HTTP_SLO_BASE_URL", "http://127.0.0.1:18001"))
    parser.add_argument("--api-prefix", default=os.getenv("FIN_OPS_HTTP_SLO_API_PREFIX", ""))
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--bearer-token", default=os.getenv("FIN_OPS_HTTP_SLO_BEARER_TOKEN", ""))
    parser.add_argument("--admin-token", default=os.getenv("FIN_OPS_HTTP_SLO_ADMIN_TOKEN", ""))
    parser.add_argument("--cookie", default=os.getenv("FIN_OPS_HTTP_SLO_COOKIE", ""))
    parser.add_argument("--allow-unauthenticated-http", action="store_true")
    parser.add_argument("--apply-read-model-smoke", action="store_true")
    parser.add_argument("--write-scenario", type=Path)
    parser.add_argument("--apply-write-scenarios", action="store_true")
    parser.add_argument(
        "--write-approval-ticket",
        default=os.getenv("FIN_OPS_WRITE_E2E_APPROVAL_TICKET", ""),
        help="Required with --apply-write-scenarios. Business approval reference for mutating write-operation smoke.",
    )
    parser.add_argument("--read-model-target-ms", type=float, default=1_000.0)
    parser.add_argument("--write-target-ms", type=float, default=1_000.0)
    parser.add_argument("--http-target-ms", type=float, default=1_000.0)
    parser.add_argument("--sse-target-ms", type=float, default=1_000.0)
    parser.add_argument("--health-ready-target-ms", type=float, default=health_ready_payload_probe.DEFAULT_TARGET_MS)
    parser.add_argument("--health-ready-max-response-bytes", type=int, default=health_ready_payload_probe.DEFAULT_MAX_RESPONSE_BYTES)
    parser.add_argument("--health-ready-max-api-performance-endpoints", type=int, default=health_ready_payload_probe.DEFAULT_MAX_API_PERFORMANCE_ENDPOINTS)
    parser.add_argument("--write-audit-lookback-hours", type=float, default=24.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=2_000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        connection = PostgresConnection(PostgresSettings.from_env())
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(tool="runtime_sync_closure_gate", message=str(exc))
        write_json_report(report, output=args.output, stdout=stdout)
        return 2
    headers = http_slo_probe._auth_headers(
        bearer_token=args.bearer_token or args.admin_token,
        admin_token="" if args.bearer_token else args.admin_token,
        cookie=args.cookie,
    )
    admin_headers = http_slo_probe._auth_headers(
        bearer_token="" if args.bearer_token else args.admin_token,
        admin_token=args.admin_token,
        cookie=args.cookie,
    )
    report = run_closure_gate(
        connection,
        base_url=str(args.base_url),
        api_prefix=str(args.api_prefix),
        tenant_id=str(args.tenant_id or "default"),
        headers=headers,
        admin_headers=admin_headers,
        allow_unauthenticated_http=bool(args.allow_unauthenticated_http),
        apply_read_model_smoke=bool(args.apply_read_model_smoke),
        write_scenario=args.write_scenario,
        apply_write_scenarios=bool(args.apply_write_scenarios),
        write_approval_ticket=str(args.write_approval_ticket or ""),
        read_model_target_ms=max(1.0, float(args.read_model_target_ms)),
        write_target_ms=max(1.0, float(args.write_target_ms)),
        http_target_ms=max(1.0, float(args.http_target_ms)),
        sse_target_ms=max(1.0, float(args.sse_target_ms)),
        health_ready_target_ms=max(1.0, float(args.health_ready_target_ms)),
        health_ready_max_response_bytes=max(1, int(args.health_ready_max_response_bytes)),
        health_ready_max_api_performance_endpoints=max(0, int(args.health_ready_max_api_performance_endpoints)),
        write_audit_lookback_hours=max(0.1, float(args.write_audit_lookback_hours)),
        timeout_seconds=max(1.0, float(args.timeout_seconds)),
        poll_interval_seconds=max(0.1, float(args.poll_interval_seconds)),
        limit=max(1, int(args.limit)),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    return 0 if report["status"] == PASS else 1


def run_closure_gate(
    connection: Any,
    *,
    base_url: str,
    api_prefix: str = "",
    tenant_id: str = "default",
    headers: Mapping[str, str] | None = None,
    admin_headers: Mapping[str, str] | None = None,
    allow_unauthenticated_http: bool = False,
    apply_read_model_smoke: bool = False,
    write_scenario: Path | None = None,
    apply_write_scenarios: bool = False,
    write_approval_ticket: str = "",
    read_model_target_ms: float = 1_000.0,
    write_target_ms: float = 1_000.0,
    http_target_ms: float = 1_000.0,
    sse_target_ms: float = 1_000.0,
    health_ready_target_ms: float = health_ready_payload_probe.DEFAULT_TARGET_MS,
    health_ready_max_response_bytes: int = health_ready_payload_probe.DEFAULT_MAX_RESPONSE_BYTES,
    health_ready_max_api_performance_endpoints: int = health_ready_payload_probe.DEFAULT_MAX_API_PERFORMANCE_ENDPOINTS,
    write_audit_lookback_hours: float = 24.0,
    timeout_seconds: float = 90.0,
    poll_interval_seconds: float = 0.5,
    limit: int = 2_000,
) -> dict[str, Any]:
    normalized_headers = {str(key): str(value) for key, value in dict(headers or {}).items() if str(value).strip()}
    normalized_admin_headers = {
        str(key): str(value)
        for key, value in dict(admin_headers or {}).items()
        if str(value).strip()
    }
    write_scenarios, write_scenario_error = _load_write_scenarios(write_scenario, http_target_ms=http_target_ms)
    write_audit_operations = _write_scenario_operations(write_scenarios)
    checks = [
        _runtime_health_check(connection),
        _read_model_smoke_check(
            connection,
            apply=apply_read_model_smoke,
            tenant_id=tenant_id,
            target_ms=read_model_target_ms,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        ),
        _http_slo_check(
            base_url=base_url,
            api_prefix=api_prefix,
            headers=normalized_headers,
            admin_headers=normalized_admin_headers,
            target_ms=http_target_ms,
            timeout_seconds=timeout_seconds,
            require_auth=not allow_unauthenticated_http,
        ),
        _sse_smoke_check(
            base_url=base_url,
            api_prefix=api_prefix,
            headers=normalized_headers,
            target_ms=sse_target_ms,
            timeout_seconds=timeout_seconds,
            require_auth=not allow_unauthenticated_http,
        ),
        _health_ready_payload_check(
            base_url=base_url,
            api_prefix=api_prefix,
            target_ms=health_ready_target_ms,
            timeout_seconds=timeout_seconds,
            max_response_bytes=health_ready_max_response_bytes,
            max_api_performance_endpoints=health_ready_max_api_performance_endpoints,
        ),
        _write_operation_audit_check(
            connection,
            tenant_id=tenant_id,
            target_ms=write_target_ms,
            lookback_hours=write_audit_lookback_hours,
            limit=limit,
            operations=write_audit_operations,
            scenario_error=write_scenario_error,
        ),
        _write_operation_e2e_check(
            connection,
            scenario_path=write_scenario,
            scenario_error=write_scenario_error,
            scenarios=write_scenarios,
            apply=apply_write_scenarios,
            approval_reference=write_approval_ticket,
            base_url=base_url,
            api_prefix=api_prefix,
            tenant_id=tenant_id,
            headers=normalized_headers,
            write_target_ms=write_target_ms,
            http_target_ms=http_target_ms,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            limit=limit,
        ),
    ]
    status = _overall_status(checks)
    return {
        "version": 1,
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "targets": {
            "page_api_first_response_p95_ms": http_target_ms,
            "sse_first_event_ms": sse_target_ms,
            "health_ready_payload_ms": health_ready_target_ms,
            "health_ready_max_response_bytes": health_ready_max_response_bytes,
            "health_ready_max_api_performance_endpoints": health_ready_max_api_performance_endpoints,
            "read_model_enqueue_to_fresh_ms": read_model_target_ms,
            "write_operation_enqueue_to_done_ms": write_target_ms,
            "write_operation_enqueue_to_done_p99_ms": write_operation_slo_audit.effective_p99_target_ms_for(
                write_target_ms,
                None,
            ),
        },
        "auth_configured": _auth_configured(normalized_headers) or _auth_configured(normalized_admin_headers),
        "apply_read_model_smoke": bool(apply_read_model_smoke),
        "apply_write_scenarios": bool(apply_write_scenarios),
        "write_approval_configured": bool(str(write_approval_ticket or "").strip()),
        "checks": [check.to_payload() for check in checks],
        "failed_checks": [check.name for check in checks if check.status == FAIL],
        "skipped_checks": [check.name for check in checks if check.status == SKIP],
    }


def _runtime_health_check(connection: Any) -> ClosureCheck:
    try:
        summary = RuntimeMonitoringRepository(connection).health_summary()
    except Exception as exc:
        return ClosureCheck("runtime_health", FAIL, "runtime monitoring health summary unavailable.", {"error": str(exc) or exc.__class__.__name__})
    missing_fields = [key for key in RUNTIME_HEALTH_REQUIRED_FIELDS if key not in summary]
    worker_metrics = summary.get("worker_metrics")
    if missing_fields or not isinstance(worker_metrics, list) or not worker_metrics:
        return ClosureCheck(
            "runtime_health",
            FAIL,
            "Runtime health summary is missing required durable queue or worker facts.",
            {
                "error": "runtime_health_missing_facts",
                "missing_fields": missing_fields,
                "worker_metric_count": len(worker_metrics) if isinstance(worker_metrics, list) else 0,
            },
        )
    blockers = _runtime_blockers(summary)
    return ClosureCheck(
        "runtime_health",
        PASS if not blockers else FAIL,
        "Runtime queue, worker, RabbitMQ and dirty-scope blockers are clear." if not blockers else "Runtime health has current blockers.",
        {
            "blockers": blockers,
            "snapshot": {
                key: summary.get(key)
                for key in (
                    "queue_backlog",
                    "failed_jobs",
                    "max_pending_age_seconds",
                    "stale_dirty_scope_count",
                    "missing_required_worker_count",
                    "stale_required_worker_count",
                    "mismatched_required_worker_count",
                    "rabbitmq_queue_depth",
                    "rabbitmq_unacked_messages",
                    "rabbitmq_dlq_count",
                    "read_model_refresh_failure_rate",
                )
                if key in summary
            },
        },
    )


def _read_model_smoke_check(
    connection: Any,
    *,
    apply: bool,
    tenant_id: str,
    target_ms: float,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> ClosureCheck:
    report = read_model_slo_smoke.run_smoke(
        connection,
        apply=apply,
        tenant_id=tenant_id,
        target_ms=target_ms,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    if not apply:
        return ClosureCheck(
            "read_model_direct_smoke",
            FAIL,
            "Direct read model smoke was not applied; final closure requires enqueue-to-fresh evidence.",
            _compact_report(report),
        )
    planned_scope_count = _safe_int(report.get("planned_scope_count"))
    result_count = _safe_int(report.get("result_count"))
    if report.get("status") == PASS and (planned_scope_count <= 0 or result_count <= 0):
        return ClosureCheck(
            "read_model_direct_smoke",
            FAIL,
            "Direct read model smoke produced no scope/result samples; final closure requires non-empty enqueue-to-fresh evidence.",
            {
                **_compact_report(report),
                "error": "read_model_smoke_empty_samples",
            },
        )
    return ClosureCheck(
        "read_model_direct_smoke",
        PASS if report.get("status") == PASS else FAIL,
        "All App Status read models converged within target." if report.get("status") == PASS else "One or more read models missed the direct-scope SLO.",
        _compact_report(report),
    )


def _http_slo_check(
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    admin_headers: Mapping[str, str],
    target_ms: float,
    timeout_seconds: float,
    require_auth: bool,
) -> ClosureCheck:
    report = http_slo_probe.collect_http_slo(
        base_url=base_url,
        api_prefix=api_prefix,
        headers=headers,
        admin_headers=admin_headers,
        iterations=3,
        warmup=1,
        timeout_seconds=min(max(1.0, timeout_seconds), 30.0),
        require_auth=require_auth,
        probes=http_slo_probe._with_target(
            [
                *[
                    http_slo_probe.HttpProbe(
                        name=http_slo_probe._page_probe_name(path, fallback_index=index),
                        path=path,
                        kind="page",
                        expected_statuses=(200,),
                        target_ms=target_ms,
                    )
                    for index, path in enumerate(http_slo_probe.DEFAULT_PAGE_PATHS, start=1)
                ],
                *http_slo_probe.DEFAULT_API_PROBES,
            ],
            target_ms,
        ),
    )
    if report.get("status") == "auth_missing":
        return ClosureCheck(
            "authenticated_http_slo",
            FAIL,
            "Authenticated page/API SLO cannot be proven without a real OA token or Admin-Token cookie.",
            _compact_report(report),
        )
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    probe_count = _safe_int(summary.get("probe_count"))
    sample_count = _safe_int(summary.get("sample_count"))
    if report.get("status") == PASS and (probe_count <= 0 or sample_count <= 0):
        return ClosureCheck(
            "authenticated_http_slo",
            FAIL,
            "Authenticated HTTP SLO produced no probe/sample evidence; final closure requires non-empty page/API samples.",
            {
                **_compact_report(report),
                "error": "http_slo_empty_samples",
            },
        )
    return ClosureCheck(
        "authenticated_http_slo",
        PASS if report.get("status") == PASS else FAIL,
        "Authenticated page shells and first-screen APIs met p95 target." if report.get("status") == PASS else "Authenticated HTTP SLO failed.",
        _compact_report(report),
    )


def _sse_smoke_check(
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    target_ms: float,
    timeout_seconds: float,
    require_auth: bool,
) -> ClosureCheck:
    report = sse_smoke_probe.collect_sse_smoke(
        base_url=base_url,
        api_prefix=api_prefix,
        headers=headers,
        timeout_seconds=min(max(1.0, timeout_seconds), 30.0),
        require_auth=require_auth,
        probes=[
            sse_smoke_probe.SseProbe(
                probe.name,
                probe.path,
                probe.expected_event_prefixes,
                expected_statuses=probe.expected_statuses,
                target_ms=target_ms,
            )
            for probe in sse_smoke_probe.DEFAULT_SSE_PROBES
        ],
    )
    if report.get("status") == "auth_missing":
        return ClosureCheck(
            "sse_first_event_smoke",
            FAIL,
            "Authenticated SSE first-event smoke cannot be proven without a real OA token or Admin-Token cookie.",
            _compact_report(report),
        )
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    probe_count = _safe_int(summary.get("probe_count"))
    if report.get("status") == PASS and probe_count <= 0:
        return ClosureCheck(
            "sse_first_event_smoke",
            FAIL,
            "Authenticated SSE smoke produced no probe evidence; final closure requires non-empty first-event samples.",
            {
                **_compact_report(report),
                "error": "sse_smoke_empty_samples",
            },
        )
    return ClosureCheck(
        "sse_first_event_smoke",
        PASS if report.get("status") == PASS else FAIL,
        "Authenticated App Health and Workbench SSE first events met target." if report.get("status") == PASS else "Authenticated SSE first-event smoke failed.",
        _compact_report(report),
    )


def _health_ready_payload_check(
    *,
    base_url: str,
    api_prefix: str,
    target_ms: float,
    timeout_seconds: float,
    max_response_bytes: int,
    max_api_performance_endpoints: int,
) -> ClosureCheck:
    report = health_ready_payload_probe.collect_health_ready_payload(
        base_url=base_url,
        api_prefix=api_prefix,
        target_ms=target_ms,
        timeout_seconds=min(max(1.0, timeout_seconds), 30.0),
        max_response_bytes=max_response_bytes,
        max_api_performance_endpoints=max_api_performance_endpoints,
    )
    return ClosureCheck(
        "health_ready_payload",
        PASS if report.get("status") == PASS else FAIL,
        "/health/ready is fast, JSON, and bounded." if report.get("status") == PASS else "/health/ready payload gate failed.",
        _compact_report(report),
    )


def _write_operation_audit_check(
    connection: Any,
    *,
    tenant_id: str,
    target_ms: float,
    lookback_hours: float,
    limit: int,
    operations: Sequence[str] | None = None,
    scenario_error: dict[str, Any] | None = None,
) -> ClosureCheck:
    if scenario_error is not None:
        return ClosureCheck(
            "write_operation_audit",
            FAIL,
            "Write-operation audit cannot be limited to approved scenario operations because the scenario file is invalid.",
            scenario_error,
        )
    report = write_operation_slo_audit.audit_write_operation_slo(
        connection,
        tenant_id=tenant_id,
        lookback_hours=lookback_hours,
        target_ms=target_ms,
        limit=limit,
        operations=operations,
    )
    targeted = bool(operations)
    event_sample_count = _safe_int(report.get("event_sample_count"))
    expectation_count = _safe_int(report.get("expectation_count"))
    if report.get("status") == PASS and (event_sample_count <= 0 or expectation_count <= 0):
        return ClosureCheck(
            "write_operation_audit",
            FAIL,
            "Write-operation audit produced no event or expectation samples; final closure requires non-empty durable write evidence.",
            {
                **_compact_report(report),
                "error": "write_operation_audit_empty_samples",
            },
        )
    return ClosureCheck(
        "write_operation_audit",
        PASS if report.get("status") == PASS else FAIL,
        (
            "Recent approved scenario write-operation outbox samples satisfy the SLO."
            if targeted and report.get("status") == PASS
            else "Recent real write-operation outbox samples satisfy the SLO."
            if report.get("status") == PASS
            else "Recent approved scenario write-operation outbox samples are missing or outside SLO."
            if targeted
            else "Recent real write-operation outbox samples are missing or outside SLO."
        ),
        _compact_report(report),
    )


def _write_operation_e2e_check(
    connection: Any,
    *,
    scenario_path: Path | None,
    scenario_error: dict[str, Any] | None,
    scenarios: Sequence[Any] | None,
    apply: bool,
    approval_reference: str,
    base_url: str,
    api_prefix: str,
    tenant_id: str,
    headers: Mapping[str, str],
    write_target_ms: float,
    http_target_ms: float,
    timeout_seconds: float,
    poll_interval_seconds: float,
    limit: int,
) -> ClosureCheck:
    if scenario_path is None:
        return ClosureCheck(
            "write_operation_e2e",
            FAIL,
            "No controlled write-operation scenario was provided; final closure requires real mutating endpoint evidence.",
            {
                "status": "input_required",
                "missing_args": ["--write-scenario"],
                "required_args": list(WRITE_E2E_REQUIRED_ARGS),
            },
        )
    if scenario_error is not None:
        return ClosureCheck(
            "write_operation_e2e",
            FAIL,
            "Controlled write-operation scenario is invalid; final closure requires a valid approved scenario.",
            scenario_error,
        )
    loaded_scenarios = list(scenarios or [])
    if not apply:
        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            connection,
            scenarios=loaded_scenarios,
            apply=False,
            base_url=base_url,
            api_prefix=api_prefix,
            tenant_id=tenant_id,
            headers=headers,
            approval_reference=approval_reference,
            write_target_ms=write_target_ms,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            limit=limit,
        )
        return ClosureCheck(
            "write_operation_e2e",
            FAIL,
            "Write-operation scenario was only dry-run; final closure requires --apply-write-scenarios.",
            {
                **_compact_report(report),
                "missing_args": ["--apply-write-scenarios"],
                "required_args": list(WRITE_E2E_REQUIRED_ARGS),
            },
        )
    if not str(approval_reference or "").strip():
        return ClosureCheck(
            "write_operation_e2e",
            FAIL,
            "Write-operation scenario has --apply-write-scenarios but no business approval reference.",
            {
                "status": "approval_missing",
                "error": "write_operation_e2e_requires_approval_ticket",
                "missing_args": ["--write-approval-ticket"],
                "required_args": list(WRITE_E2E_REQUIRED_ARGS),
            },
        )
    report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
        connection,
        scenarios=loaded_scenarios,
        apply=True,
        base_url=base_url,
        api_prefix=api_prefix,
        tenant_id=tenant_id,
        headers=headers,
        approval_reference=approval_reference,
        write_target_ms=write_target_ms,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        limit=limit,
    )
    scenario_count = _safe_int(report.get("scenario_count"))
    result_count = len(report.get("results") or []) if isinstance(report.get("results"), list) else 0
    if report.get("status") == PASS and (scenario_count <= 0 or result_count <= 0):
        return ClosureCheck(
            "write_operation_e2e",
            FAIL,
            "Controlled write-operation E2E produced no scenario/result evidence; final closure requires non-empty mutating write samples.",
            {
                **_compact_report(report),
                "error": "write_operation_e2e_empty_samples",
            },
        )
    return ClosureCheck(
        "write_operation_e2e",
        PASS if report.get("status") == PASS else FAIL,
        "Controlled mutating write-operation scenarios met the SLO." if report.get("status") == PASS else "Controlled mutating write-operation scenarios failed or were not authenticated.",
        _compact_report(report),
    )


def _runtime_blockers(summary: Mapping[str, Any]) -> dict[str, Any]:
    blockers: dict[str, Any] = {}
    for key in ("missing_required_worker_count", "stale_required_worker_count", "mismatched_required_worker_count"):
        if int(summary.get(key) or 0) > 0:
            blockers[key] = summary.get(key)
    for key in ("rabbitmq_queue_depth", "rabbitmq_unacked_messages", "rabbitmq_dlq_count", "stale_dirty_scope_count", "failed_jobs"):
        if int(summary.get(key) or 0) > 0:
            blockers[key] = summary.get(key)
    queue_backlog = summary.get("queue_backlog")
    if isinstance(queue_backlog, dict) and any(int(value or 0) > 0 for value in queue_backlog.values()):
        blockers["queue_backlog"] = queue_backlog
    failure_rate = summary.get("read_model_refresh_failure_rate")
    if isinstance(failure_rate, (int, float)) and float(failure_rate) > 0:
        blockers["read_model_refresh_failure_rate"] = failure_rate
    return blockers


def _overall_status(checks: Sequence[ClosureCheck]) -> str:
    if any(check.status == FAIL for check in checks):
        return FAIL
    if any(check.status == SKIP for check in checks):
        return SKIP
    return PASS


def _auth_configured(headers: Mapping[str, str]) -> bool:
    return any(str(key).lower() in {"authorization", "cookie"} for key in headers)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load_write_scenarios(
    scenario_path: Path | None,
    *,
    http_target_ms: float,
) -> tuple[list[Any] | None, dict[str, Any] | None]:
    if scenario_path is None:
        return None, None
    try:
        return write_operation_e2e_smoke.load_scenarios(scenario_path, http_target_ms=http_target_ms), None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, {
            "status": "input_error",
            "error": "scenario_input_error",
            "message": str(exc) or exc.__class__.__name__,
            "scenario_path": str(scenario_path),
            "required_args": list(WRITE_E2E_REQUIRED_ARGS),
        }


def _write_scenario_operations(scenarios: Sequence[Any] | None) -> tuple[str, ...] | None:
    if not scenarios:
        return None
    operations: list[str] = []
    seen: set[str] = set()
    for scenario in scenarios:
        for operation in getattr(scenario, "operations", ()):
            normalized = str(operation or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            operations.append(normalized)
    return tuple(operations) or None


def _compact_report(report: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "status",
        "summary",
        "failed_count",
        "failed_scenario_count",
        "failed_probe_count",
        "event_sample_count",
        "expectation_count",
        "failed_expectation_count",
        "missing_expectation_count",
        "p99_target_ms",
        "planned_scope_count",
        "result_count",
        "scenario_count",
        "auth_configured",
        "error",
        "errors",
        "url",
        "elapsed_ms",
        "response_bytes",
        "health_status",
        "api_performance_endpoints_returned",
        "api_performance_endpoint_count",
        "api_performance_omitted_endpoint_count",
        "runtime_blockers",
        "runtime_blocker_count",
        "runtime_release_name",
    )
    payload = {key: report.get(key) for key in keys if key in report}
    if "results" in report and isinstance(report.get("results"), list):
        results = list(report.get("results") or [])
        payload["result_count"] = len(results)
        payload["failed_results"] = [item for item in results if isinstance(item, dict) and item.get("status") != PASS][:10]
        payload["slowest_results"] = _slowest_results(results)
    if "probes" in report and isinstance(report.get("probes"), list):
        probes = list(report.get("probes") or [])
        payload["failed_probes"] = [item for item in probes if isinstance(item, dict) and item.get("status") != PASS][:10]
        payload["slowest_probes"] = sorted(
            [
                {
                    "name": item.get("name"),
                    "kind": item.get("kind"),
                    "p95_ms": (item.get("duration_ms") or {}).get("p95") if isinstance(item.get("duration_ms"), dict) else None,
                    "first_event_ms": item.get("first_event_ms"),
                    "status": item.get("status"),
                    "status_counts": item.get("status_counts"),
                    "errors": item.get("errors"),
                }
                for item in probes
                if isinstance(item, dict)
            ],
            key=lambda item: float(item.get("p95_ms") or item.get("first_event_ms") or 0),
            reverse=True,
        )[:10]
    return payload


def _slowest_results(results: Sequence[Any]) -> list[dict[str, Any]]:
    sortable: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        value = (
            item.get("enqueue_to_fresh_ms")
            or item.get("p99_enqueue_to_done_ms")
            or item.get("p95_enqueue_to_done_ms")
            or item.get("max_enqueue_to_done_ms")
        )
        if value is None and isinstance(item.get("write_slo"), dict):
            nested = item["write_slo"].get("results")
            if isinstance(nested, list):
                sortable.extend(_slowest_results(nested))
            continue
        sortable.append(
            {
                "operation": item.get("operation"),
                "read_model_key": item.get("read_model_key"),
                "scope_type": item.get("scope_type"),
                "scope_key": item.get("scope_key") or item.get("latest_scope_key"),
                "status": item.get("status"),
                "latency_ms": value,
                "handler_duration_ms": item.get("handler_duration_ms"),
            }
        )
    return sorted(sortable, key=lambda item: float(item.get("latency_ms") or 0), reverse=True)[:10]


if __name__ == "__main__":
    raise SystemExit(main())
