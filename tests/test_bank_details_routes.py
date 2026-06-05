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

    def confirm_category(self, transaction_id: str, payload: dict[str, object], *, actor_id: str) -> dict[str, object]:
        self.calls.append(("confirm_category", {"transaction_id": transaction_id, "payload": payload, "actor_id": actor_id}))
        if self.confirm_category_error is not None:
            raise self.confirm_category_error
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
