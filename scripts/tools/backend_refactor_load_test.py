#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence


REQUIRED_SCENARIO_IDS = {
    "healthz",
    "readyz",
    "workbench_month_read_model",
    "search",
    "task_status",
    "import_metadata",
    "cost_read_model",
    "tax_read_model",
}
REQUIRED_ENV_VARS = (
    "FIN_OPS_STAGING_BASE_URL",
    "FIN_OPS_STAGING_AUTH_TOKEN",
    "FIN_OPS_LOAD_TEST_MONTH",
    "FIN_OPS_LOAD_TEST_SEARCH_QUERY",
    "FIN_OPS_LOAD_TEST_TASK_ID",
    "FIN_OPS_LOAD_TEST_IMPORT_FILE_ID",
    "FIN_OPS_LOAD_TEST_DATASET_LABEL",
    "FIN_OPS_LOAD_TEST_BANK_TRANSACTION_ROWS",
    "FIN_OPS_LOAD_TEST_INVOICE_ROWS",
    "FIN_OPS_LOAD_TEST_SEARCH_ROWS",
)
STAGING_HOST_HINTS = ("staging", "stage", "stg", "localhost", "127.0.0.1", "::1")
FORBIDDEN_ROUTE_HINTS = ("oa-source", "source-db", "source_db", "live-oa", "mongo")


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    label: str
    path_template: str
    source_category: str
    target_p95_ms: float
    requires_auth: bool = True

    def render_path(self, variables: Mapping[str, str]) -> str:
        return self.path_template.format(**variables)


@dataclass(frozen=True)
class LoadTestConfig:
    base_url: str
    auth_token: str
    month: str
    search_query: str
    task_id: str
    import_file_id: str
    dataset_label: str
    bank_transaction_rows: int
    invoice_rows: int
    search_rows: int
    requests_per_scenario: int
    concurrency: int
    timeout_seconds: float
    max_error_rate: float
    dry_run: bool
    output_json: str | None
    output_markdown: str | None
    db_pool_stats: dict[str, object]
    nats_outbox_backlog: dict[str, object]
    worker_lag_seconds: dict[str, object]
    read_model_stale_seconds: dict[str, object]


@dataclass(frozen=True)
class RequestResult:
    scenario_id: str
    elapsed_ms: float
    ok: bool
    status_code: int | None
    error: str | None = None


DEFAULT_SCENARIOS = (
    ScenarioDefinition("healthz", "Process health", "/healthz", "static_health", 20.0, False),
    ScenarioDefinition("readyz", "Dependency readiness", "/readyz", "dependency_health", 80.0, False),
    ScenarioDefinition(
        "workbench_month_read_model",
        "Single-month workbench read model",
        "/api/workbench?month={month}",
        "read_model",
        800.0,
    ),
    ScenarioDefinition(
        "search",
        "Search",
        "/api/search?q={search_query}",
        "read_model",
        500.0,
    ),
    ScenarioDefinition(
        "task_status",
        "Task status",
        "/api/background-jobs/{task_id}",
        "job_status",
        300.0,
    ),
    ScenarioDefinition(
        "import_metadata",
        "Import metadata",
        "/imports/files/{import_file_id}",
        "postgres_facts",
        300.0,
    ),
    ScenarioDefinition(
        "cost_read_model",
        "Representative cost read model",
        "/api/cost-statistics?month={month}",
        "read_model",
        800.0,
    ),
    ScenarioDefinition(
        "tax_read_model",
        "Representative tax read model",
        "/api/tax-offset?month={month}",
        "read_model",
        800.0,
    ),
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a staging-only backend refactor load test baseline. "
            "The tool validates configuration before any request and refuses production-looking hosts."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate config and print the scenario matrix only.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Alias for --dry-run; does not send HTTP requests.",
    )
    parser.add_argument(
        "--requests-per-scenario",
        type=int,
        default=int_env_default("FIN_OPS_LOAD_TEST_REQUESTS_PER_SCENARIO", 20),
        help="Request count per scenario. Default: env FIN_OPS_LOAD_TEST_REQUESTS_PER_SCENARIO or 20.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int_env_default("FIN_OPS_LOAD_TEST_CONCURRENCY", 4),
        help="Maximum concurrent requests. Default: env FIN_OPS_LOAD_TEST_CONCURRENCY or 4.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float_env_default("FIN_OPS_LOAD_TEST_TIMEOUT_SECONDS", 5.0),
        help="Per-request timeout in seconds. Default: env FIN_OPS_LOAD_TEST_TIMEOUT_SECONDS or 5.",
    )
    parser.add_argument(
        "--max-error-rate",
        type=float,
        default=float_env_default("FIN_OPS_LOAD_TEST_MAX_ERROR_RATE", 0.0),
        help="Maximum allowed aggregate and per-scenario error rate from 0 to 1. Default: 0.",
    )
    parser.add_argument("--output-json", help="Optional path for generated JSON report.")
    parser.add_argument("--output-markdown", help="Optional path for generated Markdown report.")
    parser.add_argument(
        "--print-sample-config",
        action="store_true",
        help="Print placeholder environment configuration and exit.",
    )
    return parser.parse_args(argv)


def int_env_default(key: str, fallback: int) -> int:
    try:
        return int(os.environ.get(key, str(fallback)))
    except ValueError:
        return fallback


def float_env_default(key: str, fallback: float) -> float:
    try:
        return float(os.environ.get(key, str(fallback)))
    except ValueError:
        return fallback


def build_config(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> LoadTestConfig:
    environ = os.environ if env is None else env
    return LoadTestConfig(
        base_url=environ.get("FIN_OPS_STAGING_BASE_URL", "").strip(),
        auth_token=environ.get("FIN_OPS_STAGING_AUTH_TOKEN", "").strip(),
        month=environ.get("FIN_OPS_LOAD_TEST_MONTH", "").strip(),
        search_query=environ.get("FIN_OPS_LOAD_TEST_SEARCH_QUERY", "").strip(),
        task_id=environ.get("FIN_OPS_LOAD_TEST_TASK_ID", "").strip(),
        import_file_id=environ.get("FIN_OPS_LOAD_TEST_IMPORT_FILE_ID", "").strip(),
        dataset_label=environ.get("FIN_OPS_LOAD_TEST_DATASET_LABEL", "").strip(),
        bank_transaction_rows=parse_int_env(environ, "FIN_OPS_LOAD_TEST_BANK_TRANSACTION_ROWS"),
        invoice_rows=parse_int_env(environ, "FIN_OPS_LOAD_TEST_INVOICE_ROWS"),
        search_rows=parse_int_env(environ, "FIN_OPS_LOAD_TEST_SEARCH_ROWS"),
        requests_per_scenario=args.requests_per_scenario,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout_seconds,
        max_error_rate=args.max_error_rate,
        dry_run=bool(args.dry_run or args.validate_only),
        output_json=args.output_json,
        output_markdown=args.output_markdown,
        db_pool_stats=parse_optional_json_metric(environ, "FIN_OPS_LOAD_TEST_DB_POOL_STATS_JSON"),
        nats_outbox_backlog=parse_optional_json_metric(environ, "FIN_OPS_LOAD_TEST_NATS_OUTBOX_BACKLOG_JSON"),
        worker_lag_seconds=parse_optional_json_metric(environ, "FIN_OPS_LOAD_TEST_WORKER_LAG_SECONDS_JSON"),
        read_model_stale_seconds=parse_optional_json_metric(
            environ,
            "FIN_OPS_LOAD_TEST_READ_MODEL_STALE_SECONDS_JSON",
        ),
    )


def parse_int_env(env: Mapping[str, str], key: str) -> int:
    value = env.get(key, "").strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def parse_optional_json_metric(env: Mapping[str, str], key: str) -> dict[str, object]:
    value = env.get(key, "").strip()
    if not value:
        return {"available": False}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {"available": False, "parse_error": f"{key} is not valid JSON"}
    if not isinstance(payload, dict):
        return {"available": False, "parse_error": f"{key} must be a JSON object"}
    return {"available": True, **payload}


def validate_config(config: LoadTestConfig) -> list[str]:
    errors: list[str] = []
    missing = [key for key in REQUIRED_ENV_VARS if not config_value_present(config, key)]
    missing_set = set(missing)
    errors.extend(f"missing required environment variable: {key}" for key in missing)

    parsed = urllib.parse.urlsplit(config.base_url)
    if config.base_url and parsed.scheme not in {"http", "https"}:
        errors.append("FIN_OPS_STAGING_BASE_URL must start with http:// or https://")
    if config.base_url and not parsed.netloc:
        errors.append("FIN_OPS_STAGING_BASE_URL must include a host")
    if parsed.hostname and not host_looks_like_staging(parsed.hostname):
        errors.append(
            "FIN_OPS_STAGING_BASE_URL host must look like staging/local "
            "(contains staging, stage, stg, localhost, 127.0.0.1 or ::1)"
        )
    if config.requests_per_scenario <= 0:
        errors.append("--requests-per-scenario must be greater than 0")
    if config.concurrency <= 0:
        errors.append("--concurrency must be greater than 0")
    if config.timeout_seconds <= 0:
        errors.append("--timeout-seconds must be greater than 0")
    if not 0 <= config.max_error_rate <= 1:
        errors.append("--max-error-rate must be between 0 and 1")
    if "FIN_OPS_LOAD_TEST_BANK_TRANSACTION_ROWS" not in missing_set and config.bank_transaction_rows <= 0:
        errors.append("FIN_OPS_LOAD_TEST_BANK_TRANSACTION_ROWS must be a positive integer")
    if "FIN_OPS_LOAD_TEST_INVOICE_ROWS" not in missing_set and config.invoice_rows <= 0:
        errors.append("FIN_OPS_LOAD_TEST_INVOICE_ROWS must be a positive integer")
    if "FIN_OPS_LOAD_TEST_SEARCH_ROWS" not in missing_set and config.search_rows <= 0:
        errors.append("FIN_OPS_LOAD_TEST_SEARCH_ROWS must be a positive integer")

    variables = scenario_variables(config)
    for scenario in DEFAULT_SCENARIOS:
        path = scenario.render_path(variables)
        if route_looks_forbidden(path):
            errors.append(f"scenario {scenario.scenario_id} resolves to a forbidden source route: {path}")
    if REQUIRED_SCENARIO_IDS - {scenario.scenario_id for scenario in DEFAULT_SCENARIOS}:
        errors.append("default scenario set does not cover all required scenario ids")
    return errors


def config_value_present(config: LoadTestConfig, env_key: str) -> bool:
    mapping = {
        "FIN_OPS_STAGING_BASE_URL": bool(config.base_url),
        "FIN_OPS_STAGING_AUTH_TOKEN": bool(config.auth_token),
        "FIN_OPS_LOAD_TEST_MONTH": bool(config.month),
        "FIN_OPS_LOAD_TEST_SEARCH_QUERY": bool(config.search_query),
        "FIN_OPS_LOAD_TEST_TASK_ID": bool(config.task_id),
        "FIN_OPS_LOAD_TEST_IMPORT_FILE_ID": bool(config.import_file_id),
        "FIN_OPS_LOAD_TEST_DATASET_LABEL": bool(config.dataset_label),
        "FIN_OPS_LOAD_TEST_BANK_TRANSACTION_ROWS": config.bank_transaction_rows > 0,
        "FIN_OPS_LOAD_TEST_INVOICE_ROWS": config.invoice_rows > 0,
        "FIN_OPS_LOAD_TEST_SEARCH_ROWS": config.search_rows > 0,
    }
    return mapping[env_key]


def host_looks_like_staging(hostname: str) -> bool:
    normalized = hostname.lower()
    return any(hint in normalized for hint in STAGING_HOST_HINTS)


def route_looks_forbidden(path: str) -> bool:
    normalized = path.lower()
    return any(hint in normalized for hint in FORBIDDEN_ROUTE_HINTS)


def scenario_variables(config: LoadTestConfig) -> dict[str, str]:
    return {
        "month": urllib.parse.quote(config.month, safe="-"),
        "search_query": urllib.parse.quote(config.search_query, safe=""),
        "task_id": urllib.parse.quote(config.task_id, safe=""),
        "import_file_id": urllib.parse.quote(config.import_file_id, safe=""),
    }


def run_load_test(config: LoadTestConfig) -> dict[str, object]:
    variables = scenario_variables(config)
    start_time = now_iso()
    tasks: list[tuple[ScenarioDefinition, str]] = []
    for scenario in DEFAULT_SCENARIOS:
        path = scenario.render_path(variables)
        tasks.extend((scenario, path) for _ in range(config.requests_per_scenario))

    results: list[RequestResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        futures = [
            executor.submit(send_request, config, scenario, path)
            for scenario, path in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    end_time = now_iso()
    return build_report(config, start_time, end_time, results)


def send_request(config: LoadTestConfig, scenario: ScenarioDefinition, path: str) -> RequestResult:
    url = join_url(config.base_url, path)
    headers = {
        "User-Agent": "fin-ops-backend-refactor-load-test/1.0",
        "Accept": "application/json,text/plain,*/*",
        "X-Fin-Ops-Load-Test": "load-test-h3",
    }
    if scenario.requires_auth:
        headers["Authorization"] = f"Bearer {config.auth_token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            response.read()
            elapsed_ms = (time.perf_counter() - started) * 1000
            return RequestResult(
                scenario.scenario_id,
                elapsed_ms,
                200 <= response.status < 500,
                response.status,
            )
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RequestResult(scenario.scenario_id, elapsed_ms, False, exc.code, f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError) as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RequestResult(scenario.scenario_id, elapsed_ms, False, None, exc.__class__.__name__)


def join_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def build_report(
    config: LoadTestConfig,
    start_time: str,
    end_time: str,
    results: Sequence[RequestResult],
) -> dict[str, object]:
    variables = scenario_variables(config)
    by_scenario: dict[str, list[RequestResult]] = {
        scenario.scenario_id: [] for scenario in DEFAULT_SCENARIOS
    }
    for result in results:
        by_scenario.setdefault(result.scenario_id, []).append(result)

    scenario_reports = []
    for scenario in DEFAULT_SCENARIOS:
        scenario_results = by_scenario.get(scenario.scenario_id, [])
        scenario_summary = summarize_results(scenario_results, config.max_error_rate, scenario.target_p95_ms)
        scenario_reports.append(
            {
                "id": scenario.scenario_id,
                "label": scenario.label,
                "path": scenario.render_path(variables),
                "source_category": scenario.source_category,
                "request_count": scenario_summary["request_count"],
                "concurrency": config.concurrency,
                "latency_ms": scenario_summary["latency_ms"],
                "error_rate": scenario_summary["error_rate"],
                "target_p95_ms": scenario.target_p95_ms,
                "status": scenario_summary["status"],
                "status_codes": scenario_summary["status_codes"],
                "errors": scenario_summary["errors"],
            }
        )

    aggregate = summarize_results(results, config.max_error_rate, max(s.target_p95_ms for s in DEFAULT_SCENARIOS))
    status = "GO" if aggregate["status"] == "GO" and all(s["status"] == "GO" for s in scenario_reports) else "NO_GO"
    parsed = urllib.parse.urlsplit(config.base_url)
    return {
        "report": "load-test-baseline",
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "target_host": parsed.hostname or "",
        "dataset_scale": {
            "label": config.dataset_label,
            "months": [config.month],
            "bank_transactions": config.bank_transaction_rows,
            "invoice_rows": config.invoice_rows,
            "search_rows": config.search_rows,
        },
        "request_count": aggregate["request_count"],
        "concurrency": config.concurrency,
        "latency_ms": aggregate["latency_ms"],
        "error_rate": aggregate["error_rate"],
        "db_pool_stats": config.db_pool_stats,
        "nats_outbox_backlog": config.nats_outbox_backlog,
        "worker_lag_seconds": config.worker_lag_seconds,
        "read_model_stale_seconds": config.read_model_stale_seconds,
        "scenarios": scenario_reports,
    }


def summarize_results(
    results: Sequence[RequestResult],
    max_error_rate: float,
    target_p95_ms: float,
) -> dict[str, object]:
    latencies = sorted(result.elapsed_ms for result in results)
    request_count = len(results)
    error_count = sum(1 for result in results if not result.ok)
    error_rate = error_count / request_count if request_count else 1.0
    latency = {
        "p50": percentile(latencies, 50),
        "p95": percentile(latencies, 95),
        "p99": percentile(latencies, 99),
    }
    status = "GO" if request_count and error_rate <= max_error_rate and latency["p95"] <= target_p95_ms else "NO_GO"
    status_codes: dict[str, int] = {}
    errors: dict[str, int] = {}
    for result in results:
        code = str(result.status_code) if result.status_code is not None else "none"
        status_codes[code] = status_codes.get(code, 0) + 1
        if result.error:
            errors[result.error] = errors.get(result.error, 0) + 1
    return {
        "request_count": request_count,
        "latency_ms": latency,
        "error_rate": round(error_rate, 6),
        "status": status,
        "status_codes": status_codes,
        "errors": errors,
    }


def percentile(sorted_values: Sequence[float], percentile_value: int) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)
    rank = (len(sorted_values) - 1) * percentile_value / 100
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    value = sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight
    return round(value, 3)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def render_scenario_matrix(config: LoadTestConfig) -> str:
    variables = scenario_variables(config)
    lines = [
        "| Scenario | Method | Path | Source | Target P95 ms |",
        "| --- | --- | --- | --- | --- |",
    ]
    for scenario in DEFAULT_SCENARIOS:
        lines.append(
            f"| `{scenario.scenario_id}` | `GET` | `{scenario.render_path(variables)}` | "
            f"`{scenario.source_category}` | `{scenario.target_p95_ms:g}` |"
        )
    return "\n".join(lines) + "\n"


def render_markdown_report(report: Mapping[str, object]) -> str:
    lines = [
        "# Staging Load Test Baseline Report",
        "",
        f"- Gate: **{report['status']}**",
        f"- Start time: `{report['start_time']}`",
        f"- End time: `{report['end_time']}`",
        f"- Target host: `{report['target_host']}`",
        f"- Request count: `{report['request_count']}`",
        f"- Concurrency: `{report['concurrency']}`",
        f"- Error rate: `{report['error_rate']}`",
        f"- Latency P50/P95/P99 ms: `{format_latency(report['latency_ms'])}`",
        "",
        "## Scenario Results",
        "",
        "| Scenario | Path | Requests | P50 | P95 | P99 | Error Rate | Gate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for raw in report["scenarios"]:
        scenario = dict(raw)
        latency = dict(scenario["latency_ms"])
        lines.append(
            f"| `{scenario['id']}` | `{scenario['path']}` | {scenario['request_count']} | "
            f"{latency['p50']} | {latency['p95']} | {latency['p99']} | "
            f"{scenario['error_rate']} | `{scenario['status']}` |"
        )
    return "\n".join(lines) + "\n"


def format_latency(raw: object) -> str:
    latency = dict(raw) if isinstance(raw, dict) else {}
    return f"{latency.get('p50', 0)}/{latency.get('p95', 0)}/{latency.get('p99', 0)}"


def print_sample_config() -> None:
    print(
        "\n".join(
            [
                "export FIN_OPS_STAGING_BASE_URL=${STAGING_BASE_URL}",
                "export FIN_OPS_STAGING_AUTH_TOKEN=${STAGING_LOAD_TEST_TOKEN}",
                "export FIN_OPS_LOAD_TEST_MONTH=YYYY-MM",
                "export FIN_OPS_LOAD_TEST_SEARCH_QUERY=${STAGING_SEARCH_QUERY}",
                "export FIN_OPS_LOAD_TEST_TASK_ID=${STAGING_TASK_ID}",
                "export FIN_OPS_LOAD_TEST_IMPORT_FILE_ID=${STAGING_IMPORT_FILE_ID}",
                "export FIN_OPS_LOAD_TEST_DATASET_LABEL=staging-medium",
                "export FIN_OPS_LOAD_TEST_BANK_TRANSACTION_ROWS=100000",
                "export FIN_OPS_LOAD_TEST_INVOICE_ROWS=100000",
                "export FIN_OPS_LOAD_TEST_SEARCH_ROWS=1000000",
                "export FIN_OPS_LOAD_TEST_DB_POOL_STATS_JSON='{\"available\":true,\"in_use\":0}'",
                "export FIN_OPS_LOAD_TEST_NATS_OUTBOX_BACKLOG_JSON='{\"available\":true,\"pending\":0}'",
                "export FIN_OPS_LOAD_TEST_WORKER_LAG_SECONDS_JSON='{\"available\":true,\"max\":0}'",
                "export FIN_OPS_LOAD_TEST_READ_MODEL_STALE_SECONDS_JSON='{\"available\":true,\"max\":0}'",
            ]
        )
    )


def write_report_files(config: LoadTestConfig, report: Mapping[str, object]) -> None:
    if config.output_json:
        with open(config.output_json, "w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
    if config.output_markdown:
        with open(config.output_markdown, "w", encoding="utf-8") as file:
            file.write(render_markdown_report(report))


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = parse_args(argv)
    if args.print_sample_config:
        print_sample_config()
        return 0
    config = build_config(args, env)
    errors = validate_config(config)
    if errors:
        print("Configuration validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print("No requests were sent.", file=sys.stderr)
        return 2
    if config.dry_run:
        print("Configuration validation passed. No requests were sent.")
        print(render_scenario_matrix(config), end="")
        return 0

    report = run_load_test(config)
    write_report_files(config, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "GO" else 3


if __name__ == "__main__":
    raise SystemExit(main())
