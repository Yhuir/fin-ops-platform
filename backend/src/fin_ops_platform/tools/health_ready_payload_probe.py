from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Mapping, Sequence, TextIO
import sys
from urllib.parse import urljoin

from .cli_reports import write_json_report
from .http_slo_probe import HttpProbeResponse, _auth_headers, _decoded_response_body, _urllib_request

DEFAULT_TARGET_MS = 1_000.0
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RESPONSE_BYTES = 50_000
DEFAULT_MAX_API_PERFORMANCE_ENDPOINTS = 20
DEFAULT_PATH = "/health/ready"

RequestFn = Callable[[str, Mapping[str, str], float], HttpProbeResponse]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check that /health/ready is fast, JSON, and exposes bounded api_performance payload.",
    )
    parser.add_argument("--base-url", default=os.getenv("FIN_OPS_HEALTH_READY_BASE_URL", os.getenv("FIN_OPS_HTTP_SLO_BASE_URL", "http://127.0.0.1:18001")))
    parser.add_argument("--api-prefix", default=os.getenv("FIN_OPS_HEALTH_READY_API_PREFIX", os.getenv("FIN_OPS_HTTP_SLO_API_PREFIX", "")))
    parser.add_argument("--path", default=os.getenv("FIN_OPS_HEALTH_READY_PATH", DEFAULT_PATH))
    parser.add_argument("--target-ms", type=float, default=DEFAULT_TARGET_MS)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES)
    parser.add_argument("--max-api-performance-endpoints", type=int, default=DEFAULT_MAX_API_PERFORMANCE_ENDPOINTS)
    parser.add_argument("--expected-health-status", default="ready")
    parser.add_argument("--bearer-token", default=os.getenv("FIN_OPS_HTTP_SLO_BEARER_TOKEN", ""))
    parser.add_argument("--admin-token", default=os.getenv("FIN_OPS_HTTP_SLO_ADMIN_TOKEN", ""))
    parser.add_argument("--cookie", default=os.getenv("FIN_OPS_HTTP_SLO_COOKIE", ""))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="Accepted for consistency; output is always JSON.")
    return parser


def collect_health_ready_payload(
    *,
    base_url: str,
    api_prefix: str = "",
    path: str = DEFAULT_PATH,
    headers: Mapping[str, str] | None = None,
    target_ms: float = DEFAULT_TARGET_MS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    max_api_performance_endpoints: int = DEFAULT_MAX_API_PERFORMANCE_ENDPOINTS,
    expected_health_status: str = "ready",
    request_fn: RequestFn | None = None,
) -> dict[str, Any]:
    normalized_headers = {str(key): str(value) for key, value in (headers or {}).items() if str(value).strip()}
    url = resolve_health_ready_url(base_url, path, api_prefix=api_prefix)
    request = request_fn or _urllib_request
    started = monotonic()
    try:
        response = request(url, normalized_headers, timeout_seconds)
        elapsed_ms = (monotonic() - started) * 1000
    except Exception as exc:
        return {
            "version": 1,
            "tool": "health_ready_payload_probe",
            "status": "fail",
            "generated_at": datetime.now(UTC).isoformat(),
            "url": url,
            "target_ms": target_ms,
            "max_response_bytes": max_response_bytes,
            "max_api_performance_endpoints": max_api_performance_endpoints,
            "errors": [str(exc) or exc.__class__.__name__],
        }

    body = _decoded_response_body(response.body or b"", response.headers)
    content_type = _header(response.headers, "content-type")
    errors: list[str] = []
    payload: dict[str, Any] = {}
    if response.status_code != 200:
        errors.append(f"unexpected_status:{response.status_code}")
    if _looks_like_html(content_type, body):
        errors.append("html_response_for_health_ready_probe")
    elif "json" not in content_type.lower():
        errors.append("non_json_response")
    else:
        try:
            parsed = json.loads(body.decode("utf-8"))
            if isinstance(parsed, dict):
                payload = parsed
            else:
                errors.append("json_payload_not_object")
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append("invalid_json_response")

    response_bytes = len(body)
    if elapsed_ms > target_ms:
        errors.append("slo_miss")
    if response_bytes > max_response_bytes:
        errors.append("response_too_large")

    api_performance = payload.get("api_performance") if payload else None
    api_performance_endpoints_returned: int | None = None
    api_performance_endpoint_count: int | None = None
    api_performance_omitted_endpoint_count: int | None = None
    if isinstance(api_performance, dict):
        endpoints = api_performance.get("endpoints")
        if isinstance(endpoints, dict):
            api_performance_endpoints_returned = len(endpoints)
            if api_performance_endpoints_returned > max_api_performance_endpoints:
                errors.append("api_performance_endpoints_unbounded")
        endpoint_count = api_performance.get("endpoint_count")
        omitted_endpoint_count = api_performance.get("omitted_endpoint_count")
        if isinstance(endpoint_count, int):
            api_performance_endpoint_count = endpoint_count
        if isinstance(omitted_endpoint_count, int):
            api_performance_omitted_endpoint_count = omitted_endpoint_count
        if api_performance_endpoints_returned is not None and (
            api_performance_endpoint_count is None or api_performance_omitted_endpoint_count is None
        ):
            errors.append("api_performance_bound_metadata_missing")
    elif payload:
        errors.append("api_performance_missing")

    health_status = payload.get("status") if payload else None
    if expected_health_status and health_status != expected_health_status:
        errors.append("health_status_not_ready")

    runtime_blockers = _readiness_blockers(payload)
    return {
        "version": 1,
        "tool": "health_ready_payload_probe",
        "status": "pass" if not errors else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "url": url,
        "status_code": response.status_code,
        "content_type": content_type,
        "elapsed_ms": round(elapsed_ms, 3),
        "response_bytes": response_bytes,
        "target_ms": target_ms,
        "max_response_bytes": max_response_bytes,
        "max_api_performance_endpoints": max_api_performance_endpoints,
        "health_status": health_status,
        "api_performance_endpoints_returned": api_performance_endpoints_returned,
        "api_performance_endpoint_count": api_performance_endpoint_count,
        "api_performance_omitted_endpoint_count": api_performance_omitted_endpoint_count,
        "runtime_blockers": runtime_blockers,
        "runtime_blocker_count": len(runtime_blockers),
        "runtime_release_name": _runtime_release_name(payload),
        "runtime_release": payload.get("runtime_release") if payload else None,
        "errors": sorted(set(errors)),
    }


def _readiness_blockers(payload: Mapping[str, Any]) -> dict[str, Any]:
    blockers = payload.get("readiness_blockers") if payload else None
    return dict(blockers) if isinstance(blockers, dict) else {}


def _runtime_release_name(payload: Mapping[str, Any]) -> str | None:
    release = payload.get("runtime_release")
    if not isinstance(release, dict):
        return None
    metadata = release.get("release_metadata")
    if isinstance(metadata, dict):
        release_name = metadata.get("release_name")
        if isinstance(release_name, str) and release_name.strip():
            return release_name.strip()
    return None


def resolve_health_ready_url(base_url: str, path: str, *, api_prefix: str = "") -> str:
    normalized_path = str(path or DEFAULT_PATH).strip() or DEFAULT_PATH
    if normalized_path.startswith("http://") or normalized_path.startswith("https://"):
        return normalized_path
    if api_prefix and not normalized_path.startswith(_leading_slash(api_prefix).rstrip("/") + "/"):
        normalized_path = f"{_leading_slash(api_prefix).rstrip('/')}/{normalized_path.lstrip('/')}"
    return urljoin(_normalized_base_url(base_url), normalized_path.lstrip("/"))


def _looks_like_html(content_type: str, body: bytes) -> bool:
    if "html" in content_type.lower():
        return True
    prefix = body.lstrip()[:128].lower()
    return prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")


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


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    report = collect_health_ready_payload(
        base_url=args.base_url,
        api_prefix=args.api_prefix,
        path=args.path,
        headers=_auth_headers(
            bearer_token=args.bearer_token,
            admin_token=args.admin_token,
            cookie=args.cookie,
        ),
        target_ms=max(0.1, float(args.target_ms)),
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        max_response_bytes=max(1, int(args.max_response_bytes)),
        max_api_performance_endpoints=max(0, int(args.max_api_performance_endpoints)),
        expected_health_status=str(args.expected_health_status or ""),
    )
    write_json_report(report, output=args.output, stdout=stdout)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
