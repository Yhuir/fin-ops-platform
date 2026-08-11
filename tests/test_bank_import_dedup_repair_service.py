from __future__ import annotations

import hashlib
import json
from unittest import TestCase
from unittest.mock import patch

from fin_ops_platform.services.bank_import_dedup_repair_service import (
    BankImportDedupRelationEvidenceError,
    build_bank_import_dedup_repair_plan,
    public_bank_import_dedup_repair_report,
    verify_bank_import_repair_source_files,
    withdraw_bank_import_dedup_workbench_relations,
)
from fin_ops_platform.services.postgres_repositories.bank_import_dedup_repair import (
    _DELETE_TRANSACTION_SQL,
    _SOURCE_FILE_SQL,
    _TARGET_TRANSACTION_SQL,
    apply_bank_import_dedup_repair,
)
from fin_ops_platform.services.workbench_pair_relation_service import (
    WorkbenchPairRelationService,
)


def _transaction(
    transaction_pk: str,
    transaction_id: str,
    *,
    batch_pk: str,
    trade_time: str,
    reference: str,
    fingerprint: str,
    balance: str | None = None,
    currency: str | None = None,
) -> dict[str, object]:
    return {
        "transaction_pk": transaction_pk,
        "transaction_id": transaction_id,
        "batch_pk": batch_pk,
        "legacy_batch_id": "batch-1",
        "account_no": "5300",
        "trade_time": trade_time,
        "txn_direction": "outflow",
        "amount": "496.20",
        "balance": balance,
        "currency": currency,
        "counterparty_name_raw": "樊祖芳",
        "bank_serial_no": reference,
        "account_detail_no": None,
        "enterprise_serial_no": None,
        "voucher_no": None,
        "source_unique_key": f"bank-v2:5300:bank_serial_no:{reference}",
        "data_fingerprint": fingerprint,
        "txn_month": "2026-05",
        "written_off_amount": "0",
        "status": "active",
    }


def _snapshot(*, relation_count: int = 0, ambiguous: bool = False) -> dict[str, object]:
    fingerprint = "bank:5300:2026-05-22 16:10:00:outflow:496.20:樊祖芳"
    file_payload = {
        "normalized_payload": {
            "success_count": 2,
            "duplicate_count": 0,
            "row_results": [
                {"decision": "created", "linked_object_id": "target-1"},
                {"decision": "created", "linked_object_id": "target-2"},
            ],
        }
    }
    targets = [
        _transaction(
            "00000000-0000-0000-0000-000000000001",
            "target-1",
            batch_pk="10000000-0000-0000-0000-000000000001",
            trade_time="2026-05-22 16:10:00",
            reference="REF-1",
            fingerprint=fingerprint,
        ),
        _transaction(
            "00000000-0000-0000-0000-000000000002",
            "target-2",
            batch_pk="10000000-0000-0000-0000-000000000001",
            trade_time="2026-05-22 16:11:00",
            reference="REF-REUSED",
            fingerprint="bank:5300:2026-05-22 16:11:00:outflow:496.20:樊祖芳",
        ),
    ]
    protected = [
        _transaction(
            "00000000-0000-0000-0000-000000000101",
            "keeper-1",
            batch_pk="20000000-0000-0000-0000-000000000001",
            trade_time="2026-05-22 16:10:00",
            reference="REF-1" if not ambiguous else "",
            fingerprint=fingerprint,
        )
    ]
    return {
        "request": {
            "source_sessions": [{"session_id": "session-1", "file_ids": ["file-1"]}],
            "expected_target_count": 2,
            "expected_protected_count": 1,
            "expected_duplicate_delete_count": 1,
            "expected_replay_create_count": 1,
        },
        "files": [
            {
                "file_pk": "30000000-0000-0000-0000-000000000001",
                "file_id": "file-1",
                "session_id": "session-1",
                "status": "confirmed",
                "batch_pk": "10000000-0000-0000-0000-000000000001",
                "batch_id": "batch-1",
                "batch_type": "bank_transaction",
                "batch_status": "completed",
                "stored_file_path": "object://imports/file-1",
                "content_sha256": hashlib.sha256(b"source").hexdigest(),
                "raw_payload": file_payload,
            }
        ],
        "batches": [
            {
                "batch_pk": "10000000-0000-0000-0000-000000000001",
                "status": "completed",
                "success_count": 2,
                "duplicate_count": 0,
                "raw_payload": {"normalized_payload": {"success_count": 2, "duplicate_count": 0}},
            }
        ],
        "target_transactions": targets,
        "protected_transactions": protected,
        "import_rows": [
            {
                "row_pk": "40000000-0000-0000-0000-000000000001",
                "batch_pk": "10000000-0000-0000-0000-000000000001",
                "batch_id": "batch-1",
                "row_no": 1,
                "decision": "created",
                "linked_object_id": "target-1",
                "raw_payload": {"normalized_payload": {"decision": "created", "linked_object_id": "target-1"}},
            },
            {
                "row_pk": "40000000-0000-0000-0000-000000000002",
                "batch_pk": "10000000-0000-0000-0000-000000000001",
                "batch_id": "batch-1",
                "row_no": 2,
                "decision": "created",
                "linked_object_id": "target-2",
                "raw_payload": {"normalized_payload": {"decision": "created", "linked_object_id": "target-2"}},
            },
        ],
        "relation_evidence": [
            {
                "transaction_pk": targets[0]["transaction_pk"],
                "written_off_amount": "0",
                "category_count": relation_count,
            },
            {
                "transaction_pk": targets[1]["transaction_pk"],
                "written_off_amount": "0",
                "category_count": 0,
            },
        ],
    }


def _authorized_category_snapshot() -> dict[str, object]:
    snapshot = _snapshot(relation_count=1)
    snapshot["request"].update(
        {
            "cleanup_related_duplicates": True,
            "expected_category_cleanup_count": 1,
            "expected_workbench_withdraw_count": 0,
            "expected_workbench_transaction_id": None,
        }
    )
    transaction_pk = snapshot["target_transactions"][0]["transaction_pk"]
    snapshot["relation_evidence"][0].update(
        {
            "category_event_count": 1,
            "category_details": [
                {
                    "category_id": "50000000-0000-0000-0000-000000000001",
                    "bank_transaction_id": transaction_pk,
                    "legacy_transaction_id": "target-1",
                    "category": "费用 / 办公",
                    "source": "manual",
                    "confidence": "1.0",
                    "status": "active",
                    "version": 2,
                    "updated_by": "user-1",
                    "updated_at": "2026-08-11T10:00:00+08:00",
                    "raw_payload": {"source": "manual"},
                }
            ],
            "category_event_details": [
                {
                    "event_id": "60000000-0000-0000-0000-000000000001",
                    "category_id": "50000000-0000-0000-0000-000000000001",
                    "bank_transaction_id": transaction_pk,
                    "event_type": "assigned",
                    "actor_id": "user-1",
                    "occurred_at": "2026-08-11T10:00:00+08:00",
                    "payload": {"category": "费用 / 办公"},
                    "raw_payload": {},
                }
            ],
        }
    )
    return snapshot


def _authorized_workbench_snapshot() -> dict[str, object]:
    snapshot = _snapshot()
    snapshot["request"].update(
        {
            "cleanup_related_duplicates": True,
            "expected_category_cleanup_count": 0,
            "expected_workbench_withdraw_count": 1,
            "expected_workbench_transaction_id": "target-1",
        }
    )
    relation = {
        "case_id": "case-1",
        "relation_mode": "manual",
        "status": "active",
        "version": 3,
        "month_scope": "2026-05",
        "row_ids": ["target-1", "invoice-1"],
        "row_types": ["bank", "invoice"],
        "amount_check": {"matched": True},
        "special_metadata": {},
        "created_by": "user-1",
        "created_at": "2026-08-11T10:00:00+08:00",
    }
    snapshot["relation_evidence"][0].update(
        {
            "workbench_pair_count": 1,
            "workbench_relation_details": [
                {**relation, "relation_id": "70000000-0000-0000-0000-000000000001"}
            ],
        }
    )
    snapshot["workbench_snapshot"] = {"pair_relations": {"case-1": relation}}
    snapshot["invoice_relation_members"] = [
        {
            "invoice_pk": "80000000-0000-0000-0000-000000000001",
            "invoice_id": "invoice-1",
            "invoice_type": "input_invoice",
            "invoice_no": "INV-1",
            "total_with_tax": "496.20",
            "status": "active",
        }
    ]
    return snapshot


class BankImportDedupRepairServiceTests(TestCase):
    def test_plan_deletes_only_exact_fingerprint_and_reference_duplicate(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_snapshot())

        self.assertEqual(plan["target_count"], 2)
        self.assertEqual(plan["protected_count"], 1)
        self.assertEqual(plan["duplicate_delete_count"], 1)
        self.assertEqual(plan["duplicate_match_basis_counts"], {"official_reference": 1})
        self.assertEqual(plan["duplicate_pairs"][0]["match_basis"], "official_reference")
        self.assertEqual(plan["duplicate_pairs"][0]["matched_official_references"], ["REF-1"])
        self.assertEqual(plan["duplicate_pairs"][0]["delete_transaction_id"], "target-1")
        self.assertEqual(plan["duplicate_pairs"][0]["keep_transaction_id"], "keeper-1")
        self.assertEqual(plan["batch_updates"][0]["after_success_count"], 1)
        self.assertEqual(plan["batch_updates"][0]["after_duplicate_count"], 1)
        first_update = plan["row_updates"][0]
        self.assertEqual(first_update["after_decision"], "duplicate_skipped")
        self.assertEqual(first_update["after_linked_object_id"], "keeper-1")

    def test_plan_refuses_ambiguous_missing_reference_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            build_bank_import_dedup_repair_plan(_snapshot(ambiguous=True))

    def test_plan_repairs_unique_no_reference_match_with_equal_balance_evidence(self) -> None:
        snapshot = _snapshot(ambiguous=True)
        snapshot["target_transactions"][0]["bank_serial_no"] = None
        snapshot["target_transactions"][0]["balance"] = "48952.41"
        snapshot["protected_transactions"][0]["balance"] = "48952.41"

        plan = build_bank_import_dedup_repair_plan(snapshot)

        self.assertEqual(plan["duplicate_delete_count"], 1)
        self.assertEqual(plan["duplicate_match_basis_counts"], {"balance_currency": 1})

    def test_plan_repairs_unique_statement_position_when_fingerprint_drifted(self) -> None:
        snapshot = _snapshot()
        target = snapshot["target_transactions"][0]
        keeper = snapshot["protected_transactions"][0]
        target.update(
            {
                "data_fingerprint": "bank:new-parser-fingerprint",
                "balance": "48952.410",
                "currency": "人民币元",
            }
        )
        keeper.update(
            {
                "data_fingerprint": "bank:legacy-parser-fingerprint",
                "balance": "48952.41",
                "currency": "CNY",
            }
        )

        plan = build_bank_import_dedup_repair_plan(snapshot)

        self.assertEqual(plan["duplicate_delete_count"], 1)
        self.assertEqual(plan["duplicate_match_basis_counts"], {"statement_position": 1})

    def test_plan_repairs_unique_statement_position_after_legacy_reference_conflict(self) -> None:
        snapshot = _snapshot()
        target = snapshot["target_transactions"][0]
        keeper = snapshot["protected_transactions"][0]
        target.update(
            {
                "bank_serial_no": "NEW-PARSER-REFERENCE",
                "balance": "48952.410",
                "currency": "人民币元",
            }
        )
        keeper.update(
            {
                "bank_serial_no": "LEGACY-PARSER-REFERENCE",
                "balance": "48952.41",
                "currency": "CNY",
            }
        )

        plan = build_bank_import_dedup_repair_plan(snapshot)

        self.assertEqual(plan["duplicate_delete_count"], 1)
        self.assertEqual(plan["duplicate_match_basis_counts"], {"statement_position": 1})

    def test_plan_repairs_unique_statement_position_with_account_suffix_representation(self) -> None:
        snapshot = _snapshot()
        target = snapshot["target_transactions"][0]
        keeper = snapshot["protected_transactions"][0]
        target.update(
            {
                "account_no": "工商银行 6386",
                "bank_serial_no": "NEW-PARSER-REFERENCE",
                "balance": "48952.410",
                "currency": "人民币元",
            }
        )
        keeper.update(
            {
                "account_no": "6222000000006386",
                "bank_serial_no": "LEGACY-PARSER-REFERENCE",
                "balance": "48952.41",
                "currency": "CNY",
            }
        )

        plan = build_bank_import_dedup_repair_plan(snapshot)

        self.assertEqual(plan["duplicate_delete_count"], 1)
        self.assertEqual(
            plan["duplicate_match_basis_counts"],
            {"statement_position_account_suffix": 1},
        )

    def test_plan_does_not_match_two_distinct_full_accounts_with_same_suffix(self) -> None:
        snapshot = _snapshot()
        target = snapshot["target_transactions"][0]
        keeper = snapshot["protected_transactions"][0]
        target.update(
            {
                "account_no": "6222000000006386",
                "bank_serial_no": "NEW-PARSER-REFERENCE",
                "balance": "48952.41",
                "currency": "CNY",
            }
        )
        keeper.update(
            {
                "account_no": "9558800000006386",
                "bank_serial_no": "LEGACY-PARSER-REFERENCE",
                "balance": "48952.41",
                "currency": "CNY",
            }
        )
        snapshot["request"]["expected_duplicate_delete_count"] = 0

        plan = build_bank_import_dedup_repair_plan(snapshot)

        self.assertEqual(plan["duplicate_delete_count"], 0)

    def test_plan_does_not_use_ambiguous_statement_position(self) -> None:
        snapshot = _snapshot()
        target = snapshot["target_transactions"][0]
        keeper = snapshot["protected_transactions"][0]
        target.update(
            {
                "data_fingerprint": "bank:new-parser-fingerprint",
                "balance": "48952.41",
                "currency": "CNY",
            }
        )
        keeper.update(
            {
                "data_fingerprint": "bank:legacy-parser-fingerprint",
                "balance": "48952.41",
                "currency": "CNY",
            }
        )
        second_keeper = dict(keeper)
        second_keeper.update(
            {
                "transaction_pk": "00000000-0000-0000-0000-000000000102",
                "transaction_id": "keeper-2",
            }
        )
        snapshot["protected_transactions"].append(second_keeper)
        snapshot["request"]["expected_protected_count"] = 2

        with self.assertRaisesRegex(ValueError, "expected 1, resolved 0"):
            build_bank_import_dedup_repair_plan(snapshot)

    def test_plan_fails_closed_when_exact_duplicate_delete_count_changes(self) -> None:
        snapshot = _snapshot()
        snapshot["request"]["expected_duplicate_delete_count"] = 0

        with self.assertRaisesRegex(ValueError, r"expected 0, resolved 1") as context:
            build_bank_import_dedup_repair_plan(snapshot)
        self.assertIn("unmatched_details=", str(context.exception))
        self.assertIn('"transaction_id": "target-2"', str(context.exception))

    def test_plan_refuses_no_reference_match_when_balance_differs(self) -> None:
        snapshot = _snapshot(ambiguous=True)
        snapshot["target_transactions"][0]["bank_serial_no"] = None
        snapshot["target_transactions"][0]["balance"] = "48952.41"
        snapshot["protected_transactions"][0]["balance"] = "49448.61"

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            build_bank_import_dedup_repair_plan(snapshot)

    def test_plan_keeps_same_fingerprint_when_official_references_conflict(self) -> None:
        snapshot = _snapshot()
        snapshot["target_transactions"][0]["bank_serial_no"] = "REF-DIFFERENT"
        snapshot["request"]["expected_duplicate_delete_count"] = 0

        plan = build_bank_import_dedup_repair_plan(snapshot)

        self.assertEqual(plan["duplicate_delete_count"], 0)

    def test_plan_keeps_referenced_target_when_unreferenced_candidate_balance_differs(self) -> None:
        snapshot = _snapshot(ambiguous=True)
        snapshot["target_transactions"][0]["balance"] = "1000.00"
        snapshot["protected_transactions"][0]["balance"] = "2000.00"
        snapshot["request"]["expected_duplicate_delete_count"] = 0

        plan = build_bank_import_dedup_repair_plan(snapshot)

        self.assertEqual(plan["duplicate_delete_count"], 0)

    def test_plan_refuses_candidate_with_any_relation(self) -> None:
        with self.assertRaises(BankImportDedupRelationEvidenceError) as context:
            build_bank_import_dedup_repair_plan(_snapshot(relation_count=1))

        self.assertEqual(len(context.exception.candidates), 1)
        candidate = context.exception.candidates[0]
        self.assertEqual(candidate["relation_counts"], {"category_count": 1})
        self.assertEqual(candidate["duplicate_transaction"]["transaction_id"], "target-1")
        self.assertEqual(candidate["keeper_transaction"]["transaction_id"], "keeper-1")
        self.assertEqual(candidate["duplicate_transaction"]["amount"], "496.20")
        self.assertEqual(candidate["keeper_transaction"]["official_references"], ["REF-1"])

    def test_plan_reports_exact_invalid_import_row_ownership(self) -> None:
        snapshot = _snapshot()
        snapshot["import_rows"].append(
            {
                "row_pk": "40000000-0000-0000-0000-000000000099",
                "batch_pk": "10000000-0000-0000-0000-000000000001",
                "batch_id": "batch-1",
                "row_no": 99,
                "decision": "created",
                "linked_object_id": "target-1",
                "raw_payload": {},
            }
        )

        with self.assertRaises(ValueError) as context:
            build_bank_import_dedup_repair_plan(snapshot)
        message = str(context.exception)
        self.assertIn('"transaction_id": "target-1"', message)
        self.assertIn('"row_no": 1', message)
        self.assertIn('"row_no": 99', message)

    def test_plan_redirects_existing_duplicate_reference_without_double_counting(self) -> None:
        snapshot = _snapshot()
        snapshot["batches"][0]["duplicate_count"] = 1
        snapshot["batches"][0]["raw_payload"]["normalized_payload"][
            "duplicate_count"
        ] = 1
        file_payload = snapshot["files"][0]["raw_payload"]["normalized_payload"]
        file_payload["duplicate_count"] = 1
        file_payload["row_results"].append(
            {
                "decision": "duplicate_skipped",
                "decision_reason": "same-file duplicate",
                "linked_object_type": "bank_transaction",
                "linked_object_id": "target-1",
            }
        )
        snapshot["import_rows"].append(
            {
                "row_pk": "40000000-0000-0000-0000-000000000099",
                "batch_pk": "10000000-0000-0000-0000-000000000001",
                "batch_id": "batch-1",
                "row_no": 3,
                "decision": "duplicate_skipped",
                "decision_reason": "same-file duplicate",
                "linked_object_type": "bank_transaction",
                "linked_object_id": "target-1",
                "raw_payload": {
                    "normalized_payload": {
                        "decision": "duplicate_skipped",
                        "decision_reason": "same-file duplicate",
                        "linked_object_type": "bank_transaction",
                        "linked_object_id": "target-1",
                    }
                },
            }
        )

        plan = build_bank_import_dedup_repair_plan(snapshot)

        self.assertEqual(plan["duplicate_delete_count"], 1)
        self.assertEqual(plan["import_row_update_count"], 2)
        self.assertEqual(plan["created_owner_transition_count"], 1)
        self.assertEqual(plan["batch_updates"][0]["after_success_count"], 1)
        self.assertEqual(plan["batch_updates"][0]["after_duplicate_count"], 2)
        reference_update = next(
            update for update in plan["row_updates"] if not update["owner_transition"]
        )
        self.assertEqual(reference_update["after_decision_reason"], "same-file duplicate")
        self.assertEqual(reference_update["after_linked_object_id"], "keeper-1")
        self.assertEqual(
            reference_update["after_raw_payload"]["normalized_payload"]["linked_object_id"],
            "keeper-1",
        )

    def test_plan_fingerprints_immutable_file_preview_payload(self) -> None:
        snapshot = _snapshot()
        before_payload = json.loads(json.dumps(snapshot["files"][0]["raw_payload"]))

        plan = build_bank_import_dedup_repair_plan(snapshot)

        expected_hash = hashlib.sha256(
            json.dumps(
                before_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(plan["source_files"][0]["raw_payload_sha256"], expected_hash)
        self.assertEqual(snapshot["files"][0]["raw_payload"], before_payload)
        self.assertNotIn("file_updates", plan)

    def test_plan_authorizes_exact_duplicate_owned_category_and_event(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_authorized_category_snapshot())

        self.assertEqual(len(plan["category_cleanup_actions"]), 1)
        self.assertEqual(plan["category_cleanup_actions"][0]["transaction_id"], "target-1")
        self.assertEqual(plan["workbench_withdraw_actions"], [])

    def test_plan_refuses_misaligned_duplicate_owned_category_event(self) -> None:
        snapshot = _authorized_category_snapshot()
        snapshot["relation_evidence"][0]["category_event_details"][0]["category_id"] = (
            "50000000-0000-0000-0000-000000000099"
        )

        with self.assertRaises(BankImportDedupRelationEvidenceError):
            build_bank_import_dedup_repair_plan(snapshot)

    def test_plan_authorizes_exact_bank_invoice_workbench_withdraw(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_authorized_workbench_snapshot())

        self.assertEqual(len(plan["workbench_withdraw_actions"]), 1)
        action = plan["workbench_withdraw_actions"][0]
        self.assertEqual(action["case_id"], "case-1")
        self.assertEqual(action["relation_version"], 3)
        self.assertEqual(action["bank_row_id"], "target-1")
        self.assertEqual(action["invoice"]["invoice_no"], "INV-1")
        self.assertEqual(action["preview_contract"]["after_relations"], [])

    def test_plan_refuses_workbench_relation_that_would_restore_history(self) -> None:
        snapshot = _authorized_workbench_snapshot()
        relation = snapshot["workbench_snapshot"]["pair_relations"]["case-1"]
        with patch(
            "fin_ops_platform.services.bank_import_dedup_repair_service."
            "WorkbenchRelationCommandService.preview_withdraw_relation",
            return_value={
                "operation_type": "withdraw_relation",
                "preview_id": "withdraw_relation:preview",
                "can_submit": True,
                "active_relation": {"case_id": "case-1", "version": 3},
                "submit_expected_versions": {"relation:case-1": 3},
                "before_relations": [relation],
                "after_relations": [{**relation, "case_id": "case-prior"}],
            },
        ):
            with self.assertRaisesRegex(ValueError, "without restoring"):
                build_bank_import_dedup_repair_plan(snapshot)

    def test_execute_withdraw_uses_formal_command_and_persists_history(self) -> None:
        snapshot = _authorized_workbench_snapshot()
        plan = build_bank_import_dedup_repair_plan(snapshot)

        class Repository:
            def __init__(self) -> None:
                self.pairs = WorkbenchPairRelationService.from_snapshot(
                    snapshot["workbench_snapshot"]
                )

            def acquire_relation_member_locks(self, *_args, **_kwargs):
                return []

            def load_workbench_pair_relations_for_row_ids(
                self, row_ids, *, case_ids=None
            ):
                return self.pairs.snapshot_for_row_ids(row_ids, case_ids=case_ids)

            def save_workbench_pair_relation_delta(self, delta, *, changed_case_ids):
                self.pairs.apply_snapshot_delta(
                    delta,
                    changed_case_ids=changed_case_ids,
                    replace_history=False,
                )

        repository = Repository()
        with patch(
            "fin_ops_platform.services.bank_import_dedup_repair_service."
            "PostgresWorkbenchRelationRepository",
            return_value=repository,
        ):
            results = withdraw_bank_import_dedup_workbench_relations(
                object(),
                plan,
                operator_id="system_repair",
            )

        self.assertEqual(results[0]["status"], "withdrawn")
        self.assertEqual(
            repository.pairs.snapshot()["pair_relations"]["case-1"]["status"],
            "cancelled",
        )
        self.assertEqual(len(repository.pairs.snapshot()["pair_relation_history"]), 1)

    def test_source_file_verification_is_exact(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_snapshot())
        verify_bank_import_repair_source_files(plan, read_file=lambda _: b"source")
        with self.assertRaisesRegex(ValueError, "checksum changed"):
            verify_bank_import_repair_source_files(plan, read_file=lambda _: b"mutated")

    def test_public_report_separates_recovery_and_idempotence_replays(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_snapshot())
        dry_run_report = public_bank_import_dedup_repair_report(
            plan,
            mode="dry_run",
            written=False,
        )
        report = public_bank_import_dedup_repair_report(
            plan,
            mode="execute",
            written=True,
            replay_results=[{"audit_summary": {"created_count": 1}}],
            idempotence_replay_results=[{"audit_summary": {"created_count": 0}}],
        )

        self.assertEqual(report["replay_results"][0]["audit_summary"]["created_count"], 1)
        self.assertEqual(
            report["idempotence_replay_results"][0]["audit_summary"]["created_count"],
            0,
        )
        self.assertEqual(
            dry_run_report["duplicate_match_basis_counts"],
            {"official_reference": 1},
        )
        self.assertEqual(
            dry_run_report["duplicate_pair_evidence"][0]["delete_transaction_id"],
            "target-1",
        )
        self.assertIsNone(report["duplicate_pair_evidence"])

    def test_repository_apply_uses_all_compare_and_swap_preconditions(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_snapshot())

        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...]) -> int:
                self.calls.append((sql, params))
                return 1

        connection = Connection()
        apply_bank_import_dedup_repair(connection, plan, operator_id="system_repair")

        self.assertEqual(len(connection.calls), 5)
        self.assertIn("fin_ops.correction_reason", connection.calls[0][0])
        self.assertIn("fin_ops.actor_id", connection.calls[1][0])
        self.assertIn("decision = %s", connection.calls[2][0])
        self.assertEqual(connection.calls[2][1][0], "duplicate_skipped")
        self.assertEqual(
            connection.calls[2][1][1],
            "Reclassified by bank identity v3 controlled recovery.",
        )
        self.assertIn("status = 'completed'", connection.calls[3][0])
        self.assertIn("delete from app.bank_transactions", connection.calls[4][0])
        self.assertEqual(connection.calls[4][1][2], "batch-1")

    def test_repository_deletes_exact_category_event_before_category(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_authorized_category_snapshot())

        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...]) -> int:
                self.calls.append((sql, params))
                return 1

        connection = Connection()
        result = apply_bank_import_dedup_repair(
            connection,
            plan,
            operator_id="system_repair",
        )

        self.assertIn("delete from app.bank_transaction_category_events", connection.calls[2][0])
        self.assertIn("event.payload = %s::jsonb", connection.calls[2][0])
        self.assertIn("delete from app.bank_transaction_categories", connection.calls[3][0])
        self.assertIn("category.raw_payload = %s::jsonb", connection.calls[3][0])
        self.assertEqual(result["category_event_delete_count"], 1)
        self.assertEqual(result["category_delete_count"], 1)

    def test_repository_uses_durable_file_payload_batch_link(self) -> None:
        self.assertNotIn("file.import_batch_id", _SOURCE_FILE_SQL)
        self.assertIn("left join app.import_batches", _SOURCE_FILE_SQL)
        self.assertIn("normalized_payload'->>'batch_id'", _SOURCE_FILE_SQL)
        self.assertIn("normalized_payload'->>'preview_batch_id'", _SOURCE_FILE_SQL)
        self.assertIn("file.raw_payload->>'batch_id'", _SOURCE_FILE_SQL)
        self.assertIn("file.raw_payload->>'preview_batch_id'", _SOURCE_FILE_SQL)
        self.assertIn("bt.legacy_source_batch_id = any", _TARGET_TRANSACTION_SQL)
        self.assertIn("bt.legacy_source_batch_id = nullif", _DELETE_TRANSACTION_SQL)

    def test_plan_reports_the_exact_missing_authorized_file(self) -> None:
        snapshot = _snapshot()
        snapshot["files"] = []

        with self.assertRaisesRegex(ValueError, r"missing=\[\('session-1', 'file-1'\)\]"):
            build_bank_import_dedup_repair_plan(snapshot)
