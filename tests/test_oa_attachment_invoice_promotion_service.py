from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.app_settings_service import (
    OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
    OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED,
    OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
)
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import (
    OAAttachmentInvoicePromotionService,
)
from fin_ops_platform.services.postgres_repositories.oa_attachment_invoice import (
    PostgresOAAttachmentInvoiceRepository,
)


class OAAttachmentInvoicePromotionServiceTests(unittest.TestCase):
    def test_links_every_invoice_to_its_expense_item_in_one_batch_query(self) -> None:
        payloads = [
            _attachment("26539150014000401220", "145.00", "item-0", "outbound.pdf"),
            _attachment("26539148197001628598", "145.00", "item-0", "return.pdf"),
            _attachment("26532000000000000482", "482.00", "item-1", "meal.pdf"),
            _attachment("26532000000000000018", "18.00", "item-2", "post.pdf"),
            _attachment("26532000000000000290", "290.00", "item-3", "fuel.pdf"),
        ]
        repository = FakeInvoiceRepository([_invoice(payload) for payload in payloads])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-2321",
            month="2026-06",
            attachment_invoices=payloads,
            attachment_evidences=[],
        )

        first = service.promote_records([record])
        second = service.promote_records([record])

        self.assertEqual(repository.identity_query_count, 2)
        self.assertEqual(first["summary"]["cache_candidate_count"], 5)
        self.assertEqual(first["summary"]["linked_existing_invoice_count"], 5)
        self.assertEqual(first["summary"]["affected_invoice_count"], 5)
        self.assertEqual(len(repository.save_calls), 1)
        self.assertEqual(second["summary"]["affected_invoice_count"], 0)
        self.assertEqual(second["reason_counts"], {"already_linked": 5})
        linked_items = [
            invoice.source_links[0]["source_expense_item_id"]
            for invoice in repository.invoices
        ]
        self.assertEqual(linked_items, ["item-0", "item-0", "item-1", "item-2", "item-3"])

    def test_postgres_promotion_atomically_marks_expanded_matching_scopes_dirty(self) -> None:
        unchanged_payload = _attachment("26539150014000401220", "145.00", "item-0", "outbound.pdf")
        changed_payload = _attachment("26539148197001628598", "145.00", "item-1", "return.pdf")
        repository = FakeAtomicInvoiceRepository([_invoice(unchanged_payload), _invoice(changed_payload)])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        unchanged_record = SimpleNamespace(
            id="oa-exp-old",
            month="2024-01",
            attachment_invoices=[unchanged_payload],
            attachment_evidences=[],
        )
        service.promote_records([unchanged_record])
        repository.atomic_save_calls.clear()

        service.promote_records(
            [
                unchanged_record,
                SimpleNamespace(
                    id="oa-exp-2321",
                    month="2026-06",
                    attachment_invoices=[changed_payload],
                    attachment_evidences=[],
                )
            ]
        )

        self.assertEqual(len(repository.atomic_save_calls), 1)
        self.assertEqual(
            repository.atomic_save_calls[0]["scope_months"],
            ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08"],
        )
        self.assertEqual(
            repository.atomic_save_calls[0]["reason"],
            "oa_attachment_invoice_promotion",
        )
        self.assertEqual(repository.atomic_save_calls[0]["debounce_seconds"], 0)

    def test_manual_refresh_reconciles_matching_when_canonical_invoices_are_unchanged(self) -> None:
        payload = _attachment("26539150014000401220", "145.00", "item-0", "outbound.pdf")
        repository = FakeAtomicInvoiceRepository([_invoice(payload)])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-2321",
            month="2026-06",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        service.promote_records([record])
        repository.atomic_save_calls.clear()
        report = service.promote_records([record], ensure_matching=True)

        self.assertEqual(report["summary"]["affected_invoice_count"], 0)
        self.assertEqual(report["reason_counts"], {"already_linked": 1})
        self.assertEqual(len(repository.atomic_save_calls), 1)
        self.assertEqual(repository.atomic_save_calls[0]["invoices"], [])
        self.assertEqual(
            repository.atomic_save_calls[0]["scope_months"],
            ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08"],
        )
        self.assertEqual(
            repository.atomic_save_calls[0]["reason"],
            "oa_attachment_invoice_manual_refresh",
        )
        self.assertEqual(repository.atomic_save_calls[0]["debounce_seconds"], 0)

    def test_manual_refresh_fails_closed_without_matching_reconciliation_support(self) -> None:
        payload = _attachment("26539150014000401220", "145.00", "item-0", "outbound.pdf")
        repository = FakeInvoiceRepository([_invoice(payload)])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-2321",
            month="2026-06",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        service.promote_records([record])

        with self.assertRaisesRegex(RuntimeError, "matching reconciliation support"):
            service.promote_records([record], ensure_matching=True)

    def test_preloads_existing_invoice_when_attachment_only_has_bare_20_digit_invoice_no(self) -> None:
        payload = _attachment("26539150014000401220", "145.00", "item-0", "outbound.pdf")
        payload.pop("digital_invoice_no")
        existing = _invoice({**payload, "digital_invoice_no": payload["invoice_no"]})
        repository = FakeInvoiceRepository([existing])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-2321",
            month="2026-06",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        report = service.promote_records([record])

        self.assertEqual(report["summary"]["existing_invoice_count"], 1)
        self.assertEqual(report["summary"]["linked_existing_invoice_count"], 1)
        self.assertEqual(report["summary"]["created_invoice_count"], 0)
        self.assertEqual(repository.invoices[0].id, existing.id)

    def test_create_mode_creates_missing_formal_invoice_and_disabled_mode_writes_nothing(self) -> None:
        payload = _attachment("26532000000000000600", "600.00", "item-1", "invoice.pdf")
        repository = FakeInvoiceRepository([])
        create_service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
        )
        record = SimpleNamespace(
            id="oa-exp-create",
            month="2026-03",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        created = create_service.promote_records([record])
        disabled = create_service.promote_candidates(
            create_service.candidates_from_records([record]),
            promotion_mode=OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED,
            apply=True,
        )

        self.assertEqual(created["summary"]["created_invoice_count"], 1)
        self.assertEqual(created["summary"]["affected_invoice_count"], 1)
        self.assertEqual(repository.invoices[0].source_links[0]["derived_from_oa_id"], "oa-exp-create")
        self.assertEqual(disabled["reason_counts"], {"promotion_disabled": 1})
        self.assertEqual(len(repository.save_calls), 1)

    def test_rejects_reusing_one_invoice_across_different_oa_source_contexts(self) -> None:
        payload = _attachment("26532000000000000700", "700.00", "item-new", "invoice.pdf")
        invoice = _invoice(payload)
        invoice.source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "source_id": "old.pdf",
                "batch_id": "",
                "derived_from_oa_id": "oa-exp-old",
                "source_expense_item_id": "item-old",
            }
        ]
        repository = FakeInvoiceRepository([invoice])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-new",
            month="2026-03",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        report = service.promote_records([record])

        self.assertEqual(report["reason_counts"], {"source_context_conflict": 1})
        self.assertEqual(report["summary"]["affected_invoice_count"], 0)
        self.assertEqual(repository.save_calls, [])

    def test_active_lifecycle_alias_allows_completed_oa_to_reuse_ongoing_invoice(self) -> None:
        payload = _attachment("26539150014000355216", "145.00", "item-completed", "ticket.pdf")
        invoice = _invoice(payload)
        invoice.source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "source_id": "ticket.pdf",
                "batch_id": "",
                "derived_from_oa_id": "oa-exp-ongoing",
                "source_expense_item_id": "item-ongoing",
            }
        ]
        repository = FakeAliasInvoiceRepository(
            [invoice],
            aliases={
                "oa-exp-ongoing": "oa-exp-completed",
                "oa-exp-completed": "oa-exp-completed",
            },
        )
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-completed",
            month="2026-06",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        report = service.promote_records([record])

        self.assertEqual(report["summary"]["linked_existing_invoice_count"], 1)
        self.assertEqual(report["summary"]["affected_invoice_count"], 1)
        self.assertEqual(
            repository.alias_queries,
            [{"oa-exp-ongoing", "oa-exp-completed"}],
        )
        self.assertIn(
            "oa-exp-completed",
            {
                link.get("derived_from_oa_id")
                for link in invoice.source_links
                if link.get("source_type") == "oa_attachment_invoice"
            },
        )

    def test_links_one_invoice_to_multiple_expense_items_in_the_same_oa(self) -> None:
        first = _attachment("26532000000000000036", "36.00", "item-18-a", "shared.pdf")
        second = {**first, "source_expense_item_id": "item-18-b", "source_expense_row_index": "1"}
        invoice = _invoice(first)
        repository = FakeInvoiceRepository([invoice])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-shared",
            month="2026-07",
            attachment_invoices=[first],
            attachment_evidences=[],
            expense_items=[
                {"expense_item_id": "item-18-a", "row_index": "0", "attachment_invoices": [first]},
                {"expense_item_id": "item-18-b", "row_index": "1", "attachment_invoices": [second]},
            ],
        )

        report = service.promote_records([record])

        self.assertEqual(report["summary"]["cache_candidate_count"], 2)
        self.assertEqual(report["summary"]["affected_invoice_count"], 1)
        self.assertEqual(
            [
                link["source_expense_item_id"]
                for link in invoice.source_links
                if link.get("source_type") == "oa_attachment_invoice"
            ],
            ["item-18-a", "item-18-b"],
        )

    def test_enriches_legacy_parent_link_with_expense_item_context(self) -> None:
        payload = _attachment("26532000000000000800", "800.00", "item-2", "invoice.pdf")
        invoice = _invoice(payload)
        invoice.source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "source_id": payload["source_attachment_key"],
                "batch_id": "",
                "derived_from_oa_id": "oa-exp-2321",
                "source_workbench_row_id": "legacy-parent-row",
            }
        ]
        repository = FakeInvoiceRepository([invoice])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-2321",
            month="2026-06",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        report = service.promote_records([record])

        self.assertEqual(report["summary"]["affected_invoice_count"], 1)
        self.assertEqual(invoice.source_links[0]["source_expense_item_id"], "item-2")
        self.assertNotEqual(invoice.source_links[0]["source_workbench_row_id"], "legacy-parent-row")


class FakeInvoiceRepository:
    def __init__(self, invoices: list[Invoice]) -> None:
        self.invoices = list(invoices)
        self.identity_query_count = 0
        self.save_calls: list[list[Invoice]] = []

    def find_invoices_by_identity_keys(self, *, canonical_keys: set[str]) -> list[Invoice]:
        self.identity_query_count += 1
        return [
            invoice
            for invoice in self.invoices
            if invoice.source_unique_key in canonical_keys or invoice.digital_invoice_no in canonical_keys
        ]

    def save_invoices(self, invoices: list[Invoice]) -> None:
        self.save_calls.append(list(invoices))
        by_id = {invoice.id: invoice for invoice in self.invoices}
        by_id.update({invoice.id: invoice for invoice in invoices})
        self.invoices = list(by_id.values())


class FakeAtomicInvoiceRepository(FakeInvoiceRepository):
    def __init__(self, invoices: list[Invoice]) -> None:
        super().__init__(invoices)
        self.atomic_save_calls: list[dict[str, object]] = []

    def save_invoices_and_mark_matching_dirty(
        self,
        invoices: list[Invoice],
        *,
        scope_months: list[str],
        reason: str,
        debounce_seconds: int,
    ) -> list[str]:
        self.atomic_save_calls.append(
            {
                "invoices": list(invoices),
                "scope_months": list(scope_months),
                "reason": reason,
                "debounce_seconds": debounce_seconds,
            }
        )
        super().save_invoices(invoices)
        return list(scope_months)


class FakeAliasInvoiceRepository(FakeInvoiceRepository):
    def __init__(self, invoices: list[Invoice], *, aliases: dict[str, str]) -> None:
        super().__init__(invoices)
        self.aliases = dict(aliases)
        self.alias_queries: list[set[str]] = []

    def resolve_active_oa_source_aliases(self, oa_row_ids: set[str]) -> dict[str, str]:
        self.alias_queries.append(set(oa_row_ids))
        return {
            row_id: self.aliases.get(row_id, row_id)
            for row_id in oa_row_ids
        }


class PostgresOAAttachmentInvoiceRepositoryTests(unittest.TestCase):
    def test_resolves_only_active_oa_source_aliases_in_one_query(self) -> None:
        connection = _FakeAliasQueryConnection(
            [
                {
                    "alias_row_id": "oa-exp-ongoing",
                    "canonical_row_id": "oa-exp-completed",
                }
            ]
        )
        repository = PostgresOAAttachmentInvoiceRepository(connection)

        aliases = repository.resolve_active_oa_source_aliases(
            {"oa-exp-ongoing", "oa-exp-completed", "oa-exp-other"}
        )

        self.assertEqual(
            aliases,
            {
                "oa-exp-ongoing": "oa-exp-completed",
                "oa-exp-completed": "oa-exp-completed",
                "oa-exp-other": "oa-exp-other",
            },
        )
        self.assertEqual(len(connection.fetch_calls), 1)
        sql, params = connection.fetch_calls[0]
        self.assertIn("status = 'active'", sql)
        self.assertEqual(
            params,
            (
                ["oa-exp-completed", "oa-exp-ongoing", "oa-exp-other"],
                ["oa-exp-completed", "oa-exp-ongoing", "oa-exp-other"],
            ),
        )

    def test_invoice_write_and_matching_dirty_marker_share_one_transaction(self) -> None:
        transaction = object()
        connection = _FakeTransactionalConnection(transaction)
        repository = PostgresOAAttachmentInvoiceRepository(connection)

        with (
            patch(
                "fin_ops_platform.services.postgres_repositories.oa_attachment_invoice.PostgresCoreRepository"
            ) as core_repository,
            patch(
                "fin_ops_platform.services.postgres_repositories.oa_attachment_invoice."
                "PostgresWorkbenchMatchingQueueRepository.mark_workbench_matching_dirty_scopes_in_transaction",
                return_value=["2026-06"],
            ) as mark_dirty,
        ):
            result = repository.save_invoices_and_mark_matching_dirty(
                ["invoice"],
                scope_months=["2026-06"],
                reason="oa_attachment_invoice_promotion",
                debounce_seconds=0,
            )

        core_repository.assert_called_once_with(transaction)
        core_repository.return_value.save_invoices.assert_called_once_with(["invoice"])
        mark_dirty.assert_called_once_with(
            transaction=transaction,
            tenant_id="default",
            scope_months=["2026-06"],
            reason="oa_attachment_invoice_promotion",
            source_versions={},
            debounce_seconds=0,
        )
        self.assertEqual(result, ["2026-06"])


class _FakeTransactionalConnection:
    def __init__(self, transaction: object) -> None:
        self._transaction = transaction

    def transaction(self) -> "_FakeTransactionContext":
        return _FakeTransactionContext(self._transaction)


class _FakeAliasQueryConnection:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = list(rows)
        self.fetch_calls: list[tuple[str, object]] = []

    def fetch_all(self, sql: str, params: object) -> list[dict[str, str]]:
        self.fetch_calls.append((sql, params))
        return list(self._rows)


class _FakeTransactionContext:
    def __init__(self, transaction: object) -> None:
        self._transaction = transaction

    def __enter__(self) -> object:
        return self._transaction

    def __exit__(self, *_args: object) -> None:
        return None


def _attachment(invoice_no: str, amount: str, item_id: str, filename: str) -> dict[str, str]:
    return {
        "evidence_type": "tax_invoice",
        "document_kind": "digital_invoice",
        "digital_invoice_no": invoice_no,
        "invoice_no": invoice_no,
        "seller_name": "测试销方",
        "buyer_name": "云南溯源科技有限公司",
        "issue_date": "2026-06-29",
        "amount": amount,
        "total_with_tax": amount,
        "source_attachment_key": f"oa-exp-2321:{filename}",
        "source_attachment_name": filename,
        "source_expense_item_id": item_id,
    }


def _invoice(payload: dict[str, str]) -> Invoice:
    invoice_no = payload["digital_invoice_no"]
    counterparty = Counterparty(
        id=f"cp-{invoice_no}",
        name="测试销方",
        normalized_name="测试销方",
        counterparty_type="supplier",
    )
    return Invoice(
        id=f"invoice-{invoice_no}",
        invoice_type=InvoiceType.INPUT,
        invoice_no=invoice_no,
        digital_invoice_no=invoice_no,
        counterparty=counterparty,
        amount=Decimal(payload["amount"]),
        signed_amount=Decimal(payload["amount"]),
        invoice_date=payload["issue_date"],
        source_unique_key=invoice_no,
    )


if __name__ == "__main__":
    unittest.main()
