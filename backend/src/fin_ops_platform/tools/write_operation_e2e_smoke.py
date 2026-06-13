from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Callable, Mapping, Sequence, TextIO
import os
import sys

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.tools import http_slo_probe, write_operation_slo_audit


DEFAULT_WRITE_TARGET_MS = 5_000.0
DEFAULT_HTTP_TARGET_MS = 1_000.0
DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.5
DEFAULT_LIMIT = 2_000

RequestFn = Callable[[str, str, Mapping[str, str], bytes | None, float], http_slo_probe.HttpProbeResponse]


@dataclass(frozen=True)
class WriteStep:
    name: str
    method: str
    path: str
    json_body: dict[str, Any] | None
    expected_statuses: tuple[int, ...]


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


@dataclass(frozen=True)
class WriteScenario:
    name: str
    operations: tuple[str, ...]
    steps: tuple[WriteStep, ...]
    post_api_probes: tuple[http_slo_probe.HttpProbe, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run controlled authenticated write-operation E2E SLO smoke scenarios.",
    )
    parser.add_argument("--scenario", type=Path, required=True, help="JSON scenario file. Defaults to dry-run validation.")
    parser.add_argument("--apply", action="store_true", help="Execute mutating HTTP steps. Default is dry-run only.")
    parser.add_argument("--base-url", default=os.getenv("FIN_OPS_HTTP_SLO_BASE_URL", "http://127.0.0.1:18001"))
    parser.add_argument("--api-prefix", default=os.getenv("FIN_OPS_HTTP_SLO_API_PREFIX", ""))
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--bearer-token", default=os.getenv("FIN_OPS_HTTP_SLO_BEARER_TOKEN", ""))
    parser.add_argument("--admin-token", default=os.getenv("FIN_OPS_HTTP_SLO_ADMIN_TOKEN", ""))
    parser.add_argument("--cookie", default=os.getenv("FIN_OPS_HTTP_SLO_COOKIE", ""))
    parser.add_argument("--write-target-ms", type=float, default=DEFAULT_WRITE_TARGET_MS)
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
    scenarios = load_scenarios(args.scenario, http_target_ms=max(1.0, float(args.http_target_ms)))
    headers = http_slo_probe._auth_headers(  # Reuse the existing HTTP SLO auth boundary.
        bearer_token=args.bearer_token,
        admin_token=args.admin_token,
        cookie=args.cookie,
    )
    report = run_write_operation_e2e_smoke(
        PostgresConnection(PostgresSettings.from_env()) if args.apply else None,
        scenarios=scenarios,
        apply=bool(args.apply),
        base_url=str(args.base_url),
        api_prefix=str(args.api_prefix),
        tenant_id=str(args.tenant_id or "default"),
        headers=headers,
        write_target_ms=write_target_ms,
        timeout_seconds=max(1.0, float(args.timeout_seconds)),
        poll_interval_seconds=max(0.1, float(args.poll_interval_seconds)),
        limit=max(1, int(args.limit)),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    if report["status"] == "auth_missing":
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
    for index, raw in enumerate(raw_scenarios, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"scenario #{index} must be an object.")
        name = str(raw.get("name") or f"scenario_{index}").strip() or f"scenario_{index}"
        operations = tuple(str(item or "").strip() for item in list(raw.get("operations") or []) if str(item or "").strip())
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
    write_target_ms: float = DEFAULT_WRITE_TARGET_MS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    limit: int = DEFAULT_LIMIT,
    request_fn: RequestFn | None = None,
) -> dict[str, Any]:
    auth_configured = any(str(key).lower() in {"authorization", "cookie"} for key in dict(headers))
    plan = [_scenario_plan_payload(scenario) for scenario in scenarios]
    if not apply:
        return {
            "version": 1,
            "status": "dry_run",
            "generated_at": datetime.now(UTC).isoformat(),
            "base_url": http_slo_probe._normalized_base_url(base_url),
            "api_prefix": api_prefix,
            "auth_configured": auth_configured,
            "scenario_count": len(scenarios),
            "planned_scenarios": plan,
        }
    if not auth_configured:
        return {
            "version": 1,
            "status": "auth_missing",
            "generated_at": datetime.now(UTC).isoformat(),
            "base_url": http_slo_probe._normalized_base_url(base_url),
            "api_prefix": api_prefix,
            "auth_configured": False,
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
        "scenario_count": len(scenarios),
        "failed_scenario_count": len(failed),
        "results": results,
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
    timeout_seconds: float,
    poll_interval_seconds: float,
    limit: int,
    request_fn: RequestFn,
) -> dict[str, Any]:
    started_at = _database_timestamp(connection)
    step_results = [
        _execute_step(
            step,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=headers,
            timeout_seconds=timeout_seconds,
            request_fn=request_fn,
        )
        for step in scenario.steps
    ]
    step_failed = [step for step in step_results if step.status != "pass"]
    if step_failed:
        return {
            "name": scenario.name,
            "status": "fail",
            "started_at": started_at,
            "operations": list(scenario.operations),
            "steps": [asdict(step) for step in step_results],
            "write_slo": {"status": "skipped", "reason": "write_step_failed"},
            "post_api": {"status": "skipped", "reason": "write_step_failed"},
        }
    write_slo = _wait_for_write_slo(
        connection,
        operations=scenario.operations,
        tenant_id=tenant_id,
        started_at=started_at,
        target_ms=write_target_ms,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        limit=limit,
    )
    post_api = _collect_post_api_slo(
        scenario,
        base_url=base_url,
        api_prefix=api_prefix,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    status = "pass" if write_slo["status"] == "pass" and post_api["status"] in {"pass", "skipped"} else "fail"
    return {
        "name": scenario.name,
        "status": status,
        "started_at": started_at,
        "operations": list(scenario.operations),
        "steps": [asdict(step) for step in step_results],
        "write_slo": write_slo,
        "post_api": post_api,
    }


def _execute_step(
    step: WriteStep,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    request_fn: RequestFn,
) -> WriteStepResult:
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
        ok = response.status_code in step.expected_statuses
        return WriteStepResult(
            name=step.name,
            method=step.method,
            path=step.path,
            status="pass" if ok else "fail",
            elapsed_ms=round(elapsed_ms, 3),
            status_code=response.status_code,
            response_bytes=len(response.body or b""),
            content_type=content_type,
            error=None if ok else f"unexpected_status:{response.status_code}",
        )
    except Exception as exc:
        elapsed_ms = (monotonic() - started) * 1000
        return WriteStepResult(
            name=step.name,
            method=step.method,
            path=step.path,
            status="fail",
            elapsed_ms=round(elapsed_ms, 3),
            status_code=None,
            response_bytes=0,
            content_type="",
            error=str(exc) or exc.__class__.__name__,
        )


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
) -> dict[str, Any]:
    expectations = write_operation_slo_audit.selected_expectations_for_operations(operations)
    deadline = monotonic() + max(1.0, timeout_seconds)
    last_results: list[Any] = []
    last_rows: list[dict[str, Any]] = []
    while True:
        rows = write_operation_slo_audit.recent_read_model_refresh_events_since(
            connection,
            tenant_id=tenant_id,
            started_at=started_at,
            limit=limit,
        )
        results = write_operation_slo_audit.evaluate_operation_expectations(
            rows,
            expectations=expectations,
            target_ms=target_ms,
        )
        last_results = results
        last_rows = rows
        if all(result.status == "pass" for result in results):
            return {
                "status": "pass",
                "target_ms": target_ms,
                "event_sample_count": len(rows),
                "results": [asdict(result) for result in results],
            }
        if monotonic() >= deadline:
            return {
                "status": "fail",
                "target_ms": target_ms,
                "event_sample_count": len(last_rows),
                "error": "timeout_waiting_for_write_operation_refresh_slo",
                "results": [asdict(result) for result in last_results],
            }
        sleep(max(0.1, poll_interval_seconds))


def _collect_post_api_slo(
    scenario: WriteScenario,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    if not scenario.post_api_probes:
        return {"status": "skipped", "reason": "no_post_api_probes"}
    return http_slo_probe.collect_http_slo(
        base_url=base_url,
        api_prefix=api_prefix,
        probes=list(scenario.post_api_probes),
        headers=headers,
        iterations=1,
        warmup=0,
        timeout_seconds=timeout_seconds,
        require_auth=True,
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
            return http_slo_probe.HttpProbeResponse(
                status_code=int(response.getcode()),
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(),
            )
    except HTTPError as exc:
        return http_slo_probe.HttpProbeResponse(
            status_code=int(exc.code),
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=exc.read(),
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
        steps.append(
            WriteStep(
                name=name,
                method=method,
                path=path,
                json_body=dict(json_body) if isinstance(json_body, dict) else None,
                expected_statuses=expected_statuses,
            )
        )
    return steps


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
    return {
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


def _header(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return str(value)
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
