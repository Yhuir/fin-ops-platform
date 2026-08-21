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

    def test_confirm_maps_immutable_attachment_member_drop_to_relation_conflict(self) -> None:
        service = command_service()
        service.confirm_relation(
            case_id="CASE-OA-ATTACHMENT",
            row_ids=["oa-exp-2444", "inv_imported_0956"],
            row_types=["oa", "invoice"],
            relation_mode="manual_confirmed",
            actor_id="system:workbench-matching",
            special_metadata={
                "oa_attachment_bindings": [
                    {
                        "parent_oa_row_id": "oa-exp-2444",
                        "invoice_row_ids": ["inv_imported_0956"],
                    }
                ],
                "immutable_oa_attachment_binding": True,
                "contains_immutable_oa_attachment_binding": True,
            },
        )

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.confirm_relation(
                case_id="CASE-MANUAL-INVALID",
                row_ids=["oa-exp-2444", "bank-140"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                actor_id="finance",
                replace_existing=True,
            )

        self.assertEqual(
            context.exception.error_code,
            "workbench_relation_immutable_oa_attachment_binding",
        )

    def test_large_relation_confirm_and_withdraw_keep_all_members_and_idempotency(self) -> None:
        service = command_service()
        row_ids = [
            "oa-large-1",
            "bank-large-1",
            *[f"invoice-large-{index}" for index in range(98)],
        ]
        row_types = ["oa", "bank", *(["invoice"] * 98)]
        confirm_kwargs = {
            "case_id": "case-large",
            "row_ids": row_ids,
            "row_types": row_types,
            "relation_mode": "manual_confirmed",
            "actor_id": "tester",
            "month_scope": "2026-05",
            "idempotency_key": "confirm:case-large",
        }

        confirmed = service.confirm_relation(**confirm_kwargs)
        confirm_replay = service.confirm_relation(**confirm_kwargs)
        preview = service.preview_withdraw_relation(
            row_ids=row_ids,
            row_types=row_types,
            month_scope="2026-05",
        )
        withdraw_kwargs = {
            "case_id": "case-large",
            "actor_id": "tester",
            "row_ids": row_ids,
            "row_types": row_types,
            "idempotency_key": "withdraw:case-large",
            "preview_id": preview["preview_id"],
            "operation_type": preview["operation_type"],
            "expected_versions": preview["submit_expected_versions"],
        }
        withdrawn = service.withdraw_relation(**withdraw_kwargs)
        withdraw_replay = service.withdraw_relation(**withdraw_kwargs)

        self.assertEqual(confirmed["relation"]["row_ids"], row_ids)
        self.assertEqual(confirmed["relation"]["row_types"], row_types)
        self.assertEqual(confirm_replay["relation"], confirmed["relation"])
        self.assertTrue(confirm_replay["idempotent_replay"])
        self.assertEqual(preview["before_relations"][0]["row_ids"], row_ids)
        self.assertEqual(withdrawn["affected_row_ids"], row_ids)
        self.assertEqual(withdraw_replay["affected_row_ids"], withdrawn["affected_row_ids"])
        self.assertTrue(withdraw_replay["idempotent_replay"])
        self.assertEqual(service.active_relations_for_row_ids(row_ids), [])


if __name__ == "__main__":
    unittest.main()
