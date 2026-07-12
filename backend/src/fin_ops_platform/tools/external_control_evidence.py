from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from fin_ops_platform.services.external_control_evidence import ExternalControlEvidenceService
from fin_ops_platform.services.postgres_connection import PostgresConfigurationError, PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.external_control_evidence import (
    PostgresExternalControlEvidenceRepository,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and register versioned external control evidence manifests.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a manifest and source artifact without DB writes.")
    _add_manifest_arguments(validate)

    register = subparsers.add_parser("register", help="Dry-run or register one immutable evidence manifest.")
    _add_manifest_arguments(register)
    register.add_argument("--actor", required=True)
    register.add_argument("--reason", required=True)
    register_mode = register.add_mutually_exclusive_group(required=True)
    register_mode.add_argument("--dry-run", action="store_true")
    register_mode.add_argument("--apply", action="store_true")

    revoke = subparsers.add_parser("revoke", help="Dry-run or revoke one evidence version.")
    revoke.add_argument("--evidence-id", required=True)
    revoke.add_argument("--actor", required=True)
    revoke.add_argument("--reason", required=True)
    revoke_mode = revoke.add_mutually_exclusive_group(required=True)
    revoke_mode.add_argument("--dry-run", action="store_true")
    revoke_mode.add_argument("--apply", action="store_true")

    inspect = subparsers.add_parser("inspect", help="List evidence headers without item payloads.")
    inspect.add_argument("--tenant-id", default="default")
    inspect.add_argument("--domain", choices=("bank", "oa", "invoice", "etc"))
    return parser


def _add_manifest_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    connection_factory: Any = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"validate", "register"}:
            payload = _load_manifest(args.manifest)
            _verify_artifact(payload, args.artifact)
            manifest = ExternalControlEvidenceService().validate_manifest(payload)
            if args.command == "validate" or args.dry_run:
                _print(stdout, {"status": "validated", "write_applied": False, "manifest": manifest.safe_payload()})
                return 0
            repository = PostgresExternalControlEvidenceRepository(_connection(connection_factory))
            result = ExternalControlEvidenceService(repository).register(payload, actor=args.actor, reason=args.reason)
            _print(stdout, {"status": "registered", "write_applied": True, "result": result})
            return 0

        repository = PostgresExternalControlEvidenceRepository(_connection(connection_factory))
        service = ExternalControlEvidenceService(repository)
        if args.command == "inspect":
            _print(
                stdout,
                {"status": "ok", "write_applied": False, "evidence": service.inspect(tenant_id=args.tenant_id, domain=args.domain)},
            )
            return 0
        if args.command == "revoke":
            if args.dry_run:
                _print(
                    stdout,
                    {
                        "status": "planned",
                        "write_applied": False,
                        "evidence_id": args.evidence_id,
                        "actor": args.actor,
                        "reason": args.reason,
                    },
                )
                return 0
            result = service.revoke(args.evidence_id, actor=args.actor, reason=args.reason)
            _print(stdout, {"status": "revoked", "write_applied": True, "result": result})
            return 0
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        _print(stderr, {"status": "input_error", "error": type(exc).__name__, "message": str(exc)})
        return 2
    except PostgresConfigurationError as exc:
        _print(
            stderr,
            {
                "status": "configuration_missing",
                "error": "database_url_required",
                "message": str(exc),
                "required_env": ["FIN_OPS_POSTGRES_DATABASE_URL", "DATABASE_URL"],
            },
        )
        return 2
    _print(stderr, {"status": "input_error", "message": f"unsupported command: {args.command}"})
    return 2


def _connection(connection_factory: Any) -> Any:
    if connection_factory is not None:
        return connection_factory()
    return PostgresConnection(PostgresSettings.from_env())


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("external evidence manifest must be a JSON object")
    return payload


def _verify_artifact(payload: dict[str, Any], path: Path) -> None:
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("artifact must be an object")
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size_bytes += len(chunk)
    if digest.hexdigest() != str(artifact.get("sha256") or "").strip().lower() or size_bytes != artifact.get("size_bytes"):
        raise ValueError("source artifact hash/size does not match manifest")


def _print(stream: TextIO, payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stream)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
