from __future__ import annotations

from fin_ops_platform.services.workbench_relation_preview_policy import (
    WORKBENCH_RELATION_PREVIEW_MAX_CONTEXT_ROWS,
    WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS,
    WorkbenchRelationPreviewSelectionError,
)

__all__ = [
    "WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION",
    "WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION",
    "WORKBENCH_RELATION_PREVIEW_MAX_CONTEXT_ROWS",
    "WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS",
    "WorkbenchReadModelVersionConflictError",
    "WorkbenchRelationPreviewSelectionError",
]


WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION = "2026-07-25-canonical-etc-proof-v7"
WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION = (
    "workbench_sql_projection.composed_active_month_shards.canonical_etc_proof.v7"
)


class WorkbenchReadModelVersionConflictError(RuntimeError):
    def __init__(self, *, expected: str, current: str | None) -> None:
        super().__init__("Workbench read model changed after the list was loaded.")
        self.expected = expected
        self.current = current
