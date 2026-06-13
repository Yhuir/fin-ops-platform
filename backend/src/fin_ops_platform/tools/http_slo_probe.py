from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
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


DEFAULT_TARGET_MS = 5_000.0
DEFAULT_ITERATIONS = 5
DEFAULT_WARMUP = 1
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_BUSINESS_MONTH = "2026-03"


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
    "/fin-ops/no-oa-bank-batches",
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
    HttpProbe("operations_app_health_dashboard", "/api/operations/app-health-dashboard"),
    HttpProbe("workbench_summary_all", "/api/workbench/summary?month=all", expected_statuses=(200, 202)),
    HttpProbe("workbench_groups_all_paired", "/api/workbench/groups?month=all&zone=paired&page=1&page_size=50", expected_statuses=(200, 202)),
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
        "/api/pending-invoices/rows?direction=expense&page=1&page_size=50&sort_field=trade_date&sort_direction=desc",
        expected_statuses=(200, 202),
    ),
    HttpProbe(
        "pending_invoices_filter_options",
        "/api/pending-invoices/filter-options?direction=expense&sort_field=trade_date&sort_direction=desc",
        expected_statuses=(200, 202),
    ),
    HttpProbe("pending_invoices_rules", "/api/pending-invoices/rules", expected_statuses=(200, 202)),
    HttpProbe("input_invoice_usage_rows", "/api/input-invoice-usage/rows?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("input_invoice_usage_filter_options", "/api/input-invoice-usage/filter-options", expected_statuses=(200, 202)),
    HttpProbe("input_invoice_usage_payment_status_rules", "/api/input-invoice-usage/payment-status-rules", expected_statuses=(200, 202)),
    HttpProbe("oa_pending_payments_rows", "/api/oa-pending-payments/rows?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("oa_pending_payments_filter_options", "/api/oa-pending-payments/filter-options", expected_statuses=(200, 202)),
    HttpProbe("output_invoice_collections_rows", "/api/output-invoice-collections/rows?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("output_invoice_collections_filter_options", "/api/output-invoice-collections/filter-options", expected_statuses=(200, 202)),
    HttpProbe("output_invoice_collections_status_rules", "/api/output-invoice-collections/status-rules", expected_statuses=(200, 202)),
    HttpProbe("tax_offset_summary", f"/api/tax-offset/summary?month={DEFAULT_BUSINESS_MONTH}", expected_statuses=(200, 202)),
    HttpProbe("tax_offset_rows", f"/api/tax-offset?month={DEFAULT_BUSINESS_MONTH}", expected_statuses=(200, 202)),
    HttpProbe(
        "cost_statistics_explorer_all",
        f"/api/cost-statistics/explorer?month={DEFAULT_BUSINESS_MONTH}&project_scope=active",
        expected_statuses=(200, 202),
    ),
    HttpProbe(
        "cost_statistics_summary_all",
        f"/api/cost-statistics?month={DEFAULT_BUSINESS_MONTH}&project_scope=active",
        expected_statuses=(200, 202),
    ),
    HttpProbe(
        "no_oa_bank_batches",
        f"/api/no-oa-bank-batches?month={_current_month()}&bucket=unsubmitted&page=1&page_size=50",
        expected_statuses=(200, 202),
    ),
    HttpProbe("no_oa_bank_batches_tag_selection", "/api/no-oa-bank-batches/tag-selection", expected_statuses=(200, 202)),
    HttpProbe(
        "batch_accounting",
        f"/api/batch-accounting?bank_year={_current_year()}&oa_year={_current_year()}&bucket=unsubmitted&page=1&page_size=50",
        expected_statuses=(200, 202),
    ),
    HttpProbe("turnover_ledger_grouped", "/api/turnover-ledger?view=grouped&page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("turnover_ledger_tag_selection", "/api/turnover-ledger/tag-selection", expected_statuses=(200, 202)),
    HttpProbe("etc_invoices", "/api/etc/invoices?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("etc_batches", "/api/etc/batches?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("etc_business_batches", "/api/etc/business-batches?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("etc_reconciliation_tasks", "/api/etc/reconciliation-tasks?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("import_facts_batches", "/api/import-facts/batches?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("import_facts_files", "/api/import-facts/files?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("import_facts_invoices", "/api/import-facts/invoices?page=1&page_size=50", expected_statuses=(200, 202)),
    HttpProbe("search_all", "/api/search?q=%E5%85%AC%E5%8F%B8&scope=all&month=all&limit=5", expected_statuses=(200, 202)),
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
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--target-ms", type=float, default=DEFAULT_TARGET_MS)
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
    headers = _auth_headers(
        bearer_token=args.bearer_token,
        admin_token=args.admin_token,
        cookie=args.cookie,
    )
    report = collect_http_slo(
        base_url=args.base_url,
        api_prefix=args.api_prefix,
        probes=probes,
        headers=headers,
        iterations=max(1, int(args.iterations)),
        warmup=max(0, int(args.warmup)),
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        require_auth=not bool(args.allow_unauthenticated),
        include_samples=bool(args.include_samples),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    if report["status"] == "auth_missing":
        return 2
    return 0 if report["status"] == "pass" else 1


def collect_http_slo(
    *,
    base_url: str,
    api_prefix: str = "",
    probes: Sequence[HttpProbe] | None = None,
    headers: Mapping[str, str] | None = None,
    iterations: int = DEFAULT_ITERATIONS,
    warmup: int = DEFAULT_WARMUP,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    require_auth: bool = True,
    include_samples: bool = False,
    request_fn: RequestFn | None = None,
) -> dict[str, Any]:
    normalized_headers = {str(key): str(value) for key, value in (headers or {}).items() if str(value).strip()}
    auth_configured = any(key.lower() in {"authorization", "cookie"} for key in normalized_headers)
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
    request = request_fn or _urllib_request
    samples: list[HttpProbeSample] = []
    for probe in probes or DEFAULT_API_PROBES:
        url = resolve_probe_url(base_url, probe.path, api_prefix=api_prefix)
        for index in range(max(0, warmup) + max(1, iterations)):
            warmup_sample = index < warmup
            samples.append(
                _collect_one(
                    probe,
                    url=url,
                    iteration=index + 1,
                    warmup=warmup_sample,
                    headers=normalized_headers,
                    timeout_seconds=timeout_seconds,
                    request_fn=request,
                )
            )
    measured = [sample for sample in samples if not sample.warmup]
    probe_summaries = [_summarize_probe(probe, measured) for probe in probes or DEFAULT_API_PROBES]
    status = "pass" if all(item["status"] == "pass" for item in probe_summaries) else "fail"
    return {
        "version": 1,
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": _normalized_base_url(base_url),
        "api_prefix": api_prefix,
        "auth_configured": auth_configured,
        "iterations": max(1, iterations),
        "warmup": max(0, warmup),
        "timeout_seconds": timeout_seconds,
        "summary": {
            "probe_count": len(probe_summaries),
            "sample_count": len(measured),
            "failed_probe_count": sum(1 for item in probe_summaries if item["status"] != "pass"),
            "max_p95_ms": max((float(item["duration_ms"]["p95"] or 0.0) for item in probe_summaries), default=0.0),
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
        body = response.body or b""
        metadata = _extract_response_metadata(body, content_type)
        ok = response.status_code in probe.expected_statuses
        return HttpProbeSample(
            name=probe.name,
            path=probe.path,
            url=url,
            kind=probe.kind,
            iteration=iteration,
            warmup=warmup,
            elapsed_ms=elapsed_ms,
            status_code=response.status_code,
            response_bytes=len(body),
            content_type=content_type,
            ok=ok,
            error=None if ok else f"unexpected_status:{response.status_code}",
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
    status_counts: dict[str, int] = {}
    errors: list[str] = []
    read_model_statuses: dict[str, int] = {}
    cache_statuses: dict[str, int] = {}
    refresh_enqueued_count = 0
    for sample in probe_samples:
        status_key = str(sample.status_code) if sample.status_code is not None else "error"
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        if sample.error and sample.error not in errors:
            errors.append(sample.error)
        if sample.read_model_status:
            read_model_statuses[sample.read_model_status] = read_model_statuses.get(sample.read_model_status, 0) + 1
        if sample.cache_status:
            cache_statuses[sample.cache_status] = cache_statuses.get(sample.cache_status, 0) + 1
        if sample.refresh_enqueued:
            refresh_enqueued_count += 1
    success_count = sum(1 for sample in probe_samples if sample.ok)
    p95 = _percentiles(durations)["p95"]
    non_fresh_statuses = {
        status: count
        for status, count in read_model_statuses.items()
        if status != "fresh"
    }
    passes_status = success_count == len(probe_samples) and bool(probe_samples)
    passes_slo = p95 is not None and p95 <= probe.target_ms
    passes_freshness = not non_fresh_statuses and refresh_enqueued_count == 0
    return {
        "name": probe.name,
        "kind": probe.kind,
        "path": probe.path,
        "target_ms": probe.target_ms,
        "expected_statuses": list(probe.expected_statuses),
        "sample_count": len(probe_samples),
        "success_count": success_count,
        "failure_count": len(probe_samples) - success_count,
        "status_counts": status_counts,
        "duration_ms": _percentiles(durations),
        "slo_pass": bool(passes_slo),
        "freshness_pass": bool(passes_freshness),
        "status": "pass" if passes_status and passes_slo and passes_freshness else "fail",
        "errors": errors,
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
        )
        for index, path in enumerate(page_paths, start=1)
    )
    if not args.replace_default_probes:
        probes.extend(_with_target(DEFAULT_API_PROBES, float(args.target_ms)))
    if args.probe_config is not None:
        probes.extend(_load_probe_config(args.probe_config, default_target_ms=float(args.target_ms)))
    return probes


def _page_probe_name(path: str, *, fallback_index: int) -> str:
    normalized = str(path or "").strip().strip("/")
    if normalized.startswith("fin-ops/"):
        normalized = normalized.removeprefix("fin-ops/")
    elif normalized == "fin-ops":
        normalized = "home"
    normalized = normalized.replace("/", "_").replace("-", "_") or "home"
    return f"page_shell_{normalized or fallback_index}"


def _load_probe_config(path: Path, *, default_target_ms: float) -> list[HttpProbe]:
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
            )
        )
    return probes


def _with_target(probes: Sequence[HttpProbe], target_ms: float) -> list[HttpProbe]:
    return [
        HttpProbe(
            name=probe.name,
            path=probe.path,
            kind=probe.kind,
            expected_statuses=probe.expected_statuses,
            target_ms=target_ms,
        )
        for probe in probes
    ]


def _auth_headers(*, bearer_token: str = "", admin_token: str = "", cookie: str = "") -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json, text/html;q=0.9, */*;q=0.1",
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
