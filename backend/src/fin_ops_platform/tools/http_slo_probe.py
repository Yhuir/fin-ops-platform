from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import gzip
import json
from math import ceil
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Mapping, Sequence, TextIO
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_TARGET_MS = 1_000.0
DEFAULT_P99_TARGET_MS = 2_000.0
DEFAULT_ITERATIONS = 5
DEFAULT_WARMUP = 1
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_BUSINESS_MONTH = "2026-03"
MAX_CONCURRENCY = 8
FOURTEEN_DAY_MINUTE_BUCKETS = 14 * 24 * 60


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def _current_year() -> str:
    return datetime.now().strftime("%Y")


def _current_year_start() -> str:
    return f"{_current_year()}-01-01"


def _current_year_end() -> str:
    return f"{_current_year()}-12-31"


@dataclass(frozen=True)
class HttpProbe:
    name: str
    path: str
    kind: str = "api"
    expected_statuses: tuple[int, ...] = (200,)
    target_ms: float = DEFAULT_TARGET_MS
    p99_target_ms: float = DEFAULT_P99_TARGET_MS
    auth_scope: str = "user"


@dataclass(frozen=True)
class HttpProbeResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class HttpProbeSample:
    name: str
    path: str
    url: str
    kind: str
    iteration: int
    warmup: bool
    elapsed_ms: float
    status_code: int | None
    response_bytes: int
    content_type: str
    ok: bool
    error: str | None = None
    read_model_status: str | None = None
    cache_status: str | None = None
    refresh_enqueued: bool | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "url": self.url,
            "kind": self.kind,
            "iteration": self.iteration,
            "warmup": self.warmup,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "status_code": self.status_code,
            "response_bytes": self.response_bytes,
            "content_type": self.content_type,
            "ok": self.ok,
            **({"error": self.error} if self.error else {}),
            **({"read_model_status": self.read_model_status} if self.read_model_status else {}),
            **({"cache_status": self.cache_status} if self.cache_status else {}),
            **({"refresh_enqueued": self.refresh_enqueued} if self.refresh_enqueued is not None else {}),
        }


RequestFn = Callable[[str, Mapping[str, str], float], HttpProbeResponse]


DEFAULT_PAGE_PATHS: tuple[str, ...] = (
    "/fin-ops/",
    "/fin-ops/bank-details",
    "/fin-ops/pending-invoices",
    "/fin-ops/input-invoice-usage",
    "/fin-ops/oa-pending-payments",
    "/fin-ops/output-invoice-collections",
    "/fin-ops/tax-offset",
    "/fin-ops/cost-statistics",
    "/fin-ops/bank-flow-rule-batches",
    "/fin-ops/batch-accounting",
    "/fin-ops/turnover-ledger",
    "/fin-ops/etc-tickets",
    "/fin-ops/imports/bank-transactions",
    "/fin-ops/imports/invoices",
    "/fin-ops/imports/etc-invoices",
    "/fin-ops/settings",
    "/fin-ops/operations/app-health",
)


DEFAULT_API_PROBES: tuple[HttpProbe, ...] = (
    HttpProbe("session_me", "/api/session/me"),
    HttpProbe("app_health", "/api/app-health"),
    HttpProbe("background_jobs_active", "/api/background-jobs/active"),
    HttpProbe("operations_app_health_dashboard", "/api/operations/app-health-dashboard", auth_scope="admin"),
    HttpProbe("workbench_initial_all", "/api/workbench?month=all", expected_statuses=(200, 202)),
    HttpProbe("workbench_refresh_status_all", "/api/workbench/refresh-status?month=all"),
    HttpProbe("workbench_groups_all_paired", "/api/workbench/groups?month=all&zone=paired&page=1&page_size=50&detail_level=summary", expected_statuses=(200, 202)),
    HttpProbe("workbench_settings", "/api/workbench/settings", expected_statuses=(200, 202)),
    HttpProbe(
        "bank_details_accounts",
        f"/api/bank-details/accounts?date_from={_current_year_start()}&date_to={_current_year_end()}",
        expected_statuses=(200, 202),
    ),
    HttpProbe(
        "bank_details_transactions",
        f"/api/bank-details/transactions?date_from={_current_year_start()}&date_to={_current_year_end()}&page=1&page_size=50",
        expected_statuses=(200, 202),
    ),
    HttpProbe("bank_details_auto_tag_rules", "/api/bank-details/auto-tag-rules", expected_statuses=(200, 202)),
    HttpProbe(
        "pending_invoices_rows",
        "/api/pending-invoices/rows?direction=expense&page=1&page_size=50&sort_field=trade_date&sort_direction=desc&include_statistics=false",
        expected_statuses=(200, 202),
    ),
    HttpProbe("pending_invoices_rules", "/api/pending-invoices/rules", expected_statuses=(200, 202)),
    HttpProbe("input_invoice_usage_rows", "/api/input-invoice-usage/rows?page=1&page_size=20", expected_statuses=(200, 202)),
    HttpProbe("input_invoice_usage_filter_options", "/api/input-invoice-usage/filter-options", expected_statuses=(200, 202)),
    HttpProbe("input_invoice_usage_payment_status_rules", "/api/input-invoice-usage/payment-status-rules", expected_statuses=(200, 202)),
    HttpProbe("oa_pending_payments_rows", "/api/oa-pending-payments/rows?page=1&page_size=20", expected_statuses=(200, 202)),
    HttpProbe("output_invoice_collections_rows", "/api/output-invoice-collections/rows?page=1&page_size=20", expected_statuses=(200, 202)),
    HttpProbe("output_invoice_collections_filter_options", "/api/output-invoice-collections/filter-options", expected_statuses=(200, 202)),
    HttpProbe("tax_offset_summary", f"/api/tax-offset/summary?month={DEFAULT_BUSINESS_MONTH}", expected_statuses=(200, 202)),
    HttpProbe("tax_offset_rows", f"/api/tax-offset?month={DEFAULT_BUSINESS_MONTH}", expected_statuses=(200, 202)),
    HttpProbe(
        "cost_statistics_explorer_all",
        f"/api/cost-statistics/explorer?scope={DEFAULT_BUSINESS_MONTH}&view=time&project_scope=active&include_statistics=false",
        expected_statuses=(200, 202),
    ),
    HttpProbe(
        "bank_flow_rule_batches",
        f"/api/bank-flow-rule-batches?month={_current_month()}&bucket=unsubmitted&page=1&page_size=200",
        expected_statuses=(200, 202),
    ),
    HttpProbe("bank_flow_rule_batches_tag_rules", "/api/bank-flow-rule-batches/tag-rules", expected_statuses=(200, 202)),
    HttpProbe(
        "batch_accounting",
        f"/api/batch-accounting?bank_year={_current_year()}&bucket=unsubmitted&bank_page=1&bank_page_size=200&oa_page=1&oa_page_size=200",
        expected_statuses=(200, 202),
    ),
    HttpProbe("turnover_ledger_grouped", "/api/turnover-ledger?view=grouped&page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("turnover_ledger_tag_selection", "/api/turnover-ledger/tag-selection", expected_statuses=(200, 202)),
    HttpProbe("etc_invoices", "/api/etc/invoices?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("etc_business_batches", "/api/etc/business-batches?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("etc_reconciliation_tasks", "/api/etc/reconciliation-tasks?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("import_facts_batches", "/api/import-facts/batches?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("import_facts_files", "/api/import-facts/files?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("import_facts_invoices", "/api/import-facts/invoices?page=1&page_size=50", expected_statuses=(200, 202)),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect authenticated page/API first-response SLO samples from a deployed fin-ops HTTP endpoint.",
    )
    parser.add_argument("--base-url", default=os.getenv("FIN_OPS_HTTP_SLO_BASE_URL", "http://127.0.0.1:18001"))
    parser.add_argument("--api-prefix", default=os.getenv("FIN_OPS_HTTP_SLO_API_PREFIX", ""))
    parser.add_argument(
        "--page-path",
        action="append",
        default=[],
        help="Page shell path to sample. Can be repeated. Defaults to all core page shells unless --no-default-page-probe is set.",
    )
    parser.add_argument("--no-default-page-probe", action="store_true")
    parser.add_argument("--probe-config", type=Path, help="Optional JSON file with additional or replacement probes.")
    parser.add_argument("--replace-default-probes", action="store_true")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("FIN_OPS_HTTP_SLO_CONCURRENCY", "1")),
        help=f"Maximum concurrent measured requests per probe, capped at {MAX_CONCURRENCY}. Warmup requests remain sequential.",
    )
    parser.add_argument("--capacity-evidence", type=Path, help="Anonymous 14-day access aggregates or an approved capacity contract.")
    parser.add_argument("--capacity-tier", choices=("normal", "peak"), help="Use the derived normal or peak target concurrency.")
    parser.add_argument(
        "--environment-name",
        default=os.getenv("FIN_OPS_HTTP_SLO_ENVIRONMENT", "current-production"),
        help="Evidence environment label included in the report.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--target-ms", type=float, default=DEFAULT_TARGET_MS)
    parser.add_argument("--p99-target-ms", type=float, default=DEFAULT_P99_TARGET_MS)
    parser.add_argument("--bearer-token", default=os.getenv("FIN_OPS_HTTP_SLO_BEARER_TOKEN", ""))
    parser.add_argument("--admin-token", default=os.getenv("FIN_OPS_HTTP_SLO_ADMIN_TOKEN", ""))
    parser.add_argument("--cookie", default=os.getenv("FIN_OPS_HTTP_SLO_COOKIE", ""))
    parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="Allow running without auth headers. Use only for public page-shell smoke, not final production SLO.",
    )
    parser.add_argument("--include-samples", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    probes = _configured_probes(args)
    capacity: dict[str, Any] | None = None
    if args.capacity_evidence is not None or args.capacity_tier is not None:
        capacity = _capacity_not_measured("capacity evidence and --capacity-tier are required for a capacity run")
        if args.capacity_evidence is not None:
            capacity = derive_capacity_targets(json.loads(args.capacity_evidence.read_text(encoding="utf-8")))
        if capacity["status"] != "measured" or not args.capacity_tier:
            print(json.dumps({
                "version": 1,
                "status": "not_measured",
                "release_blocked": True,
                "capacity": capacity,
                "error": "capacity evidence and --capacity-tier are required for a capacity run",
            }, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
            return 1
        target_concurrency = int(capacity[f"n_{args.capacity_tier}"])
        if target_concurrency > MAX_CONCURRENCY:
            print(json.dumps({
                "version": 1,
                "status": "fail",
                "release_blocked": True,
                "capacity": capacity,
                "capacity_tier": args.capacity_tier,
                "target_concurrency": target_concurrency,
                "error": f"derived concurrency exceeds the bounded probe ceiling ({MAX_CONCURRENCY})",
            }, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
            return 1
        if args.iterations < target_concurrency:
            print(json.dumps({
                "version": 1,
                "status": "fail",
                "release_blocked": True,
                "capacity": capacity,
                "capacity_tier": args.capacity_tier,
                "target_concurrency": target_concurrency,
                "iterations": args.iterations,
                "error": "capacity iterations must be at least the derived target concurrency",
            }, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
            return 1
        args.concurrency = target_concurrency
    headers = _auth_headers(
        bearer_token=args.bearer_token or args.admin_token,
        admin_token="" if args.bearer_token else args.admin_token,
        cookie=args.cookie,
    )
    admin_headers = _auth_headers(
        bearer_token="" if args.bearer_token else args.admin_token,
        admin_token=args.admin_token,
        cookie=args.cookie,
    )
    report = collect_http_slo(
        base_url=args.base_url,
        api_prefix=args.api_prefix,
        probes=probes,
        headers=headers,
        admin_headers=admin_headers,
        iterations=max(1, int(args.iterations)),
        warmup=max(0, int(args.warmup)),
        concurrency=max(1, int(args.concurrency)),
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        evidence_environment=args.environment_name,
        require_auth=not bool(args.allow_unauthenticated),
        include_samples=bool(args.include_samples),
    )
    if capacity is not None:
        report["capacity"] = capacity
        report["capacity_tier"] = args.capacity_tier
        report["target_concurrency"] = int(capacity[f"n_{args.capacity_tier}"])
        report["capacity_concurrency_pass"] = report.get("concurrency") == report["target_concurrency"]
        if not report["capacity_concurrency_pass"]:
            report["status"] = "fail"
            report["release_blocked"] = True
            report["error"] = "actual concurrency did not equal the derived target concurrency"
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    if report["status"] == "auth_missing":
        return 2
    return 0 if report["status"] == "pass" else 1


def derive_capacity_targets(evidence: Mapping[str, Any]) -> dict[str, Any]:
    mode = str(evidence.get("mode") or "").strip()
    source = str(evidence.get("source") or "").strip()
    if mode == "capacity_contract":
        version = str(evidence.get("contract_version") or "").strip()
        approved_by = str(evidence.get("approved_by") or "").strip()
        counts = _capacity_pair(evidence)
        if not source or not version or not approved_by or counts is None:
            return _capacity_not_measured("approved capacity contract is incomplete")
        return _capacity_payload(
            source=source,
            source_version=version,
            source_proof=f"approved_by:{approved_by}",
            window=None,
            method="approved_capacity_contract",
            c_normal=counts[0],
            c_peak=counts[1],
            aggregate_sample_count=0,
        )
    if mode != "access_evidence":
        return _capacity_not_measured("named access evidence or an approved capacity contract is required")
    source_version = str(evidence.get("source_version") or "").strip()
    source_proof = str(evidence.get("source_proof") or "").strip()
    method = str(evidence.get("method") or "").strip()
    window = evidence.get("window")
    counts = evidence.get("rolling_60s_unique_visible_clients")
    if (
        not source
        or not source_version
        or not source_proof
        or method != "rolling_60s_unique_visible_clients"
        or not isinstance(window, Mapping)
        or not isinstance(counts, list)
        or len(counts) != FOURTEEN_DAY_MINUTE_BUCKETS
    ):
        return _capacity_not_measured("14-day anonymous rolling-60s access aggregates require 20,160 complete minute buckets")
    try:
        started_at = datetime.fromisoformat(str(window.get("started_at") or ""))
        completed_at = datetime.fromisoformat(str(window.get("completed_at") or ""))
        if any(not isinstance(value, int) or isinstance(value, bool) for value in counts):
            raise ValueError("counts must be integers")
        normalized_counts = list(counts)
    except (TypeError, ValueError):
        return _capacity_not_measured("capacity evidence contains invalid timestamps or counts")
    if (
        started_at.tzinfo is None
        or completed_at.tzinfo is None
        or started_at.timetz().replace(tzinfo=None) != datetime.min.time()
        or completed_at.timetz().replace(tzinfo=None) != datetime.min.time()
        or completed_at - started_at != timedelta(days=14)
        or any(value < 0 for value in normalized_counts)
    ):
        return _capacity_not_measured("capacity evidence must cover exactly 14 complete natural days")
    sorted_counts = sorted(normalized_counts)
    return _capacity_payload(
        source=source,
        source_version=source_version,
        source_proof=source_proof,
        window={"started_at": started_at.isoformat(), "completed_at": completed_at.isoformat()},
        method=method,
        c_normal=int(_nearest_rank(sorted_counts, 0.95)),
        c_peak=max(sorted_counts),
        aggregate_sample_count=len(sorted_counts),
    )


def _capacity_pair(evidence: Mapping[str, Any]) -> tuple[int, int] | None:
    c_normal = evidence.get("c_normal")
    c_peak = evidence.get("c_peak")
    if (
        not isinstance(c_normal, int)
        or isinstance(c_normal, bool)
        or not isinstance(c_peak, int)
        or isinstance(c_peak, bool)
    ):
        return None
    return (c_normal, c_peak) if 0 <= c_normal <= c_peak else None


def _capacity_payload(
    *,
    source: str,
    source_version: str,
    source_proof: str,
    window: Mapping[str, str] | None,
    method: str,
    c_normal: int,
    c_peak: int,
    aggregate_sample_count: int,
) -> dict[str, Any]:
    return {
        "status": "measured",
        "release_blocked": False,
        "source": source,
        "source_version": source_version,
        "source_proof": source_proof,
        "window": dict(window) if window is not None else None,
        "method": method,
        "c_normal": c_normal,
        "c_peak": c_peak,
        "n_normal": max(4, c_normal),
        "n_peak": max(8, c_peak),
        "aggregate_sample_count": aggregate_sample_count,
        "raw_client_data_retained": False,
    }


def _capacity_not_measured(reason: str) -> dict[str, Any]:
    return {
        "status": "not_measured",
        "release_blocked": True,
        "reason": reason,
        "raw_client_data_retained": False,
    }


def collect_http_slo(
    *,
    base_url: str,
    api_prefix: str = "",
    probes: Sequence[HttpProbe] | None = None,
    headers: Mapping[str, str] | None = None,
    admin_headers: Mapping[str, str] | None = None,
    iterations: int = DEFAULT_ITERATIONS,
    warmup: int = DEFAULT_WARMUP,
    concurrency: int = 1,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    evidence_environment: str = "current-production",
    require_auth: bool = True,
    include_samples: bool = False,
    request_fn: RequestFn | None = None,
) -> dict[str, Any]:
    normalized_headers = _normalized_probe_headers(headers or {})
    normalized_admin_headers = _normalized_probe_headers(admin_headers or {})
    auth_configured = any(key.lower() in {"authorization", "cookie"} for key in normalized_headers) or any(
        key.lower() in {"authorization", "cookie"} for key in normalized_admin_headers
    )
    if require_auth and not auth_configured:
        return {
            "version": 1,
            "status": "auth_missing",
            "generated_at": datetime.now(UTC).isoformat(),
            "base_url": _normalized_base_url(base_url),
            "api_prefix": api_prefix,
            "auth_configured": False,
            "error": "authenticated HTTP SLO sampling requires FIN_OPS_HTTP_SLO_BEARER_TOKEN, FIN_OPS_HTTP_SLO_ADMIN_TOKEN, FIN_OPS_HTTP_SLO_COOKIE, or CLI auth options",
        }
    started_at = datetime.now(UTC)
    request = request_fn or _urllib_request
    samples: list[HttpProbeSample] = []
    normalized_iterations = max(1, iterations)
    normalized_warmup = max(0, warmup)
    normalized_concurrency = max(1, min(int(concurrency), normalized_iterations, MAX_CONCURRENCY))
    for probe in probes or DEFAULT_API_PROBES:
        url = resolve_probe_url(base_url, probe.path, api_prefix=api_prefix)
        probe_headers = _headers_for_probe(
            probe,
            user_headers=normalized_headers,
            admin_headers=normalized_admin_headers,
        )
        for index in range(normalized_warmup):
            samples.append(
                _collect_one(
                    probe,
                    url=url,
                    iteration=index + 1,
                    warmup=True,
                    headers=probe_headers,
                    timeout_seconds=timeout_seconds,
                    request_fn=request,
                )
            )
        measured_indexes = range(normalized_warmup, normalized_warmup + normalized_iterations)
        if normalized_concurrency == 1:
            samples.extend(
                _collect_one(
                    probe,
                    url=url,
                    iteration=index + 1,
                    warmup=False,
                    headers=probe_headers,
                    timeout_seconds=timeout_seconds,
                    request_fn=request,
                )
                for index in measured_indexes
            )
        else:
            with ThreadPoolExecutor(max_workers=normalized_concurrency) as executor:
                futures = [
                    executor.submit(
                        _collect_one,
                        probe,
                        url=url,
                        iteration=index + 1,
                        warmup=False,
                        headers=probe_headers,
                        timeout_seconds=timeout_seconds,
                        request_fn=request,
                    )
                    for index in measured_indexes
                ]
                samples.extend(future.result() for future in futures)
    measured = [sample for sample in samples if not sample.warmup]
    probe_summaries = [_summarize_probe(probe, measured) for probe in probes or DEFAULT_API_PROBES]
    status = "pass" if all(item["status"] == "pass" for item in probe_summaries) else "fail"
    completed_at = datetime.now(UTC)
    return {
        "version": 1,
        "status": status,
        "generated_at": completed_at.isoformat(),
        "evidence_environment": str(evidence_environment or "").strip() or "current-production",
        "evidence_window": {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        },
        "base_url": _normalized_base_url(base_url),
        "api_prefix": api_prefix,
        "auth_configured": auth_configured,
        "iterations": normalized_iterations,
        "warmup": normalized_warmup,
        "concurrency": normalized_concurrency,
        "timeout_seconds": timeout_seconds,
        "summary": {
            "probe_count": len(probe_summaries),
            "sample_count": len(measured),
            "request_count": len(measured),
            "error_count": sum(1 for sample in measured if not sample.ok),
            "failed_probe_count": sum(1 for item in probe_summaries if item["status"] != "pass"),
            "max_p95_ms": max((float(item["duration_ms"]["p95"] or 0.0) for item in probe_summaries), default=0.0),
            "response_bytes_total": sum(sample.response_bytes for sample in measured),
        },
        "probes": probe_summaries,
        **({"samples": [sample.to_payload() for sample in samples]} if include_samples else {}),
    }


def resolve_probe_url(base_url: str, path: str, *, api_prefix: str = "") -> str:
    normalized_path = str(path or "/").strip() or "/"
    if normalized_path.startswith("http://") or normalized_path.startswith("https://"):
        return normalized_path
    if normalized_path.startswith("/api/") and api_prefix:
        normalized_path = f"{_leading_slash(api_prefix).rstrip('/')}{normalized_path}"
    return urljoin(_normalized_base_url(base_url), normalized_path.lstrip("/"))


def _collect_one(
    probe: HttpProbe,
    *,
    url: str,
    iteration: int,
    warmup: bool,
    headers: Mapping[str, str],
    timeout_seconds: float,
    request_fn: RequestFn,
) -> HttpProbeSample:
    started = monotonic()
    try:
        response = request_fn(url, headers, timeout_seconds)
        elapsed_ms = (monotonic() - started) * 1000
        content_type = _header(response.headers, "content-type")
        raw_body = response.body or b""
        body = _decoded_response_body(raw_body, response.headers)
        metadata = _extract_response_metadata(body, content_type)
        status_ok = response.status_code in probe.expected_statuses
        html_api_error = _html_response_error(probe, content_type, body) if status_ok else None
        ok = status_ok and html_api_error is None
        return HttpProbeSample(
            name=probe.name,
            path=probe.path,
            url=url,
            kind=probe.kind,
            iteration=iteration,
            warmup=warmup,
            elapsed_ms=elapsed_ms,
            status_code=response.status_code,
            response_bytes=len(raw_body),
            content_type=content_type,
            ok=ok,
            error=None if ok else html_api_error or f"unexpected_status:{response.status_code}",
            read_model_status=metadata.get("read_model_status"),
            cache_status=metadata.get("cache_status"),
            refresh_enqueued=metadata.get("refresh_enqueued"),
        )
    except Exception as exc:
        elapsed_ms = (monotonic() - started) * 1000
        return HttpProbeSample(
            name=probe.name,
            path=probe.path,
            url=url,
            kind=probe.kind,
            iteration=iteration,
            warmup=warmup,
            elapsed_ms=elapsed_ms,
            status_code=None,
            response_bytes=0,
            content_type="",
            ok=False,
            error=str(exc) or exc.__class__.__name__,
        )


def _urllib_request(url: str, headers: Mapping[str, str], timeout_seconds: float) -> HttpProbeResponse:
    request = Request(url, method="GET", headers=dict(headers))
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - operator-provided URL for SLO probe.
            return HttpProbeResponse(
                status_code=int(response.getcode()),
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(),
            )
    except HTTPError as exc:
        return HttpProbeResponse(
            status_code=int(exc.code),
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=exc.read(),
        )
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(str(reason) or exc.__class__.__name__) from exc


def _summarize_probe(probe: HttpProbe, samples: Sequence[HttpProbeSample]) -> dict[str, Any]:
    probe_samples = [sample for sample in samples if sample.name == probe.name]
    durations = [sample.elapsed_ms for sample in probe_samples]
    response_sizes = [float(sample.response_bytes) for sample in probe_samples]
    status_counts: dict[str, int] = {}
    errors: list[str] = []
    error_counts: dict[str, int] = {}
    read_model_statuses: dict[str, int] = {}
    cache_statuses: dict[str, int] = {}
    refresh_enqueued_count = 0
    for sample in probe_samples:
        status_key = str(sample.status_code) if sample.status_code is not None else "error"
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        if sample.error and sample.error not in errors:
            errors.append(sample.error)
        if sample.error:
            error_counts[sample.error] = error_counts.get(sample.error, 0) + 1
        if sample.read_model_status:
            read_model_statuses[sample.read_model_status] = read_model_statuses.get(sample.read_model_status, 0) + 1
        if sample.cache_status:
            cache_statuses[sample.cache_status] = cache_statuses.get(sample.cache_status, 0) + 1
        if sample.refresh_enqueued:
            refresh_enqueued_count += 1
    success_count = sum(1 for sample in probe_samples if sample.ok)
    duration_percentiles = _percentiles(durations)
    p95 = duration_percentiles["p95"]
    p99 = duration_percentiles["p99"]
    non_fresh_statuses = {
        status: count
        for status, count in read_model_statuses.items()
        if status != "fresh"
    }
    passes_status = success_count == len(probe_samples) and bool(probe_samples)
    passes_p95 = p95 is not None and p95 <= probe.target_ms
    passes_p99 = p99 is not None and p99 <= probe.p99_target_ms
    passes_slo = passes_p95 and passes_p99
    passes_freshness = not non_fresh_statuses and refresh_enqueued_count == 0
    return {
        "name": probe.name,
        "kind": probe.kind,
        "path": probe.path,
        "target_ms": probe.target_ms,
        "p99_target_ms": probe.p99_target_ms,
        "expected_statuses": list(probe.expected_statuses),
        "sample_count": len(probe_samples),
        "request_count": len(probe_samples),
        "success_count": success_count,
        "error_count": len(probe_samples) - success_count,
        "failure_count": len(probe_samples) - success_count,
        "status_counts": status_counts,
        "duration_ms": duration_percentiles,
        "response_bytes": _percentiles(response_sizes),
        "p95_pass": bool(passes_p95),
        "p99_pass": bool(passes_p99),
        "slo_pass": bool(passes_slo),
        "freshness_pass": bool(passes_freshness),
        "status": "pass" if passes_status and passes_slo and passes_freshness else "fail",
        "errors": errors,
        "error_counts": error_counts,
        "read_model_statuses": read_model_statuses,
        "non_fresh_read_model_statuses": non_fresh_statuses,
        "cache_statuses": cache_statuses,
        "refresh_enqueued_count": refresh_enqueued_count,
    }


def _configured_probes(args: argparse.Namespace) -> list[HttpProbe]:
    probes: list[HttpProbe] = []
    page_paths = list(args.page_path or [])
    if not args.no_default_page_probe and not page_paths:
        page_paths.extend(DEFAULT_PAGE_PATHS)
    probes.extend(
        HttpProbe(
            name=_page_probe_name(path, fallback_index=index),
            path=path,
            kind="page",
            expected_statuses=(200,),
            target_ms=float(args.target_ms),
            p99_target_ms=float(args.p99_target_ms),
        )
        for index, path in enumerate(page_paths, start=1)
    )
    if not args.replace_default_probes:
        probes.extend(_with_target(DEFAULT_API_PROBES, float(args.target_ms), float(args.p99_target_ms)))
    if args.probe_config is not None:
        probes.extend(_load_probe_config(
            args.probe_config,
            default_target_ms=float(args.target_ms),
            default_p99_target_ms=float(args.p99_target_ms),
        ))
    return probes


def _page_probe_name(path: str, *, fallback_index: int) -> str:
    normalized = str(path or "").strip().strip("/")
    if normalized.startswith("fin-ops/"):
        normalized = normalized.removeprefix("fin-ops/")
    elif normalized == "fin-ops":
        normalized = "home"
    normalized = normalized.replace("/", "_").replace("-", "_") or "home"
    return f"page_shell_{normalized or fallback_index}"


def _load_probe_config(
    path: Path,
    *,
    default_target_ms: float,
    default_p99_target_ms: float,
) -> list[HttpProbe]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items = payload.get("probes") if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise ValueError("probe config must be a JSON list or an object with a probes list.")
    probes: list[HttpProbe] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"probe #{index} must be an object.")
        statuses = raw.get("expected_statuses", [200])
        if not isinstance(statuses, list) or not statuses:
            raise ValueError(f"probe #{index} expected_statuses must be a non-empty list.")
        probes.append(
            HttpProbe(
                name=str(raw.get("name") or f"custom_probe_{index}").strip() or f"custom_probe_{index}",
                path=str(raw.get("path") or "").strip(),
                kind=str(raw.get("kind") or "api").strip() or "api",
                expected_statuses=tuple(int(value) for value in statuses),
                target_ms=float(raw.get("target_ms") or default_target_ms),
                p99_target_ms=float(raw.get("p99_target_ms") or default_p99_target_ms),
                auth_scope=_normalize_auth_scope(raw.get("auth_scope")),
            )
        )
    return probes


def _with_target(probes: Sequence[HttpProbe], target_ms: float, p99_target_ms: float) -> list[HttpProbe]:
    return [
        HttpProbe(
            name=probe.name,
            path=probe.path,
            kind=probe.kind,
            expected_statuses=probe.expected_statuses,
            target_ms=target_ms,
            p99_target_ms=p99_target_ms,
            auth_scope=probe.auth_scope,
        )
        for probe in probes
    ]


def _headers_for_probe(
    probe: HttpProbe,
    *,
    user_headers: Mapping[str, str],
    admin_headers: Mapping[str, str],
) -> Mapping[str, str]:
    if _normalize_auth_scope(probe.auth_scope) == "admin" and admin_headers:
        return admin_headers
    return user_headers


def _normalize_auth_scope(value: object) -> str:
    return "admin" if str(value or "").strip().lower() == "admin" else "user"


def _normalized_probe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    normalized = _auth_headers()
    normalized.update({str(key): str(value) for key, value in headers.items() if str(value).strip()})
    return normalized


def _auth_headers(*, bearer_token: str = "", admin_token: str = "", cookie: str = "") -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json, text/html;q=0.9, */*;q=0.1",
        "Accept-Encoding": "gzip",
        "User-Agent": "fin-ops-http-slo-probe/1",
    }
    normalized_cookie = str(cookie or "").strip()
    normalized_admin_token = str(admin_token or "").strip()
    normalized_bearer_token = str(bearer_token or "").strip()
    if normalized_cookie:
        headers["Cookie"] = normalized_cookie
    elif normalized_admin_token:
        headers["Cookie"] = f"Admin-Token={normalized_admin_token}"
    if normalized_bearer_token:
        headers["Authorization"] = f"Bearer {normalized_bearer_token}"
    elif normalized_admin_token:
        headers["Authorization"] = f"Bearer {normalized_admin_token}"
    return headers


def _decoded_response_body(body: bytes, headers: Mapping[str, str]) -> bytes:
    if _header(headers, "content-encoding").lower() != "gzip":
        return body
    try:
        return gzip.decompress(body)
    except (OSError, EOFError):
        return body


def _extract_response_metadata(body: bytes, content_type: str) -> dict[str, Any]:
    if "json" not in content_type.lower():
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: value
        for key, value in {
            "read_model_status": _first_string(payload, ("read_model_status", "readModelStatus")),
            "cache_status": _first_string(payload, ("cache_status", "cacheStatus")),
            "refresh_enqueued": _first_bool(payload, ("refresh_enqueued", "refreshEnqueued")),
        }.items()
        if value is not None
    }


def _first_string(payload: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _html_response_error(probe: HttpProbe, content_type: str, body: bytes) -> str | None:
    if str(probe.kind or "").lower() != "api":
        return None
    normalized_content_type = content_type.lower()
    if "html" in normalized_content_type:
        return "html_response_for_api_probe"
    prefix = body.lstrip()[:128].lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
        return "html_response_for_api_probe"
    return None


def _first_bool(payload: Mapping[str, Any], keys: Sequence[str]) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _percentiles(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None}
    sorted_values = sorted(float(value) for value in values)
    return {
        "p50": _nearest_rank(sorted_values, 0.50),
        "p95": _nearest_rank(sorted_values, 0.95),
        "p99": _nearest_rank(sorted_values, 0.99),
    }


def _nearest_rank(sorted_values: Sequence[float], percentile: float) -> float:
    index = max(0, min(len(sorted_values) - 1, ceil(percentile * len(sorted_values)) - 1))
    return round(float(sorted_values[index]), 3)


def _header(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return str(value)
    return ""


def _leading_slash(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.startswith("/") else f"/{text}"


def _normalized_base_url(value: str) -> str:
    text = str(value or "").strip() or "http://127.0.0.1:18001"
    return text if text.endswith("/") else f"{text}/"


if __name__ == "__main__":
    raise SystemExit(main())
