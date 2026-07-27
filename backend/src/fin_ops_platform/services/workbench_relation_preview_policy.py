from __future__ import annotations


WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS = 20
WORKBENCH_RELATION_PREVIEW_MAX_CONTEXT_ROWS = 100


class WorkbenchRelationPreviewSelectionError(RuntimeError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
