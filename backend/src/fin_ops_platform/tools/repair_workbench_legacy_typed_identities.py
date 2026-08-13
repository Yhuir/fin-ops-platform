from __future__ import annotations

from collections.abc import Sequence
import json
import os
import sys
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.workbench import (
    PostgresWorkbenchRepository,
)


TOOL_NAME = "repair_workbench_legacy_typed_identities"


def main(
    argv: Sequence[str] | None = None,
    *,
    connection: Any | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    if argv:
        raise SystemExit(f"{TOOL_NAME} accepts no arguments")
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    tenant_id = str(os.environ.get("FIN_OPS_TENANT_ID") or "default").strip() or "default"
    owned_connection = connection is None
    active_connection = connection
    try:
        if active_connection is None:
            active_connection = PostgresConnection(PostgresSettings.from_env())
        counts = PostgresWorkbenchRepository(
            active_connection
        ).repair_legacy_workbench_typed_identities(tenant_id=tenant_id)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "tool": TOOL_NAME,
                    "error": "legacy_typed_identity_repair_failed",
                    "exception_type": exc.__class__.__name__,
                },
                sort_keys=True,
            ),
            file=stderr,
        )
        return 1
    finally:
        if owned_connection and active_connection is not None:
            active_connection.close()

    report = {
        "status": "completed",
        "tool": TOOL_NAME,
        "contract_schema": "workbench_typed_identity",
        "contract_version": 1,
        "changed": bool(
            int(counts.get("override_repaired") or 0)
            + int(counts.get("exception_repaired") or 0)
        ),
        "counts": {
            "override_repaired": int(counts.get("override_repaired") or 0),
            "override_unresolved_missing_source": int(
                counts.get("override_unresolved_missing_source") or 0
            ),
            "exception_repaired": int(counts.get("exception_repaired") or 0),
        },
    }
    print(json.dumps(report, sort_keys=True), file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
