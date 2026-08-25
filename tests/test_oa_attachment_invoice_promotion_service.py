from __future__ import annotations

import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.app_settings_service import (
    OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
    OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED,
    OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
)
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import (
    OAAttachmentInvoiceCandidate,
    OAAttachmentInvoicePromotionService,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.oa_attachment_invoice import (
    PostgresOAAttachmentInvoiceRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_attachment_identity_bridge import (
    reconcile_oa_attachment_cache_identity_sources,
)

from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class OAAttachmentInvoicePromotionServiceTests(unittest.TestCase):
    def test_reverse_promotion_fails_closed_for_numberless_tax_composite_identity(self) -> None:
        self.assertIsNone(OAAttachmentInvoicePromotionService.strong_identity_key({
            "seller_tax_no": "SELLER",
            "buyer_tax_no": "BUYER",
            "issue_date": "2026-06-29",
            "total_with_tax": "145.00",
        }))

    def test_reverse_promotion_skips_cache_for_disabled_or_empty_identity_batches(self) -> None:
        repository = FakeReverseInvoiceRepository([], [])
        service = OAAttachmentInvoicePromotionService(invoice_repository=repository)

        disabled = service.promote_confirmed_invoice_identity_keys(
            {"26539150014000401220"},
            configured_mode=OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED,
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )
        empty = service.promote_confirmed_invoice_identity_keys(
            set(),
            configured_mode=OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )

        self.assertEqual(repository.promotion_source_calls, [])
        self.assertEqual(disabled["reason_counts"], {"promotion_disabled": 1})
        self.assertEqual(empty["summary"]["requested_identity_count"], 0)

    def test_reverse_promotion_reads_only_requested_current_cache_and_never_creates(self) -> None:
        payload = _attachment("26539150014000401220", "145.00", "item-0", "outbound.pdf")
        repository = FakeReverseInvoiceRepository(
            [_invoice(payload)],
            [{
                "cache_source_attachment_key": "cache-key",
                "invoices": [payload],
                "invoice_indexes": [4],
                "oa_application_id": "oa-app-1",
                "oa_row_id": "oa-exp-1",
                "source_expense_item_id": "item-0",
                "source_expense_row_index": "0",
                "source_attachment_key": "attachment-outbound",
                "source_attachment_name": "outbound.pdf",
                "month": "2026-06",
            }],
        )
        service = OAAttachmentInvoicePromotionService(invoice_repository=repository)

        report = service.promote_confirmed_invoice_identity_keys(
            {payload["digital_invoice_no"], "26539150014000409999"},
            configured_mode=OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )

        self.assertEqual(repository.promotion_source_calls, [{
            "canonical_keys": {payload["digital_invoice_no"], "26539150014000409999"},
            "parser_version": "parser-current",
            "cache_schema_version": "schema-current",
        }])
        self.assertEqual(report["summary"]["matched_identity_count"], 1)
        self.assertEqual(report["summary"]["created_invoice_count"], 0)
        self.assertEqual(report["reason_counts"]["no_current_bridged_attachment_candidate"], 1)
        self.assertEqual(repository.invoices[0].source_links[0]["source_expense_item_id"], "item-0")

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

    def test_rejects_attachment_when_invoice_is_explicitly_owned_by_another_oa(self) -> None:
        payload = _attachment("26532000000000000701", "701.00", "item-new", "invoice.pdf")
        invoice = _invoice(payload)
        invoice.source_links = [
            {
                "source_type": "oa_expense_item_invoice",
                "derived_from_oa_id": "oa-exp-old",
                "source_expense_item_id": "oa-exp-old:item:0:explicit",
            }
        ]
        repository = FakeInvoiceRepository([invoice])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )

        report = service.promote_records([
            SimpleNamespace(
                id="oa-exp-new",
                month="2026-03",
                attachment_invoices=[payload],
                attachment_evidences=[],
            )
        ])

        self.assertEqual(report["reason_counts"], {"source_context_conflict": 1})
        self.assertEqual(report["summary"]["affected_invoice_count"], 0)
        self.assertEqual(repository.save_calls, [])

    def test_active_alias_allows_explicit_owner_and_attachment_context(self) -> None:
        payload = _attachment("26532000000000000702", "702.00", "item-new", "invoice.pdf")
        invoice = _invoice(payload)
        invoice.source_links = [
            {
                "source_type": "oa_expense_item_invoice",
                "derived_from_oa_id": "oa-exp-ongoing",
                "source_expense_item_id": "oa-exp-ongoing:item:0:explicit",
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

        report = service.promote_records([
            SimpleNamespace(
                id="oa-exp-completed",
                month="2026-03",
                attachment_invoices=[payload],
                attachment_evidences=[],
            )
        ])

        self.assertEqual(report["summary"]["affected_invoice_count"], 1)
        self.assertNotIn("source_context_conflict", report["reason_counts"])

    def test_same_identity_from_two_active_oas_fails_closed_before_any_write(self) -> None:
        payload = _attachment("26532000000000000703", "703.00", "item-a", "invoice.pdf")
        repository = FakeInvoiceRepository([_invoice(payload)])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )

        report = service.promote_records([
            SimpleNamespace(
                id="oa-exp-a",
                month="2026-03",
                attachment_invoices=[payload],
                attachment_evidences=[],
            ),
            SimpleNamespace(
                id="oa-exp-b",
                month="2026-03",
                attachment_invoices=[{**payload, "source_expense_item_id": "item-b"}],
                attachment_evidences=[],
            ),
        ])

        self.assertEqual(report["reason_counts"], {"source_context_conflict": 2})
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
                "derived_from_oa_id": "oa-exp-ongoing:item:0:historical-fingerprint",
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

    def test_structured_expense_item_owner_overrides_stale_nested_attachment_owner(self) -> None:
        payload = _attachment(
            "26532000000000000035",
            "35.00",
            "oa-exp-old:item:7:stale",
            "invoice.pdf",
        )
        payload["source_expense_row_index"] = "7"

        candidates = OAAttachmentInvoicePromotionService.candidates_from_records([
            SimpleNamespace(
                id="oa-exp-current",
                month="2026-07",
                attachment_invoices=[],
                attachment_evidences=[],
                expense_items=[{
                    "expense_item_id": "oa-exp-current:item:0:current",
                    "row_index": "0",
                    "attachment_invoices": [payload],
                }],
            )
        ])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0].attachment_invoice["source_expense_item_id"],
            "oa-exp-current:item:0:current",
        )
        self.assertEqual(
            candidates[0].attachment_invoice["source_expense_row_index"],
            "0",
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


class FakeReverseInvoiceRepository(FakeInvoiceRepository):
    def __init__(self, invoices: list[Invoice], rows: list[dict[str, object]]) -> None:
        super().__init__(invoices)
        self.rows = list(rows)
        self.promotion_source_calls: list[dict[str, object]] = []

    def list_promotion_source_rows(self, **kwargs: object) -> list[dict[str, object]]:
        self.promotion_source_calls.append(dict(kwargs))
        return list(self.rows)


class PostgresOAAttachmentInvoiceRepositoryTests(unittest.TestCase):
    def test_reverse_cache_query_joins_each_invoice_to_one_proven_context(self) -> None:
        connection = _FakeAliasQueryConnection([])

        PostgresOAAttachmentInvoiceRepository(connection).list_promotion_source_rows(
            canonical_keys={"26539150014000401220"},
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )

        sql, params = connection.fetch_calls[0]
        self.assertIn("with matched_invoices as", sql.lower())
        self.assertIn("matched.invoice_payload->>'source_attachment_key'", sql)
        self.assertIn("matched.invoice_payload->>'source_expense_item_id'", sql)
        self.assertIn("join proven_contexts context", sql.lower())
        self.assertIn("source.source_kind = 'attachment_identity_invoice'", sql)
        self.assertIn("join app.oa_application_items item", sql)
        self.assertIn("from app.oa_attachments exact_attachment", sql)
        self.assertIn("exact_app.status <> 'deleted'", sql)
        self.assertIn("app.status <> 'deleted'", sql)
        self.assertIn("item.row_id as source_expense_item_id", sql)
        self.assertNotIn("source.source_kind <> 'cache_key'", sql)
        self.assertNotIn("having count(*)", sql.lower())
        self.assertNotIn("min(source_expense_item_id)", sql.lower())
        self.assertEqual(
            params,
            ("parser-current", "schema-current", ["26539150014000401220"]),
        )

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
        core_repository.return_value.save_oa_attachment_invoices_in_transaction.assert_called_once_with(
            transaction,
            ["invoice"],
        )
        mark_dirty.assert_called_once_with(
            transaction=transaction,
            tenant_id="default",
            scope_months=["2026-06"],
            reason="oa_attachment_invoice_promotion",
            source_versions={},
            debounce_seconds=0,
        )
        self.assertEqual(result, ["2026-06"])


class PostgresOAAttachmentInvoiceRepositoryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        apply_test_migrations(self.database_url)
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )

    def tearDown(self) -> None:
        connection = getattr(self, "connection", None)
        if connection is not None:
            connection.close()

    def test_reverse_cache_maps_each_invoice_only_to_its_unique_proven_context(self) -> None:
        self.connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, row_id, status, scope_month
            ) values
                ('source-a', 'form-a', 'oa-a', 'completed', '2026-06-01'),
                ('source-b', 'form-b', 'oa-b', 'completed', '2026-06-01'),
                ('source-c', 'form-c', 'oa-c', 'completed', '2026-06-01')
            """
        )
        self.connection.execute(
            """
            insert into app.oa_application_items(
                oa_application_id, oa_source_id, form_id, row_id,
                item_no, normalized_payload
            )
            select id, oa_source_id, form_id,
                   row_id || ':item:0:' || right(row_id, 1),
                   '0', '{"row_index":"0"}'::jsonb
            from app.oa_applications
            """
        )
        self.connection.execute(
            """
            insert into app.oa_attachments(
                oa_application_id, oa_source_id, form_id, row_id,
                source_attachment_key, filename, normalized_payload
            )
            select app.id, app.oa_source_id, app.form_id, item.row_id,
                   'attachment-' || right(app.row_id, 1),
                   case app.row_id
                       when 'oa-b' then 'invoice-b.pdf'
                       else 'invoice-a.pdf'
                   end,
                   jsonb_build_object(
                       'source_expense_item_id', item.row_id,
                       'source_expense_row_index', '0',
                       'source_attachment_name',
                       case app.row_id
                           when 'oa-b' then 'invoice-b.pdf'
                           else 'invoice-a.pdf'
                       end
                   )
            from app.oa_applications app
            join app.oa_application_items item
              on item.oa_application_id = app.id
            """
        )
        self.connection.execute(
            """
            insert into app.oa_attachment_invoice_cache(
                source_attachment_key, parser_version, cache_schema_version,
                parsed_at, invoices
            ) values (
                'cache-two-invoices', 'parser-current', 'schema-current', now(),
                %s::jsonb
            )
            """,
            (
                """[
                    {
                        "evidence_type":"tax_invoice",
                        "document_kind":"digital_invoice",
                        "digital_invoice_no":"26532000000000000901",
                        "invoice_no":"26532000000000000901",
                        "issue_date":"2026-06-01",
                        "total_with_tax":"901.00",
                        "source_attachment_key":"attachment-a",
                        "source_attachment_name":"invoice-a.pdf",
                        "source_expense_item_id":"oa-a:item:0:a"
                    },
                    {
                        "evidence_type":"tax_invoice",
                        "document_kind":"digital_invoice",
                        "digital_invoice_no":"26532000000000000902",
                        "invoice_no":"26532000000000000902",
                        "issue_date":"2026-06-02",
                        "total_with_tax":"902.00",
                        "source_attachment_key":"attachment-b",
                        "source_attachment_name":"invoice-b.pdf",
                        "source_expense_item_id":"oa-b:item:0:b"
                    }
                ]""",
            ),
        )
        self.connection.execute(
            """
            insert into app.oa_attachment_invoice_cache_sources(
                cache_source_attachment_key, source_attachment_key, source_kind,
                source_expense_item_id, source_expense_row_index, source_attachment_name
            ) values
                (
                    'cache-two-invoices', 'attachment-a', 'invoice',
                    'oa-a:item:0:a', '0', 'invoice-a.pdf'
                ),
                (
                    'cache-two-invoices', 'attachment-b', 'invoice',
                    'oa-b:item:0:b', '0', 'invoice-b.pdf'
                )
            """
        )
        repository = PostgresOAAttachmentInvoiceRepository(self.connection)

        raw_only_rows = repository.list_promotion_source_rows(
            canonical_keys={"26532000000000000901", "26532000000000000902"},
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )
        self.assertEqual(raw_only_rows, [])

        reconcile_oa_attachment_cache_identity_sources(
            self.connection,
            cache_source_attachment_keys=["cache-two-invoices"],
        )
        rows = repository.list_promotion_source_rows(
            canonical_keys={"26532000000000000901", "26532000000000000902"},
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )

        self.assertEqual(
            {
                row["invoices"][0]["digital_invoice_no"]: (
                    row["oa_row_id"],
                    row["source_expense_item_id"],
                )
                for row in rows
            },
            {
                "26532000000000000901": ("oa-a", "oa-a:item:0:a"),
                "26532000000000000902": ("oa-b", "oa-b:item:0:b"),
            },
        )

        # A stale nested owner must not win once the same occurrence still has
        # an exact current attachment key.  The second bridged attachment is a
        # valid context for the other occurrence in this cache, not this one.
        self.connection.execute(
            """
            update app.oa_attachment_invoice_cache
            set invoices = jsonb_set(
                jsonb_set(
                    invoices,
                    '{0,source_expense_item_id}',
                    to_jsonb('oa-b:item:0:b'::text)
                ),
                '{0,source_attachment_name}',
                to_jsonb('invoice-b.pdf'::text)
            )
            where source_attachment_key = 'cache-two-invoices'
            """
        )
        exact_owner_rows = repository.list_promotion_source_rows(
            canonical_keys={"26532000000000000901"},
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )
        self.assertEqual(len(exact_owner_rows), 1)
        self.assertEqual(exact_owner_rows[0]["oa_row_id"], "oa-a")
        self.assertEqual(
            exact_owner_rows[0]["source_expense_item_id"],
            "oa-a:item:0:a",
        )

        self.connection.execute(
            """
            insert into app.oa_attachment_invoice_cache_sources(
                cache_source_attachment_key, source_attachment_key, source_kind,
                source_expense_item_id, source_expense_row_index, source_attachment_name
            ) values (
                'cache-two-invoices', 'attachment-c', 'attachment_identity_invoice',
                'oa-a:item:0:a', '0', 'invoice-a.pdf'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                source_unique_key, amount, signed_amount, status, source_links, raw_payload
            ) values (
                'invoice-ambiguous-a', 'input', '26532000000000000901',
                '26532000000000000901', '26532000000000000901',
                901, 901, 'pending', '[]'::jsonb,
                '{"normalized_payload":{"id":"invoice-ambiguous-a"}}'::jsonb
            )
            """
        )
        current_rows = repository.list_promotion_source_rows(
            canonical_keys={"26532000000000000901", "26532000000000000902"},
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )

        current_invoice_numbers = [
            row["invoices"][0]["digital_invoice_no"] for row in current_rows
        ]
        self.assertEqual(current_invoice_numbers.count("26532000000000000901"), 1)
        self.assertEqual(current_invoice_numbers.count("26532000000000000902"), 1)
        report = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
        ).promote_confirmed_invoice_identity_keys(
            {"26532000000000000901"},
            configured_mode=OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )
        persisted = self.connection.fetch_one(
            """
            select source_links
            from app.invoices
            where legacy_mongo_id = 'invoice-ambiguous-a'
            """
        )

        oa_links = [
            link
            for link in persisted["source_links"]
            if link.get("source_type") == "oa_attachment_invoice"
        ]
        self.assertEqual(report["summary"]["affected_invoice_count"], 1)
        self.assertEqual(len(oa_links), 1)
        self.assertEqual(oa_links[0]["derived_from_oa_id"], "oa-a")
        self.assertEqual(oa_links[0]["source_expense_item_id"], "oa-a:item:0:a")

    def test_reverse_cache_keeps_all_same_oa_expense_item_contexts(self) -> None:
        invoice_no = "26532000000000000910"
        self.connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, row_id, status, scope_month
            ) values (
                'source-shared', 'form-shared', 'oa-shared', 'completed', '2026-06-01'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.oa_application_items(
                oa_application_id, oa_source_id, form_id, row_id,
                item_no, normalized_payload
            )
            select id, oa_source_id, form_id, 'oa-shared:item:0',
                   '0', '{"row_index":"0"}'::jsonb
            from app.oa_applications where row_id = 'oa-shared'
            union all
            select id, oa_source_id, form_id, 'oa-shared:item:1',
                   '1', '{"row_index":"1"}'::jsonb
            from app.oa_applications where row_id = 'oa-shared'
            """
        )
        self.connection.execute(
            """
            insert into app.oa_attachments(
                oa_application_id, oa_source_id, form_id, row_id,
                source_attachment_key, filename, normalized_payload
            )
            select app.id, app.oa_source_id, app.form_id, item.row_id,
                   'attachment-shared-' || item.item_no,
                   'invoice-shared.pdf',
                   jsonb_build_object(
                       'source_expense_item_id', item.row_id,
                       'source_expense_row_index', item.item_no,
                       'source_attachment_name', 'invoice-shared.pdf',
                       'physical_source_attachment_key', 'physical-shared'
                   )
            from app.oa_applications app
            join app.oa_application_items item on item.oa_application_id = app.id
            where app.row_id = 'oa-shared'
            """
        )
        first_attachment_invoice = _attachment(
            invoice_no,
            "910.00",
            "oa-shared:item:0",
            "invoice-shared.pdf",
        )
        first_attachment_invoice["source_attachment_key"] = "attachment-shared-0"
        second_attachment_invoice = dict(first_attachment_invoice)
        second_attachment_invoice["source_attachment_key"] = "attachment-shared-1"
        second_attachment_invoice["source_expense_item_id"] = "oa-shared:item:1"
        second_attachment_invoice["source_expense_row_index"] = "1"
        self.connection.execute(
            """
            insert into app.oa_attachment_invoice_cache(
                source_attachment_key, parser_version, cache_schema_version,
                parsed_at, invoices
            ) values (
                'cache-shared-invoice', 'parser-current', 'schema-current', now(), %s::jsonb
            )
            """,
            (json.dumps([first_attachment_invoice, second_attachment_invoice]),),
        )
        self.connection.execute(
            """
            insert into app.oa_attachment_invoice_cache_sources(
                cache_source_attachment_key, source_attachment_key, source_kind,
                source_expense_item_id, source_expense_row_index, source_attachment_name
            ) values
                (
                    'cache-shared-invoice', 'attachment-shared-0', 'invoice',
                    'oa-shared:item:0', '0', 'invoice-shared.pdf'
                ),
                (
                    'cache-shared-invoice', 'attachment-shared-1', 'invoice',
                    'oa-shared:item:1', '1', 'invoice-shared.pdf'
                )
            """
        )
        reconcile_oa_attachment_cache_identity_sources(
            self.connection,
            cache_source_attachment_keys=["cache-shared-invoice"],
        )
        manual_link = {
            "source_type": "manual_invoice_import",
            "source_id": invoice_no,
            "batch_id": "batch-formal",
        }
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                source_unique_key, amount, signed_amount, status, source_links, raw_payload
            ) values (
                'invoice-shared-contexts', 'input', %s, %s, %s,
                910, 910, 'pending', %s::jsonb, %s::jsonb
            )
            """,
            (
                invoice_no,
                invoice_no,
                invoice_no,
                json.dumps([manual_link]),
                json.dumps({"normalized_payload": {
                    "id": "invoice-shared-contexts",
                    "invoice_type": "input",
                    "invoice_no": invoice_no,
                    "digital_invoice_no": invoice_no,
                    "source_unique_key": invoice_no,
                    "amount": "910.00",
                    "signed_amount": "910.00",
                    "status": "pending",
                    "source_links": [manual_link],
                }}),
            ),
        )
        repository = PostgresOAAttachmentInvoiceRepository(self.connection)

        rows = repository.list_promotion_source_rows(
            canonical_keys={invoice_no},
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )
        report = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
        ).promote_confirmed_invoice_identity_keys(
            {invoice_no},
            configured_mode=OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
            parser_version="parser-current",
            cache_schema_version="schema-current",
        )
        persisted = self.connection.fetch_one(
            """
            select source_links,
                   raw_payload->'normalized_payload'->'source_links' as raw_source_links
            from app.invoices
            where legacy_mongo_id = 'invoice-shared-contexts'
            """
        )
        oa_links = [
            link
            for link in persisted["source_links"]
            if link.get("source_type") == "oa_attachment_invoice"
        ]

        self.assertEqual(
            {row["source_expense_item_id"] for row in rows},
            {"oa-shared:item:0", "oa-shared:item:1"},
        )
        self.assertEqual(report["summary"]["affected_invoice_count"], 1)
        self.assertEqual(
            {link["source_expense_item_id"] for link in oa_links},
            {"oa-shared:item:0", "oa-shared:item:1"},
        )
        self.assertEqual(persisted["raw_source_links"], persisted["source_links"])

    def test_structured_owner_blocks_stale_raw_and_cas_keeps_mirror_exact(self) -> None:
        invoice_no = "26532000000000000911"
        manual_link = {
            "source_type": "manual_invoice_import",
            "source_id": "file-current",
        }
        explicit_link = {
            "source_type": "oa_expense_item_invoice",
            "source_expense_item_id": "oa-owner-1:item:0:explicit",
            "derived_from_oa_id": "oa-owner-1",
        }
        structured_links = [manual_link, explicit_link]
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                source_unique_key, amount, signed_amount, status, tags,
                source_links, raw_payload
            ) values (
                'invoice-structured-owner', 'input', %s, %s, %s,
                911, 911, 'pending', array['structured-tag'], %s::jsonb, %s::jsonb
            )
            """,
            (
                invoice_no,
                invoice_no,
                invoice_no,
                json.dumps(structured_links),
                json.dumps({
                    "top_level_keep": "top-level-value",
                    "normalized_payload": {
                        "id": "invoice-structured-owner",
                        "invoice_type": "input",
                        "invoice_no": invoice_no,
                        "digital_invoice_no": invoice_no,
                        "source_unique_key": invoice_no,
                        "amount": "911.00",
                        "signed_amount": "911.00",
                        "status": "pending",
                        "tags": ["stale-raw-tag"],
                        "source_links": [manual_link],
                        "keep_me": "normalized-value",
                    },
                }),
            ),
        )
        attachment = _attachment(
            invoice_no,
            "911.00",
            "oa-owner-2:item:0:new",
            "owner-2.pdf",
        )
        attachment["source_attachment_key"] = "oa-owner-2:owner-2.pdf"
        candidate = OAAttachmentInvoiceCandidate(
            cache_source_attachment_key="oa-owner-2:owner-2.pdf",
            invoice_index=0,
            attachment_invoice=attachment,
            oa_form_id="oa-owner-2",
            oa_row_id="oa-owner-2",
            source_workbench_row_id="oa-owner-2:invoice:0",
            context={"month": "2026-06"},
        )
        repository = PostgresOAAttachmentInvoiceRepository(self.connection)
        service = OAAttachmentInvoicePromotionService(invoice_repository=repository)

        blocked = service.promote_candidates(
            [candidate],
            promotion_mode=OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
            apply=True,
            persist_matching_dirty=False,
        )
        before_cas = self.connection.fetch_one(
            """
            select source_links,
                   raw_payload->'normalized_payload'->'source_links' as raw_source_links
            from app.invoices
            where legacy_mongo_id = 'invoice-structured-owner'
            """
        )

        self.assertEqual(blocked["summary"]["affected_invoice_count"], 0)
        self.assertEqual(blocked["reason_counts"], {"source_context_conflict": 1})
        self.assertEqual(before_cas["source_links"], structured_links)
        self.assertEqual(before_cas["raw_source_links"], [manual_link])

        with self.connection.transaction() as transaction:
            core = PostgresCoreRepository(transaction)
            snapshot = core.load_invoice_source_links_for_update(
                transaction,
                invoice_id="invoice-structured-owner",
            )
            self.assertIsNotNone(snapshot)
            core.update_invoice_source_links_cas(
                transaction,
                [{
                    "invoice_id": "invoice-structured-owner",
                    "before_source_links": snapshot["stored_source_links"],
                    "source_links": snapshot["source_links"],
                }],
                actor_id="integration-test",
                reason="sync provenance mirror",
            )

        after_cas = self.connection.fetch_one(
            """
            select source_links,
                   raw_payload->'normalized_payload'->'source_links' as raw_source_links,
                   raw_payload->'normalized_payload'->>'keep_me' as keep_me,
                   raw_payload->>'top_level_keep' as top_level_keep
            from app.invoices
            where legacy_mongo_id = 'invoice-structured-owner'
            """
        )
        self.assertEqual(after_cas["source_links"], structured_links)
        self.assertEqual(after_cas["raw_source_links"], structured_links)
        self.assertEqual(after_cas["keep_me"], "normalized-value")
        self.assertEqual(after_cas["top_level_keep"], "top-level-value")

        self.connection.execute(
            """
            insert into app.oa_source_aliases(
                alias_row_id, canonical_row_id, reason, evidence_hash, status
            ) values (
                'oa-owner-2', 'oa-owner-1', 'integration test',
                'structured-source-links-authority', 'active'
            )
            """
        )
        allowed = service.promote_candidates(
            [candidate],
            promotion_mode=OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
            apply=True,
            persist_matching_dirty=False,
        )
        persisted = self.connection.fetch_one(
            """
            select source_links,
                   raw_payload->'normalized_payload'->'source_links' as raw_source_links
            from app.invoices
            where legacy_mongo_id = 'invoice-structured-owner'
            """
        )

        self.assertEqual(allowed["summary"]["affected_invoice_count"], 1)
        self.assertIn(explicit_link, persisted["source_links"])
        self.assertTrue(any(
            link.get("source_type") == "oa_attachment_invoice"
            and link.get("derived_from_oa_id") == "oa-owner-2"
            for link in persisted["source_links"]
        ))
        self.assertEqual(persisted["raw_source_links"], persisted["source_links"])

    def test_first_formal_import_preserves_fresh_downstream_state(self) -> None:
        invoice_no = "26532000000000000912"
        oa_link = {
            "source_type": "oa_attachment_invoice",
            "source_id": "oa-owner-1:invoice.pdf",
            "derived_from_oa_id": "oa-owner-1",
            "source_expense_item_id": "oa-owner-1:item:0",
        }
        etc_link = {
            "source_type": "etc_invoice_import",
            "source_id": "etc-invoice-1",
            "batch_id": "etc-import-1",
        }
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                source_unique_key, invoice_date, invoice_month, counterparty_name, seller_name,
                buyer_name, amount, signed_amount, written_off_amount,
                tax_amount, total_with_tax, legacy_source_batch_id, oa_form_id,
                etc_invoice_id, workbench_visibility, status, tags, source_links,
                raw_payload
            ) values (
                'invoice-oa-first', 'input', %s, %s, %s, '2026-06-01', '2026-06-01',
                'OA识别销方', 'OA识别销方', 'OA识别购方', 912, 912, 312,
                12, 912, 'oa-source-batch', 'oa-owner-1', 'etc-invoice-1',
                'hidden_after_etc_submission', 'partially_reconciled',
                array['OA附件', 'ETC'], %s::jsonb, %s::jsonb
            )
            """,
            (
                invoice_no,
                invoice_no,
                invoice_no,
                json.dumps([oa_link, etc_link]),
                json.dumps({
                    "normalized_payload": {
                        "id": "invoice-oa-first",
                        "invoice_type": "input",
                        "invoice_no": invoice_no,
                        "digital_invoice_no": invoice_no,
                        "source_unique_key": invoice_no,
                        "invoice_date": "2026-06-01",
                        "seller_name": "OA识别销方",
                        "buyer_name": "OA识别购方",
                        "amount": "912.00",
                        "signed_amount": "912.00",
                        "tax_amount": "12.00",
                        "total_with_tax": "912.00",
                        "written_off_amount": "312.00",
                        "oa_form_id": "oa-owner-1",
                        "derived_from_oa_id": "oa-owner-1",
                        "source_attachment_key": "oa-owner-1:invoice.pdf",
                        "source_attachment_name": "invoice.pdf",
                        "source_expense_item_id": "oa-owner-1:item:0",
                        "source_expense_row_index": "0",
                        "etc_invoice_id": "etc-invoice-1",
                        "etc_import_batch_id": "etc-import-1",
                        "etc_submission_batch_id": "etc-submit-1",
                        "etc_submission_status": "submitted",
                        "workbench_visibility": "hidden_after_etc_submission",
                        "status": "partially_reconciled",
                        "invoice_status_from_source": "valid",
                        "tags": ["OA附件", "ETC"],
                        "source_links": [oa_link, etc_link],
                    }
                }),
            ),
        )
        manual_link = {
            "source_type": "manual_invoice_import",
            "source_id": invoice_no,
            "batch_id": "batch-formal-first",
        }
        incoming = {
            "id": "invoice-oa-first",
            "invoice_type": "input",
            "invoice_no": invoice_no,
            "digital_invoice_no": invoice_no,
            "source_unique_key": invoice_no,
            "invoice_date": "2026-06-02",
            "counterparty": {"id": "excel-counterparty", "name": "Excel权威销方"},
            "seller_name": "Excel权威销方",
            "buyer_name": "Excel权威购方",
            "amount": "1000.00",
            "signed_amount": "1000.00",
            "tax_amount": "130.00",
            "total_with_tax": "1130.00",
            "written_off_amount": "0.00",
            "source_batch_id": "batch-formal-first",
            "workbench_visibility": "visible",
            "status": "pending",
            "invoice_status_from_source": "cancelled",
            "tags": ["人工导入"],
            "source_links": [manual_link],
        }

        with self.connection.transaction() as transaction:
            core = PostgresCoreRepository(transaction)
            core.prepare_confirmed_invoice_upserts_in_transaction(
                transaction,
                imports_snapshot={"invoices": {"invoice-oa-first": incoming}},
            )
            core.save_import_delta_in_transaction(
                transaction,
                imports_snapshot={"invoices": {"invoice-oa-first": incoming}},
                file_imports_snapshot={},
            )

        persisted = self.connection.fetch_one(
            """
            select seller_name, buyer_name, amount, signed_amount, tax_amount,
                   total_with_tax, written_off_amount, legacy_source_batch_id,
                   oa_form_id, etc_invoice_id, workbench_visibility, status,
                   tags, source_links, raw_payload->'normalized_payload' as normalized
            from app.invoices
            where legacy_mongo_id = 'invoice-oa-first'
            """
        )
        normalized = persisted["normalized"]

        self.assertEqual(persisted["seller_name"], "Excel权威销方")
        self.assertEqual(persisted["buyer_name"], "Excel权威购方")
        self.assertEqual(persisted["amount"], Decimal("1000.00"))
        self.assertEqual(persisted["tax_amount"], Decimal("130.00"))
        self.assertEqual(persisted["total_with_tax"], Decimal("1130.00"))
        self.assertEqual(persisted["legacy_source_batch_id"], "batch-formal-first")
        self.assertEqual(persisted["written_off_amount"], Decimal("312.00"))
        self.assertEqual(persisted["oa_form_id"], "oa-owner-1")
        self.assertEqual(persisted["etc_invoice_id"], "etc-invoice-1")
        self.assertEqual(
            persisted["workbench_visibility"],
            "hidden_after_etc_submission",
        )
        self.assertEqual(persisted["status"], "partially_reconciled")
        self.assertEqual(persisted["tags"], ["OA附件", "ETC", "人工导入"])
        self.assertEqual(
            [link["source_type"] for link in persisted["source_links"]],
            ["oa_attachment_invoice", "etc_invoice_import", "manual_invoice_import"],
        )
        self.assertEqual(normalized["seller_name"], "Excel权威销方")
        self.assertEqual(normalized["amount"], "1000.00")
        self.assertEqual(Decimal(normalized["written_off_amount"]), Decimal("312.00"))
        self.assertEqual(normalized["oa_form_id"], "oa-owner-1")
        self.assertEqual(normalized["source_expense_item_id"], "oa-owner-1:item:0")
        self.assertEqual(normalized["etc_invoice_id"], "etc-invoice-1")
        self.assertEqual(normalized["etc_import_batch_id"], "etc-import-1")
        self.assertEqual(normalized["etc_submission_batch_id"], "etc-submit-1")
        self.assertEqual(normalized["etc_submission_status"], "submitted")
        self.assertEqual(normalized["workbench_visibility"], "hidden_after_etc_submission")
        self.assertEqual(normalized["status"], "partially_reconciled")
        self.assertEqual(normalized["invoice_status_from_source"], "cancelled")
        self.assertEqual(normalized["source_links"], persisted["source_links"])


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
