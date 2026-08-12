from __future__ import annotations

import re
import unittest
from pathlib import Path

from fin_ops_platform.services.page_audit_registry import (
    PAGE_AUDIT_CONTRACT_REVISION,
    PAGE_AUDIT_REGISTRY,
    legacy_domain_page_key,
    page_audit_registration,
)

ROOT = Path(__file__).resolve().parents[1]
PAGE_REGISTRY_PATH = ROOT / "web" / "src" / "app" / "pageRegistry.tsx"
INPUT_PAGE_PATH = ROOT / "web" / "src" / "pages" / "InputInvoiceUsagePage.tsx"
OUTPUT_PAGE_PATH = ROOT / "web" / "src" / "pages" / "OutputInvoiceCollectionsPage.tsx"
APP_HEALTH_PAGE_PATH = ROOT / "web" / "src" / "pages" / "AppHealthOperationsPage.tsx"
SYSTEM_AUDIT_PATH = (
    ROOT
    / "backend"
    / "src"
    / "fin_ops_platform"
    / "services"
    / "postgres_repositories"
    / "app_health_system_audit.py"
)


class PageAuditRegistryTests(unittest.TestCase):
    def test_registry_exactly_covers_frontend_page_registry(self) -> None:
        source = PAGE_REGISTRY_PATH.read_text(encoding="utf-8")
        frontend_page_keys = re.findall(r'pageKey:\s*"([^"]+)"', source)

        self.assertEqual(len(frontend_page_keys), len(set(frontend_page_keys)))
        self.assertEqual(set(PAGE_AUDIT_REGISTRY), set(frontend_page_keys))
        self.assertEqual(len(PAGE_AUDIT_REGISTRY), 18)

    def test_ready_and_unavailable_pages_are_explicit_and_fail_closed(self) -> None:
        ready = [item for item in PAGE_AUDIT_REGISTRY.values() if item.availability == "ready"]
        unavailable = [item for item in PAGE_AUDIT_REGISTRY.values() if item.availability == "unavailable"]

        self.assertEqual(len(ready), 18)
        self.assertEqual(len(unavailable), 0)
        self.assertEqual(PAGE_AUDIT_REGISTRY["tax-offset"].executor, "tax_offset")
        self.assertFalse(PAGE_AUDIT_REGISTRY["tax-offset"].relation_proof_required)
        self.assertEqual(PAGE_AUDIT_REGISTRY["etc-tickets"].executor, "etc_tickets")
        self.assertEqual(PAGE_AUDIT_REGISTRY["etc-tickets"].read_model_keys, ())
        self.assertTrue(PAGE_AUDIT_REGISTRY["etc-tickets"].relation_proof_required)
        self.assertEqual(PAGE_AUDIT_REGISTRY["settings"].executor, "settings")
        self.assertEqual(PAGE_AUDIT_REGISTRY["settings"].read_model_keys, ())
        self.assertFalse(PAGE_AUDIT_REGISTRY["settings"].relation_proof_required)
        self.assertEqual(PAGE_AUDIT_REGISTRY["imports.bank-transactions"].executor, "bank_transaction_import")
        self.assertEqual(PAGE_AUDIT_REGISTRY["imports.bank-transactions"].read_model_keys, ())
        self.assertFalse(PAGE_AUDIT_REGISTRY["imports.bank-transactions"].relation_proof_required)
        self.assertEqual(PAGE_AUDIT_REGISTRY["imports.invoices"].executor, "invoice_import")
        self.assertEqual(PAGE_AUDIT_REGISTRY["imports.etc-invoices"].executor, "etc_import")
        self.assertEqual(PAGE_AUDIT_REGISTRY["imports.etc-invoices"].read_model_keys, ())
        self.assertEqual(PAGE_AUDIT_REGISTRY["imports.invoices"].read_model_keys, ())
        self.assertFalse(PAGE_AUDIT_REGISTRY["imports.invoices"].relation_proof_required)
        self.assertEqual(PAGE_AUDIT_REGISTRY["app-health-operations"].executor, "system")
        self.assertEqual(PAGE_AUDIT_REGISTRY["app-health-operations"].read_model_keys, ())
        self.assertFalse(PAGE_AUDIT_REGISTRY["app-health-operations"].relation_proof_required)
        self.assertEqual(PAGE_AUDIT_REGISTRY["app-health-operations"].external_evidence_keys, ())
        self.assertEqual(PAGE_AUDIT_REGISTRY["operation-history"].executor, "operation_history")
        self.assertEqual(PAGE_AUDIT_REGISTRY["operation-history"].external_evidence_keys, ())
        direct_page_keys = {
            "reconciliation-workbench",
            "cost-statistics",
            "bank-details",
            "oa-pending-payments",
            "bank-flow-rule-batches",
            "batch-accounting",
            "turnover-ledger",
            "etc-tickets",
            "tax-offset",
            "pending-invoices",
            "input-invoice-usage",
            "output-invoice-collections",
        }
        self.assertTrue(
            all(PAGE_AUDIT_REGISTRY[page_key].read_model_keys == () for page_key in direct_page_keys)
        )
        self.assertTrue(PAGE_AUDIT_REGISTRY["reconciliation-workbench"].relation_proof_required)
        self.assertEqual(PAGE_AUDIT_REGISTRY["imports.bank-transactions"].external_evidence_keys, ("bank",))
        self.assertEqual(PAGE_AUDIT_REGISTRY["imports.invoices"].external_evidence_keys, ("invoice",))
        self.assertEqual(PAGE_AUDIT_REGISTRY["imports.etc-invoices"].external_evidence_keys, ("etc",))
        self.assertEqual(
            set(PAGE_AUDIT_REGISTRY["reconciliation-workbench"].external_evidence_keys),
            {"bank", "oa", "invoice", "etc"},
        )
        self.assertTrue(
            all(
                registration.external_evidence_keys
                or registration.page_key in {"app-health-operations", "operation-history"}
                for registration in PAGE_AUDIT_REGISTRY.values()
            )
        )
        self.assertTrue(all(item.executor != "unavailable" for item in ready))
        self.assertTrue(all(item.executor == "unavailable" and item.unavailable_reason for item in unavailable))
        self.assertTrue(all(item.contract_revision == PAGE_AUDIT_CONTRACT_REVISION for item in PAGE_AUDIT_REGISTRY.values()))

    def test_legacy_generic_domains_map_to_their_page_keys(self) -> None:
        self.assertEqual(legacy_domain_page_key("bank_details"), "bank-details")
        self.assertEqual(legacy_domain_page_key("pending_invoices"), "pending-invoices")
        self.assertIsNone(legacy_domain_page_key("unknown"))

    def test_unknown_page_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported page audit page"):
            page_audit_registration("unknown")

    def test_invoice_pages_do_not_call_specialized_audit_clients(self) -> None:
        input_source = INPUT_PAGE_PATH.read_text(encoding="utf-8")
        output_source = OUTPUT_PAGE_PATH.read_text(encoding="utf-8")

        self.assertIn('pageKey="input-invoice-usage"', input_source)
        self.assertIn('pageKey="output-invoice-collections"', output_source)
        self.assertNotIn("fetchInputInvoiceUsageAudit", input_source)
        self.assertNotIn("fetchOutputInvoiceCollectionAudit", output_source)

    def test_specialized_invoice_audit_http_paths_are_removed_from_runtime(self) -> None:
        forbidden = (
            "/api/operations/app-health/input-invoice-usage-audit",
            "/api/operations/app-health/output-invoice-collection-audit",
        )
        runtime_files = [
            *sorted((ROOT / "backend" / "src").rglob("*.py")),
            *sorted((ROOT / "web" / "src").rglob("*.ts")),
            *sorted((ROOT / "web" / "src").rglob("*.tsx")),
        ]
        runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)

        for path in forbidden:
            self.assertNotIn(path, runtime_text)

    def test_app_health_legacy_input_invoice_audit_panel_is_removed(self) -> None:
        source = APP_HEALTH_PAGE_PATH.read_text(encoding="utf-8")

        self.assertIn('fetchPageAudit<AppHealthSystemAuditPayload>("app-health-operations"', source)
        self.assertIn("AppHealthSystemAuditPanel", source)
        self.assertNotIn("InputInvoiceUsageAuditPanel", source)
        self.assertNotIn("runInputUsageAudit", source)
        self.assertNotIn("inputUsageAudit", source)
        self.assertNotIn('fetchPageAudit("input-invoice-usage"', source)

    def test_system_audit_uses_exact_external_evidence_owner_without_legacy_classifier(self) -> None:
        source = SYSTEM_AUDIT_PATH.read_text(encoding="utf-8")

        self.assertIn("audit_external_control_evidence", source)
        self.assertNotRegex(source, r"def\s+_external_evidence\s*\(")


if __name__ == "__main__":
    unittest.main()
