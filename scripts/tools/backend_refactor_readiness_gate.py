#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


GO_MARKERS = ("`GO`", "| GO |", "go_no_go: GO", "go/no-go | `GO`", "Gate: **GO**")
NO_GO_MARKERS = ("`NO_GO`", "| NO_GO |", "go_no_go: NO_GO", "go/no-go | `NO_GO`", "Gate: **NO_GO**")
API_SHADOW_ALLOWED_SOURCE_CATEGORIES = {
    "postgres_facts",
    "read_model",
    "job_outbox",
    "object_storage",
    "static_contract",
    "oa_identity",
    "transactional_workbench_write",
}
API_SHADOW_SOURCE_CATEGORY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("postgres_facts", ("postgresql", "job.worker_tasks")),
    ("read_model", ("read_model", "read model")),
    ("job_outbox", ("job/outbox", "outbox", "job.worker_tasks")),
    ("object_storage", ("object-storage", "object storage")),
    ("static_contract", ("static contract", "static legacy")),
    ("oa_identity", ("oa identity",)),
    ("transactional_workbench_write", ("transactional workbench write",)),
)
API_SHADOW_APP_MONGO_HINTS = ("app mongo", "mongo")
API_SHADOW_NEGATIVE_SOURCE_HINTS = ("no ", "not ", "without ", "does not ", "doesn't ", "不得", "不", "未")
LOAD_TEST_REQUIRED_SCENARIOS = {
    "healthz",
    "readyz",
    "workbench_month_read_model",
    "search",
    "task_status",
    "import_metadata",
    "cost_read_model",
    "tax_read_model",
}
LOAD_TEST_REQUIRED_TOP_LEVEL_FIELDS = {
    "start_time",
    "end_time",
    "dataset_scale",
    "request_count",
    "concurrency",
    "latency_ms",
    "error_rate",
    "db_pool_stats",
    "nats_outbox_backlog",
    "worker_lag_seconds",
    "read_model_stale_seconds",
    "scenarios",
}


@dataclass(frozen=True)
class EvidenceCheck:
    check_id: str
    label: str
    patterns: tuple[str, ...]
    required_text_any: tuple[str, ...] = ()
    blocking_prompt: str | None = None
    required_text_all: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    label: str
    status: str
    evidence: list[str]
    reason: str
    blocking_prompt: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "label": self.label,
            "status": self.status,
            "evidence": self.evidence,
            "reason": self.reason,
            "blocking_prompt": self.blocking_prompt,
        }


DEFAULT_CHECKS: tuple[EvidenceCheck, ...] = (
    EvidenceCheck(
        check_id="app_mongo_backup_restore",
        label="App Mongo backup, checksum and restore drill",
        patterns=("docs/operations/backend-refactor/app-mongo-backup-runbook.md",),
        required_text_all=("collection count", "diff=0", "checksum"),
        blocking_prompt="docs/exec-plans/active/backend-refactor-prompts/02-app-mongo-backup.md",
    ),
    EvidenceCheck(
        "postgres_backup_pitr",
        "PostgreSQL backup and PITR or restore drill",
        (
            "docs/operations/backend-refactor/postgres-pitr-drill-*.md",
            "docs/operations/backend-refactor/postgres-backup-restore-drill-*.md",
            "docs/operations/backend-refactor/postgres-backup-restore-drill-*.json",
        ),
        GO_MARKERS,
        "docs/exec-plans/active/backend-refactor-prompts/10-observability-security-readiness.md",
    ),
    EvidenceCheck(
        "migration_dry_run",
        "06C data dry-run reconciliation report",
        ("docs/operations/backend-refactor/migration-dry-run-report-*.md",),
        GO_MARKERS,
        "docs/exec-plans/active/backend-refactor-prompts/06c-data-migration-dry-run.md",
    ),
    EvidenceCheck(
        "file_checksum",
        "GridFS to MinIO/S3 checksum validation",
        (
            "docs/operations/backend-refactor/gridfs-minio-migration-report-*.md",
            "docs/operations/backend-refactor/gridfs-minio-migration-report-*.json",
        ),
        GO_MARKERS,
        "docs/exec-plans/active/backend-refactor-prompts/06d-gridfs-minio-migration.md",
    ),
    EvidenceCheck(
        "api_shadow_validation",
        "Python vs Axum shadow read or contract validation",
        (
            "docs/operations/backend-refactor/api-shadow-validation-report-*.md",
            "docs/operations/backend-refactor/api-contract-validation-report-*.md",
            "docs/operations/backend-refactor/api-shadow-validation-report-*.json",
        ),
        GO_MARKERS,
        "docs/exec-plans/active/backend-refactor-prompts/09a-low-risk-read-apis.md",
    ),
    EvidenceCheck(
        "nats_worker_replay",
        "NATS/outbox/worker staging validation and replay drill",
        (
            "docs/operations/backend-refactor/nats-worker-validation-report-*.md",
            "docs/operations/backend-refactor/nats-worker-validation-report-*.json",
        ),
        GO_MARKERS,
        "docs/exec-plans/active/backend-refactor-prompts/07-outbox-queue-worker.md",
    ),
    EvidenceCheck(
        "read_model_rebuild",
        "Read model/search rebuild validation",
        (
            "docs/operations/backend-refactor/read-model-rebuild-validation-report-*.md",
            "docs/operations/backend-refactor/read-model-rebuild-validation-report-*.json",
        ),
        GO_MARKERS,
        "docs/exec-plans/active/backend-refactor-prompts/08-read-models-and-search.md",
    ),
    EvidenceCheck(
        "monitoring_alerts",
        "Prometheus/Grafana/P0/P1 alert verification",
        (
            "docs/operations/backend-refactor/monitoring-alert-verification-*.md",
            "docs/operations/backend-refactor/monitoring-alert-verification-*.json",
        ),
        GO_MARKERS,
        "docs/exec-plans/active/backend-refactor-prompts/10-observability-security-readiness.md",
    ),
    EvidenceCheck(
        "load_test",
        "Staging load test baseline",
        (
            "docs/operations/backend-refactor/load-test-baseline-*.md",
            "docs/operations/backend-refactor/load-test-baseline-*.json",
        ),
        GO_MARKERS,
        "docs/exec-plans/active/backend-refactor-prompts/10-observability-security-readiness.md",
    ),
    EvidenceCheck(
        "cutover_window_rollback",
        "Maintenance window and rollback drill approval",
        (
            "docs/operations/backend-refactor/cutover-window-approval-*.md",
            "docs/operations/backend-refactor/rollback-drill-record-*.md",
            "docs/operations/backend-refactor/rollback-drill-record-*.json",
        ),
        GO_MARKERS,
        "docs/exec-plans/active/backend-refactor-prompts/11-cutover-and-rollback.md",
    ),
)


def evaluate(root: Path, checks: Iterable[EvidenceCheck] = DEFAULT_CHECKS) -> dict[str, object]:
    results = [evaluate_check(root, check) for check in checks]
    blocking = [result for result in results if result.status != "passed"]
    return {
        "status": "GO" if not blocking else "NO_GO",
        "blocking_count": len(blocking),
        "passed_count": len(results) - len(blocking),
        "checks": [result.to_dict() for result in results],
    }


def evaluate_check(root: Path, check: EvidenceCheck) -> CheckResult:
    matches = find_matches(root, check.patterns)
    evidence = [str(path.relative_to(root)) for path in matches]
    if not matches:
        return CheckResult(
            check.check_id,
            check.label,
            "missing",
            evidence,
            "required evidence file is missing",
            check.blocking_prompt,
        )

    if check.check_id == "api_shadow_validation":
        return evaluate_api_shadow_validation_check(root, check, matches, evidence)

    if check.check_id == "load_test":
        return evaluate_load_test_check(root, check, matches, evidence)

    if not check.required_text_any and not check.required_text_all:
        return CheckResult(check.check_id, check.label, "passed", evidence, "evidence exists", None)

    for path in matches:
        text = read_text(path)
        structured_decision = read_structured_decision(path, text)
        if check.check_id == "api_shadow_validation" and path.name.startswith("api-shadow-validation-report-"):
            if path.suffix.lower() == ".json" and not api_shadow_json_evidence_is_complete(text):
                structured_decision = "NO_GO"
        any_marker_ok = not check.required_text_any or any(
            marker in text for marker in check.required_text_any
        ) or structured_decision == "GO"
        all_markers_ok = all(marker in text for marker in check.required_text_all)
        blocker_ok = not contains_blocker_evidence(text) if check.check_id == "migration_dry_run" else True
        has_no_go = contains_no_go(text) or structured_decision == "NO_GO"
        if any_marker_ok and all_markers_ok and not has_no_go and blocker_ok:
            return CheckResult(
                check.check_id,
                check.label,
                "passed",
                evidence,
                f"required marker found in {path.relative_to(root)}",
                None,
            )

    return CheckResult(
        check.check_id,
        check.label,
        "failed",
        evidence,
        "evidence exists but does not contain a passing marker",
        check.blocking_prompt,
    )


def evaluate_api_shadow_validation_check(
    root: Path,
    check: EvidenceCheck,
    matches: list[Path],
    evidence: list[str],
) -> CheckResult:
    shadow_json_by_stem = {
        path.stem: path
        for path in matches
        if path.name.startswith("api-shadow-validation-report-") and path.suffix.lower() == ".json"
    }
    shadow_markdown_by_stem = {
        path.stem: path
        for path in matches
        if path.name.startswith("api-shadow-validation-report-") and path.suffix.lower() == ".md"
    }
    paired_stems = sorted(set(shadow_json_by_stem) & set(shadow_markdown_by_stem))
    if not paired_stems:
        return CheckResult(
            check.check_id,
            check.label,
            "failed",
            evidence,
            "api shadow validation requires matching JSON and Markdown reports",
            check.blocking_prompt,
        )

    for stem in paired_stems:
        json_path = shadow_json_by_stem[stem]
        markdown_path = shadow_markdown_by_stem[stem]
        json_text = read_text(json_path)
        markdown_text = read_text(markdown_path)
        json_decision = read_structured_decision(json_path, json_text)
        json_go = (
            json_decision == "GO"
            and api_shadow_json_evidence_is_complete(json_text)
            and not contains_no_go(json_text)
        )
        markdown_go = any(marker in markdown_text for marker in check.required_text_any) and not contains_no_go(
            markdown_text
        )
        if json_go and markdown_go:
            return CheckResult(
                check.check_id,
                check.label,
                "passed",
                evidence,
                f"paired API shadow reports passed for {stem}",
                None,
            )

    return CheckResult(
        check.check_id,
        check.label,
        "failed",
        evidence,
        "paired API shadow reports exist but no pair has complete GO JSON and GO Markdown evidence",
        check.blocking_prompt,
    )


def evaluate_load_test_check(
    root: Path,
    check: EvidenceCheck,
    matches: list[Path],
    evidence: list[str],
) -> CheckResult:
    load_json_by_stem = {
        path.stem: path
        for path in matches
        if path.name.startswith("load-test-baseline-") and path.suffix.lower() == ".json"
    }
    load_markdown_by_stem = {
        path.stem: path
        for path in matches
        if path.name.startswith("load-test-baseline-") and path.suffix.lower() == ".md"
    }
    paired_stems = sorted(set(load_json_by_stem) & set(load_markdown_by_stem))
    if not paired_stems:
        return CheckResult(
            check.check_id,
            check.label,
            "failed",
            evidence,
            "load test baseline requires matching JSON and Markdown reports",
            check.blocking_prompt,
        )

    for stem in paired_stems:
        json_path = load_json_by_stem[stem]
        markdown_path = load_markdown_by_stem[stem]
        json_text = read_text(json_path)
        markdown_text = read_text(markdown_path)
        json_go = load_test_json_evidence_is_complete(json_text)
        markdown_go = any(marker in markdown_text for marker in check.required_text_any) and not contains_no_go(
            markdown_text
        )
        if json_go and markdown_go:
            return CheckResult(
                check.check_id,
                check.label,
                "passed",
                evidence,
                f"paired load test baseline reports passed for {stem}",
                None,
            )

    return CheckResult(
        check.check_id,
        check.label,
        "failed",
        evidence,
        "paired load test baseline reports exist but no pair has complete GO JSON and GO Markdown evidence",
        check.blocking_prompt,
    )


def find_matches(root: Path, patterns: Iterable[str]) -> list[Path]:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(path for path in root.glob(pattern) if path.is_file() and not is_template(path))
    return sorted(set(matches))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def is_template(path: Path) -> bool:
    return path.stem.endswith("-template")


def read_structured_decision(path: Path, text: str) -> str | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return extract_json_decision(payload)


def extract_json_decision(payload: dict[str, object]) -> str | None:
    candidates: list[str] = []
    for key in ("status", "go_no_go"):
        value = payload.get(key)
        if isinstance(value, str):
            candidates.append(value)

    decision = payload.get("decision")
    if isinstance(decision, dict):
        value = decision.get("go_no_go")
        if isinstance(value, str):
            candidates.append(value)

    summary = payload.get("summary")
    if isinstance(summary, dict):
        no_go = summary.get("no_go")
        if isinstance(no_go, int) and no_go > 0:
            candidates.append("NO_GO")
        fixture_error_count = summary.get("fixture_error_count")
        if isinstance(fixture_error_count, int) and fixture_error_count > 0:
            candidates.append("NO_GO")

    fixture_validation = payload.get("fixture_validation")
    if isinstance(fixture_validation, dict):
        status = fixture_validation.get("status")
        if isinstance(status, str):
            candidates.append(status)
        endpoint_errors = fixture_validation.get("endpoint_errors")
        if isinstance(endpoint_errors, list) and endpoint_errors:
            candidates.append("NO_GO")

    results = payload.get("results")
    if isinstance(results, list):
        for result in results:
            if isinstance(result, dict):
                status = result.get("status")
                if isinstance(status, str):
                    candidates.append(status)

    readiness_gates = payload.get("readiness_gates")
    if isinstance(readiness_gates, dict):
        for gate in readiness_gates.values():
            if isinstance(gate, dict):
                decision = gate.get("decision")
                if isinstance(decision, str):
                    candidates.append(decision)

    normalized = {candidate.strip().upper() for candidate in candidates if candidate.strip()}
    if "NO_GO" in normalized:
        return "NO_GO"
    if normalized and normalized <= {"GO"}:
        return "GO"
    return None


def api_shadow_json_evidence_is_complete(text: str) -> bool:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("status") != "GO":
        return False
    fixture_validation = payload.get("fixture_validation")
    if not isinstance(fixture_validation, dict):
        return False
    if fixture_validation.get("status") != "GO":
        return False
    endpoint_errors = fixture_validation.get("endpoint_errors")
    if not isinstance(endpoint_errors, list) or endpoint_errors:
        return False
    endpoint_count = fixture_validation.get("endpoint_count")
    if not isinstance(endpoint_count, int) or endpoint_count <= 0:
        return False
    endpoint_ids = fixture_validation.get("endpoint_ids")
    if not api_shadow_fixture_endpoint_ids_are_complete(endpoint_ids, endpoint_count):
        return False
    permission_failure_endpoint_ids = fixture_validation.get("permission_failure_endpoint_ids")
    if not api_shadow_permission_failure_endpoint_ids_are_valid(
        permission_failure_endpoint_ids,
        endpoint_ids,
    ):
        return False
    if not api_shadow_filters_are_unscoped(payload.get("filters")):
        return False
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return False
    total = summary.get("total")
    go = summary.get("go")
    no_go = summary.get("no_go")
    unexpected_diff_count = summary.get("unexpected_diff_count", 0)
    fixture_error_count = summary.get("fixture_error_count", 0)
    if total != len(results) or total <= 0:
        return False
    if go != total or no_go != 0:
        return False
    if unexpected_diff_count != 0 or fixture_error_count != 0:
        return False
    if not api_shadow_primary_coverage_matches_fixture(results, endpoint_ids):
        return False
    if not api_shadow_permission_failure_coverage_matches_fixture(
        results,
        permission_failure_endpoint_ids,
    ):
        return False
    if not api_shadow_permission_failure_summary_matches_results(
        summary,
        results,
        permission_failure_endpoint_ids,
    ):
        return False
    for result in results:
        if not isinstance(result, dict):
            return False
        if result.get("status") != "GO":
            return False
        if result.get("unexpected_diff_count", 0) != 0:
            return False
        source = result.get("source")
        if not isinstance(source, str) or not source.strip() or source.strip() == "unspecified":
            return False
        if not api_shadow_source_is_allowed(source):
            return False
        source_categories = result.get("source_categories")
        if not api_shadow_source_categories_match(source, source_categories):
            return False
    return True


def load_test_json_evidence_is_complete(text: str) -> bool:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("status") != "GO":
        return False
    if contains_no_go(text):
        return False
    if not LOAD_TEST_REQUIRED_TOP_LEVEL_FIELDS <= set(payload):
        return False
    if not isinstance(payload.get("start_time"), str) or not payload["start_time"].strip():
        return False
    if not isinstance(payload.get("end_time"), str) or not payload["end_time"].strip():
        return False
    if not isinstance(payload.get("dataset_scale"), dict) or not payload["dataset_scale"]:
        return False
    request_count = payload.get("request_count")
    concurrency = payload.get("concurrency")
    error_rate = payload.get("error_rate")
    if not isinstance(request_count, int) or request_count <= 0:
        return False
    if not isinstance(concurrency, int) or concurrency <= 0:
        return False
    if not load_test_error_rate_is_valid(error_rate):
        return False
    if not load_test_latency_is_valid(payload.get("latency_ms")):
        return False
    for metric_key in (
        "db_pool_stats",
        "nats_outbox_backlog",
        "worker_lag_seconds",
        "read_model_stale_seconds",
    ):
        if not isinstance(payload.get(metric_key), dict):
            return False
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return False
    scenario_ids: set[str] = set()
    scenario_request_total = 0
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            return False
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or not scenario_id:
            return False
        scenario_ids.add(scenario_id)
        if scenario.get("status") != "GO":
            return False
        path = scenario.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            return False
        scenario_request_count = scenario.get("request_count")
        if not isinstance(scenario_request_count, int) or scenario_request_count <= 0:
            return False
        scenario_request_total += scenario_request_count
        if not load_test_latency_is_valid(scenario.get("latency_ms")):
            return False
        if not load_test_error_rate_is_valid(scenario.get("error_rate")):
            return False
    if not LOAD_TEST_REQUIRED_SCENARIOS <= scenario_ids:
        return False
    return scenario_request_total == request_count


def load_test_latency_is_valid(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    percentiles: list[float] = []
    for key in ("p50", "p95", "p99"):
        raw = value.get(key)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool) or raw < 0:
            return False
        percentiles.append(float(raw))
    return percentiles[0] <= percentiles[1] <= percentiles[2]


def load_test_error_rate_is_valid(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def api_shadow_filters_are_unscoped(filters: object) -> bool:
    if not isinstance(filters, dict):
        return False
    if "endpoint_ids" not in filters or "risks" not in filters:
        return False
    return filters["endpoint_ids"] == [] and filters["risks"] == []


def api_shadow_fixture_endpoint_ids_are_complete(endpoint_ids: object, endpoint_count: int) -> bool:
    if not isinstance(endpoint_ids, list):
        return False
    if not all(isinstance(endpoint_id, str) and endpoint_id for endpoint_id in endpoint_ids):
        return False
    return len(endpoint_ids) == endpoint_count and len(set(endpoint_ids)) == endpoint_count


def api_shadow_permission_failure_endpoint_ids_are_valid(
    permission_failure_endpoint_ids: object,
    fixture_endpoint_ids: object,
) -> bool:
    if not isinstance(permission_failure_endpoint_ids, list):
        return False
    if not isinstance(fixture_endpoint_ids, list):
        return False
    if not all(isinstance(endpoint_id, str) and endpoint_id for endpoint_id in permission_failure_endpoint_ids):
        return False
    fixture_id_set = set(fixture_endpoint_ids)
    permission_id_set = set(permission_failure_endpoint_ids)
    return len(permission_id_set) == len(permission_failure_endpoint_ids) and permission_id_set <= fixture_id_set


def api_shadow_primary_coverage_matches_fixture(results: list[object], fixture_endpoint_ids: object) -> bool:
    if not isinstance(fixture_endpoint_ids, list):
        return False
    primary_endpoint_ids = []
    for result in results:
        if not isinstance(result, dict):
            return False
        case = result.get("case", "primary")
        if case == "primary":
            endpoint_id = result.get("endpoint_id")
            if not isinstance(endpoint_id, str) or not endpoint_id:
                return False
            primary_endpoint_ids.append(endpoint_id)
    return sorted(primary_endpoint_ids) == sorted(fixture_endpoint_ids)


def api_shadow_permission_failure_coverage_matches_fixture(
    results: list[object],
    permission_failure_endpoint_ids: object,
) -> bool:
    if not isinstance(permission_failure_endpoint_ids, list):
        return False
    required_case_ids = {f"{endpoint_id}#permission_failure" for endpoint_id in permission_failure_endpoint_ids}
    actual_case_ids = set()
    for result in results:
        if not isinstance(result, dict):
            return False
        if result.get("case") == "permission_failure":
            endpoint_id = result.get("endpoint_id")
            if not isinstance(endpoint_id, str) or not endpoint_id:
                return False
            actual_case_ids.add(endpoint_id)
    return actual_case_ids == required_case_ids


def api_shadow_permission_failure_summary_matches_results(
    summary: dict[str, object],
    results: list[object],
    permission_failure_endpoint_ids: object,
) -> bool:
    if not isinstance(permission_failure_endpoint_ids, list):
        return False
    required_summary_keys = {
        "permission_failure_cases",
        "permission_failure_required_count",
        "permission_failure_missing_count",
    }
    if not required_summary_keys <= set(summary):
        return False
    permission_failure_cases = sum(
        1
        for result in results
        if isinstance(result, dict) and result.get("case") == "permission_failure"
    )
    return (
        summary.get("permission_failure_cases", 0) == permission_failure_cases
        and summary.get("permission_failure_required_count", 0) == len(permission_failure_endpoint_ids)
        and summary.get("permission_failure_missing_count", 0) == 0
    )


def api_shadow_source_categories_match(source: str, source_categories: object) -> bool:
    if not isinstance(source_categories, list) or not source_categories:
        return False
    if not all(isinstance(category, str) and category in API_SHADOW_ALLOWED_SOURCE_CATEGORIES for category in source_categories):
        return False
    return sorted(set(source_categories)) == classify_api_shadow_source_categories(source)


def api_shadow_source_is_allowed(source: str) -> bool:
    normalized = normalize_api_shadow_source(source)
    if not classify_api_shadow_source_categories(source):
        return False
    return not api_shadow_source_mentions_active_app_mongo(normalized)


def classify_api_shadow_source_categories(source: str) -> list[str]:
    normalized = normalize_api_shadow_source(source)
    categories = [
        category
        for category, hints in API_SHADOW_SOURCE_CATEGORY_HINTS
        if any(hint in normalized for hint in hints)
    ]
    return sorted(set(categories))


def normalize_api_shadow_source(source: str) -> str:
    lowered = source.lower()
    return "".join(character if character.isalnum() or character == "_" else " " for character in lowered)


def api_shadow_source_mentions_active_app_mongo(normalized_source: str) -> bool:
    for hint in API_SHADOW_APP_MONGO_HINTS:
        start = 0
        while True:
            index = normalized_source.find(hint, start)
            if index < 0:
                break
            context = normalized_source[max(0, index - 48):index]
            if not any(negative in context for negative in API_SHADOW_NEGATIVE_SOURCE_HINTS):
                return True
            start = index + len(hint)
    return False


def contains_no_go(text: str) -> bool:
    return any(marker in text for marker in NO_GO_MARKERS)


def contains_blocker_evidence(text: str) -> bool:
    normalized = text.lower()
    if '"blocking": true' in normalized:
        return True
    if "blocking: `true`" in normalized or "| blocking | `true`" in normalized:
        return True
    if '"has_blockers": true' in normalized:
        return True
    if '"blocking_findings": 0' not in normalized and '"blocking_findings":' in normalized:
        return True
    return False


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Backend Refactor Readiness Gate",
        "",
        f"Decision: `{report['status']}`",
        f"Blocking checks: `{report['blocking_count']}`",
        "",
        "| Check | Status | Evidence | Reason | Prompt |",
        "| --- | --- | --- | --- | --- |",
    ]
    for raw in report["checks"]:
        item = dict(raw)
        evidence = "<br>".join(item["evidence"]) if item["evidence"] else "-"
        prompt = item["blocking_prompt"] or "-"
        lines.append(
            f"| `{item['check_id']}` | `{item['status']}` | {evidence} | {item['reason']} | {prompt} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate backend refactor readiness evidence without touching production systems.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--fail-on-no-go", action="store_true", help="Exit 2 when the decision is NO_GO.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    report = evaluate(root)
    if args.format == "markdown":
        print(render_markdown(report), end="")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if args.fail_on_no_go and report["status"] != "GO" else 0


if __name__ == "__main__":
    raise SystemExit(main())
