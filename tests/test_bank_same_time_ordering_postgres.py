from __future__ import annotations

import json
import unittest
from decimal import Decimal
from typing import Any

from fin_ops_platform.domain.enums import BatchType, ImportDecision
from fin_ops_platform.services.bank_details_canonical_query import (
    BankDetailsCanonicalQueryService,
    PostgresBankDetailsCanonicalQueryRepository,
)
from fin_ops_platform.services.bank_import_withdrawal_service import BankImportWithdrawalService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.bank_import_withdrawal import (
    PostgresBankImportWithdrawalRepository,
)
from fin_ops_platform.services.postgres_repositories.common import serialize_value
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import (
    PostgresWorkbenchRelationRepository,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.runtime_paths import default_data_dir
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandService

from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class BankSameTimeOrderingPostgresTests(unittest.TestCase):
    """Business assertions against the same PostgreSQL reader used by the page."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.service = BankDetailsCanonicalQueryService(PostgresBankDetailsCanonicalQueryRepository(self.connection))

    def tearDown(self) -> None:
        truncate_test_database(self.database_url)

    def add_transaction(
        self,
        row_id: str,
        *,
        signed_amount: str,
        balance: str | None,
        trade_time: str | None = "2026-09-08 15:36:50+08",
        txn_date: str = "2026-09-08",
        account_no: str = "6222000011118106",
        currency: str | None = "CNY",
        serial: str | None = None,
        summary: str = "匿名测试流水",
        direction: str | None = None,
        imported_bank_name: str = "测试银行",
        imported_bank_last4: str | None = None,
    ) -> None:
        signed = Decimal(signed_amount)
        self.connection.execute(
            """
            insert into app.bank_transactions (
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, balance, txn_date, txn_month, trade_time,
                currency, bank_serial_no, summary, raw_payload, status
            ) values (
                %s, %s, %s, '匿名交易对方', %s, %s, %s, %s::date,
                date_trunc('month', %s::date)::date, %s::timestamptz,
                %s, %s, %s, %s::jsonb, 'active'
            )
            """,
            (
                row_id,
                account_no,
                direction or ("inflow" if signed > 0 else "outflow"),
                abs(signed),
                signed,
                Decimal(balance) if balance is not None else None,
                txn_date,
                txn_date,
                trade_time,
                currency,
                serial,
                summary,
                json.dumps(
                    {
                        "normalized_payload": {
                            "imported_bank_name": imported_bank_name,
                            "imported_bank_last4": imported_bank_last4 or account_no[-4:],
                        }
                    }
                ),
            ),
        )

    def transactions(self, **overrides: Any) -> dict[str, Any]:
        return self.service.transactions_payload(
            **{
                "account_key": None,
                "date_from": None,
                "date_to": None,
                "keyword": None,
                "category_code": None,
                "category_primary_label": None,
                "category_sub_label": None,
                "category_third_label": None,
                "page": 1,
                "page_size": 50,
                **overrides,
            }
        )

    def accounts(self, **overrides: Any) -> dict[str, Any]:
        return self.service.accounts_payload(**{"date_from": None, "date_to": None, **overrides})

    def export(self, **overrides: Any) -> dict[str, Any]:
        return self.service.export_payload(
            **{
                "include_accounts": True,
                "account_key": None,
                "date_from": None,
                "date_to": None,
                "keyword": None,
                "category_code": None,
                "category_primary_label": None,
                "category_sub_label": None,
                "category_third_label": None,
                **overrides,
            }
        )

    def assert_balance(
        self,
        account: dict[str, Any],
        status: str,
        balance: str | None,
        transaction_id: str | None,
    ) -> None:
        self.assertEqual(account["balance_status"], status)
        if balance is None:
            self.assertIsNone(account["latest_balance"])
        else:
            self.assertIsInstance(account["latest_balance"], str)
            self.assertEqual(Decimal(account["latest_balance"]), Decimal(balance))
        self.assertEqual(account["latest_balance_transaction_id"], transaction_id)
        self.assertEqual(account["has_balance"], balance is not None)

    def assert_order(self, payload: dict[str, Any], ids: list[str], status: str) -> None:
        self.assertEqual([row["id"] for row in payload["rows"]], ids)
        self.assertEqual(
            [row["same_time_order_status"] for row in payload["rows"]],
            [status] * len(ids),
        )

    def add_screenshot_groups(self) -> None:
        # Both lexical IDs and serial numbers deliberately favor the wrong fee.
        self.add_transaction("z-new-fee", signed_amount="-1.00", balance="94512.82", serial="999")
        self.add_transaction("a-new-payment", signed_amount="-54000.00", balance="40512.82", serial="001")
        self.add_transaction(
            "z-old-fee",
            signed_amount="-1.00",
            balance="60671.45",
            trade_time="2026-09-03 17:16:44+08",
            txn_date="2026-09-03",
            serial="999",
        )
        self.add_transaction(
            "a-old-payment",
            signed_amount="-300.00",
            balance="60371.45",
            trade_time="2026-09-03 17:16:44+08",
            txn_date="2026-09-03",
            serial="001",
        )

    def test_screenshot_groups_list_accounts_and_export_share_the_proven_order(self) -> None:
        self.add_screenshot_groups()
        before = self.connection.fetch_all(
            "select legacy_mongo_id, trade_time, amount, signed_amount, balance "
            "from app.bank_transactions order by legacy_mongo_id"
        )

        payload = self.transactions()
        expected = ["a-new-payment", "z-new-fee", "a-old-payment", "z-old-fee"]
        self.assert_order(payload, expected, "balance_chain")
        self.assertEqual(payload["pagination"]["total"], 4)
        self.assertEqual(payload["statistics"]["transaction_count"], 4)
        self.assertEqual(payload["statistics"]["expense_transaction_count"], 4)
        self.assertEqual(sum(Decimal(row["amount"]) for row in payload["rows"]), Decimal("54302"))
        self.assertEqual(sum(payload["category_counts"].values()), 4)

        accounts = self.accounts(date_from="2026-09-08", date_to="2026-09-08")
        [account] = accounts["accounts"]
        self.assert_balance(account, "confirmed", "40512.82", "a-new-payment")
        self.assertEqual(account["transaction_count"], 2)
        self.assertEqual(account["transaction_total_count"], 4)
        self.assertEqual(Decimal(accounts["total_balance"]), Decimal("40512.82"))
        exported = self.export()
        self.assert_order(exported["transactions"], expected, "balance_chain")
        self.assert_balance(exported["accounts"]["accounts"][0], "confirmed", "40512.82", "a-new-payment")
        self.assertEqual(
            self.connection.fetch_all(
                "select legacy_mongo_id, trade_time, amount, signed_amount, balance "
                "from app.bank_transactions order by legacy_mongo_id"
            ),
            before,
        )

    def test_page_size_one_and_money_search_keep_the_complete_group_evidence(self) -> None:
        self.add_screenshot_groups()
        for page, row_id in enumerate(["a-new-payment", "z-new-fee", "a-old-payment", "z-old-fee"], start=1):
            with self.subTest(page=page):
                payload = self.transactions(page=page, page_size=1)
                self.assert_order(payload, [row_id], "balance_chain")
                self.assertEqual(payload["pagination"]["total"], 4)
        for keyword, row_id in [("54000", "a-new-payment"), ("300", "a-old-payment")]:
            with self.subTest(keyword=keyword):
                payload = self.transactions(keyword=keyword, page_size=1)
                self.assert_order(payload, [row_id], "balance_chain")
                self.assertEqual(payload["pagination"]["total"], 1)
                self.assert_order(self.export(keyword=keyword)["transactions"], [row_id], "balance_chain")

    def test_three_mixed_flows_use_exact_balances_and_allow_negative_endpoint(self) -> None:
        # 100 -> 120.13 -> 110.11 -> -0.01; neither amount nor balance sorting works.
        self.add_transaction("z-income", signed_amount="20.13", balance="120.13")
        self.add_transaction("m-fee", signed_amount="-10.02", balance="110.11")
        self.add_transaction("a-payment", signed_amount="-110.12", balance="-0.01")
        self.assert_order(self.transactions(), ["a-payment", "m-fee", "z-income"], "balance_chain")
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "-0.01", "a-payment")

    def test_open_chain_does_not_require_continuous_earlier_import_history(self) -> None:
        self.add_transaction("prior", signed_amount="10", balance="999", trade_time="2026-09-08 10:00:00+08")
        self.add_transaction("z-first", signed_amount="-10", balance="90")
        self.add_transaction("a-last", signed_amount="-20", balance="70")
        self.assert_order(
            {"rows": self.transactions()["rows"][:2]},
            ["a-last", "z-first"],
            "balance_chain",
        )
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "70.00", "a-last")

    def test_closed_group_without_prior_single_balance_is_unresolved(self) -> None:
        self.add_transaction("out", signed_amount="-10", balance="90")
        self.add_transaction("in", signed_amount="10", balance="100")
        rows = self.transactions()["rows"]
        self.assertEqual({row["same_time_order_status"] for row in rows}, {"unresolved"})
        self.assertEqual(len(rows), 2)
        payload = self.accounts()
        self.assert_balance(payload["accounts"][0], "unresolved", None, None)
        self.assertIsNone(payload["total_balance"])
        self.assertEqual(payload["total_balances_by_currency"], {})

    def test_closed_group_uses_only_the_immediately_previous_single_balance(self) -> None:
        self.add_transaction("anchor", signed_amount="10", balance="100", trade_time="2026-09-08 10:00:00+08")
        self.add_transaction("z-out", signed_amount="-10", balance="90")
        self.add_transaction("a-in", signed_amount="10", balance="100")
        rows = self.transactions()["rows"]
        self.assert_order({"rows": rows[:2]}, ["a-in", "z-out"], "balance_chain")
        self.assertEqual(rows[2]["same_time_order_status"], "time")
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "100.00", "a-in")

    def test_closed_group_cannot_skip_missing_adjacent_anchor(self) -> None:
        self.add_transaction("old-anchor", signed_amount="10", balance="100", trade_time="2026-09-08 09:00:00+08")
        self.add_transaction("missing-anchor", signed_amount="1", balance=None, trade_time="2026-09-08 10:00:00+08")
        self.add_transaction("out", signed_amount="-10", balance="90")
        self.add_transaction("in", signed_amount="10", balance="100")
        self.assertEqual(
            {row["same_time_order_status"] for row in self.transactions()["rows"][:2]},
            {"unresolved"},
        )
        self.assert_balance(self.accounts()["accounts"][0], "unresolved", None, None)

    def test_branched_group_can_confirm_endpoint_without_claiming_full_order(self) -> None:
        # 0 -> 1 twice and 1 -> 0 once: balance 1 is unique, last row ID is not.
        self.add_transaction("first-copy", signed_amount="1", balance="1")
        self.add_transaction("second-copy", signed_amount="1", balance="1")
        self.add_transaction("return", signed_amount="-1", balance="0")
        payload = self.transactions()
        self.assertEqual(len(payload["rows"]), 3)
        self.assertEqual({row["id"] for row in payload["rows"]}, {"first-copy", "second-copy", "return"})
        self.assertEqual({row["same_time_order_status"] for row in payload["rows"]}, {"unresolved"})
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "1.00", None)
        self.assertEqual(Decimal(self.accounts()["total_balance"]), Decimal("1.00"))

    def test_disconnected_chain_and_cycle_do_not_confirm_a_false_unique_endpoint(self) -> None:
        self.add_transaction("open", signed_amount="1", balance="1")
        self.add_transaction("cycle-out", signed_amount="10", balance="110")
        self.add_transaction("cycle-in", signed_amount="-10", balance="100")
        rows = self.transactions()["rows"]
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["same_time_order_status"] for row in rows}, {"unresolved"})
        self.assert_balance(self.accounts()["accounts"][0], "unresolved", None, None)

    def test_two_disconnected_chains_remain_visible_with_original_balances(self) -> None:
        self.add_transaction("one", signed_amount="-10", balance="90")
        self.add_transaction("two", signed_amount="-20", balance="180")
        rows = self.transactions()["rows"]
        self.assertEqual({row["same_time_order_status"] for row in rows}, {"unresolved"})
        self.assertEqual({row["balance"] for row in rows}, {"90.00", "180.00"})
        self.assert_balance(self.accounts()["accounts"][0], "unresolved", None, None)

    def test_latest_partial_balance_group_does_not_fall_back_to_history(self) -> None:
        self.add_transaction("old", signed_amount="10", balance="100", trade_time="2026-09-08 10:00:00+08")
        self.add_transaction("known", signed_amount="-10", balance="90")
        self.add_transaction("missing", signed_amount="-1", balance=None)
        self.assert_balance(self.accounts()["accounts"][0], "unresolved", None, None)
        self.assertEqual(
            {row["same_time_order_status"] for row in self.transactions()["rows"][:2]},
            {"unresolved"},
        )

    def test_latest_all_missing_uses_proven_historical_group_as_last_known(self) -> None:
        self.add_transaction("z-old-first", signed_amount="-1", balance="99", trade_time="2026-09-08 10:00:00+08")
        self.add_transaction("a-old-last", signed_amount="-10", balance="89", trade_time="2026-09-08 10:00:00+08")
        self.add_transaction("new-missing", signed_amount="-5", balance=None)
        payload = self.accounts()
        self.assert_balance(payload["accounts"][0], "last_known", "89.00", "a-old-last")
        self.assertIsNotNone(payload["accounts"][0]["latest_balance_at"])
        self.assertIsNone(payload["total_balance"])
        self.assertEqual(payload["total_balances_by_currency"], {})
        self.assertEqual(payload["balance_account_count"], 1)
        self.assertEqual(payload["missing_balance_account_count"], 0)

    def test_last_known_does_not_skip_an_unresolved_historical_balance_group(self) -> None:
        self.add_transaction("old-confirmed", signed_amount="10", balance="100", trade_time="2026-09-08 09:00:00+08")
        self.add_transaction("broken-one", signed_amount="-10", balance="90", trade_time="2026-09-08 10:00:00+08")
        self.add_transaction("broken-two", signed_amount="-20", balance="180", trade_time="2026-09-08 10:00:00+08")
        self.add_transaction("new-missing", signed_amount="-5", balance=None)
        self.assert_balance(self.accounts()["accounts"][0], "unresolved", None, None)

    def test_account_without_any_balance_is_missing_and_not_zero(self) -> None:
        self.add_transaction("missing", signed_amount="1", balance=None)
        payload = self.accounts()
        self.assert_balance(payload["accounts"][0], "missing", None, None)
        self.assertIsNone(payload["total_balance"])
        self.assertEqual(payload["total_balances_by_currency"], {})
        self.assertEqual(payload["missing_balance_account_count"], 1)
        self.assert_order(self.transactions(), ["missing"], "time")

    def test_true_zero_balance_and_total_remain_numeric_zero(self) -> None:
        self.add_transaction("z-first", signed_amount="-1", balance="9")
        self.add_transaction("a-last", signed_amount="-9", balance="0")
        payload = self.accounts()
        self.assert_balance(payload["accounts"][0], "confirmed", "0.00", "a-last")
        self.assertIsInstance(payload["total_balance"], str)
        self.assertEqual(Decimal(payload["total_balance"]), Decimal("0.00"))
        self.assertEqual(set(payload["total_balances_by_currency"]), {"CNY"})
        self.assertEqual(Decimal(payload["total_balances_by_currency"]["CNY"]), Decimal("0.00"))

    def test_mixed_date_only_day_stays_unresolved_when_search_hides_missing_time(self) -> None:
        self.add_transaction("date-only", signed_amount="-1", balance="99", trade_time=None)
        self.add_transaction("timed-payment", signed_amount="-50", balance="49")
        self.assertEqual(
            {row["same_time_order_status"] for row in self.transactions()["rows"]},
            {"unresolved"},
        )
        filtered = self.transactions(keyword="50", page_size=1)
        self.assert_order(filtered, ["timed-payment"], "unresolved")
        self.assertEqual(filtered["pagination"]["total"], 1)
        self.assert_order(self.export(keyword="50")["transactions"], ["timed-payment"], "unresolved")
        self.assert_balance(self.accounts()["accounts"][0], "unresolved", None, None)

    def test_single_date_only_row_is_confirmed_without_invented_midnight(self) -> None:
        self.add_transaction("date-only", signed_amount="10", balance="100", trade_time=None)
        payload = self.transactions()
        self.assert_order(payload, ["date-only"], "time")
        self.assertEqual(payload["rows"][0]["trade_time"], "2026-09-08")
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "100.00", "date-only")

    def test_later_complete_day_is_not_invalidated_by_historical_date_only_day(self) -> None:
        self.add_transaction("date-only", signed_amount="-1", balance="99", trade_time=None, txn_date="2026-09-07")
        self.add_transaction(
            "old-timed", signed_amount="-1", balance="98", trade_time="2026-09-07 15:00:00+08", txn_date="2026-09-07"
        )
        self.add_transaction("latest", signed_amount="2", balance="100")
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "100.00", "latest")
        rows = self.transactions()["rows"]
        self.assertEqual(rows[0]["same_time_order_status"], "time")
        self.assertEqual({row["same_time_order_status"] for row in rows[1:]}, {"unresolved"})

    def test_actual_subsecond_times_are_not_collapsed_into_same_second(self) -> None:
        self.add_transaction("z-earlier", signed_amount="1", balance="10", trade_time="2026-09-08 15:36:50.000001+08")
        self.add_transaction("a-later", signed_amount="1", balance="99", trade_time="2026-09-08 15:36:50.000002+08")
        self.assert_order(self.transactions(), ["a-later", "z-earlier"], "time")
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "99.00", "a-later")

    def test_same_last_four_digits_do_not_join_different_accounts_into_one_chain(self) -> None:
        self.add_transaction("one", signed_amount="-1", balance="99", account_no="6222000011118106")
        self.add_transaction("two", signed_amount="-10", balance="89", account_no="6222000022228106")
        payload = self.accounts()
        self.assertEqual(len(payload["accounts"]), 2)
        self.assertEqual(len({row["account_key"] for row in payload["accounts"]}), 2)
        self.assertEqual(Decimal(payload["total_balance"]), Decimal("188.00"))
        self.assertEqual({row["same_time_order_status"] for row in self.transactions()["rows"]}, {"time"})
        for account in payload["accounts"]:
            selected = self.transactions(account_key=account["account_key"])
            self.assertEqual(len(selected["rows"]), 1)
            self.assertEqual(selected["rows"][0]["id"], account["latest_balance_transaction_id"])

    def test_currencies_do_not_form_a_chain_or_a_partial_total(self) -> None:
        self.add_transaction("cny", signed_amount="-1", balance="99", currency="CNY")
        self.add_transaction("usd", signed_amount="-10", balance="89", currency="USD")
        self.add_transaction(
            "other-cny", signed_amount="1", balance="10", currency="CNY", account_no="6222000022228207"
        )
        self.add_transaction(
            "other-usd", signed_amount="1", balance="20", currency="USD", account_no="6222000033338308"
        )
        payload = self.accounts()
        mixed = next(row for row in payload["accounts"] if row["account_last4"] == "8106")
        self.assert_balance(mixed, "unresolved", None, None)
        self.assertIsNone(mixed["currency"])
        self.assertEqual(mixed["transaction_total_count"], 2)
        self.assertIsNone(payload["total_balance"])
        self.assertEqual(payload["total_balances_by_currency"], {})
        self.assertEqual({row["same_time_order_status"] for row in self.transactions()["rows"]}, {"time"})

    def test_existing_cny_alias_and_empty_currency_normalization_share_one_group(self) -> None:
        self.add_transaction("z-first", signed_amount="-1", balance="99", currency="RMB")
        self.add_transaction("m-second", signed_amount="-10", balance="89", currency="人民币")
        self.add_transaction("a-last", signed_amount="-9", balance="80", currency=None)
        self.assert_order(self.transactions(), ["a-last", "m-second", "z-first"], "balance_chain")
        payload = self.accounts()
        self.assert_balance(payload["accounts"][0], "confirmed", "80.00", "a-last")
        self.assertEqual(payload["accounts"][0]["currency"], "CNY")
        self.assertEqual(Decimal(payload["total_balance"]), Decimal("80.00"))

    def test_direction_signed_amount_conflict_cannot_establish_balance_chain(self) -> None:
        self.add_transaction("conflict", signed_amount="10", balance="110", direction="outflow")
        self.add_transaction("valid", signed_amount="-1", balance="109")
        self.assertEqual({row["same_time_order_status"] for row in self.transactions()["rows"]}, {"unresolved"})
        self.assert_balance(self.accounts()["accounts"][0], "unresolved", None, None)

    def test_all_income_chain_preserves_full_numeric_precision_when_ordering(self) -> None:
        self.add_transaction("z-first", signed_amount="0.000001", balance="0.000001")
        self.add_transaction("m-second", signed_amount="0.000002", balance="0.000003")
        self.add_transaction("a-last", signed_amount="0.000004", balance="0.000007")
        self.assert_order(self.transactions(), ["a-last", "m-second", "z-first"], "balance_chain")
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "0.000007", "a-last")
        [fact] = self.connection.fetch_all("select balance from app.bank_transactions where legacy_mongo_id = 'a-last'")
        self.assertEqual(fact["balance"], Decimal("0.000007"))

    def test_empty_database_has_no_accounts_transactions_or_fabricated_total(self) -> None:
        payload = self.accounts()
        self.assertEqual(payload["accounts"], [])
        self.assertIsNone(payload["total_balance"])
        self.assertEqual(payload["total_balances_by_currency"], {})
        self.assertEqual(payload["balance_account_count"], 0)
        self.assertEqual(payload["missing_balance_account_count"], 0)
        transactions = self.transactions()
        self.assertEqual(transactions["rows"], [])
        self.assertEqual(transactions["pagination"]["total"], 0)

    def test_date_filter_changes_account_count_but_not_latest_balance_source(self) -> None:
        self.add_screenshot_groups()
        payload = self.accounts(date_from="2026-09-03", date_to="2026-09-03")
        [account] = payload["accounts"]
        self.assert_balance(account, "confirmed", "40512.82", "a-new-payment")
        self.assertEqual(account["transaction_count"], 2)
        self.assertEqual(account["transaction_total_count"], 4)
        self.assert_order(
            self.transactions(date_from="2026-09-03", date_to="2026-09-03"),
            ["a-old-payment", "z-old-fee"],
            "balance_chain",
        )

    def test_missing_balance_account_is_retained_outside_date_range_and_invalidates_total(self) -> None:
        self.add_transaction("known", signed_amount="10", balance="950")
        self.add_transaction(
            "missing",
            signed_amount="-20",
            balance=None,
            account_no="6222000011111410",
            trade_time="2026-09-07 10:00:00+08",
            txn_date="2026-09-07",
        )
        payload = self.accounts(date_from="2026-09-08", date_to="2026-09-08")
        self.assertEqual(len(payload["accounts"]), 2)
        by_last4 = {account["account_last4"]: account for account in payload["accounts"]}
        self.assert_balance(by_last4["8106"], "confirmed", "950", "known")
        self.assertEqual(by_last4["8106"]["transaction_count"], 1)
        self.assert_balance(by_last4["1410"], "missing", None, None)
        self.assertEqual(by_last4["1410"]["transaction_count"], 0)
        self.assertEqual(by_last4["1410"]["transaction_total_count"], 1)
        self.assertEqual(payload["balance_account_count"], 1)
        self.assertEqual(payload["missing_balance_account_count"], 1)
        self.assertIsNone(payload["total_balance"])
        self.assertEqual(payload["total_balances_by_currency"], {})

    def test_real_account_identity_and_consistent_metadata_survive_settings_display_mapping(self) -> None:
        self.add_transaction(
            "consistent",
            signed_amount="10",
            balance="100",
            trade_time="2026-09-08 10:00:00+08",
            imported_bank_name="正确银行",
        )
        self.add_transaction(
            "latest-mislabeled",
            signed_amount="-1",
            balance="99",
            imported_bank_name="错误历史银行",
            imported_bank_last4="9999",
        )
        [account] = self.accounts()["accounts"]
        original_key = account["account_key"]
        self.assertEqual(account["account_no"], "6222000011118106")
        self.assertEqual(account["account_last4"], "8106")
        self.assertEqual(account["bank_name"], "正确银行")
        self.assertEqual(account["display_name"], "正确银行 8106")
        self.assert_balance(account, "confirmed", "99", "latest-mislabeled")
        PostgresStateStore(data_dir=default_data_dir(), connection=self.connection).save_app_settings(
            {
                "bank_account_mappings": [
                    {"bank_name": "配置银行", "last4": "8106"},
                    {"bank_name": "错误尾号配置", "last4": "9999"},
                ]
            }
        )
        [mapped] = self.accounts()["accounts"]
        self.assertEqual(mapped["account_key"], original_key)
        self.assertEqual(mapped["account_no"], "6222000011118106")
        self.assertEqual(mapped["account_last4"], "8106")
        self.assertEqual(mapped["bank_name"], "配置银行")
        self.assertEqual(mapped["display_name"], "配置银行 8106")
        self.assert_balance(mapped, "confirmed", "99", "latest-mislabeled")

    def test_formal_import_duplicate_and_withdrawal_recompute_query_without_refresh_jobs(self) -> None:
        repository = PostgresCoreRepository(self.connection)
        importer = ImportNormalizationService(fact_repository=repository)

        def confirm_row(*, amount: str, balance: str, serial: str) -> Any:
            preview = importer.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name=f"anonymous-{serial}.json",
                imported_by="bank-order-test",
                rows=[
                    {
                        "account_no": "6222000011118106",
                        "txn_date": "2026-09-08",
                        "trade_time": "2026-09-08 15:36:50",
                        "counterparty_name": "匿名交易对方",
                        "debit_amount": amount,
                        "credit_amount": "",
                        "balance": balance,
                        "currency": "CNY",
                        "bank_serial_no": serial,
                        "summary": "匿名合成银行导入",
                    }
                ],
            )
            importer.confirm_import(preview.id)
            repository.save_import_delta(serialize_value(importer.persistence_snapshot_for_batches([preview.id])), {})
            return preview

        fee = confirm_row(amount="1.00", balance="94512.82", serial="999-fee")
        fee_id = fee.row_results[0].linked_object_id
        self.assertEqual(fee.row_results[0].decision, ImportDecision.CREATED)
        self.assert_order(self.transactions(), [fee_id], "time")
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "94512.82", fee_id)

        payment = confirm_row(amount="54000.00", balance="40512.82", serial="001-payment")
        payment_id = payment.row_results[0].linked_object_id
        self.assertEqual(payment.row_results[0].decision, ImportDecision.CREATED)
        self.assert_order(self.transactions(), [payment_id, fee_id], "balance_chain")
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "40512.82", payment_id)
        self.assert_order(self.export()["transactions"], [payment_id, fee_id], "balance_chain")

        duplicate = confirm_row(amount="1.00", balance="94512.82", serial="999-fee")
        self.assertEqual(duplicate.row_results[0].decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(duplicate.row_results[0].linked_object_id, fee_id)
        self.assertEqual(self.transactions()["pagination"]["total"], 2)

        withdrawal = BankImportWithdrawalService(
            repository=PostgresBankImportWithdrawalRepository(self.connection),
            relation_service_for_transaction=lambda transaction: WorkbenchRelationCommandService(
                relation_repository=PostgresWorkbenchRelationRepository(transaction),
                tenant_id="default",
            ),
        )
        result = withdrawal.withdraw(batch_id=payment.id, actor_id="bank-order-test")
        self.assertEqual(result["withdrawn_count"], 1)
        self.assertFalse(result["idempotent_replay"])
        self.assert_order(self.transactions(), [fee_id], "time")
        self.assert_balance(self.accounts()["accounts"][0], "confirmed", "94512.82", fee_id)
        self.assert_order(self.export()["transactions"], [fee_id], "time")
        replay = withdrawal.withdraw(batch_id=payment.id, actor_id="bank-order-test")
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["withdrawn_count"], 1)
        self.assertEqual(self.transactions()["pagination"]["total"], 1)
        [job_count] = self.connection.fetch_all("select count(*) as count from job.outbox_events")
        self.assertEqual(job_count["count"], 0)


if __name__ == "__main__":
    unittest.main()
