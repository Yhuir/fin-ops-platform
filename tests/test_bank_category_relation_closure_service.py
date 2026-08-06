from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import unittest

from fin_ops_platform.services.bank_category_relation_closure_service import (
    BankCategoryRelationClosureService,
)
from fin_ops_platform.services.workbench_pair_relation_service import (
    WorkbenchPairRelationService,
)


INTEREST_TAG = "custom_interest"


def _relation(*, metadata: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "case_id": "case-interest",
        "status": "active",
        "relation_mode": "manual_confirmed",
        "month_scope": "2026-08",
        "row_ids": ["oa-1", "bank-1"],
        "row_types": ["oa", "bank"],
        "special_metadata": deepcopy(
            metadata
            or {
                "paired_requirement_source": "bank_transaction_paired_policy",
                "paired_requirement_tag_codes": [],
                "paired_requirement_version": 11,
                "requires_oa": True,
                "requires_invoice": True,
                "unrelated": "keep",
            }
        ),
        "amount_check": {"difference": "0.00"},
        "created_by": "tester",
        "created_at": "2026-08-01T00:00:00+08:00",
        "updated_at": "2026-08-01T00:00:00+08:00",
    }


class _Connection:
    def __init__(self) -> None:
        self.transactions = 0

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield object()


class _CategoryWriter:
    def __init__(self, *, changed: bool = True) -> None:
        self.changed = changed
        self.calls: list[dict[str, object]] = []

    def persist_many(self, *, mutations, transaction):
        self.calls.append({"mutations": deepcopy(mutations), "transaction": transaction})
        return {
            "changed": self.changed,
            "affected_months": ["2026-08"],
            "mutation_results": [
                {
                    "changed": self.changed,
                    "transaction_id": "bank-1",
                    "bank_transaction_id": "00000000-0000-0000-0000-000000000001",
                    "affected_months": ["2026-08"],
                }
            ],
        }


class _RelationRepository:
    def __init__(self, relation: dict[str, object], *, fail_save: bool = False) -> None:
        self.relation = deepcopy(relation)
        self.fail_save = fail_save
        self.lock_calls: list[dict[str, object]] = []
        self.saved: list[dict[str, object]] = []

    def acquire_relation_member_locks(self, row_ids, *, row_types=None, case_ids=None):
        self.lock_calls.append(
            {
                "row_ids": list(row_ids or []),
                "row_types": list(row_types or []),
                "case_ids": list(case_ids or []),
            }
        )
        return []

    def load_active_workbench_pair_relations_for_row_ids(self, _row_ids, *, case_ids=None):
        _ = case_ids
        return {"pair_relations": {"case-interest": deepcopy(self.relation)}}

    def load_workbench_pair_relations_for_row_ids(self, _row_ids, *, case_ids=None):
        if case_ids and "case-interest" not in case_ids:
            return {"pair_relations": {}}
        return {"pair_relations": {"case-interest": deepcopy(self.relation)}}

    def save_workbench_pair_relation_delta(self, snapshot, *, changed_case_ids=None):
        if self.fail_save:
            raise RuntimeError("relation save failed")
        self.saved.append(
            {
                "snapshot": deepcopy(snapshot),
                "changed_case_ids": list(changed_case_ids or []),
            }
        )
        relation = snapshot.get("pair_relations", {}).get("case-interest")
        if isinstance(relation, dict):
            self.relation = deepcopy(relation)


class BankCategoryRelationClosureServiceTests(unittest.TestCase):
    def _service(
        self,
        *,
        relation: dict[str, object] | None = None,
        changed: bool = True,
        fail_save: bool = False,
    ):
        connection = _Connection()
        writer = _CategoryWriter(changed=changed)
        repository = _RelationRepository(relation or _relation(), fail_save=fail_save)
        global_pairs = WorkbenchPairRelationService.from_snapshot(
            {"pair_relations": {"case-interest": deepcopy(repository.relation)}}
        )
        category_calls: list[list[str]] = []

        def effective_rows(_transaction, *, settings, transaction_ids):
            self.assertIn("bank_transaction_tags", settings)
            category_calls.append(list(transaction_ids))
            return {
                "bank-1": {
                    "effective_category_code": INTEREST_TAG,
                    "effective_category_source": "manual",
                }
            }

        service = BankCategoryRelationClosureService(
            connection=connection,
            category_writer=writer,
            relation_repository_factory=lambda _transaction: repository,
            effective_category_rows=effective_rows,
            settings_snapshot_provider=lambda _transaction: {
                "bank_transaction_tags": {"version": 3, "definitions": []},
                "paired_policy": {
                    "version": 11,
                    "requirements_by_tag_code": {
                        INTEREST_TAG: {
                            "requires_oa": False,
                            "requires_invoice": False,
                        }
                    },
                },
            },
            relation_delta_publisher=global_pairs.apply_snapshot_delta,
        )
        return service, connection, writer, repository, global_pairs, category_calls

    def test_category_change_atomically_rebinds_requirement_and_publishes_after_commit(self) -> None:
        service, connection, writer, repository, global_pairs, category_calls = self._service()

        result = service.persist(
            transaction_id="bank-1",
            mutation_type="manual_assign",
            record={"category_code": INTEREST_TAG},
            actor_id="alice",
            action="bank_detail_category_manually_assigned",
            metadata={},
        )

        self.assertEqual(connection.transactions, 1)
        self.assertEqual(len(writer.calls), 1)
        self.assertEqual(category_calls, [["bank-1"]])
        self.assertEqual(result["changed_case_ids"], ["case-interest"])
        self.assertEqual(result["updated_relation_count"], 1)
        self.assertNotIn("_relation_snapshot_delta", result)
        self.assertEqual(len(repository.saved), 1)
        metadata = repository.relation["special_metadata"]
        self.assertEqual(metadata["paired_requirement_tag_codes"], [INTEREST_TAG])
        self.assertFalse(metadata["requires_oa"])
        self.assertFalse(metadata["requires_invoice"])
        self.assertEqual(metadata["unrelated"], "keep")
        published = global_pairs.get_active_relation_by_case_id("case-interest")
        self.assertEqual(published["special_metadata"], metadata)
        self.assertEqual(
            global_pairs.list_history()[-1]["operation_type"],
            "bank_category_requirement_rebind",
        )
        self.assertEqual(repository.lock_calls[0]["row_ids"], ["bank-1"])
        self.assertIn("bank-1", repository.lock_calls[1]["row_ids"])
        self.assertEqual(repository.lock_calls[2]["case_ids"], ["case-interest"])

    def test_unchanged_category_short_circuits_before_relation_category_query(self) -> None:
        service, _connection, _writer, repository, _pairs, category_calls = self._service(
            changed=False
        )

        result = service.persist(
            transaction_id="bank-1",
            mutation_type="manual_assign",
            record={"category_code": INTEREST_TAG},
            actor_id="alice",
            action="bank_detail_category_manually_assigned",
            metadata={},
        )

        self.assertFalse(result["changed"])
        self.assertEqual(result["changed_case_ids"], [])
        self.assertEqual(category_calls, [])
        self.assertEqual(repository.saved, [])

    def test_caller_owned_transaction_defers_process_snapshot_until_outer_commit(self) -> None:
        service, _connection, _writer, repository, global_pairs, _calls = self._service()
        before = global_pairs.get_active_relation_by_case_id("case-interest")

        result = service.persist_many(
            mutations=[
                {
                    "transaction_id": "bank-1",
                    "mutation_type": "turnover_update",
                    "record": {"category_code": INTEREST_TAG},
                    "actor_id": "alice",
                    "action": "turnover_bank_transaction_category_updated",
                    "metadata": {},
                }
            ],
            transaction=object(),
        )

        self.assertEqual(
            global_pairs.get_active_relation_by_case_id("case-interest"),
            before,
        )
        self.assertFalse(repository.relation["special_metadata"]["requires_invoice"])
        service.apply_committed_relation_delta(result)
        self.assertFalse(
            global_pairs.get_active_relation_by_case_id("case-interest")["special_metadata"][
                "requires_invoice"
            ]
        )

    def test_relation_failure_does_not_publish_process_snapshot(self) -> None:
        service, _connection, _writer, _repository, global_pairs, _calls = self._service(
            fail_save=True
        )
        before = global_pairs.get_active_relation_by_case_id("case-interest")

        with self.assertRaisesRegex(RuntimeError, "relation save failed"):
            service.persist(
                transaction_id="bank-1",
                mutation_type="manual_assign",
                record={"category_code": INTEREST_TAG},
                actor_id="alice",
                action="bank_detail_category_manually_assigned",
                metadata={},
            )

        self.assertEqual(
            global_pairs.get_active_relation_by_case_id("case-interest"),
            before,
        )


if __name__ == "__main__":
    unittest.main()
