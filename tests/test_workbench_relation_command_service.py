from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandError,
    WorkbenchRelationCommandService,
)


def command_service() -> WorkbenchRelationCommandService:
    pair_service = WorkbenchPairRelationService()
    return WorkbenchRelationCommandService(
        relation_repository=WorkbenchRelationCommandRepositoryAdapter(
            pair_relation_service=pair_service,
            save_repository=False,
        )
    )


class WorkbenchRelationCommandServiceTests(unittest.TestCase):
    def test_confirm_and_query_use_canonical_relation_state(self) -> None:
        service = command_service()
        result = service.confirm_relation(
            case_id="case-direct",
            row_ids=["bank-1", "invoice-1"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            actor_id="tester",
            month_scope="2026-05",
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertNotIn("read_model_status", result)
        self.assertEqual(
            [relation["case_id"] for relation in service.active_relations_for_row_ids(["bank-1"])],
            ["case-direct"],
        )

    def test_conflicting_active_relation_fails_without_freshness_gate(self) -> None:
        service = command_service()
        service.confirm_relation(
            case_id="case-one",
            row_ids=["bank-1", "invoice-1"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            actor_id="tester",
        )

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.confirm_relation(
                case_id="case-two",
                row_ids=["bank-1", "invoice-2"],
                row_types=["bank", "invoice"],
                relation_mode="manual_confirmed",
                actor_id="tester",
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_active_row_conflict")


if __name__ == "__main__":
    unittest.main()
