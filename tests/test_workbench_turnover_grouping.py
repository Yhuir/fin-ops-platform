import json
import unittest

from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.workbench_exception_projection import EXCEPTION_PROJECTION_VERSION
from fin_ops_platform.services.workbench_candidate_grouping import WorkbenchCandidateGroupingService


def _bank_row(
    row_id: str,
    *,
    debit_amount: str = "",
    credit_amount: str = "",
    counterparty_name: str = "贾小花",
    case_id: str | None = None,
    relation_code: str = "pending_match",
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "case_id": case_id,
        "trade_time": "2026-03-05 09:34:42",
        "pay_receive_time": "2026-03-05 09:34:42",
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
        "counterparty_name": counterparty_name,
        "invoice_relation": {
            "code": relation_code,
            "label": "待人工确认" if relation_code == "pending_match" else "完全关联",
            "tone": "warn" if relation_code == "pending_match" else "success",
        },
    }


def _relation(
    relation_id: str,
    *,
    status: str,
    row_ids: list[str],
    sync_to_workbench: bool = True,
    family: str = "company",
    business_type: str = "borrow_in",
) -> dict[str, object]:
    return {
        "relation_id": relation_id,
        "status": status,
        "sync_to_workbench": sync_to_workbench,
        "category_family": family,
        "business_type": business_type,
        "bank_row_ids": row_ids,
        "principal_row_ids": [row_ids[0]] if row_ids else [],
        "settlement_row_ids": row_ids[1:] if len(row_ids) > 1 else [],
        "source": "system" if status != "confirmed" else "manual",
    }


def _open_bank_groups(payload: dict[str, object]) -> list[dict[str, object]]:
    groups = payload["open"]["groups"]
    return [group for group in groups if group.get("bank_rows")]


def _group_bank_ids(group: dict[str, object]) -> list[str]:
    return [str(row["id"]) for row in group.get("bank_rows", [])]


class WorkbenchTurnoverGroupingTests(unittest.TestCase):
    def test_deterministic_turnover_relation_does_not_group_bank_rows_in_workbench(self) -> None:
        service = WorkbenchCandidateGroupingService()

        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                _bank_row("bank-principal", credit_amount="200000.00"),
                _bank_row("bank-settlement", debit_amount="200000.00"),
            ],
            invoice_rows=[],
            turnover_relations=[
                _relation(
                    "turnover_rel_closed",
                    status="deterministic",
                    row_ids=["bank-principal", "bank-settlement"],
                )
            ],
        )

        self.assertFalse([
            group
            for group in payload["open"]["groups"]
            if group.get("group_id") == "turnover:turnover_rel_closed"
        ])
        flattened_bank_ids = [
            bank_id
            for group in _open_bank_groups(payload)
            for bank_id in _group_bank_ids(group)
        ]
        self.assertEqual(flattened_bank_ids.count("bank-principal"), 1)
        self.assertEqual(flattened_bank_ids.count("bank-settlement"), 1)

    def test_confirmed_turnover_relation_does_not_group_bank_rows_in_workbench(self) -> None:
        service = WorkbenchCandidateGroupingService()

        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                _bank_row("bank-lent", debit_amount="50000.00"),
                _bank_row("bank-collected", credit_amount="50000.00"),
            ],
            invoice_rows=[],
            turnover_relations=[
                _relation(
                    "turnover_rel_confirmed",
                    status="confirmed",
                    row_ids=["bank-lent", "bank-collected"],
                    family="personal",
                    business_type="borrow_out",
                )
            ],
        )

        self.assertFalse([
            group
            for group in payload["open"]["groups"]
            if group.get("group_id") == "turnover:turnover_rel_confirmed"
        ])
        self.assertEqual(
            sorted(len(group["bank_rows"]) for group in _open_bank_groups(payload)),
            [1, 1],
        )

    def test_non_syncable_turnover_relations_do_not_group_bank_rows(self) -> None:
        for status in ("suggested", "conflict", "stale", "withdrawn"):
            with self.subTest(status=status):
                service = WorkbenchCandidateGroupingService()

                payload = service.group_payload(
                    "2026-03",
                    oa_rows=[],
                    bank_rows=[
                        _bank_row(f"bank-a-{status}", credit_amount="100.00"),
                        _bank_row(f"bank-b-{status}", debit_amount="100.00"),
                    ],
                    invoice_rows=[],
                    turnover_relations=[
                        _relation(
                            f"turnover_rel_{status}",
                            status=status,
                            row_ids=[f"bank-a-{status}", f"bank-b-{status}"],
                            sync_to_workbench=status in {"deterministic", "confirmed"},
                        )
                    ],
                )

                self.assertFalse(
                    [
                        group
                        for group in payload["open"]["groups"]
                        if group["group_id"] == f"turnover:turnover_rel_{status}"
                    ]
                )
                self.assertEqual(
                    sorted(len(group["bank_rows"]) for group in _open_bank_groups(payload)),
                    [1, 1],
                )

    def test_sync_false_deterministic_relation_does_not_group_bank_rows(self) -> None:
        service = WorkbenchCandidateGroupingService()

        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                _bank_row("bank-a", credit_amount="100.00"),
                _bank_row("bank-b", debit_amount="100.00"),
            ],
            invoice_rows=[],
            turnover_relations=[
                _relation(
                    "turnover_rel_disabled",
                    status="deterministic",
                    row_ids=["bank-a", "bank-b"],
                    sync_to_workbench=False,
                )
            ],
        )

        self.assertEqual(sorted(len(group["bank_rows"]) for group in _open_bank_groups(payload)), [1, 1])

    def test_deterministic_turnover_relation_does_not_extract_bank_rows_from_candidate_group(self) -> None:
        service = WorkbenchCandidateGroupingService()

        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                _bank_row("bank-principal", credit_amount="200000.00", case_id="candidate:old"),
                _bank_row("bank-settlement", debit_amount="200000.00", case_id="candidate:old"),
                _bank_row("bank-unrelated", debit_amount="10.00", case_id="candidate:old"),
            ],
            invoice_rows=[],
            turnover_relations=[
                _relation(
                    "turnover_rel_from_candidate",
                    status="deterministic",
                    row_ids=["bank-principal", "bank-settlement"],
                )
            ],
        )

        self.assertFalse([
            group
            for group in payload["open"]["groups"]
            if group.get("group_id") == "turnover:turnover_rel_from_candidate"
        ])
        candidate_groups = [
            group
            for group in payload["open"]["groups"]
            if group.get("group_id") == "case:candidate:old"
        ]
        self.assertEqual(len(candidate_groups), 1)
        self.assertEqual(
            _group_bank_ids(candidate_groups[0]),
            ["bank-principal", "bank-settlement", "bank-unrelated"],
        )

    def test_turnover_relation_does_not_extract_from_real_open_exception_case(self) -> None:
        service = WorkbenchCandidateGroupingService()

        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    **_bank_row("bank-open-case-principal", credit_amount="200000.00", case_id="WEX-OPEN-1"),
                    "projection_version": EXCEPTION_PROJECTION_VERSION,
                    "projection_kind": "exception_case",
                    "case_status": "open",
                    "relation_mode": "manual_exception",
                },
                {
                    **_bank_row("bank-open-case-settlement", debit_amount="200000.00", case_id="WEX-OPEN-1"),
                    "projection_version": EXCEPTION_PROJECTION_VERSION,
                    "projection_kind": "exception_case",
                    "case_status": "open",
                    "relation_mode": "manual_exception",
                },
            ],
            invoice_rows=[],
            turnover_relations=[
                _relation(
                    "turnover_rel_real_open_case",
                    status="confirmed",
                    row_ids=["bank-open-case-principal", "bank-open-case-settlement"],
                )
            ],
        )

        self.assertFalse([
            group
            for group in payload["open"]["groups"]
            if group.get("group_id") == "turnover:turnover_rel_real_open_case"
        ])
        self.assertTrue([
            group
            for group in payload["open"]["groups"]
            if group.get("group_id") == "case:WEX-OPEN-1"
            and group.get("group_type") == "open_exception"
        ])

    def test_manual_pair_relation_occupied_bank_row_is_not_overridden_by_turnover_relation(self) -> None:
        service = WorkbenchCandidateGroupingService()

        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-1",
                    "type": "oa",
                    "case_id": "WEX-MANUAL-1",
                    "amount": "200000.00",
                    "counterparty_name": "贾小花",
                    "oa_bank_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                }
            ],
            bank_rows=[
                _bank_row(
                    "bank-paired",
                    debit_amount="200000.00",
                    case_id="WEX-MANUAL-1",
                    relation_code="fully_linked",
                ),
                _bank_row("bank-open", credit_amount="200000.00"),
            ],
            invoice_rows=[
                {
                    "id": "invoice-1",
                    "type": "invoice",
                    "case_id": "WEX-MANUAL-1",
                    "amount": "200000.00",
                    "seller_name": "贾小花",
                    "buyer_name": "云南溯源科技有限公司",
                    "invoice_type": "进项发票",
                    "invoice_bank_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                }
            ],
            turnover_relations=[
                _relation(
                    "turnover_rel_overlap",
                    status="confirmed",
                    row_ids=["bank-paired", "bank-open"],
                )
            ],
        )

        self.assertEqual(payload["paired"]["groups"][0]["group_id"], "case:WEX-MANUAL-1")
        self.assertFalse(
            [
                group
                for group in payload["open"]["groups"]
                if group["group_id"] == "turnover:turnover_rel_overlap"
            ]
        )
        open_bank_ids = [
            bank_id
            for group in _open_bank_groups(payload)
            for bank_id in _group_bank_ids(group)
        ]
        self.assertEqual(open_bank_ids, ["bank-open"])

    def test_bank_only_turnover_manual_closure_rows_stay_open_until_three_way_complete(self) -> None:
        service = WorkbenchCandidateGroupingService()

        payload = service.group_payload(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    **_bank_row(
                        "bank-in-1",
                        credit_amount="200000.00",
                        case_id="turnover:rel-1",
                        relation_code="turnover_manual_closure",
                    ),
                    "relation_mode": "turnover_manual_closure",
                },
                {
                    **_bank_row(
                        "bank-out-1",
                        debit_amount="200000.00",
                        case_id="turnover:rel-1",
                        relation_code="turnover_manual_closure",
                    ),
                    "relation_mode": "turnover_manual_closure",
                },
            ],
            invoice_rows=[],
            turnover_relations=[],
        )

        self.assertEqual(payload["paired"]["groups"], [])
        matching_open_groups = [
            group
            for group in payload["open"]["groups"]
            if set(_group_bank_ids(group)) == {"bank-in-1", "bank-out-1"}
        ]
        self.assertEqual(len(matching_open_groups), 1)
        self.assertEqual(matching_open_groups[0]["group_id"], "case:turnover:rel-1")
        self.assertEqual(matching_open_groups[0]["group_type"], "candidate")
        self.assertEqual(matching_open_groups[0]["relation_mode"], "turnover_manual_closure")
        self.assertTrue(all(row["status"] == "open" for row in matching_open_groups[0]["bank_rows"]))

    def test_two_pane_turnover_manual_closure_rows_stay_open_until_invoice_exists(self) -> None:
        service = WorkbenchCandidateGroupingService()

        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-turnover-1",
                    "type": "oa",
                    "case_id": "turnover:rel-2",
                    "payment_date": "2026-03-05",
                    "counterparty_name": "贾小花",
                    "amount": "200000.00",
                    "oa_bank_relation": {"code": "turnover_manual_closure", "label": "外部往来款闭环", "tone": "success"},
                    "relation_mode": "turnover_manual_closure",
                }
            ],
            bank_rows=[
                {
                    **_bank_row(
                        "bank-turnover-1",
                        credit_amount="200000.00",
                        case_id="turnover:rel-2",
                        relation_code="turnover_manual_closure",
                    ),
                    "relation_mode": "turnover_manual_closure",
                }
            ],
            invoice_rows=[],
            turnover_relations=[],
        )

        self.assertEqual(payload["paired"]["groups"], [])
        matching_open_groups = [
            group
            for group in payload["open"]["groups"]
            if group["group_id"] == "case:turnover:rel-2"
        ]
        self.assertEqual(len(matching_open_groups), 1)
        self.assertEqual(matching_open_groups[0]["group_type"], "candidate")
        self.assertEqual(matching_open_groups[0]["relation_mode"], "turnover_manual_closure")
        self.assertEqual([row["id"] for row in matching_open_groups[0].get("oa_rows", [])], ["oa-turnover-1"])
        self.assertEqual(_group_bank_ids(matching_open_groups[0]), ["bank-turnover-1"])
        self.assertEqual(matching_open_groups[0]["bank_rows"][0]["status"], "open")

    def test_two_pane_turnover_manual_closure_with_no_invoice_requirement_is_paired(self) -> None:
        service = WorkbenchCandidateGroupingService()
        requirement_metadata = {
            "requires_oa": True,
            "requires_invoice": False,
            "paired_requirement_source": "no_oa_bank_batch_tag_selection",
            "paired_requirement_tag_codes": ["external_turnover"],
        }

        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-turnover-no-invoice",
                    "type": "oa",
                    "case_id": "turnover:rel-no-invoice",
                    "payment_date": "2026-03-05",
                    "counterparty_name": "贾小花",
                    "amount": "200000.00",
                    "oa_bank_relation": {"code": "turnover_manual_closure", "label": "外部往来款闭环", "tone": "success"},
                    "relation_mode": "turnover_manual_closure",
                    "special_metadata": requirement_metadata,
                }
            ],
            bank_rows=[
                {
                    **_bank_row(
                        "bank-turnover-no-invoice",
                        credit_amount="200000.00",
                        case_id="turnover:rel-no-invoice",
                        relation_code="turnover_manual_closure",
                    ),
                    "relation_mode": "turnover_manual_closure",
                    "special_metadata": requirement_metadata,
                }
            ],
            invoice_rows=[],
            turnover_relations=[],
        )

        self.assertEqual(payload["open"]["groups"], [])
        matching_paired_groups = [
            group
            for group in payload["paired"]["groups"]
            if group["group_id"] == "case:turnover:rel-no-invoice"
        ]
        self.assertEqual(len(matching_paired_groups), 1)
        self.assertEqual(matching_paired_groups[0]["group_type"], "manual_confirmed")
        self.assertEqual(matching_paired_groups[0]["relation_mode"], "turnover_manual_closure")

    def test_three_pane_turnover_manual_closure_rows_render_as_paired_case(self) -> None:
        service = WorkbenchCandidateGroupingService()

        payload = service.group_payload(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-turnover-3",
                    "type": "oa",
                    "case_id": "turnover:rel-3",
                    "payment_date": "2026-03-05",
                    "counterparty_name": "贾小花",
                    "amount": "300000.00",
                    "oa_bank_relation": {"code": "turnover_manual_closure", "label": "收支闭环", "tone": "success"},
                    "relation_mode": "turnover_manual_closure",
                }
            ],
            bank_rows=[
                {
                    **_bank_row(
                        "bank-turnover-3",
                        credit_amount="300000.00",
                        case_id="turnover:rel-3",
                        relation_code="turnover_manual_closure",
                    ),
                    "relation_mode": "turnover_manual_closure",
                }
            ],
            invoice_rows=[
                {
                    "id": "invoice-turnover-3",
                    "type": "invoice",
                    "case_id": "turnover:rel-3",
                    "total_with_tax": "300000.00",
                    "counterparty_name": "贾小花",
                    "invoice_bank_relation": {"code": "turnover_manual_closure", "label": "收支闭环", "tone": "success"},
                    "relation_mode": "turnover_manual_closure",
                }
            ],
            turnover_relations=[],
        )

        self.assertEqual(payload["open"]["groups"], [])
        matching_paired_groups = [
            group
            for group in payload["paired"]["groups"]
            if group["group_id"] == "case:turnover:rel-3"
        ]
        self.assertEqual(len(matching_paired_groups), 1)
        self.assertEqual(matching_paired_groups[0]["group_type"], "manual_confirmed")
        self.assertEqual(matching_paired_groups[0]["relation_mode"], "turnover_manual_closure")


class WorkbenchTurnoverReadModelCacheTests(unittest.TestCase):
    def _import_and_tag_closed_turnover_rows(self, app) -> None:
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank.xlsx",
            imported_by="YNSYLP005",
            rows=[
                {
                    "account_no": "6222000011118106",
                    "account_name": "云南溯源科技有限公司基本户",
                    "txn_date": "2026-03-04",
                    "trade_time": "2026-03-04 13:00:00",
                    "pay_receive_time": "2026-03-04 13:00:00",
                    "counterparty_name": "梁希涛",
                    "debit_amount": "",
                    "credit_amount": "200000.00",
                    "summary": "暂借款",
                    "remark": "借入",
                },
                {
                    "account_no": "6222000011118106",
                    "account_name": "云南溯源科技有限公司基本户",
                    "txn_date": "2026-03-05",
                    "trade_time": "2026-03-05 09:00:00",
                    "pay_receive_time": "2026-03-05 09:00:00",
                    "counterparty_name": "梁希涛",
                    "debit_amount": "200000.00",
                    "credit_amount": "",
                    "summary": "还暂借款",
                    "remark": "归还",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        transaction_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [
                {
                    "transaction_id": transaction_ids[0],
                    "category_code": "borrow_in_company_pending_repayment",
                    "expected_version": 0,
                },
                {
                    "transaction_id": transaction_ids[1],
                    "category_code": "borrow_in_company_repaid",
                    "expected_version": 0,
                },
            ],
            actor="YNSYLP005",
        )

    def test_legacy_read_model_without_source_versions_rebuilds_for_turnover_relations(self) -> None:
        app = build_application()
        self._import_and_tag_closed_turnover_rows(app)
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": [{"group_id": "legacy-cache", "bank_rows": []}]},
            },
            ignored_rows=[],
        )

        response = app.handle_request("GET", "/api/workbench?month=2026-03")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        group_ids = [group["group_id"] for group in payload["open"]["groups"]]
        self.assertNotIn("legacy-cache", group_ids)
        self.assertFalse(any(group_id.startswith("turnover:") for group_id in group_ids))

    def test_read_model_missing_turnover_source_version_rebuilds(self) -> None:
        app = build_application()
        self._import_and_tag_closed_turnover_rows(app)
        stale_versions = app._workbench_read_model_source_versions()
        stale_versions.pop("turnover_relation_snapshot_version", None)
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": [{"group_id": "missing-turnover-version", "bank_rows": []}]},
            },
            ignored_rows=[],
            source_versions=stale_versions,
        )

        response = app.handle_request("GET", "/api/workbench?month=2026-03")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        group_ids = [group["group_id"] for group in payload["open"]["groups"]]
        self.assertNotIn("missing-turnover-version", group_ids)
        self.assertFalse(any(group_id.startswith("turnover:") for group_id in group_ids))

    def test_turnover_relation_source_version_is_stable_for_unchanged_inputs(self) -> None:
        app = build_application()
        self._import_and_tag_closed_turnover_rows(app)

        first_versions = app._workbench_read_model_source_versions()
        second_versions = app._workbench_read_model_source_versions()

        self.assertEqual(
            first_versions["turnover_relation_snapshot_version"],
            second_versions["turnover_relation_snapshot_version"],
        )


if __name__ == "__main__":
    unittest.main()
