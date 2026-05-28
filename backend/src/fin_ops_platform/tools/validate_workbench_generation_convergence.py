from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _get_json(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - operator-provided URL
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _version(payload: dict[str, Any]) -> str:
    value = (
        payload.get("active_generation_id")
        or payload.get("read_model_version")
        or payload.get("generated_at")
        or "unknown"
    )
    return str(value)


def _summary_counts(payload: dict[str, Any]) -> dict[str, int]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        key: int(summary.get(key) or 0)
        for key in ("oa_count", "bank_count", "invoice_count", "paired_count", "open_count")
    }


def _groups_counts(payload: dict[str, Any]) -> dict[str, int]:
    row_counts = payload.get("row_counts") if isinstance(payload.get("row_counts"), dict) else {}
    return {
        "total": int(payload.get("total") or 0),
        "oa": int(row_counts.get("oa") or 0),
        "bank": int(row_counts.get("bank") or 0),
        "invoice": int(row_counts.get("invoice") or 0),
    }


def validate(args: argparse.Namespace) -> int:
    base_url = str(args.base_url).rstrip("/")
    observations: list[dict[str, Any]] = []
    failures: list[str] = []
    seen_by_version: dict[str, dict[str, Any]] = {}
    for index in range(max(1, int(args.iterations))):
        summary_url = f"{base_url}/api/workbench/summary?{urlencode({'month': args.month})}"
        groups_query = urlencode(
            {
                "month": args.month,
                "zone": args.zone,
                "page": 1,
                "page_size": args.page_size,
                "detail_level": "summary",
            }
        )
        groups_url = f"{base_url}/api/workbench/groups?{groups_query}"
        started_at = time.perf_counter()
        summary_payload = _get_json(summary_url, timeout_seconds=args.timeout_seconds)
        groups_payload = _get_json(groups_url, timeout_seconds=args.timeout_seconds)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
        version = _version(groups_payload) if _version(groups_payload) != "unknown" else _version(summary_payload)
        observation = {
            "iteration": index + 1,
            "version": version,
            "summary_status": summary_payload.get("read_model_status"),
            "groups_status": groups_payload.get("read_model_status"),
            "summary_counts": _summary_counts(summary_payload),
            "groups_counts": _groups_counts(groups_payload),
            "duration_ms": duration_ms,
        }
        observations.append(observation)
        previous = seen_by_version.get(version)
        comparable = {
            "summary_counts": observation["summary_counts"],
            "groups_counts": observation["groups_counts"],
        }
        if previous is not None and comparable != previous:
            failures.append(f"counts changed under version {version}: {previous} -> {comparable}")
        seen_by_version[version] = comparable
        if index + 1 < args.iterations:
            time.sleep(max(float(args.delay_seconds), 0.0))
    output = {
        "status": "fail" if failures else "pass",
        "base_url": base_url,
        "month": args.month,
        "zone": args.zone,
        "observations": observations,
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate workbench read model generation convergence.")
    parser.add_argument("--base-url", required=True, help="API base URL, for example http://localhost:8000")
    parser.add_argument("--month", default="all")
    parser.add_argument("--zone", choices=("open", "paired"), default="paired")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return validate(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
