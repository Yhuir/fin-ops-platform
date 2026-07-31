from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence, TextIO
import sys

from .cli_reports import input_file_error_report, write_json_report

_HEALTH_READY_PAYLOAD_ERRORS = {
    "api_performance_bound_metadata_missing",
    "api_performance_endpoints_unbounded",
    "api_performance_missing",
    "health_status_not_ready",
    "html_response_for_health_ready_probe",
    "invalid_json_response",
    "json_payload_not_object",
    "non_json_response",
    "response_too_large",
    "slo_miss",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify a P2/P3 gate JSON result into the next autonomous workflow branch.",
    )
    parser.add_argument("--result", type=Path, help="Path to a gate JSON result. Defaults to stdin.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    parser.add_argument("--json", action="store_true", help="Accepted for consistency; output is always JSON.")
    return parser


def classify_gate_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "").strip()
    error = str(payload.get("error") or "").strip()
    failed_checks = _string_list(payload.get("failed_checks"))
    classification, next_actions = _classification_for(payload, status=status, error=error, failed_checks=failed_checks)
    return {
        "version": 1,
        "tool": "p2p3_gate_result_classifier",
        "status": "classified",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_tool": payload.get("tool", ""),
        "source_status": status,
        "source_error": error,
        "classification": classification,
        "next_actions": next_actions,
        "failed_checks": failed_checks,
        "blocking_condition": payload.get("blocking_condition", ""),
        "required_env": payload.get("required_env", []),
        "missing_args": payload.get("missing_args", []),
        "required_args": payload.get("required_args", []),
        "runtime_blockers": payload.get("runtime_blockers", {}),
        "runtime_blocker_count": payload.get("runtime_blocker_count", 0),
        "errors": payload.get("errors", []),
        "forbidden_without_approval": payload.get("forbidden_without_approval", []),
    }


def _classification_for(
    payload: Mapping[str, Any],
    *,
    status: str,
    error: str,
    failed_checks: Sequence[str],
) -> tuple[str, list[str]]:
    if status == "pass":
        return "passed", ["Record the passing evidence in the P2/P3 ledger and continue to the next gated item."]
    if status == "configuration_missing":
        return "environment-required", _merge_actions(
            payload.get("next_actions"),
            [
                "Provide the required environment securely, then rerun the same gate.",
                "If this is production evidence, use an approved read-only session and keep credentials out of files, logs, scripts, docs, and prompts.",
            ],
        )
    if status == "auth_missing":
        return "auth-required", ["Provide a real token/cookie through the supported environment variables or CLI args, then rerun the gate."]
    if status == "input_error" or error.startswith("scenario_") or error in {"plan_not_found", "scenario_input_error"}:
        return "input-required", ["Fix the referenced input file or scenario contract, then rerun the gate."]
    if status == "no_candidates":
        return "approved-scenario-required", ["Prepare approved, reversible test objects or scenario input before running mutating E2E evidence."]
    if status in {"approval_missing", "dry_run"}:
        return "approval-required", ["Review the dry-run output, secure approval for apply/mutating steps when needed, then rerun with explicit apply flags."]
    if _has_write_approval_missing_check(payload):
        return "approval-required", ["Review the approved scenario, provide the required write approval ticket, then rerun with explicit apply flags."]
    if any(check in failed_checks for check in ("runtime_health", "health_ready_payload")):
        return "runtime-repair-or-deploy-required", [
            "Inspect runtime blockers, release status, dirty/outbox/readiness, worker mismatch, and health-ready payload details.",
            "Do not deploy, restart, clean up database rows, or run mutating repair without an explicit plan and rollback approval.",
        ]
    source_tool = str(payload.get("tool") or "").strip()
    errors = _string_list(payload.get("errors"))
    if status == "fail" and (
        source_tool == "health_ready_payload_probe"
        or any(error in _HEALTH_READY_PAYLOAD_ERRORS or error.startswith("unexpected_status:") for error in errors)
    ):
        return "runtime-repair-or-deploy-required", [
            "Inspect runtime release, runtime blockers, readiness status, response size, API performance bounds, Nginx/API prefix routing, and worker/queue state.",
            "Deploy bounded readiness fixes or repair runtime blockers only after an explicit plan with rollback approval.",
            "Rerun health_ready_payload_probe and runtime_sync_closure_gate before claiming one-second production sync closure.",
        ]
    if "authenticated_http_slo" in failed_checks:
        return "authenticated-smoke-required", ["Inspect auth, API prefix, Nginx fallback, p95 samples, and freshness status before optimizing."]
    if any(check in failed_checks for check in ("read_model_direct_smoke", "write_operation_audit", "write_operation_e2e")):
        return "durable-evidence-required", ["Inspect sample counts, outbox status, dirty scope status, readiness status, p95/p99 latency, and scenario/apply requirements."]
    if status == "fail":
        return "gate-failed", ["Inspect the gate JSON errors and failed checks, then fix the narrowest runtime/tooling/config gap before rerunning."]
    return "unknown", ["Inspect the raw gate JSON and add classifier coverage if this status is expected in unattended P2/P3 workflow."]


def _has_write_approval_missing_check(payload: Mapping[str, Any]) -> bool:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return False
    for check in checks:
        if not isinstance(check, Mapping) or check.get("name") != "write_operation_e2e":
            continue
        check_payload = check.get("payload")
        if not isinstance(check_payload, Mapping):
            continue
        missing_args = _string_list(check_payload.get("missing_args"))
        if check_payload.get("status") == "approval_missing" or "--write-approval-ticket" in missing_args:
            return True
    return False


def _merge_actions(value: Any, fallback: Sequence[str]) -> list[str]:
    actions = [str(item) for item in value] if isinstance(value, list) else []
    return actions or list(fallback)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _load_result(path: Path | None, *, stdin: TextIO) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        text = path.read_text(encoding="utf-8") if path is not None else stdin.read()
    except OSError as exc:
        return None, input_file_error_report(
            tool="p2p3_gate_result_classifier",
            path=str(path),
            error="result_not_readable",
            message=str(exc) or exc.__class__.__name__,
        )
    try:
        parsed = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        return None, input_file_error_report(
            tool="p2p3_gate_result_classifier",
            path=str(path or "<stdin>"),
            error="invalid_json",
            message=str(exc),
        )
    if not isinstance(parsed, dict):
        return None, input_file_error_report(
            tool="p2p3_gate_result_classifier",
            path=str(path or "<stdin>"),
            error="json_payload_not_object",
            message="Gate result JSON must be an object.",
        )
    return parsed, None


def main(argv: Sequence[str] | None = None, *, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    args = build_parser().parse_args(argv)
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    payload, error_report = _load_result(args.result, stdin=stdin)
    if error_report is not None:
        write_json_report(error_report, output=args.output, stdout=stdout)
        return 2
    report = classify_gate_result(payload or {})
    write_json_report(report, output=args.output, stdout=stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
