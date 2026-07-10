from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TextIO

from fin_ops_platform.services.postgres_repositories.input_invoice_usage_audit import (
    audit_input_invoice_usage_read_model as _audit_input_invoice_usage_read_model,
)
from fin_ops_platform.tools.invoice_read_model_audit_cli import run_invoice_read_model_audit


def main(
    argv: Sequence[str] | None = None,
    *,
    connection: Any | None = None,
    stdout: TextIO | None = None,
) -> int:
    return run_invoice_read_model_audit(
        argv,
        tool_name="audit_input_invoice_usage_read_model",
        description=(
            "Read-only audit for the input invoice usage read model against canonical "
            "input invoices and Workbench relation distribution."
        ),
        audit=_audit_input_invoice_usage_read_model,
        connection=connection,
        stdout=stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
