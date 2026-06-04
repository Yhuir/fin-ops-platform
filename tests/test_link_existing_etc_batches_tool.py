from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest

from fin_ops_platform.services.existing_etc_batch_link_service import ExistingEtcBatchLinkSpec
from fin_ops_platform.tools.link_existing_etc_batches import _dry_run_spec


class _IdentityRepository:
    def __init__(self, invoices: dict[str, object]) -> None:
        self._invoices = dict(invoices)
        self.queries: list[str] = []

    def find_invoice_by_identity(self, *, canonical_key: str, suspected_key: str | None = None) -> object | None:
        self.queries.append(str(canonical_key))
        return self._invoices.get(str(canonical_key))


class _ImportServiceWithoutListInvoices(_IdentityRepository):
    def list_invoices(self) -> list[object]:
        raise AssertionError("dry-run must not scan all canonical invoices")


class _EtcService:
    def __init__(self, invoices: dict[str, object]) -> None:
        self._invoices = dict(invoices)
        self.queries: list[tuple[str, ...]] = []

    def list_invoices_by_numbers(self, invoice_numbers: list[str]) -> list[object]:
        self.queries.append(tuple(invoice_numbers))
        return [self._invoices[number] for number in invoice_numbers if number in self._invoices]


class _RelationService:
    def __init__(self, relation: dict[str, object] | None) -> None:
        self._relation = relation

    def get_active_relation_by_case_id(self, case_id: str) -> dict[str, object] | None:
        return self._relation


def _spec(*invoice_numbers: str) -> ExistingEtcBatchLinkSpec:
    return ExistingEtcBatchLinkSpec(
        label="历史 ETC",
        case_id="case-1",
        external_batch_id="etc-batch-1",
        oa_row_id="oa-1",
        oa_amount=Decimal("100.00"),
        invoice_numbers=invoice_numbers,
    )


class LinkExistingEtcBatchesToolTests(unittest.TestCase):
    def test_dry_run_uses_identity_repository_for_canonical_invoice_lookup(self) -> None:
        import_service = _ImportServiceWithoutListInvoices(
            {
                "ETC-001": SimpleNamespace(total_with_tax=Decimal("70.00")),
            }
        )
        app = SimpleNamespace(
            _import_fact_repository=None,
            _import_service=import_service,
            _etc_service=_EtcService({"ETC-002": SimpleNamespace(invoice_number="ETC-002", total_amount=Decimal("30.00"))}),
            _workbench_pair_relation_service=_RelationService({"case_id": "case-1"}),
        )

        payload = _dry_run_spec(app, _spec("ETC-001", "ETC-002"))

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["found_invoice_count"], 2)
        self.assertEqual(payload["invoice_total"], "100.00")
        self.assertEqual(payload["missing_invoice_numbers"], [])
        self.assertEqual(import_service.queries, ["ETC-001", "ETC-002"])

    def test_dry_run_reports_missing_invoice_without_full_scan(self) -> None:
        import_service = _ImportServiceWithoutListInvoices({})
        app = SimpleNamespace(
            _import_fact_repository=None,
            _import_service=import_service,
            _etc_service=_EtcService({}),
            _workbench_pair_relation_service=_RelationService({"case_id": "case-1"}),
        )

        payload = _dry_run_spec(app, _spec("ETC-MISSING"))

        self.assertEqual(payload["status"], "attention")
        self.assertEqual(payload["found_invoice_count"], 0)
        self.assertEqual(payload["missing_invoice_numbers"], ["ETC-MISSING"])
        self.assertEqual(import_service.queries, ["ETC-MISSING"])

    def test_dry_run_returns_unavailable_when_identity_repository_is_missing(self) -> None:
        app = SimpleNamespace(
            _import_fact_repository=None,
            _import_service=SimpleNamespace(),
            _etc_service=_EtcService({}),
            _workbench_pair_relation_service=_RelationService({"case_id": "case-1"}),
        )

        payload = _dry_run_spec(app, _spec("ETC-001"))

        self.assertEqual(payload["status"], "attention")
        self.assertEqual(payload["error"], "identity_repository_unavailable")
        self.assertEqual(payload["invoice_total"], "0.00")
        self.assertEqual(payload["missing_invoice_numbers"], ["ETC-001"])


if __name__ == "__main__":
    unittest.main()
