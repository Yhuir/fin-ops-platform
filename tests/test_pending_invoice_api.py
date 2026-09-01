from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.app_test_support import (
    build_local_state_application as build_application,
    configure_access_control,
)
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.pending_invoice_service import PENDING_INVOICE_EXPORT_ROW_LIMIT
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.pending_invoice_rules import pending_invoice_rules_payload


class PendingInvoiceApiTests(unittest.TestCase):
    def test_rows_endpoint_returns_pending_invoice_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor API")

            response = app.handle_request("GET", "/api/pending-invoices/rows?direction=expense&filter=all")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["direction"], "expense")
        self.assertEqual(payload["rows"][0]["id"], transaction_id)
        self.assertEqual(
            payload["rows"][0]["bank_transactions"]["primary"]["counterparty_name"],
            "Vendor API",
        )
        self.assertNotIn("bank_transaction", payload["rows"][0])
        self.assertNotIn("invoices", payload["rows"][0])
        self.assertNotIn("oa_applicant", payload["rows"][0])
        self.assertTrue(payload["rows"][0]["can_create_invoice"])
        self.assertEqual(payload["rows"][0]["invoice_acquisition_status"]["code"], "paid_pending_invoice")

    def test_rows_endpoint_ignores_legacy_pending_invoice_read_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Direct Canonical")

            class PendingInvoiceSqlReadRepository:
                def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                    raise AssertionError("legacy pending invoice read model must not be queried")

            app._pending_invoice_sql_read_repository = PendingInvoiceSqlReadRepository()
            if hasattr(app, "_pending_invoice_api_routes"):
                delattr(app, "_pending_invoice_api_routes")

            response = app.handle_request("GET", "/api/pending-invoices/rows?direction=expense&filter=all")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["rows"][0]["id"], transaction_id)
        self.assertNotIn("read_model_status", payload)

    def test_oa_detail_endpoint_rejects_candidate_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request("GET", "/api/pending-invoices/oa/candidate%3A030404426078/detail")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_oa_detail_id")

    def test_detail_candidates_attach_rules_and_export_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Attach")
            invoice_id = self._create_input_invoice(app, seller_name="Vendor Attach", invoice_no="ATTACH-001")

            candidates_response = app.handle_request(
                "GET",
                f"/api/pending-invoices/invoice-candidates?transaction_id={transaction_id}",
            )
            preview_response = app.handle_request(
                "POST",
                f"/api/pending-invoices/rows/{transaction_id}/attach-existing-invoice/preview",
                body=json.dumps({"invoice_id": invoice_id, "request_id": "preview-attach-api"}),
            )
            preview_payload = json.loads(preview_response.body)
            confirm_response = app.handle_request(
                "POST",
                f"/api/pending-invoices/rows/{transaction_id}/attach-existing-invoice",
                body=json.dumps({
                    "preview_id": preview_payload["preview_id"],
                    "invoice_id": invoice_id,
                    "request_id": "attach-api-001",
                }),
            )
            relation_response = app.handle_request(
                "GET",
                f"/api/pending-invoices/rows/{transaction_id}/relation-detail",
            )
            invoice_detail_response = app.handle_request(
                "GET",
                f"/api/pending-invoices/invoices/{invoice_id}/detail",
            )
            export_preview_response = app.handle_request("GET", "/api/pending-invoices/export-preview?direction=expense")
            export_response = app.handle_request("GET", "/api/pending-invoices/export?direction=expense")
            rules_response = app.handle_request("GET", "/api/pending-invoices/rules")

        candidates_payload = json.loads(candidates_response.body)
        confirm_payload = json.loads(confirm_response.body)
        relation_payload = json.loads(relation_response.body)
        invoice_detail_payload = json.loads(invoice_detail_response.body)
        export_preview_payload = json.loads(export_preview_response.body)
        rules_payload = json.loads(rules_response.body)
        self.assertEqual(candidates_response.status_code, 200)
        self.assertEqual(candidates_payload["rows"][0]["invoice_id"], invoice_id)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(confirm_payload["status"], "completed")
        self.assertEqual(confirm_payload["relation_mode"], "pending_invoice_attach_existing_invoice")
        self.assertEqual(relation_response.status_code, 200)
        self.assertTrue(relation_payload["detail_available"])
        self.assertEqual(relation_payload["sections"][0]["title"], "银行流水")
        self.assertNotIn("transaction_summary", relation_payload)
        self.assertNotIn("relation_case_ids", relation_payload)
        self.assertEqual(invoice_detail_response.status_code, 200)
        self.assertTrue(invoice_detail_payload["detail_available"])
        self.assertTrue(invoice_detail_payload["sections"])
        self.assertNotIn("invoice", invoice_detail_payload)
        self.assertEqual(export_preview_response.status_code, 200)
        self.assertIn("columns", export_preview_payload)
        self.assertEqual(export_response.status_code, 200)
        self.assertTrue(export_response.body)
        self.assertEqual(rules_response.status_code, 200)
        self.assertIn("pending_invoice_tag_groups", rules_payload)

    def test_export_endpoints_reject_row_limit_before_xlsx_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            class PageRepository:
                def __init__(self) -> None:
                    self.calls: list[dict[str, object]] = []

                def query(
                    self,
                    request: dict[str, object],
                    *,
                    page: int,
                    page_size: int,
                ) -> dict[str, object]:
                    self.calls.append({"request": request, "page": page, "page_size": page_size})
                    return {
                        "rows": [],
                        "total": PENDING_INVOICE_EXPORT_ROW_LIMIT + 1,
                        "settings": {},
                    }

            from fin_ops_platform.services.pending_invoice_canonical_query import (
                PendingInvoiceCanonicalQueryService,
            )

            repository = PageRepository()
            app._pending_invoice_page_query_service = PendingInvoiceCanonicalQueryService(repository=repository)
            if hasattr(app, "_pending_invoice_api_routes"):
                delattr(app, "_pending_invoice_api_routes")

            preview_response = app.handle_request("GET", "/api/pending-invoices/export-preview?direction=expense")
            export_response = app.handle_request("GET", "/api/pending-invoices/export?direction=expense")

        preview_payload = json.loads(preview_response.body)
        export_payload = json.loads(export_response.body)
        self.assertEqual(preview_response.status_code, 400)
        self.assertEqual(export_response.status_code, 400)
        self.assertEqual(preview_payload["error"], "pending_invoice_export_row_limit_exceeded")
        self.assertEqual(export_payload["error"], "pending_invoice_export_row_limit_exceeded")
        self.assertEqual(preview_payload["details"], {"total": PENDING_INVOICE_EXPORT_ROW_LIMIT + 1, "limit": PENDING_INVOICE_EXPORT_ROW_LIMIT})
        self.assertEqual(export_payload["details"], {"total": PENDING_INVOICE_EXPORT_ROW_LIMIT + 1, "limit": PENDING_INVOICE_EXPORT_ROW_LIMIT})
        self.assertEqual([call["page"] for call in repository.calls], [1, 1])
        self.assertEqual(
            [call["page_size"] for call in repository.calls],
            [PENDING_INVOICE_EXPORT_ROW_LIMIT + 1, PENDING_INVOICE_EXPORT_ROW_LIMIT + 1],
        )

    def test_batch_attach_existing_invoice_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            first_transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Batch A")
            second_transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Batch B")
            first_invoice_id = self._create_input_invoice(app, seller_name="Vendor Batch A", invoice_no="BATCH-ATTACH-001")
            second_invoice_id = self._create_input_invoice(app, seller_name="Vendor Batch B", invoice_no="BATCH-ATTACH-002")

            candidates_response = app.handle_request(
                "POST",
                "/api/pending-invoices/invoice-candidates/batch",
                body=json.dumps({"transaction_ids": [first_transaction_id, second_transaction_id]}),
            )
            preview_response = app.handle_request(
                "POST",
                "/api/pending-invoices/attach-existing-invoices/preview",
                body=json.dumps(
                    {
                        "transaction_ids": [first_transaction_id, second_transaction_id],
                        "invoice_ids": [first_invoice_id, second_invoice_id],
                    }
                ),
            )
            preview_payload = json.loads(preview_response.body)
            confirm_response = app.handle_request(
                "POST",
                "/api/pending-invoices/attach-existing-invoices",
                body=json.dumps(
                    {
                        "preview_id": preview_payload["preview_id"],
                        "transaction_ids": [first_transaction_id, second_transaction_id],
                        "invoice_ids": [first_invoice_id, second_invoice_id],
                        "request_id": "batch-attach-api-001",
                    }
                ),
            )

        candidates_payload = json.loads(candidates_response.body)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(candidates_response.status_code, 200)
        self.assertEqual(candidates_payload["selection_summary"]["transaction_count"], 2)
        self.assertEqual(candidates_payload["selection_summary"]["bank_total"], "236.00")
        self.assertTrue(candidates_payload["rows"])
        for row in candidates_payload["rows"]:
            self.assertIn("bank_relation_status", row)
            self.assertIn("linked_bank_transaction_count", row)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_payload["selection_summary"]["bank_total"], "236.00")
        self.assertEqual(preview_payload["selection_summary"]["invoice_total"], "236.00")
        self.assertEqual(preview_payload["selection_summary"]["difference_amount"], "0.00")
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(confirm_payload["status"], "completed")
        self.assertEqual(confirm_payload["affected_transaction_ids"], [first_transaction_id, second_transaction_id])
        self.assertEqual(confirm_payload["affected_invoice_ids"], [first_invoice_id, second_invoice_id])
        self.assertEqual(confirm_payload["relation_mode"], "pending_invoice_attach_existing_invoice")

    def test_income_endpoint_accepts_rule_group_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._create_bank_transaction(app, counterparty_name="Customer API Income", credit=True)

            response = app.handle_request("GET", "/api/pending-invoices/rows?direction=income&filter=requires_invoice")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["direction"], "income")
        self.assertEqual(payload["filter"], "requires_invoice")

    def test_read_model_miss_does_not_gate_or_enqueue_direct_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._create_bank_transaction(app, counterparty_name="Vendor Read Model Miss")

            class MissingPendingInvoiceSqlReadRepository:
                def list_pending_invoice_rows(self, **_kwargs: object) -> None:
                    return None

                def pending_invoice_source_summary(self, **_kwargs: object) -> dict[str, int]:
                    return {}

            class QueueRepository:
                def __init__(self) -> None:
                    self.enqueued: list[dict[str, str]] = []

                def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                    self.enqueued.append({"scope_type": scope_type, "scope_key": scope_key, "reason": reason})

            queue_repository = QueueRepository()
            app._pending_invoice_sql_read_repository = MissingPendingInvoiceSqlReadRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue_repository)
            self.assertFalse(hasattr(app._pending_invoice_query_service, "list_rows"))

            rows_response = app.handle_request("GET", "/api/pending-invoices/rows?direction=expense&filter=all")
            filter_options_response = app.handle_request("GET", "/api/pending-invoices/filter-options?direction=expense")
            export_preview_response = app.handle_request("GET", "/api/pending-invoices/export-preview?direction=expense")
            export_response = app.handle_request("GET", "/api/pending-invoices/export?direction=expense")
            income_response = app.handle_request("GET", "/api/pending-invoices/rows?direction=income&filter=cash_income")

        rows_payload = json.loads(rows_response.body)
        filter_options_payload = json.loads(filter_options_response.body)
        export_preview_payload = json.loads(export_preview_response.body)
        income_payload = json.loads(income_response.body)
        self.assertEqual(rows_response.status_code, 200)
        self.assertEqual(filter_options_response.status_code, 200)
        self.assertEqual(export_preview_response.status_code, 200)
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(income_response.status_code, 200)
        for payload in (rows_payload, filter_options_payload, export_preview_payload, income_payload):
            self.assertNotIn("read_model_status", payload)
        self.assertEqual(queue_repository.enqueued, [])

    def test_filter_options_ignore_legacy_read_model_status(self) -> None:
        app = build_application()
        self._create_bank_transaction(app, counterparty_name="Vendor Direct Facet")

        class AggregatingPendingInvoiceSqlReadRepository:
            def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("legacy pending invoice read model must not be queried")

        app._pending_invoice_sql_read_repository = AggregatingPendingInvoiceSqlReadRepository()
        if hasattr(app, "_pending_invoice_api_routes"):
            delattr(app, "_pending_invoice_api_routes")

        response = app.handle_request("GET", "/api/pending-invoices/filter-options?direction=expense")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("read_model_status", payload)
        self.assertIn(
            "Vendor Direct Facet",
            [option["value"] for option in payload["options"]["counterparty_name"]],
        )

    def test_rows_endpoint_does_not_require_pending_invoice_read_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._create_bank_transaction(app, counterparty_name="Vendor No Repository")
            self.assertFalse(hasattr(app._pending_invoice_query_service, "list_rows"))

            response = app.handle_request("GET", "/api/pending-invoices/rows?direction=expense&filter=all")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            payload["rows"][0]["bank_transactions"]["primary"]["counterparty_name"],
            "Vendor No Repository",
        )
        self.assertNotIn("bank_transaction", payload["rows"][0])
        self.assertIn("filter_options", payload)
        self.assertIn("fields", payload["filter_options"])
        self.assertNotIn("read_model_status", payload)

    def test_manual_invoice_endpoints_are_not_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Removed")
            payload = {
                "bank_transaction_id": transaction_id,
                "invoice_no": "API-MAN-REMOVED",
                "issue_date": "2026-05-20",
                "total_with_tax": "118.00",
                "seller_name": "Vendor Removed",
                "buyer_name": "云南溯源科技有限公司",
                "preview_id": "removed-preview",
                "request_id": "api-manual-removed",
            }

            preview_response = app.handle_request(
                "POST",
                "/api/pending-invoices/manual-invoices/preview",
                body=json.dumps(payload),
            )
            confirm_response = app.handle_request(
                "POST",
                "/api/pending-invoices/manual-invoices",
                body=json.dumps(payload),
            )

        preview_payload = json.loads(preview_response.body)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(preview_response.status_code, 404)
        self.assertEqual(confirm_response.status_code, 404)
        self.assertEqual(preview_payload["error"], "not_found")
        self.assertEqual(confirm_payload["error"], "not_found")
        self.assertNotIn("api-manual-removed", app._pending_invoice_commands)

    def test_settings_update_requires_write_permission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            settings = app._app_settings_service.get_settings_payload()
            configure_access_control(app, page_access={"LIMITED001": ["pending-invoices"]})
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="readonly-user-id",
                username="LIMITED001",
                nickname="受限用户",
                display_name="受限用户",
                roles=["finance"],
                permissions=[],
            )

            response = app.handle_request(
                "POST",
                "/api/workbench/settings",
                body=json.dumps({
                    "completed_project_ids": [],
                    "bank_account_mappings": [],
                    "allowed_usernames": ["READONLY001"],
                    "readonly_export_usernames": ["READONLY001"],
                    "admin_usernames": [],
                    "workbench_column_layouts": settings["workbench_column_layouts"],
                    "oa_retention": settings["oa_retention"],
                    "oa_import": settings["oa_import"],
                    "oa_invoice_offset": settings["oa_invoice_offset"],
                    "bank_transaction_tags": settings["bank_transaction_tags"],
                    "pending_invoice_tag_groups": settings["pending_invoice_tag_groups"],
                }),
                headers={"Authorization": "Bearer readonly-user"},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "page_access_denied")

    def test_pending_invoice_rules_update_requires_pending_invoice_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            current = app._app_settings_service.get_settings_payload()
            configure_access_control(app, page_access={"LIMITED001": ["bank-details"]})
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="readonly-user-id",
                username="LIMITED001",
                nickname="受限用户",
                display_name="受限用户",
                roles=["finance"],
                permissions=[],
            )

            response = app.handle_request(
                "PUT",
                "/api/pending-invoices/rules",
                body=json.dumps({"pending_invoice_tag_groups": current["pending_invoice_tag_groups"]}),
                headers={"Authorization": "Bearer readonly-user"},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "page_access_denied")

    def test_pending_invoice_rules_get_derives_requires_invoice_from_active_tag_complement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._state_store.save_app_settings(
                {
                    "bank_transaction_tags": self._tag_dictionary_payload(),
                    "pending_invoice_tag_groups": {
                        "version": 7,
                        "groups": {
                            "requires_invoice": {"tag_codes": ["old_tag"]},
                            "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                            "no_invoice_required": {"tag_codes": ["salary"]},
                        },
                    },
                }
            )

            response = app.handle_request("GET", "/api/pending-invoices/rules")

        payload = json.loads(response.body)
        expected_requires = self._active_rule_codes(payload["available_tags"], excluding={"fee", "salary"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["groups"]["requires_invoice"]["tag_codes"], expected_requires)
        custom_meal_tag = next(tag for tag in payload["groups"]["requires_invoice"]["tags"] if tag["code"] == "custom_meal")
        self.assertEqual(custom_meal_tag["output_primary_label"], "餐饮")
        self.assertEqual(custom_meal_tag["output_sub_label"], "")
        self.assertNotIn("old_tag", payload["groups"]["requires_invoice"]["tag_codes"])
        self.assertEqual(
            payload["pending_invoice_tag_groups"]["groups"]["requires_invoice"]["tag_codes"],
            expected_requires,
        )

    def test_pending_invoice_rules_available_tags_match_bank_auto_rules_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = pending_invoice_rules_payload(app._app_settings_service.get_pending_invoice_settings_payload())

        available_codes = {tag["code"] for tag in payload["available_tags"]}
        requires_codes = set(payload["groups"]["requires_invoice"]["tag_codes"])
        self.assertIn("internal_transfer", available_codes)
        self.assertIn("fee", available_codes)
        self.assertIn("external_turnover", available_codes)
        self.assertNotIn("borrow_in_company_repaid", available_codes)
        self.assertNotIn("borrow_out_bank_lent", available_codes)
        self.assertNotIn("borrow_in_company_repaid", requires_codes)
        self.assertFalse(any(tag["output_primary_label"].startswith("公司暂借款") for tag in payload["available_tags"]))

    def test_pending_invoice_rules_put_ignores_legacy_requires_invoice_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._configure_rule_tags(app)

            response = app.handle_request(
                "PUT",
                "/api/pending-invoices/rules",
                body=json.dumps({
                    "groups": {
                        "requires_invoice": {"tag_codes": ["unknown_legacy_code"]},
                        "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                        "no_invoice_required": {"tag_codes": ["salary"]},
                    }
                }),
            )
            auto_rules_after_save = app._app_settings_service.get_bank_auto_tag_rules_payload()

        payload = json.loads(response.body)
        active_auto_rule_codes = {rule["code"] for rule in auto_rules_after_save["active_rules"]}
        expected_requires = self._active_rule_codes(payload["available_tags"], excluding={"fee", "salary"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("custom_meal", active_auto_rule_codes)
        self.assertEqual(payload["groups"]["requires_invoice"]["tag_codes"], expected_requires)
        self.assertIn("custom_meal", payload["groups"]["requires_invoice"]["tag_codes"])
        self.assertNotIn("unknown_legacy_code", payload["groups"]["requires_invoice"]["tag_codes"])
        self.assertEqual(
            payload["pending_invoice_tag_groups"]["groups"]["requires_invoice"]["tag_codes"],
            expected_requires,
        )

    def test_pending_invoice_rules_put_enqueues_all_rule_filter_read_model_scopes(self) -> None:
        class QueueRepository:
            def __init__(self) -> None:
                self.enqueued: list[tuple[str, str, str]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.enqueued.append((scope_type, scope_key, reason))

        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._configure_rule_tags(app)
            queue_repository = QueueRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue_repository)
            if hasattr(app, "_pending_invoice_api_routes"):
                delattr(app, "_pending_invoice_api_routes")

            response = app.handle_request(
                "PUT",
                "/api/pending-invoices/rules",
                body=json.dumps({
                    "groups": {
                        "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                        "no_invoice_required": {"tag_codes": ["salary"]},
                    }
                }),
            )

        self.assertEqual(response.status_code, 200)
        pending_invoice_refreshes = [
            refresh
            for refresh in queue_repository.enqueued
            if refresh[0] == "pending_invoice" and refresh[2] == "pending_invoice_rules_update"
        ]
        self.assertEqual(pending_invoice_refreshes, [])

    def test_pending_invoice_rules_put_runs_low_coupling_lifecycle_without_unrelated_domains(self) -> None:
        class QueueRepository:
            def __init__(self) -> None:
                self.enqueued: list[tuple[str, str, str]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.enqueued.append((scope_type, scope_key, reason))

        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._configure_rule_tags(app)
            queue_repository = QueueRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue_repository)
            if hasattr(app, "_pending_invoice_api_routes"):
                delattr(app, "_pending_invoice_api_routes")
            current = app._app_settings_service.get_pending_invoice_settings_payload()
            initial_bank_rules_version = current["bank_transaction_tags"]["version"]

            response = app.handle_request(
                "PUT",
                "/api/pending-invoices/rules",
                body=json.dumps({
                    "version": current["pending_invoice_tag_groups"]["version"],
                    "groups": {
                        "bank_statement_as_invoice": {"tag_codes": []},
                        "no_invoice_required": {"tag_codes": ["external_rule_borrow_out"]},
                    },
                }),
            )
            saved_settings = app._app_settings_service.get_settings_payload()

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("derived_data_lifecycle", payload)
        self.assertEqual(saved_settings["bank_transaction_tags"]["version"], initial_bank_rules_version)
        self.assertEqual(
            saved_settings["pending_invoice_tag_groups"]["groups"]["no_invoice_required"]["tag_codes"],
            ["external_rule_borrow_out"],
        )
        self.assertEqual(queue_repository.enqueued, [])

    def test_pending_invoice_rules_put_rejects_stale_rule_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._configure_rule_tags(app)
            current = app._app_settings_service.get_pending_invoice_settings_payload()

            response = app.handle_request(
                "PUT",
                "/api/pending-invoices/rules",
                body=json.dumps({
                    "version": current["pending_invoice_tag_groups"]["version"] - 1,
                    "groups": {
                        "bank_statement_as_invoice": {"tag_codes": []},
                        "no_invoice_required": {"tag_codes": ["salary"]},
                    },
                }),
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["error"], "pending_invoice_tag_groups_version_conflict")

    def test_pending_invoice_rules_put_rejects_duplicate_editable_group_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._configure_rule_tags(app)

            response = app.handle_request(
                "PUT",
                "/api/pending-invoices/rules",
                body=json.dumps({
                    "groups": {
                        "requires_invoice": {"tag_codes": ["custom_meal"]},
                        "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                        "no_invoice_required": {"tag_codes": ["fee"]},
                    }
                }),
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "duplicate_pending_invoice_tag_mapping")

    def test_income_pending_invoice_rules_are_saved_separately_from_expense_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._configure_rule_tags(app)

            response = app.handle_request(
                "PUT",
                "/api/pending-invoices/rules?direction=income",
                body=json.dumps({
                    "groups": {
                        "requires_invoice": {"tag_codes": ["ignored_requires"]},
                        "no_invoice_required": {"tag_codes": ["custom_meal"]},
                        "cash_income": {"tag_codes": ["custom_cash"]},
                    }
                }),
            )
            settings = app._app_settings_service.get_settings_payload()

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["direction"], "income")
        self.assertEqual(payload["groups"]["no_invoice_required"]["tag_codes"], ["custom_meal"])
        self.assertEqual(payload["groups"]["cash_income"]["tag_codes"], ["custom_cash"])
        self.assertNotIn("ignored_requires", payload["groups"]["requires_invoice"]["tag_codes"])
        self.assertEqual(
            settings["pending_invoice_tag_groups"]["groups"]["bank_statement_as_invoice"]["tag_codes"],
            [],
        )
        self.assertEqual(
            settings["pending_output_invoice_tag_groups"]["groups"]["cash_income"]["tag_codes"],
            ["custom_cash"],
        )

    def test_income_status_override_endpoint_is_idempotent_and_updates_row_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_bank_transaction(app, counterparty_name="Income Customer", credit=True)
            body = {"status_code": "cash_income", "request_id": "income-status-001"}

            response = app.handle_request(
                "PUT",
                f"/api/pending-invoices/rows/{transaction_id}/income-status",
                body=json.dumps(body),
            )
            retry_response = app.handle_request(
                "PUT",
                f"/api/pending-invoices/rows/{transaction_id}/income-status",
                body=json.dumps(body),
            )
            rows_response = app.handle_request("GET", "/api/pending-invoices/rows?direction=income&filter=all")

        payload = json.loads(response.body)
        retry_payload = json.loads(retry_response.body)
        rows_payload = json.loads(rows_response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(retry_payload, payload)
        self.assertEqual(rows_payload["rows"][0]["invoice_acquisition_status"]["code"], "cash_income")

    def test_income_status_batch_endpoint_is_idempotent_and_updates_row_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            first_transaction_id = self._create_bank_transaction(app, counterparty_name="Income Batch A", credit=True)
            second_transaction_id = self._create_bank_transaction(app, counterparty_name="Income Batch B", credit=True)
            body = {
                "transaction_ids": [first_transaction_id, second_transaction_id],
                "status_code": "cash_income",
                "request_id": "income-status-batch-001",
            }

            response = app.handle_request(
                "PUT",
                "/api/pending-invoices/income-statuses",
                body=json.dumps(body),
            )
            retry_response = app.handle_request(
                "PUT",
                "/api/pending-invoices/income-statuses",
                body=json.dumps(body),
            )
            rows_response = app.handle_request("GET", "/api/pending-invoices/rows?direction=income&filter=all")

        payload = json.loads(response.body)
        retry_payload = json.loads(retry_response.body)
        rows_payload = json.loads(rows_response.body)
        statuses = {row["id"]: row["invoice_acquisition_status"]["code"] for row in rows_payload["rows"]}
        self.assertEqual(response.status_code, 200)
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(retry_payload, payload)
        self.assertEqual(payload["affected_transaction_ids"], [first_transaction_id, second_transaction_id])
        self.assertEqual(statuses[first_transaction_id], "cash_income")
        self.assertEqual(statuses[second_transaction_id], "cash_income")

    @staticmethod
    def _create_bank_transaction(app: object, *, counterparty_name: str, credit: bool = False) -> str:
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="api-bank.json",
            imported_by="api-test",
            rows=[
                {
                    "account_no": "622200001234",
                    "txn_date": "2026-05-20",
                    "trade_time": "2026-05-20 10:00:00",
                    "counterparty_name": counterparty_name,
                    "debit_amount": "" if credit else "118.00",
                    "credit_amount": "118.00" if credit else "",
                    "bank_serial_no": f"SERIAL-{counterparty_name}",
                    "selected_bank_name": "工商银行",
                    "selected_bank_last4": "1234",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        return str(preview.row_results[0].linked_object_id)

    @staticmethod
    def _create_input_invoice(app: object, *, seller_name: str, invoice_no: str) -> str:
        preview = app._import_service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="api-input-invoice.json",
            imported_by="api-test",
            rows=[
                {
                    "counterparty_name": seller_name,
                    "invoice_no": invoice_no,
                    "invoice_date": "2026-05-20",
                    "seller_name": seller_name,
                    "buyer_name": "云南溯源科技有限公司",
                    "amount": "118.00",
                    "total_with_tax": "118.00",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        return str(preview.row_results[0].linked_object_id)

    @staticmethod
    def _tag_dictionary_payload() -> dict[str, object]:
        return {
            "version": 7,
            "definitions": [
                {
                    "code": "fee",
                    "label": "手续费",
                    "path": ["费用", "手续费"],
                    "source": "system",
                    "status": "active",
                    "output_primary_label": "费用",
                    "output_sub_label": "手续费",
                },
                {
                    "code": "salary",
                    "label": "工资",
                    "path": ["薪酬", "工资"],
                    "source": "system",
                    "status": "active",
                    "output_primary_label": "薪酬",
                    "output_sub_label": "工资",
                },
                {
                    "code": "custom_meal",
                    "label": "餐饮",
                    "path": ["餐饮"],
                    "source": "custom",
                    "status": "active",
                    "output_primary_label": "餐饮",
                    "output_sub_label": "",
                    "rules": {"match_fields": ["all_text"], "contains": ["餐饮"]},
                },
                {
                    "code": "custom_cash",
                    "label": "现金收入",
                    "path": ["收入", "现金收入"],
                    "source": "custom",
                    "status": "active",
                    "output_primary_label": "收入",
                    "output_sub_label": "现金收入",
                    "rules": {"match_fields": ["all_text"], "contains": ["现金"]},
                },
                {
                    "code": "external_rule_borrow_out",
                    "label": "借出款",
                    "path": ["银行明细自动标签规则", "外部往来款付款", "借出款"],
                    "source": "custom",
                    "status": "active",
                    "output_primary_label": "外部往来款付款",
                    "output_sub_label": "借出款",
                    "turnover_role": "external_turnover",
                    "turnover_action_type": "pending_collection",
                    "rules": {"match_fields": ["all_text"], "contains": ["借出"]},
                },
                {
                    "code": "old_tag",
                    "label": "旧标签",
                    "path": ["历史"],
                    "source": "custom",
                    "status": "archived",
                    "output_primary_label": "历史",
                    "output_sub_label": "旧标签",
                },
            ],
        }

    @classmethod
    def _configure_rule_tags(cls, app: object) -> None:
        app._state_store.save_app_settings(
            {
                "bank_transaction_tags": cls._tag_dictionary_payload(),
                "pending_invoice_tag_groups": {
                    "version": 7,
                    "groups": {
                        "requires_invoice": {"tag_codes": []},
                        "bank_statement_as_invoice": {"tag_codes": []},
                        "no_invoice_required": {"tag_codes": []},
                    },
                },
            }
        )

    @staticmethod
    def _active_rule_codes(tag_source: object, *, excluding: set[str]) -> list[str]:
        if isinstance(tag_source, dict):
            definitions = tag_source.get("definitions") or tag_source.get("tags") or []
        else:
            definitions = tag_source
        return [
            str(definition.get("code"))
            for definition in list(definitions)
            if isinstance(definition, dict)
            and str(definition.get("code") or "")
            and str(definition.get("status") or "active") == "active"
            and str(definition.get("code")) not in excluding
        ]


if __name__ == "__main__":
    unittest.main()
