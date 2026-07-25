from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Callable, Mapping, Sequence, TextIO
import os
import sys

from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.tools import http_slo_probe, write_operation_slo_audit
from fin_ops_platform.tools.cli_reports import (
    input_file_error_report,
    postgres_configuration_missing_report,
    write_json_report,
)


DEFAULT_WRITE_TARGET_MS = 1_000.0
DEFAULT_REFRESH_TARGET_MS = 30_000.0
DEFAULT_HTTP_TARGET_MS = 1_000.0
DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.5
DEFAULT_LIMIT = 2_000
MIN_WRITE_SLO_EVENT_SAMPLE_LIMIT = 200
MAX_TEST_OWNED_RELATION_ROW_IDS = 20
MAX_AFFECTED_CONSUMER_SCOPES_PER_PAGE = 3
MAX_PARALLEL_CONSUMER_PROBES = 16
SYSTEM_AUDIT_PATH = "/api/operations/app-health/page-audit?page=app-health-operations"
CONFIRM_PREVIEW_PATH = "/api/workbench/actions/confirm-link/preview"
CONFIRM_MUTATION_PATH = "/api/workbench/actions/confirm-link"
WITHDRAW_PREVIEW_PATH = "/api/workbench/actions/withdraw-link/preview"
WITHDRAW_MUTATION_PATH = "/api/workbench/actions/withdraw-link"

REVERSIBLE_RELATION_CONSUMER_CONTRACTS: dict[str, dict[str, object]] = {
    "reconciliation-workbench": {
        "path": "/api/workbench/groups",
        "business_roots": ("groups",),
    },
    "bank-details": {"path": "/api/bank-details/transactions", "business_roots": ("rows",)},
    "pending-invoices": {"path": "/api/pending-invoices/rows", "business_roots": ("rows",)},
    "input-invoice-usage": {"path": "/api/input-invoice-usage/rows", "business_roots": ("rows",)},
    "output-invoice-collections": {"path": "/api/output-invoice-collections/rows", "business_roots": ("rows",)},
    "oa-pending-payments": {"path": "/api/oa-pending-payments/rows", "business_roots": ("rows",)},
    "cost-statistics": {
        "path": "/api/cost-statistics/explorer",
        "business_roots": ("rows",),
    },
    "tax-offset": {
        "path": "/api/tax-offset",
        "business_roots": ("output_items", "input_plan_items", "certified_items"),
    },
    "turnover-ledger": {
        "path": "/api/turnover-ledger",
        "business_roots": ("groups", "rows"),
    },
}

REVERSIBLE_RELATION_SHAPE_CONTRACTS: dict[str, dict[str, object]] = {
    "bank_invoice": {
        "mutation_contract": "workbench_relation",
        "confirm_profile": "workbench_relation_confirm_bank_invoice_cross_page",
        "withdraw_profile": "workbench_relation_withdraw_bank_invoice_cross_page",
        "affected_consumer_page_keys": (
            "reconciliation-workbench",
            "bank-details",
            "pending-invoices",
            "input-invoice-usage",
        ),
        "non_consumer_isolation_page_keys": (
            "output-invoice-collections",
            "oa-pending-payments",
            "cost-statistics",
            "tax-offset",
        ),
    },
    "bank_turnover": {
        "mutation_contract": "turnover_closure",
        "confirm_profile": "turnover_relation_confirm_cross_page",
        "withdraw_profile": "turnover_relation_withdraw_cross_page",
        "affected_consumer_page_keys": (
            "reconciliation-workbench",
            "cost-statistics",
            "turnover-ledger",
        ),
        "non_consumer_isolation_page_keys": ("input-invoice-usage",),
    },
    "bank_oa_invoice": {
        "mutation_contract": "workbench_relation",
        "confirm_profile": "workbench_relation_confirm_cross_page",
        "withdraw_profile": "workbench_relation_withdraw_cross_page",
        "affected_consumer_page_keys": (
            "reconciliation-workbench",
            "bank-details",
            "pending-invoices",
            "input-invoice-usage",
            "oa-pending-payments",
            "cost-statistics",
        ),
        "non_consumer_isolation_page_keys": ("output-invoice-collections", "tax-offset"),
    },
}

RequestFn = Callable[[str, str, Mapping[str, str], bytes | None, float], http_slo_probe.HttpProbeResponse]
_RESPONSE_OUTBOX_EVENT_IDS = "__response_outbox_event_ids"


@dataclass(frozen=True)
class WriteStep:
    name: str
    method: str
    path: str
    json_body: dict[str, Any] | None
    expected_statuses: tuple[int, ...]
    mutation: bool = True
    captures: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class WriteStepResult:
    name: str
    method: str
    path: str
    status: str
    elapsed_ms: float | None
    status_code: int | None
    response_bytes: int
    content_type: str
    error: str | None = None
    request_id: str | None = None
    response_error_code: str | None = None


@dataclass(frozen=True)
class _ExecutedStep:
    result: WriteStepResult
    captures: dict[str, Any]
    committed: bool
    ambiguous: bool


@dataclass(frozen=True)
class JsonPointerAssertion:
    pointer: str
    operator: str
    expected: Any


@dataclass(frozen=True)
class ConsumerProbe:
    probe: http_slo_probe.HttpProbe
    assertions: tuple[JsonPointerAssertion, ...]
    page_key: str = ""
    role: str = "affected"


@dataclass(frozen=True)
class WriteCheckpoint:
    name: str
    operations: tuple[str, ...]
    steps: tuple[WriteStep, ...]
    consumers: tuple[ConsumerProbe, ...] = ()
    system_audit_path: str | None = None
    relation_state_after: str | None = None
    fixture_row_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WriteScenario:
    name: str
    operations: tuple[str, ...]
    steps: tuple[WriteStep, ...]
    post_api_probes: tuple[http_slo_probe.HttpProbe, ...]
    checkpoints: tuple[WriteCheckpoint, ...] = ()
    recovery_checkpoint: WriteCheckpoint | None = None
    fixture_ownership: str | None = None
    shape: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run controlled authenticated write-operation E2E SLO smoke scenarios.",
    )
    parser.add_argument(
        "--scenario", type=Path, required=True, help="JSON scenario file. Defaults to dry-run validation."
    )
    parser.add_argument("--apply", action="store_true", help="Execute mutating HTTP steps. Default is dry-run only.")
    parser.add_argument("--base-url", default=os.getenv("FIN_OPS_HTTP_SLO_BASE_URL", "http://127.0.0.1:18001"))
    parser.add_argument("--api-prefix", default=os.getenv("FIN_OPS_HTTP_SLO_API_PREFIX", ""))
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--bearer-token", default=os.getenv("FIN_OPS_HTTP_SLO_BEARER_TOKEN", ""))
    parser.add_argument("--admin-token", default=os.getenv("FIN_OPS_HTTP_SLO_ADMIN_TOKEN", ""))
    parser.add_argument("--cookie", default=os.getenv("FIN_OPS_HTTP_SLO_COOKIE", ""))
    parser.add_argument(
        "--approval-ticket",
        default=os.getenv("FIN_OPS_WRITE_E2E_APPROVAL_TICKET", ""),
        help="Required with --apply. Business approval reference for mutating production write-operation smoke.",
    )
    parser.add_argument("--write-target-ms", type=float, default=DEFAULT_WRITE_TARGET_MS)
    parser.add_argument("--refresh-target-ms", type=float, default=DEFAULT_REFRESH_TARGET_MS)
    parser.add_argument("--http-target-ms", type=float, default=DEFAULT_HTTP_TARGET_MS)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    write_target_ms = max(1.0, float(args.write_target_ms))
    refresh_target_ms = max(1.0, float(args.refresh_target_ms))
    try:
        scenarios = load_scenarios(args.scenario, http_target_ms=max(1.0, float(args.http_target_ms)))
    except FileNotFoundError:
        report = input_file_error_report(
            tool="write_operation_e2e_smoke",
            path=str(args.scenario),
            error="scenario_file_missing",
            message="Scenario file does not exist.",
        )
        write_json_report(report, output=args.output, stdout=stdout)
        return 2
    except json.JSONDecodeError as exc:
        report = input_file_error_report(
            tool="write_operation_e2e_smoke",
            path=str(args.scenario),
            error="scenario_json_invalid",
            message=str(exc),
        )
        write_json_report(report, output=args.output, stdout=stdout)
        return 2
    except ValueError as exc:
        report = input_file_error_report(
            tool="write_operation_e2e_smoke",
            path=str(args.scenario),
            error="scenario_contract_invalid",
            message=str(exc),
        )
        write_json_report(report, output=args.output, stdout=stdout)
        return 2
    headers = http_slo_probe._auth_headers(  # Reuse the existing HTTP SLO auth boundary.
        bearer_token=args.bearer_token,
        admin_token=args.admin_token,
        cookie=args.cookie,
    )
    approval_ticket = str(args.approval_ticket or "").strip()
    connection = None
    if args.apply:
        if not approval_ticket:
            report = _approval_missing_report(
                base_url=str(args.base_url),
                api_prefix=str(args.api_prefix),
                scenario_count=len(scenarios),
            )
            write_json_report(report, output=args.output, stdout=stdout)
            return 2
        try:
            connection = PostgresConnection(PostgresSettings.from_env())
        except PostgresConfigurationError as exc:
            report = postgres_configuration_missing_report(tool="write_operation_e2e_smoke", message=str(exc))
            write_json_report(report, output=args.output, stdout=stdout)
            return 2
    report = run_write_operation_e2e_smoke(
        connection,
        scenarios=scenarios,
        apply=bool(args.apply),
        base_url=str(args.base_url),
        api_prefix=str(args.api_prefix),
        tenant_id=str(args.tenant_id or "default"),
        headers=headers,
        approval_reference=approval_ticket,
        write_target_ms=write_target_ms,
        refresh_target_ms=refresh_target_ms,
        timeout_seconds=max(1.0, float(args.timeout_seconds)),
        poll_interval_seconds=max(0.05, float(args.poll_interval_seconds)),
        limit=max(1, int(args.limit)),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    if report["status"] in {"approval_missing", "auth_missing"}:
        return 2
    if report["status"] == "dry_run":
        return 0
    return 0 if report["status"] == "pass" else 1


def load_scenarios(path: Path, *, http_target_ms: float) -> list[WriteScenario]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_scenarios = payload.get("scenarios") if isinstance(payload, dict) else payload
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("scenario file must be a non-empty JSON list or an object with a scenarios list.")
    scenarios: list[WriteScenario] = []
    seen_idempotency_keys: set[str] = set()
    relation_contracts: dict[str, dict[str, Any]] | None = None
    for index, raw in enumerate(raw_scenarios, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"scenario #{index} must be an object.")
        name = str(raw.get("name") or f"scenario_{index}").strip() or f"scenario_{index}"
        raw_checkpoints = raw.get("checkpoints")
        if raw_checkpoints is not None:
            relation_contracts = relation_contracts or _reversible_relation_contracts()
            shape = str(raw.get("shape") or "").strip()
            if shape not in relation_contracts:
                raise ValueError(f"scenario {name!r} must declare a registered reversible relation shape.")
            relation_contract = relation_contracts[shape]
            if raw.get("fixture_ownership") != "test_owned":
                raise ValueError(f"scenario {name!r} checkpoints require fixture_ownership='test_owned'.")
            consumer_roles = {
                **{
                    str(page_key): "affected"
                    for page_key in list(relation_contract.get("affected_consumer_page_keys") or [])
                },
                **{
                    str(page_key): "isolation"
                    for page_key in list(relation_contract.get("non_consumer_isolation_page_keys") or [])
                },
            }
            if not isinstance(raw_checkpoints, list) or not raw_checkpoints:
                raise ValueError(f"scenario {name!r} checkpoints must be a non-empty list.")
            checkpoints = tuple(
                _load_checkpoint(
                    item,
                    scenario_name=name,
                    checkpoint_index=checkpoint_index,
                    http_target_ms=http_target_ms,
                    strict=True,
                    consumer_roles=consumer_roles,
                )
                for checkpoint_index, item in enumerate(raw_checkpoints, start=1)
            )
            recovery_raw = raw.get("recovery_checkpoint")
            recovery_checkpoint = (
                _load_checkpoint(
                    recovery_raw,
                    scenario_name=name,
                    checkpoint_index=0,
                    http_target_ms=http_target_ms,
                    strict=True,
                    consumer_roles=consumer_roles,
                )
                if recovery_raw is not None
                else None
            )
            if (
                any(checkpoint.relation_state_after == "active" for checkpoint in checkpoints)
                and recovery_checkpoint is None
            ):
                raise ValueError(f"scenario {name!r} activates a relation and must declare recovery_checkpoint.")
            if recovery_checkpoint is not None and recovery_checkpoint.relation_state_after != "inactive":
                raise ValueError(f"scenario {name!r} recovery_checkpoint must declare relation_state_after='inactive'.")
            _validate_reversible_checkpoint_contract(
                scenario_name=name,
                checkpoints=checkpoints,
                recovery_checkpoint=recovery_checkpoint,
                relation_contract=relation_contract,
            )
            all_checkpoints = (*checkpoints, *((recovery_checkpoint,) if recovery_checkpoint else ()))
            idempotency_keys = [
                str((step.json_body or {}).get("idempotency_key") or "").strip()
                for checkpoint in all_checkpoints
                for step in checkpoint.steps
                if step.mutation
            ]
            if len(idempotency_keys) != len(set(idempotency_keys)):
                raise ValueError(f"scenario {name!r} mutation idempotency_key values must be unique.")
            duplicate_keys = sorted(set(idempotency_keys) & seen_idempotency_keys)
            if duplicate_keys:
                raise ValueError(
                    f"scenario mutation idempotency_key values must be unique across the file: {duplicate_keys}"
                )
            seen_idempotency_keys.update(idempotency_keys)
            scenarios.append(
                WriteScenario(
                    name=name,
                    operations=(),
                    steps=(),
                    post_api_probes=(),
                    checkpoints=checkpoints,
                    recovery_checkpoint=recovery_checkpoint,
                    fixture_ownership="test_owned",
                    shape=shape,
                )
            )
            continue
        operations = tuple(
            str(item or "").strip() for item in list(raw.get("operations") or []) if str(item or "").strip()
        )
        if not operations:
            operation = str(raw.get("operation") or "").strip()
            operations = (operation,) if operation else ()
        if not operations:
            raise ValueError(f"scenario {name!r} must include operation or operations.")
        write_operation_slo_audit.selected_expectations_for_operations(operations)
        steps = _load_steps(raw.get("steps"), scenario_name=name)
        post_api_probes = _load_post_api_probes(raw.get("post_api_probes"), default_target_ms=http_target_ms)
        scenarios.append(
            WriteScenario(
                name=name,
                operations=operations,
                steps=tuple(steps),
                post_api_probes=tuple(post_api_probes),
                checkpoints=(
                    WriteCheckpoint(
                        name=name,
                        operations=operations,
                        steps=tuple(steps),
                        consumers=tuple(ConsumerProbe(probe=probe, assertions=()) for probe in post_api_probes),
                    ),
                ),
            )
        )
    return scenarios


def run_write_operation_e2e_smoke(
    connection: Any,
    *,
    scenarios: Sequence[WriteScenario],
    apply: bool,
    base_url: str,
    api_prefix: str,
    tenant_id: str,
    headers: Mapping[str, str],
    approval_reference: str | None = None,
    write_target_ms: float = DEFAULT_WRITE_TARGET_MS,
    refresh_target_ms: float = DEFAULT_REFRESH_TARGET_MS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    limit: int = DEFAULT_LIMIT,
    request_fn: RequestFn | None = None,
) -> dict[str, Any]:
    auth_configured = any(str(key).lower() in {"authorization", "cookie"} for key in dict(headers))
    approval_reference = str(approval_reference or "").strip()
    plan = [_scenario_plan_payload(scenario) for scenario in scenarios]
    if not scenarios:
        return {
            "version": 1,
            "status": "input_error",
            "generated_at": datetime.now(UTC).isoformat(),
            "base_url": http_slo_probe._normalized_base_url(base_url),
            "api_prefix": api_prefix,
            "auth_configured": auth_configured,
            "approval_configured": bool(approval_reference),
            "scenario_count": 0,
            "error": "scenario_empty",
            "message": "write-operation E2E smoke requires at least one approved scenario.",
            "planned_scenarios": plan,
        }
    if not apply:
        return {
            "version": 1,
            "status": "dry_run",
            "generated_at": datetime.now(UTC).isoformat(),
            "base_url": http_slo_probe._normalized_base_url(base_url),
            "api_prefix": api_prefix,
            "auth_configured": auth_configured,
            "approval_configured": bool(approval_reference),
            "scenario_count": len(scenarios),
            "planned_scenarios": plan,
        }
    if not approval_reference:
        return _approval_missing_report(
            base_url=base_url,
            api_prefix=api_prefix,
            scenario_count=len(scenarios),
            planned_scenarios=plan,
        )
    if not auth_configured:
        return {
            "version": 1,
            "status": "auth_missing",
            "generated_at": datetime.now(UTC).isoformat(),
            "base_url": http_slo_probe._normalized_base_url(base_url),
            "api_prefix": api_prefix,
            "auth_configured": False,
            "approval_configured": True,
            "approval_reference": approval_reference,
            "error": "write-operation E2E smoke requires FIN_OPS_HTTP_SLO_BEARER_TOKEN, FIN_OPS_HTTP_SLO_ADMIN_TOKEN, FIN_OPS_HTTP_SLO_COOKIE, or CLI auth options",
            "planned_scenarios": plan,
        }
    request = request_fn or _http_request
    results = [
        _run_one_scenario(
            connection,
            scenario,
            base_url=base_url,
            api_prefix=api_prefix,
            tenant_id=tenant_id,
            headers=headers,
            write_target_ms=write_target_ms,
            refresh_target_ms=refresh_target_ms,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            limit=limit,
            request_fn=request,
        )
        for scenario in scenarios
    ]
    failed = [result for result in results if result.get("status") != "pass"]
    return {
        "version": 1,
        "status": "pass" if not failed else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": http_slo_probe._normalized_base_url(base_url),
        "api_prefix": api_prefix,
        "auth_configured": auth_configured,
        "approval_configured": True,
        "approval_reference": approval_reference,
        "scenario_count": len(scenarios),
        "failed_scenario_count": len(failed),
        "results": results,
    }


def _approval_missing_report(
    *,
    base_url: str,
    api_prefix: str,
    scenario_count: int,
    planned_scenarios: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "status": "approval_missing",
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": http_slo_probe._normalized_base_url(base_url),
        "api_prefix": api_prefix,
        "approval_configured": False,
        "scenario_count": int(scenario_count),
        "error": "write_operation_e2e_requires_approval_ticket",
        "message": "Mutating write-operation E2E smoke requires --approval-ticket or FIN_OPS_WRITE_E2E_APPROVAL_TICKET.",
        "required_args": ["--scenario", "--apply", "--approval-ticket"],
        "planned_scenarios": list(planned_scenarios or []),
    }


def _run_one_scenario(
    connection: Any,
    scenario: WriteScenario,
    *,
    base_url: str,
    api_prefix: str,
    tenant_id: str,
    headers: Mapping[str, str],
    write_target_ms: float,
    refresh_target_ms: float,
    timeout_seconds: float,
    poll_interval_seconds: float,
    limit: int,
    request_fn: RequestFn,
) -> dict[str, Any]:
    checkpoints = scenario.checkpoints or (
        WriteCheckpoint(
            name=scenario.name,
            operations=scenario.operations,
            steps=scenario.steps,
            consumers=tuple(ConsumerProbe(probe=probe, assertions=()) for probe in scenario.post_api_probes),
        ),
    )
    variables: dict[str, Any] = {}
    checkpoint_results: list[dict[str, Any]] = []
    audit_ids: set[str] = set()
    preflight: dict[str, Any] | None = None
    if scenario.fixture_ownership == "test_owned":
        preflight = _wait_for_system_audit(
            checkpoints[0],
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            request_fn=request_fn,
            excluded_audit_ids=audit_ids,
        )
        if preflight.get("status") != "pass":
            return {
                "name": scenario.name,
                "status": "fail",
                "checkpoints": [],
                "preflight": preflight,
                "recovery_required": False,
            }
        audit_ids.add(str(preflight["system_audit_id"]))
    relation_active = False
    recovery_required = False
    recovery: dict[str, Any] | None = None
    for checkpoint in checkpoints:
        checkpoint_isolation_baseline = _capture_isolation_baseline(
            checkpoint,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            request_fn=request_fn,
            variables=variables,
        )
        result = _run_checkpoint(
            connection,
            checkpoint,
            base_url=base_url,
            api_prefix=api_prefix,
            tenant_id=tenant_id,
            headers=headers,
            write_target_ms=write_target_ms,
            refresh_target_ms=refresh_target_ms,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            limit=limit,
            request_fn=request_fn,
            variables=variables,
            audit_ids=audit_ids,
            strict=bool(scenario.checkpoints),
            prepared_isolation_baseline=checkpoint_isolation_baseline,
        )
        checkpoint_results.append(result)
        if result.get("mutation_committed"):
            if checkpoint.relation_state_after == "active":
                relation_active = True
            elif checkpoint.relation_state_after == "inactive":
                relation_active = False
        if result.get("status") != "pass":
            recovery_required = (
                bool(result.get("mutation_ambiguous"))
                or relation_active
                or bool(result.get("mutation_committed") and checkpoint.relation_state_after == "active")
            )
            if recovery_required and not result.get("mutation_ambiguous") and scenario.recovery_checkpoint is not None:
                recovery = _run_checkpoint(
                    connection,
                    scenario.recovery_checkpoint,
                    base_url=base_url,
                    api_prefix=api_prefix,
                    tenant_id=tenant_id,
                    headers=headers,
                    write_target_ms=write_target_ms,
                    refresh_target_ms=refresh_target_ms,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    limit=limit,
                    request_fn=request_fn,
                    variables=variables,
                    audit_ids=audit_ids,
                    strict=True,
                    prepared_isolation_baseline=checkpoint_isolation_baseline,
                )
                recovery_required = not bool(recovery.get("mutation_committed")) or bool(
                    recovery.get("mutation_ambiguous")
                )
            break
    status = (
        "pass"
        if len(checkpoint_results) == len(checkpoints)
        and all(item.get("status") == "pass" for item in checkpoint_results)
        else "fail"
    )
    payload: dict[str, Any] = {
        "name": scenario.name,
        "status": status,
        "checkpoints": checkpoint_results,
        "recovery_required": recovery_required,
        **({"preflight": preflight} if preflight is not None else {}),
        **({"recovery": recovery} if recovery is not None else {}),
    }
    # Preserve the established single-checkpoint report shape without retaining a second execution path.
    if len(checkpoint_results) == 1:
        first = checkpoint_results[0]
        payload.update(
            {
                "started_at": first["started_at"],
                "operations": first["operations"],
                "steps": first["steps"],
                "write_slo": first["write_slo"],
                "post_api": first["post_api"],
            }
        )
    return payload


def _run_checkpoint(
    connection: Any,
    checkpoint: WriteCheckpoint,
    *,
    base_url: str,
    api_prefix: str,
    tenant_id: str,
    headers: Mapping[str, str],
    write_target_ms: float,
    refresh_target_ms: float,
    timeout_seconds: float,
    poll_interval_seconds: float,
    limit: int,
    request_fn: RequestFn,
    variables: dict[str, Any],
    audit_ids: set[str],
    strict: bool,
    prepared_isolation_baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    started_at = _database_timestamp(connection)
    variables.pop(_RESPONSE_OUTBOX_EVENT_IDS, None)
    step_results: list[WriteStepResult] = []
    isolation_baseline = dict(
        prepared_isolation_baseline
        if prepared_isolation_baseline is not None
        else _capture_isolation_baseline(
            checkpoint,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            request_fn=request_fn,
            variables=variables,
        )
    )
    if isolation_baseline["status"] != "pass":
        return _failed_checkpoint(
            checkpoint,
            started_at=started_at,
            step_results=step_results,
            mutation_committed=False,
            mutation_ambiguous=False,
            post_api=isolation_baseline,
        )
    mutation_committed = False
    mutation_ambiguous = False
    mutation_commit_ack_monotonic: float | None = None
    idempotency_key: str | None = None
    for step in checkpoint.steps:
        try:
            resolved_step = _resolved_step(step, variables)
        except ValueError as exc:
            step_results.append(
                WriteStepResult(
                    name=step.name,
                    method=step.method,
                    path=step.path,
                    status="fail",
                    elapsed_ms=None,
                    status_code=None,
                    response_bytes=0,
                    content_type="",
                    error=str(exc),
                )
            )
            break
        if resolved_step.mutation:
            key = str((resolved_step.json_body or {}).get("idempotency_key") or "").strip()
            if strict and not key:
                step_results.append(
                    WriteStepResult(
                        name=resolved_step.name,
                        method=resolved_step.method,
                        path=resolved_step.path,
                        status="fail",
                        elapsed_ms=None,
                        status_code=None,
                        response_bytes=0,
                        content_type="",
                        error="mutation_idempotency_key_required",
                    )
                )
                break
            if key:
                if idempotency_key is not None:
                    raise ValueError(f"checkpoint {checkpoint.name!r} must contain exactly one mutation step.")
                idempotency_key = key
        executed = _execute_step(
            resolved_step,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            target_ms=write_target_ms,
            timeout_seconds=timeout_seconds,
            request_fn=request_fn,
        )
        step_results.append(executed.result)
        variables.update(executed.captures)
        if (
            resolved_step.mutation
            and executed.committed
            and executed.result.status == "pass"
            and mutation_commit_ack_monotonic is None
        ):
            mutation_commit_ack_monotonic = monotonic()
        mutation_committed = mutation_committed or (resolved_step.mutation and executed.committed)
        mutation_ambiguous = mutation_ambiguous or (resolved_step.mutation and executed.ambiguous)
        if executed.result.status != "pass":
            if resolved_step.mutation and idempotency_key and mutation_ambiguous:
                mutation_committed, mutation_ambiguous = _reconcile_ambiguous_mutation(
                    connection,
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                    step=resolved_step,
                    variables=variables,
                )
                if mutation_committed and mutation_commit_ack_monotonic is None:
                    mutation_commit_ack_monotonic = monotonic()
            break
    if any(step.status != "pass" for step in step_results) or len(step_results) != len(checkpoint.steps):
        return _failed_checkpoint(
            checkpoint,
            started_at=started_at,
            step_results=step_results,
            mutation_committed=mutation_committed,
            mutation_ambiguous=mutation_ambiguous,
        )
    response_receipt_present = _RESPONSE_OUTBOX_EVENT_IDS in variables
    response_event_ids = _response_outbox_event_ids(variables.get(_RESPONSE_OUTBOX_EVENT_IDS))
    event_ids: list[str] | None = response_event_ids or None
    write_slo: dict[str, Any] | None = None
    if idempotency_key:
        if not response_receipt_present:
            try:
                durable_event_ids = write_operation_slo_audit.committed_workbench_outbox_event_ids(
                    connection,
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                )
                event_ids = durable_event_ids or None
            except Exception as exc:
                write_slo = {"status": "fail", "error": str(exc) or exc.__class__.__name__}
    post_api = _wait_for_checkpoint_consumers(
        checkpoint,
        base_url=base_url,
        api_prefix=api_prefix,
        headers=headers,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        request_fn=request_fn,
        variables=variables,
        strict=strict,
        isolation_baseline=isolation_baseline.get("values", {}),
        operation_commit_ack_monotonic=mutation_commit_ack_monotonic,
    )
    if write_slo is None:
        write_slo = _wait_for_write_slo(
            connection,
            operations=checkpoint.operations,
            tenant_id=tenant_id,
            started_at=started_at,
            target_ms=refresh_target_ms,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            limit=limit,
            event_ids=event_ids,
        )
    if write_slo["status"] != "pass" or post_api["status"] not in {"pass", "skipped"}:
        return _failed_checkpoint(
            checkpoint,
            started_at=started_at,
            step_results=step_results,
            mutation_committed=mutation_committed,
            mutation_ambiguous=mutation_ambiguous,
            write_slo=write_slo,
            post_api=post_api,
        )
    system_audit = _wait_for_system_audit(
        checkpoint,
        base_url=base_url,
        api_prefix=api_prefix,
        headers=headers,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        request_fn=request_fn,
        excluded_audit_ids=audit_ids,
    )
    if system_audit["status"] not in {"pass", "skipped"}:
        return _failed_checkpoint(
            checkpoint,
            started_at=started_at,
            step_results=step_results,
            mutation_committed=mutation_committed,
            mutation_ambiguous=mutation_ambiguous,
            write_slo=write_slo,
            post_api=post_api,
            system_audit=system_audit,
        )
    system_audit_id = system_audit.get("system_audit_id")
    if system_audit_id:
        if system_audit_id in audit_ids:
            system_audit = {"status": "fail", "error": "system_audit_id_reused"}
            return _failed_checkpoint(
                checkpoint,
                started_at=started_at,
                step_results=step_results,
                mutation_committed=mutation_committed,
                mutation_ambiguous=mutation_ambiguous,
                write_slo=write_slo,
                post_api=post_api,
                system_audit=system_audit,
            )
        audit_ids.add(str(system_audit_id))
    return {
        "name": checkpoint.name,
        "status": "pass",
        "started_at": started_at,
        "operations": list(checkpoint.operations),
        "steps": [asdict(step) for step in step_results],
        "mutation_committed": mutation_committed,
        "mutation_ambiguous": mutation_ambiguous,
        "event_ids": list(event_ids or []),
        "write_slo": write_slo,
        "post_api": post_api,
        "system_audit": system_audit,
    }


def _failed_checkpoint(
    checkpoint: WriteCheckpoint,
    *,
    started_at: Any,
    step_results: Sequence[WriteStepResult],
    mutation_committed: bool,
    mutation_ambiguous: bool,
    write_slo: dict[str, Any] | None = None,
    post_api: dict[str, Any] | None = None,
    system_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": checkpoint.name,
        "status": "fail",
        "started_at": started_at,
        "operations": list(checkpoint.operations),
        "steps": [asdict(step) for step in step_results],
        "mutation_committed": mutation_committed,
        "mutation_ambiguous": mutation_ambiguous,
        "write_slo": write_slo or {"status": "skipped", "reason": "write_step_failed"},
        "post_api": post_api or {"status": "skipped", "reason": "previous_gate_failed"},
        "system_audit": system_audit or {"status": "skipped", "reason": "previous_gate_failed"},
    }


def _execute_step(
    step: WriteStep,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    target_ms: float,
    timeout_seconds: float,
    request_fn: RequestFn,
) -> _ExecutedStep:
    url = http_slo_probe.resolve_probe_url(base_url, step.path, api_prefix=api_prefix)
    body = json.dumps(step.json_body, ensure_ascii=False).encode("utf-8") if step.json_body is not None else None
    request_headers = dict(headers)
    if body is not None:
        request_headers.setdefault("Content-Type", "application/json")
    started = monotonic()
    try:
        response = request_fn(url, step.method, request_headers, body, timeout_seconds)
        elapsed_ms = (monotonic() - started) * 1000
        content_type = _header(response.headers, "content-type")
        status_ok = response.status_code in step.expected_statuses
        html_api_error = (
            http_slo_probe._html_response_error(
                http_slo_probe.HttpProbe(
                    name=step.name,
                    path=step.path,
                    kind="api",
                    expected_statuses=step.expected_statuses,
                ),
                content_type,
                response.body or b"",
            )
            if status_ok
            else None
        )
        elapsed_rounded = round(elapsed_ms, 3)
        response_request_id, response_error_code = _response_diagnostics(
            response.body or b"",
            content_type,
            response.headers,
        )
        error = None
        if html_api_error:
            error = html_api_error
        elif not status_ok:
            error = f"unexpected_status:{response.status_code}"
        elif elapsed_ms > target_ms:
            error = f"write_step_slo_miss:{elapsed_rounded}>{round(target_ms, 3)}"
        result = WriteStepResult(
            name=step.name,
            method=step.method,
            path=step.path,
            status="pass" if error is None else "fail",
            elapsed_ms=elapsed_rounded,
            status_code=response.status_code,
            response_bytes=len(response.body or b""),
            content_type=content_type,
            error=error,
            request_id=response_request_id,
            response_error_code=response_error_code,
        )
        captures: dict[str, Any] = {}
        if (
            status_ok
            and not html_api_error
            and (step.mutation or step.captures or step.path in {CONFIRM_PREVIEW_PATH, WITHDRAW_PREVIEW_PATH})
        ):
            try:
                payload = json.loads((response.body or b"").decode("utf-8"))
                _validate_canonical_preview_payload(step, payload)
                captures = {name: _json_pointer(payload, pointer) for name, pointer in step.captures}
                if step.mutation and "outbox_event_ids" in payload:
                    if not isinstance(payload.get("outbox_event_ids"), list):
                        raise ValueError("outbox_event_ids must be a list")
                    response_event_ids = _response_outbox_event_ids(payload.get("outbox_event_ids"))
                    captures[_RESPONSE_OUTBOX_EVENT_IDS] = response_event_ids
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
                result = WriteStepResult(
                    **{**asdict(result), "status": "fail", "error": f"response_capture_failed:{exc}"}
                )
        return _ExecutedStep(
            result=result,
            captures=captures,
            committed=bool(step.mutation and status_ok and not html_api_error),
            ambiguous=bool(step.mutation and (not status_ok or html_api_error)),
        )
    except Exception as exc:
        elapsed_ms = (monotonic() - started) * 1000
        return _ExecutedStep(
            result=WriteStepResult(
                name=step.name,
                method=step.method,
                path=step.path,
                status="fail",
                elapsed_ms=round(elapsed_ms, 3),
                status_code=None,
                response_bytes=0,
                content_type="",
                error=str(exc) or exc.__class__.__name__,
            ),
            captures={},
            committed=False,
            ambiguous=step.mutation,
        )


def _response_outbox_event_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    event_ids: list[str] = []
    for item in value:
        event_id = str(item or "").strip()
        if not event_id or event_id in event_ids:
            continue
        event_ids.append(event_id)
    return event_ids


def _reconcile_ambiguous_mutation(
    connection: Any,
    *,
    tenant_id: str,
    idempotency_key: str,
    step: WriteStep,
    variables: dict[str, Any],
) -> tuple[bool, bool]:
    try:
        evidence = write_operation_slo_audit.workbench_idempotency_evidence(
            connection,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
        )
    except Exception:
        return False, True
    status = str(evidence.get("status") or "")
    if status == "failed":
        return False, False
    if status != "committed":
        return False, True
    response_payload = evidence.get("response_payload")
    if step.captures:
        try:
            variables.update({name: _json_pointer(response_payload, pointer) for name, pointer in step.captures})
        except (KeyError, TypeError, ValueError):
            return True, True
    return True, False


def _validate_canonical_preview_payload(step: WriteStep, payload: Any) -> None:
    if step.path not in {CONFIRM_PREVIEW_PATH, WITHDRAW_PREVIEW_PATH}:
        return
    if not isinstance(payload, dict) or payload.get("can_submit") is not True:
        raise ValueError("canonical_relation_preview_not_submittable")
    if step.path == CONFIRM_PREVIEW_PATH:
        if payload.get("operation") != "confirm_link":
            raise ValueError("canonical_confirm_preview_operation_mismatch")
        return
    if (
        payload.get("operation") != "withdraw_link"
        or not str(payload.get("preview_id") or "").strip()
        or not isinstance(payload.get("submit_expected_versions"), dict)
        or not payload.get("submit_expected_versions")
    ):
        raise ValueError("canonical_withdraw_preview_contract_invalid")


def _response_diagnostics(
    body: bytes,
    content_type: str,
    headers: Mapping[str, str],
) -> tuple[str | None, str | None]:
    header_request_id = _header(headers, "x-request-id").strip() or None
    if "json" not in str(content_type or "").lower():
        return header_request_id, None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return header_request_id, None
    if not isinstance(payload, dict):
        return header_request_id, None
    request_id = (
        str(payload.get("requestId") or payload.get("request_id") or "").strip()
        or header_request_id
    )
    error_code = str(payload.get("error") or "").strip() or None
    return request_id, error_code


def _wait_for_write_slo(
    connection: Any,
    *,
    operations: Sequence[str],
    tenant_id: str,
    started_at: Any,
    target_ms: float,
    timeout_seconds: float,
    poll_interval_seconds: float,
    limit: int,
    event_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    expectations = write_operation_slo_audit.selected_expectations_for_operations(operations)
    p99_target_ms = write_operation_slo_audit.effective_p99_target_ms_for(target_ms, None)
    effective_limit = _effective_write_slo_event_sample_limit(limit, expectation_count=len(expectations))
    deadline = monotonic() + max(1.0, timeout_seconds)
    last_results: list[Any] = []
    last_rows: list[dict[str, Any]] = []
    last_unexpected_events: list[dict[str, Any]] = []
    expected_event_ids = set(event_ids or []) if event_ids is not None else None
    receipt_bound = event_ids is not None
    last_matched_event_ids: set[str] = set()
    while True:
        rows = write_operation_slo_audit.recent_read_model_refresh_events_since(
            connection,
            tenant_id=tenant_id,
            started_at=started_at,
            limit=effective_limit,
            expectations=None if receipt_bound else expectations,
            event_ids=event_ids,
        )
        results = write_operation_slo_audit.evaluate_operation_expectations(
            rows,
            expectations=expectations,
            target_ms=target_ms,
            p99_target_ms=p99_target_ms,
            match_metadata=not receipt_bound,
        )
        last_results = results
        last_rows = rows
        last_matched_event_ids = {
            str(row.get("event_id") or "").strip() for row in rows if str(row.get("event_id") or "").strip()
        }
        last_unexpected_events = [
            _event_contract_summary(row)
            for row in rows
            if not any(
                write_operation_slo_audit.event_matches_expectation(
                    row,
                    expectation,
                    match_metadata=not receipt_bound,
                )
                for expectation in expectations
            )
        ]
        exact_event_set_matches = expected_event_ids is None or last_matched_event_ids == expected_event_ids
        forbidden_fan_out_detected = any(
            bool(result.forbidden) and result.status == "fail" and result.sample_count > 0
            for result in results
        )
        if exact_event_set_matches and not last_unexpected_events and forbidden_fan_out_detected:
            return {
                "status": "fail",
                "target_ms": target_ms,
                "p99_target_ms": p99_target_ms,
                "requested_event_sample_limit": max(1, int(limit)),
                "effective_event_sample_limit": effective_limit,
                "event_sample_count": len(rows),
                "matched_event_ids": sorted(last_matched_event_ids),
                "unexpected_event_contracts": [],
                "error": "forbidden_write_time_read_model_fan_out_detected",
                "results": [asdict(result) for result in results],
            }
        if exact_event_set_matches and not last_unexpected_events and all(result.status == "pass" for result in results):
            return {
                "status": "pass",
                "target_ms": target_ms,
                "p99_target_ms": p99_target_ms,
                "requested_event_sample_limit": max(1, int(limit)),
                "effective_event_sample_limit": effective_limit,
                "event_sample_count": len(rows),
                "matched_event_ids": sorted(last_matched_event_ids),
                "unexpected_event_contracts": [],
                "results": [asdict(result) for result in results],
            }
        if monotonic() >= deadline:
            return {
                "status": "fail",
                "target_ms": target_ms,
                "p99_target_ms": p99_target_ms,
                "requested_event_sample_limit": max(1, int(limit)),
                "effective_event_sample_limit": effective_limit,
                "event_sample_count": len(last_rows),
                "matched_event_ids": sorted(last_matched_event_ids),
                "missing_or_unmatched_event_ids": sorted((expected_event_ids or set()) - last_matched_event_ids),
                "unexpected_event_contracts": last_unexpected_events,
                "error": (
                    "exact_checkpoint_event_set_mismatch"
                    if not exact_event_set_matches
                    else "unexpected_checkpoint_event_contract"
                    if last_unexpected_events
                    else "timeout_waiting_for_write_operation_refresh_slo"
                ),
                "results": [asdict(result) for result in last_results],
            }
        sleep(max(0.05, poll_interval_seconds))


def _event_contract_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(row.get("event_id") or "") or None,
        "event_type": str(row.get("event_type") or "") or None,
        "scope_type": str(row.get("scope_type") or "") or None,
        "scope_key": str(row.get("scope_key") or "") or None,
        "reason": str(row.get("reason") or "") or None,
        "action_name": str(row.get("action_name") or "") or None,
        "event_status": str(row.get("event_status") or "") or None,
        "dirty_status": str(row.get("dirty_status") or "") or None,
    }


def _collect_checkpoint_consumers(
    checkpoint: WriteCheckpoint,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    request_fn: RequestFn,
    variables: Mapping[str, Any],
    strict: bool,
    isolation_baseline: Mapping[str, Any] | None = None,
    operation_commit_ack_monotonic: float | None = None,
    consumers: Sequence[ConsumerProbe] | None = None,
    access_started_monotonic_by_consumer: dict[tuple[str, str, str], float] | None = None,
) -> dict[str, Any]:
    selected_consumers = tuple(checkpoint.consumers if consumers is None else consumers)
    if not selected_consumers:
        return {"status": "skipped", "reason": "no_post_api_probes"}
    if not strict and all(not consumer.assertions for consumer in selected_consumers):
        return http_slo_probe.collect_http_slo(
            base_url=base_url,
            api_prefix=api_prefix,
            probes=[consumer.probe for consumer in selected_consumers],
            headers=headers,
            iterations=1,
            warmup=0,
            timeout_seconds=timeout_seconds,
            require_auth=True,
            request_fn=lambda url, request_headers, timeout: request_fn(url, "GET", request_headers, None, timeout),
        )
    access_started = (
        access_started_monotonic_by_consumer
        if access_started_monotonic_by_consumer is not None
        else {}
    )

    def collect_consumer(consumer: ConsumerProbe) -> dict[str, Any]:
        key = (
            consumer.page_key,
            consumer.probe.name,
            str(_resolve_value(consumer.probe.path, variables)),
        )
        consumer_access_started = access_started.get(key)
        if consumer_access_started is None:
            consumer_access_started = monotonic()
            access_started[key] = consumer_access_started
        return _collect_checkpoint_consumer(
            consumer,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            timeout_seconds=timeout_seconds,
            request_fn=request_fn,
            variables=variables,
            isolation_baseline=isolation_baseline,
            operation_commit_ack_monotonic=operation_commit_ack_monotonic,
            access_started_monotonic=consumer_access_started,
        )
    worker_count = min(len(selected_consumers), MAX_PARALLEL_CONSUMER_PROBES)
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="consumer-probe") as executor:
        results = list(executor.map(collect_consumer, selected_consumers))
    return {
        "status": "pass" if all(result["status"] == "pass" for result in results) else "fail",
        "consumer_count": len(results),
        "results": results,
    }


def _collect_checkpoint_consumer(
    consumer: ConsumerProbe,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    request_fn: RequestFn,
    variables: Mapping[str, Any],
    isolation_baseline: Mapping[str, Any] | None,
    operation_commit_ack_monotonic: float | None = None,
    access_started_monotonic: float | None = None,
) -> dict[str, Any]:
    path = str(_resolve_value(consumer.probe.path, variables))
    if not consumer.assertions:
        return {
            "name": consumer.probe.name,
            "page_key": consumer.page_key,
            "role": consumer.role,
            "path": path,
            "status": "fail",
            "error": "consumer_assertion_required",
        }
    try:
        path, payload, read_model_status = _request_fresh_consumer_payload(
            consumer,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            timeout_seconds=timeout_seconds,
            request_fn=request_fn,
            variables=variables,
        )
        if consumer.role == "isolation":
            assertions = [
                _evaluate_isolation_assertion(
                    consumer,
                    assertion,
                    payload=payload,
                    baseline=isolation_baseline or {},
                )
                for assertion in consumer.assertions
            ]
        else:
            assertions = [
                _evaluate_json_assertion(assertion, payload=payload, variables=variables)
                for assertion in consumer.assertions
            ]
        failed = [assertion for assertion in assertions if assertion["status"] != "pass"]
        access_to_visible_ms = _elapsed_ms_since(access_started_monotonic)
        operation_commit_to_visible_ms = _elapsed_ms_since(operation_commit_ack_monotonic)
        visibility_slo_miss = (
            access_to_visible_ms is not None and access_to_visible_ms > consumer.probe.target_ms
        )
        return {
            "name": consumer.probe.name,
            "page_key": consumer.page_key,
            "role": consumer.role,
            "path": path,
            "status": "fail" if failed or visibility_slo_miss else "pass",
            "read_model_status": read_model_status,
            "assertions": assertions,
            **(
                {
                    "error": (
                        f"consumer_visibility_slo_miss:{round(access_to_visible_ms, 3)}"
                        f">{round(consumer.probe.target_ms, 3)}"
                    )
                }
                if visibility_slo_miss
                else {}
            ),
            **(
                {
                    "access_to_visible_ms": access_to_visible_ms,
                    "access_to_visible_clock": "first_consumer_access_started",
                }
                if access_to_visible_ms is not None
                else {}
            ),
            **(
                {
                    "operation_commit_to_visible_ms": operation_commit_to_visible_ms,
                    "operation_commit_clock": "successful_mutation_response_received",
                }
                if operation_commit_to_visible_ms is not None
                else {}
            ),
        }
    except Exception as exc:
        access_to_visible_ms = _elapsed_ms_since(access_started_monotonic)
        operation_commit_to_visible_ms = _elapsed_ms_since(operation_commit_ack_monotonic)
        return {
            "name": consumer.probe.name,
            "page_key": consumer.page_key,
            "role": consumer.role,
            "path": path,
            "status": "fail",
            "error": str(exc) or exc.__class__.__name__,
            **(
                {
                    "access_to_visible_ms": access_to_visible_ms,
                    "access_to_visible_clock": "first_consumer_access_started",
                }
                if access_to_visible_ms is not None
                else {}
            ),
            **(
                {
                    "operation_commit_to_visible_ms": operation_commit_to_visible_ms,
                    "operation_commit_clock": "successful_mutation_response_received",
                }
                if operation_commit_to_visible_ms is not None
                else {}
            ),
        }


_RETRYABLE_CONSUMER_ERRORS = {
    "consumer_read_model_not_fresh",
    "unexpected_status:202",
    "unexpected_status:503",
}


def _elapsed_ms_since(started_monotonic: float | None) -> float | None:
    if started_monotonic is None:
        return None
    return round(max(0.0, monotonic() - started_monotonic) * 1000, 3)


def _consumer_result_key(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("page_key") or ""),
        str(item.get("name") or ""),
        str(item.get("path") or ""),
    )


def _consumer_failure_is_retryable(item: Mapping[str, Any]) -> bool:
    error = str(item.get("error") or "")
    if error in _RETRYABLE_CONSUMER_ERRORS:
        return True
    if str(item.get("role") or "affected") != "affected":
        return False
    assertions = list(item.get("assertions") or [])
    failed_assertions = [assertion for assertion in assertions if assertion.get("status") != "pass"]
    return bool(failed_assertions) and all(
        str(assertion.get("error") or "") in {"json_assertion_mismatch", "consumer_source_version_unchanged"}
        for assertion in failed_assertions
    )


def _wait_for_checkpoint_consumers(
    checkpoint: WriteCheckpoint,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    poll_interval_seconds: float,
    request_fn: RequestFn,
    variables: Mapping[str, Any],
    strict: bool,
    isolation_baseline: Mapping[str, Any] | None = None,
    operation_commit_ack_monotonic: float | None = None,
) -> dict[str, Any]:
    deadline = monotonic() + max(1.0, timeout_seconds)
    access_started_monotonic_by_consumer: dict[tuple[str, str, str], float] = {}
    settled: dict[tuple[str, str, str], dict[str, Any]] = {}
    pending = list(checkpoint.consumers)
    while True:
        result = _collect_checkpoint_consumers(
            checkpoint,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            timeout_seconds=timeout_seconds,
            request_fn=request_fn,
            variables=variables,
            strict=strict,
            isolation_baseline=isolation_baseline,
            operation_commit_ack_monotonic=operation_commit_ack_monotonic,
            consumers=pending,
            access_started_monotonic_by_consumer=access_started_monotonic_by_consumer,
        )
        unresolved: list[ConsumerProbe] = []
        for consumer, item in zip(pending, list(result.get("results") or []), strict=True):
            key = _consumer_result_key(item)
            if item.get("status") == "pass" or not _consumer_failure_is_retryable(item):
                settled[key] = dict(item)
            else:
                unresolved.append(consumer)
        pending = unresolved
        if not pending or monotonic() >= deadline:
            for item in list(result.get("results") or []):
                settled.setdefault(_consumer_result_key(item), dict(item))
            ordered_results = [
                settled[
                    (
                        consumer.page_key,
                        consumer.probe.name,
                        str(_resolve_value(consumer.probe.path, variables)),
                    )
                ]
                for consumer in checkpoint.consumers
            ]
            return {
                "status": "pass" if all(item.get("status") == "pass" for item in ordered_results) else "fail",
                "consumer_count": len(ordered_results),
                "results": ordered_results,
            }
        sleep(max(0.05, poll_interval_seconds))


def _capture_isolation_baseline(
    checkpoint: WriteCheckpoint,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    request_fn: RequestFn,
    variables: Mapping[str, Any],
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    isolation_consumers = [consumer for consumer in checkpoint.consumers if consumer.role == "isolation"]
    if not isolation_consumers:
        return {"status": "pass", "values": {}}
    values: dict[str, Any] = {}
    try:
        for consumer in isolation_consumers:
            _path, payload, _read_model_status = _wait_for_fresh_consumer_payload(
                consumer,
                base_url=base_url,
                api_prefix=api_prefix,
                headers=headers,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                request_fn=request_fn,
                variables=variables,
                enforce_slo=False,
            )
            for assertion in consumer.assertions:
                values[_isolation_key(consumer.page_key, assertion.pointer)] = _json_pointer(
                    payload,
                    assertion.pointer,
                )
    except Exception as exc:
        return {"status": "fail", "error": f"isolation_baseline_failed:{str(exc) or exc.__class__.__name__}"}
    return {"status": "pass", "values": values}


def _request_fresh_consumer_payload(
    consumer: ConsumerProbe,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    request_fn: RequestFn,
    variables: Mapping[str, Any],
    enforce_slo: bool = True,
) -> tuple[str, Any, Any]:
    path = str(_resolve_value(consumer.probe.path, variables))
    url = http_slo_probe.resolve_probe_url(base_url, path, api_prefix=api_prefix)
    started = monotonic()
    response = request_fn(url, "GET", headers, None, timeout_seconds)
    elapsed_ms = (monotonic() - started) * 1000
    content_type = _header(response.headers, "content-type")
    status_ok = response.status_code in consumer.probe.expected_statuses
    html_error = http_slo_probe._html_response_error(consumer.probe, content_type, response.body or b"")
    if not status_ok or html_error:
        raise ValueError(html_error or f"unexpected_status:{response.status_code}")
    if enforce_slo and elapsed_ms > consumer.probe.target_ms:
        raise ValueError(f"consumer_slo_miss:{round(elapsed_ms, 3)}>{round(consumer.probe.target_ms, 3)}")
    payload = json.loads((response.body or b"").decode("utf-8"))
    metadata = http_slo_probe._extract_response_metadata(response.body or b"", content_type)
    statistics_status = (
        str(payload.get("statistics_status") or "").strip().lower()
        if isinstance(payload, dict)
        else ""
    )
    if (
        metadata.get("read_model_status") != "fresh"
        or metadata.get("refresh_enqueued") is True
        or (statistics_status and statistics_status != "fresh")
        or (isinstance(payload, dict) and payload.get("statistics_refresh_enqueued") is True)
    ):
        raise ValueError("consumer_read_model_not_fresh")
    return path, payload, metadata.get("read_model_status")


def _wait_for_fresh_consumer_payload(
    consumer: ConsumerProbe,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    poll_interval_seconds: float,
    request_fn: RequestFn,
    variables: Mapping[str, Any],
    enforce_slo: bool = True,
) -> tuple[str, Any, Any]:
    deadline = monotonic() + max(1.0, timeout_seconds)
    while True:
        try:
            return _request_fresh_consumer_payload(
                consumer,
                base_url=base_url,
                api_prefix=api_prefix,
                headers=headers,
                timeout_seconds=timeout_seconds,
                request_fn=request_fn,
                variables=variables,
                enforce_slo=enforce_slo,
            )
        except ValueError as exc:
            if str(exc) not in _RETRYABLE_CONSUMER_ERRORS or monotonic() >= deadline:
                raise
        sleep(max(0.05, poll_interval_seconds))


def _evaluate_isolation_assertion(
    consumer: ConsumerProbe,
    assertion: JsonPointerAssertion,
    *,
    payload: Any,
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    key = _isolation_key(consumer.page_key, assertion.pointer)
    if key not in baseline:
        return {
            "pointer": assertion.pointer,
            "operator": "unchanged",
            "status": "fail",
            "error": "isolation_baseline_missing",
        }
    try:
        passed = _json_pointer(payload, assertion.pointer) == baseline[key]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return {
            "pointer": assertion.pointer,
            "operator": "unchanged",
            "status": "fail",
            "error": f"json_pointer_unavailable:{exc}",
        }
    return {
        "pointer": assertion.pointer,
        "operator": "unchanged",
        "status": "pass" if passed else "fail",
        **({"error": "non_consumer_changed"} if not passed else {}),
    }


def _isolation_key(page_key: str, pointer: str) -> str:
    return f"{page_key}\x1f{pointer}"


def _evaluate_json_assertion(
    assertion: JsonPointerAssertion,
    *,
    payload: Any,
    variables: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        actual = _json_pointer(payload, assertion.pointer)
        expected = _resolve_value(assertion.expected, variables)
        if assertion.operator == "equals":
            passed = actual == expected
        elif assertion.operator == "contains":
            if isinstance(actual, str):
                passed = str(expected) in actual
            elif isinstance(actual, list):
                passed = expected in actual
            elif isinstance(actual, dict) and isinstance(expected, dict):
                passed = all(actual.get(key) == value for key, value in expected.items())
            else:
                passed = False
        elif assertion.operator == "excludes":
            passed = not bool(_string_leaves(actual) & _string_leaves(expected))
        else:
            raise ValueError(f"unsupported_json_assertion_operator:{assertion.operator}")
        return {
            "pointer": assertion.pointer,
            "operator": assertion.operator,
            "status": "pass" if passed else "fail",
            **({"error": "json_assertion_mismatch"} if not passed else {}),
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return {
            "pointer": assertion.pointer,
            "operator": assertion.operator,
            "status": "fail",
            "error": f"json_pointer_unavailable:{exc}",
        }


def _collect_system_audit(
    checkpoint: WriteCheckpoint,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    request_fn: RequestFn,
) -> dict[str, Any]:
    if not checkpoint.system_audit_path:
        return {"status": "skipped", "reason": "system_audit_not_requested"}
    path = checkpoint.system_audit_path
    if path != SYSTEM_AUDIT_PATH:
        return {"status": "fail", "error": "system_audit_path_not_canonical"}
    url = http_slo_probe.resolve_probe_url(base_url, path, api_prefix=api_prefix)
    try:
        response = request_fn(url, "GET", headers, None, timeout_seconds)
        if response.status_code != 200:
            raise ValueError(f"unexpected_status:{response.status_code}")
        payload = json.loads((response.body or b"").decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("system_audit_payload_not_object")
        snapshot = payload.get("database_system_snapshot")
        contract = payload.get("audit_contract")
        summary = payload.get("summary")
        audit_status = payload.get("audit_status")
        if (
            not isinstance(snapshot, dict)
            or not snapshot.get("system_audit_id")
            or not snapshot.get("snapshot_identity")
        ):
            raise ValueError("system_audit_snapshot_missing")
        if (
            snapshot.get("database_snapshot") is not True
            or snapshot.get("snapshot_consistency") != "repeatable_read_read_only"
        ):
            raise ValueError("system_audit_snapshot_not_repeatable_read_only")
        if not isinstance(contract, dict) or not contract:
            raise ValueError("system_audit_contract_missing")
        if not isinstance(summary, dict) or (
            summary.get("registered_page_count") != 17
            or summary.get("audited_business_page_count") != 16
            or summary.get("passed_business_page_count") != 16
            or summary.get("database_internal_contracts") != "pass"
        ):
            raise ValueError("system_audit_page_count_or_contract_failed")
        if (
            payload.get("overall_status") != "pass"
            or not isinstance(audit_status, dict)
            or any(
                audit_status.get(key) != expected
                for key, expected in (("integrity", "pass"), ("freshness", "fresh"), ("queue", "drained"))
            )
        ):
            raise ValueError("system_audit_internal_gate_failed")
        page_results = snapshot.get("page_results")
        if (
            not isinstance(page_results, list)
            or len(page_results) != 16
            or any(
                not isinstance(page, dict)
                or page.get("overall_status") != "pass"
                or not isinstance(page.get("audit_status"), dict)
                or page["audit_status"].get("integrity") != "pass"
                or page["audit_status"].get("freshness") != "fresh"
                or page["audit_status"].get("queue") != "drained"
                for page in page_results
            )
        ):
            raise ValueError("system_audit_business_pages_failed")
        external_status = str((payload.get("external_evidence") or {}).get("status") or "unknown")
        if external_status not in {"pass", "unknown"}:
            raise ValueError("system_audit_external_evidence_failed")
        return {
            "status": "pass",
            "system_audit_id": str(snapshot["system_audit_id"]),
            "snapshot_identity": str(snapshot["snapshot_identity"]),
            "external_evidence": external_status,
        }
    except Exception as exc:
        return {"status": "fail", "error": str(exc) or exc.__class__.__name__}


_RETRYABLE_SYSTEM_AUDIT_ERRORS = {
    "system_audit_page_count_or_contract_failed",
    "system_audit_internal_gate_failed",
    "system_audit_business_pages_failed",
    "system_audit_id_reused",
    "unexpected_status:500",
    "unexpected_status:502",
    "unexpected_status:503",
    "unexpected_status:504",
}


def _wait_for_system_audit(
    checkpoint: WriteCheckpoint,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    poll_interval_seconds: float,
    request_fn: RequestFn,
    excluded_audit_ids: set[str],
) -> dict[str, Any]:
    deadline = monotonic() + max(1.0, timeout_seconds)
    last_result: dict[str, Any] = {"status": "fail", "error": "system_audit_not_attempted"}
    while True:
        result = _collect_system_audit(
            checkpoint,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            timeout_seconds=timeout_seconds,
            request_fn=request_fn,
        )
        if result.get("status") == "pass":
            audit_id = str(result.get("system_audit_id") or "")
            if audit_id and audit_id not in excluded_audit_ids:
                return result
            result = {"status": "fail", "error": "system_audit_id_reused"}
        last_result = result
        error = str(result.get("error") or "")
        if error not in _RETRYABLE_SYSTEM_AUDIT_ERRORS or monotonic() >= deadline:
            return last_result
        sleep(max(0.05, poll_interval_seconds))


def _effective_write_slo_event_sample_limit(limit: int, *, expectation_count: int) -> int:
    return max(
        1,
        int(limit),
        MIN_WRITE_SLO_EVENT_SAMPLE_LIMIT,
        int(expectation_count) * 4,
    )


def _database_timestamp(connection: Any) -> Any:
    row = connection.fetch_one("select clock_timestamp() as started_at") or {}
    return row.get("started_at") or datetime.now(UTC)


def _http_request(
    url: str,
    method: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout_seconds: float,
) -> http_slo_probe.HttpProbeResponse:
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    request = Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - operator-provided URL.
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return http_slo_probe.HttpProbeResponse(
                status_code=int(response.getcode()),
                headers=response_headers,
                body=http_slo_probe._decoded_response_body(response.read(), response_headers),
            )
    except HTTPError as exc:
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
        return http_slo_probe.HttpProbeResponse(
            status_code=int(exc.code),
            headers=response_headers,
            body=http_slo_probe._decoded_response_body(exc.read(), response_headers),
        )
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(str(reason) or exc.__class__.__name__) from exc


def _load_steps(raw_steps: Any, *, scenario_name: str) -> list[WriteStep]:
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError(f"scenario {scenario_name!r} must include a non-empty steps list.")
    steps: list[WriteStep] = []
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"scenario {scenario_name!r} step #{index} must be an object.")
        name = str(raw.get("name") or f"step_{index}").strip() or f"step_{index}"
        method = str(raw.get("method") or "POST").strip().upper() or "POST"
        path = str(raw.get("path") or "").strip()
        if not path:
            raise ValueError(f"scenario {scenario_name!r} step {name!r} must include path.")
        expected_statuses = tuple(int(value) for value in list(raw.get("expected_statuses") or [200]))
        json_body = raw.get("json")
        if json_body is not None and not isinstance(json_body, dict):
            raise ValueError(f"scenario {scenario_name!r} step {name!r} json must be an object when provided.")
        raw_captures = raw.get("captures") or {}
        if not isinstance(raw_captures, dict) or any(
            not str(key or "").strip() or not str(value or "").startswith("/") for key, value in raw_captures.items()
        ):
            raise ValueError(f"scenario {scenario_name!r} step {name!r} captures must map names to JSON Pointers.")
        steps.append(
            WriteStep(
                name=name,
                method=method,
                path=path,
                json_body=dict(json_body) if isinstance(json_body, dict) else None,
                expected_statuses=expected_statuses,
                mutation=bool(raw.get("mutation", method not in {"GET", "HEAD", "OPTIONS"})),
                captures=tuple((str(key), str(value)) for key, value in raw_captures.items()),
            )
        )
    return steps


def _reversible_relation_contracts() -> dict[str, dict[str, Any]]:
    consumer_probe_paths = {
        page_key: str(contract["path"]) for page_key, contract in REVERSIBLE_RELATION_CONSUMER_CONTRACTS.items()
    }
    consumer_business_roots = {
        page_key: list(contract["business_roots"])
        for page_key, contract in REVERSIBLE_RELATION_CONSUMER_CONTRACTS.items()
    }
    return {
        shape: {
            **contract,
            "consumer_probe_paths": consumer_probe_paths,
            "consumer_business_roots": consumer_business_roots,
        }
        for shape, contract in REVERSIBLE_RELATION_SHAPE_CONTRACTS.items()
    }


def _validate_reversible_checkpoint_contract(
    *,
    scenario_name: str,
    checkpoints: tuple[WriteCheckpoint, ...],
    recovery_checkpoint: WriteCheckpoint | None,
    relation_contract: Mapping[str, Any],
) -> None:
    if len(checkpoints) != 2:
        raise ValueError(f"scenario {scenario_name!r} must contain confirm and withdraw checkpoints.")
    expected_profiles = (
        str(relation_contract.get("confirm_profile") or ""),
        str(relation_contract.get("withdraw_profile") or ""),
    )
    expected_states = ("active", "inactive")
    mutation_contract = str(relation_contract.get("mutation_contract") or "").strip()
    if mutation_contract not in {"workbench_relation", "turnover_closure"}:
        raise ValueError(f"scenario {scenario_name!r} has an unsupported mutation contract.")
    expected_roles = {
        **{
            str(page_key): "affected"
            for page_key in list(relation_contract.get("affected_consumer_page_keys") or [])
            if str(page_key).strip()
        },
        **{
            str(page_key): "isolation"
            for page_key in list(relation_contract.get("non_consumer_isolation_page_keys") or [])
            if str(page_key).strip()
        },
    }
    expected_probe_paths = {
        str(page_key): str(path)
        for page_key, path in dict(relation_contract.get("consumer_probe_paths") or {}).items()
        if page_key in expected_roles
    }
    if set(expected_probe_paths) != set(expected_roles):
        raise ValueError(f"scenario {scenario_name!r} has incomplete consumer probe path contracts.")
    expected_business_roots = {
        str(page_key): frozenset(str(root) for root in roots if str(root).strip())
        for page_key, roots in dict(relation_contract.get("consumer_business_roots") or {}).items()
        if page_key in expected_roles and isinstance(roots, list)
    }
    if set(expected_business_roots) != set(expected_roles) or any(
        not roots for roots in expected_business_roots.values()
    ):
        raise ValueError(f"scenario {scenario_name!r} has incomplete consumer business-root contracts.")
    for checkpoint, expected_profile, expected_state, direction in zip(
        checkpoints,
        expected_profiles,
        expected_states,
        ("confirm", "withdraw"),
        strict=True,
    ):
        if checkpoint.operations != (expected_profile,) or checkpoint.relation_state_after != expected_state:
            raise ValueError(
                f"scenario {scenario_name!r} checkpoint order must match registered confirm/withdraw profiles."
            )
        _validate_checkpoint_consumers_and_rows(
            scenario_name=scenario_name,
            checkpoint=checkpoint,
            expected_roles=expected_roles,
            mutation_contract=mutation_contract,
            expected_probe_paths=expected_probe_paths,
            expected_business_roots=expected_business_roots,
        )
        if mutation_contract == "workbench_relation":
            _validate_canonical_relation_steps(
                scenario_name=scenario_name,
                checkpoint=checkpoint,
                direction=direction,
            )
        else:
            _validate_turnover_closure_steps(
                scenario_name=scenario_name,
                checkpoint=checkpoint,
                direction=direction,
            )
    if recovery_checkpoint is None or recovery_checkpoint.operations != (expected_profiles[1],):
        raise ValueError(f"scenario {scenario_name!r} recovery checkpoint must use the registered withdraw profile.")
    _validate_checkpoint_consumers_and_rows(
        scenario_name=scenario_name,
        checkpoint=recovery_checkpoint,
        expected_roles=expected_roles,
        mutation_contract=mutation_contract,
        expected_probe_paths=expected_probe_paths,
        expected_business_roots=expected_business_roots,
    )
    if mutation_contract == "workbench_relation":
        _validate_canonical_relation_steps(
            scenario_name=scenario_name,
            checkpoint=recovery_checkpoint,
            direction="withdraw",
        )
    else:
        _validate_turnover_closure_steps(
            scenario_name=scenario_name,
            checkpoint=recovery_checkpoint,
            direction="withdraw",
        )
        if not checkpoints[0].fixture_row_ids or any(
            checkpoint.fixture_row_ids != checkpoints[0].fixture_row_ids
            for checkpoint in (*checkpoints, recovery_checkpoint)
        ):
            raise ValueError(f"scenario {scenario_name!r} turnover checkpoints must use the same fixture_row_ids.")
        closure_case_capture = next(
            name
            for name, pointer in checkpoints[0].steps[0].captures
            if pointer == "/workbench_pair_relation/case_id"
        )
        expected_withdraw_path = "/api/turnover-ledger/closures/withdraw"
        if any(
            checkpoint.steps[0].path != expected_withdraw_path
            or (checkpoint.steps[0].json_body or {}).get("cash_closure_case_id") != f"${{{closure_case_capture}}}"
            for checkpoint in (checkpoints[1], recovery_checkpoint)
        ):
            raise ValueError(
                f"scenario {scenario_name!r} turnover withdraw checkpoints must consume the canonical closure case_id."
            )


def _validate_checkpoint_consumers_and_rows(
    *,
    scenario_name: str,
    checkpoint: WriteCheckpoint,
    expected_roles: Mapping[str, str],
    mutation_contract: str,
    expected_probe_paths: Mapping[str, str],
    expected_business_roots: Mapping[str, frozenset[str]],
) -> None:
    page_keys = [consumer.page_key for consumer in checkpoint.consumers]
    consumer_counts = {page_key: page_keys.count(page_key) for page_key in set(page_keys)}
    invalid_scope_counts = [
        page_key
        for page_key, count in consumer_counts.items()
        if count > MAX_AFFECTED_CONSUMER_SCOPES_PER_PAGE
        or (expected_roles.get(page_key) == "isolation" and count != 1)
    ]
    if set(page_keys) != set(expected_roles) or invalid_scope_counts:
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} consumers must exactly match "
            "the registered affected and isolation pages; an affected page may declare at most three exact "
            "scope probes, while an isolation page must declare exactly one."
        )
    if any(consumer.role != expected_roles[consumer.page_key] for consumer in checkpoint.consumers):
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} consumer roles must match the impact matrix."
        )
    if any(
        str(consumer.probe.path).split("?", 1)[0] != expected_probe_paths[consumer.page_key]
        for consumer in checkpoint.consumers
    ):
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} consumer paths must match the impact matrix."
        )
    for consumer in checkpoint.consumers:
        invalid_pointers = [
            assertion.pointer
            for assertion in consumer.assertions
            if _json_pointer_root(assertion.pointer) not in expected_business_roots[consumer.page_key]
        ]
        if invalid_pointers:
            raise ValueError(
                f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} consumer "
                f"{consumer.page_key!r} assertions must target registered business roots; "
                f"invalid pointers: {invalid_pointers}."
            )
    mutation = next(step for step in checkpoint.steps if step.mutation)
    row_ids = (
        (mutation.json_body or {}).get("row_ids")
        if mutation_contract == "workbench_relation"
        else list(checkpoint.fixture_row_ids)
    )
    if (
        not isinstance(row_ids, list)
        or not row_ids
        or len(row_ids) > MAX_TEST_OWNED_RELATION_ROW_IDS
        or any(not isinstance(row_id, str) or not row_id.strip() for row_id in row_ids)
        or len(row_ids) != len(set(row_ids))
    ):
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} requires 1.."
            f"{MAX_TEST_OWNED_RELATION_ROW_IDS} explicit test-owned row_ids."
        )
    captured_names = {
        capture_name
        for step in checkpoint.steps
        for capture_name, pointer in step.captures
        if pointer in {
            "/case_id",
            "/active_relation/case_id",
            "/workbench_pair_relation/case_id",
        }
    }
    for page_key in {
        consumer.page_key
        for consumer in checkpoint.consumers
        if consumer.role == "affected"
    }:
        page_consumers = [
            consumer
            for consumer in checkpoint.consumers
            if consumer.page_key == page_key
        ]
        if not any(
            _assertion_binds_fixture_identity(
                assertion,
                row_ids=set(row_ids),
                captured_names=captured_names,
            )
            for consumer in page_consumers
            for assertion in consumer.assertions
        ):
            raise ValueError(
                f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} affected page "
                f"{page_key!r} must have at least one consumer asserting a test-owned row "
                "or preview-captured identity."
            )


def _validate_canonical_relation_steps(
    *,
    scenario_name: str,
    checkpoint: WriteCheckpoint,
    direction: str,
) -> None:
    expected_preview_path, expected_mutation_path = (
        (CONFIRM_PREVIEW_PATH, CONFIRM_MUTATION_PATH)
        if direction == "confirm"
        else (WITHDRAW_PREVIEW_PATH, WITHDRAW_MUTATION_PATH)
    )
    if len(checkpoint.steps) != 3:
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} must contain exactly "
            "read-version, preview, and mutation steps."
        )
    read_version, preview, mutation = checkpoint.steps
    if (
        preview.mutation
        or preview.method != "POST"
        or preview.path != expected_preview_path
        or preview.expected_statuses != (200,)
        or not mutation.mutation
        or mutation.method != "POST"
        or mutation.path != expected_mutation_path
        or mutation.expected_statuses != (200,)
    ):
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} must use the canonical Workbench "
            f"{direction} preview and mutation endpoints."
        )
    preview_rows = (preview.json_body or {}).get("row_ids")
    mutation_rows = (mutation.json_body or {}).get("row_ids")
    preview_month = str((preview.json_body or {}).get("month") or "").strip()
    mutation_month = str((mutation.json_body or {}).get("month") or "").strip()
    if not preview_month or preview_month != mutation_month or preview_rows != mutation_rows:
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} preview and mutation month/row_ids must match."
        )
    read_version_captures = [
        name for name, pointer in read_version.captures if pointer == "/read_model_version"
    ]
    if (
        len(read_version_captures) != 1
        or read_version.mutation
        or read_version.method != "GET"
        or read_version.path != f"/api/workbench?month={preview_month}"
        or read_version.json_body is not None
        or read_version.expected_statuses != (200,)
    ):
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} must read and capture the exact "
            "Workbench read_model_version for its month before preview."
        )
    expected_read_model_version = f"${{{read_version_captures[0]}}}"
    if (
        (preview.json_body or {}).get("expected_read_model_version") != expected_read_model_version
        or (mutation.json_body or {}).get("expected_read_model_version") != expected_read_model_version
    ):
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} preview and mutation must consume "
            "the captured Workbench read_model_version."
        )
    if direction == "confirm":
        if (preview.json_body or {}).get("case_id") != (mutation.json_body or {}).get("case_id"):
            raise ValueError(
                f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} preview and mutation case_id must match."
            )
        if set(preview.json_body or {}) - {
            "month",
            "row_ids",
            "case_id",
            "expected_read_model_version",
        } or set(mutation.json_body or {}) - {
            "month",
            "row_ids",
            "case_id",
            "expected_read_model_version",
            "note",
            "comment",
            "idempotency_key",
        }:
            raise ValueError(
                f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} contains unsupported confirm fields."
            )
        return
    capture_pointers = {name: pointer for name, pointer in preview.captures}
    preview_id_names = [name for name, pointer in capture_pointers.items() if pointer == "/preview_id"]
    version_names = [name for name, pointer in capture_pointers.items() if pointer == "/submit_expected_versions"]
    mutation_body = mutation.json_body or {}
    if (
        len(preview_id_names) != 1
        or len(version_names) != 1
        or mutation_body.get("preview_id") != f"${{{preview_id_names[0]}}}"
        or mutation_body.get("expected_versions") != f"${{{version_names[0]}}}"
        or mutation_body.get("operation_type") != "withdraw_relation"
        or set(preview.json_body or {}) - {"month", "row_ids", "expected_read_model_version"}
        or set(mutation_body)
        - {
            "month",
            "row_ids",
            "expected_read_model_version",
            "operation_type",
            "preview_id",
            "expected_versions",
            "idempotency_key",
            "note",
            "comment",
        }
    ):
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} withdraw must consume preview_id "
            "and submit_expected_versions captured from the official preview."
        )


def _validate_turnover_closure_steps(
    *,
    scenario_name: str,
    checkpoint: WriteCheckpoint,
    direction: str,
) -> None:
    if len(checkpoint.steps) != 1 or not checkpoint.steps[0].mutation:
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} turnover closure must contain one mutation."
        )
    mutation = checkpoint.steps[0]
    body = mutation.json_body or {}
    if mutation.method != "POST" or mutation.expected_statuses != (200,):
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} turnover closure must use POST/200."
        )
    if direction == "confirm":
        expected_versions = body.get("expected_versions")
        if mutation.path != "/api/turnover-ledger/closures/confirm":
            raise ValueError(
                f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} must use the canonical turnover confirm endpoint."
            )
        if (
            body.get("bank_row_ids") != list(checkpoint.fixture_row_ids)
            or not isinstance(expected_versions, dict)
            or set(expected_versions) != {f"turnover_bank_row:{row_id}" for row_id in checkpoint.fixture_row_ids}
            or set(body) - {"bank_row_ids", "expected_versions", "idempotency_key", "note"}
        ):
            raise ValueError(
                f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} turnover confirm requires fixture rows and expected_versions."
            )
        closure_captures = [
            name
            for name, pointer in mutation.captures
            if pointer == "/workbench_pair_relation/case_id"
        ]
        if len(closure_captures) != 1:
            raise ValueError(
                f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} must capture the canonical closure case_id."
            )
        return
    closure_case_id = body.get("cash_closure_case_id")
    if (
        mutation.path != "/api/turnover-ledger/closures/withdraw"
        or len(_placeholder_names(closure_case_id)) != 1
        or set(body) - {"cash_closure_case_id", "idempotency_key", "note"}
    ):
        raise ValueError(
            f"scenario {scenario_name!r} checkpoint {checkpoint.name!r} must use the captured canonical closure withdraw endpoint."
        )


def _assertion_binds_fixture_identity(
    assertion: JsonPointerAssertion,
    *,
    row_ids: set[str],
    captured_names: set[str],
) -> bool:
    if _placeholder_names(assertion.expected) & captured_names:
        return True
    return bool(_string_leaves(assertion.expected) & row_ids)


def _json_pointer_root(pointer: str) -> str:
    token = pointer.split("/", 2)[1] if pointer.startswith("/") else ""
    return token.replace("~1", "/").replace("~0", "~")


def _string_leaves(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, (list, tuple)):
        return {item for value_item in value for item in _string_leaves(value_item)}
    if isinstance(value, dict):
        return {item for value_item in value.values() for item in _string_leaves(value_item)}
    return set()


def _load_checkpoint(
    raw: Any,
    *,
    scenario_name: str,
    checkpoint_index: int,
    http_target_ms: float,
    strict: bool,
    consumer_roles: Mapping[str, str] | None = None,
) -> WriteCheckpoint:
    if not isinstance(raw, dict):
        raise ValueError(f"scenario {scenario_name!r} checkpoint #{checkpoint_index} must be an object.")
    name = str(raw.get("name") or f"checkpoint_{checkpoint_index}").strip()
    operations = tuple(str(item or "").strip() for item in list(raw.get("operations") or []) if str(item or "").strip())
    if not operations:
        operation = str(raw.get("operation") or "").strip()
        operations = (operation,) if operation else ()
    if not operations:
        raise ValueError(f"checkpoint {name!r} must include operation or operations.")
    write_operation_slo_audit.selected_expectations_for_operations(operations)
    steps = tuple(_load_steps(raw.get("steps"), scenario_name=f"{scenario_name}/{name}"))
    mutations = [step for step in steps if step.mutation]
    if strict and len(mutations) != 1:
        raise ValueError(f"checkpoint {name!r} must contain exactly one mutation step.")
    if strict:
        idempotency_key = str((mutations[0].json_body or {}).get("idempotency_key") or "").strip()
        if not idempotency_key or "${" in idempotency_key:
            raise ValueError(f"checkpoint {name!r} mutation must include a static idempotency_key.")
    consumers = tuple(
        _load_consumer(
            item,
            index=index,
            default_target_ms=http_target_ms,
            role=(consumer_roles or {}).get(str(item.get("page_key") or "").strip(), "affected")
            if isinstance(item, dict)
            else "affected",
        )
        for index, item in enumerate(list(raw.get("consumers") or []), start=1)
    )
    if strict and (not consumers or any(not consumer.assertions for consumer in consumers)):
        raise ValueError(f"checkpoint {name!r} must include typed consumer assertions.")
    system_audit = raw.get("system_audit")
    if strict and system_audit is not True:
        raise ValueError(f"checkpoint {name!r} must enable system_audit.")
    system_audit_path = SYSTEM_AUDIT_PATH if system_audit is True else None
    relation_state_after = raw.get("relation_state_after")
    if relation_state_after not in (None, "active", "inactive"):
        raise ValueError(f"checkpoint {name!r} relation_state_after must be active or inactive.")
    fixture_row_ids = tuple(
        str(row_id).strip() for row_id in list(raw.get("fixture_row_ids") or []) if str(row_id).strip()
    )
    return WriteCheckpoint(
        name=name,
        operations=operations,
        steps=steps,
        consumers=consumers,
        system_audit_path=system_audit_path,
        relation_state_after=relation_state_after,
        fixture_row_ids=fixture_row_ids,
    )


def _load_consumer(raw: Any, *, index: int, default_target_ms: float, role: str = "affected") -> ConsumerProbe:
    if not isinstance(raw, dict):
        raise ValueError(f"consumer #{index} must be an object.")
    path = str(raw.get("path") or "").strip()
    if not path:
        raise ValueError(f"consumer #{index} path is required.")
    page_key = str(raw.get("page_key") or "").strip()
    if not page_key:
        raise ValueError(f"consumer #{index} page_key is required.")
    raw_assertions = raw.get("assertions")
    if not isinstance(raw_assertions, list) or not raw_assertions:
        raise ValueError(f"consumer #{index} assertions must be a non-empty list.")
    assertions: list[JsonPointerAssertion] = []
    for assertion_index, item in enumerate(raw_assertions, start=1):
        if not isinstance(item, dict) or not str(item.get("pointer") or "").startswith("/"):
            raise ValueError(f"consumer #{index} assertion #{assertion_index} requires a JSON Pointer.")
        operators = [operator for operator in ("equals", "contains", "excludes") if operator in item]
        if len(operators) != 1:
            raise ValueError(
                f"consumer #{index} assertion #{assertion_index} requires exactly one "
                "equals/contains/excludes."
            )
        operator = operators[0]
        assertions.append(
            JsonPointerAssertion(
                pointer=str(item["pointer"]),
                operator=operator,
                expected=item[operator],
            )
        )
    statuses = raw.get("expected_statuses") or [200]
    return ConsumerProbe(
        probe=http_slo_probe.HttpProbe(
            name=str(raw.get("name") or f"consumer_{index}").strip() or f"consumer_{index}",
            path=path,
            kind="api",
            expected_statuses=tuple(int(value) for value in statuses),
            target_ms=float(raw.get("target_ms") or default_target_ms),
        ),
        assertions=tuple(assertions),
        page_key=page_key,
        role=role,
    )


def _load_post_api_probes(raw_probes: Any, *, default_target_ms: float) -> list[http_slo_probe.HttpProbe]:
    if raw_probes in (None, []):
        return []
    if not isinstance(raw_probes, list):
        raise ValueError("post_api_probes must be a list when provided.")
    probes: list[http_slo_probe.HttpProbe] = []
    for index, raw in enumerate(raw_probes, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"post_api_probe #{index} must be an object.")
        statuses = raw.get("expected_statuses", [200, 202])
        if not isinstance(statuses, list) or not statuses:
            raise ValueError(f"post_api_probe #{index} expected_statuses must be a non-empty list.")
        probes.append(
            http_slo_probe.HttpProbe(
                name=str(raw.get("name") or f"post_api_{index}").strip() or f"post_api_{index}",
                path=str(raw.get("path") or "").strip(),
                kind="api",
                expected_statuses=tuple(int(value) for value in statuses),
                target_ms=float(raw.get("target_ms") or default_target_ms),
            )
        )
    return probes


def _scenario_plan_payload(scenario: WriteScenario) -> dict[str, Any]:
    payload = {
        "name": scenario.name,
        "operations": list(scenario.operations),
        "steps": [
            {
                "name": step.name,
                "method": step.method,
                "path": step.path,
                "expected_statuses": list(step.expected_statuses),
                "has_json_body": step.json_body is not None,
            }
            for step in scenario.steps
        ],
        "post_api_probes": [
            {
                "name": probe.name,
                "path": probe.path,
                "expected_statuses": list(probe.expected_statuses),
                "target_ms": probe.target_ms,
            }
            for probe in scenario.post_api_probes
        ],
    }
    if scenario.checkpoints:
        payload["checkpoints"] = [
            {
                "name": checkpoint.name,
                "operations": list(checkpoint.operations),
                "steps": [
                    {
                        "name": step.name,
                        "method": step.method,
                        "path": step.path,
                        "expected_statuses": list(step.expected_statuses),
                        "has_json_body": step.json_body is not None,
                        "mutation": step.mutation,
                    }
                    for step in checkpoint.steps
                ],
                "consumers": [
                    {
                        "name": consumer.probe.name,
                        "page_key": consumer.page_key,
                        "role": consumer.role,
                        "path": consumer.probe.path,
                        "assertion_count": len(consumer.assertions),
                    }
                    for consumer in checkpoint.consumers
                ],
                "system_audit": bool(checkpoint.system_audit_path),
                "relation_state_after": checkpoint.relation_state_after,
                "fixture_row_count": len(checkpoint.fixture_row_ids),
            }
            for checkpoint in scenario.checkpoints
        ]
        payload["fixture_ownership"] = scenario.fixture_ownership
        payload["shape"] = scenario.shape
        payload["recovery_checkpoint"] = scenario.recovery_checkpoint.name if scenario.recovery_checkpoint else None
    return payload


def _resolved_step(step: WriteStep, variables: Mapping[str, Any]) -> WriteStep:
    resolved_body = _resolve_value(step.json_body, variables) if step.json_body is not None else None
    if resolved_body is not None and not isinstance(resolved_body, dict):
        raise ValueError("resolved step body must remain an object")
    return WriteStep(
        name=step.name,
        method=step.method,
        path=str(_resolve_value(step.path, variables)),
        json_body=resolved_body,
        expected_statuses=step.expected_statuses,
        mutation=step.mutation,
        captures=step.captures,
    )


def _resolve_value(value: Any, variables: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}") and value.count("${") == 1:
            key = value[2:-1]
            if key not in variables:
                raise ValueError(f"unresolved_placeholder:{key}")
            return variables[key]
        resolved = value
        for key, replacement in variables.items():
            resolved = resolved.replace(f"${{{key}}}", str(replacement))
        if "${" in resolved:
            raise ValueError("unresolved_placeholder")
        return resolved
    if isinstance(value, list):
        return [_resolve_value(item, variables) for item in value]
    if isinstance(value, tuple):
        return tuple(_resolve_value(item, variables) for item in value)
    if isinstance(value, dict):
        return {str(key): _resolve_value(item, variables) for key, item in value.items()}
    return value


def _placeholder_names(value: Any) -> set[str]:
    if isinstance(value, str):
        return {part.split("}", 1)[0] for part in value.split("${")[1:] if "}" in part and part.split("}", 1)[0]}
    if isinstance(value, (list, tuple)):
        return {name for item in value for name in _placeholder_names(item)}
    if isinstance(value, dict):
        return {name for item in value.values() for name in _placeholder_names(item)}
    return set()


def _json_pointer(payload: Any, pointer: str) -> Any:
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must start with '/'")
    current = payload
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, dict):
            if token not in current:
                raise KeyError(token)
            current = current[token]
        else:
            raise TypeError(f"cannot traverse {token!r}")
    return current


def _header(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return str(value)
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
