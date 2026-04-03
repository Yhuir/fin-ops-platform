import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService


class MutableOAAdapter:
    def __init__(self, seed_data: dict[str, list[OAApplicationRecord]]) -> None:
        self._seed_data = seed_data

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        return list(self._seed_data.get(month, []))


class WorkbenchQueryServiceTests(unittest.TestCase):
    def test_open_invoice_rows_include_ignore_action(self) -> None:
        service = WorkbenchQueryService()

        payload = service.get_workbench("2026-03")
        invoice_row = payload["open"]["invoice"][0]

        self.assertIn("ignore", invoice_row["available_actions"])

    def test_refreshes_oa_rows_for_month_and_preserves_manual_relation_state(self) -> None:
        adapter = MutableOAAdapter(
            {
                "2026-03": [
                    OAApplicationRecord(
                        id="oa-real-001",
                        month="2026-03",
                        section="open",
                        case_id=None,
                        applicant="刘际涛",
                        project_name="云南溯源科技",
                        apply_type="支付申请",
                        amount="199",
                        counterparty_name="中国电信股份有限公司昆明分公司",
                        reason="托收电话费及宽带",
                        relation_code="pending_match",
                        relation_label="待找流水与发票",
                        relation_tone="warn",
                    )
                ]
            }
        )
        service = WorkbenchQueryService(oa_adapter=adapter)

        first_payload = service.get_workbench("2026-03")
        oa_row = first_payload["open"]["oa"][0]
        self.assertEqual(oa_row["applicant"], "刘际涛")
        self.assertEqual(oa_row["amount"], "199")

        row_record = service.get_row_record("oa-real-001")
        row_record["case_id"] = "CASE-MANUAL-001"
        row_record["oa_bank_relation"] = {"code": "fully_linked", "label": "完全关联", "tone": "success"}
        row_record["_section"] = "paired"
        row_record["available_actions"] = service.available_actions("oa", "paired")

        adapter._seed_data["2026-03"] = [
            OAApplicationRecord(
                id="oa-real-001",
                month="2026-03",
                section="open",
                case_id=None,
                applicant="刘际涛-更新",
                project_name="云南溯源科技",
                apply_type="支付申请",
                amount="299",
                counterparty_name="中国电信股份有限公司昆明分公司",
                reason="托收电话费及宽带-更新",
                relation_code="pending_match",
                relation_label="待找流水与发票",
                relation_tone="warn",
            )
        ]

        refreshed_payload = service.get_workbench("2026-03")
        refreshed_row = refreshed_payload["paired"]["oa"][0]
        self.assertEqual(refreshed_row["applicant"], "刘际涛-更新")
        self.assertEqual(refreshed_row["amount"], "299")
        self.assertEqual(refreshed_row["case_id"], "CASE-MANUAL-001")
        self.assertEqual(refreshed_row["oa_bank_relation"]["code"], "fully_linked")


if __name__ == "__main__":
    unittest.main()
