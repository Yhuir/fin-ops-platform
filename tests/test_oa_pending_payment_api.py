from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from fin_ops_platform.app.routes_oa_pending_payments import OaPendingPaymentApiRoutes
from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentQueryService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = records

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self.records)

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]


class OaPendingPaymentApiTests(unittest.TestCase):
    def test_rows_filter_options_and_detail_routes_delegate_to_module_route_facade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            bank = BankTransaction(
                id="bank-api",
                account_no="622200001234",
                txn_direction=TransactionDirection.OUTFLOW,
                counterparty_name_raw="API供应商",
                amount=Decimal("100.00"),
                signed_amount=Decimal("-100.00"),
                txn_date="2026-05-21",
                trade_time="2026-05-21 10:00:00",
            )
            pair_service = WorkbenchPairRelationService()
            pair_service.create_active_relation(
                case_id="case-api",
                row_ids=["oa-api", "bank-api"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            import_service = ImportNormalizationService(existing_transactions=[bank])
            service = OaPendingPaymentQueryService(
                import_service=import_service,
                pair_relation_service=pair_service,
                oa_projection=StaticOAProjection([self._oa("oa-api", "张三", "100.00")]),
            )
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(service)

            rows_response = app.handle_request("GET", "/api/oa-pending-payments/rows?page=1&page_size=20")
            filter_response = app.handle_request("GET", "/api/oa-pending-payments/filter-options")
            oa_response = app.handle_request("GET", "/api/oa-pending-payments/oa/oa-api/detail")
            bank_response = app.handle_request("GET", "/api/oa-pending-payments/bank-transactions/bank-api/detail")
            row_id = json.loads(rows_response.body)["rows"][0]["id"]
            relation_response = app.handle_request(
                "GET",
                f"/api/oa-pending-payments/rows/{row_id}/relation-details?kind=bank",
            )

        self.assertEqual(rows_response.status_code, 200)
        self.assertEqual(filter_response.status_code, 200)
        self.assertEqual(oa_response.status_code, 200)
        self.assertEqual(bank_response.status_code, 200)
        self.assertEqual(relation_response.status_code, 200)
        self.assertEqual(json.loads(rows_response.body)["rows"][0]["paymentStatus"]["code"], "paid")
        self.assertIn("oa_applicant", [field["field"] for field in json.loads(filter_response.body)["fields"]])
        self.assertEqual(json.loads(oa_response.body)["id"], "oa-api")
        self.assertEqual(json.loads(bank_response.body)["id"], "bank-api")
        self.assertEqual(json.loads(relation_response.body)["kind"], "bank")

    def test_routes_return_structured_validation_and_not_found_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            service = OaPendingPaymentQueryService(
                import_service=ImportNormalizationService(),
                pair_relation_service=WorkbenchPairRelationService(),
                oa_projection=StaticOAProjection([]),
            )
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(service)

            invalid_page = app.handle_request("GET", "/api/oa-pending-payments/rows?page=0")
            invalid_sort = app.handle_request("GET", "/api/oa-pending-payments/rows?sort_field=bad")
            missing_oa = app.handle_request("GET", "/api/oa-pending-payments/oa/missing/detail")

        self.assertEqual(invalid_page.status_code, 400)
        self.assertEqual(json.loads(invalid_page.body)["error"]["code"], "invalid_paging")
        self.assertEqual(invalid_sort.status_code, 400)
        self.assertEqual(json.loads(invalid_sort.body)["error"]["code"], "invalid_sort_field")
        self.assertEqual(missing_oa.status_code, 404)
        self.assertEqual(json.loads(missing_oa.body)["error"]["code"], "oa_not_found")

    @staticmethod
    def _oa(oa_id: str, applicant: str, amount: str) -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month="2026-05",
            section="审批通过",
            case_id=None,
            applicant=applicant,
            project_name="API项目",
            apply_type="报销",
            amount=amount,
            counterparty_name="API供应商",
            reason="API测试",
            relation_code="",
            relation_label="",
            relation_tone="",
            project_name_display="API项目",
        )


if __name__ == "__main__":
    unittest.main()
