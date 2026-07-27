from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.bank_batch_application_service import (
    canonical_snapshot_version,
)


class WorkbenchRelationSourceVersionProvider:
    def __init__(self, relation_snapshot_provider: Callable[[], Any]) -> None:
        self._relation_snapshot_provider = relation_snapshot_provider

    def pair_relation_snapshot_version(self) -> str:
        return canonical_snapshot_version(self._relation_snapshot_provider())
