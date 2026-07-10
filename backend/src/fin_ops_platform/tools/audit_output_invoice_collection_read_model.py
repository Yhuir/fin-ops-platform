from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TextIO

from fin_ops_platform.services.postgres_repositories.output_invoice_collection_audit import (
    audit_output_invoice_collection_read_model as _audit_output_invoice_collection_read_model,
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
        tool_name="audit_output_invoice_collection_read_model",
        description=(
            "Read-only audit for the output invoice collection read model against canonical "
            "output invoices and Workbench relation distribution."
        ),
        audit=_audit_output_invoice_collection_read_model,
        connection=connection,
        stdout=stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
