from __future__ import annotations

import hashlib
from unittest import TestCase

from fin_ops_platform.services.bank_import_dedup_repair_service import (
    BankImportDedupRelationEvidenceError,
    build_bank_import_dedup_repair_plan,
    public_bank_import_dedup_repair_report,
    verify_bank_import_repair_source_files,
)
from fin_ops_platform.services.postgres_repositories.bank_import_dedup_repair import (
    _DELETE_TRANSACTION_SQL,
    _SOURCE_FILE_SQL,
    _TARGET_TRANSACTION_SQL,
    _UPDATE_FILE_SQL,
    apply_bank_import_dedup_repair,
)


def _transaction(
    transaction_pk: str,
    transaction_id: str,
    *,
    batch_pk: str,
    trade_time: str,
    reference: str,
    fingerprint: str,
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


class BankImportDedupRepairServiceTests(TestCase):
    def test_plan_deletes_only_exact_fingerprint_and_reference_duplicate(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_snapshot())

        self.assertEqual(plan["target_count"], 2)
        self.assertEqual(plan["protected_count"], 1)
        self.assertEqual(plan["duplicate_delete_count"], 1)
        self.assertEqual(plan["duplicate_pairs"][0]["delete_transaction_id"], "target-1")
        self.assertEqual(plan["duplicate_pairs"][0]["keep_transaction_id"], "keeper-1")
        self.assertEqual(plan["batch_updates"][0]["after_success_count"], 1)
        self.assertEqual(plan["batch_updates"][0]["after_duplicate_count"], 1)
        row_results = plan["file_updates"][0]["after_raw_payload"]["normalized_payload"]["row_results"]
        self.assertEqual(row_results[0]["decision"], "duplicate_skipped")
        self.assertEqual(row_results[1]["decision"], "created")

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

        plan = build_bank_import_dedup_repair_plan(snapshot)

        self.assertEqual(plan["duplicate_delete_count"], 0)

    def test_plan_keeps_referenced_target_when_unreferenced_candidate_balance_differs(self) -> None:
        snapshot = _snapshot(ambiguous=True)
        snapshot["target_transactions"][0]["balance"] = "1000.00"
        snapshot["protected_transactions"][0]["balance"] = "2000.00"

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

    def test_source_file_verification_is_exact(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_snapshot())
        verify_bank_import_repair_source_files(plan, read_file=lambda _: b"source")
        with self.assertRaisesRegex(ValueError, "checksum changed"):
            verify_bank_import_repair_source_files(plan, read_file=lambda _: b"mutated")

    def test_public_report_separates_recovery_and_idempotence_replays(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_snapshot())
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

    def test_repository_apply_uses_all_compare_and_swap_preconditions(self) -> None:
        plan = build_bank_import_dedup_repair_plan(_snapshot())

        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...]) -> int:
                self.calls.append((sql, params))
                return 1

        connection = Connection()
        apply_bank_import_dedup_repair(connection, plan)

        self.assertEqual(len(connection.calls), 4)
        self.assertIn("decision = 'duplicate_skipped'", connection.calls[0][0])
        self.assertEqual(connection.calls[0][1][0], "Reclassified by bank identity v3 controlled recovery.")
        self.assertIn("status = 'completed'", connection.calls[1][0])
        self.assertIn("status = 'confirmed'", connection.calls[2][0])
        self.assertIn("delete from app.bank_transactions", connection.calls[3][0])
        self.assertEqual(connection.calls[3][1][2], "batch-1")

    def test_repository_uses_durable_file_payload_batch_link(self) -> None:
        self.assertNotIn("file.import_batch_id", _SOURCE_FILE_SQL)
        self.assertNotIn("import_batch_id =", _UPDATE_FILE_SQL)
        self.assertIn("left join app.import_batches", _SOURCE_FILE_SQL)
        self.assertIn("normalized_payload'->>'batch_id'", _SOURCE_FILE_SQL)
        self.assertIn("normalized_payload'->>'preview_batch_id'", _SOURCE_FILE_SQL)
        self.assertIn("file.raw_payload->>'batch_id'", _SOURCE_FILE_SQL)
        self.assertIn("file.raw_payload->>'preview_batch_id'", _SOURCE_FILE_SQL)
        self.assertIn("normalized_payload'->>'batch_id'", _UPDATE_FILE_SQL)
        self.assertIn("raw_payload->>'batch_id'", _UPDATE_FILE_SQL)
        self.assertIn("raw_payload->>'preview_batch_id'", _UPDATE_FILE_SQL)
        self.assertIn("bt.legacy_source_batch_id = any", _TARGET_TRANSACTION_SQL)
        self.assertIn("bt.legacy_source_batch_id = nullif", _DELETE_TRANSACTION_SQL)

    def test_plan_reports_the_exact_missing_authorized_file(self) -> None:
        snapshot = _snapshot()
        snapshot["files"] = []

        with self.assertRaisesRegex(ValueError, r"missing=\[\('session-1', 'file-1'\)\]"):
            build_bank_import_dedup_repair_plan(snapshot)
