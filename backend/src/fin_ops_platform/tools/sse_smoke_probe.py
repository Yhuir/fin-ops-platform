from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from time import monotonic
from typing import Any, Callable, Mapping, Sequence, TextIO
import sys

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fin_ops_platform.tools import http_slo_probe


DEFAULT_TARGET_MS = 1_000.0
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_BYTES = 8_192


@dataclass(frozen=True)
class SseProbe:
    name: str
    path: str
    expected_event_prefixes: tuple[str, ...]
    expected_statuses: tuple[int, ...] = (200,)
    target_ms: float = DEFAULT_TARGET_MS


@dataclass(frozen=True)
class SseProbeResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


RequestFn = Callable[[str, Mapping[str, str], float, int], SseProbeResponse]


DEFAULT_SSE_PROBES: tuple[SseProbe, ...] = (
    SseProbe("app_health_stream", "/api/app-health/stream", ("app_health", "heartbeat")),
    SseProbe("workbench_events_all", "/api/workbench/events?month=all", ("workbench.read_model", "heartbeat")),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect first-event SLO samples from fin-ops SSE endpoints.",
    )
    parser.add_argument("--base-url", default=os.getenv("FIN_OPS_HTTP_SLO_BASE_URL", "http://127.0.0.1:18001"))
    parser.add_argument("--api-prefix", default=os.getenv("FIN_OPS_HTTP_SLO_API_PREFIX", ""))
    parser.add_argument("--path", action="append", default=[], help="SSE path to sample. Defaults to core SSE endpoints.")
    parser.add_argument("--target-ms", type=float, default=DEFAULT_TARGET_MS)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--bearer-token", default=os.getenv("FIN_OPS_HTTP_SLO_BEARER_TOKEN", ""))
    parser.add_argument("--admin-token", default=os.getenv("FIN_OPS_HTTP_SLO_ADMIN_TOKEN", ""))
    parser.add_argument("--cookie", default=os.getenv("FIN_OPS_HTTP_SLO_COOKIE", ""))
    parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="Allow running without auth headers. Use only for route/debug smoke, not final production SSE SLO.",
    )
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    headers = http_slo_probe._auth_headers(
        bearer_token=args.bearer_token,
        admin_token=args.admin_token,
        cookie=args.cookie,
    )
    report = collect_sse_smoke(
        base_url=str(args.base_url),
        api_prefix=str(args.api_prefix),
        probes=_configured_probes(args),
        headers=headers,
        timeout_seconds=max(0.1, float(args.timeout_seconds)),
        max_bytes=max(128, int(args.max_bytes)),
        require_auth=not bool(args.allow_unauthenticated),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output:
        from pathlib import Path

        output = Path(str(args.output))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    if report["status"] == "auth_missing":
        return 2
    return 0 if report["status"] == "pass" else 1


def collect_sse_smoke(
    *,
    base_url: str,
    api_prefix: str = "",
    probes: Sequence[SseProbe] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    require_auth: bool = True,
    request_fn: RequestFn | None = None,
) -> dict[str, Any]:
    normalized_headers = {
        str(key): str(value)
        for key, value in (headers or {}).items()
        if str(value).strip()
    }
    normalized_headers["Accept"] = "text/event-stream"
    auth_configured = any(key.lower() in {"authorization", "cookie"} for key in normalized_headers)
    if require_auth and not auth_configured:
        return {
            "version": 1,
            "status": "auth_missing",
            "generated_at": datetime.now(UTC).isoformat(),
            "base_url": http_slo_probe._normalized_base_url(base_url),
            "api_prefix": api_prefix,
            "auth_configured": False,
            "error": "SSE smoke sampling requires FIN_OPS_HTTP_SLO_BEARER_TOKEN, FIN_OPS_HTTP_SLO_ADMIN_TOKEN, FIN_OPS_HTTP_SLO_COOKIE, or CLI auth options",
        }
    request = request_fn or _urllib_sse_request
    probe_results = [
        _collect_one(
            probe,
            base_url=base_url,
            api_prefix=api_prefix,
            headers=normalized_headers,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            request_fn=request,
        )
        for probe in (probes or DEFAULT_SSE_PROBES)
    ]
    failed = [item for item in probe_results if item["status"] != "pass"]
    return {
        "version": 1,
        "status": "pass" if not failed else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": http_slo_probe._normalized_base_url(base_url),
        "api_prefix": api_prefix,
        "auth_configured": auth_configured,
        "timeout_seconds": timeout_seconds,
        "summary": {
            "probe_count": len(probe_results),
            "failed_probe_count": len(failed),
            "max_first_event_ms": max((float(item.get("first_event_ms") or 0.0) for item in probe_results), default=0.0),
        },
        "probes": probe_results,
    }


def _collect_one(
    probe: SseProbe,
    *,
    base_url: str,
    api_prefix: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
    max_bytes: int,
    request_fn: RequestFn,
) -> dict[str, Any]:
    url = http_slo_probe.resolve_probe_url(base_url, probe.path, api_prefix=api_prefix)
    started = monotonic()
    try:
        response = request_fn(url, headers, timeout_seconds, max_bytes)
        elapsed_ms = round((monotonic() - started) * 1000, 3)
        content_type = http_slo_probe._header(response.headers, "content-type")
        status_ok = response.status_code in probe.expected_statuses
        html_api_error = (
            http_slo_probe._html_response_error(
                http_slo_probe.HttpProbe(probe.name, probe.path, kind="api", expected_statuses=probe.expected_statuses),
                content_type,
                response.body,
            )
            if status_ok
            else None
        )
        event_names = _event_names(response.body)
        errors = _probe_errors(
            probe,
            response,
            content_type=content_type,
            status_ok=status_ok,
            html_api_error=html_api_error,
            event_names=event_names,
            elapsed_ms=elapsed_ms,
        )
        return {
            "name": probe.name,
            "path": probe.path,
            "url": url,
            "target_ms": probe.target_ms,
            "status": "pass" if not errors else "fail",
            "first_event_ms": elapsed_ms,
            "status_code": response.status_code,
            "response_bytes": len(response.body or b""),
            "content_type": content_type,
            "cache_control": http_slo_probe._header(response.headers, "cache-control"),
            "x_accel_buffering": http_slo_probe._header(response.headers, "x-accel-buffering"),
            "event_names": event_names,
            "errors": errors,
        }
    except Exception as exc:
        return {
            "name": probe.name,
            "path": probe.path,
            "url": url,
            "target_ms": probe.target_ms,
            "status": "fail",
            "first_event_ms": round((monotonic() - started) * 1000, 3),
            "status_code": None,
            "response_bytes": 0,
            "content_type": "",
            "event_names": [],
            "errors": [str(exc) or exc.__class__.__name__],
        }


def _probe_errors(
    probe: SseProbe,
    response: SseProbeResponse,
    *,
    content_type: str,
    status_ok: bool,
    html_api_error: str | None,
    event_names: Sequence[str],
    elapsed_ms: float,
) -> list[str]:
    errors: list[str] = []
    if not status_ok:
        errors.append(f"unexpected_status:{response.status_code}")
        return errors
    if html_api_error:
        errors.append(html_api_error)
        return errors
    if "text/event-stream" not in content_type.lower():
        errors.append("unexpected_content_type")
    if not event_names:
        errors.append("missing_sse_event")
    elif not _matches_expected_event(event_names, probe.expected_event_prefixes):
        errors.append("unexpected_sse_event")
    if elapsed_ms > probe.target_ms:
        errors.append("sse_first_event_slo_miss")
    return errors


def _matches_expected_event(event_names: Sequence[str], expected_prefixes: Sequence[str]) -> bool:
    if not expected_prefixes:
        return True
    return any(
        event_name == expected or event_name.startswith(f"{expected}.")
        for event_name in event_names
        for expected in expected_prefixes
    )


def _event_names(body: bytes) -> list[str]:
    names: list[str] = []
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return names
    for line in text.splitlines():
        if not line.startswith("event:"):
            continue
        name = line.partition(":")[2].strip()
        if name:
            names.append(name)
    return names


def _urllib_sse_request(url: str, headers: Mapping[str, str], timeout_seconds: float, max_bytes: int) -> SseProbeResponse:
    request = Request(url, method="GET", headers=dict(headers))
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - operator-provided URL for SSE smoke.
            return SseProbeResponse(
                status_code=int(response.getcode()),
                headers={key.lower(): value for key, value in response.headers.items()},
                body=_read_until_first_event(response, max_bytes=max_bytes),
            )
    except HTTPError as exc:
        return SseProbeResponse(
            status_code=int(exc.code),
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=exc.read(max_bytes),
        )
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(str(reason) or exc.__class__.__name__) from exc


def _read_until_first_event(response: Any, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < max_bytes:
        chunk = response.read(1)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        joined = b"".join(chunks)
        if b"\n\n" in joined or b"\r\n\r\n" in joined:
            return joined
    return b"".join(chunks)


def _configured_probes(args: argparse.Namespace) -> list[SseProbe]:
    paths = list(args.path or [])
    if not paths:
        return [
            SseProbe(
                probe.name,
                probe.path,
                probe.expected_event_prefixes,
                expected_statuses=probe.expected_statuses,
                target_ms=float(args.target_ms),
            )
            for probe in DEFAULT_SSE_PROBES
        ]
    return [
        SseProbe(
            name=f"sse_probe_{index}",
            path=path,
            expected_event_prefixes=(),
            target_ms=float(args.target_ms),
        )
        for index, path in enumerate(paths, start=1)
    ]


if __name__ == "__main__":
    raise SystemExit(main())
