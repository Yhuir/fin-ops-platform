#!/usr/bin/env python3
"""Compare legacy Python API responses with Axum responses for migration gates."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


SENSITIVE_HEADERS = {"authorization", "cookie", "x-oa-token"}
SENSITIVE_FIELD_HINTS = (
    "authorization",
    "cookie",
    "credential",
    "non_json_body",
    "password",
    "presign",
    "signed_url",
    "raw_content",
    "raw_file",
    "secret",
    "stack",
    "token",
    "traceback",
    "url",
)
REDACTED_VALUE = "[REDACTED]"
ID_KEYS = ("id", "row_id", "batch_id", "transaction_id", "invoice_id", "relation_id", "task_id")
MONEY_HINTS = ("amount", "balance", "tax", "price", "total", "fee")
DATE_HINTS = ("date", "time", "_at", "month")
REQUIRED_ENDPOINT_FIELDS = {
    "id",
    "method",
    "path",
    "expected_status",
    "owner",
    "risk",
    "source",
    "contract_cases",
}
REQUIRED_CONTRACT_CASE_FIELDS = {
    "query",
    "body",
    "status",
    "error_shape",
    "pagination",
    "empty_result",
    "permission_failure",
}
VALID_RISKS = {"low", "medium", "high"}
VALID_RESPONSE_MODES = {"binary", "json", "sse_first_events"}
REQUIRED_ACCEPTED_CHANGE_FIELDS = {
    "change_id",
    "legacy_status",
    "axum_status",
    "summary",
    "source_contract",
    "owner",
    "next_verification",
}
RUNTIME_VARIABLE_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")
ALLOWED_SOURCE_HINTS = (
    "postgresql",
    "read_model",
    "read model",
    "job.worker_tasks",
    "job/outbox",
    "outbox",
    "object-storage",
    "object storage",
    "static contract",
    "static legacy",
    "oa identity",
    "transactional workbench write",
)
SOURCE_CATEGORY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("postgres_facts", ("postgresql", "job.worker_tasks")),
    ("read_model", ("read_model", "read model")),
    ("job_outbox", ("job/outbox", "outbox", "job.worker_tasks")),
    ("object_storage", ("object-storage", "object storage")),
    ("static_contract", ("static contract", "static legacy")),
    ("oa_identity", ("oa identity",)),
    ("transactional_workbench_write", ("transactional workbench write",)),
)
APP_MONGO_HINTS = ("app mongo", "mongo")
NEGATIVE_SOURCE_HINTS = ("no ", "not ", "without ", "does not ", "doesn't ", "不得", "不", "未")


def validate_shadow_fixture(
    fixture_path: Path,
    *,
    endpoint_ids: set[str] | None = None,
    risks: set[str] | None = None,
) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    defaults = fixture.get("defaults") if isinstance(fixture.get("defaults"), dict) else {}
    endpoints = fixture.get("endpoints")
    if not isinstance(endpoints, list):
        return {
            "status": "NO_GO",
            "fixture": str(fixture_path),
            "endpoint_errors": [
                {
                    "endpoint_id": None,
                    "path": "$.endpoints",
                    "missing_fields": [],
                    "messages": ["fixture must contain endpoints[]"],
                }
            ],
        }

    filter_endpoint_ids = endpoint_ids
    filter_risks = risks
    if filter_endpoint_ids or filter_risks:
        selected_endpoint_entries = [
            (index, endpoint)
            for index, endpoint in enumerate(endpoints)
            if isinstance(endpoint, dict)
            and (
                not filter_endpoint_ids
                or str(endpoint.get("id") or endpoint.get("path") or "") in filter_endpoint_ids
            )
            and (not filter_risks or str(endpoint.get("risk") or "") in filter_risks)
        ]
    else:
        selected_endpoint_entries = list(enumerate(endpoints))
    if (filter_endpoint_ids or filter_risks) and not selected_endpoint_entries:
        return {
            "status": "NO_GO",
            "fixture": str(fixture_path),
            "filters": {
                "endpoint_ids": sorted(filter_endpoint_ids) if filter_endpoint_ids else [],
                "risks": sorted(filter_risks) if filter_risks else [],
            },
            "endpoint_count": 0,
            "endpoint_ids": [],
            "permission_failure_endpoint_ids": [],
            "endpoint_errors": [
                {
                    "endpoint_id": None,
                    "path": "$.endpoints",
                    "missing_fields": [],
                    "messages": ["no endpoints matched the selected filters"],
                }
            ],
        }

    endpoint_errors = []
    seen_ids = set()
    fixture_endpoint_ids = []
    permission_failure_endpoint_ids = []
    for index, endpoint in selected_endpoint_entries:
        if not isinstance(endpoint, dict):
            endpoint_errors.append(
                {
                    "endpoint_id": None,
                    "path": f"$.endpoints[{index}]",
                    "missing_fields": [],
                    "messages": ["endpoint must be an object"],
                }
            )
            continue
        endpoint_id = str(endpoint.get("id") or endpoint.get("path") or f"endpoint[{index}]")
        missing_fields = sorted(REQUIRED_ENDPOINT_FIELDS - set(endpoint))
        contract_cases = endpoint.get("contract_cases")
        if isinstance(contract_cases, dict):
            missing_fields.extend(
                f"contract_cases.{field}"
                for field in sorted(REQUIRED_CONTRACT_CASE_FIELDS - set(contract_cases))
            )
        elif "contract_cases" in endpoint:
            missing_fields.append("contract_cases.*")

        messages = []
        if endpoint_id in seen_ids:
            messages.append("endpoint id must be unique")
        seen_ids.add(endpoint_id)
        fixture_endpoint_ids.append(endpoint_id)
        if endpoint_requires_permission_failure(endpoint):
            permission_failure_endpoint_ids.append(endpoint_id)
        if str(endpoint.get("method") or "").upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            messages.append("method must be a supported HTTP method")
        if not str(endpoint.get("path") or "").startswith("/"):
            messages.append("path must start with /")
        if endpoint.get("risk") not in VALID_RISKS:
            messages.append("risk must be low, medium, or high")
        messages.extend(validate_source_contract(endpoint.get("source")))
        response_mode = str(endpoint.get("response_mode") or "json")
        if response_mode not in VALID_RESPONSE_MODES:
            messages.append("response_mode must be binary, json, or sse_first_events")
        messages.extend(validate_accepted_production_change(endpoint.get("accepted_production_change")))
        expected_status = endpoint.get("expected_status")
        if not isinstance(expected_status, int) or not 200 <= expected_status < 500:
            messages.append("expected_status must be an expected 2xx or 4xx contract status")
        if isinstance(contract_cases, dict):
            statuses = contract_cases.get("status")
            if not isinstance(statuses, list) or endpoint.get("expected_status") not in statuses:
                messages.append("contract_cases.status must include expected_status")
            error_shape = contract_cases.get("error_shape")
            if not isinstance(error_shape, dict) or "error" not in error_shape or "message" not in error_shape:
                messages.append("contract_cases.error_shape must include error and message")
            if response_mode == "sse_first_events":
                sse_events = contract_cases.get("sse_events")
                if not isinstance(sse_events, list) or not sse_events:
                    messages.append("contract_cases.sse_events must be a non-empty list for sse_first_events")
            messages.extend(validate_request_sample_contract(endpoint, contract_cases))
            messages.extend(validate_permission_failure_contract(defaults, endpoint, contract_cases))
        if missing_fields or messages:
            endpoint_errors.append(
                {
                    "endpoint_id": endpoint_id,
                    "path": f"$.endpoints[{index}]",
                    "missing_fields": missing_fields,
                    "messages": messages,
                }
            )
    return {
        "status": "GO" if not endpoint_errors else "NO_GO",
        "fixture": str(fixture_path),
        "filters": {
            "endpoint_ids": sorted(filter_endpoint_ids) if filter_endpoint_ids else [],
            "risks": sorted(filter_risks) if filter_risks else [],
        },
        "endpoint_count": len(selected_endpoint_entries),
        "endpoint_ids": fixture_endpoint_ids,
        "permission_failure_endpoint_ids": permission_failure_endpoint_ids,
        "endpoint_errors": endpoint_errors,
    }


def validate_accepted_production_change(change: Any) -> list[str]:
    if change is None:
        return []
    if not isinstance(change, dict):
        return ["accepted_production_change must be an object when present"]
    messages = []
    for field in sorted(REQUIRED_ACCEPTED_CHANGE_FIELDS - set(change)):
        messages.append(f"accepted_production_change.{field} is required")
    for field in ("change_id", "summary", "source_contract", "owner", "next_verification"):
        if field in change and not str(change.get(field) or "").strip():
            messages.append(f"accepted_production_change.{field} must be non-empty")
    for field in ("legacy_status", "axum_status"):
        value = change.get(field)
        if field in change and (not isinstance(value, int) or not 100 <= value < 600):
            messages.append(f"accepted_production_change.{field} must be an HTTP status integer")
    return messages


def endpoint_requires_permission_failure(endpoint: dict[str, Any]) -> bool:
    contract_cases = endpoint.get("contract_cases") if isinstance(endpoint.get("contract_cases"), dict) else {}
    permission_contract = str(contract_cases.get("permission_failure") or "").strip().lower()
    return bool(permission_contract and "not applicable" not in permission_contract)


def validate_permission_failure_contract(
    defaults: dict[str, Any],
    endpoint: dict[str, Any],
    contract_cases: dict[str, Any],
) -> list[str]:
    if not endpoint_requires_permission_failure(endpoint):
        return []

    messages = []
    permission_spec = merged_permission_failure_spec(defaults, endpoint)
    if not isinstance(permission_spec.get("request_headers"), dict):
        messages.append(
            "permission_failure.request_headers must be configured in defaults.permission_failure or endpoint.permission_failure"
        )

    expected_status = permission_spec.get("expected_status", 401)
    if not isinstance(expected_status, int) or not 400 <= expected_status < 500:
        messages.append("permission_failure.expected_status must be a 4xx integer")
    elif expected_status not in (contract_cases.get("status") if isinstance(contract_cases.get("status"), list) else []):
        messages.append("contract_cases.status must include permission_failure.expected_status")

    error_shape = permission_spec.get("error_shape")
    if error_shape is not None and (
        not isinstance(error_shape, dict) or "error" not in error_shape or "message" not in error_shape
    ):
        messages.append("permission_failure.error_shape must include error and message when configured")
    return messages


def merged_permission_failure_spec(defaults: dict[str, Any], endpoint: dict[str, Any]) -> dict[str, Any]:
    permission_defaults = defaults.get("permission_failure")
    permission_endpoint = endpoint.get("permission_failure")
    if isinstance(permission_endpoint, dict):
        return {**(permission_defaults if isinstance(permission_defaults, dict) else {}), **permission_endpoint}
    if isinstance(permission_defaults, dict):
        return dict(permission_defaults)
    return {}


def validate_request_sample_contract(endpoint: dict[str, Any], contract_cases: dict[str, Any]) -> list[str]:
    messages = []
    sample_query = endpoint.get("query")
    contract_query = contract_cases.get("query")
    if isinstance(sample_query, dict):
        if not isinstance(contract_query, list):
            messages.append("contract_cases.query must be a list when query sample is present")
        else:
            declared_query_keys = {str(key) for key in contract_query}
            for key in sorted(str(key) for key in sample_query):
                if key not in declared_query_keys:
                    messages.append(f"contract_cases.query must include sample query key: {key}")

    if "body" in endpoint and endpoint.get("body") is not None and contract_cases.get("body") is None:
        messages.append("contract_cases.body must describe sample body")
    return messages


def validate_source_contract(source: Any) -> list[str]:
    if not isinstance(source, str) or not source.strip():
        return ["source must name at least one allowed cutover source family"]

    normalized = normalize_source_text(source)
    categories = classify_source_categories(source)
    messages = []
    if not categories:
        messages.append("source must name at least one allowed cutover source family")
    if mentions_app_mongo_as_active_source(normalized):
        messages.append("source must not use app Mongo as an active route source")
    return messages


def classify_source_categories(source: Any) -> list[str]:
    if not isinstance(source, str):
        return []
    normalized = normalize_source_text(source)
    categories = [
        category
        for category, hints in SOURCE_CATEGORY_HINTS
        if any(hint in normalized for hint in hints)
    ]
    return sorted(set(categories))


def normalize_source_text(source: str) -> str:
    lowered = source.lower()
    return "".join(character if character.isalnum() or character == "_" else " " for character in lowered)


def mentions_app_mongo_as_active_source(normalized_source: str) -> bool:
    for hint in APP_MONGO_HINTS:
        start = 0
        while True:
            index = normalized_source.find(hint, start)
            if index < 0:
                break
            context = normalized_source[max(0, index - 48):index]
            if not any(negative in context for negative in NEGATIVE_SOURCE_HINTS):
                return True
            start = index + len(hint)
    return False


def compare_payloads(python_payload: Any, axum_payload: Any) -> dict[str, Any]:
    diffs: list[dict[str, Any]] = []
    _compare_value("$", python_payload, axum_payload, diffs)
    return {
        "diffs": diffs,
        "field_diff_count": sum(1 for item in diffs if item["kind"] == "field"),
        "sorting_diff_count": sum(1 for item in diffs if item["kind"] == "sorting"),
        "money_format_diff_count": sum(1 for item in diffs if item["kind"] == "money_format"),
        "date_format_diff_count": sum(1 for item in diffs if item["kind"] == "date_format"),
        "value_diff_count": sum(1 for item in diffs if item["kind"] == "value"),
    }


def evaluate_endpoint_gate(
    endpoint: dict[str, Any],
    python_status: int | None,
    axum_status: int | None,
    diff: dict[str, Any],
) -> dict[str, Any]:
    explained_patterns = [str(pattern) for pattern in endpoint.get("explain_diffs") or []]
    explained = []
    unexpected = []
    accepted_change = accepted_production_change_for_status(endpoint, python_status, axum_status)

    if python_status != axum_status:
        status_diff = (
            {
                "kind": "status",
                "path": "$.status",
                "python": python_status,
                "axum": axum_status,
            }
        )
        if accepted_change:
            status_diff["accepted_production_change"] = accepted_change["change_id"]
            explained.append(status_diff)
        else:
            unexpected.append(status_diff)

    expected_status = endpoint.get("expected_status")
    if expected_status is not None and (python_status != expected_status or axum_status != expected_status):
        expected_diff = {
                "kind": "expected_status",
                "path": "$.status",
                "expected": expected_status,
                "python": python_status,
                "axum": axum_status,
            }
        if accepted_change and axum_status == expected_status:
            expected_diff["accepted_production_change"] = accepted_change["change_id"]
            explained.append(expected_diff)
        else:
            unexpected.append(expected_diff)

    for item in diff.get("diffs", []):
        path = str(item.get("path", ""))
        kind_path = f"{item.get('kind')}:{path}"
        if any(
            explain_pattern_matches(path, pattern)
            or explain_pattern_matches(kind_path, pattern)
            for pattern in explained_patterns
        ):
            explained.append(item)
        else:
            unexpected.append(item)

    result = {
        "endpoint_id": endpoint.get("id") or endpoint.get("path"),
        "case": endpoint.get("case", "primary"),
        "method": endpoint.get("method", "GET"),
        "path": endpoint.get("path"),
        "isolation_group": endpoint.get("isolation_group"),
        "owner": endpoint.get("owner", "unassigned"),
        "risk": endpoint.get("risk", "unknown"),
        "source": endpoint.get("source", "unspecified"),
        "source_categories": classify_source_categories(endpoint.get("source")),
        "status": "GO" if not unexpected else "NO_GO",
        "python_status": python_status,
        "axum_status": axum_status,
        "expected_status": endpoint.get("expected_status"),
        "diff_count": len(diff.get("diffs", [])),
        "explained_diff_count": len(explained),
        "unexpected_diff_count": len(unexpected),
        "explained_diffs": explained,
        "unexpected_diffs": unexpected,
        "diff_summary": {
            key: value
            for key, value in diff.items()
            if key.endswith("_count")
        },
    }
    if accepted_change:
        result["accepted_production_change"] = accepted_change
    return result


def explain_pattern_matches(value: str, pattern: str) -> bool:
    if fnmatch.fnmatch(value, pattern):
        return True
    if "[*]" not in pattern:
        return False
    regex = re.escape(pattern)
    regex = regex.replace(r"\[\*\]", r"\[[^\]]+\]")
    regex = regex.replace(r"\*", ".*")
    return re.fullmatch(regex, value) is not None


def accepted_production_change_for_status(
    endpoint: dict[str, Any],
    python_status: int | None,
    axum_status: int | None,
) -> dict[str, Any] | None:
    change = endpoint.get("accepted_production_change")
    if not isinstance(change, dict):
        return None
    if change.get("legacy_status") != python_status or change.get("axum_status") != axum_status:
        return None
    return {
        "change_id": str(change["change_id"]),
        "legacy_status": int(change["legacy_status"]),
        "axum_status": int(change["axum_status"]),
        "summary": str(change["summary"]),
        "source_contract": str(change["source_contract"]),
        "owner": str(change["owner"]),
        "next_verification": str(change["next_verification"]),
    }


def run_shadow_validation(
    *,
    python_base_url: str,
    axum_base_url: str,
    fixture_path: Path,
    output_dir: Path,
    report_date: str | None = None,
    timeout: float = 10.0,
    include_permission_failures: bool = False,
    endpoint_ids: set[str] | None = None,
    risks: set[str] | None = None,
    before_group_hook: str | None = None,
) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture_validation = validate_shadow_fixture(fixture_path)
    endpoints = fixture.get("endpoints")
    if not isinstance(endpoints, list):
        endpoints = []

    results = []
    defaults = fixture.get("defaults") if isinstance(fixture.get("defaults"), dict) else {}
    if fixture_validation["status"] != "GO":
        results.extend(fixture_validation_results(fixture_validation))
    else:
        selected_endpoints = filter_endpoints(endpoints, endpoint_ids=endpoint_ids, risks=risks)
        isolation_runtime = ShadowIsolationRuntime(before_group_hook=before_group_hook)
        for endpoint in selected_endpoints:
            isolation_info = isolation_runtime.prepare_endpoint(endpoint)
            if isolation_info.get("status") == "NO_GO":
                results.append(isolation_failure_result(endpoint, isolation_info))
                continue
            for case_endpoint, request_spec in endpoint_shadow_cases(
                defaults,
                endpoint,
                include_permission_failures=include_permission_failures,
            ):
                case_endpoint = {**case_endpoint, **isolation_info}
                unresolved_variables = unresolved_runtime_variables(request_spec)
                if unresolved_variables:
                    results.append(unresolved_runtime_variable_result(case_endpoint, unresolved_variables))
                    continue
                python_response, axum_response = request_endpoint_pair(
                    python_base_url,
                    axum_base_url,
                    request_spec,
                    timeout,
                )
                diff = compare_payloads(python_response.get("json"), axum_response.get("json"))
                diff["diffs"].extend(response_contract_diffs(case_endpoint, python_response, axum_response))
                gate = evaluate_endpoint_gate(
                    case_endpoint,
                    python_response.get("status"),
                    axum_response.get("status"),
                    diff,
                )
                gate["python_error"] = python_response.get("error")
                gate["axum_error"] = axum_response.get("error")
                add_isolation_result_fields(gate, isolation_info)
                results.append(gate)

        if should_require_permission_failure_coverage(
            fixture_validation,
            include_permission_failures=include_permission_failures,
            endpoint_ids=endpoint_ids,
            risks=risks,
        ):
            results.extend(missing_permission_failure_coverage_results(fixture_validation, results))

    if not results:
        results.append(
            {
                "endpoint_id": None,
                "case": "selection",
                "method": None,
                "path": None,
                "owner": "unassigned",
                "risk": "unknown",
                "source": "selection filter",
                "source_categories": [],
                "status": "NO_GO",
                "python_status": None,
                "axum_status": None,
                "diff_count": 0,
                "explained_diff_count": 0,
                "unexpected_diff_count": 1,
                "explained_diffs": [],
                "unexpected_diffs": [
                    {
                        "kind": "selection",
                        "path": "$.endpoints",
                        "message": "no endpoints matched the selected filters",
                    }
                ],
                "diff_summary": {},
                "python_error": None,
                "axum_error": None,
            }
        )

    overall_status = "GO" if all(result["status"] == "GO" for result in results) else "NO_GO"
    generated_date = report_date or date.today().strftime("%Y%m%d")
    accepted_changes = accepted_production_changes_from_results(results)
    report = {
        "report": f"api-shadow-validation-report-{generated_date}",
        "status": overall_status,
        "python_base_url": python_base_url,
        "axum_base_url": axum_base_url,
        "fixture": str(fixture_path),
        "fixture_validation": fixture_validation,
        "filters": {
            "endpoint_ids": sorted(endpoint_ids) if endpoint_ids else [],
            "risks": sorted(risks) if risks else [],
        },
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "redaction": {
            "sensitive_value": REDACTED_VALUE,
            "field_hints": list(SENSITIVE_FIELD_HINTS),
        },
        "summary": {
            "total": len(results),
            "go": sum(1 for result in results if result["status"] == "GO"),
            "no_go": sum(1 for result in results if result["status"] == "NO_GO"),
            "unexpected_diff_count": sum(result["unexpected_diff_count"] for result in results),
            "explained_diff_count": sum(result["explained_diff_count"] for result in results),
            "accepted_production_change_count": len(accepted_changes),
            "permission_failure_cases": sum(1 for result in results if result.get("case") == "permission_failure"),
                "fixture_error_count": len(fixture_validation.get("endpoint_errors") or []),
                "permission_failure_required_count": len(
                    fixture_validation.get("permission_failure_endpoint_ids") or []
                ),
                "permission_failure_missing_count": sum(
                    1 for result in results if result.get("case") == "permission_failure_coverage"
                ),
        },
        "accepted_production_changes": accepted_changes,
        "side_effect_probe_results": [],
        "seed_generation": {
            "before_group_hook_configured": bool(before_group_hook),
            "groups_reseeded": isolation_runtime.groups_reseeded if fixture_validation["status"] == "GO" else [],
        },
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"api-shadow-validation-report-{generated_date}.json"
    md_path = output_dir / f"api-shadow-validation-report-{generated_date}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["markdown_path"] = str(md_path)
    return report


class ShadowIsolationRuntime:
    def __init__(self, *, before_group_hook: str | None) -> None:
        self.before_group_hook = before_group_hook
        self.seeded_groups: dict[str, dict[str, Any]] = {}
        self.groups_reseeded: list[dict[str, Any]] = []

    def prepare_endpoint(self, endpoint: dict[str, Any]) -> dict[str, Any]:
        group = str(endpoint.get("isolation_group") or "default")
        requires_reseed = bool(endpoint.get("requires_reseed")) or is_mutating_endpoint(endpoint) or bool(self.before_group_hook)
        info: dict[str, Any] = {
            "isolation_group": group,
            "seed_applied_at": None,
            "legacy_seed_applied": False,
            "postgres_cleanup_applied": False,
        }
        if not requires_reseed:
            return info
        if group in self.seeded_groups:
            return {**info, **self.seeded_groups[group]}
        if not self.before_group_hook:
            return info

        applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        env = {
            **os.environ,
            "SHADOW_ISOLATION_GROUP": group,
            "SHADOW_ENDPOINT_ID": str(endpoint.get("id") or endpoint.get("path") or ""),
        }
        completed = subprocess.run(
            self.before_group_hook,
            shell=True,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        hook_report = parse_hook_report(completed.stdout)
        hook_postgres_cleanup = hook_report.get("postgres_cleanup_applied")
        hook_legacy_seed = hook_report.get("legacy_seed_applied")
        postgres_cleanup_applied = bool(hook_postgres_cleanup) if hook_postgres_cleanup is not None else completed.returncode == 0
        legacy_seed_applied = bool(hook_legacy_seed) if hook_legacy_seed is not None else completed.returncode == 0
        if completed.returncode != 0:
            return {
                **info,
                "status": "NO_GO",
                "seed_applied_at": applied_at,
                "legacy_seed_applied": legacy_seed_applied,
                "postgres_cleanup_applied": postgres_cleanup_applied,
                "hook_report": hook_report,
                "hook_returncode": completed.returncode,
                "hook_stdout": redact_sensitive_fields(completed.stdout.strip()),
                "hook_stderr": redact_sensitive_fields(completed.stderr.strip()),
            }
        if hook_report.get("status") == "NO_GO" or hook_report.get("restart_required") is True:
            return {
                **info,
                "status": "NO_GO",
                "seed_applied_at": applied_at,
                "legacy_seed_applied": legacy_seed_applied,
                "postgres_cleanup_applied": postgres_cleanup_applied,
                "hook_report": hook_report,
                "hook_returncode": completed.returncode,
                "hook_stdout": redact_sensitive_fields(completed.stdout.strip()),
                "hook_stderr": redact_sensitive_fields(completed.stderr.strip()),
            }
        seed_info = {
            "seed_applied_at": applied_at,
            "legacy_seed_applied": legacy_seed_applied,
            "postgres_cleanup_applied": postgres_cleanup_applied,
            "hook_report": hook_report,
        }
        self.seeded_groups[group] = seed_info
        self.groups_reseeded.append({"isolation_group": group, "seed_applied_at": applied_at})
        return {**info, **seed_info}


def parse_hook_report(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return redact_sensitive_fields(parsed)
    return {}


def is_mutating_endpoint(endpoint: dict[str, Any]) -> bool:
    return str(endpoint.get("method") or "GET").upper() in {"POST", "PUT", "PATCH", "DELETE"}


def add_isolation_result_fields(result: dict[str, Any], isolation_info: dict[str, Any]) -> None:
    result["isolation_group"] = isolation_info.get("isolation_group")
    result["seed_applied_at"] = isolation_info.get("seed_applied_at")
    result["legacy_seed_applied"] = bool(isolation_info.get("legacy_seed_applied"))
    result["postgres_cleanup_applied"] = bool(isolation_info.get("postgres_cleanup_applied"))


def isolation_failure_result(endpoint: dict[str, Any], isolation_info: dict[str, Any]) -> dict[str, Any]:
    hook_report = isolation_info.get("hook_report") if isinstance(isolation_info.get("hook_report"), dict) else {}
    message = "before-group seed hook failed"
    if hook_report.get("restart_required"):
        message = "before-group seed hook reported restart_required; request was not sent"
    elif hook_report.get("message"):
        message = str(hook_report.get("message"))
    return {
        "endpoint_id": endpoint.get("id") or endpoint.get("path"),
        "case": "seed_isolation",
        "method": endpoint.get("method", "GET"),
        "path": endpoint.get("path"),
        "isolation_group": isolation_info.get("isolation_group"),
        "seed_applied_at": isolation_info.get("seed_applied_at"),
        "legacy_seed_applied": bool(isolation_info.get("legacy_seed_applied")),
        "postgres_cleanup_applied": bool(isolation_info.get("postgres_cleanup_applied")),
        "hook_report": hook_report,
        "owner": endpoint.get("owner", "unassigned"),
        "risk": endpoint.get("risk", "unknown"),
        "source": endpoint.get("source", "runtime seed isolation"),
        "source_categories": classify_source_categories(endpoint.get("source")),
        "status": "NO_GO",
        "python_status": None,
        "axum_status": None,
        "expected_status": endpoint.get("expected_status"),
        "diff_count": 0,
        "explained_diff_count": 0,
        "unexpected_diff_count": 1,
        "explained_diffs": [],
        "unexpected_diffs": [
            {
                "kind": "seed_isolation",
                "path": "$.isolation_group",
                "message": message,
                "returncode": isolation_info.get("hook_returncode"),
                "stdout": isolation_info.get("hook_stdout"),
                "stderr": isolation_info.get("hook_stderr"),
            }
        ],
        "diff_summary": {"seed_isolation_failure_count": 1},
        "python_error": "request_not_sent_seed_isolation_failed",
        "axum_error": "request_not_sent_seed_isolation_failed",
    }


def accepted_production_changes_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changes = []
    seen = set()
    for result in results:
        change = result.get("accepted_production_change")
        if not isinstance(change, dict):
            continue
        key = (result.get("endpoint_id"), result.get("case"), change.get("change_id"))
        if key in seen:
            continue
        seen.add(key)
        changes.append(
            {
                "endpoint_id": result.get("endpoint_id"),
                "case": result.get("case", "primary"),
                **change,
            }
        )
    return changes


def should_require_permission_failure_coverage(
    fixture_validation: dict[str, Any],
    *,
    include_permission_failures: bool,
    endpoint_ids: set[str] | None,
    risks: set[str] | None,
) -> bool:
    if fixture_validation.get("status") != "GO":
        return False
    if include_permission_failures:
        return False
    if endpoint_ids or risks:
        return False
    return bool(fixture_validation.get("permission_failure_endpoint_ids"))


def missing_permission_failure_coverage_results(
    fixture_validation: dict[str, Any],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    already_run = {
        str(result.get("endpoint_id"))
        for result in results
        if result.get("case") == "permission_failure"
    }
    missing = []
    for endpoint_id in fixture_validation.get("permission_failure_endpoint_ids") or []:
        case_id = f"{endpoint_id}#permission_failure"
        if case_id in already_run:
            continue
        missing.append(
            {
                "endpoint_id": case_id,
                "case": "permission_failure_coverage",
                "method": None,
                "path": None,
                "owner": "unassigned",
                "risk": "unknown",
                "source": "fixture permission_failure coverage static contract",
                "source_categories": ["static_contract"],
                "status": "NO_GO",
                "python_status": None,
                "axum_status": None,
                "diff_count": 0,
                "explained_diff_count": 0,
                "unexpected_diff_count": 1,
                "explained_diffs": [],
                "unexpected_diffs": [
                    {
                        "kind": "permission_failure_coverage",
                        "path": "$.fixture_validation.permission_failure_endpoint_ids",
                        "message": "required permission-failure case was not run; rerun with --include-permission-failures",
                    }
                ],
                "diff_summary": {},
                "python_error": None,
                "axum_error": None,
            }
        )
    return missing


def unresolved_runtime_variable_result(
    endpoint: dict[str, Any],
    variables: list[str],
) -> dict[str, Any]:
    return {
        "endpoint_id": endpoint.get("id") or endpoint.get("path"),
        "case": endpoint.get("case", "primary"),
        "method": endpoint.get("method", "GET"),
        "path": endpoint.get("path"),
        "isolation_group": endpoint.get("isolation_group"),
        "seed_applied_at": endpoint.get("seed_applied_at"),
        "legacy_seed_applied": bool(endpoint.get("legacy_seed_applied")),
        "postgres_cleanup_applied": bool(endpoint.get("postgres_cleanup_applied")),
        "owner": endpoint.get("owner", "unassigned"),
        "risk": endpoint.get("risk", "unknown"),
        "source": endpoint.get("source", "runtime variable preflight"),
        "source_categories": classify_source_categories(endpoint.get("source")),
        "status": "NO_GO",
        "python_status": None,
        "axum_status": None,
        "expected_status": endpoint.get("expected_status"),
        "diff_count": 0,
        "explained_diff_count": 0,
        "unexpected_diff_count": 1,
        "explained_diffs": [],
        "unexpected_diffs": [
            {
                "kind": "runtime_variable",
                "path": "$.request",
                "message": "runtime shadow request contains unresolved environment variables",
                "variables": variables,
            }
        ],
        "diff_summary": {"runtime_variable_diff_count": 1},
        "python_error": "request_not_sent_unresolved_runtime_variables",
        "axum_error": "request_not_sent_unresolved_runtime_variables",
    }


def unresolved_runtime_variables(value: Any) -> list[str]:
    variables: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, str):
            expanded = os.path.expandvars(item)
            variables.update(RUNTIME_VARIABLE_PATTERN.findall(expanded))
            return
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if isinstance(item, dict):
            for child in item.values():
                visit(child)

    visit(value)
    return sorted(variables)


def response_contract_diffs(
    endpoint: dict[str, Any],
    python_response: dict[str, Any],
    axum_response: dict[str, Any],
) -> list[dict[str, Any]]:
    contract_cases = endpoint.get("contract_cases") if isinstance(endpoint.get("contract_cases"), dict) else {}
    error_shape = contract_cases.get("error_shape") if isinstance(contract_cases.get("error_shape"), dict) else None
    if not error_shape:
        return []

    diffs = []
    for side, response in (("python", python_response), ("axum", axum_response)):
        status = response.get("status")
        if not isinstance(status, int) or status < 400:
            continue
        message = error_shape_violation(response.get("json"), error_shape)
        if message:
            diffs.append(
                {
                    "kind": "error_shape",
                    "path": f"$.error_shape.{side}",
                    "message": message,
                }
            )
    return diffs


def error_shape_violation(payload: Any, error_shape: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return "response body is not a JSON object"

    for key, expected in error_shape.items():
        if key not in payload:
            return f"missing $.{key}"
        actual = payload[key]
        if expected == "string":
            if not isinstance(actual, str):
                return f"$.{key} expected string"
        elif expected == "number":
            if not isinstance(actual, (int, float)) or isinstance(actual, bool):
                return f"$.{key} expected number"
        elif expected == "boolean":
            if not isinstance(actual, bool):
                return f"$.{key} expected boolean"
        elif expected is not None and actual != expected:
            return f"$.{key} expected {expected!r}"
    return None


def fixture_validation_results(fixture_validation: dict[str, Any]) -> list[dict[str, Any]]:
    errors = fixture_validation.get("endpoint_errors")
    if not isinstance(errors, list) or not errors:
        errors = [
            {
                "endpoint_id": None,
                "path": "$",
                "missing_fields": [],
                "messages": ["fixture validation failed"],
            }
        ]

    results = []
    for error in errors:
        missing_fields = error.get("missing_fields") if isinstance(error, dict) else []
        messages = error.get("messages") if isinstance(error, dict) else []
        if not isinstance(missing_fields, list):
            missing_fields = []
        if not isinstance(messages, list):
            messages = []
        details = [f"missing_fields={', '.join(map(str, missing_fields))}"] if missing_fields else []
        details.extend(str(message) for message in messages)
        results.append(
            {
                "endpoint_id": error.get("endpoint_id") if isinstance(error, dict) else None,
                "case": "fixture_validation",
                "method": None,
                "path": error.get("path") if isinstance(error, dict) else "$",
                "owner": "contract",
                "risk": "high",
                "source": "fixture validation",
                "source_categories": ["static_contract"],
                "status": "NO_GO",
                "python_status": None,
                "axum_status": None,
                "diff_count": 0,
                "explained_diff_count": 0,
                "unexpected_diff_count": 1,
                "explained_diffs": [],
                "unexpected_diffs": [
                    {
                        "kind": "fixture_validation",
                        "path": error.get("path", "$") if isinstance(error, dict) else "$",
                        "message": "; ".join(details) if details else "fixture validation failed",
                    }
                ],
                "diff_summary": {},
                "python_error": None,
                "axum_error": None,
            }
        )
    return results


def request_endpoint(base_url: str, endpoint: dict[str, Any], timeout: float) -> dict[str, Any]:
    method = str(endpoint.get("method") or "GET").upper()
    path = expand_env(str(endpoint.get("path") or "/"))
    query = expand_env_value(endpoint.get("query")) if isinstance(endpoint.get("query"), dict) else {}
    headers = {
        str(key): expand_env(str(value))
        for key, value in (endpoint.get("headers") or {}).items()
    }
    body = expand_env_value(endpoint.get("body"))
    raw_body = None
    if body is not None:
        raw_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    url = build_url(base_url, path, query)
    request = Request(url, data=raw_body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local/staging validation tool
            content_type = response.headers.get("Content-Type", "")
            if str(endpoint.get("response_mode") or "json") == "sse_first_events":
                return sse_response_payload(
                    response.status,
                    response,
                    content_type,
                    expected_events=expected_sse_events(endpoint),
                )
            raw = response.read()
            if str(endpoint.get("response_mode") or "json") == "binary":
                return binary_response_payload(response.status, raw, response.headers)
            return response_payload(response.status, raw, content_type)
    except HTTPError as error:
        return response_payload(error.code, error.read(), error.headers.get("Content-Type", ""))
    except URLError as error:
        return {"status": None, "json": None, "error": str(error)}


def request_endpoint_pair(
    python_base_url: str,
    axum_base_url: str,
    endpoint: dict[str, Any],
    timeout: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        python_future = executor.submit(request_endpoint, python_base_url, endpoint, timeout)
        axum_future = executor.submit(request_endpoint, axum_base_url, endpoint, timeout)
        return python_future.result(), axum_future.result()


def filter_endpoints(
    endpoints: list[Any],
    *,
    endpoint_ids: set[str] | None,
    risks: set[str] | None,
) -> list[dict[str, Any]]:
    selected = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        endpoint_id = str(endpoint.get("id") or endpoint.get("path") or "")
        risk = str(endpoint.get("risk") or "")
        if endpoint_ids and endpoint_id not in endpoint_ids:
            continue
        if risks and risk not in risks:
            continue
        selected.append(endpoint)
    return selected


def endpoint_with_defaults(defaults: dict[str, Any], endpoint: dict[str, Any]) -> dict[str, Any]:
    merged = dict(endpoint)
    default_headers = defaults.get("headers") if isinstance(defaults.get("headers"), dict) else {}
    endpoint_headers = endpoint.get("headers") if isinstance(endpoint.get("headers"), dict) else {}
    if default_headers or endpoint_headers:
        merged["headers"] = {**default_headers, **endpoint_headers}
    return merged


def endpoint_shadow_cases(
    defaults: dict[str, Any],
    endpoint: dict[str, Any],
    *,
    include_permission_failures: bool,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    primary_endpoint = dict(endpoint)
    primary_endpoint["case"] = "primary"
    cases = [(primary_endpoint, endpoint_with_defaults(defaults, endpoint))]
    permission_case = build_permission_failure_case(defaults, endpoint) if include_permission_failures else None
    if permission_case is not None:
        cases.append(permission_case)
    return cases


def build_permission_failure_case(
    defaults: dict[str, Any],
    endpoint: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if not endpoint_requires_permission_failure(endpoint):
        return None

    contract_cases = endpoint.get("contract_cases") if isinstance(endpoint.get("contract_cases"), dict) else {}
    permission_spec = merged_permission_failure_spec(defaults, endpoint)
    if not permission_spec:
        return None

    request_spec = endpoint_with_defaults(defaults, endpoint)
    if "request_headers" in permission_spec:
        request_spec["headers"] = permission_spec["request_headers"]
    if isinstance(permission_spec.get("query"), dict):
        request_spec["query"] = permission_spec["query"]
    if "body" in permission_spec:
        request_spec["body"] = permission_spec["body"]

    expected_status = permission_spec.get("expected_status")
    if not isinstance(expected_status, int):
        expected_status = 401
    case_endpoint = dict(endpoint)
    case_endpoint["id"] = f"{endpoint.get('id') or endpoint.get('path')}#permission_failure"
    case_endpoint["case"] = "permission_failure"
    case_endpoint["expected_status"] = expected_status
    case_endpoint["explain_diffs"] = permission_spec.get("explain_diffs", endpoint.get("explain_diffs", []))
    if isinstance(permission_spec.get("error_shape"), dict):
        contract_cases = dict(case_endpoint.get("contract_cases") or {})
        contract_cases["error_shape"] = permission_spec["error_shape"]
        status_cases = contract_cases.get("status")
        if isinstance(status_cases, list) and expected_status not in status_cases:
            contract_cases["status"] = [*status_cases, expected_status]
        case_endpoint["contract_cases"] = contract_cases
    return case_endpoint, request_spec


def expand_env(value: str) -> str:
    return os.path.expandvars(value)


def expand_env_value(value: Any) -> Any:
    if isinstance(value, str):
        return expand_env(value)
    if isinstance(value, list):
        return [expand_env_value(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env_value(item) for key, item in value.items()}
    return value


def build_url(base_url: str, path: str, query: dict[str, Any]) -> str:
    base = base_url.rstrip("/") + "/"
    url = urljoin(base, path.lstrip("/"))
    clean_query = {key: value for key, value in query.items() if value is not None}
    if clean_query:
        url = f"{url}?{urlencode(clean_query, doseq=True)}"
    return url


def response_payload(status: int, raw: bytes, content_type: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        parsed: Any = None
    else:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"_non_json_body": text[:1000], "_content_type": content_type}
    return {"status": status, "json": parsed, "error": None}


def binary_response_payload(status: int, raw: bytes, headers: Any) -> dict[str, Any]:
    content_type = headers.get("Content-Type", "")
    content_disposition = headers.get("Content-Disposition", "")
    payload = {
        "_binary": True,
        "_content_type": content_type,
        "_content_disposition": content_disposition,
        "_magic": raw[:4].hex(),
    }
    if raw.startswith(b"PK"):
        payload["_container"] = "zip"
    return {"status": status, "json": payload, "error": None}


def expected_sse_events(endpoint: dict[str, Any]) -> list[str]:
    contract_cases = endpoint.get("contract_cases") if isinstance(endpoint.get("contract_cases"), dict) else {}
    sse_events = contract_cases.get("sse_events")
    if isinstance(sse_events, list) and sse_events:
        return [str(event) for event in sse_events]
    return ["message"]


def sse_response_payload(
    status: int,
    response: Any,
    content_type: str,
    *,
    expected_events: list[str],
) -> dict[str, Any]:
    events = read_sse_events(response, expected_events)
    return {
        "status": status,
        "json": {
            "_content_type": content_type,
            "_sse_events": events,
        },
        "error": None,
    }


def read_sse_events(response: Any, expected_events: list[str]) -> list[dict[str, Any]]:
    target_count = max(1, len(expected_events))
    events = []
    current_event = "message"
    data_lines: list[str] = []
    while len(events) < target_count:
        raw_line = response.readline()
        if raw_line == b"":
            break
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            if data_lines:
                events.append(parsed_sse_event(current_event, data_lines))
            current_event = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            current_event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())
    if data_lines and len(events) < target_count:
        events.append(parsed_sse_event(current_event, data_lines))
    return events


def parsed_sse_event(event_name: str, data_lines: list[str]) -> dict[str, Any]:
    raw_data = "\n".join(data_lines)
    try:
        parsed_data: Any = json.loads(raw_data)
    except json.JSONDecodeError:
        parsed_data = raw_data
    return {"event": event_name, "data": parsed_data}


def _compare_value(path: str, left: Any, right: Any, diffs: list[dict[str, Any]]) -> None:
    if isinstance(left, dict) and isinstance(right, dict):
        left_keys = set(left)
        right_keys = set(right)
        for key in sorted(left_keys - right_keys):
            item_path = f"{path}.{key}"
            diffs.append(
                {
                    "kind": "field",
                    "path": item_path,
                    "python": redact_diff_value(item_path, left[key]),
                    "axum": None,
                }
            )
        for key in sorted(right_keys - left_keys):
            item_path = f"{path}.{key}"
            diffs.append(
                {
                    "kind": "field",
                    "path": item_path,
                    "python": None,
                    "axum": redact_diff_value(item_path, right[key]),
                }
            )
        for key in sorted(left_keys & right_keys):
            _compare_value(f"{path}.{key}", left[key], right[key], diffs)
        return

    if isinstance(left, list) and isinstance(right, list):
        _compare_list(path, left, right, diffs)
        return

    if left == right:
        return
    if is_money_path(path) and decimal_equal(left, right):
        diffs.append(
            {
                "kind": "money_format",
                "path": path,
                "python": redact_diff_value(path, left),
                "axum": redact_diff_value(path, right),
            }
        )
        return
    if is_date_path(path) and looks_date_like(left) and looks_date_like(right):
        diffs.append(
            {
                "kind": "date_format",
                "path": path,
                "python": redact_diff_value(path, left),
                "axum": redact_diff_value(path, right),
            }
        )
        return
    diffs.append(
        {
            "kind": "value",
            "path": path,
            "python": redact_diff_value(path, left),
            "axum": redact_diff_value(path, right),
        }
    )


def _compare_list(path: str, left: list[Any], right: list[Any], diffs: list[dict[str, Any]]) -> None:
    key = common_id_key(left, right)
    if key:
        left_ids = [str(item.get(key)) for item in left if isinstance(item, dict)]
        right_ids = [str(item.get(key)) for item in right if isinstance(item, dict)]
        if left_ids != right_ids and sorted(left_ids) == sorted(right_ids):
            diffs.append({"kind": "sorting", "path": path, "python_order": left_ids, "axum_order": right_ids, "key": key})
            left_by_id = {str(item.get(key)): item for item in left if isinstance(item, dict)}
            right_by_id = {str(item.get(key)): item for item in right if isinstance(item, dict)}
            for item_id in sorted(set(left_by_id) & set(right_by_id)):
                _compare_value(f"{path}[{key}={item_id}]", left_by_id[item_id], right_by_id[item_id], diffs)
            return

    if len(left) != len(right):
        diffs.append({"kind": "field", "path": f"{path}.length", "python": len(left), "axum": len(right)})
    for index, (left_item, right_item) in enumerate(zip(left, right)):
        _compare_value(f"{path}[{index}]", left_item, right_item, diffs)


def common_id_key(left: list[Any], right: list[Any]) -> str | None:
    if not left or not right:
        return None
    if not all(isinstance(item, dict) for item in [*left, *right]):
        return None
    for key in ID_KEYS:
        left_values = [item.get(key) for item in left]
        right_values = [item.get(key) for item in right]
        if all(value is not None for value in left_values + right_values) and sorted(map(str, left_values)) == sorted(map(str, right_values)):
            return key
    return None


def redact_diff_value(path: str, value: Any) -> Any:
    if is_sensitive_path(path):
        return REDACTED_VALUE
    return redact_sensitive_fields(value)


def redact_sensitive_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED_VALUE if is_sensitive_field(str(key)) else redact_sensitive_fields(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_fields(item) for item in value]
    return value


def is_sensitive_path(path: str) -> bool:
    normalized = path.lower().replace("[", ".").replace("]", ".").replace("=", ".")
    return any(hint in normalized for hint in SENSITIVE_FIELD_HINTS)


def is_sensitive_field(field: str) -> bool:
    lowered = field.lower()
    return any(hint in lowered for hint in SENSITIVE_FIELD_HINTS)


def is_money_path(path: str) -> bool:
    lowered = path.lower()
    return any(hint in lowered for hint in MONEY_HINTS)


def is_date_path(path: str) -> bool:
    lowered = path.lower()
    return any(hint in lowered for hint in DATE_HINTS)


def decimal_equal(left: Any, right: Any) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError):
        return False


def looks_date_like(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) < 7:
        return False
    return bool(
        _parse_date(text)
        or _parse_date(text.replace("Z", "+00:00"))
        or _parse_date(text[:10])
    )


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['report']}",
        "",
        f"- Gate: **{report['status']}**",
        f"- Python base URL: `{report['python_base_url']}`",
        f"- Axum base URL: `{report['axum_base_url']}`",
        f"- Fixture: `{report['fixture']}`",
        f"- Endpoint filters: `{', '.join(report.get('filters', {}).get('endpoint_ids', [])) or 'all'}`",
        f"- Risk filters: `{', '.join(report.get('filters', {}).get('risks', [])) or 'all'}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Sensitive diff values: `{report.get('redaction', {}).get('sensitive_value', REDACTED_VALUE)}`",
        "",
        "## Summary",
        "",
        f"- Total: {report['summary']['total']}",
        f"- GO: {report['summary']['go']}",
        f"- NO_GO: {report['summary']['no_go']}",
        f"- Unexpected diffs: {report['summary']['unexpected_diff_count']}",
        f"- Accepted production changes: {report['summary'].get('accepted_production_change_count', 0)}",
        f"- Permission failure cases: {report['summary'].get('permission_failure_cases', 0)}",
        f"- Fixture validation errors: {report['summary'].get('fixture_error_count', 0)}",
        "",
        "## Endpoints",
        "",
        "| Endpoint | Method | Risk | Owner | Source | Gate | Unexpected diffs |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in report["results"]:
        lines.append(
            "| {endpoint} | {method} | {risk} | {owner} | {source} | {status} | {diffs} |".format(
                endpoint=markdown_cell(result.get("path") or result.get("endpoint_id") or ""),
                method=markdown_cell(result.get("method") or ""),
                risk=markdown_cell(result.get("risk") or ""),
                owner=markdown_cell(result.get("owner") or ""),
                source=markdown_cell(result.get("source") or "unspecified"),
                status=markdown_cell(result.get("status") or ""),
                diffs=result["unexpected_diff_count"],
            )
        )
    append_markdown_accepted_changes(lines, report.get("accepted_production_changes") or [])
    append_markdown_diff_section(lines, "Diff Details", report["results"], "unexpected_diffs")
    append_markdown_diff_section(lines, "Explained Diffs", report["results"], "explained_diffs")
    lines.append("")
    lines.append("Any endpoint with an unexplained status, field, ordering, money-format, date-format, or value diff keeps the overall gate at `NO_GO`.")
    return "\n".join(lines) + "\n"


def append_markdown_accepted_changes(lines: list[str], changes: list[dict[str, Any]]) -> None:
    if not changes:
        return
    lines.extend(
        [
            "",
            "## Accepted Production Changes",
            "",
            "| Endpoint | Change | Legacy | Axum | Source Contract | Owner | Next Verification |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for change in changes:
        lines.append(
            "| {endpoint} | {change_id} | {legacy_status} | {axum_status} | {source_contract} | {owner} | {next_verification} |".format(
                endpoint=markdown_cell(change.get("endpoint_id") or ""),
                change_id=markdown_cell(change.get("change_id") or ""),
                legacy_status=markdown_cell(change.get("legacy_status")),
                axum_status=markdown_cell(change.get("axum_status")),
                source_contract=markdown_cell(change.get("source_contract") or ""),
                owner=markdown_cell(change.get("owner") or ""),
                next_verification=markdown_cell(change.get("next_verification") or ""),
            )
        )


def append_markdown_diff_section(
    lines: list[str],
    title: str,
    results: list[dict[str, Any]],
    field: str,
) -> None:
    rows = []
    for result in results:
        for diff in result.get(field) or []:
            rows.append((result, diff))
    if not rows:
        return
    lines.extend(
        [
            "",
            f"## {title}",
            "",
            "| Endpoint | Case | Kind | Path | Python | Axum |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for result, diff in rows:
        lines.append(
            "| {endpoint} | {case} | `{kind}` | `{path}` | `{python}` | `{axum}` |".format(
                endpoint=markdown_cell(result.get("path") or result.get("endpoint_id") or ""),
                case=markdown_cell(result.get("case") or "primary"),
                kind=markdown_cell(diff.get("kind") or ""),
                path=markdown_cell(diff.get("path") or ""),
                python=markdown_cell(diff_side_value(diff, "python")),
                axum=markdown_cell(diff_side_value(diff, "axum")),
            )
        )


def diff_side_value(diff: dict[str, Any], side: str) -> Any:
    if side in diff:
        return diff.get(side)
    order_key = f"{side}_order"
    if order_key in diff:
        return diff.get(order_key)
    if side == "python":
        return diff.get("expected")
    return diff.get("message", "")


def markdown_cell(value: Any) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = text.replace("\n", "\\n").replace("|", "\\|").replace("`", "\\`")
    if len(text) > 160:
        text = text[:157] + "..."
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-base-url")
    parser.add_argument("--axum-base-url")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/api-shadow-validation"))
    parser.add_argument("--report-date", help="YYYYMMDD override for deterministic report names")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--endpoint-id",
        action="append",
        dest="endpoint_ids",
        help="Run only the named endpoint id. Can be provided multiple times.",
    )
    parser.add_argument(
        "--risk",
        action="append",
        choices=sorted(VALID_RISKS),
        dest="risks",
        help="Run only endpoints with this risk level. Can be provided multiple times.",
    )
    parser.add_argument(
        "--validate-fixture-only",
        action="store_true",
        help="Validate fixture schema/contract coverage without sending HTTP requests.",
    )
    parser.add_argument(
        "--include-permission-failures",
        action="store_true",
        help="Also run permission-failure shadow cases using defaults.permission_failure and endpoint contracts.",
    )
    parser.add_argument(
        "--before-group-hook",
        help=(
            "Shell command run before each mutating isolation group. The command receives "
            "SHADOW_ISOLATION_GROUP and SHADOW_ENDPOINT_ID and should reapply PostgreSQL seed/cleanup "
            "and rewrite the isolated legacy data-dir."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.validate_fixture_only:
        report = validate_shadow_fixture(
            args.fixture,
            endpoint_ids=set(args.endpoint_ids or []),
            risks=set(args.risks or []),
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "GO" else 1
    if not args.python_base_url or not args.axum_base_url:
        raise SystemExit("--python-base-url and --axum-base-url are required unless --validate-fixture-only is set")
    report = run_shadow_validation(
        python_base_url=args.python_base_url,
        axum_base_url=args.axum_base_url,
        fixture_path=args.fixture,
        output_dir=args.output_dir,
        report_date=args.report_date,
        timeout=args.timeout,
        include_permission_failures=args.include_permission_failures,
        endpoint_ids=set(args.endpoint_ids or []),
        risks=set(args.risks or []),
        before_group_hook=args.before_group_hook,
    )
    print(json.dumps({"status": report["status"], "json_path": report["json_path"], "markdown_path": report["markdown_path"]}, ensure_ascii=False))
    return 0 if report["status"] == "GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
