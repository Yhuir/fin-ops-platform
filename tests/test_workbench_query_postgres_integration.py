from __future__ import annotations

import json
import os
import time
import unittest
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.workbench_page_query import (
    PostgresWorkbenchPageQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench import (
    PostgresWorkbenchRepository,
)
from fin_ops_platform.services.workbench_direct_query_errors import (
    WorkbenchDirectQueryUnavailable,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_selection import (
    PostgresWorkbenchPageSelectionRepository,
)
from fin_ops_platform.services.workbench_canonical_rows import (
    WorkbenchCanonicalRowsBuilder,
)
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class _InstrumentedConnection:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.statements: list[dict[str, object]] = []

    def _measure(
        self,
        operation: str,
        sql: str,
        params: tuple[Any, ...],
        callback: Any,
    ) -> Any:
        started = time.perf_counter()
        result: Any = None
        try:
            result = callback()
            return result
        finally:
            statement: dict[str, object] = {
                "operation": operation,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "sql": " ".join(sql.split())[:240],
                "raw_sql": sql,
                "params": params,
            }
            if isinstance(result, list):
                statement["metadata_row_count"] = sum(
                    1
                    for row in result
                    if isinstance(row, dict) and row.get("record_zone") == "metadata"
                )
                statement["page_rows_with_anomaly_payload"] = sum(
                    1
                    for row in result
                    if isinstance(row, dict)
                    and row.get("record_zone") in {"paired", "unpaired"}
                    and (
                        row.get("anomaly_members") not in (None, [])
                        or row.get("ignored_anomaly_fingerprints") not in (None, [])
                    )
                )
            self.statements.append(statement)

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return self._measure(
            "fetch_all",
            sql,
            params,
            lambda: self._connection.fetch_all(sql, params),
        )

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return self._measure(
            "fetch_one",
            sql,
            params,
            lambda: self._connection.fetch_one(sql, params),
        )

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return self._measure(
            "execute",
            sql,
            params,
            lambda: self._connection.execute(sql, params),
        )

    def transaction(self) -> Any:
        connection = self
        outer_connection = self._connection
        delegate = outer_connection.transaction()

        class _Transaction:
            def __enter__(self) -> _InstrumentedConnection:
                transaction = delegate.__enter__()
                connection._connection = transaction
                return connection

            def __exit__(self, *args: object) -> object:
                try:
                    return delegate.__exit__(*args)
                finally:
                    connection._connection = outer_connection

        return _Transaction()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class WorkbenchQueryPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.raw_connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self.connection = _InstrumentedConnection(self.raw_connection)
        self.repository = PostgresWorkbenchPageQueryRepository(
            self.connection, tenant_id="default"
        )
        self.selection_repository = PostgresWorkbenchPageSelectionRepository(
            self.connection, tenant_id="default"
        )
        self._insert_canonical_fixtures()

    def tearDown(self) -> None:
        self.raw_connection.close()
        truncate_test_database(self.database_url)

    def _insert_canonical_fixtures(self) -> None:
        settings_payload = {
            "allowed_usernames": ["YNSYLP005"],
            "readonly_export_usernames": [],
            "admin_usernames": ["YNSYLP005"],
            "full_access_usernames": [],
            "access_control_version": 1,
            "bank_transaction_tags": {
                "version": 2,
                "definitions": [
                    {
                        "code": "materials",
                        "label": "材料采购",
                        "path": ["货款", "材料采购"],
                        "output_primary_label": "货款",
                        "output_sub_label": "材料采购",
                        "status": "active",
                        "priority": 2,
                        "sort_order": 1,
                        "rules": {
                            "match_fields": ["summary_text"],
                            "contains_any": ["材料款"],
                        },
                    }
                ],
            },
        }
        self.raw_connection.execute(
            """
            insert into app.app_settings(settings_key, settings_payload, raw_payload)
            values ('app_settings', %s::jsonb, %s::jsonb)
            on conflict (settings_key) do nothing
            """,
            (
                json.dumps(settings_payload, ensure_ascii=False),
                json.dumps(
                    {"normalized_payload": settings_payload},
                    ensure_ascii=False,
                ),
            ),
        )
        self.raw_connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values
                (
                    'etc_202607_unlinked', 'oa_submitted', '2026-07-01', 1,
                    88, '{"normalized_payload":{"external_etc_batch_id":"etc_202607_unlinked"}}'::jsonb
                ),
                (
                    'etc_202607_linked', 'oa_submitted', '2026-07-01', 1,
                    44, '{"normalized_payload":{"external_etc_batch_id":"etc_202607_linked"}}'::jsonb
                ),
                (
                    'etc_202607_special', 'oa_submitted', '2026-07-01', 1,
                    33, '{"normalized_payload":{"external_etc_batch_id":"ETC 空格/中文"}}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            ) values
                (
                    'etc-invoice-direct-1', 'etc_202607_unlinked', 'submitted',
                    'ETC-INV-DIRECT', '2026-07-24', 'ETC供应商', 80, 8, 88,
                    '{}'::jsonb
                ),
                (
                    'etc-invoice-direct-2', 'etc_202607_linked', 'submitted',
                    'ETC-INV-LINKED', '2026-07-24', 'ETC供应商', 40, 4, 44,
                    '{}'::jsonb
                ),
                (
                    'etc-invoice-direct-3', 'etc_202607_special', 'submitted',
                    'ETC-INV-SPECIAL', '2026-07-25', 'ETC特殊供应商', 30, 3, 33,
                    '{}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            ) values (
                'oa-source-direct', 'payment_request', '付款申请', 'oa-direct-1',
                'active', 'completed', '张三', '2026-07-21', '2026-07-01',
                '直接查询项目', 100, 'CNY',
                '{"id":"oa-direct-1","month":"2026-07","section":"unpaired","applicant":"张三","project_name":"直接查询项目","expense_type":"交通费","amount":"100","workflow_status":"completed","expense_items":[{"id":"oa-direct-1:item:0","amount":"100","attachment_file_count":"0"}]}'::jsonb,
                '{}'::jsonb
            )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values
                ('bank-direct-1', '6222000011118106', '基本户', 'outflow',
                 '云南腾安科技有限公司', 100, -100, '2026-07-22', '2026-07-01',
                 '2026-07-22 10:00:00+08', '材料款', '{}'::jsonb, 'active'),
                ('same-text-id', '6222000011118107', '基本户', 'outflow',
                 '银行同名', 10, -10, '2026-07-23', '2026-07-01',
                 '2026-07-23 10:00:00+08', '同名', '{}'::jsonb, 'active')
            """
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, workbench_visibility,
                source_links, raw_payload
            ) values (
                'same-text-id', 'input', 'INV-SAME', '2026-07-23', '2026-07-01',
                10, 10, 10, 'active', 'visible', '[]'::jsonb, '{}'::jsonb
            )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-DIRECT-1', 'manual_confirmed', 'active', 1, '2026-07-01',
                array['oa-direct-1','bank-direct-1','etc-summary-etc_202607_linked'],
                array['oa','bank','invoice'],
                '{}'::jsonb,
                '{"requires_invoice":false,"external_etc_batch_id":"etc_202607_linked"}'::jsonb,
                '{}'::jsonb
            )
            """
        )

    def test_direct_initial_and_groups_use_canonical_facts_without_read_model(self) -> None:
        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")

        self.assertEqual(initial["summary"]["oa_count"], 1)
        self.assertEqual(initial["summary"]["bank_count"], 2)
        self.assertEqual(initial["summary"]["invoice_count"], 4)
        self.assertEqual(initial["summary"]["paired_count"], 0)
        self.assertEqual(initial["summary"]["unpaired_count"], 5)
        self.assertEqual(initial["paired"]["total"], 0)
        self.assertEqual(initial["unpaired"]["total"], 5)
        initial_oa_rows = [
            row
            for zone in ("paired", "unpaired")
            for group in initial[zone]["groups"]
            for row in list(group.get("oa_rows") or [])
        ]
        self.assertEqual(initial_oa_rows[0]["expense_type"], "交通费")
        initial_bank_rows = [
            row
            for zone in ("paired", "unpaired")
            for group in initial[zone]["groups"]
            for row in list(group.get("bank_rows") or [])
        ]
        bank_direct = next(
            row for row in initial_bank_rows if row.get("id") == "bank-direct-1"
        )
        self.assertEqual(bank_direct["category_code"], "materials")
        self.assertEqual(bank_direct["category_label"], "材料采购")
        self.assertEqual(bank_direct["category_label_path"], ["货款", "材料采购"])
        self.assertEqual(bank_direct["category_resolution_status"], "auto_matched")
        same_text_bank = next(
            row for row in initial_bank_rows if row.get("id") == "same-text-id"
        )
        self.assertEqual(same_text_bank["category_resolution_status"], "unmatched")
        etc_groups = [
            group
            for group in initial["unpaired"]["groups"]
            if list(group.get("invoice_rows") or [])
            and group["invoice_rows"][0].get("etc_batch_id")
            == "etc_202607_unlinked"
        ]
        self.assertEqual(len(etc_groups), 1)
        self.assertEqual(
            etc_groups[0]["invoice_rows"][0]["source_kind"],
            "etc_invoice_summary",
        )
        special_group = next(
            group
            for group in initial["unpaired"]["groups"]
            if list(group.get("invoice_rows") or [])
            and group["invoice_rows"][0].get("etc_batch_id") == "ETC 空格/中文"
        )
        self.assertEqual(
            special_group["invoice_rows"][0]["id"],
            "etc-summary-ETC-"
        )
        self.assertEqual(
            next(
                group
                for group in initial["unpaired"]["groups"]
                if group.get("detail_key") == "CASE-DIRECT-1"
            )["invoice_rows"][0]["source_kind"],
            "etc_invoice_summary",
        )
        initial_statement = next(
            statement
            for statement in self.connection.statements
            if "with recursive requested_scope" in str(statement.get("sql") or "")
        )
        self.assertEqual(initial_statement["operation"], "fetch_all")
        self.assertEqual(initial_statement["metadata_row_count"], 1)
        self.assertEqual(initial_statement["page_rows_with_anomaly_payload"], 0)
        self.assertNotIn("read_model_version", initial)
        self.assertNotIn("generation_id", initial)
        self.assertFalse(
            any("read_model.workbench_" in str(statement["sql"]) for statement in self.connection.statements)
        )
        classification_statements = [
            statement
            for statement in self.connection.statements
            if "classified_with_semantics" in str(statement.get("raw_sql") or "")
        ]
        self.assertEqual(len(classification_statements), 1)
        self.assertEqual(
            classification_statements[0]["params"][-1],
            ["bank-direct-1", "same-text-id"],
        )

        detail = self.repository.get_workbench_row_detail(
            scope_key="2026-07",
            row_id="bank-direct-1",
            row_type="bank",
        )
        self.assertEqual(detail["row"]["category_code"], "materials")
        self.assertEqual(detail["row"]["category_label"], "材料采购")
        self.assertEqual(detail["row"]["category_resolution_status"], "auto_matched")

        self.connection.statements.clear()
        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="云南腾安%",
        )
        self.assertEqual(page["total"], 0, "percent must be treated as a literal")
        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="云南腾安科技有限公司",
        )
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["groups"][0]["detail_key"], "CASE-DIRECT-1")

    def test_unpaired_submitted_etc_summary_detail_hydrates_all_invoices(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values (
                'etc_detail_49', 'oa_submitted', '2026-07-01', 49, 49,
                '{"normalized_payload":{"external_etc_batch_id":"etc_detail_49"}}'::jsonb
            );
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            )
            select
                'etc-detail-' || item::text,
                'etc_detail_49',
                'submitted',
                'ETC-DETAIL-' || lpad(item::text, 2, '0'),
                '2026-07-20'::date,
                'ETC详情供应商',
                1,
                0,
                1,
                '{}'::jsonb
            from generate_series(1, 49) item
            """
        )

        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            page_size=100,
        )
        group = next(
            item
            for item in page["groups"]
            if list(item.get("invoice_rows") or [])
            and item["invoice_rows"][0].get("etc_batch_id") == "etc_detail_49"
        )
        detail = self.repository.get_workbench_group_detail(
            scope_key="all",
            zone="unpaired",
            group_id=str(group["group_id"]),
            detail_key=str(group["detail_key"]),
        )

        self.assertIsNotNone(detail)
        assert detail is not None
        detailed_group = detail["group"]
        self.assertEqual(detailed_group["collapsed_row_counts"], {"invoice": 49})
        invoice_rows = detailed_group["collapsed_rows"]["invoice"]
        self.assertEqual(len(invoice_rows), 49)
        self.assertEqual(
            {row["source_kind"] for row in invoice_rows},
            {"etc_invoice"},
        )
        self.assertEqual(
            len({row["invoice_no"] for row in invoice_rows}),
            49,
        )
        self.assertNotIn(
            "etc_invoice_summary",
            {row["source_kind"] for row in invoice_rows},
        )

    def test_pending_oa_uses_nested_application_date_for_display_and_search(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.oa_pending_payment_admissions(
                tenant_id, scope_key, oa_id, workflow_status, applicant,
                project_name, project_name_display, amount, source_signature,
                source_payload, raw_payload
            ) values (
                'default', '2026-07', 'oa-pending-with-time', 'in_progress', '胡琦',
                '大理卷烟厂余热综合利用项目', '大理卷烟厂余热综合利用项目', 175,
                'signature:oa-pending-with-time',
                '{"detail_fields":{"申请日期":"2026-07-17 09:08:07"},"apply_type":"日常报销","expense_type":"交通费"}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        pending_row = next(
            row
            for group in initial["unpaired"]["groups"]
            for row in list(group.get("oa_rows") or [])
            if row.get("id") == "oa-pending-with-time"
        )
        self.assertEqual(pending_row["apply_time"], "2026-07-17 09:08:07")
        self.assertEqual(pending_row["application_date"], "2026-07-17")
        self.assertEqual(pending_row["expense_type"], "交通费")

        searched = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="2026-07-17",
        )
        self.assertTrue(
            any(
                row.get("id") == "oa-pending-with-time"
                for group in searched["groups"]
                for row in list(group.get("oa_rows") or [])
            )
        )

    def test_anomaly_state_is_sql_compact_fingerprint_parity_and_keyset_bounded(self) -> None:
        self.connection.statements.clear()
        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        group = next(
            group
            for group in initial["unpaired"]["groups"]
            if group.get("detail_key") == "CASE-DIRECT-1"
        )
        anomaly = dict(group.get("workbench_anomaly") or {})

        self.assertEqual(initial["summary"]["unpaired_exception_count"], 1)
        self.assertEqual(initial["summary"]["paired_exception_count"], 0)
        self.assertEqual(anomaly.get("review_decision"), "pending")
        self.assertTrue(str(anomaly.get("fingerprint") or ""))
        self.assertEqual(
            {str(item.get("code") or "") for item in anomaly.get("items") or []},
            {"oa_invoice_attachment_absent", "oa_bank_equal_invoice_less"},
        )
        candidate_statement = next(
            statement
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "anomaly_counts" in str(statement.get("raw_sql") or "")
        )
        self.assertEqual(candidate_statement["page_rows_with_anomaly_payload"], 0)

        self.connection.statements.clear()
        unpaired = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            page_size=1,
            exception_bucket="unpaired",
        )
        self.assertEqual(unpaired["total"], 1)
        self.assertEqual(
            unpaired["groups"][0]["workbench_anomaly"]["fingerprint"],
            anomaly["fingerprint"],
        )
        self.assertEqual(
            sum(
                statement["operation"] == "fetch_all"
                for statement in self.connection.statements
            ),
            3,
        )
        exception_sql = next(
            str(statement.get("raw_sql") or "")
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "anomaly_states" in str(statement.get("raw_sql") or "")
        )
        self.assertIn("groups.zone = %s", exception_sql)
        self.assertIn("limit %s", exception_sql.lower())
        self.assertIn("relation_amount_classifications", exception_sql)
        self.assertNotIn("expense_component_reach", exception_sql)
        self.assertNotIn("component_anomaly_items", exception_sql)

        PostgresWorkbenchRepository(
            self.raw_connection
        ).set_workbench_anomaly_review_decision(
            fingerprint=str(anomaly["fingerprint"]),
            group_id="case:CASE-DIRECT-1",
            scope_key="2026-07",
            actor_id="test-suite",
            decision="accept_paired",
            note="附件异常与金额异常均已复核",
            detected_classification_codes=[
                str(item["code"]) for item in anomaly["items"]
            ],
            evidence_item_fingerprints=list(anomaly["evidence_item_fingerprints"]),
        )
        accepted = self.repository.get_workbench_initial_page(scope_key="2026-07")
        self.assertEqual(accepted["summary"]["unpaired_exception_count"], 0)
        self.assertEqual(accepted["summary"]["paired_exception_count"], 1)
        self.assertEqual(
            accepted["paired"]["groups"][0]["workbench_anomaly"]["review_decision"],
            "accept_paired",
        )
        paired = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="paired",
            exception_bucket="paired",
        )
        self.assertEqual(paired["total"], 1)
        unpaired_after_review = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
        )
        self.assertFalse(
            any(
                group.get("detail_key") == "CASE-DIRECT-1"
                for group in unpaired_after_review["groups"]
            )
        )

    def test_exception_views_count_unique_relations_and_auto_select_first_amount_code(self) -> None:
        fixtures = [
            {
                "fixture_id": "oa-bank-equal-invoice-more",
                "oa_amount": 100,
                "bank_amount": 100,
                "invoice_amount": 120,
                "has_document_anomaly": True,
            },
            {
                "fixture_id": "oa-bank-equal-invoice-more-2",
                "oa_amount": 100,
                "bank_amount": 100,
                "invoice_amount": 120,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "oa-bank-equal-invoice-less",
                "oa_amount": 100,
                "bank_amount": 100,
                "invoice_amount": 80,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "oa-invoice-equal-bank-more",
                "oa_amount": 100,
                "bank_amount": 120,
                "invoice_amount": 100,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "oa-invoice-equal-bank-less",
                "oa_amount": 100,
                "bank_amount": 80,
                "invoice_amount": 100,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "bank-invoice-equal-oa-less",
                "oa_amount": 80,
                "bank_amount": 100,
                "invoice_amount": 100,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "bank-invoice-equal-oa-more",
                "oa_amount": 120,
                "bank_amount": 100,
                "invoice_amount": 100,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "all-amounts-different",
                "oa_amount": 120,
                "bank_amount": 100,
                "invoice_amount": 80,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "document-only",
                "oa_amount": 50,
                "bank_amount": 50,
                "invoice_amount": 50,
                "has_document_anomaly": True,
            },
        ]
        fixture_json = json.dumps(fixtures, ensure_ascii=False)
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            )
            select
                'source-' || fixture.fixture_id,
                'payment_request',
                '付款申请',
                'oa-facet-' || fixture.fixture_id,
                'active',
                'completed',
                '测试用户',
                '2026-08-01'::date,
                '2026-08-01'::date,
                '异常分类测试',
                fixture.oa_amount,
                'CNY',
                jsonb_build_object(
                    'id', 'oa-facet-' || fixture.fixture_id,
                    'month', '2026-08',
                    'section', 'unpaired',
                    'applicant', '测试用户',
                    'project_name', '异常分类测试',
                    'amount', fixture.oa_amount::text,
                    'workflow_status', 'completed'
                ) || case
                    when fixture.has_document_anomaly then jsonb_build_object(
                        'expense_items',
                        jsonb_build_array(jsonb_build_object(
                            'id', 'oa-facet-' || fixture.fixture_id || ':item:0',
                            'amount', case
                                when fixture.fixture_id = 'document-only'
                                    then (fixture.oa_amount / 2)::text
                                else fixture.oa_amount::text
                            end,
                            'attachment_file_count', '0'
                        )) || case
                            when fixture.fixture_id = 'document-only'
                                then jsonb_build_array(jsonb_build_object(
                                    'id', 'oa-facet-' || fixture.fixture_id || ':item:1',
                                    'amount', (fixture.oa_amount / 2)::text,
                                    'attachment_file_count', '0'
                                ))
                            else '[]'::jsonb
                        end
                    )
                    else '{}'::jsonb
                end,
                '{}'::jsonb
            from jsonb_to_recordset(%s::jsonb) as fixture(
                fixture_id text,
                oa_amount numeric,
                bank_amount numeric,
                invoice_amount numeric,
                has_document_anomaly boolean
            )
            """,
            (fixture_json,),
        )
        self.raw_connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            )
            select
                'bank-facet-' || fixture.fixture_id,
                '6222000011118106',
                '基本户',
                'outflow',
                '异常分类测试供应商',
                fixture.bank_amount,
                -fixture.bank_amount,
                '2026-08-02'::date,
                '2026-08-01'::date,
                '2026-08-02 10:00:00+08'::timestamptz,
                '异常分类测试',
                '{}'::jsonb,
                'active'
            from jsonb_to_recordset(%s::jsonb) as fixture(
                fixture_id text,
                oa_amount numeric,
                bank_amount numeric,
                invoice_amount numeric,
                has_document_anomaly boolean
            )
            """,
            (fixture_json,),
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, workbench_visibility,
                source_links, raw_payload
            )
            select
                'invoice-facet-' || fixture.fixture_id,
                'input',
                'INV-FACET-' || fixture.fixture_id,
                '2026-08-03'::date,
                '2026-08-01'::date,
                fixture.invoice_amount,
                fixture.invoice_amount,
                fixture.invoice_amount,
                'active',
                'visible',
                '[]'::jsonb,
                '{}'::jsonb
            from jsonb_to_recordset(%s::jsonb) as fixture(
                fixture_id text,
                oa_amount numeric,
                bank_amount numeric,
                invoice_amount numeric,
                has_document_anomaly boolean
            )
            """,
            (fixture_json,),
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            )
            select
                'CASE-FACET-' || fixture.fixture_id,
                'manual_confirmed',
                'active',
                1,
                '2026-08-01'::date,
                array[
                    'oa-facet-' || fixture.fixture_id,
                    'bank-facet-' || fixture.fixture_id,
                    'invoice-facet-' || fixture.fixture_id
                ],
                array['oa', 'bank', 'invoice'],
                '{}'::jsonb,
                '{}'::jsonb,
                '{}'::jsonb
            from jsonb_to_recordset(%s::jsonb) as fixture(
                fixture_id text,
                oa_amount numeric,
                bank_amount numeric,
                invoice_amount numeric,
                has_document_anomaly boolean
            )
            """,
            (fixture_json,),
        )

        self.connection.statements.clear()
        amount_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=20,
            exception_bucket="unpaired",
            exception_view="amount",
        )

        self.assertEqual(amount_page["selected_exception_code"], "oa_bank_equal_invoice_more")
        self.assertEqual(amount_page["total"], 2)
        self.assertEqual(amount_page["exception_counts"], {
            "total": 9,
            "amount_total": 8,
            "document_only": 1,
            "by_code": {
                "oa_bank_equal_invoice_more": 2,
                "oa_bank_equal_invoice_less": 1,
                "oa_invoice_equal_bank_more": 1,
                "oa_invoice_equal_bank_less": 1,
                "bank_invoice_equal_oa_less": 1,
                "bank_invoice_equal_oa_more": 1,
                "all_amounts_different": 1,
            },
        })
        self.assertEqual(
            {group["detail_key"] for group in amount_page["groups"]},
            {
                "CASE-FACET-oa-bank-equal-invoice-more",
                "CASE-FACET-oa-bank-equal-invoice-more-2",
            },
        )
        category_sql = [
            statement
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "exception_counts as materialized" in str(statement.get("raw_sql") or "")
        ]
        self.assertEqual(len(category_sql), 1)

        explicit_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=20,
            exception_bucket="unpaired",
            exception_view="amount",
            exception_code="all_amounts_different",
        )
        self.assertEqual(explicit_page["selected_exception_code"], "all_amounts_different")
        self.assertEqual(explicit_page["total"], 1)
        self.assertEqual(
            explicit_page["groups"][0]["detail_key"],
            "CASE-FACET-all-amounts-different",
        )

        document_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=20,
            exception_bucket="unpaired",
            exception_view="document_only",
        )
        self.assertIsNone(document_page["selected_exception_code"])
        self.assertEqual(document_page["total"], 1)
        self.assertEqual(len(document_page["groups"]), 1)
        self.assertEqual(
            document_page["groups"][0]["detail_key"],
            "CASE-FACET-document-only",
        )
        self.assertEqual(
            [
                item["code"]
                for item in document_page["groups"][0]["workbench_anomaly"]["items"]
            ],
            ["oa_invoice_attachment_absent", "oa_invoice_attachment_absent"],
        )
        self.assertEqual(document_page["exception_counts"], amount_page["exception_counts"])

        cursor_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=1,
            exception_bucket="unpaired",
            exception_view="amount",
        )
        self.assertTrue(cursor_page["has_more"])
        self.assertIsNotNone(cursor_page["next_cursor"])
        review_repository = PostgresWorkbenchRepository(self.raw_connection)
        for group in amount_page["groups"]:
            anomaly = group["workbench_anomaly"]
            review_repository.set_workbench_anomaly_review_decision(
                fingerprint=str(anomaly["fingerprint"]),
                group_id=str(group["group_id"]),
                scope_key="2026-08",
                actor_id="test-suite",
                decision="accept_paired",
                note="验证自动分类 cursor 固定分区",
                detected_classification_codes=[
                    str(item["code"]) for item in anomaly["items"]
                ],
                evidence_item_fingerprints=list(anomaly["evidence_item_fingerprints"]),
            )
        continued_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=1,
            cursor=cursor_page["next_cursor"],
            exception_bucket="unpaired",
            exception_view="amount",
        )
        self.assertEqual(
            continued_page["selected_exception_code"],
            "oa_bank_equal_invoice_more",
        )
        self.assertEqual(continued_page["total"], 0)
        self.assertEqual(continued_page["groups"], [])
        self.assertEqual(
            continued_page["exception_counts"]["by_code"]["oa_bank_equal_invoice_less"],
            1,
        )

    def test_shared_invoice_sources_are_counted_once_with_sql_fingerprint_parity(self) -> None:
        oa_payload = {
            "id": "oa-shared-36",
            "month": "2026-07",
            "section": "unpaired",
            "applicant": "樊祖芳",
            "project_name": "快递费",
            "apply_type": "日常报销",
            "amount": "36.00",
            "workflow_status": "completed",
            "expense_items": [
                {
                    "id": "oa-shared-36:item:0",
                    "expense_item_id": "oa-shared-36:item:0",
                    "row_index": "0",
                    "amount": "18.00",
                    "attachment_file_count": "1",
                },
                {
                    "id": "oa-shared-36:item:1",
                    "expense_item_id": "oa-shared-36:item:1",
                    "row_index": "1",
                    "amount": "18.00",
                    "attachment_file_count": "1",
                },
            ],
        }
        source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-shared-36",
                "source_expense_item_id": "oa-shared-36:item:0",
                "source_expense_row_index": "0",
            },
            {
                "source_type": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-shared-36",
                "source_expense_item_id": "oa-shared-36:item:1",
                "source_expense_row_index": "1",
            },
        ]
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            ) values (
                'oa-source-shared-36', '32', '日常报销', 'oa-shared-36',
                'active', 'completed', '樊祖芳', '2026-07-16', '2026-07-01',
                '快递费', 36, 'CNY', %s::jsonb, '{}'::jsonb
            )
            """,
            (json.dumps(oa_payload, ensure_ascii=False),),
        )
        self.raw_connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values (
                'bank-shared-36', '6222000011118108', '基本户', 'outflow',
                '云南顺丰速运有限公司', 36, -36, '2026-07-16', '2026-07-01',
                '2026-07-16 10:00:00+08', '快递费', '{}'::jsonb, 'active'
            )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, workbench_visibility,
                source_links, raw_payload
            ) values (
                'invoice-shared-36', 'input', 'INV-SHARED-36', '2026-07-16', '2026-07-01',
                36, 36, 36, 'active', 'visible', %s::jsonb, '{}'::jsonb
            )
            """,
            (json.dumps(source_links, ensure_ascii=False),),
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-SHARED-36', 'manual_confirmed', 'active', 1, '2026-07-01',
                array['oa-shared-36','bank-shared-36','invoice-shared-36'],
                array['oa','bank','invoice'], '{}'::jsonb,
                '{"requires_oa":true,"requires_invoice":true}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        matched = self.repository.get_workbench_initial_page(scope_key="2026-07")
        matched_group = next(
            group
            for group in matched["paired"]["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        self.assertNotIn("workbench_anomaly", matched_group)
        self.assertEqual(
            matched_group["invoice_rows"][0]["source_expense_item_ids"],
            ["oa-shared-36:item:0", "oa-shared-36:item:1"],
        )

        with self.raw_connection.transaction() as transaction:
            transaction.execute(
                "select set_config('fin_ops.correction_reason', '多对多金额异常测试', true)"
            )
            transaction.execute("select set_config('fin_ops.actor_id', 'test-suite', true)")
            transaction.execute(
                """
                update app.invoices
                set amount = 35.99, signed_amount = 35.99, total_with_tax = 35.99
                where legacy_mongo_id = 'invoice-shared-36'
                """
            )
        mismatched = self.repository.get_workbench_initial_page(scope_key="2026-07")
        mismatched_group = next(
            group
            for group in mismatched["unpaired"]["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        anomaly = mismatched_group["workbench_anomaly"]
        self.assertEqual(anomaly["items"][0]["code"], "oa_bank_equal_invoice_less")
        self.assertEqual(anomaly["items"][0]["display_scope"], "row")
        self.assertEqual(anomaly["items"][0]["display_pane"], "invoice")
        self.assertEqual(anomaly["items"][0]["display_row_id"], "invoice-shared-36")
        self.assertEqual(anomaly["items"][0]["source_expense_item_ids"], [
            "oa-shared-36:item:0",
            "oa-shared-36:item:1",
        ])
        active = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            exception_bucket="unpaired",
        )
        active_group = next(
            group for group in active["groups"] if group.get("detail_key") == "CASE-SHARED-36"
        )
        self.assertEqual(
            active_group["workbench_anomaly"]["fingerprint"],
            anomaly["fingerprint"],
        )

        PostgresWorkbenchRepository(
            self.raw_connection
        ).set_workbench_anomaly_review_decision(
            fingerprint=str(anomaly["fingerprint"]),
            group_id=str(mismatched_group["group_id"]),
            scope_key="2026-07",
            actor_id="test-suite",
            decision="accept_paired",
            note="production-shape regression",
            detected_classification_codes=[
                str(item["code"]) for item in anomaly["items"]
            ],
            evidence_item_fingerprints=list(anomaly["evidence_item_fingerprints"]),
        )

        accepted = self.repository.get_workbench_initial_page(scope_key="2026-07")
        accepted_group = next(
            group
            for group in accepted["paired"]["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        self.assertEqual(
            accepted_group["workbench_anomaly"]["review_decision"],
            "accept_paired",
        )
        summary_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="paired",
            exception_bucket="paired",
            detail_level="summary",
        )
        full_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="paired",
            exception_bucket="paired",
            detail_level="full",
        )
        summary_group = next(
            group
            for group in summary_page["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        full_group = next(
            group
            for group in full_page["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        detail = self.repository.get_workbench_group_detail(
            scope_key="2026-07",
            zone="paired",
            group_id=str(accepted_group["group_id"]),
            detail_key=str(accepted_group["detail_key"]),
        )
        self.assertEqual(summary_group["zone"], "paired")
        self.assertEqual(full_group["zone"], "paired")
        self.assertEqual(detail["group"]["zone"], "paired")

        self.raw_connection.execute(
            """
            update app.workbench_pair_relations
            set updated_at = now() + interval '1 second'
            where case_id = 'CASE-SHARED-36'
            """
        )
        stale = self.repository.get_workbench_initial_page(scope_key="2026-07")
        stale_group = next(
            group
            for group in stale["unpaired"]["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        self.assertNotEqual(
            stale_group["workbench_anomaly"].get("review_decision"),
            "accept_paired",
        )

    def test_manual_expense_item_invoices_satisfy_missing_attachment_evidence(self) -> None:
        oa_payload = {
            "id": "oa-manual-2308",
            "month": "2026-07",
            "section": "unpaired",
            "applicant": "刘涵静",
            "project_name": "2025年1-12月电话费",
            "apply_type": "日常报销",
            "amount": "2308.02",
            "workflow_status": "completed",
            "expense_items": [
                {
                    "id": "oa-manual-2308:item:0",
                    "expense_item_id": "oa-manual-2308:item:0",
                    "row_index": "0",
                    "amount": "2308.02",
                    "attachment_file_count": "0",
                }
            ],
        }
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            ) values (
                'oa-source-manual-2308', '32', '日常报销', 'oa-manual-2308',
                'active', 'completed', '刘涵静', '2026-07-20', '2026-07-01',
                '2025年1-12月电话费', 2308.02, 'CNY', %s::jsonb, '{}'::jsonb
            )
            """,
            (json.dumps(oa_payload, ensure_ascii=False),),
        )
        self.raw_connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values (
                'bank-manual-2038', '6222000011118108', '基本户', 'outflow',
                '中国电信股份有限公司昆明分公司', 2038.02, -2038.02,
                '2026-07-20', '2026-07-01', '2026-07-20 10:00:00+08',
                '2025年1-12月电话费', '{}'::jsonb, 'active'
            )
            """
        )
        source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-manual-2308",
                "source_expense_item_id": "oa-manual-2308:item:9:historical",
                "source_expense_row_index": "9",
                "source_attachment_key": "historical-attachment.pdf",
            },
            {
                "source_type": "oa_expense_item_invoice",
                "entry_method": "manual_invoice_import",
                "derived_from_oa_id": "oa-manual-2308",
                "source_expense_item_id": "oa-manual-2308:item:0",
                "source_expense_row_index": "0",
                "source_relation_case_id": "CASE-MANUAL-2308",
            }
        ]
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, workbench_visibility,
                source_links, raw_payload
            ) values
                (
                    'invoice-manual-859', 'input', 'INV-MANUAL-859',
                    '2026-07-18', '2026-07-01', 859.57, 859.57, 859.57,
                    'active', 'visible', %s::jsonb, '{}'::jsonb
                ),
                (
                    'invoice-manual-1178', 'input', 'INV-MANUAL-1178',
                    '2026-07-18', '2026-07-01', 1178.45, 1178.45, 1178.45,
                    'active', 'visible', %s::jsonb, '{}'::jsonb
                )
            """,
            (
                json.dumps(source_links, ensure_ascii=False),
                json.dumps(source_links, ensure_ascii=False),
            ),
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-MANUAL-2308', 'manual_confirmed', 'active', 1, '2026-07-01',
                array[
                    'oa-manual-2308', 'bank-manual-2038',
                    'invoice-manual-859', 'invoice-manual-1178'
                ],
                array['oa','bank','invoice','invoice'], '{}'::jsonb,
                '{"requires_oa":true,"requires_invoice":true}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="INV-MANUAL-859",
            detail_level="summary",
        )
        group = next(
            row for row in page["groups"] if row.get("detail_key") == "CASE-MANUAL-2308"
        )
        self.assertEqual(len(group["invoice_rows"]), 2)
        for invoice_row in group["invoice_rows"]:
            self.assertEqual(
                invoice_row["source_expense_item_ids"],
                ["oa-manual-2308:item:0"],
            )

        expense_item = group["oa_rows"][0]["expense_items"][0]
        self.assertEqual(str(expense_item["attachment_file_count"]), "0")
        anomaly_codes = {
            item["code"] for item in group["workbench_anomaly"]["items"]
        }
        self.assertEqual(anomaly_codes, {"bank_invoice_equal_oa_more"})
        self.assertNotIn("oa_invoice_attachment_absent", anomaly_codes)
        self.assertNotIn("oa_invoice_attachment_unparsed", anomaly_codes)

    def test_summary_hydration_does_not_transport_large_unused_source_payloads(self) -> None:
        sentinel = "summary-hot-path-unused-" + ("x" * 200_000)
        self.raw_connection.execute(
            """
            update app.oa_applications
            set raw_payload = jsonb_build_object('unused_blob', %s::text),
                normalized_payload = normalized_payload ||
                    jsonb_build_object('unused_blob', %s::text)
            where row_id = 'oa-direct-1'
            """,
            (sentinel, sentinel),
        )
        self.raw_connection.execute(
            """
            update app.bank_transactions
            set raw_payload = jsonb_build_object('unused_blob', %s::text)
            where legacy_mongo_id = 'bank-direct-1'
            """,
            (sentinel,),
        )
        self.raw_connection.execute(
            """
            update app.invoices
            set raw_payload = jsonb_build_object('unused_blob', %s::text)
            where legacy_mongo_id = 'same-text-id'
            """,
            (sentinel,),
        )

        self.connection.statements.clear()
        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        encoded = json.dumps(initial, ensure_ascii=False, default=str)

        self.assertNotIn("summary-hot-path-unused", encoded)
        self.assertLess(len(encoded.encode("utf-8")), 80_000)
        self.assertEqual(
            sum(
                statement["operation"] == "fetch_all"
                for statement in self.connection.statements
            ),
            3,
        )

    def test_page_etc_hydration_is_one_statement_and_matches_legacy_dto(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.etc_submission_batches(
                submission_batch_id, status, scope_month, invoice_ids, raw_payload
            ) values
                (
                    'legacy-only-submission', 'submitted', '2026-07-01',
                    array['legacy-only-invoice'],
                    '{"normalized_payload":{"etc_batch_id":"legacy-only"}}'::jsonb
                ),
                (
                    'priority-submission', 'submitted', '2026-07-01',
                    array['priority-submitted-invoice'],
                    '{"normalized_payload":{"etc_batch_id":"priority-batch"}}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values
                (
                    'legacy-only-invoice', 'input', 'LEGACY-ONLY', '2026-07-27',
                    '2026-07-01', 33, 33, 33, 'active',
                    'hidden_after_etc_submission', '[]'::jsonb,
                    '{"normalized_payload":{"etc_submission_batch_id":"legacy-only-submission"}}'::jsonb
                ),
                (
                    'priority-linked-invoice', 'input', 'PRIORITY-LINK', '2026-07-28',
                    '2026-07-01', 11, 11, 11, 'active', 'visible', '[]'::jsonb,
                    '{}'::jsonb
                ),
                (
                    'priority-submitted-invoice', 'input', 'PRIORITY-SUBMITTED',
                    '2026-07-28', '2026-07-01', 33, 33, 33, 'active',
                    'hidden_after_etc_submission', '[]'::jsonb,
                    '{"normalized_payload":{"etc_submission_batch_id":"priority-submission"}}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values (
                'priority-business', 'oa_submitted', '2026-07-01', 2, 33,
                '{"normalized_payload":{"external_etc_batch_id":"priority-batch"}}'::jsonb
            )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            ) values
                (
                    'priority-business-linked', 'priority-business', 'submitted',
                    'PRIORITY-LINK', '2026-07-28', '业务批次供应商', 10, 1, 11,
                    '{}'::jsonb
                ),
                (
                    'priority-business-invoice', 'priority-business', 'submitted',
                    'PRIORITY-BUSINESS', '2026-07-28', '业务批次供应商', 20, 2, 22,
                    '{}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_batch_invoice_links(
                business_batch_id, invoice_id, identity_key, link_status,
                link_source, confidence, raw_payload
            )
            select
                'priority-business', invoices.id, 'priority-link', 'active',
                'test', 'strict', '{}'::jsonb
            from app.invoices invoices
            where invoices.legacy_mongo_id = 'priority-linked-invoice'
            """
        )
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount,
                currency, normalized_payload, raw_payload
            ) values (
                'oa-source-priority', 'payment_request', '付款申请', 'oa-priority',
                'active', 'completed', '测试用户', '2026-07-28', '2026-07-01',
                'ETC部分桥接测试', 33, 'CNY',
                '{"id":"oa-priority","month":"2026-07","amount":"33","workflow_status":"completed"}'::jsonb,
                '{}'::jsonb
            );
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values (
                'bank-priority', '6222000011118106', '基本户', 'outflow',
                'ETC部分桥接测试', 33, -33, '2026-07-28', '2026-07-01',
                '2026-07-28 10:00:00+08', 'ETC报销', '{}'::jsonb, 'active'
            );
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-ETC-PARTIAL-BRIDGE', 'manual_confirmed', 'active', 1,
                '2026-07-01',
                array['oa-priority','bank-priority','etc-summary-priority-batch'],
                array['oa','bank','invoice'], '{}'::jsonb,
                '{"external_etc_batch_id":"priority-batch"}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        row_ids_by_external_id = {
            "etc_202607_unlinked": "etc-summary-etc_202607_unlinked",
            "ETC 空格/中文": "etc-summary-ETC-",
            "legacy-only": "etc-summary-legacy-only",
            "priority-batch": "etc-summary-priority-batch",
        }
        external_ids_by_row_id = {row_id: external_id for external_id, row_id in row_ids_by_external_id.items()}
        builder = WorkbenchCanonicalRowsBuilder(connection=self.connection)

        self.connection.statements.clear()
        page_rows = builder._etc_invoice_summary_rows_by_ids(
            set(external_ids_by_row_id),
            external_ids_by_row_id=external_ids_by_row_id,
        )
        page_statement_count = len(self.connection.statements)

        self.connection.statements.clear()
        legacy_rows = builder._etc_invoice_summary_rows(
            external_batch_ids=set(row_ids_by_external_id),
        )
        legacy_statement_count = len(self.connection.statements)
        expected_rows = {
            external_id: {
                **row,
                "id": row_ids_by_external_id[external_id],
            }
            for external_id, row in legacy_rows.items()
        }

        actual_rows = {str(row["etc_batch_id"]): row for row in page_rows}
        self.assertEqual(set(actual_rows), set(expected_rows))
        for external_batch_id in sorted(expected_rows):
            self.assertEqual(
                actual_rows[external_batch_id],
                expected_rows[external_batch_id],
                external_batch_id,
            )
        self.assertEqual(page_statement_count, 1)
        self.assertEqual(legacy_statement_count, 5)
        self.assertEqual(expected_rows["priority-batch"]["amount"], "33.00")
        self.assertEqual(expected_rows["priority-batch"]["etc_invoice_count"], 2)
        self.assertEqual(
            {
                row["invoice_no"]
                for row in expected_rows["priority-batch"]["etc_invoice_detail_rows"]
            },
            {"PRIORITY-LINK", "PRIORITY-BUSINESS"},
        )
        self.assertNotIn(
            "PRIORITY-SUBMITTED",
            {
                row["invoice_no"]
                for row in expected_rows["priority-batch"]["etc_invoice_detail_rows"]
            },
        )
        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        priority_group = next(
            group
            for zone in ("paired", "unpaired")
            for group in initial[zone]["groups"]
            if group.get("detail_key") == "CASE-ETC-PARTIAL-BRIDGE"
        )
        self.assertEqual(priority_group["invoice_rows"][0]["amount"], "33.00")
        self.assertEqual(priority_group["collapsed_row_counts"], {"invoice": 2})
        self.assertEqual(
            [
                (row["source_kind"], row["invoice_no"])
                for row in priority_group["collapsed_rows"]["invoice"]
            ],
            [("etc_invoice", "PRIORITY-BUSINESS")],
        )
        anomaly_items = list(
            (priority_group.get("workbench_anomaly") or {}).get("items") or []
        )
        self.assertFalse(
            {
                "oa_bank_equal_invoice_more",
                "oa_bank_equal_invoice_less",
                "oa_invoice_equal_bank_more",
                "oa_invoice_equal_bank_less",
                "bank_invoice_equal_oa_less",
                "bank_invoice_equal_oa_more",
                "all_amounts_different",
            }
            & {item.get("code") for item in anomaly_items},
        )

    def test_typed_selection_accepts_cross_pane_same_text_id_and_untyped_fails_closed(self) -> None:
        selection = self.selection_repository.get_workbench_relation_preview_selection(
            scope_key="2026-07",
            row_ids=["same-text-id", "same-text-id"],
            row_types=["bank", "invoice"],
        )

        self.assertEqual(selection["selected_row_types"], ["bank", "invoice"])
        self.assertEqual(
            [row["type"] for row in selection["selected_rows"]],
            ["bank", "invoice"],
        )
        with self.assertRaisesRegex(Exception, "内容不一致"):
            self.selection_repository.get_workbench_relation_preview_selection(
                scope_key="2026-07",
                row_ids=["same-text-id"],
            )

    def test_preview_selection_queries_only_requested_typed_sources_and_owned_relation(self) -> None:
        self.connection.statements.clear()
        selection = self.selection_repository.get_workbench_relation_preview_selection(
            scope_key="2026-07",
            row_ids=["oa-direct-1"],
            row_types=["oa"],
        )

        self.assertEqual(selection["selected_row_ids"], ["oa-direct-1"])
        self.assertEqual(
            {(row["type"], row["id"]) for row in selection["context_rows"]},
            {
                ("bank", "bank-direct-1"),
                ("invoice", "etc-summary-etc_202607_linked"),
                ("invoice", "etc-invoice-direct-2"),
            },
        )
        fetches = [
            statement
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
        ]
        source_sql = str(fetches[0].get("raw_sql") or "").lower()
        descriptor_sql = str(fetches[1].get("raw_sql") or "").lower()
        self.assertIn("oa.row_id = requested.row_id", source_sql)
        self.assertNotIn("canonical_groups", source_sql)
        self.assertNotIn("canonical_groups", descriptor_sql)
        self.assertIn("join selected_sources source", descriptor_sql)

    def test_non_prefixed_oa_id_hydrates_initial_detail_and_preview(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount,
                currency, normalized_payload, raw_payload
            ) values (
                'oa-source-object-id', 'payment_request', '付款申请',
                '64ef01a2b3c4d5e6f7890123', 'active', 'completed',
                '李四', '2026-07-26', '2026-07-01', '对象ID项目', 20, 'CNY',
                '{"id":"64ef01a2b3c4d5e6f7890123","month":"2026-07","applicant":"李四","project_name":"对象ID项目","amount":"20","workflow_status":"completed"}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        oa_group = next(
            group
            for group in initial["unpaired"]["groups"]
            if any(
                row.get("id") == "64ef01a2b3c4d5e6f7890123"
                for row in list(group.get("oa_rows") or [])
            )
        )
        detail = self.repository.get_workbench_group_detail(
            scope_key="2026-07",
            zone="unpaired",
            group_id=str(oa_group["group_id"]),
            detail_key=str(oa_group["detail_key"]),
        )
        selection = self.selection_repository.get_workbench_relation_preview_selection(
            scope_key="2026-07",
            row_ids=["64ef01a2b3c4d5e6f7890123"],
            row_types=["oa"],
        )

        self.assertEqual(detail["group"]["oa_rows"][0]["id"], "64ef01a2b3c4d5e6f7890123")
        self.assertEqual(selection["selected_rows"][0]["id"], "64ef01a2b3c4d5e6f7890123")

    def test_etc_legacy_identity_collision_fails_closed(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values (
                'etc_202607_collision', 'oa_submitted', '2026-07-01', 1,
                11, '{"normalized_payload":{"external_etc_batch_id":"ETC/中文"}}'::jsonb
            )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            ) values (
                'etc-invoice-collision', 'etc_202607_collision', 'submitted',
                'ETC-INV-COLLISION', '2026-07-26', 'ETC碰撞供应商', 10, 1, 11,
                '{}'::jsonb
            )
            """
        )

        with self.assertRaises(WorkbenchDirectQueryUnavailable):
            self.repository.get_workbench_groups_page(
                scope_key="2026-07",
                zone="unpaired",
            )

    def test_invalid_relation_member_arrays_fail_closed_in_postgres(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-INVALID-TYPED-MEMBERS', 'manual_confirmed', 'active', 1,
                '2026-07-01', array['same-text-id'], array['unsupported'],
                '{}'::jsonb, '{}'::jsonb, '{}'::jsonb
            )
            """
        )

        with self.assertRaises(WorkbenchDirectQueryUnavailable):
            self.repository.get_workbench_groups_page(
                scope_key="2026-07",
                zone="unpaired",
            )

    def test_invoice_identity_arbitration_uses_global_active_owner(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values
                (
                    'invoice-july-duplicate', 'input', 'GLOBAL-DUPLICATE', 'GLOBAL-DUPLICATE',
                    '2026-07-25', '2026-07-01', 12, 12, 12, 'active',
                    'visible', '[]'::jsonb, '{}'::jsonb
                ),
                (
                    'invoice-august-owner', 'input', 'GLOBAL-DUPLICATE', 'GLOBAL-DUPLICATE',
                    '2026-08-01', '2026-08-01', 12, 12, 12, 'active',
                    'visible', '[]'::jsonb, '{}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-GLOBAL-INVOICE-OWNER', 'manual_confirmed', 'active', 1,
                '2026-08-01', array['invoice-august-owner'], array['invoice'],
                '{}'::jsonb,
                '{"requires_oa":false,"requires_invoice":false}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="GLOBAL-DUPLICATE",
        )

        self.assertEqual(page["total"], 0, page)
        self.assertEqual(page["groups"], [])

        with self.assertRaisesRegex(ValueError, "missing"):
            self.selection_repository._resolve_source_descriptors(
                scope_key="2026-07",
                row_ids=["invoice-july-duplicate"],
                row_types=["invoice"],
            )
        owner = self.selection_repository._resolve_source_descriptors(
            scope_key="2026-08",
            row_ids=["invoice-august-owner"],
            row_types=["invoice"],
        )
        self.assertEqual(
            [(row["row_type"], row["row_id"]) for row in owner],
            [("invoice", "invoice-august-owner")],
        )

    def test_statement_count_is_page_size_independent_and_emits_timings(self) -> None:
        statement_counts: list[int] = []
        for page_size in (50, 100):
            self.connection.statements.clear()
            self.repository.get_workbench_groups_page(
                scope_key="2026-07",
                zone="unpaired",
                page_size=page_size,
            )
            statement_counts.append(
                sum(
                    statement["operation"] == "fetch_all"
                    for statement in self.connection.statements
                )
            )
            self.assertTrue(
                all(float(statement["duration_ms"]) >= 0 for statement in self.connection.statements)
            )
        self.assertEqual(statement_counts[0], statement_counts[1])
        self.assertEqual(statement_counts, [3, 3])
        if os.environ.get("FIN_OPS_PRINT_QUERY_TIMINGS") == "1":
            print(json.dumps(self.connection.statements, ensure_ascii=False, indent=2))

    def test_direct_page_snapshot_uses_hash_merge_plan_for_canonical_spine(self) -> None:
        self.connection.statements.clear()

        self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            page_size=50,
        )

        executed_sql = [
            str(statement.get("raw_sql") or "").strip().lower()
            for statement in self.connection.statements
            if statement["operation"] == "execute"
        ]
        self.assertIn("set local jit = off", executed_sql)
        self.assertIn("set local enable_nestloop = off", executed_sql)
        self.assertIn("set local max_parallel_workers_per_gather = 0", executed_sql)


if __name__ == "__main__":
    unittest.main()
