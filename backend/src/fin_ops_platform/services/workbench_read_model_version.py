from __future__ import annotations


WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION = "2026-07-14-formal-relation-partition-v1"
WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION = (
    "workbench_sql_projection.composed_active_month_shards.formal_relation_partition.v1"
)


class WorkbenchReadModelVersionConflictError(RuntimeError):
    def __init__(self, *, expected: str, current: str | None) -> None:
        super().__init__("Workbench read model changed after the list was loaded.")
        self.expected = expected
        self.current = current
