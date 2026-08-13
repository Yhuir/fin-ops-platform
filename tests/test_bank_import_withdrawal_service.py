from __future__ import annotations

import unittest
from contextlib import contextmanager

from fin_ops_platform.services.bank_import_withdrawal_service import (
    BankImportWithdrawalConflict,
    BankImportWithdrawalService,
)


class FakeWithdrawalRepository:
    def __init__(self) -> None:
        self.transaction_connection = object()
        self.batch = {
            "batch_uuid": "00000000-0000-4000-8000-000000000001",
            "batch_id": "batch-1",
            "batch_type": "bank_transaction",
            "source_name": "bank.xlsx",
            "success_count": 2,
            "updated_count": 0,
            "status": "completed",
        }
        self.transactions = [
            {
                "transaction_uuid": "00000000-0000-4000-8000-000000000011",
                "row_id": "bank-1",
                "txn_month": "2026-08-01",
                "written_off_amount": 0,
            },
            {
                "transaction_uuid": "00000000-0000-4000-8000-000000000012",
                "row_id": "bank-2",
                "txn_month": "2026-08-01",
                "written_off_amount": 0,
            },
        ]
        self.blockers: dict[str, int] = {}
        self.calls: list[tuple[str, object]] = []

    @contextmanager
    def transaction(self):
        self.calls.append(("transaction", "begin"))
        try:
            yield self
        except Exception:
            self.calls.append(("transaction", "rollback"))
            raise
        self.calls.append(("transaction", "commit"))

    def lock_batch(self, batch_id: str):
        self.calls.append(("lock_batch", batch_id))
        return dict(self.batch) if batch_id == self.batch["batch_id"] else None

    def withdrawal_payload(self, _batch: dict[str, object]):
        return {"withdrawn_count": 2} if self.batch["status"] == "withdrawn" else None

    def created_transactions(self, batch_uuid: str, batch_id: str):
        self.calls.append(("created_transactions", (batch_uuid, batch_id)))
        return [dict(row) for row in self.transactions]

    def blocking_references(self, **_kwargs: object):
        self.calls.append(("blocking_references", None))
        return dict(self.blockers)

    def cleanup_removable_state(self, **kwargs: object):
        self.calls.append(("cleanup", kwargs))
        return {"categories": 1, "matching_results": 1}

    def delete_transactions(self, **kwargs: object):
        self.calls.append(("delete", kwargs))
        return len(self.transactions)

    def mark_withdrawn(self, **kwargs: object):
        self.calls.append(("mark_withdrawn", kwargs))

    def append_audit_event(self, **kwargs: object):
        self.calls.append(("audit", kwargs))


class FakeRelationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def remove_rows_from_active_relations(self, **kwargs: object):
        self.calls.append(dict(kwargs))
        return {"changed_case_ids": ["case-1"], "affected_months": ["2026-08"]}


class FakeQueueRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def enqueue_read_model_refreshes_in_transaction(self, **kwargs: object):
        self.calls.append(dict(kwargs))
        return []


class BankImportWithdrawalServiceTests(unittest.TestCase):
    def build_service(self, repository: FakeWithdrawalRepository):
        relation = FakeRelationService()
        queue = FakeQueueRepository()
        service = BankImportWithdrawalService(
            repository=repository,  # type: ignore[arg-type]
            relation_service_for_transaction=lambda transaction: relation,
            queue_repository=queue,
        )
        return service, relation, queue

    def test_withdraw_is_atomic_removes_only_owned_rows_and_refreshes_changed_relation_scope(self) -> None:
        repository = FakeWithdrawalRepository()
        service, relation, queue = self.build_service(repository)

        result = service.withdraw(batch_id="batch-1", actor_id="005", request_id="request-1")

        self.assertEqual(result["withdrawn_count"], 2)
        self.assertFalse(result["idempotent_replay"])
        self.assertEqual(relation.calls[0]["row_ids"], ["bank-1", "bank-2"])
        self.assertEqual(
            relation.calls[0]["cancel_history_operation_type"],
            "cancel_relation_for_withdrawn_bank_import_fact",
        )
        self.assertEqual(queue.calls[0]["refreshes"][0]["scope_key"], "2026-08")
        call_names = [name for name, _ in repository.calls]
        self.assertLess(call_names.index("cleanup"), call_names.index("delete"))
        self.assertLess(call_names.index("delete"), call_names.index("mark_withdrawn"))
        self.assertEqual(call_names[-1], "transaction")
        self.assertEqual(repository.calls[-1][1], "commit")

    def test_blocks_external_business_references_without_mutation(self) -> None:
        repository = FakeWithdrawalRepository()
        repository.blockers = {"oa_pending_relations": 1}
        service, relation, queue = self.build_service(repository)

        with self.assertRaises(BankImportWithdrawalConflict) as raised:
            service.withdraw(batch_id="batch-1", actor_id="005")

        self.assertEqual(raised.exception.blockers, {"oa_pending_relations": 1})
        self.assertEqual(relation.calls, [])
        self.assertEqual(queue.calls, [])
        self.assertNotIn("delete", [name for name, _ in repository.calls])
        self.assertEqual(repository.calls[-1], ("transaction", "rollback"))

    def test_repository_does_not_write_retired_relation_claim_storage(self) -> None:
        from inspect import getsource

        from fin_ops_platform.services.postgres_repositories.bank_import_withdrawal import (
            PostgresBankImportWithdrawalRepository,
        )

        source = getsource(PostgresBankImportWithdrawalRepository.cleanup_removable_state)
        self.assertNotIn("bank_transaction_relation_claims", source)

    def test_repository_uses_current_import_file_batch_binding(self) -> None:
        from inspect import getsource

        from fin_ops_platform.services.postgres_repositories.bank_import_withdrawal import (
            PostgresBankImportWithdrawalRepository,
        )

        source = getsource(PostgresBankImportWithdrawalRepository.mark_withdrawn)
        self.assertNotIn("where import_batch_id", source)
        self.assertIn("raw_payload->'normalized_payload'->>'batch_id'", source)

    def test_rejects_updated_or_partially_owned_batch_and_supports_idempotent_replay(self) -> None:
        repository = FakeWithdrawalRepository()
        service, _, _ = self.build_service(repository)
        repository.batch["updated_count"] = 1
        with self.assertRaisesRegex(BankImportWithdrawalConflict, "更新过既有流水"):
            service.withdraw(batch_id="batch-1", actor_id="005")

        repository.batch["updated_count"] = 0
        repository.transactions.pop()
        with self.assertRaisesRegex(BankImportWithdrawalConflict, "独占创建"):
            service.withdraw(batch_id="batch-1", actor_id="005")

        repository.batch["status"] = "withdrawn"
        replay = service.withdraw(batch_id="batch-1", actor_id="005")
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["withdrawn_count"], 2)


if __name__ == "__main__":
    unittest.main()
