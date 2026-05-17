#!/usr/bin/env python3
"""Run the P0 platform API runtime shadow gate when staging inputs are ready."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from api_shadow_validate import run_shadow_validation  # noqa: E402
from platform_shadow_preflight import (  # noqa: E402
    DEFAULT_FIXTURE,
    DEFAULT_OUTPUT_DIR,
    PLATFORM_ENDPOINT_IDS,
    PYTHON_SHADOW_AUTH_ENV,
    build_preflight_report,
    redact_sensitive_text,
)


@dataclass(frozen=True)
class HttpProbe:
    name: str
    url: str
    status: str
    http_status: int | None
    error: str | None

    def to_report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": redact_sensitive_text(self.url),
            "status": self.status,
            "http_status": self.http_status,
            "error": redact_sensitive_text(self.error or ""),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-date", help="YYYYMMDD; defaults to current UTC date")
    parser.add_argument("--python-base-url", default=os.environ.get("FIN_OPS_SHADOW_PYTHON_BASE_URL"))
    parser.add_argument("--axum-base-url", default=os.environ.get("FIN_OPS_SHADOW_AXUM_BASE_URL"))
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--skip-python-check", action="store_true")
    parser.add_argument(
        "--before-group-hook",
        default=os.environ.get("FIN_OPS_SHADOW_BEFORE_GROUP_HOOK"),
        help=(
            "Shell command run before each mutating isolation group. Defaults to the bundled "
            "platform_shadow_reseed_hook.py when runtime shadow executes."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_runtime_report(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"p0-platform-runtime-shadow-{report['report_date']}.json"
    md_path = args.output_dir / f"p0-platform-runtime-shadow-{report['report_date']}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {"status": report["status"], "json_path": str(json_path), "markdown_path": str(md_path)},
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "GO" else 2


def build_runtime_report(
    args: argparse.Namespace,
    *,
    preflight_builder: Callable[[argparse.Namespace], dict[str, Any]] = build_preflight_report,
    shadow_runner: Callable[..., dict[str, Any]] = run_shadow_validation,
    http_probe: Callable[[str, str, float], HttpProbe] | None = None,
) -> dict[str, Any]:
    if http_probe is None:
        http_probe = probe_url
    report_date = args.report_date or datetime.now(UTC).strftime("%Y%m%d")
    preflight = preflight_builder(args)
    health_checks = collect_health_checks(args, http_probe=http_probe)
    shadow_report = None

    blocking_reasons = []
    if preflight.get("status") != "GO":
        blocking_reasons.append("preflight_no_go")
    failed_health = [item for item in health_checks if item.status != "GO"]
    if failed_health:
        blocking_reasons.append("shadow_service_health_no_go")

    if not blocking_reasons:
        before_group_hook = runtime_before_group_hook(args)
        shadow_report = shadow_runner(
            python_base_url=args.python_base_url,
            axum_base_url=args.axum_base_url,
            fixture_path=args.fixture,
            output_dir=args.output_dir,
            report_date=report_date,
            timeout=args.timeout,
            include_permission_failures=True,
            endpoint_ids=set(PLATFORM_ENDPOINT_IDS),
            before_group_hook=before_group_hook,
        )
        if shadow_report.get("status") != "GO":
            blocking_reasons.append("runtime_shadow_no_go")

    status = "GO" if not blocking_reasons else "NO_GO"
    return {
        "report": f"p0-platform-runtime-shadow-{report_date}",
        "report_date": report_date,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "scope": "P0 platform API runtime Python-vs-Axum shadow validation for Prompt 04.",
        "platform_endpoint_ids": PLATFORM_ENDPOINT_IDS,
        "python_shadow_auth_environment": PYTHON_SHADOW_AUTH_ENV,
        "preflight_status": preflight.get("status"),
        "preflight_findings": preflight.get("findings") or [],
        "preflight_blocker_summary": preflight.get("blocker_summary") or {},
        "preflight_report": preflight,
        "health_checks": [item.to_report() for item in health_checks],
        "health_blockers": health_blockers(failed_health),
        "blocking_details": blocking_details(
            preflight_findings=preflight.get("findings") or [],
            failed_health=failed_health,
            blocking_reasons=blocking_reasons,
        ),
        "shadow_validation_status": shadow_report.get("status") if shadow_report else "SKIPPED",
        "shadow_validation_report": summarize_shadow_report(shadow_report),
        "blocking_reasons": blocking_reasons,
        "go_standard": {
            "preflight": "GO",
            "python_health": "GO",
            "axum_healthz": "GO",
            "axum_readyz": "GO",
            "runtime_shadow_validation": "GO",
        },
    }


def runtime_before_group_hook(args: argparse.Namespace) -> str:
    configured_hook = str(getattr(args, "before_group_hook", "") or "").strip()
    if configured_hook:
        return configured_hook
    return " ".join(
        [
            shlex.quote(sys.executable),
            shlex.quote(str(TOOLS_DIR / "platform_shadow_reseed_hook.py")),
            "--output-dir",
            shlex.quote(str(args.output_dir)),
            "--report-date",
            shlex.quote(str(args.report_date or datetime.now(UTC).strftime("%Y%m%d"))),
            "--database-url-env",
            shlex.quote(str(args.database_url_env)),
        ]
    )


def health_blockers(failed_health: list[HttpProbe]) -> list[dict[str, Any]]:
    blockers = []
    for probe in failed_health:
        if probe.url.startswith("$"):
            blocker_type = "environment_blocker"
            required_action = "Set the corresponding base URL environment variable and start the shadow service."
        else:
            blocker_type = "environment_blocker"
            required_action = "Start or fix the shadow service until the health endpoint returns a 2xx status."
        blockers.append(
            {
                "code": f"{probe.name.upper()}_NO_GO",
                "severity": "blocking",
                "blocker_type": blocker_type,
                "message": f"{probe.name} failed for {redact_sensitive_text(probe.url)}: {probe.error or probe.http_status}",
                "required_action": required_action,
            }
        )
    return blockers


def blocking_details(
    *,
    preflight_findings: list[dict[str, Any]],
    failed_health: list[HttpProbe],
    blocking_reasons: list[str],
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    if "preflight_no_go" in blocking_reasons:
        details.extend(preflight_findings)
    if "shadow_service_health_no_go" in blocking_reasons:
        details.extend(health_blockers(failed_health))
    return details


def collect_health_checks(
    args: argparse.Namespace,
    *,
    http_probe: Callable[[str, str, float], HttpProbe],
) -> list[HttpProbe]:
    checks = []
    if args.python_base_url:
        checks.append(http_probe("python_health", urljoin(args.python_base_url.rstrip("/") + "/", "health"), args.timeout))
    else:
        checks.append(HttpProbe("python_health", "$FIN_OPS_SHADOW_PYTHON_BASE_URL/health", "NO_GO", None, "python base URL missing"))

    if args.axum_base_url:
        base = args.axum_base_url.rstrip("/") + "/"
        checks.append(http_probe("axum_healthz", urljoin(base, "healthz"), args.timeout))
        checks.append(http_probe("axum_readyz", urljoin(base, "readyz"), args.timeout))
    else:
        checks.append(HttpProbe("axum_healthz", "$FIN_OPS_SHADOW_AXUM_BASE_URL/healthz", "NO_GO", None, "axum base URL missing"))
        checks.append(HttpProbe("axum_readyz", "$FIN_OPS_SHADOW_AXUM_BASE_URL/readyz", "NO_GO", None, "axum base URL missing"))
    return checks


def probe_url(name: str, url: str, timeout: float) -> HttpProbe:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local/staging validation tool
            status = "GO" if 200 <= response.status < 300 else "NO_GO"
            return HttpProbe(name, url, status, response.status, None)
    except HTTPError as error:
        return HttpProbe(name, url, "NO_GO", error.code, error.reason)
    except URLError as error:
        return HttpProbe(name, url, "NO_GO", None, str(error.reason))
    except TimeoutError:
        return HttpProbe(name, url, "NO_GO", None, "timed out")


def summarize_shadow_report(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {"status": "SKIPPED"}
    return {
        "status": report.get("status"),
        "json_path": report.get("json_path"),
        "markdown_path": report.get("markdown_path"),
        "summary": report.get("summary"),
        "filters": report.get("filters"),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['report']}",
        "",
        f"- Status: `{report['status']}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Preflight status: `{report['preflight_status']}`",
        f"- Shadow validation status: `{report['shadow_validation_status']}`",
        f"- Endpoint count: `{len(report['platform_endpoint_ids'])}`",
        "",
        "## Blocking Reasons",
        "",
    ]
    if report["blocking_reasons"]:
        for reason in report["blocking_reasons"]:
            lines.append(f"- `{reason}`")
    else:
        lines.append("- `none`")

    lines.extend(
        [
            "",
            "## Health Checks",
            "",
            "| Check | Status | HTTP | URL | Error |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in report["health_checks"]:
        lines.append(
            "| `{name}` | `{status}` | `{http_status}` | `{url}` | {error} |".format(
                name=markdown_cell(item.get("name")),
                status=markdown_cell(item.get("status")),
                http_status=markdown_cell(item.get("http_status")),
                url=markdown_cell(item.get("url")),
                error=markdown_cell(item.get("error")),
            )
        )

    lines.extend(
        [
            "",
            "## Preflight Findings",
            "",
            "| Code | Severity | Message | Required action |",
            "| --- | --- | --- | --- |",
        ]
    )
    findings = report.get("preflight_findings") or []
    if findings:
        for finding in findings:
            lines.append(
                "| `{code}` | `{severity}` | {message} | {required_action} |".format(
                    code=markdown_cell(finding.get("code")),
                    severity=markdown_cell(finding.get("severity")),
                    message=markdown_cell(finding.get("message")),
                    required_action=markdown_cell(finding.get("required_action")),
                )
            )
    else:
        lines.append("| `NONE` | `none` | No preflight findings. | Run runtime shadow validation. |")

    lines.extend(
        [
            "",
            "## Blocking Details",
            "",
            "| Code | Type | Message | Required action |",
            "| --- | --- | --- | --- |",
        ]
    )
    details = report.get("blocking_details") or []
    if details:
        for item in details:
            lines.append(
                "| `{code}` | `{blocker_type}` | {message} | {required_action} |".format(
                    code=markdown_cell(item.get("code")),
                    blocker_type=markdown_cell(item.get("blocker_type") or "unspecified"),
                    message=markdown_cell(item.get("message")),
                    required_action=markdown_cell(item.get("required_action")),
                )
            )
    else:
        lines.append("| `NONE` | `none` | No runtime blockers. | Shadow validation completed. |")

    lines.extend(
        [
            "",
            "## Shadow Report",
            "",
            "```json",
            json.dumps(report["shadow_validation_report"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def markdown_cell(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", "\\n").replace("|", "\\|").replace("`", "\\`")
    if len(text) > 220:
        text = text[:217] + "..."
    return text


if __name__ == "__main__":
    raise SystemExit(main())
