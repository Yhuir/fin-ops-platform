from __future__ import annotations

from collections.abc import Callable, Sequence
import json
import os
import sys
from typing import Any, TextIO


TOOL_NAME = "workbench_direct_application_bootstrap_probe"


def main(
    argv: Sequence[str] | None = None,
    *,
    application_factory: Callable[..., Any] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    if argv:
        raise SystemExit(f"{TOOL_NAME} accepts no arguments")
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    application = None
    previous_pgoptions = os.environ.get("PGOPTIONS")
    try:
        if str(os.environ.get("FIN_OPS_APP_STORAGE_BACKEND") or "").strip() != "postgres":
            raise RuntimeError("PostgreSQL storage mode is required.")
        existing_pgoptions = str(os.environ.get("PGOPTIONS") or "").strip()
        os.environ["PGOPTIONS"] = " ".join(
            value
            for value in (existing_pgoptions, "-c default_transaction_read_only=on")
            if value
        )
        if application_factory is None:
            from fin_ops_platform.app.application_factory import create_application

            application_factory = create_application
        application = application_factory(bootstrap_mode="production")
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "tool": TOOL_NAME,
                    "error": "candidate_application_bootstrap_failed",
                    "exception_type": exc.__class__.__name__,
                },
                sort_keys=True,
            ),
            file=stderr,
        )
        return 1
    finally:
        if application is not None:
            close = getattr(application, "close", None)
            if callable(close):
                close()
        if previous_pgoptions is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = previous_pgoptions

    print(
        json.dumps(
            {
                "status": "passed",
                "tool": TOOL_NAME,
                "read_only": True,
            },
            sort_keys=True,
        ),
        file=stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
