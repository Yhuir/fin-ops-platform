from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, TextIO

from fin_ops_platform.services.cutover_preflight import redact_secret_text, redact_secret_values
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.runtime_state_policy import (
    BLOCKED_UNKNOWN,
    classify_app_health_alert,
    classify_background_job,
)
from fin_ops_platform.services.shadow_read_psql_store import PsqlShadowReadStore
from fin_ops_platform.services.state_store import ApplicationStateStore, default_data_dir


READ_ONLY_GUARD_ENV = "FIN_OPS_SHADOW_REHEARSAL_READ_ONLY"
RUN_ID_ENV = "FIN_OPS_STAGE15_RUN_ID"
DEFAULT_REPORT_DIR = Path("docs/database-migration/reports")
FORBIDDEN_CLI_FLAGS = {
    "--cutover",
    "--enable-dual-write",
    "--dual-write",
    "--write",
    "--write-all",
    "--execute",
    "--restart-service",
    "--switch-backend",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify production runtime state before controlled mirror-write.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--output", type=Path, default=None, help="Write report artifact to this path.")
    parser.add_argument("--primary-backend", choices=("local_pickle", "mongo_readonly"), default="local_pickle")
    parser.add_argument("--shadow-backend", choices=("local_pickle", "postgres", "postgres_psql_json"), default="postgres")
    parser.add_argument("--psql-command", default=os.environ.get("FIN_OPS_SHADOW_REHEARSAL_PSQL_COMMAND", "psql"))
    parser.add_argument("--postgres-database", default=os.environ.get("FIN_OPS_SHADOW_REHEARSAL_POSTGRES_DATABASE", "fin_ops"))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=10)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    primary_store: Any | None = None,
    shadow_store: Any | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args_list = list(sys.argv[1:] if argv is None else argv)
    forbidden = [arg for arg in args_list if arg.split("=", 1)[0] in FORBIDDEN_CLI_FLAGS]
    if forbidden:
        print(f"ERROR: runtime policy preflight refuses write or cutover flags: {', '.join(forbidden)}", file=stderr)
        return 2

    try:
        args = build_parser().parse_args(args_list)
        _enforce_read_only_guard(args.production or args.primary_backend == "mongo_readonly")
        data_dir = args.data_dir or default_data_dir()
        primary = primary_store or _build_store(args.primary_backend, data_dir=data_dir)
        shadow = shadow_store or _build_store(
            args.shadow_backend,
            data_dir=data_dir,
            psql_command=args.psql_command,
            postgres_database=args.postgres_database,
        )
        report = build_runtime_policy_report(
            primary_store=primary,
            shadow_store=shadow,
            run_id=args.run_id or os.environ.get(RUN_ID_ENV),
            primary_backend=args.primary_backend,
            shadow_backend=args.shadow_backend,
            sample_limit=args.sample_limit,
        )
        report = redact_secret_values(report)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must redact errors.
        print(f"ERROR: {redact_secret_text(str(exc))}", file=stderr)
        return 1

    output = args.output or _default_output(report)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0 if report.get("gate_recommendation") == "PASS" else 1


def build_runtime_policy_report(
    *,
    primary_store: Any,
    shadow_store: Any,
    run_id: str | None = None,
    primary_backend: str | None = None,
    shadow_backend: str | None = None,
    sample_limit: int = 10,
) -> dict[str, Any]:
    if sample_limit <= 0:
        raise ValueError("sample_limit must be positive.")
    background_jobs_primary = _mapping_snapshot(primary_store.load_background_jobs())
    background_jobs_shadow = _mapping_snapshot(shadow_store.load_background_jobs())
    alerts_primary = _alert_records(primary_store.load_app_health_alerts())
    alerts_shadow = _alert_records(shadow_store.load_app_health_alerts())
    domains = {
        "background_jobs": _classify_domain(
            domain="background_jobs",
            primary=background_jobs_primary,
            shadow=background_jobs_shadow,
            classifier=classify_background_job,
            sample_limit=sample_limit,
        ),
        "app_health_alerts": _classify_domain(
            domain="app_health_alerts",
            primary=alerts_primary,
            shadow=alerts_shadow,
            classifier=classify_app_health_alert,
            sample_limit=sample_limit,
        ),
    }
    summary = _summarize_domains(domains)
    gate = "BLOCKED_RUNTIME_POLICY_UNKNOWN" if summary["blocked_unknown_count"] else "PASS"
    return {
        "run_id": run_id or f"stage15-runtime-policy-{_utc_compact()}",
        "generated_at": _utc_now(),
        "redacted": True,
        "primary_backend": primary_backend or str(getattr(primary_store, "storage_backend", "unknown")),
        "shadow_backend": shadow_backend or str(getattr(shadow_store, "storage_backend", "unknown")),
        "domains": domains,
        "summary": summary,
        "gate_recommendation": gate,
    }


def _classify_domain(
    *,
    domain: str,
    primary: Mapping[str, Mapping[str, Any]],
    shadow: Mapping[str, Mapping[str, Any]],
    classifier: Any,
    sample_limit: int,
) -> dict[str, Any]:
    classification_counts: dict[str, int] = {}
    mismatch_counts = {"missing_in_primary": 0, "missing_in_shadow": 0, "different": 0}
    samples: list[dict[str, Any]] = []
    keys = sorted(set(primary) | set(shadow))
    for key in keys:
        present_in_primary = key in primary
        present_in_shadow = key in shadow
        payload = primary.get(key) if present_in_primary else shadow.get(key)
        decision = classifier(payload or {}, present_in_primary=present_in_primary, present_in_shadow=present_in_shadow)
        classification_counts[decision.classification] = classification_counts.get(decision.classification, 0) + 1
        mismatch_kind: str | None = None
        if not present_in_primary:
            mismatch_kind = "missing_in_primary"
        elif not present_in_shadow:
            mismatch_kind = "missing_in_shadow"
        elif _fingerprint(primary[key]) != _fingerprint(shadow[key]):
            mismatch_kind = "different"
        if mismatch_kind:
            mismatch_counts[mismatch_kind] += 1
            if len(samples) < sample_limit:
                samples.append(
                    {
                        "record_key_hash": _hash_text(key),
                        "mismatch_kind": mismatch_kind,
                        "classification": decision.classification,
                        "reason": decision.reason,
                        "status": decision.status,
                        "runtime_type": decision.runtime_type,
                    }
                )
    return {
        "primary_count": len(primary),
        "shadow_count": len(shadow),
        "union_count": len(keys),
        "mismatch_counts": mismatch_counts,
        "classification_counts": classification_counts,
        "blocked_unknown_count": classification_counts.get(BLOCKED_UNKNOWN, 0),
        "samples": samples,
    }


def _summarize_domains(domains: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    classification_counts: dict[str, int] = {}
    mismatch_counts = {"missing_in_primary": 0, "missing_in_shadow": 0, "different": 0}
    for domain in domains.values():
        for classification, count in (domain.get("classification_counts") or {}).items():
            classification_counts[str(classification)] = classification_counts.get(str(classification), 0) + int(count)
        for kind, count in (domain.get("mismatch_counts") or {}).items():
            if kind in mismatch_counts:
                mismatch_counts[kind] += int(count)
    return {
        "domain_count": len(domains),
        "classification_counts": classification_counts,
        "mismatch_counts": mismatch_counts,
        "blocked_unknown_count": classification_counts.get(BLOCKED_UNKNOWN, 0),
    }


def _build_store(
    backend: str,
    *,
    data_dir: Path,
    psql_command: str = "psql",
    postgres_database: str = "fin_ops",
) -> Any:
    if backend == "local_pickle":
        return ApplicationStateStore(data_dir, read_only=True)
    if backend == "mongo_readonly":
        _enforce_read_only_guard(True)
        store = ApplicationStateStore(data_dir, read_only=True)
        if store.storage_backend != "mongo":
            raise RuntimeError("mongo_readonly backend requires app Mongo state settings in data_dir/env.")
        return store
    if backend == "postgres":
        return PostgresStateStore(data_dir=data_dir, connection=PostgresConnection(PostgresSettings.from_env()))
    if backend == "postgres_psql_json":
        return PsqlShadowReadStore(database=postgres_database, psql_command=psql_command)
    raise RuntimeError(f"Unsupported runtime policy backend {backend!r}.")


def _mapping_snapshot(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    return {str(key): dict(item) for key, item in value.items() if isinstance(item, dict)}


def _alert_records(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    records = value.get("records") if isinstance(value.get("records"), dict) else value
    return {str(key): dict(item) for key, item in records.items() if isinstance(item, dict)}


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _enforce_read_only_guard(required: bool) -> None:
    if required and os.environ.get(READ_ONLY_GUARD_ENV) != "1":
        raise RuntimeError(f"runtime policy preflight requires {READ_ONLY_GUARD_ENV}=1.")


def _default_output(report: Mapping[str, Any]) -> Path:
    run_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(report.get("run_id") or "stage15-runtime-policy")).strip("-")
    return DEFAULT_REPORT_DIR / f"{run_id}.stage15.runtime-policy.json"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _utc_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
