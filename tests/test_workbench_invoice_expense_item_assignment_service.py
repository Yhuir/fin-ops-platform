from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.invoice_expense_item_links import (
    InvoiceSourceLinksCasConflict,
)
from fin_ops_platform.services.workbench_amount_check_service import (
    unassigned_invoice_anomaly_fingerprint,
)
from fin_ops_platform.services.workbench_invoice_expense_item_assignment_service import (
    WorkbenchInvoiceExpenseItemAssignmentError,
    WorkbenchInvoiceExpenseItemAssignmentService,
)
from fin_ops_platform.services.workbench_uow import WorkbenchWriteUnitOfWork


class _UnitOfWork:
    def __init__(self, context: object) -> None:
        self.context = context
        self.commands: list[object] = []

    def run(self, command: object, handler: object) -> dict[str, object]:
        self.commands.append(command)
        return handler(self.context)


class _Relations:
    def __init__(self, relation: dict[str, object]) -> None:
        self.relation = relation
        self.lock_calls: list[dict[str, object]] = []

    def acquire_relation_member_locks(
        self,
        row_ids: list[str],
        *,
        row_types: list[str],
        case_ids: list[str],
    ) -> list[str]:
        self.lock_calls.append({"row_ids": row_ids, "row_types": row_types, "case_ids": case_ids})
        return []

    def load_active_workbench_pair_relation_by_case_id_for_update(
        self,
        case_id: str,
    ) -> dict[str, object] | None:
        return dict(self.relation) if case_id == self.relation.get("case_id") else None


class _CanonicalQuery:
    def __init__(self, rows: dict[str, dict[str, object]]) -> None:
        self.rows = rows

    def get_canonical_rows_by_ids_in_current_transaction(
        self,
        row_ids: list[str],
        *,
        row_types: list[str],
    ) -> dict[str, dict[str, object]]:
        assert len(row_ids) == len(row_types)
        return {row_id: dict(self.rows[row_id]) for row_id in row_ids}

    def get_oa_expense_items_by_row_ids_in_current_transaction(
        self,
        oa_row_ids: list[str],
    ) -> dict[str, list[dict[str, object]]]:
        return {
            row_id: [
                dict(item)
                for item in list(self.rows[row_id].get("expense_items") or [])
                if isinstance(item, dict)
            ]
            for row_id in oa_row_ids
        }


class _Invoices:
    def __init__(
        self,
        snapshot: dict[str, object],
        *,
        update_error: Exception | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.update_error = update_error
        self.updates: list[dict[str, object]] = []

    def load_invoice_source_links_for_update(
        self,
        transaction: object,
        *,
        invoice_id: str,
    ) -> dict[str, object] | None:
        _ = transaction
        return dict(self.snapshot) if invoice_id == self.snapshot.get("invoice_id") else None

    def update_invoice_source_links_cas(
        self,
        transaction: object,
        updates: list[dict[str, object]],
        *,
        actor_id: str,
        reason: str,
    ) -> dict[str, object]:
        _ = (transaction, reason)
        if self.update_error is not None:
            raise self.update_error
        self.updates.extend({**item, "actor_id": actor_id} for item in updates)
        return {"written_invoice_count": len(updates)}


class _Audit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def append_operation_event(self, event: dict[str, object]) -> dict[str, object]:
        self.events.append(dict(event))
        return {"id": "audit-1"}


class _RollbackConnection:
    def __init__(self, source_links: list[dict[str, object]]) -> None:
        self.source_links = [dict(item) for item in source_links]
        self.commits = 0
        self.rollbacks = 0

    def transaction(self) -> object:
        owner = self

        class _Transaction:
            def __enter__(self) -> _RollbackConnection:
                self.before = [dict(item) for item in owner.source_links]
                return owner

            def __exit__(
                self,
                exc_type: object,
                _exc: object,
                _traceback: object,
            ) -> bool:
                if exc_type is None:
                    owner.commits += 1
                else:
                    owner.source_links = self.before
                    owner.rollbacks += 1
                return False

        return _Transaction()


class _TransactionalInvoices:
    def load_invoice_source_links_for_update(
        self,
        transaction: _RollbackConnection,
        *,
        invoice_id: str,
    ) -> dict[str, object] | None:
        if invoice_id != "invoice-1":
            return None
        return {
            "invoice_id": invoice_id,
            "invoice_total": "338.00",
            "stored_source_links": [dict(item) for item in transaction.source_links],
            "source_links": [dict(item) for item in transaction.source_links],
        }

    def update_invoice_source_links_cas(
        self,
        transaction: _RollbackConnection,
        updates: list[dict[str, object]],
        *,
        actor_id: str,
        reason: str,
    ) -> dict[str, object]:
        _ = (actor_id, reason)
        transaction.source_links = [
            dict(item) for item in list(updates[0]["source_links"])
        ]
        return {"written_invoice_count": 1}


class _FailingAudit:
    def append_operation_event(self, _event: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("audit append failed")


class WorkbenchInvoiceExpenseItemAssignmentServiceTests(unittest.TestCase):
    def _fixture(
        self,
        *,
        source_links: list[dict[str, object]] | None = None,
    ) -> tuple[WorkbenchInvoiceExpenseItemAssignmentService, _Invoices, _Relations, _Audit]:
        relation = _Relations({
            "case_id": "CASE-1",
            "row_ids": ["oa-1", "invoice-1"],
            "row_types": ["oa", "invoice"],
        })
        rows = {
            "oa-1": {
                "id": "oa-1",
                "type": "oa",
                "expense_items": [
                    {"id": "item-a", "amount": "436.30"},
                    {"id": "item-b", "amount": "531.92"},
                ],
            },
            "invoice-1": {
                "id": "invoice-1",
                "type": "invoice",
                "total_with_tax": "338.00",
            },
        }
        invoices = _Invoices({
            "invoice_id": "invoice-1",
            "invoice_total": "338.00",
            "stored_source_links": source_links or [],
            "source_links": source_links or [],
        })
        audit = _Audit()
        context = SimpleNamespace(
            transaction=object(),
            pair_relations=relation,
            canonical_query=_CanonicalQuery(rows),
            invoice_source_links=invoices,
            operation_audit=audit,
        )
        return (
            WorkbenchInvoiceExpenseItemAssignmentService(
                unit_of_work=_UnitOfWork(context)
            ),
            invoices,
            relation,
            audit,
        )

    @staticmethod
    def _payload(**overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "case_id": "CASE-1",
            "invoice_row_id": "invoice-1",
            "targets": [
                {"oa_row_id": "oa-1", "expense_item_id": "item-b"},
                {"oa_row_id": "oa-1", "expense_item_id": "item-a"},
            ],
            "anomaly_fingerprint": unassigned_invoice_anomaly_fingerprint(
                relation_id="CASE-1",
                invoice_row_id="invoice-1",
                invoice_total="338.00",
            ),
            "idempotency_key": "assign-1",
        }
        payload.update(overrides)
        return payload

    def test_assigns_one_invoice_to_multiple_explicit_targets_without_amount_inference(self) -> None:
        service, invoices, relations, audit = self._fixture(
            source_links=[{"source_type": "manual_invoice_import", "source_id": "manual-1"}]
        )

        result = service.assign(
            self._payload(),
            actor_id="finance-user",
            tenant_id="default",
            request_id="request-1",
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            result["targets"],
            [
                {"oa_row_id": "oa-1", "expense_item_id": "item-a"},
                {"oa_row_id": "oa-1", "expense_item_id": "item-b"},
            ],
        )
        self.assertEqual(len(invoices.updates), 1)
        written_links = invoices.updates[0]["source_links"]
        self.assertEqual(written_links[0]["source_type"], "manual_invoice_import")
        self.assertEqual(
            [link["source_expense_item_id"] for link in written_links[1:]],
            ["item-a", "item-b"],
        )
        self.assertEqual(relations.lock_calls[0]["case_ids"], ["CASE-1"])
        self.assertEqual(audit.events[0]["request_id"], "request-1")

    def test_rejects_changed_anomaly_before_any_write(self) -> None:
        service, invoices, _relations, audit = self._fixture()

        with self.assertRaises(WorkbenchInvoiceExpenseItemAssignmentError) as caught:
            service.assign(
                self._payload(anomaly_fingerprint="stale"),
                actor_id="finance-user",
                tenant_id="default",
                request_id="request-1",
            )

        self.assertEqual(caught.exception.code, "workbench_anomaly_changed")
        self.assertEqual(invoices.updates, [])
        self.assertEqual(audit.events, [])

    def test_rejects_existing_explicit_edges_that_do_not_exactly_match_targets(self) -> None:
        service, invoices, _relations, audit = self._fixture(source_links=[{
            "source_type": "oa_expense_item_invoice",
            "derived_from_oa_id": "oa-1",
            "source_expense_item_id": "item-a",
        }])

        with self.assertRaises(WorkbenchInvoiceExpenseItemAssignmentError) as caught:
            service.assign(
                self._payload(),
                actor_id="finance-user",
                tenant_id="default",
                request_id="request-1",
            )

        self.assertEqual(caught.exception.code, "invoice_expense_item_assignment_conflict")
        self.assertEqual(invoices.updates, [])
        self.assertEqual(audit.events, [])

    def test_exact_existing_explicit_targets_are_idempotent_noop_with_a_new_key(self) -> None:
        service, invoices, _relations, audit = self._fixture(source_links=[
            {
                "source_type": "oa_expense_item_invoice",
                "derived_from_oa_id": "oa-1",
                "source_expense_item_id": "item-b",
            },
            {
                "source_type": "oa_expense_item_invoice",
                "source_workbench_row_id": "oa-1",
                "source_expense_item_id": "item-a",
            },
        ])

        result = service.assign(
            self._payload(idempotency_key="another-key", anomaly_fingerprint="already-closed"),
            actor_id="finance-user",
            tenant_id="default",
            request_id="request-2",
        )

        self.assertTrue(result["success"])
        self.assertFalse(result["changed"])
        self.assertEqual(invoices.updates, [])
        self.assertEqual(audit.events, [])

    def test_foreign_or_malformed_explicit_edges_are_never_overwritten(self) -> None:
        existing_edges = (
            [{
                "source_type": "oa_expense_item_invoice",
                "derived_from_oa_id": "oa-foreign",
                "source_expense_item_id": "foreign-item",
            }],
            [{
                "source_type": "oa_expense_item_invoice",
                "source_expense_item_id": "item-a",
            }],
        )
        for source_links in existing_edges:
            with self.subTest(source_links=source_links):
                service, invoices, _relations, audit = self._fixture(source_links=source_links)
                with self.assertRaises(WorkbenchInvoiceExpenseItemAssignmentError) as caught:
                    service.assign(
                        self._payload(),
                        actor_id="finance-user",
                        tenant_id="default",
                        request_id="request-1",
                    )
                self.assertEqual(
                    caught.exception.code,
                    "invoice_expense_item_assignment_conflict",
                )
                self.assertEqual(invoices.updates, [])
                self.assertEqual(audit.events, [])

    def test_requires_unique_targets_and_idempotency_key(self) -> None:
        service, _invoices, _relations, _audit = self._fixture()
        duplicate_target = {"oa_row_id": "oa-1", "expense_item_id": "item-a"}
        for payload in (
            self._payload(idempotency_key=""),
            self._payload(targets=[duplicate_target, duplicate_target]),
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(WorkbenchInvoiceExpenseItemAssignmentError) as caught:
                    service.assign(
                        payload,
                        actor_id="finance-user",
                        tenant_id="default",
                        request_id="request-1",
                    )
                self.assertEqual(caught.exception.status_code, 400)

    def test_rejects_foreign_oa_member_without_writing(self) -> None:
        service, invoices, _relations, audit = self._fixture()

        with self.assertRaises(WorkbenchInvoiceExpenseItemAssignmentError) as caught:
            service.assign(
                self._payload(targets=[{
                    "oa_row_id": "oa-foreign",
                    "expense_item_id": "foreign-item",
                }]),
                actor_id="finance-user",
                tenant_id="default",
                request_id="request-foreign",
            )

        self.assertEqual(caught.exception.code, "oa_target_not_in_relation")
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(invoices.updates, [])
        self.assertEqual(audit.events, [])

    def test_rejects_more_than_one_hundred_targets_before_the_unit_of_work(self) -> None:
        service, invoices, _relations, audit = self._fixture()

        with self.assertRaises(WorkbenchInvoiceExpenseItemAssignmentError) as caught:
            service.assign(
                self._payload(targets=[
                    {"oa_row_id": "oa-1", "expense_item_id": f"item-{index}"}
                    for index in range(101)
                ]),
                actor_id="finance-user",
                tenant_id="default",
                request_id="request-too-many",
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(invoices.updates, [])
        self.assertEqual(audit.events, [])

    def test_maps_source_link_cas_conflict_to_stable_domain_conflict_without_audit(self) -> None:
        service, invoices, _relations, audit = self._fixture()
        invoices.update_error = InvoiceSourceLinksCasConflict(
            "changed",
            invoice_id="invoice-1",
        )

        with self.assertRaises(WorkbenchInvoiceExpenseItemAssignmentError) as caught:
            service.assign(
                self._payload(),
                actor_id="finance-user",
                tenant_id="default",
                request_id="request-cas",
            )

        self.assertEqual(caught.exception.code, "invoice_source_links_changed")
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(invoices.updates, [])
        self.assertEqual(audit.events, [])

    def test_audit_append_failure_rolls_back_the_source_link_write(self) -> None:
        original_links = [{
            "source_type": "manual_invoice_import",
            "source_id": "manual-1",
        }]
        connection = _RollbackConnection(original_links)
        relation = _Relations({
            "case_id": "CASE-1",
            "row_ids": ["oa-1", "invoice-1"],
            "row_types": ["oa", "invoice"],
        })
        canonical_query = _CanonicalQuery({
            "oa-1": {
                "id": "oa-1",
                "type": "oa",
                "expense_items": [
                    {"id": "item-a", "amount": "436.30"},
                    {"id": "item-b", "amount": "531.92"},
                ],
            },
            "invoice-1": {
                "id": "invoice-1",
                "type": "invoice",
                "total_with_tax": "338.00",
            },
        })

        def repository_factory(transaction: object) -> SimpleNamespace:
            _ = transaction
            return SimpleNamespace(
                pair_relations=relation,
                exception_cases=SimpleNamespace(),
                row_overrides=SimpleNamespace(),
                canonical_query=canonical_query,
                invoice_source_links=_TransactionalInvoices(),
                operation_audit=_FailingAudit(),
            )

        service = WorkbenchInvoiceExpenseItemAssignmentService(
            unit_of_work=WorkbenchWriteUnitOfWork(
                connection=connection,
                repository_factory=repository_factory,
                idempotency_store=SimpleNamespace(),
            )
        )

        with self.assertRaisesRegex(RuntimeError, "audit append failed"):
            service.assign(
                self._payload(),
                actor_id="finance-user",
                tenant_id="default",
                request_id="request-audit-failure",
            )

        self.assertEqual(connection.source_links, original_links)
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
