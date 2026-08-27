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
from fin_ops_platform.tools import (
    health_ready_payload_probe,
    http_slo_probe,
    write_operation_e2e_smoke,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report, write_json_report


PASS = "pass"
FAIL = "fail"
SKIP = "skip"
GATE_PROFILES = ("preflight", "full", "stability")
STANDALONE_WRITE_E2E_REQUIRED_ARGS = ("--scenario", "--apply", "--approval-ticket")
RUNTIME_HEALTH_REQUIRED_FIELDS = (
    "queue_backlog",
    "failed_jobs",
    "missing_required_worker_count",
    "stale_required_worker_count",
    "mismatched_required_worker_count",
    "worker_metrics",
    "critical_failed_outbox_count",
)
PREFLIGHT_UPGRADE_AUDIT_ISSUE_CODES = frozenset(
    {"page_runtime_queue_not_drained", "worker_event_type_mismatch"}
)
CANDIDATE_AUDIT_BOOTSTRAP_ERRORS = frozenset(
    {
        "system_audit_business_pages_failed",
        "system_audit_internal_gate_failed",
        "system_audit_page_count_or_contract_failed",
        "system_audit_registry_contract_failed",
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
        description="Run the production runtime closure gate for canonical page API SLO and worker health.",
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
    parser.add_argument("--write-target-ms", type=float, default=1_000.0)
    parser.add_argument("--http-target-ms", type=float, default=1_000.0)
    parser.add_argument("--health-ready-target-ms", type=float, default=health_ready_payload_probe.DEFAULT_TARGET_MS)
    parser.add_argument("--health-ready-max-response-bytes", type=int, default=health_ready_payload_probe.DEFAULT_MAX_RESPONSE_BYTES)
    parser.add_argument("--health-ready-max-api-performance-endpoints", type=int, default=health_ready_payload_probe.DEFAULT_MAX_API_PERFORMANCE_ENDPOINTS)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    parser.add_argument(
        "--required-worker-instance",
        action="append",
        default=[],
        help="Override the required worker inventory used by runtime health checks.",
    )
    parser.add_argument(
        "--allow-preflight-pending-event-type",
        action="append",
        default=[],
        help=(
            "Allow a preflight-only pending backlog for an event type introduced by the exact candidate release. "
            "Processing, failed, dead-lettered, mixed, or unaccounted rows still fail closed."
        ),
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
        write_target_ms=max(1.0, float(args.write_target_ms)),
        http_target_ms=max(1.0, float(args.http_target_ms)),
        health_ready_target_ms=max(1.0, float(args.health_ready_target_ms)),
        health_ready_max_response_bytes=max(1, int(args.health_ready_max_response_bytes)),
        health_ready_max_api_performance_endpoints=max(0, int(args.health_ready_max_api_performance_endpoints)),
        timeout_seconds=max(1.0, float(args.timeout_seconds)),
        poll_interval_seconds=max(0.05, float(args.poll_interval_seconds)),
        required_worker_instances={
            str(instance).strip()
            for instance in args.required_worker_instance
            if str(instance).strip()
        } or None,
        allowed_preflight_pending_event_types={
            str(event_type).strip()
            for event_type in args.allow_preflight_pending_event_type
            if str(event_type).strip()
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
    write_target_ms: float = 1_000.0,
    http_target_ms: float = 1_000.0,
    health_ready_target_ms: float = health_ready_payload_probe.DEFAULT_TARGET_MS,
    health_ready_max_response_bytes: int = health_ready_payload_probe.DEFAULT_MAX_RESPONSE_BYTES,
    health_ready_max_api_performance_endpoints: int = health_ready_payload_probe.DEFAULT_MAX_API_PERFORMANCE_ENDPOINTS,
    timeout_seconds: float = 90.0,
    poll_interval_seconds: float = 0.5,
    required_worker_instances: set[str] | None = None,
    allowed_preflight_pending_event_types: set[str] | None = None,
) -> dict[str, Any]:
    if profile not in GATE_PROFILES:
        raise ValueError(f"unsupported release gate profile: {profile}")
    if allowed_preflight_pending_event_types and profile != "preflight":
        raise ValueError("preflight pending event types are only valid for the preflight profile")
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
                    allowed_preflight_pending_event_types=allowed_preflight_pending_event_types,
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
    # and durable queue convergence check has completed.
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
            allowed_preflight_pending_event_types=allowed_preflight_pending_event_types,
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
            "database_reversible_write_ms": min(write_target_ms, 1_000.0),
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
    allowed_preflight_pending_event_types: set[str] | None = None,
) -> ClosureCheck:
    deadline = monotonic() + max(0.0, timeout_seconds)
    monitoring_repository = RuntimeMonitoringRepository(connection)
    while True:
        try:
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
                "Runtime queue or worker monitoring health summary unavailable.",
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
        # A preflight explicitly pins the currently active worker instances while
        # running this candidate's gate code.  The active processes cannot yet
        # advertise event types introduced by the candidate; their current-release
        # contract is still enforced by /health/ready.  Keep missing/stale/queue
        # checks strict here, and defer the candidate contract check to T+0 after
        # the candidate workers have actually started.
        blockers = _runtime_blockers(
            summary,
            allow_required_worker_contract_mismatch=required_worker_instances is not None,
            allowed_preflight_pending_event_types=allowed_preflight_pending_event_types,
        )
        accepted_preflight_pending_events = _accepted_preflight_pending_events(
            summary,
            allowed_event_types=allowed_preflight_pending_event_types,
        )
        timed_out = monotonic() >= deadline
        if not blockers or timed_out:
            return ClosureCheck(
                name,
                PASS if not blockers else FAIL,
                "Runtime queue and worker blockers are clear." if not blockers else "Runtime health did not converge before the gate deadline.",
                {
                    "blockers": blockers,
                    "required_worker_contract": (
                        "active_release_compatible"
                        if required_worker_instances is not None
                        else "strict_current_release"
                    ),
                    "snapshot": {
                        key: summary.get(key)
                        for key in (
                            "queue_backlog",
                            "failed_jobs",
                            "max_pending_age_seconds",
                            "missing_required_worker_count",
                            "stale_required_worker_count",
                            "mismatched_required_worker_count",
                            "critical_failed_outbox_count",
                        )
                        if key in summary
                    },
                    **(
                        {"accepted_preflight_pending_events": accepted_preflight_pending_events}
                        if accepted_preflight_pending_events is not None
                        else {}
                    ),
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
        retryable_latency = attempts == 1 and _http_slo_has_only_single_window_latency_miss(report)
        if report.get("status") == PASS or not retryable_latency:
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
    allowed_preflight_pending_event_types: set[str] | None = None,
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
    accepted_preflight_pending_events = (
        _accepted_preflight_pending_events(
            RuntimeMonitoringRepository(connection).ready_health_summary(),
            allowed_event_types=allowed_preflight_pending_event_types,
        )
        if allowed_preflight_pending_event_types
        else None
    )
    audit = (
        {
            "status": SKIP,
            "reason": "candidate_upgrade_backlog_requires_candidate_snapshot",
            "accepted_preflight_pending_events": accepted_preflight_pending_events,
        }
        if accepted_preflight_pending_events is not None
        else write_operation_e2e_smoke._wait_for_system_audit(
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
    )
    verification_source = (
        "candidate_read_only_snapshot"
        if accepted_preflight_pending_events is not None
        else "current_http_api"
    )
    candidate_audit: dict[str, Any] | None = None
    if accepted_preflight_pending_events is not None or (
        audit.get("status") != PASS and audit.get("error") in CANDIDATE_AUDIT_BOOTSTRAP_ERRORS
    ):
        candidate_audit = _candidate_system_audit(
            connection,
            tenant_id=tenant_id,
            timeout_seconds=timeout_seconds,
        )
        candidate_audit = _accept_preflight_candidate_audit(
            candidate_audit,
            accepted_preflight_pending_events=accepted_preflight_pending_events,
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
    candidate_audit = write_operation_e2e_smoke._collect_system_audit(
        checkpoint,
        base_url="https://candidate-release.invalid",
        api_prefix="",
        headers={},
        timeout_seconds=timeout_seconds,
        request_fn=lambda *_args: response,
    )
    if candidate_audit.get("status") != PASS:
        page_reports = list(
            dict(report.get("database_system_snapshot") or {}).get("page_results") or []
        )
        candidate_audit["diagnostics"] = {
            "overall_status": report.get("overall_status"),
            "audit_status": report.get("audit_status"),
            "summary": report.get("summary"),
            "issues": list(report.get("issues") or [])[:10],
            "issue_codes": sorted(
                {
                    str(issue.get("code") or "")
                    for issue in list(report.get("issues") or [])
                    if isinstance(issue, dict) and str(issue.get("code") or "")
                }
            ),
            "failed_page_reports": [
                {
                    "page_key": page_report.get("page_key"),
                    "overall_status": page_report.get("overall_status"),
                    "audit_status": page_report.get("audit_status"),
                    "summary": page_report.get("summary"),
                    "issues": list(page_report.get("issues") or [])[:10],
                }
                for page_report in page_reports
                if page_report.get("overall_status") != "pass"
            ][:5],
        }
    return candidate_audit


def _runtime_blockers(
    summary: Mapping[str, Any],
    *,
    allow_required_worker_contract_mismatch: bool = False,
    allowed_preflight_pending_event_types: set[str] | None = None,
) -> dict[str, Any]:
    blockers: dict[str, Any] = {}
    for key in ("missing_required_worker_count", "stale_required_worker_count"):
        if int(summary.get(key) or 0) > 0:
            blockers[key] = summary.get(key)
    if (
        not allow_required_worker_contract_mismatch
        and int(summary.get("mismatched_required_worker_count") or 0) > 0
    ):
        blockers["mismatched_required_worker_count"] = summary.get(
            "mismatched_required_worker_count"
        )
    for key in (
        "failed_jobs",
        "critical_failed_outbox_count",
    ):
        if int(summary.get(key) or 0) > 0:
            blockers[key] = summary.get(key)
    queue_backlog = summary.get("queue_backlog")
    accepted_preflight_pending_events = _accepted_preflight_pending_events(
        summary,
        allowed_event_types=allowed_preflight_pending_event_types,
    )
    if (
        isinstance(queue_backlog, dict)
        and any(int(value or 0) > 0 for value in queue_backlog.values())
        and accepted_preflight_pending_events is None
    ):
        blockers["queue_backlog"] = queue_backlog
    return blockers


def _accepted_preflight_pending_events(
    summary: Mapping[str, Any],
    *,
    allowed_event_types: set[str] | None,
) -> dict[str, Any] | None:
    normalized_allowed = {
        str(event_type).strip()
        for event_type in (allowed_event_types or set())
        if str(event_type).strip()
    }
    if not normalized_allowed:
        return None
    queue_backlog = summary.get("queue_backlog")
    if not isinstance(queue_backlog, dict):
        return None
    positive_queue = {
        str(status): int(count or 0)
        for status, count in queue_backlog.items()
        if int(count or 0) > 0
    }
    if set(positive_queue) != {"pending"}:
        return None
    type_rows = summary.get("outbox_events_by_type_status")
    if not isinstance(type_rows, list) or not type_rows:
        return None
    normalized_rows = [
        {
            "event_type": str(row.get("event_type") or "").strip(),
            "status": str(row.get("status") or "").strip(),
            "count": int(row.get("count") or 0),
        }
        for row in type_rows
        if isinstance(row, dict) and int(row.get("count") or 0) > 0
    ]
    if (
        not normalized_rows
        or any(row["status"] != "pending" for row in normalized_rows)
        or any(row["event_type"] not in normalized_allowed for row in normalized_rows)
        or sum(row["count"] for row in normalized_rows) != positive_queue["pending"]
    ):
        return None
    return {
        "status": "accepted_candidate_upgrade_backlog",
        "count": positive_queue["pending"],
        "event_types": sorted({row["event_type"] for row in normalized_rows}),
        "rows": normalized_rows,
    }


def _accept_preflight_candidate_audit(
    candidate_audit: dict[str, Any],
    *,
    accepted_preflight_pending_events: dict[str, Any] | None,
) -> dict[str, Any]:
    if candidate_audit.get("status") == PASS or accepted_preflight_pending_events is None:
        return candidate_audit
    diagnostics = candidate_audit.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return candidate_audit
    summary = diagnostics.get("summary")
    issue_codes = {
        str(code)
        for code in list(diagnostics.get("issue_codes") or [])
        if str(code)
    }
    failed_page_reports = list(diagnostics.get("failed_page_reports") or [])
    business_pages_passed = (
        isinstance(summary, dict)
        and int(summary.get("audited_business_page_count") or -1)
        == int(summary.get("passed_business_page_count") or -2)
    )
    if (
        candidate_audit.get("error") != "system_audit_internal_gate_failed"
        or not business_pages_passed
        or failed_page_reports
        or not issue_codes
        or not issue_codes.issubset(PREFLIGHT_UPGRADE_AUDIT_ISSUE_CODES)
        or "page_runtime_queue_not_drained" not in issue_codes
    ):
        return candidate_audit
    accepted = dict(candidate_audit)
    accepted["status"] = PASS
    accepted.pop("error", None)
    accepted["accepted_preflight_pending_events"] = accepted_preflight_pending_events
    accepted["accepted_issue_codes"] = sorted(issue_codes)
    return accepted


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
            item.get("p99_enqueue_to_done_ms")
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
