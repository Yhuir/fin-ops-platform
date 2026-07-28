from __future__ import annotations


WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION = "2026-07-28-pane-collapse-v10"
WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION = (
    "workbench_sql_projection.composed_active_month_shards.pane_collapse.v10"
)
WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS = 20
WORKBENCH_RELATION_PREVIEW_MAX_CONTEXT_ROWS = 100


class WorkbenchReadModelVersionConflictError(RuntimeError):
    def __init__(self, *, expected: str, current: str | None) -> None:
        super().__init__("Workbench read model changed after the list was loaded.")
        self.expected = expected
        self.current = current


class WorkbenchRelationPreviewSelectionError(RuntimeError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
