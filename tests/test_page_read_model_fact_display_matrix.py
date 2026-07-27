from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY  # noqa: E402
from fin_ops_platform.tools.http_slo_probe import DEFAULT_API_PROBES  # noqa: E402


MATRIX_PATH = REPO_ROOT / "docs" / "dev" / "page-read-model-fact-display-matrix.json"
PAGE_REGISTRY_PATH = REPO_ROOT / "web" / "src" / "app" / "pageRegistry.tsx"
DIRECT_CANONICAL_FRONTEND_PATHS = (
    "web/src/features/workbench",
    "web/src/features/bankDetails",
    "web/src/features/oaPendingPayments",
    "web/src/features/bankFlowRuleBatches",
    "web/src/features/batchAccounting",
    "web/src/features/etc",
    "web/src/features/pendingInvoices",
    "web/src/features/inputInvoiceUsage",
    "web/src/features/outputInvoiceCollections",
    "web/src/features/turnoverLedger",
    "web/src/pages/ReconciliationWorkbenchPage.tsx",
    "web/src/pages/BankDetailsPage.tsx",
    "web/src/pages/OaPendingPaymentsPage.tsx",
    "web/src/pages/BankFlowRuleBatchPage.tsx",
    "web/src/pages/BatchAccountingPage.tsx",
    "web/src/pages/EtcTicketManagementPage.tsx",
    "web/src/pages/TaxOffsetPage.tsx",
    "web/src/pages/PendingInvoicesPage.tsx",
    "web/src/pages/InputInvoiceUsagePage.tsx",
    "web/src/pages/OutputInvoiceCollectionsPage.tsx",
    "web/src/pages/CostStatisticsPage.tsx",
    "web/src/pages/TurnoverLedgerPage.tsx",
)

RELATION_DISPLAY_PAGE_KEYS = {
    "reconciliation-workbench",
    "cost-statistics",
    "bank-details",
    "oa-pending-payments",
    "bank-flow-rule-batches",
    "batch-accounting",
    "turnover-ledger",
    "pending-invoices",
    "input-invoice-usage",
    "output-invoice-collections",
}

DIRECT_CANONICAL_PAGE_KEYS = {
    "reconciliation-workbench",
    "bank-details",
    "oa-pending-payments",
    "bank-flow-rule-batches",
    "batch-accounting",
    "cost-statistics",
    "turnover-ledger",
    "etc-tickets",
    "tax-offset",
    "pending-invoices",
    "input-invoice-usage",
    "output-invoice-collections",
    "imports.bank-transactions",
    "imports.invoices",
    "imports.etc-invoices",
    "settings",
}
ZERO_OWN_READ_MODEL_PAGE_KEYS = DIRECT_CANONICAL_PAGE_KEYS | {"app-health-operations"}

def _load_matrix_rows() -> list[dict[str, Any]]:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    return list(payload["rows"])


def _page_registry_routes() -> dict[str, str]:
    source = PAGE_REGISTRY_PATH.read_text(encoding="utf-8")
    matches = re.finditer(
        r'\{\s*path:\s*"(?P<route>[^"]+)"\s*,\s*pageKey:\s*"(?P<page_key>[^"]+)"',
        source,
        flags=re.DOTALL,
    )
    return {match.group("page_key"): match.group("route") for match in matches}


class PageReadModelFactDisplayMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = _load_matrix_rows()
        self.rows_by_page_key = {str(row["page_key"]): row for row in self.rows}

    def test_every_registered_page_has_one_matrix_row_with_matching_route(self) -> None:
        registry_routes = _page_registry_routes()
        matrix_page_keys = set(self.rows_by_page_key)
        registry_page_keys = set(registry_routes)

        self.assertEqual(matrix_page_keys - registry_page_keys, set())
        self.assertEqual(registry_page_keys - matrix_page_keys, set())
        self.assertEqual(len(self.rows), len(matrix_page_keys))

        for page_key, route in registry_routes.items():
            self.assertEqual(self.rows_by_page_key[page_key]["route"], route)

    def test_read_models_and_freshness_probes_are_current_runtime_contracts(self) -> None:
        valid_read_model_keys = set(APP_STATUS_READ_MODEL_REGISTRY)
        valid_probe_names = {probe.name for probe in DEFAULT_API_PROBES}

        for row in self.rows:
            page_key = row["page_key"]
            read_model_keys = list(row.get("read_model_keys", []))
            probe_names = list(row.get("freshness_probe_names", []))

            if page_key in ZERO_OWN_READ_MODEL_PAGE_KEYS:
                self.assertEqual(read_model_keys, [], page_key)
            else:
                self.assertTrue(read_model_keys, page_key)
            self.assertTrue(probe_names, page_key)
            self.assertEqual(sorted(set(read_model_keys)), sorted(read_model_keys), page_key)
            self.assertEqual(sorted(set(probe_names)), sorted(probe_names), page_key)
            self.assertEqual(set(read_model_keys) - valid_read_model_keys, set(), page_key)
            self.assertEqual(set(probe_names) - valid_probe_names, set(), page_key)

    def test_current_page_matrix_does_not_reference_legacy_no_oa_page_read_model(self) -> None:
        matrix_text = MATRIX_PATH.read_text(encoding="utf-8")
        self.assertNotIn("no_oa_bank_batch", matrix_text)
        self.assertNotIn("No OA", matrix_text)

        bank_flow_row = self.rows_by_page_key["bank-flow-rule-batches"]
        self.assertEqual(bank_flow_row["read_model_keys"], [])
        self.assertEqual(bank_flow_row["route"], "/bank-flow-rule-batches")

    def test_direct_canonical_frontends_do_not_reintroduce_page_read_model_runtime(self) -> None:
        forbidden = (
            "readModelStatus",
            "read_model_status",
            "readModelVersion",
            "read_model_version",
            "sourceVersions",
            "source_versions",
            "refreshEnqueued",
            "refresh_enqueued",
            "/refresh-status",
            "operationBarrier",
            "operation_barrier",
        )
        for relative_path in DIRECT_CANONICAL_FRONTEND_PATHS:
            path = REPO_ROOT / relative_path
            files = sorted(path.rglob("*.ts*")) if path.is_dir() else [path]
            self.assertTrue(files, relative_path)
            for source_path in files:
                source = source_path.read_text(encoding="utf-8")
                for marker in forbidden:
                    with self.subTest(path=relative_path, marker=marker):
                        self.assertNotIn(marker, source)

        for relative_path in (
            "web/src/components/common/PageAuditIcon.tsx",
            "web/src/components/common/PageBusinessAuditIcon.tsx",
        ):
            self.assertNotIn("readModelStatus", (REPO_ROOT / relative_path).read_text(encoding="utf-8"))

    def test_fact_sources_and_relation_sources_are_declared_for_each_page(self) -> None:
        for row in self.rows:
            page_key = row["page_key"]
            self.assertTrue(row.get("fact_sources"), page_key)
            self.assertTrue(row.get("production_readonly_gates"), page_key)

            relation_sources = set(row.get("pairing_relation_fact_sources", []))
            if page_key in DIRECT_CANONICAL_PAGE_KEYS & RELATION_DISPLAY_PAGE_KEYS:
                self.assertEqual(relation_sources, {"app.workbench_pair_relations"}, page_key)
            elif page_key in RELATION_DISPLAY_PAGE_KEYS:
                self.assertIn("app.workbench_pair_relations", relation_sources, page_key)
                self.assertIn("read_model.workbench_relation_rows", relation_sources, page_key)
            else:
                self.assertEqual(relation_sources, set(), page_key)

        etc_row = self.rows_by_page_key["etc-tickets"]
        self.assertTrue(etc_row.get("internal_relation_fact_sources"))
        self.assertNotIn("app.workbench_pair_relations", etc_row["internal_relation_fact_sources"])

    def test_production_gates_point_to_declared_freshness_probes(self) -> None:
        for row in self.rows:
            page_key = row["page_key"]
            probe_names = set(row["freshness_probe_names"])
            expected_gates = {f"http_slo_probe:{probe_name}" for probe_name in probe_names}
            declared_gates = set(row["production_readonly_gates"])

            self.assertEqual(declared_gates, expected_gates, page_key)

    def test_deterministic_evidence_files_exist_and_contain_required_business_markers(self) -> None:
        for row in self.rows:
            page_key = row["page_key"]
            evidence_entries = list(row.get("deterministic_evidence", []))
            self.assertTrue(evidence_entries, page_key)

            for evidence in evidence_entries:
                evidence_path = REPO_ROOT / evidence["path"]
                self.assertTrue(evidence_path.exists(), f"{page_key}: {evidence_path}")
                evidence_text = evidence_path.read_text(encoding="utf-8")
                markers = list(evidence.get("required_markers", []))
                self.assertTrue(markers, f"{page_key}: {evidence_path}")
                for marker in markers:
                    self.assertIn(marker, evidence_text, f"{page_key}: {evidence['path']} missing {marker!r}")


if __name__ == "__main__":
    unittest.main()
