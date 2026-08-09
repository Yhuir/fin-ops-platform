from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
from time import monotonic, sleep
from typing import Any, Mapping, Sequence, TextIO
from uuid import uuid4

from fin_ops_platform.services.api_performance_metrics import ApiPerformanceRecorder
from fin_ops_platform.services.operations_dashboard import OperationsDashboardService
from fin_ops_platform.services.postgres_connection import PostgresConfigurationError, PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.runtime_worker_registry import rabbitmq_dispatch_event_types
from fin_ops_platform.tools import (
    health_ready_payload_probe,
    http_slo_probe,
    write_operation_e2e_smoke,
    write_operation_slo_audit,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report, write_json_report


PASS = "pass"
FAIL = "fail"
SKIP = "skip"
GATE_PROFILES = ("preflight", "full", "stability")
STANDALONE_WRITE_E2E_REQUIRED_ARGS = ("--scenario", "--apply", "--approval-ticket")
RUNTIME_HEALTH_REQUIRED_FIELDS = (
    "queue_backlog",
    "dirty_scopes",
    "failed_jobs",
    "rabbitmq_unpublished_backlog",
    "rabbitmq_publishing_backlog",
    "rabbitmq_publish_failed_backlog",
    "stale_dirty_scope_count",
    "missing_required_worker_count",
    "stale_required_worker_count",
    "mismatched_required_worker_count",
    "worker_metrics",
    "rabbitmq_management_configured",
    "rabbitmq_queue_depth",
    "rabbitmq_unacked_messages",
    "rabbitmq_dlq_count",
    "rabbitmq_queues",
)
CANDIDATE_AUDIT_BOOTSTRAP_ERRORS = frozenset(
    {
        "system_audit_business_pages_failed",
        "system_audit_internal_gate_failed",
        "system_audit_page_count_or_contract_failed",
    }
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
    parser.add_argument(
        "--page-base-url",
        default=os.getenv("FIN_OPS_HTTP_SLO_PAGE_BASE_URL", ""),
        help="Optional public page origin. API/write probes continue to use --base-url.",
    )
    parser.add_argument("--api-prefix", default=os.getenv("FIN_OPS_HTTP_SLO_API_PREFIX", ""))
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--bearer-token", default=os.getenv("FIN_OPS_HTTP_SLO_BEARER_TOKEN", ""))
    parser.add_argument("--admin-token", default=os.getenv("FIN_OPS_HTTP_SLO_ADMIN_TOKEN", ""))
    parser.add_argument("--cookie", default=os.getenv("FIN_OPS_HTTP_SLO_COOKIE", ""))
    parser.add_argument("--allow-unauthenticated-http", action="store_true")
    parser.add_argument("--profile", choices=GATE_PROFILES, default="full")
    # ponytail: accept the retired flag until the pinned production helper is replaced.
    parser.add_argument("--apply-read-model-smoke", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--read-model-target-ms", type=float, default=1_000.0)
    parser.add_argument("--write-target-ms", type=float, default=1_000.0)
    parser.add_argument("--http-target-ms", type=float, default=1_000.0)
    parser.add_argument("--health-ready-target-ms", type=float, default=health_ready_payload_probe.DEFAULT_TARGET_MS)
    parser.add_argument("--health-ready-max-response-bytes", type=int, default=health_ready_payload_probe.DEFAULT_MAX_RESPONSE_BYTES)
    parser.add_argument("--health-ready-max-api-performance-endpoints", type=int, default=health_ready_payload_probe.DEFAULT_MAX_API_PERFORMANCE_ENDPOINTS)
    parser.add_argument("--write-audit-lookback-hours", type=float, default=24.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=2_000)
    parser.add_argument(
        "--required-worker-instance",
        action="append",
        default=[],
        help="Override the required worker inventory used by runtime health checks.",
    )
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
        page_base_url=str(args.page_base_url or args.base_url),
        api_prefix=str(args.api_prefix),
        tenant_id=str(args.tenant_id or "default"),
        headers=headers,
        admin_headers=admin_headers,
        allow_unauthenticated_http=bool(args.allow_unauthenticated_http),
        profile=str(args.profile),
        read_model_target_ms=max(1.0, float(args.read_model_target_ms)),
        write_target_ms=max(1.0, float(args.write_target_ms)),
        http_target_ms=max(1.0, float(args.http_target_ms)),
        health_ready_target_ms=max(1.0, float(args.health_ready_target_ms)),
        health_ready_max_response_bytes=max(1, int(args.health_ready_max_response_bytes)),
        health_ready_max_api_performance_endpoints=max(0, int(args.health_ready_max_api_performance_endpoints)),
        write_audit_lookback_hours=max(0.1, float(args.write_audit_lookback_hours)),
        timeout_seconds=max(1.0, float(args.timeout_seconds)),
        poll_interval_seconds=max(0.05, float(args.poll_interval_seconds)),
        limit=max(1, int(args.limit)),
        required_worker_instances={
            str(instance).strip()
            for instance in args.required_worker_instance
            if str(instance).strip()
        } or None,
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
    page_base_url: str | None = None,
    api_prefix: str = "",
    tenant_id: str = "default",
    headers: Mapping[str, str] | None = None,
    admin_headers: Mapping[str, str] | None = None,
    allow_unauthenticated_http: bool = False,
    profile: str = "full",
    read_model_target_ms: float = 1_000.0,
    write_target_ms: float = 1_000.0,
    http_target_ms: float = 1_000.0,
    health_ready_target_ms: float = health_ready_payload_probe.DEFAULT_TARGET_MS,
    health_ready_max_response_bytes: int = health_ready_payload_probe.DEFAULT_MAX_RESPONSE_BYTES,
    health_ready_max_api_performance_endpoints: int = health_ready_payload_probe.DEFAULT_MAX_API_PERFORMANCE_ENDPOINTS,
    write_audit_lookback_hours: float = 24.0,
    timeout_seconds: float = 90.0,
    poll_interval_seconds: float = 0.5,
    limit: int = 2_000,
    required_worker_instances: set[str] | None = None,
) -> dict[str, Any]:
    if profile not in GATE_PROFILES:
        raise ValueError(f"unsupported release gate profile: {profile}")
    normalized_headers = {str(key): str(value) for key, value in dict(headers or {}).items() if str(value).strip()}
    normalized_admin_headers = {
        str(key): str(value)
        for key, value in dict(admin_headers or {}).items()
        if str(value).strip()
    }
    canonical_audit_headers = normalized_admin_headers or normalized_headers
    checks = [
        _postgres_reversible_write_check(
            connection,
            target_ms=min(write_target_ms, 1_000.0),
        )
    ]
    if profile == "preflight":
        checks.extend(
            [
                _runtime_health_check(
                    connection,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    required_worker_instances=required_worker_instances,
                ),
                _health_ready_payload_check(
                    base_url=base_url,
                    api_prefix=api_prefix,
                    target_ms=health_ready_target_ms,
                    timeout_seconds=timeout_seconds,
                    max_response_bytes=health_ready_max_response_bytes,
                    max_api_performance_endpoints=health_ready_max_api_performance_endpoints,
                ),
            ]
        )
    else:
        checks.extend(
            [
                _http_slo_check(
                    base_url=base_url,
                    page_base_url=page_base_url or base_url,
                    api_prefix=api_prefix,
                    headers=normalized_headers,
                    admin_headers=normalized_admin_headers,
                    target_ms=http_target_ms,
                    timeout_seconds=timeout_seconds,
                    require_auth=not allow_unauthenticated_http,
                    poll_interval_seconds=poll_interval_seconds,
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
                ),
            ]
        )
        if profile == "full":
            pre_final_health = _runtime_health_check(
                connection,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                name="runtime_health_before_final_convergence",
                required_worker_instances=required_worker_instances,
            )
            checks.append(pre_final_health)
        # Sample runtime convergence after every release-gate probe has completed.
        checks.append(
            _runtime_health_check(
                connection,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                required_worker_instances=required_worker_instances,
            )
        )
    # The canonical snapshot is the final proof after every queue-producing probe
    # and terminal publish reconciliation has converged.
    checks.append(
        _page_canonical_audit_check(
            connection,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=canonical_audit_headers,
            tenant_id=tenant_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            require_auth=not allow_unauthenticated_http,
            allow_compatible_previous_registry=profile == "preflight",
        )
    )
    status = _overall_status(checks)
    return {
        "version": 1,
        "profile": profile,
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "targets": {
            "page_api_first_response_p95_ms": http_target_ms,
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
        "checks": [check.to_payload() for check in checks],
        "failed_checks": [check.name for check in checks if check.status == FAIL],
        "skipped_checks": [check.name for check in checks if check.status == SKIP],
    }


def _runtime_health_check(
    connection: Any,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    name: str = "runtime_health",
    required_worker_instances: set[str] | None = None,
) -> ClosureCheck:
    deadline = monotonic() + max(0.0, timeout_seconds)
    monitoring_repository = RuntimeMonitoringRepository(connection)
    queue_repository = RuntimeQueueRepository(connection)
    reconciled_completed_publish_states = 0
    clean_samples_after_reconciliation = 0
    while True:
        try:
            reconciled = queue_repository.reconcile_completed_publish_states()
            reconciled_completed_publish_states += reconciled
            if reconciled > 0:
                clean_samples_after_reconciliation = 0
            elif reconciled_completed_publish_states > 0:
                clean_samples_after_reconciliation += 1
            summary = (
                monitoring_repository.ready_health_summary()
                if required_worker_instances is None
                else monitoring_repository.ready_health_summary(
                    required_worker_instances=required_worker_instances,
                )
            )
        except Exception as exc:
            return ClosureCheck(
                name,
                FAIL,
                "runtime queue reconciliation or monitoring health summary unavailable.",
                {"error": str(exc) or exc.__class__.__name__},
            )
        missing_fields = [key for key in RUNTIME_HEALTH_REQUIRED_FIELDS if key not in summary]
        worker_metrics = summary.get("worker_metrics")
        if missing_fields or not isinstance(worker_metrics, list) or not worker_metrics:
            return ClosureCheck(
                name,
                FAIL,
                "Runtime health summary is missing required durable queue or worker facts.",
                {
                    "error": "runtime_health_missing_facts",
                    "missing_fields": missing_fields,
                    "worker_metric_count": len(worker_metrics) if isinstance(worker_metrics, list) else 0,
                },
            )
        blockers = _runtime_blockers(summary)
        reconciliation_stable = (
            reconciled_completed_publish_states == 0
            or clean_samples_after_reconciliation > 0
        )
        timed_out = monotonic() >= deadline
        if not blockers and not reconciliation_stable and not timed_out:
            sleep(min(max(0.05, poll_interval_seconds), max(0.0, deadline - monotonic())))
            continue
        if not blockers and not reconciliation_stable:
            blockers = {
                "terminal_publish_reconciliation_not_stable": {
                    "reconciled_count": reconciled_completed_publish_states,
                    "clean_samples_after_reconciliation": clean_samples_after_reconciliation,
                }
            }
        if not blockers or timed_out:
            return ClosureCheck(
                name,
                PASS if not blockers else FAIL,
                "Runtime queue, worker, RabbitMQ and dirty-scope blockers are clear." if not blockers else "Runtime health did not converge before the gate deadline.",
                {
                    "blockers": blockers,
                    "reconciled_completed_publish_states": reconciled_completed_publish_states,
                    "clean_samples_after_reconciliation": clean_samples_after_reconciliation,
                    "terminal_publish_reconciliation_stable": reconciliation_stable,
                    "snapshot": {
                        key: summary.get(key)
                        for key in (
                            "queue_backlog",
                            "dirty_scopes",
                            "failed_jobs",
                            "rabbitmq_unpublished_backlog",
                            "rabbitmq_publishing_backlog",
                            "rabbitmq_publish_failed_backlog",
                            "max_pending_age_seconds",
                            "stale_dirty_scope_count",
                            "missing_required_worker_count",
                            "stale_required_worker_count",
                            "mismatched_required_worker_count",
                            "rabbitmq_queue_depth",
                            "rabbitmq_unacked_messages",
                            "rabbitmq_dlq_count",
                            "rabbitmq_queues",
                        )
                        if key in summary
                    },
                },
            )
        sleep(min(max(0.05, poll_interval_seconds), max(0.0, deadline - monotonic())))


def _http_slo_check(
    *,
    base_url: str,
    page_base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    admin_headers: Mapping[str, str],
    target_ms: float,
    timeout_seconds: float,
    require_auth: bool,
    poll_interval_seconds: float = 0.5,
) -> ClosureCheck:
    probes = http_slo_probe._with_target(
        [
            *[
                http_slo_probe.HttpProbe(
                    name=http_slo_probe._page_probe_name(path, fallback_index=index),
                    path=http_slo_probe.resolve_probe_url(page_base_url, path),
                    kind="page",
                    expected_statuses=(200,),
                    target_ms=target_ms,
                )
                for index, path in enumerate(http_slo_probe.DEFAULT_PAGE_PATHS, start=1)
            ],
            *http_slo_probe.DEFAULT_API_PROBES,
        ],
        target_ms,
        http_slo_probe.DEFAULT_P99_TARGET_MS,
    )
    started = monotonic()
    deadline = started + max(1.0, timeout_seconds)
    attempts = 0
    while True:
        attempts += 1
        report = http_slo_probe.collect_http_slo(
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            admin_headers=admin_headers,
            iterations=3,
            warmup=1,
            timeout_seconds=min(max(1.0, timeout_seconds), 30.0),
            require_auth=require_auth,
            probes=probes,
        )
        retryable_freshness = _http_slo_has_only_transient_freshness_failures(report)
        retryable_latency = attempts == 1 and _http_slo_has_only_single_window_latency_miss(report)
        if report.get("status") == PASS or not (retryable_freshness or retryable_latency):
            break
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(max(0.05, poll_interval_seconds), remaining))
    wait_payload = {
        "retry_attempts": max(0, attempts - 1),
        "retry_elapsed_ms": round(max(0.0, monotonic() - started) * 1000, 3),
    }
    if report.get("status") == "auth_missing":
        return ClosureCheck(
            "authenticated_http_slo",
            FAIL,
            "Authenticated page/API SLO cannot be proven without a real OA token or Admin-Token cookie.",
            {**_compact_report(report), **wait_payload},
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
                **wait_payload,
                "error": "http_slo_empty_samples",
            },
        )
    return ClosureCheck(
        "authenticated_http_slo",
        PASS if report.get("status") == PASS else FAIL,
        "Authenticated page shells and first-screen APIs met p95/p99 targets." if report.get("status") == PASS else "Authenticated HTTP SLO failed.",
        {**_compact_report(report), **wait_payload},
    )


def _http_slo_has_only_transient_freshness_failures(report: Mapping[str, Any]) -> bool:
    probes = report.get("probes")
    if report.get("status") != FAIL or not isinstance(probes, list):
        return False
    failed_probes = [
        probe
        for probe in probes
        if isinstance(probe, Mapping) and probe.get("status") != PASS
    ]
    return bool(failed_probes) and all(
        _safe_int(probe.get("failure_count")) == 0
        and not probe.get("errors")
        and probe.get("slo_pass") is True
        and probe.get("freshness_pass") is False
        and (
            bool(probe.get("non_fresh_read_model_statuses"))
            or _safe_int(probe.get("refresh_enqueued_count")) > 0
        )
        for probe in failed_probes
    )


def _http_slo_has_only_single_window_latency_miss(report: Mapping[str, Any]) -> bool:
    probes = report.get("probes")
    if report.get("status") != FAIL or not isinstance(probes, list):
        return False
    failed_probes = [
        probe
        for probe in probes
        if isinstance(probe, Mapping) and probe.get("status") != PASS
    ]
    return bool(failed_probes) and all(
        _safe_int(probe.get("failure_count")) == 0
        and not probe.get("errors")
        and probe.get("freshness_pass") is True
        and probe.get("p95_pass") is False
        and probe.get("p99_pass") is True
        for probe in failed_probes
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


def _postgres_reversible_write_check(
    connection: Any,
    *,
    target_ms: float,
) -> ClosureCheck:
    marker = uuid4().hex
    started = monotonic()
    try:
        with connection.transaction() as transaction:
            transaction.execute(
                """
                create temporary table finops_release_gate_write_probe (
                    marker text primary key
                ) on commit drop
                """
            )
            inserted = transaction.execute(
                """
                insert into pg_temp.finops_release_gate_write_probe (marker)
                values (%s)
                """,
                (marker,),
            )
            written = transaction.fetch_one(
                """
                select marker
                from pg_temp.finops_release_gate_write_probe
                where marker = %s
                """,
                (marker,),
            )
            deleted = transaction.execute(
                """
                delete from pg_temp.finops_release_gate_write_probe
                where marker = %s
                """,
                (marker,),
            )
            residue = transaction.fetch_one(
                """
                select marker
                from pg_temp.finops_release_gate_write_probe
                where marker = %s
                """,
                (marker,),
            )
    except Exception as exc:
        return ClosureCheck(
            "postgres_reversible_write",
            FAIL,
            "Isolated PostgreSQL write probe failed.",
            {
                "isolation": "pg_temp",
                "error": str(exc) or exc.__class__.__name__,
            },
        )
    elapsed_ms = round((monotonic() - started) * 1_000, 3)
    passed = (
        inserted == 1
        and written == {"marker": marker}
        and deleted == 1
        and residue is None
        and elapsed_ms <= target_ms
    )
    return ClosureCheck(
        "postgres_reversible_write",
        PASS if passed else FAIL,
        (
            "Isolated PostgreSQL write/read/delete probe met target without touching business rows."
            if passed
            else "Isolated PostgreSQL write probe did not prove reversible persistence within target."
        ),
        {
            "isolation": "pg_temp",
            "rows_inserted": inserted,
            "rows_deleted": deleted,
            "residue_count": 0 if residue is None else 1,
            "elapsed_ms": elapsed_ms,
            "target_ms": target_ms,
            **({"error": "postgres_reversible_write_invariant_failed"} if not passed else {}),
        },
    )


def _page_canonical_audit_check(
    connection: Any,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    tenant_id: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    require_auth: bool,
    allow_compatible_previous_registry: bool = False,
) -> ClosureCheck:
    if require_auth and not _auth_configured(headers):
        return ClosureCheck(
            "page_canonical_audit",
            FAIL,
            "Canonical page audit requires authenticated HTTP evidence.",
            {"error": "auth_required"},
        )
    checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
        name="release-gate-canonical-page-audit",
        operations=(),
        steps=(),
        system_audit_path=write_operation_e2e_smoke.SYSTEM_AUDIT_PATH,
    )
    audit = write_operation_e2e_smoke._wait_for_system_audit(
        checkpoint,
        base_url=base_url,
        api_prefix=api_prefix,
        headers=headers,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        request_fn=write_operation_e2e_smoke._http_request,
        excluded_audit_ids=set(),
        allow_compatible_previous_registry=allow_compatible_previous_registry,
    )
    verification_source = "current_http_api"
    candidate_audit: dict[str, Any] | None = None
    if audit.get("status") != PASS and audit.get("error") in CANDIDATE_AUDIT_BOOTSTRAP_ERRORS:
        candidate_audit = _candidate_system_audit(
            connection,
            tenant_id=tenant_id,
            timeout_seconds=timeout_seconds,
        )
        verification_source = "candidate_read_only_snapshot"
    passed = audit.get("status") == PASS or bool(candidate_audit and candidate_audit.get("status") == PASS)
    verified_audit = candidate_audit if candidate_audit and candidate_audit.get("status") == PASS else audit
    return ClosureCheck(
        "page_canonical_audit",
        PASS if passed else FAIL,
        (
            "Canonical page audit passed against one repeatable-read database snapshot."
            if passed
            else "Canonical page audit failed."
        ),
        {
            "status": PASS if passed else FAIL,
            "audit_count": 1 if passed else 0,
            "verification_source": verification_source,
            "system_audits": [verified_audit] if passed else [],
            "current_http_audit": audit,
            **({"candidate_audit": candidate_audit} if candidate_audit is not None else {}),
            **(
                {
                    "error": (
                        (candidate_audit or {}).get("error")
                        or audit.get("error")
                        or "page_canonical_audit_failed"
                    )
                }
                if not passed
                else {}
            ),
        },
    )


def _candidate_system_audit(
    connection: Any,
    *,
    tenant_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        report = PostgresOperationsAuditRepository(connection).audit_system(
            tenant_id=tenant_id,
            sample_limit=50,
            dashboard_payload_builder=lambda snapshot_connection: OperationsDashboardService(
                snapshot_connection,
                api_performance_recorder=ApiPerformanceRecorder(),
            ).build_payload(),
        )
    except Exception as exc:
        return {"status": FAIL, "error": str(exc) or exc.__class__.__name__}

    response = http_slo_probe.HttpProbeResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps(report, ensure_ascii=False, default=str).encode("utf-8"),
    )
    checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
        name="release-gate-candidate-canonical-page-audit",
        operations=(),
        steps=(),
        system_audit_path=write_operation_e2e_smoke.SYSTEM_AUDIT_PATH,
    )
    return write_operation_e2e_smoke._collect_system_audit(
        checkpoint,
        base_url="https://candidate-release.invalid",
        api_prefix="",
        headers={},
        timeout_seconds=timeout_seconds,
        request_fn=lambda *_args: response,
    )


def _write_operation_audit_check(
    connection: Any,
    *,
    tenant_id: str,
    target_ms: float,
    lookback_hours: float,
    limit: int,
    operations: Sequence[str] | None = None,
) -> ClosureCheck:
    report = write_operation_slo_audit.audit_write_operation_slo(
        connection,
        tenant_id=tenant_id,
        lookback_hours=lookback_hours,
        target_ms=target_ms,
        limit=limit,
        operations=operations,
    )
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
            "Recent real write-operation outbox samples satisfy the SLO."
            if report.get("status") == PASS
            else "Recent real write-operation outbox samples are missing or outside SLO."
        ),
        _compact_report(report),
    )


def _runtime_blockers(summary: Mapping[str, Any]) -> dict[str, Any]:
    blockers: dict[str, Any] = {}
    if summary.get("rabbitmq_management_configured") is not True:
        blockers["rabbitmq_management_configured"] = summary.get("rabbitmq_management_configured")
    if summary.get("rabbitmq_metric_error"):
        blockers["rabbitmq_metric_error"] = summary.get("rabbitmq_metric_error")
    for key in ("missing_required_worker_count", "stale_required_worker_count", "mismatched_required_worker_count"):
        if int(summary.get(key) or 0) > 0:
            blockers[key] = summary.get(key)
    for key in (
        "rabbitmq_queue_depth",
        "rabbitmq_unacked_messages",
        "rabbitmq_dlq_count",
        "rabbitmq_unpublished_backlog",
        "rabbitmq_publishing_backlog",
        "rabbitmq_publish_failed_backlog",
        "stale_dirty_scope_count",
        "failed_jobs",
    ):
        if int(summary.get(key) or 0) > 0:
            blockers[key] = summary.get(key)
    queue_backlog = summary.get("queue_backlog")
    if isinstance(queue_backlog, dict) and any(int(value or 0) > 0 for value in queue_backlog.values()):
        blockers["queue_backlog"] = queue_backlog
    dirty_scopes = summary.get("dirty_scopes")
    if isinstance(dirty_scopes, dict) and any(int(value or 0) > 0 for value in dirty_scopes.values()):
        blockers["dirty_scopes"] = dirty_scopes
    rabbitmq_queues = summary.get("rabbitmq_queues")
    if isinstance(rabbitmq_queues, Mapping):
        expected_event_types = rabbitmq_dispatch_event_types()
        missing_metrics = [
            event_type
            for event_type in expected_event_types
            if not isinstance(rabbitmq_queues.get(event_type), Mapping)
        ]
        without_consumers = [
            event_type
            for event_type in expected_event_types
            if isinstance(rabbitmq_queues.get(event_type), Mapping)
            and _safe_int(rabbitmq_queues[event_type].get("consumers")) <= 0
        ]
        if missing_metrics:
            blockers["rabbitmq_queue_metrics_missing"] = missing_metrics
        if without_consumers:
            blockers["rabbitmq_queues_without_consumers"] = without_consumers
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
        scenarios = write_operation_e2e_smoke.load_scenarios(
            scenario_path,
            http_target_ms=http_target_ms,
        )
        _validate_release_write_scenarios(scenarios)
        return scenarios, None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, {
            "status": "input_error",
            "error": "scenario_input_error",
            "message": str(exc) or exc.__class__.__name__,
            "scenario_path": str(scenario_path),
            "required_args": list(STANDALONE_WRITE_E2E_REQUIRED_ARGS),
        }


def _validate_release_write_scenarios(scenarios: Sequence[Any]) -> None:
    registered_shapes = write_operation_e2e_smoke.REVERSIBLE_RELATION_SHAPE_CONTRACTS
    for scenario in scenarios:
        recovery = getattr(scenario, "recovery_checkpoint", None)
        if (
            getattr(scenario, "fixture_ownership", None) != "test_owned"
            or getattr(scenario, "shape", None) not in registered_shapes
            or not tuple(getattr(scenario, "checkpoints", ()) or ())
            or recovery is None
            or getattr(recovery, "relation_state_after", None) != "inactive"
        ):
            raise ValueError(
                "production release gate requires registered test_owned reversible "
                "confirm/withdraw scenarios with an inactive recovery checkpoint."
            )


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
