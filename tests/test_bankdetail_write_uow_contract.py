from __future__ import annotations

import importlib
import unittest


class BankdetailWriteUowContractTests(unittest.TestCase):
    """PF-P199 target contracts for Bankdetail / No OA transaction-bound writes.

    These tests intentionally describe the target Unit of Work state before the
    implementation exists. They stay in the default unittest suite as expected
    failures so future slices must turn them green instead of losing the target
    contract.
    """

    def _target_uow_class(self):
        try:
            module = importlib.import_module("fin_ops_platform.services.bankdetail_write_uow")
        except ModuleNotFoundError as exc:
            self.fail(
                "PF-P199 target missing: create "
                "fin_ops_platform.services.bankdetail_write_uow with "
                "BankdetailWriteUnitOfWork before removing expectedFailure."
            )
        uow_class = getattr(module, "BankdetailWriteUnitOfWork", None)
        if uow_class is None:
            self.fail("PF-P199 target missing: BankdetailWriteUnitOfWork.")
        return uow_class

    def test_target_category_expected_version_conflict_does_not_write_dirty_or_outbox(self) -> None:
        uow_class = self._target_uow_class()
        recorder = _RecordingWriter()
        category_port = _ConflictCategoryPort()
        uow = uow_class(category_port=category_port, side_effect_writer=recorder)

        with self.assertRaises(Exception):
            uow.confirm_category(
                transaction_id="txn-001",
                category_code="equipment_purchase",
                expected_version=3,
                actor_id="U001",
            )

        self.assertEqual(recorder.records, [])

    def test_target_category_mutation_commits_facts_audit_and_dirty_outbox_in_one_transaction(self) -> None:
        uow_class = self._target_uow_class()
        recorder = _RecordingWriter()
        category_port = _SuccessfulCategoryPort(affected_months=["2026-05"])
        uow = uow_class(category_port=category_port, side_effect_writer=recorder)

        result = uow.confirm_category(
            transaction_id="txn-001",
            category_code="equipment_purchase",
            expected_version=1,
            actor_id="U001",
        )

        self.assertEqual(result["affected_months"], ["2026-05"])
        self.assertEqual(
            recorder.records,
            [
                {
                    "transaction": "begin",
                    "facts": ["bank_transaction_category"],
                    "audit": ["bank_detail_category_confirmed"],
                    "dirty_scopes": [
                        ("bank_detail", "2026-05"),
                        ("turnover_ledger", "all"),
                    ],
                    "outbox": [
                        "bank_detail.read_model.refresh",
                        "turnover_ledger.read_model.refresh",
                    ],
                    "transaction_end": "commit",
                }
            ],
        )

    def test_target_category_side_effect_failure_rolls_back_facts_and_refresh_requests(self) -> None:
        uow_class = self._target_uow_class()
        recorder = _FailingWriter()
        category_port = _SuccessfulCategoryPort(affected_months=["2026-05"])
        uow = uow_class(category_port=category_port, side_effect_writer=recorder)

        with self.assertRaises(Exception):
            uow.confirm_category(
                transaction_id="txn-001",
                category_code="equipment_purchase",
                expected_version=1,
                actor_id="U001",
            )

        self.assertEqual(category_port.committed_transactions, [])
        self.assertEqual(recorder.records, [{"transaction": "rollback"}])

    def test_target_auto_tag_rules_update_commits_settings_audit_bankdetail_and_turnover_dirty_scopes(self) -> None:
        uow_class = self._target_uow_class()
        recorder = _RecordingWriter()
        settings_port = _SuccessfulSettingsPort(priority_scope_keys=["2026-05", "all"])
        uow = uow_class(settings_port=settings_port, side_effect_writer=recorder)

        result = uow.update_auto_tag_rules(actor_id="U001", payload={"rules": []})

        self.assertEqual(result["new_version"], 2)
        self.assertEqual(
            recorder.records,
            [
                {
                    "transaction": "begin",
                    "facts": ["bank_auto_tag_rules"],
                    "audit": ["bank_auto_tag_rules_changed"],
                    "dirty_scopes": [
                        ("bank_detail", "2026-05"),
                        ("turnover_ledger", "all"),
                    ],
                    "outbox": [
                        "bank_detail.read_model.refresh",
                        "turnover_ledger.read_model.refresh",
                    ],
                    "lifecycle_events": ["bank_auto_tag_rules_changed"],
                    "transaction_end": "commit",
                }
            ],
        )

    def test_target_no_oa_stale_expected_version_does_not_persist_lifecycle_or_refresh(self) -> None:
        uow_class = self._target_uow_class()
        recorder = _RecordingWriter()
        no_oa_port = _StaleNoOaPort()
        uow = uow_class(no_oa_port=no_oa_port, side_effect_writer=recorder)

        with self.assertRaisesRegex(RuntimeError, "no_oa_bank_batch_stale_version"):
            uow.submit_no_oa_batch(
                batch_id="batch-001",
                expected_version=4,
                actor_id="U001",
                note="submit",
            )

        self.assertEqual(recorder.records, [])

    def test_target_no_oa_submit_commits_batch_relation_audit_dirty_and_outbox_in_one_transaction(self) -> None:
        uow_class = self._target_uow_class()
        recorder = _RecordingWriter()
        no_oa_port = _SuccessfulNoOaPort(affected_months=["2026-05"], changed_case_ids=["case-001"])
        uow = uow_class(no_oa_port=no_oa_port, side_effect_writer=recorder)

        result = uow.submit_no_oa_batch(
            batch_id="batch-001",
            expected_version=1,
            actor_id="U001",
            note="submit",
        )

        self.assertEqual(result["changed_case_ids"], ["case-001"])
        self.assertEqual(
            recorder.records,
            [
                {
                    "transaction": "begin",
                    "facts": ["no_oa_bank_batch", "workbench_pair_relation"],
                    "audit": ["no_oa_bank_batch_submit"],
                    "dirty_scopes": [
                        ("no_oa_bank_batch", "all"),
                        ("no_oa_bank_batch", "2026-05"),
                        ("workbench", "case-001"),
                    ],
                    "outbox": [
                        "no_oa_bank_batch.read_model.refresh",
                        "workbench.read_model.refresh",
                    ],
                    "lifecycle_events": ["no_oa_bank_batch_changed"],
                    "transaction_end": "commit",
                }
            ],
        )

    def test_target_no_oa_side_effect_failure_rolls_back_batch_and_pair_relation_facts(self) -> None:
        uow_class = self._target_uow_class()
        recorder = _FailingWriter()
        no_oa_port = _SuccessfulNoOaPort(affected_months=["2026-05"], changed_case_ids=["case-001"])
        uow = uow_class(no_oa_port=no_oa_port, side_effect_writer=recorder)

        with self.assertRaises(Exception):
            uow.withdraw_no_oa_batch(
                batch_id="batch-001",
                expected_version=2,
                actor_id="U001",
                reason="undo",
            )

        self.assertEqual(no_oa_port.committed_batches, [])
        self.assertEqual(no_oa_port.committed_relations, [])
        self.assertEqual(recorder.records, [{"transaction": "rollback"}])


class _RecordingWriter:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def write(self, record: dict[str, object]) -> None:
        self.records.append(dict(record))


class _FailingWriter(_RecordingWriter):
    def write(self, record: dict[str, object]) -> None:
        self.records.append({"transaction": "rollback"})
        raise RuntimeError("side_effect_writer_failed")


class _ConflictCategoryPort:
    committed_transactions: list[str] = []

    def confirm_category(self, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("category_version_conflict")


class _SuccessfulCategoryPort:
    def __init__(self, *, affected_months: list[str]) -> None:
        self.affected_months = list(affected_months)
        self.committed_transactions: list[str] = []

    def confirm_category(self, *, transaction_id: str, **_kwargs: object) -> dict[str, object]:
        return {"transaction_id": transaction_id, "affected_months": list(self.affected_months)}

    def commit(self, *, transaction_id: str) -> None:
        self.committed_transactions.append(transaction_id)

    def rollback(self, *, transaction_id: str) -> None:
        self.committed_transactions = [
            committed for committed in self.committed_transactions if committed != transaction_id
        ]


class _SuccessfulSettingsPort:
    def __init__(self, *, priority_scope_keys: list[str]) -> None:
        self.priority_scope_keys = list(priority_scope_keys)

    def update_auto_tag_rules(self, **_kwargs: object) -> dict[str, object]:
        return {"new_version": 2, "priority_scope_keys": list(self.priority_scope_keys)}


class _StaleNoOaPort:
    committed_batches: list[str] = []
    committed_relations: list[str] = []

    def submit_no_oa_batch(self, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("no_oa_bank_batch_stale_version")


class _SuccessfulNoOaPort:
    def __init__(self, *, affected_months: list[str], changed_case_ids: list[str]) -> None:
        self.affected_months = list(affected_months)
        self.changed_case_ids = list(changed_case_ids)
        self.committed_batches: list[str] = []
        self.committed_relations: list[str] = []

    def submit_no_oa_batch(self, **_kwargs: object) -> dict[str, object]:
        return {
            "affected_months": list(self.affected_months),
            "changed_case_ids": list(self.changed_case_ids),
        }

    def withdraw_no_oa_batch(self, **_kwargs: object) -> dict[str, object]:
        return {
            "affected_months": list(self.affected_months),
            "changed_case_ids": list(self.changed_case_ids),
        }

    def commit(self, *, batch_id: str) -> None:
        self.committed_batches.append(batch_id)
        self.committed_relations.append(batch_id)

    def rollback(self, *, batch_id: str) -> None:
        self.committed_batches = [committed for committed in self.committed_batches if committed != batch_id]
        self.committed_relations = [committed for committed in self.committed_relations if committed != batch_id]


if __name__ == "__main__":
    unittest.main()
