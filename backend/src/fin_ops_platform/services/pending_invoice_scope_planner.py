from __future__ import annotations

import re
from typing import Any

from fin_ops_platform.services.read_model_write_targets import normalized_scope_keys


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def pending_invoice_read_model_scope_keys_for_import_state(*scope_key_groups: Any) -> list[str]:
    month_scope_keys: list[str] = []
    for scope_key_group in scope_key_groups:
        for scope_key in normalized_scope_keys(scope_key_group):
            if MONTH_RE.match(scope_key) and scope_key not in month_scope_keys:
                month_scope_keys.append(scope_key)
    if not month_scope_keys:
        return ["expense:all", "income:all", "income:cash_income"]
    return [
        scoped_key
        for month in month_scope_keys
        for scoped_key in (
            f"expense:all:{month}",
            f"income:all:{month}",
            f"income:cash_income:{month}",
        )
    ]
