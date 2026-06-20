from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
import sys
from typing import Mapping, Sequence, TextIO


def _configured(environ: Mapping[str, str], name: str) -> bool:
    return bool(str(environ.get(name, "")).strip())


def _status(*, ready: bool) -> str:
    return "ready" if ready else "external_input_required"


def _missing(required: Sequence[str], environ: Mapping[str, str]) -> list[str]:
    return [name for name in required if not _configured(environ, name)]


def build_report(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    environ = environ or os.environ
    e2e_admin_ready = _configured(environ, "FIN_OPS_E2E_ADMIN_TOKEN")
    e2e_route_shell_ready = _configured(environ, "FIN_OPS_E2E_OA_TOKEN")
    http_user_ready = any(
        _configured(environ, name)
        for name in ("FIN_OPS_HTTP_SLO_BEARER_TOKEN", "FIN_OPS_HTTP_SLO_ADMIN_TOKEN", "FIN_OPS_HTTP_SLO_COOKIE")
    )
    http_admin_ready = any(_configured(environ, name) for name in ("FIN_OPS_HTTP_SLO_ADMIN_TOKEN", "FIN_OPS_HTTP_SLO_COOKIE"))
    postgres_ready = any(_configured(environ, name) for name in ("FIN_OPS_POSTGRES_DATABASE_URL", "DATABASE_URL", "FIN_OPS_TEST_DATABASE_URL"))
    write_scenario_ready = _configured(environ, "FIN_OPS_WRITE_E2E_SCENARIO")
    write_approval_ready = _configured(environ, "FIN_OPS_WRITE_E2E_APPROVAL_TICKET")
    write_apply_ready = http_user_ready and postgres_ready and write_scenario_ready and write_approval_ready

    gates = {
        "production_route_shell_browser": {
            "status": _status(ready=e2e_route_shell_ready),
            "required_env": ["FIN_OPS_E2E_OA_TOKEN"],
            "missing_env": _missing(["FIN_OPS_E2E_OA_TOKEN"], environ),
            "secret_values_redacted": True,
        },
        "production_admin_app_health_browser": {
            "status": _status(ready=e2e_admin_ready),
            "required_env": ["FIN_OPS_E2E_ADMIN_TOKEN"],
            "missing_env": _missing(["FIN_OPS_E2E_ADMIN_TOKEN"], environ),
            "secret_values_redacted": True,
        },
        "authenticated_http_slo_user_scope": {
            "status": _status(ready=http_user_ready),
            "required_any_env": ["FIN_OPS_HTTP_SLO_BEARER_TOKEN", "FIN_OPS_HTTP_SLO_ADMIN_TOKEN", "FIN_OPS_HTTP_SLO_COOKIE"],
            "missing_any_env": [] if http_user_ready else ["FIN_OPS_HTTP_SLO_BEARER_TOKEN", "FIN_OPS_HTTP_SLO_ADMIN_TOKEN", "FIN_OPS_HTTP_SLO_COOKIE"],
            "secret_values_redacted": True,
        },
        "authenticated_http_slo_admin_scope": {
            "status": _status(ready=http_admin_ready),
            "required_any_env": ["FIN_OPS_HTTP_SLO_ADMIN_TOKEN", "FIN_OPS_HTTP_SLO_COOKIE"],
            "missing_any_env": [] if http_admin_ready else ["FIN_OPS_HTTP_SLO_ADMIN_TOKEN", "FIN_OPS_HTTP_SLO_COOKIE"],
            "notes": ["A configured cookie/token still must prove can_admin_access via /api/session/me or the admin dashboard probe."],
            "secret_values_redacted": True,
        },
        "write_operation_apply": {
            "status": _status(ready=write_apply_ready),
            "required_env": ["FIN_OPS_WRITE_E2E_SCENARIO", "FIN_OPS_WRITE_E2E_APPROVAL_TICKET"],
            "required_any_auth_env": ["FIN_OPS_HTTP_SLO_BEARER_TOKEN", "FIN_OPS_HTTP_SLO_ADMIN_TOKEN", "FIN_OPS_HTTP_SLO_COOKIE"],
            "required_any_postgres_env": ["FIN_OPS_POSTGRES_DATABASE_URL", "DATABASE_URL", "FIN_OPS_TEST_DATABASE_URL"],
            "missing_env": _missing(["FIN_OPS_WRITE_E2E_SCENARIO", "FIN_OPS_WRITE_E2E_APPROVAL_TICKET"], environ),
            "missing_auth_env": [] if http_user_ready else ["FIN_OPS_HTTP_SLO_BEARER_TOKEN", "FIN_OPS_HTTP_SLO_ADMIN_TOKEN", "FIN_OPS_HTTP_SLO_COOKIE"],
            "missing_postgres_env": [] if postgres_ready else ["FIN_OPS_POSTGRES_DATABASE_URL", "DATABASE_URL", "FIN_OPS_TEST_DATABASE_URL"],
            "notes": ["Never run production --apply without an approved, isolated, reversible scenario."],
            "secret_values_redacted": True,
        },
    }
    ready_count = sum(1 for gate in gates.values() if gate["status"] == "ready")
    return {
        "version": 1,
        "status": "pass" if ready_count == len(gates) else "external_input_required",
        "generated_at": datetime.now(UTC).isoformat(),
        "ready_gate_count": ready_count,
        "gate_count": len(gates),
        "gates": gates,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report whether production-only external E2E gates have the required local inputs.")
    parser.add_argument("--require-ready", action="store_true", help="Exit 2 when any external gate is missing credentials or approval inputs.")
    parser.add_argument("--json", action="store_true", help="Print JSON. This is the default output shape.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None, environ: Mapping[str, str] | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    report = build_report(environ)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    if args.require_ready and report["status"] != "pass":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
