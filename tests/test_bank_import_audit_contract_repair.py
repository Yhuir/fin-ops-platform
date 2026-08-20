from __future__ import annotations

import json
import unittest

from fin_ops_platform.services.bank_import_audit_contract_repair_service import (
    MISLINKED_CONFIRM_REASON,
    build_bank_import_audit_contract_repair_plan,
    public_bank_import_audit_contract_repair_report,
)
from fin_ops_platform.services.postgres_repositories.bank_import_audit_contract_repair import (
    apply_bank_import_audit_contract_repair,
)


def _snapshot() -> dict[str, list[dict[str, object]]]:
    file_row = {
        "file_pk": "00000000-0000-0000-0000-000000000001",
        "file_id": "file-1",
        "session_id": "session-1",
        "audit_contract_revision": "import-page-audit.v1",
        "file_object_id": None,
        "stored_file_path": "s3://imports/file-1.xlsx",
        "original_filename": "file-1.xlsx",
        "template_kind": "generic_bank",
        "status": "confirmed",
        "raw_payload": {
            "normalized_payload": {
                "batch_type": "bank_transaction",
                "preview_batch_id": "batch-1",
                "batch_id": "batch-1",
                "content_sha256": "a" * 64,
                "audit": {},
                "session_audit": {},
            }
        },
    }
    return {
        "files": [file_row],
        "batches": [
            {
                "batch_id": "batch-1",
                "batch_type": "bank_transaction",
            }
        ],
        "rows": [
            {
                "row_pk": "00000000-0000-0000-0000-000000000003",
                "row_id": "row-1",
                "batch_id": "batch-1",
                "row_no": 1,
                "source_record_type": "bank_transaction",
                "source_unique_key": "bank-v3:row-1",
                "data_fingerprint": "bank:row-1",
                "decision": "created",
                "decision_reason": "created",
                "linked_object_type": "bank_transaction",
                "linked_object_id": "transaction-1",
                "identity_kind": "stable",
                "account_no": "62220001",
                "trade_time": "2026-07-01 10:00:00",
                "direction": "outflow",
                "amount": "100.00",
                "counterparty_name": "供应商",
                "raw_payload": {
                    "normalized_payload": {
                        "balance": "900.00",
                        "currency": "CNY",
                    }
                },
            }
        ],
        "transactions": [],
        "file_objects": [
            {
                "file_object_id": "00000000-0000-0000-0000-000000000002",
                "storage_uri": "s3://imports/file-1.xlsx",
                "sha256": "a" * 64,
                "size_bytes": 128,
                "migration_status": "verified",
                "tombstoned_at": None,
            }
        ],
    }


class BankImportAuditContractRepairPlanTests(unittest.TestCase):
    def test_plan_links_proven_archive_and_recalculates_registered_counts(self) -> None:
        plan = build_bank_import_audit_contract_repair_plan(
            _snapshot(),
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=0,
        )

        self.assertEqual(plan["formal_file_count"], 1)
        self.assertEqual(plan["session_count"], 1)
        self.assertEqual(
            plan["file_object_link_actions"][0]["after_file_object_id"],
            "00000000-0000-0000-0000-000000000002",
        )
        normalized = plan["payload_update_actions"][0]["after_raw_payload"][
            "normalized_payload"
        ]
        self.assertEqual(normalized["audit"]["original_count"], 1)
        self.assertEqual(normalized["session_audit"]["confirmable_count"], 1)
        report = public_bank_import_audit_contract_repair_report(
            plan,
            mode="dry_run",
            written=False,
        )
        self.assertFalse(report["written"])
        self.assertEqual(len(report["source_fingerprint"]), 64)

    def test_plan_fails_closed_on_ambiguous_archive_uri(self) -> None:
        snapshot = _snapshot()
        snapshot["file_objects"].append(dict(snapshot["file_objects"][0]))

        with self.assertRaisesRegex(ValueError, "exactly one archived object"):
            build_bank_import_audit_contract_repair_plan(
                snapshot,
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=0,
                expected_row_unlink_count=0,
            )

    def test_plan_fails_closed_on_archive_hash_mismatch(self) -> None:
        snapshot = _snapshot()
        snapshot["file_objects"][0]["sha256"] = "b" * 64

        with self.assertRaisesRegex(ValueError, "hash or lifecycle is not proven"):
            build_bank_import_audit_contract_repair_plan(
                snapshot,
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=0,
                expected_row_unlink_count=0,
            )

    def test_plan_requires_exact_action_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "object-link count changed"):
            build_bank_import_audit_contract_repair_plan(
                _snapshot(),
                expected_file_object_link_count=2,
                expected_payload_update_count=1,
                expected_row_relink_count=0,
                expected_row_unlink_count=0,
            )

    def test_plan_relinks_one_uniquely_proven_mislinked_confirm_row(self) -> None:
        snapshot = _mislinked_snapshot()

        plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=1,
            expected_row_unlink_count=0,
        )

        action = plan["row_relink_actions"][0]
        self.assertEqual(action["before_linked_object_id"], "transaction-wrong")
        self.assertEqual(action["after_linked_object_id"], "transaction-correct")
        self.assertEqual(
            action["match_basis"], "data_fingerprint_and_statement_position"
        )
        self.assertEqual(
            action["after_raw_payload"]["normalized_payload"]["linked_object_id"],
            "transaction-correct",
        )

    def test_plan_fails_closed_when_mislinked_row_has_multiple_candidates(self) -> None:
        snapshot = _mislinked_snapshot()
        duplicate_candidate = dict(snapshot["transactions"][1])
        duplicate_candidate["transaction_id"] = "transaction-also-correct"
        snapshot["transactions"].append(duplicate_candidate)

        with self.assertRaisesRegex(ValueError, "candidate_count"):
            build_bank_import_audit_contract_repair_plan(
                snapshot,
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=1,
                expected_row_unlink_count=0,
            )

    def test_plan_uses_unique_strict_position_when_historical_fingerprint_drifted(
        self,
    ) -> None:
        snapshot = _mislinked_snapshot()
        snapshot["transactions"][1]["data_fingerprint"] = "bank:legacy-drift"

        plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=1,
            expected_row_unlink_count=0,
        )

        self.assertEqual(
            plan["row_relink_actions"][0]["match_basis"],
            "unique_statement_position_fallback",
        )

    def test_plan_preserves_nullable_identity_fields_for_compare_and_swap(self) -> None:
        snapshot = _mislinked_snapshot()
        snapshot["rows"][0]["source_unique_key"] = None
        snapshot["rows"][0]["data_fingerprint"] = None

        plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=1,
            expected_row_unlink_count=0,
        )

        action = plan["row_relink_actions"][0]
        self.assertIsNone(action["source_unique_key"])
        self.assertIsNone(action["data_fingerprint"])
        self.assertEqual(action["match_basis"], "unique_statement_position_fallback")

    def test_plan_is_idempotent_after_unique_strict_position_relink(self) -> None:
        snapshot = _mislinked_snapshot()
        snapshot["transactions"][1]["data_fingerprint"] = "bank:legacy-drift"
        first_plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=1,
            expected_row_unlink_count=0,
        )
        snapshot["rows"][0]["linked_object_id"] = first_plan["row_relink_actions"][0][
            "after_linked_object_id"
        ]
        snapshot["rows"][0]["raw_payload"] = first_plan["row_relink_actions"][0][
            "after_raw_payload"
        ]

        second_plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=0,
        )

        self.assertEqual(second_plan["row_relink_actions"], [])

    def test_plan_fails_closed_when_strict_position_fallback_is_ambiguous(
        self,
    ) -> None:
        snapshot = _mislinked_snapshot()
        snapshot["transactions"][1]["data_fingerprint"] = "bank:legacy-drift"
        duplicate_candidate = dict(snapshot["transactions"][1])
        duplicate_candidate["transaction_id"] = "transaction-also-correct"
        duplicate_candidate["data_fingerprint"] = "bank:another-legacy-drift"
        snapshot["transactions"].append(duplicate_candidate)

        with self.assertRaisesRegex(ValueError, "candidate_count"):
            build_bank_import_audit_contract_repair_plan(
                snapshot,
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=1,
                expected_row_unlink_count=0,
            )

    def test_plan_fails_closed_when_strict_statement_evidence_is_missing(self) -> None:
        snapshot = _mislinked_snapshot()
        snapshot["rows"][0]["raw_payload"]["normalized_payload"].pop("balance")

        with self.assertRaisesRegex(ValueError, "candidate_count"):
            build_bank_import_audit_contract_repair_plan(
                snapshot,
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=1,
                expected_row_unlink_count=0,
            )

    def test_plan_fails_closed_when_counterparty_evidence_is_missing(self) -> None:
        snapshot = _mislinked_snapshot()
        snapshot["rows"][0]["counterparty_name"] = None
        snapshot["rows"][0]["raw_payload"]["normalized_payload"].pop(
            "counterparty_name"
        )

        with self.assertRaisesRegex(ValueError, "candidate_count"):
            build_bank_import_audit_contract_repair_plan(
                snapshot,
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=1,
                expected_row_unlink_count=0,
            )

    def test_plan_unlinks_terminal_suspected_duplicate_without_changing_decision(
        self,
    ) -> None:
        snapshot = _suspected_link_snapshot()

        plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=1,
        )

        action = plan["row_unlink_actions"][0]
        self.assertEqual(action["decision"], "suspected_duplicate")
        self.assertEqual(action["decision_reason"], "weak_identity_match")
        self.assertEqual(action["before_batch_type"], "bank_transaction")
        self.assertEqual(action["before_batch_status"], "completed_with_errors")
        self.assertEqual(
            action["before_linked_object_type"], "bank_transaction"
        )
        self.assertEqual(action["before_linked_object_id"], "transaction-candidate")
        self.assertIsNone(action["after_linked_object_type"])
        self.assertIsNone(action["after_linked_object_id"])
        normalized = action["after_raw_payload"]["normalized_payload"]
        self.assertIsNone(normalized["linked_object_type"])
        self.assertIsNone(normalized["linked_object_id"])
        report = public_bank_import_audit_contract_repair_report(
            plan,
            mode="dry_run",
            written=False,
        )
        self.assertEqual(report["row_unlink_count"], 1)
        self.assertEqual(report["row_unlink_rows"][0]["row_id"], "row-suspected")

    def test_plan_requires_exact_suspected_duplicate_unlink_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "row-unlink count changed"):
            build_bank_import_audit_contract_repair_plan(
                _suspected_link_snapshot(),
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=0,
                expected_row_unlink_count=0,
            )

    def test_plan_suspected_duplicate_unlink_is_idempotent(self) -> None:
        snapshot = _suspected_link_snapshot()
        first_plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=1,
        )
        action = first_plan["row_unlink_actions"][0]
        snapshot["rows"][0]["linked_object_type"] = None
        snapshot["rows"][0]["linked_object_id"] = None
        snapshot["rows"][0]["raw_payload"] = action["after_raw_payload"]

        second_plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=0,
        )

        self.assertEqual(second_plan["row_unlink_actions"], [])

    def test_plan_unlinks_suspected_candidate_present_only_in_raw_payload(
        self,
    ) -> None:
        snapshot = _suspected_link_snapshot()
        snapshot["rows"][0]["linked_object_type"] = None
        snapshot["rows"][0]["linked_object_id"] = None

        plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=1,
        )

        action = plan["row_unlink_actions"][0]
        self.assertIsNone(action["before_linked_object_type"])
        self.assertIsNone(action["before_linked_object_id"])
        self.assertEqual(
            action["before_payload_linked_object_type"], "bank_transaction"
        )
        self.assertEqual(
            action["before_payload_linked_object_id"], "transaction-candidate"
        )
        self.assertIsNone(
            action["after_raw_payload"]["normalized_payload"][
                "linked_object_type"
            ]
        )
        self.assertIsNone(
            action["after_raw_payload"]["normalized_payload"]["linked_object_id"]
        )

    def test_plan_fails_closed_when_typed_and_payload_candidate_links_differ(
        self,
    ) -> None:
        snapshot = _suspected_link_snapshot()
        snapshot["rows"][0]["raw_payload"]["normalized_payload"][
            "linked_object_id"
        ] = "transaction-other"

        with self.assertRaisesRegex(
            ValueError, "unsupported partial or non-bank"
        ):
            build_bank_import_audit_contract_repair_plan(
                snapshot,
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=0,
                expected_row_unlink_count=1,
            )

    def test_plan_fingerprint_changes_when_suspected_link_changes(self) -> None:
        snapshot = _suspected_link_snapshot()
        first_plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=1,
        )
        snapshot["rows"][0]["linked_object_id"] = "transaction-other"
        snapshot["rows"][0]["raw_payload"]["normalized_payload"][
            "linked_object_id"
        ] = "transaction-other"

        second_plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=1,
        )

        self.assertNotEqual(
            first_plan["source_fingerprint"], second_plan["source_fingerprint"]
        )

    def test_plan_fails_closed_on_non_bank_suspected_duplicate_link(self) -> None:
        snapshot = _suspected_link_snapshot()
        snapshot["rows"][0]["linked_object_type"] = "invoice"

        with self.assertRaisesRegex(ValueError, "unsupported partial or non-bank"):
            build_bank_import_audit_contract_repair_plan(
                snapshot,
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=0,
                expected_row_unlink_count=1,
            )

    def test_plan_fails_closed_on_non_bank_suspected_duplicate_source_type(
        self,
    ) -> None:
        snapshot = _suspected_link_snapshot()
        snapshot["rows"][0]["source_record_type"] = "invoice"

        with self.assertRaisesRegex(ValueError, "unsupported partial or non-bank"):
            build_bank_import_audit_contract_repair_plan(
                snapshot,
                expected_file_object_link_count=1,
                expected_payload_update_count=1,
                expected_row_relink_count=0,
                expected_row_unlink_count=1,
            )

    def test_plan_does_not_unlink_nonterminal_preview_candidate(self) -> None:
        snapshot = _suspected_link_snapshot()
        snapshot["batches"][0]["status"] = "pending"

        plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=0,
        )

        self.assertEqual(plan["row_unlink_actions"], [])


class BankImportAuditContractRepairRepositoryTests(unittest.TestCase):
    def test_apply_uses_compare_and_swap_for_every_planned_write(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
                self.calls.append((sql, params))
                return 1

        connection = Connection()
        plan = build_bank_import_audit_contract_repair_plan(
            _snapshot(),
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=0,
        )

        result = apply_bank_import_audit_contract_repair(
            connection,
            plan,
            operator_id="system_repair",
        )

        self.assertEqual(
            result,
            {
                "file_object_link_count": 1,
                "payload_update_count": 1,
                "row_relink_count": 0,
                "row_unlink_count": 0,
            },
        )
        self.assertEqual(len(connection.calls), 4)

    def test_apply_rolls_back_via_error_when_compare_and_swap_misses(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.write_calls = 0

            def execute(self, sql: str, _params: tuple[object, ...] = ()) -> int:
                if sql.lstrip().startswith("update app.import_files"):
                    self.write_calls += 1
                    return 0
                return 1

        plan = build_bank_import_audit_contract_repair_plan(
            _snapshot(),
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=0,
        )

        with self.assertRaisesRegex(RuntimeError, "archive link changed"):
            apply_bank_import_audit_contract_repair(
                Connection(),
                plan,
                operator_id="system_repair",
            )

    def test_apply_uses_compare_and_swap_for_proven_row_relink(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
                self.calls.append((sql, params))
                return 1

        connection = Connection()
        plan = build_bank_import_audit_contract_repair_plan(
            _mislinked_snapshot(),
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=1,
            expected_row_unlink_count=0,
        )

        result = apply_bank_import_audit_contract_repair(
            connection,
            plan,
            operator_id="system_repair",
        )

        self.assertEqual(result["row_relink_count"], 1)
        row_write = next(
            params
            for sql, params in connection.calls
            if sql.lstrip().startswith("update app.import_batch_rows")
        )
        self.assertEqual(row_write[0], "transaction-correct")

    def test_apply_passes_nullable_identity_fields_to_compare_and_swap(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
                self.calls.append((sql, params))
                return 1

        snapshot = _mislinked_snapshot()
        snapshot["rows"][0]["source_unique_key"] = None
        snapshot["rows"][0]["data_fingerprint"] = None
        plan = build_bank_import_audit_contract_repair_plan(
            snapshot,
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=1,
            expected_row_unlink_count=0,
        )
        connection = Connection()

        apply_bank_import_audit_contract_repair(
            connection,
            plan,
            operator_id="system_repair",
        )

        row_write = next(
            params
            for sql, params in connection.calls
            if sql.lstrip().startswith("update app.import_batch_rows")
        )
        self.assertIsNone(row_write[6])
        self.assertIsNone(row_write[7])

    def test_apply_rolls_back_when_row_relink_compare_and_swap_misses(self) -> None:
        class Connection:
            def execute(self, sql: str, _params: tuple[object, ...] = ()) -> int:
                if sql.lstrip().startswith("update app.import_batch_rows"):
                    return 0
                return 1

        plan = build_bank_import_audit_contract_repair_plan(
            _mislinked_snapshot(),
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=1,
            expected_row_unlink_count=0,
        )

        with self.assertRaisesRegex(RuntimeError, "canonical link changed"):
            apply_bank_import_audit_contract_repair(
                Connection(),
                plan,
                operator_id="system_repair",
            )

    def test_apply_unlinks_suspected_duplicate_with_full_compare_and_swap(
        self,
    ) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
                self.calls.append((sql, params))
                return 1

        connection = Connection()
        plan = build_bank_import_audit_contract_repair_plan(
            _suspected_link_snapshot(),
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=1,
        )

        result = apply_bank_import_audit_contract_repair(
            connection,
            plan,
            operator_id="system_repair",
        )

        self.assertEqual(result["row_unlink_count"], 1)
        row_sql, row_params = next(
            (sql, params)
            for sql, params in connection.calls
            if "set linked_object_type = null" in sql
        )
        self.assertEqual(row_params[2], "row-suspected")
        self.assertEqual(row_params[3], "batch-1")
        self.assertEqual(row_params[6], "suspected_duplicate")
        self.assertEqual(row_params[7], "weak_identity_match")
        self.assertEqual(row_params[8], "bank_transaction")
        self.assertEqual(row_params[9], "transaction-candidate")
        self.assertIsNone(
            json.loads(row_params[0])["normalized_payload"]["linked_object_id"]
        )
        self.assertEqual(
            row_params[-2:], ("bank_transaction", "completed_with_errors")
        )
        set_clause = row_sql.lower().split("where", 1)[0]
        self.assertNotIn("decision =", set_clause)
        self.assertNotIn("decision_reason =", set_clause)
        self.assertNotIn("suspected_duplicate_count", row_sql.lower())
        self.assertIn("batch.batch_type = %s", row_sql)
        self.assertIn("batch.status = %s", row_sql)

    def test_apply_rolls_back_when_row_unlink_compare_and_swap_misses(self) -> None:
        class Connection:
            def execute(self, sql: str, _params: tuple[object, ...] = ()) -> int:
                if "set linked_object_type = null" in sql:
                    return 0
                return 1

        plan = build_bank_import_audit_contract_repair_plan(
            _suspected_link_snapshot(),
            expected_file_object_link_count=1,
            expected_payload_update_count=1,
            expected_row_relink_count=0,
            expected_row_unlink_count=1,
        )

        with self.assertRaisesRegex(RuntimeError, "link changed after dry-run"):
            apply_bank_import_audit_contract_repair(
                Connection(),
                plan,
                operator_id="system_repair",
            )


def _suspected_link_snapshot() -> dict[str, list[dict[str, object]]]:
    snapshot = _snapshot()
    snapshot["batches"][0]["status"] = "completed_with_errors"
    snapshot["rows"] = [
        {
            "row_pk": "00000000-0000-0000-0000-000000000004",
            "row_id": "row-suspected",
            "batch_id": "batch-1",
            "row_no": 1,
            "source_record_type": "bank_transaction",
            "source_unique_key": "bank-weak:row-1",
            "data_fingerprint": "bank:weak-row-1",
            "decision": "suspected_duplicate",
            "decision_reason": "weak_identity_match",
            "linked_object_type": "bank_transaction",
            "linked_object_id": "transaction-candidate",
            "identity_kind": "weak",
            "account_no": "62220001",
            "trade_time": "2026-07-01 10:00:00",
            "direction": "outflow",
            "amount": "100.00",
            "counterparty_name": "供应商",
            "raw_payload": {
                "normalized_payload": {
                    "balance": "900.00",
                    "currency": "CNY",
                    "linked_object_type": "bank_transaction",
                    "linked_object_id": "transaction-candidate",
                }
            },
        }
    ]
    return snapshot


def _mislinked_snapshot() -> dict[str, list[dict[str, object]]]:
    snapshot = _snapshot()
    snapshot["rows"] = [
        {
            "row_pk": "00000000-0000-0000-0000-000000000003",
            "row_id": "row-mislinked",
            "batch_id": "batch-1",
            "row_no": 1,
            "source_record_type": "bank_transaction",
            "source_unique_key": "bank-v3:fee",
            "data_fingerprint": "bank:fee",
            "decision": "duplicate_skipped",
            "decision_reason": MISLINKED_CONFIRM_REASON,
            "linked_object_type": "bank_transaction",
            "linked_object_id": "transaction-wrong",
            "identity_kind": "stable",
            "account_no": "62220001",
            "trade_time": "2026-07-01 10:00:00",
            "direction": "outflow",
            "amount": "0.90",
            "counterparty_name": "手续费",
            "raw_payload": {
                "normalized_payload": {
                    "account_no": "62220001",
                    "trade_time": "2026-07-01 10:00:00",
                    "txn_direction": "outflow",
                    "amount": "0.90",
                    "balance": "899.10",
                    "currency": "CNY",
                    "counterparty_name": "手续费",
                    "linked_object_id": "transaction-wrong",
                }
            },
        }
    ]
    snapshot["transactions"] = [
        {
            "transaction_id": "transaction-wrong",
            "data_fingerprint": "bank:principal",
            "account_no": "62220001",
            "trade_time": "2026-07-01 10:00:00",
            "txn_direction": "outflow",
            "amount": "2000.00",
            "balance": "900.00",
            "currency": "CNY",
            "counterparty_name_raw": "供应商",
        },
        {
            "transaction_id": "transaction-correct",
            "data_fingerprint": "bank:fee",
            "account_no": "62220001",
            "trade_time": "2026-07-01 10:00:00",
            "txn_direction": "outflow",
            "amount": "0.90",
            "balance": "899.10",
            "currency": "CNY",
            "counterparty_name_raw": "手续费",
        },
    ]
    return snapshot


if __name__ == "__main__":
    unittest.main()
