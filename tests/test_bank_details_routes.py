from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from types import SimpleNamespace
import unittest

from fin_ops_platform.app.routes_bank_details import BankDetailsApiRoutes
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryValidationError


@dataclass(slots=True)
class FakeBankDetailsExportResult:
    filename: str = "bank-details.xlsx"
    content: bytes = b"xlsx"
    row_count: int = 1
    sheet_names: list[str] | None = None


class FakeBankDetailsApplicationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.confirm_category_error: BankTransactionCategoryValidationError | None = None
        self.accounts_result: dict[str, object] = {
            "accounts": [],
            "read_model_status": "fresh",
        }
        self.transactions_result: dict[str, object] = {
            "rows": [],
            "read_model_status": "fresh",
        }

    def accounts_payload(self, *, date_from: str | None, date_to: str | None) -> dict[str, object]:
        self.calls.append(("accounts", {"date_from": date_from, "date_to": date_to}))
        return self.accounts_result

    def transactions_payload(self, **kwargs) -> dict[str, object]:
        self.calls.append(("transactions", dict(kwargs)))
        return self.transactions_result

    def get_auto_tag_rules_payload(self, *, can_save: bool) -> dict[str, object]:
        self.calls.append(("auto_tag_rules", {"can_save": can_save}))
        return {"version": 1, "active_rules": [], "can_save": can_save}

    def update_auto_tag_rules(self, payload: dict[str, object], *, actor_id: str) -> dict[str, object]:
        self.calls.append(("update_auto_tag_rules", {"payload": payload, "actor_id": actor_id}))
        return {"version": 2}

    def replace_auto_tag_rules_from_file_source(self, source: object, *, actor_id: str) -> dict[str, object]:
        self.calls.append(("replace_auto_tag_rules", {"source": source, "actor_id": actor_id}))
        return {"version": 3}

    def reapply_auto_tag_rules(self, *, actor_id: str, can_save: bool) -> dict[str, object]:
        self.calls.append(("reapply_auto_tag_rules", {"actor_id": actor_id, "can_save": can_save}))
        return {"version": 4, "read_model_status": "refreshing"}

    def confirm_category(self, transaction_id: str, payload: dict[str, object], *, actor_id: str) -> dict[str, object]:
        self.calls.append(("confirm_category", {"transaction_id": transaction_id, "payload": payload, "actor_id": actor_id}))
        if self.confirm_category_error is not None:
            raise self.confirm_category_error
        return {"transaction_id": transaction_id, "affected_months": ["2026-05"]}

    def revoke_category_confirmation(self, transaction_id: str, *, actor_id: str) -> dict[str, object]:
        self.calls.append(("revoke_category", {"transaction_id": transaction_id, "actor_id": actor_id}))
        return {"transaction_id": transaction_id, "affected_months": ["2026-05"]}

    def assign_manual_category(self, transaction_id: str, payload: dict[str, object], *, actor_id: str) -> dict[str, object]:
        self.calls.append(("assign_category", {"transaction_id": transaction_id, "payload": payload, "actor_id": actor_id}))
        return {"transaction_id": transaction_id, "affected_months": ["2026-05"]}

    def clear_manual_category(self, transaction_id: str, *, actor_id: str) -> dict[str, object]:
        self.calls.append(("clear_category", {"transaction_id": transaction_id, "actor_id": actor_id}))
        return {"transaction_id": transaction_id, "affected_months": ["2026-05"]}

    def export_transactions(self, **kwargs) -> FakeBankDetailsExportResult:
        self.calls.append(("export_transactions", dict(kwargs)))
        return FakeBankDetailsExportResult(sheet_names=["银行明细"])


class BankDetailsRoutesTests(unittest.TestCase):
    @staticmethod
    def _session(*, username: str = "finance-user", can_mutate_data: bool = True):
        return SimpleNamespace(
            identity=SimpleNamespace(username=username, user_id="oa-001"),
            can_mutate_data=can_mutate_data,
        )

    def test_routes_facade_delegates_reads_and_preserves_stale_rows_as_200(self) -> None:
        service = FakeBankDetailsApplicationService()
        service.accounts_result = {
            "accounts": [{"account_key": "icbc:0001"}],
            "read_model_status": "refreshing",
            "read_model_scope_keys": ["2026-05"],
        }
        routes = BankDetailsApiRoutes(application_service=service)

        status, payload = routes.accounts(date_from="2026-05-01", date_to="2026-05-31")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["accounts"], [{"account_key": "icbc:0001"}])
        self.assertEqual(
            service.calls,
            [("accounts", {"date_from": "2026-05-01", "date_to": "2026-05-31"})],
        )

    def test_route_owner_handles_read_and_export_http_mapping_with_platform_ports(self) -> None:
        service = FakeBankDetailsApplicationService()
        responses: list[tuple[HTTPStatus, object]] = []
        exports: list[tuple[HTTPStatus, object]] = []
        session = self._session(username="exporter")
        routes = BankDetailsApiRoutes(
            application_service=service,
            resolve_read_session=lambda _headers: (session, None),
            json_response=lambda status, payload: responses.append((status, payload)) or {"status": status, "payload": payload},
            export_response=lambda status, result: exports.append((status, result)) or {"status": status, "filename": result.filename},
        )

        accounts_response = routes.route(
            "GET",
            "/api/bank-details/accounts",
            {"date_from": ["2026-05-01"], "date_to": ["2026-05-31"]},
            None,
            {},
        )
        rules_response = routes.route("GET", "/api/bank-details/auto-tag-rules", {}, None, {})
        export_response = routes.route(
            "GET",
            "/api/bank-details/transactions/export",
            {
                "mode": ["filtered"],
                "date_from": ["2026-05-01"],
                "date_to": ["2026-05-31"],
                "keyword": ["外部候选"],
            },
            None,
            {},
        )

        self.assertEqual(accounts_response["status"], HTTPStatus.OK)
        self.assertTrue(rules_response["payload"]["can_save"])
        self.assertEqual(export_response, {"status": HTTPStatus.OK, "filename": "bank-details.xlsx"})
        self.assertEqual(exports[0][1].filename, "bank-details.xlsx")
        self.assertEqual(
            service.calls,
            [
                ("accounts", {"date_from": "2026-05-01", "date_to": "2026-05-31"}),
                ("auto_tag_rules", {"can_save": True}),
                (
                    "export_transactions",
                    {
                        "mode": "filtered",
                        "account_key": None,
                        "date_from": "2026-05-01",
                        "date_to": "2026-05-31",
                        "keyword": "外部候选",
                        "category_code": None,
                        "category_primary_label": None,
                        "category_sub_label": None,
                        "category_third_label": None,
                        "actor_id": "exporter",
                    },
                ),
            ],
        )

    def test_routes_facade_returns_202_only_when_refreshing_payload_has_no_rows(self) -> None:
        service = FakeBankDetailsApplicationService()
        service.transactions_result = {
            "rows": [],
            "read_model_status": "refreshing",
            "read_model_scope_keys": ["2026-05"],
        }
        routes = BankDetailsApiRoutes(application_service=service)

        status, payload = routes.transactions(
            account_key=None,
            date_from="2026-05-01",
            date_to="2026-05-31",
            keyword=None,
            category_code=None,
            category_primary_label=None,
            category_sub_label=None,
            category_third_label=None,
            page="2",
            page_size="50",
        )

        self.assertEqual(status, HTTPStatus.ACCEPTED)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(service.calls[0][0], "transactions")
        self.assertEqual(service.calls[0][1]["page"], 2)
        self.assertEqual(service.calls[0][1]["page_size"], 50)

    def test_route_owner_handles_auto_tag_write_mapping_with_body_and_default_source_ports(self) -> None:
        service = FakeBankDetailsApplicationService()
        responses: list[tuple[HTTPStatus, object]] = []
        session = self._session(username="writer")
        routes = BankDetailsApiRoutes(
            application_service=service,
            resolve_read_session=lambda _headers: (session, None),
            json_response=lambda status, payload: responses.append((status, payload)) or {"status": status, "payload": payload},
            load_json_body=lambda body: ({"version": 1, "body": body}, None),
            default_auto_tag_rules_source_provider=lambda: {"source": "bundled"},
        )

        put_response = routes.route("PUT", "/api/bank-details/auto-tag-rules", {}, "{}", {})
        reapply_response = routes.route("POST", "/api/bank-details/auto-tag-rules/reapply", {}, "not-json", {})
        replacement_response = routes.route("POST", "/api/bank-details/auto-tag-rules/file-replacement", {}, None, {})

        self.assertEqual(put_response["status"], HTTPStatus.OK)
        self.assertEqual(reapply_response["status"], HTTPStatus.ACCEPTED)
        self.assertEqual(replacement_response["status"], HTTPStatus.OK)
        self.assertEqual(
            service.calls,
            [
                ("update_auto_tag_rules", {"payload": {"version": 1, "body": "{}"}, "actor_id": "writer"}),
                ("reapply_auto_tag_rules", {"actor_id": "writer", "can_save": True}),
                ("replace_auto_tag_rules", {"source": {"source": "bundled"}, "actor_id": "writer"}),
            ],
        )

    def test_routes_facade_delegates_mutations_with_default_actor(self) -> None:
        service = FakeBankDetailsApplicationService()
        routes = BankDetailsApiRoutes(application_service=service)

        update_status, update_payload = routes.update_auto_tag_rules({"version": 1}, session=None)
        confirm_status, confirm_payload = routes.confirm_category("bank-row-001", {"category_code": "fee"}, session=None)

        self.assertEqual(update_status, HTTPStatus.OK)
        self.assertEqual(update_payload["version"], 2)
        self.assertEqual(confirm_status, HTTPStatus.OK)
        self.assertEqual(confirm_payload["affected_months"], ["2026-05"])
        self.assertEqual(
            service.calls,
            [
                ("update_auto_tag_rules", {"payload": {"version": 1}, "actor_id": "bank_auto_tag_rules"}),
                (
                    "confirm_category",
                    {
                        "transaction_id": "bank-row-001",
                        "payload": {"category_code": "fee"},
                        "actor_id": "bank_category_confirmation",
                    },
                ),
            ],
        )

    def test_route_owner_handles_category_write_mapping_with_transaction_id_and_body_ports(self) -> None:
        service = FakeBankDetailsApplicationService()
        session = self._session(username="category-writer")
        routes = BankDetailsApiRoutes(
            application_service=service,
            resolve_read_session=lambda _headers: (session, None),
            json_response=lambda status, payload: {"status": status, "payload": payload},
            load_json_body=lambda body: ({"category_code": "fee", "body": body}, None),
        )

        confirm_response = routes.route(
            "POST",
            "/api/bank-details/transactions/txn%2F001/category-confirmation",
            {},
            "{}",
            {},
        )
        revoke_response = routes.route(
            "DELETE",
            "/api/bank-details/transactions/txn%2F001/category-confirmation",
            {},
            None,
            {},
        )
        assign_response = routes.route(
            "POST",
            "/api/bank-details/transactions/txn%2F001/category-assignment",
            {},
            "{}",
            {},
        )
        clear_response = routes.route(
            "DELETE",
            "/api/bank-details/transactions/txn%2F001/category-assignment",
            {},
            None,
            {},
        )

        self.assertEqual(confirm_response["status"], HTTPStatus.OK)
        self.assertEqual(revoke_response["status"], HTTPStatus.OK)
        self.assertEqual(assign_response["status"], HTTPStatus.OK)
        self.assertEqual(clear_response["status"], HTTPStatus.OK)
        self.assertEqual(
            service.calls,
            [
                (
                    "confirm_category",
                    {
                        "transaction_id": "txn/001",
                        "payload": {"category_code": "fee", "body": "{}"},
                        "actor_id": "category-writer",
                    },
                ),
                ("revoke_category", {"transaction_id": "txn/001", "actor_id": "category-writer"}),
                (
                    "assign_category",
                    {
                        "transaction_id": "txn/001",
                        "payload": {"category_code": "fee", "body": "{}"},
                        "actor_id": "category-writer",
                    },
                ),
                ("clear_category", {"transaction_id": "txn/001", "actor_id": "category-writer"}),
            ],
        )

    def test_route_owner_keeps_disabled_bulk_category_patch_without_service_call(self) -> None:
        service = FakeBankDetailsApplicationService()
        routes = BankDetailsApiRoutes(
            application_service=service,
            json_response=lambda status, payload: {"status": status, "payload": payload},
        )

        response = routes.route("PATCH", "/api/bank-details/transactions/categories", {}, "{}", {})

        self.assertEqual(response["status"], HTTPStatus.GONE)
        self.assertEqual(response["payload"]["error"], "manual_bank_transaction_category_disabled")
        self.assertEqual(service.calls, [])

    def test_routes_facade_denies_mutations_before_calling_application_service(self) -> None:
        service = FakeBankDetailsApplicationService()
        routes = BankDetailsApiRoutes(application_service=service)

        update_status, update_payload = routes.update_auto_tag_rules(
            {"version": 1},
            session=self._session(can_mutate_data=False),
        )
        confirm_status, confirm_payload = routes.confirm_category(
            "bank-row-001",
            {"category_code": "fee"},
            session=self._session(can_mutate_data=False),
        )

        self.assertEqual(update_status, HTTPStatus.FORBIDDEN)
        self.assertEqual(update_payload["error"], "permission_denied")
        self.assertEqual(confirm_status, HTTPStatus.FORBIDDEN)
        self.assertEqual(confirm_payload["error"], "permission_denied")
        self.assertEqual(service.calls, [])

    def test_routes_facade_maps_category_validation_error_without_hiding_transaction_id(self) -> None:
        service = FakeBankDetailsApplicationService()
        service.confirm_category_error = BankTransactionCategoryValidationError(
            "bank_transaction_tags_version_conflict",
            "version conflict",
            transaction_id="bank-row-001",
            expected_version=2,
            actual_version=3,
        )
        routes = BankDetailsApiRoutes(application_service=service)

        status, payload = routes.confirm_category(
            "bank-row-001",
            {"category_code": "fee", "expected_version": 2},
            session=self._session(username="alice"),
        )

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload["error"], "bank_transaction_tags_version_conflict")
        self.assertEqual(payload["transaction_id"], "bank-row-001")
        self.assertEqual(service.calls[0][1]["actor_id"], "alice")

    def test_routes_facade_delegates_export_to_application_service(self) -> None:
        service = FakeBankDetailsApplicationService()
        routes = BankDetailsApiRoutes(application_service=service)

        status, result = routes.export_transactions(
            mode="all",
            account_key=None,
            date_from="2026-05-01",
            date_to="2026-05-31",
            keyword="外部候选",
            category_code="external_payment",
            category_primary_label="外部往来款付款",
            category_sub_label="借出款",
            category_third_label="公司往来",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(result.filename, "bank-details.xlsx")
        self.assertEqual(
            service.calls,
            [
                (
                    "export_transactions",
                    {
                        "mode": "all",
                        "account_key": None,
                        "date_from": "2026-05-01",
                        "date_to": "2026-05-31",
                        "keyword": "外部候选",
                        "category_code": "external_payment",
                        "category_primary_label": "外部往来款付款",
                        "category_sub_label": "借出款",
                        "category_third_label": "公司往来",
                        "actor_id": "bank_detail_export",
                    },
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
