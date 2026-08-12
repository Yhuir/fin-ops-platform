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
        self.raw_connection.execute(
            """
            insert into app.app_settings(settings_key, settings_payload, raw_payload)
            values (
                'app_settings',
                '{
                    "allowed_usernames":["YNSYLP005"],
                    "readonly_export_usernames":[],
                    "admin_usernames":["YNSYLP005"],
                    "full_access_usernames":[],
                    "access_control_version":1
                }'::jsonb,
                '{"normalized_payload":{
                    "allowed_usernames":["YNSYLP005"],
                    "readonly_export_usernames":[],
                    "admin_usernames":["YNSYLP005"],
                    "full_access_usernames":[],
                    "access_control_version":1
                }}'::jsonb
            )
            on conflict (settings_key) do nothing
            """
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
                '{"id":"oa-direct-1","month":"2026-07","section":"unpaired","applicant":"张三","project_name":"直接查询项目","amount":"100","workflow_status":"completed"}'::jsonb,
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
        self.assertEqual(initial["summary"]["paired_count"], 1)
        self.assertEqual(initial["summary"]["unpaired_count"], 4)
        self.assertEqual(initial["paired"]["total"], 1)
        self.assertEqual(initial["unpaired"]["total"], 4)
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
            initial["paired"]["groups"][0]["invoice_rows"][0]["source_kind"],
            "etc_invoice_summary",
        )
        initial_statement = next(
            statement
            for statement in self.connection.statements
            if "with requested_scope" in str(statement.get("sql") or "")
        )
        self.assertEqual(initial_statement["operation"], "fetch_all")
        self.assertEqual(initial_statement["metadata_row_count"], 1)
        self.assertEqual(initial_statement["page_rows_with_anomaly_payload"], 0)
        self.assertNotIn("read_model_version", initial)
        self.assertNotIn("generation_id", initial)
        self.assertFalse(
            any("read_model.workbench_" in str(statement["sql"]) for statement in self.connection.statements)
        )

        self.connection.statements.clear()
        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="云南腾安%",
        )
        self.assertEqual(page["total"], 0, "percent must be treated as a literal")
        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="paired",
            search="云南腾安科技有限公司",
        )
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["groups"][0]["detail_key"], "CASE-DIRECT-1")

    def test_anomaly_state_is_sql_compact_fingerprint_parity_and_keyset_bounded(self) -> None:
        self.connection.statements.clear()
        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        group = initial["paired"]["groups"][0]
        anomaly = dict(group.get("oa_invoice_anomaly") or {})

        self.assertEqual(initial["summary"]["exception_count"], 1)
        self.assertEqual(initial["summary"]["ignored_exception_count"], 0)
        self.assertEqual(anomaly.get("state"), "active")
        self.assertTrue(str(anomaly.get("fingerprint") or ""))
        candidate_statement = next(
            statement
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "anomaly_counts" in str(statement.get("raw_sql") or "")
        )
        self.assertEqual(candidate_statement["page_rows_with_anomaly_payload"], 0)

        self.connection.statements.clear()
        active = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="paired",
            page_size=1,
            exception_bucket="active",
        )
        self.assertEqual(active["total"], 1)
        self.assertEqual(
            active["groups"][0]["oa_invoice_anomaly"]["fingerprint"],
            anomaly["fingerprint"],
        )
        self.assertEqual(
            sum(
                statement["operation"] == "fetch_all"
                for statement in self.connection.statements
            ),
            2,
        )
        exception_sql = next(
            str(statement.get("raw_sql") or "")
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "anomaly_states" in str(statement.get("raw_sql") or "")
        )
        self.assertIn("anomaly.state = %s", exception_sql)
        self.assertIn("limit %s", exception_sql.lower())

        self.raw_connection.execute(
            """
            insert into app.workbench_exception_cases(
                case_id, status, version, business_line, scenario, scope_month,
                row_ids, candidate_ids, raw_payload
            ) values (
                'amount-mismatch-sql-parity', 'ignored', 1,
                'reconciliation_workbench', 'oa_invoice_amount_mismatch',
                '2026-07-01', array[]::text[], array[]::text[],
                jsonb_build_object('normalized_payload', jsonb_build_object(
                    'group_id', 'case:CASE-DIRECT-1',
                    'fingerprint', %s::text
                ))
            )
            """,
            (str(anomaly["fingerprint"]),),
        )
        ignored = self.repository.get_workbench_initial_page(scope_key="2026-07")
        self.assertEqual(ignored["summary"]["exception_count"], 0)
        self.assertEqual(ignored["summary"]["ignored_exception_count"], 1)
        self.assertEqual(
            ignored["paired"]["groups"][0]["oa_invoice_anomaly"]["state"],
            "ignored",
        )
        processed = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="paired",
            exception_bucket="processed",
        )
        self.assertEqual(processed["total"], 1)

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
            2,
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
                'priority-business', 'oa_submitted', '2026-07-01', 1, 22,
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
            ) values (
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

        self.assertEqual(
            {str(row["etc_batch_id"]): row for row in page_rows},
            expected_rows,
        )
        self.assertEqual(page_statement_count, 1)
        self.assertEqual(legacy_statement_count, 5)
        self.assertEqual(expected_rows["priority-batch"]["amount"], "11.00")
        self.assertEqual(
            expected_rows["priority-batch"]["etc_invoice_detail_rows"][0]["invoice_no"],
            "PRIORITY-LINK",
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

    def test_typed_overrides_persist_cross_pane_collision_and_plain_get_sees_write(self) -> None:
        override_service = WorkbenchOverrideService()
        bank = {
            "id": "same-text-id",
            "type": "bank",
            "month": "2026-07",
            "invoice_relation": {
                "code": "pending_invoice_match",
                "label": "待关联发票",
                "tone": "warn",
            },
        }
        invoice = {
            "id": "same-text-id",
            "type": "invoice",
            "month": "2026-07",
            "invoice_bank_relation": {
                "code": "pending_collection",
                "label": "待匹配流水",
                "tone": "warn",
            },
        }
        override_service.update_bank_exception(
            row=bank,
            relation_code="bank_fee",
            relation_label="银行手续费",
            exception_case_id="WEX-BANK-SAME-ID",
        )
        override_service.ignore_row(
            row=invoice,
            exception_case_id="WEX-INVOICE-SAME-ID",
        )
        persistence = PostgresWorkbenchRepository(self.raw_connection)

        persistence.save_workbench_overrides(
            override_service.snapshot(),
            changed_row_ids={"same-text-id"},
        )

        persisted = self.raw_connection.fetch_all(
            """
            select row_type, row_id, legacy_mongo_id, override_payload
            from app.workbench_row_overrides
            where row_id = 'same-text-id'
            order by row_type
            """
        )
        self.assertEqual(
            [(row["row_type"], row["row_id"]) for row in persisted],
            [("bank", "same-text-id"), ("invoice", "same-text-id")],
        )
        self.assertEqual(len({row["legacy_mongo_id"] for row in persisted}), 2)
        reloaded = WorkbenchOverrideService.from_snapshot(
            persistence.load_workbench_overrides()
        )
        self.assertEqual(
            reloaded.apply_to_row(bank)["exception_case_id"],
            "WEX-BANK-SAME-ID",
        )
        self.assertTrue(reloaded.apply_to_row(invoice)["ignored"])
        ignored_rows = self.selection_repository.list_workbench_ignored_rows(
            scope_key="2026-07"
        )
        self.assertEqual(
            [(row["type"], row["id"]) for row in ignored_rows],
            [("invoice", "same-text-id")],
        )

        ignored_initial = self.repository.get_workbench_initial_page(
            scope_key="2026-07"
        )
        ignored_identities = {
            (row_type, str(row.get("id") or ""))
            for zone in ("paired", "unpaired")
            for group in list(ignored_initial[zone].get("groups") or [])
            for row_type, field_name in (
                ("oa", "oa_rows"),
                ("bank", "bank_rows"),
                ("invoice", "invoice_rows"),
            )
            for row in list(group.get(field_name) or [])
        }
        self.assertIn(("bank", "same-text-id"), ignored_identities)
        self.assertNotIn(("invoice", "same-text-id"), ignored_identities)

        override_service.unignore_row(row=invoice)
        persistence.save_workbench_overrides(
            override_service.snapshot(),
            changed_row_ids={"same-text-id"},
        )
        visible_initial = self.repository.get_workbench_initial_page(
            scope_key="2026-07"
        )
        visible_identities = {
            (row_type, str(row.get("id") or ""))
            for zone in ("paired", "unpaired")
            for group in list(visible_initial[zone].get("groups") or [])
            for row_type, field_name in (
                ("oa", "oa_rows"),
                ("bank", "bank_rows"),
                ("invoice", "invoice_rows"),
            )
            for row in list(group.get(field_name) or [])
        }
        self.assertIn(("bank", "same-text-id"), visible_identities)
        self.assertIn(("invoice", "same-text-id"), visible_identities)

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
        self.assertEqual(statement_counts, [2, 2])
        if os.environ.get("FIN_OPS_PRINT_QUERY_TIMINGS") == "1":
            print(json.dumps(self.connection.statements, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    unittest.main()
