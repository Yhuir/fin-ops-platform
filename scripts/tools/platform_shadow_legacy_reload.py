#!/usr/bin/env python3
"""Reload the isolated legacy Python shadow runtime after reseeding its data-dir."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


SENSITIVE_PATTERN = re.compile(r"(?i)((?:password|token|secret|key)=)[^\s&]+")


def main() -> int:
    base_url = os.environ.get("FIN_OPS_SHADOW_PYTHON_BASE_URL", "").strip()
    token = os.environ.get("FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN", "").strip()
    report = {
        "status": "NO_GO",
        "hook": "platform_shadow_legacy_reload",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": "",
    }
    missing = [
        name
        for name, value in (
            ("FIN_OPS_SHADOW_PYTHON_BASE_URL", base_url),
            ("FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN", token),
        )
        if not value
    ]
    if missing:
        report["missing_environment"] = missing
        report["message"] = "legacy Python shadow reload environment is missing"
        print_report(report)
        return 3

    url = urljoin(base_url.rstrip("/") + "/", "__shadow/reload-runtime")
    report["url"] = redact(url)
    request = Request(
        url,
        method="POST",
        headers={"X-Fin-Ops-Shadow-Reload-Token": token},
        data=b"{}",
    )
    try:
        with urlopen(request, timeout=10.0) as response:  # noqa: S310 - local shadow runtime tool
            body = response.read().decode("utf-8", errors="replace")
            report["http_status"] = response.status
            report["response"] = parse_json(body)
            report["status"] = "GO" if 200 <= response.status < 300 else "NO_GO"
            report["message"] = "legacy Python shadow runtime reloaded"
            print_report(report)
            return 0 if report["status"] == "GO" else 4
    except HTTPError as error:
        report["http_status"] = error.code
        report["message"] = str(error.reason)
    except URLError as error:
        report["message"] = str(error.reason)
    except TimeoutError:
        report["message"] = "timed out"
    print_report(report)
    return 4


def parse_json(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return redact(value)


def redact(value: str) -> str:
    return SENSITIVE_PATTERN.sub(lambda match: match.group(1) + "[REDACTED]", value)


def print_report(report: dict[str, object]) -> None:
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
