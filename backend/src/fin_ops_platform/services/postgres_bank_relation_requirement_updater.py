from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.workbench_relation import (
    PostgresWorkbenchRelationRepository,
)
from fin_ops_platform.services.workbench_pair_relation_service import (
    WorkbenchPairRelationService,
)
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandService,
)


class PostgresBankRelationRequirementUpdater:
    """Run one formal relation metadata command in its own PostgreSQL transaction."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        with self._connection.transaction() as transaction:
            repository = WorkbenchRelationCommandRepositoryAdapter(
                pair_relation_service=WorkbenchPairRelationService(),
                repository=PostgresWorkbenchRelationRepository(transaction),
                save_repository=True,
            )
            return WorkbenchRelationCommandService(
                relation_repository=repository,
            ).update_relation_metadata_for_case_id(**kwargs)
