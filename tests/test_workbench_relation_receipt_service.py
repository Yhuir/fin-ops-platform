from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from http import HTTPStatus
import unittest

from fin_ops_platform.app.routes_workbench_actions import WorkbenchActionApiRoutes
from fin_ops_platform.services.workbench_relation_receipt_service import (
    WorkbenchReceiptError,
    WorkbenchReceiptFile,
    WorkbenchRelationReceiptService,
)


def _bank(
    row_id: str,
    *,
    payer: str,
    amount: str,
    occurred_at: str = "2026-08-28T10:00:00+08:00",
) -> dict[str, object]:
    return {
        "id": row_id,
        "txn_direction": "inflow",
        "counterparty_name_raw": payer,
        "normalized_counterparty_name": payer,
        "amount": amount,
        "pay_receive_time": datetime.fromisoformat(occurred_at),
        "currency": "CNY",
    }


def _invoice(
    row_id: str,
    *,
    buyer: str,
    amount: str,
    invoice_no: str,
    invoice_date: str = "2026-08-28",
) -> dict[str, object]:
    return {
        "id": row_id,
        "invoice_type": "output",
        "invoice_no": invoice_no,
        "digital_invoice_no": invoice_no,
        "invoice_date": invoice_date,
        "buyer_name": buyer,
        "counterparty_name": buyer,
        "total_with_tax": amount,
        "currency": "CNY",
        "raw_payload": {"备注": f"发票 {invoice_no}"},
    }


def _relation(
    *,
    banks: list[dict[str, object]],
    invoices: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "id": "00000000-0000-4000-8000-000000000001",
        "case_id": "CASE-RECEIPT-1",
        "version": 3,
        "row_types": [*("bank" for _ in banks), *("invoice" for _ in invoices)],
        "bank_rows": banks,
        "invoice_rows": invoices,
    }


class _Repository:
    def __init__(self, relation: dict[str, object] | None) -> None:
        self.relation = relation
        self.rows: dict[tuple[str, str], dict[str, object]] = {}
        self.insert_calls = 0
        self.external_invoices: list[dict[str, object]] = []

    def load_active_relation(self, case_id: str) -> dict[str, object] | None:
        if self.relation is None or case_id != self.relation["case_id"]:
            return None
        return deepcopy(self.relation)

    def find_by_fingerprint(self, case_id: str, fingerprint: str) -> dict[str, object] | None:
        row = self.rows.get((case_id, fingerprint))
        return deepcopy(row) if row is not None else None

    def load_output_invoices_by_numbers(self, invoice_nos: list[str]) -> list[dict[str, object]]:
        return [
            deepcopy(row)
            for row in self.external_invoices
            if str(row.get("digital_invoice_no") or row.get("invoice_no") or "") in invoice_nos
        ]

    def insert(self, payload: dict[str, object]) -> tuple[dict[str, object], bool]:
        self.insert_calls += 1
        key = (str(payload["case_id"]), str(payload["source_fingerprint"]))
        created = key not in self.rows
        if created:
            self.rows[key] = {
                **deepcopy(payload),
                "storage_uri": str(payload["storage_uri"]),
            }
        return deepcopy(self.rows[key]), created


class _FileStore:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.store_calls = 0

    def store_workbench_relation_receipt(
        self,
        *,
        receipt_id: str,
        file_name: str,
        content: bytes,
        content_type: str,
    ) -> dict[str, object]:
        self.store_calls += 1
        assert file_name.endswith(".pdf")
        assert content_type == "application/pdf"
        storage_uri = f"memory://{receipt_id}"
        self.files[storage_uri] = content
        return {
            "file_object_id": "00000000-0000-4000-8000-000000000002",
            "storage_uri": storage_uri,
        }

    def read_workbench_relation_receipt(self, storage_uri: str) -> bytes:
        return self.files[storage_uri]


class _Renderer:
    def __init__(self) -> None:
        self.snapshots: list[dict[str, object]] = []

    def render(self, snapshot: dict[str, object]) -> bytes:
        self.snapshots.append(deepcopy(snapshot))
        return b"%PDF-receipt"


class _Audit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def append_operation_event(self, event: dict[str, object]) -> dict[str, object]:
        self.events.append(deepcopy(event))
        return {"id": str(len(self.events))}


class WorkbenchRelationReceiptServiceTests(unittest.TestCase):
    def _service(
        self,
        relation: dict[str, object] | None,
    ) -> tuple[WorkbenchRelationReceiptService, _Repository, _FileStore, _Renderer, _Audit]:
        repository = _Repository(relation)
        file_store = _FileStore()
        renderer = _Renderer()
        audit = _Audit()
        return (
            WorkbenchRelationReceiptService(
                repository=repository,
                file_store=file_store,
                audit_repository=audit,
                renderer=renderer,
            ),
            repository,
            file_store,
            renderer,
            audit,
        )

    @staticmethod
    def _print(service: WorkbenchRelationReceiptService) -> WorkbenchReceiptFile:
        draft = service.draft_receipt(case_id="CASE-RECEIPT-1")
        return service.print_receipt(
            case_id="CASE-RECEIPT-1",
            relation_version=draft["relation_version"],
            source_fingerprint=str(draft["source_fingerprint"]),
            receipts=draft["receipts"],
            issues_acknowledged=False,
            actor_id="finance-user",
            actor_account="YNSYLP007",
            actor_name="财务用户",
            request_id="request-receipt-1",
        )

    def test_groups_multiple_income_rows_and_preserves_every_output_invoice(self) -> None:
        relation = _relation(
            banks=[
                _bank("bank-1", payer="成都智领趋势科技有限公司", amount="100.00"),
                _bank("bank-2", payer="成都智领趋势科技有限公司", amount="80.00"),
            ],
            invoices=[
                _invoice("invoice-1", buyer="成都智领趋势科技有限公司", amount="120.00", invoice_no="INV-1"),
                _invoice("invoice-2", buyer="成都智领趋势科技有限公司", amount="60.00", invoice_no="INV-2"),
            ],
        )
        service, repository, file_store, renderer, audit = self._service(relation)

        result = self._print(service)

        snapshot = renderer.snapshots[0]
        self.assertEqual(snapshot["total_amount"], "180.00")
        self.assertEqual(len(snapshot["receipts"]), 1)
        receipt = snapshot["receipts"][0]
        self.assertEqual(receipt["amount"], "180.00")
        self.assertEqual(receipt["bank_transaction_ids"], ["bank-1", "bank-2"])
        original_receipt = snapshot["original_receipts"][0]
        self.assertEqual([line["invoice_no"] for line in original_receipt["lines"]], ["INV-1", "INV-2"])
        self.assertEqual([line["amount"] for line in receipt["lines"]], ["120.00", "60.00"])
        self.assertEqual(result.content, b"%PDF-receipt")
        self.assertEqual(repository.insert_calls, 1)
        self.assertEqual(file_store.store_calls, 1)
        self.assertEqual([event["event_type"] for event in audit.events], [
            "receipt_generated",
            "receipt_print_requested",
        ])

    def test_exact_red_blue_pair_is_removed_and_only_effective_invoice_remains(self) -> None:
        reversed_blue_no = "26532000000809302711"
        effective_blue_no = "26532000000809302712"
        reversed_blue = _invoice(
            "invoice-blue-reversed",
            buyer="付款单位",
            amount="182400.00",
            invoice_no=reversed_blue_no,
        )
        red = {
            **_invoice(
                "invoice-red",
                buyer="付款单位",
                amount="-182400.00",
                invoice_no="26532000000809302713",
            ),
            "raw_payload": {
                "备注": f"被红冲蓝字数电发票号码：{reversed_blue_no}",
            },
        }
        effective_blue = {
            **_invoice(
                "invoice-blue-effective",
                buyer="付款单位",
                amount="182400.00",
                invoice_no=effective_blue_no,
            ),
            "raw_payload": {
                "normalized_payload": {"taxable_item_name": "技术服务费"},
            },
        }
        service, _repository, _file_store, _renderer, _audit = self._service(
            _relation(
                banks=[_bank("bank-1", payer="付款单位", amount="182400.00")],
                invoices=[reversed_blue, red, effective_blue],
            )
        )

        draft = service.draft_receipt(case_id="CASE-RECEIPT-1")

        self.assertTrue(draft["can_print"])
        self.assertEqual(draft["issues"], [])
        self.assertEqual(draft["reversal_adjustments"][0]["kind"], "full")
        self.assertEqual(draft["receipts"][0]["lines"], [{
            "source_invoice_ids": ["invoice-blue-effective"],
            "invoice_no": effective_blue_no,
            "summary": "技术服务费",
            "amount": "182400.00",
            "note": "",
        }])

    def test_partial_red_blue_pair_keeps_only_the_blue_net_amount(self) -> None:
        blue_no = "26532000000809302721"
        blue = _invoice(
            "invoice-blue", buyer="付款单位", amount="200.00", invoice_no=blue_no
        )
        red = {
            **_invoice(
                "invoice-red",
                buyer="付款单位",
                amount="-50.00",
                invoice_no="26532000000809302722",
            ),
            "raw_payload": {"remark": f"被红冲蓝字数电发票号码：{blue_no}"},
        }
        service, *_ = self._service(
            _relation(
                banks=[_bank("bank-1", payer="付款单位", amount="150.00")],
                invoices=[blue, red],
            )
        )

        draft = service.draft_receipt(case_id="CASE-RECEIPT-1")

        self.assertTrue(draft["can_print"])
        self.assertEqual(draft["reversal_adjustments"][0]["kind"], "partial")
        self.assertEqual(
            [(line["invoice_no"], line["amount"]) for line in draft["receipts"][0]["lines"]],
            [(blue_no, "150.00")],
        )

    def test_unresolved_red_invoice_requires_acknowledgement_and_manual_correction(self) -> None:
        blue = _invoice(
            "invoice-blue", buyer="付款单位", amount="150.00", invoice_no="INV-BLUE"
        )
        red = _invoice(
            "invoice-red", buyer="付款单位", amount="-50.00", invoice_no="INV-RED"
        )
        service, *_ = self._service(
            _relation(
                banks=[_bank("bank-1", payer="付款单位", amount="100.00")],
                invoices=[blue, red],
            )
        )
        draft = service.draft_receipt(case_id="CASE-RECEIPT-1")

        self.assertFalse(draft["can_print"])
        self.assertEqual(draft["issues"][0]["code"], "receipt_reversal_target_unresolved")
        with self.assertRaises(WorkbenchReceiptError) as raised:
            service.print_receipt(
                case_id="CASE-RECEIPT-1",
                relation_version=draft["relation_version"],
                source_fingerprint=draft["source_fingerprint"],
                receipts=draft["receipts"],
                issues_acknowledged=False,
                actor_id="finance-user",
                actor_account="YNSYLP007",
                actor_name="财务用户",
                request_id="request-1",
            )
        self.assertEqual(raised.exception.code, "receipt_reversal_issue_unacknowledged")

        corrected = deepcopy(draft["receipts"])
        corrected[0]["lines"] = [{"summary": "人工核对后的服务费", "amount": "100.00", "note": ""}]
        result = service.print_receipt(
            case_id="CASE-RECEIPT-1",
            relation_version=draft["relation_version"],
            source_fingerprint=draft["source_fingerprint"],
            receipts=corrected,
            issues_acknowledged=True,
            actor_id="finance-user",
            actor_account="YNSYLP007",
            actor_name="财务用户",
            request_id="request-2",
        )
        self.assertEqual(result.content, b"%PDF-receipt")

    def test_exact_reversal_can_resolve_a_blue_invoice_outside_the_relation(self) -> None:
        blue_no = "26532000000809302731"
        red = {
            **_invoice(
                "invoice-red",
                buyer="付款单位",
                amount="-80.00",
                invoice_no="26532000000809302732",
            ),
            "raw_payload": {"备注": f"被红冲蓝字数电发票号码：{blue_no}"},
        }
        effective = _invoice(
            "invoice-effective",
            buyer="付款单位",
            amount="120.00",
            invoice_no="26532000000809302733",
        )
        service, repository, *_ = self._service(
            _relation(
                banks=[_bank("bank-1", payer="付款单位", amount="120.00")],
                invoices=[red, effective],
            )
        )
        repository.external_invoices = [
            _invoice(
                "invoice-blue-external",
                buyer="付款单位",
                amount="80.00",
                invoice_no=blue_no,
            )
        ]

        draft = service.draft_receipt(case_id="CASE-RECEIPT-1")

        self.assertTrue(draft["can_print"])
        self.assertEqual(draft["reversal_adjustments"][0]["kind"], "full")
        self.assertEqual(
            [line["invoice_no"] for line in draft["receipts"][0]["lines"]],
            ["26532000000809302733"],
        )

    def test_print_rejects_stale_source_and_unbalanced_edits(self) -> None:
        relation = _relation(
            banks=[_bank("bank-1", payer="付款单位", amount="88.00")],
            invoices=[
                _invoice(
                    "invoice-1", buyer="付款单位", amount="88.00", invoice_no="INV-88"
                )
            ],
        )
        service, repository, *_ = self._service(relation)
        draft = service.draft_receipt(case_id="CASE-RECEIPT-1")

        with self.assertRaises(WorkbenchReceiptError) as raised:
            service.print_receipt(
                case_id="CASE-RECEIPT-1",
                relation_version=int(draft["relation_version"]) - 1,
                source_fingerprint=draft["source_fingerprint"],
                receipts=draft["receipts"],
                issues_acknowledged=False,
                actor_id="finance-user",
                actor_account="YNSYLP007",
                actor_name="财务用户",
                request_id="request-version",
            )
        self.assertEqual(raised.exception.code, "receipt_relation_version_conflict")

        unbalanced_receipts = deepcopy(draft["receipts"])
        unbalanced_receipts[0]["lines"][0]["amount"] = "87.99"
        with self.assertRaises(WorkbenchReceiptError) as raised:
            service.print_receipt(
                case_id="CASE-RECEIPT-1",
                relation_version=draft["relation_version"],
                source_fingerprint=draft["source_fingerprint"],
                receipts=unbalanced_receipts,
                issues_acknowledged=False,
                actor_id="finance-user",
                actor_account="YNSYLP007",
                actor_name="财务用户",
                request_id="request-1",
            )
        self.assertEqual(raised.exception.code, "receipt_amount_unbalanced")

        assert repository.relation is not None
        repository.relation["bank_rows"][0]["amount"] = "89.00"
        with self.assertRaises(WorkbenchReceiptError) as raised:
            service.print_receipt(
                case_id="CASE-RECEIPT-1",
                relation_version=draft["relation_version"],
                source_fingerprint=draft["source_fingerprint"],
                receipts=draft["receipts"],
                issues_acknowledged=False,
                actor_id="finance-user",
                actor_account="YNSYLP007",
                actor_name="财务用户",
                request_id="request-2",
            )
        self.assertEqual(raised.exception.code, "receipt_source_conflict")

    def test_print_rejects_invalid_edited_receipt_fields(self) -> None:
        service, *_ = self._service(
            _relation(
                banks=[_bank("bank-1", payer="付款单位", amount="88.00")],
                invoices=[
                    _invoice(
                        "invoice-1",
                        buyer="付款单位",
                        amount="88.00",
                        invoice_no="INV-88",
                    )
                ],
            )
        )
        draft = service.draft_receipt(case_id="CASE-RECEIPT-1")
        cases = (
            ("payer", "", "receipt_payer_missing"),
            ("date", "2026-02-31", "invalid_receipt_date"),
            ("lines", [], "receipt_lines_empty"),
            ("summary", "", "receipt_line_summary_missing"),
            ("amount", "not-money", "receipt_line_amount_invalid"),
        )
        for field, value, expected_code in cases:
            with self.subTest(field=field):
                receipts = deepcopy(draft["receipts"])
                if field in {"payer", "date", "lines"}:
                    receipts[0][field] = value
                else:
                    receipts[0]["lines"][0][field] = value
                with self.assertRaises(WorkbenchReceiptError) as raised:
                    service.print_receipt(
                        case_id="CASE-RECEIPT-1",
                        relation_version=draft["relation_version"],
                        source_fingerprint=draft["source_fingerprint"],
                        receipts=receipts,
                        issues_acknowledged=False,
                        actor_id="finance-user",
                        actor_account="YNSYLP007",
                        actor_name="财务用户",
                        request_id="request-invalid",
                    )
                self.assertEqual(raised.exception.code, expected_code)

    def test_accepts_the_canonical_renminbi_currency_label(self) -> None:
        relation = _relation(
            banks=[{
                **_bank("bank-1", payer="付款单位", amount="88.00"),
                "currency": "人民币元",
            }],
            invoices=[_invoice("invoice-1", buyer="付款单位", amount="88.00", invoice_no="INV-88")],
        )
        service, _repository, _file_store, renderer, _audit = self._service(relation)

        result = self._print(service)

        self.assertEqual(result.receipt_count, 1)
        self.assertEqual(renderer.snapshots[0]["receipts"][0]["currency"], "CNY")

    def test_repeated_print_reuses_same_snapshot_without_regenerating_file(self) -> None:
        relation = _relation(
            banks=[_bank("bank-1", payer="付款单位", amount="88.00")],
            invoices=[_invoice("invoice-1", buyer="付款单位", amount="88.00", invoice_no="INV-88")],
        )
        service, repository, file_store, renderer, audit = self._service(relation)

        first = self._print(service)
        second = self._print(service)

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.receipt_id, second.receipt_id)
        self.assertEqual(repository.insert_calls, 1)
        self.assertEqual(file_store.store_calls, 1)
        self.assertEqual(len(renderer.snapshots), 1)
        self.assertEqual([event["event_type"] for event in audit.events], [
            "receipt_generated",
            "receipt_print_requested",
            "receipt_print_requested",
        ])

    def test_multiple_payers_are_rejected_instead_of_guessing_receipt_ownership(self) -> None:
        relation = _relation(
            banks=[
                _bank("bank-a", payer="付款方 A", amount="100.00", occurred_at="2026-08-27T09:00:00+08:00"),
                _bank("bank-b", payer="付款方 B", amount="200.00", occurred_at="2026-08-28T09:00:00+08:00"),
            ],
            invoices=[
                _invoice("invoice-a", buyer="付款方 A", amount="100.00", invoice_no="INV-A", invoice_date="2026-01-01"),
                _invoice("invoice-b", buyer="付款方 B", amount="200.00", invoice_no="INV-B", invoice_date="2026-01-01"),
            ],
        )
        service, *_ = self._service(relation)

        with self.assertRaises(WorkbenchReceiptError) as raised:
            service.draft_receipt(case_id="CASE-RECEIPT-1")

        self.assertEqual(raised.exception.code, "receipt_payer_ambiguous")
        self.assertEqual(raised.exception.status_code, HTTPStatus.CONFLICT)

    def test_same_payer_on_multiple_dates_produces_one_receipt_using_latest_income_date(self) -> None:
        relation = _relation(
            banks=[
                _bank("bank-1", payer="付款方", amount="100.00", occurred_at="2026-08-27T09:00:00+08:00"),
                _bank("bank-2", payer="付款方", amount="200.00", occurred_at="2026-08-28T09:00:00+08:00"),
            ],
            invoices=[
                _invoice("invoice-1", buyer="付款方", amount="300.00", invoice_no="INV-1", invoice_date="2026-08-26"),
            ],
        )
        service, *_ = self._service(relation)

        draft = service.draft_receipt(case_id="CASE-RECEIPT-1")

        self.assertEqual(draft["total_amount"], "300.00")
        self.assertEqual(len(draft["receipts"]), 1)
        self.assertEqual(draft["receipts"][0]["date"], "2026-08-28")
        self.assertEqual(draft["receipts"][0]["income_amount"], "300.00")
        self.assertTrue(draft["receipts"][0]["balanced"])

    def test_rejects_relations_outside_the_income_output_invoice_contract(self) -> None:
        invalid_relations = {
            "oa": {
                **_relation(
                    banks=[_bank("bank-1", payer="付款方", amount="1")],
                    invoices=[_invoice("invoice-1", buyer="付款方", amount="1", invoice_no="INV")],
                ),
                "row_types": ["oa", "bank", "invoice"],
            },
            "outflow": _relation(
                banks=[{**_bank("bank-1", payer="付款方", amount="1"), "txn_direction": "outflow"}],
                invoices=[_invoice("invoice-1", buyer="付款方", amount="1", invoice_no="INV")],
            ),
            "input_invoice": _relation(
                banks=[_bank("bank-1", payer="付款方", amount="1")],
                invoices=[{
                    **_invoice("invoice-1", buyer="付款方", amount="1", invoice_no="INV"),
                    "invoice_type": "input",
                }],
            ),
            "missing_currency": _relation(
                banks=[{**_bank("bank-1", payer="付款方", amount="1"), "currency": None}],
                invoices=[_invoice("invoice-1", buyer="付款方", amount="1", invoice_no="INV")],
            ),
            "missing_date": _relation(
                banks=[{**_bank("bank-1", payer="付款方", amount="1"), "pay_receive_time": None}],
                invoices=[_invoice("invoice-1", buyer="付款方", amount="1", invoice_no="INV")],
            ),
            "nonpositive_income": _relation(
                banks=[_bank("bank-1", payer="付款方", amount="0")],
                invoices=[_invoice("invoice-1", buyer="付款方", amount="1", invoice_no="INV")],
            ),
            "missing_invoice_number": _relation(
                banks=[_bank("bank-1", payer="付款方", amount="1")],
                invoices=[_invoice("invoice-1", buyer="付款方", amount="1", invoice_no="")],
            ),
        }
        expected_codes = {
            "oa": "receipt_relation_not_eligible",
            "outflow": "receipt_relation_not_income",
            "input_invoice": "receipt_relation_not_output_invoice",
            "missing_currency": "receipt_currency_not_supported",
            "missing_date": "receipt_transaction_date_missing",
            "nonpositive_income": "receipt_income_amount_invalid",
            "missing_invoice_number": "receipt_invoice_number_missing",
        }
        for name, relation in invalid_relations.items():
            with self.subTest(name=name):
                service, *_ = self._service(relation)
                with self.assertRaises(WorkbenchReceiptError) as raised:
                    self._print(service)
                self.assertEqual(raised.exception.code, expected_codes[name])


class WorkbenchRelationReceiptActionRouteTests(unittest.TestCase):
    def test_action_forwards_authenticated_actor_and_returns_pdf_contract(self) -> None:
        calls: list[dict[str, str]] = []

        class _Service:
            def print_receipt(self, **kwargs: str) -> WorkbenchReceiptFile:
                calls.append(kwargs)
                return WorkbenchReceiptFile(
                    content=b"%PDF",
                    file_name="receipt.pdf",
                    receipt_id="receipt-1",
                    receipt_count=1,
                    reused=False,
                )

        routes = WorkbenchActionApiRoutes(
            write_facade_provider=lambda: None,
            receipt_service_provider=_Service,
        )

        status, result = routes.print_receipt(
            {
                "case_id": "CASE-RECEIPT-1",
                "relation_version": 3,
                "source_fingerprint": "source-1",
                "issues_acknowledged": True,
                "receipts": [{"receipt_key": "receipt-key-1"}],
            },
            actor_id="finance-user",
            actor_account="YNSYLP007",
            actor_name="财务用户",
            request_id="request-1",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(result.content, b"%PDF")
        self.assertEqual(calls, [{
            "case_id": "CASE-RECEIPT-1",
            "relation_version": 3,
            "source_fingerprint": "source-1",
            "issues_acknowledged": True,
            "receipts": [{"receipt_key": "receipt-key-1"}],
            "actor_id": "finance-user",
            "actor_account": "YNSYLP007",
            "actor_name": "财务用户",
            "request_id": "request-1",
        }])

    def test_draft_action_returns_structured_receipt_without_generating_pdf(self) -> None:
        calls: list[dict[str, str]] = []

        class _Service:
            def draft_receipt(self, **kwargs: str) -> dict[str, object]:
                calls.append(kwargs)
                return {"case_id": kwargs["case_id"], "receipts": [{"lines": []}]}

        routes = WorkbenchActionApiRoutes(
            write_facade_provider=lambda: None,
            receipt_service_provider=_Service,
        )

        status, result = routes.receipt_draft({"case_id": "CASE-RECEIPT-1"})

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(result["case_id"], "CASE-RECEIPT-1")
        self.assertEqual(calls, [{"case_id": "CASE-RECEIPT-1"}])

    def test_action_maps_domain_error_and_fails_closed_without_service(self) -> None:
        class _Service:
            def print_receipt(self, **_kwargs: str) -> WorkbenchReceiptFile:
                raise WorkbenchReceiptError("receipt_relation_not_eligible", "不能打印。", 409)

        routes = WorkbenchActionApiRoutes(
            write_facade_provider=lambda: None,
            receipt_service_provider=_Service,
        )
        status, payload = routes.print_receipt(
            {"case_id": "CASE-1"},
            actor_id="user",
            actor_account="account",
            actor_name="name",
            request_id="request",
        )
        self.assertEqual(status, HTTPStatus.CONFLICT)
        self.assertEqual(payload, {"error": "receipt_relation_not_eligible", "message": "不能打印。"})

        unavailable = WorkbenchActionApiRoutes(write_facade_provider=lambda: None)
        status, payload = unavailable.print_receipt(
            {"case_id": "CASE-1"},
            actor_id="user",
            actor_account="account",
            actor_name="name",
            request_id="request",
        )
        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(payload["error"], "workbench_receipt_service_unavailable")

        def unavailable_provider() -> object:
            raise RuntimeError("postgres unavailable")

        unavailable = WorkbenchActionApiRoutes(
            write_facade_provider=lambda: None,
            receipt_service_provider=unavailable_provider,
        )
        status, payload = unavailable.receipt_draft({"case_id": "CASE-1"})
        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(payload["error"], "workbench_receipt_service_unavailable")


if __name__ == "__main__":
    unittest.main()
