from __future__ import annotations

from pathlib import Path
import io
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.services.page_audit_registry import PAGE_AUDIT_REGISTRY, page_audit_registration
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.audit_report import AuditSnapshot
from fin_ops_platform.services.postgres_repositories.cost_statistics_page_audit import (
    COST_STATISTICS_AUDIT_QUERY_BUDGET,
    audit_cost_statistics_page,
)
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
)
from tests.test_audit_page_business_read_model_tool import FakeConnection
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)
from fin_ops_platform.tools import audit_page_business_read_model as audit_cli


ROOT = Path(__file__).resolve().parents[1]
SHARED_PAGE_AUDIT_PATH = (
    ROOT
    / "backend"
    / "src"
    / "fin_ops_platform"
    / "services"
    / "postgres_repositories"
    / "page_business_audit.py"
)
COST_PAGE_AUDIT_PATH = (
    ROOT
    / "backend"
    / "src"
    / "fin_ops_platform"
    / "services"
    / "postgres_repositories"
    / "cost_statistics_page_audit.py"
)


class CostAuditFakeConnection(FakeConnection):
    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        row = super().fetch_one(sql, params)
        if "dirty_scope_issues" in sql:
            dirty_rows = [dict(item) for item in self.rows_by_check.get("dirty_scope", [])]
            outbox_rows = [dict(item) for item in self.rows_by_check.get("outbox_backlog", [])]
            row.update(
                {
                    "dirty_scope_count": len(dirty_rows),
                    "outbox_backlog_count": len(outbox_rows),
                    "dirty_scope_issues": dirty_rows,
                    "outbox_backlog_issues": outbox_rows,
                }
            )
        return row


class ActiveRelationCostAuditFakeConnection(CostAuditFakeConnection):
    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        if (
            "from app.workbench_pair_relations" in sql
            and "case_id," in sql
            and "relation_mode," in sql
            and "/* check:" not in sql
        ):
            self.fetch_all_calls.append((sql, params))
            return [
                {
                    "case_id": "cost-audit-query-budget",
                    "relation_mode": "manual",
                    "status": "active",
                    "row_ids": [],
                    "row_types": [],
                    "month_scope": "2026-06",
                    "amount_check": {},
                    "special_metadata": {},
                    "raw_payload": {},
                }
            ]
        return super().fetch_all(sql, params)


class CostStatisticsPageAuditTests(unittest.TestCase):
    def test_clean_audit_preserves_contract_and_active_relation_query_budget(self) -> None:
        connection = ActiveRelationCostAuditFakeConnection()

        report = audit_cost_statistics_page(connection)

        self.assertEqual(report["domain_key"], "cost_statistics")
        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertEqual(
            [timing["proof"] for timing in report["proof_timings"]],
            [
                "queue_readiness",
                "exact_set",
                "source_version_parent",
                "business_values",
                "dependency_workbench",
                "dependency_bank_details",
            ],
        )
        self.assertTrue(
            all(
                isinstance(timing["duration_ms"], float)
                and timing["duration_ms"] >= 0
                and timing["issue_count"] == 0
                for timing in report["proof_timings"]
            )
        )
        self.assertEqual(
            len(connection.fetch_one_calls) + len(connection.fetch_all_calls),
            COST_STATISTICS_AUDIT_QUERY_BUDGET,
        )
        self.assertEqual(COST_STATISTICS_AUDIT_QUERY_BUDGET, 24)
        relation_queries = [
            sql for sql, _params in connection.fetch_all_calls if "/* check: relation_edge_equality */" in sql
        ]
        self.assertEqual(len(relation_queries), 1)
        self.assertFalse(
            any(
                "from read_model.workbench_generations" in sql
                and "build_metadata" in sql
                and "/* check:" not in sql
                for sql, _params in connection.fetch_all_calls
            )
        )
        self.assertEqual(connection.executed, [])

    def test_exact_set_proofs_use_one_query_and_preserve_each_issue_contract(self) -> None:
        issue_rows = [
            {
                "issue_code": "cost_statistics_scope_row_count_mismatch",
                "subject_id": "",
                "scope_key": "active:2026-06",
                "details": {"scope_row_count": 3, "actual_row_count": 2},
            },
            {
                "issue_code": "cost_statistics_missing_read_model_scope",
                "subject_id": "",
                "scope_key": "all:2026-06",
                "details": {"source_count": 1},
            },
            {
                "issue_code": "cost_statistics_duplicate_read_model_identity",
                "subject_id": "active:2026-06:row-1",
                "scope_key": "active:2026-06",
                "details": {"row_count": 2},
            },
            {
                "issue_code": "cost_statistics_canonical_expected_set_mismatch",
                "subject_id": "bank-1",
                "scope_key": "2026-06",
                "details": {
                    "mismatch_kind": "bank_detail_cost_projection_mismatch",
                    "expected_count": 1,
                    "projected_count": 0,
                    "expected_amount": "10",
                    "projected_amount": None,
                    "expected_fields": None,
                    "projected_fields": None,
                },
            },
        ]
        connection = CostAuditFakeConnection(
            rows_by_check={"cost_exact_set_proofs": issue_rows}
        )

        report = audit_cost_statistics_page(connection)

        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {row["issue_code"]: 1 for row in issue_rows},
        )
        self.assertEqual(
            {issue["code"]: issue["details"] for issue in report["issues"]},
            {row["issue_code"]: row["details"] for row in issue_rows},
        )
        proof_calls = [
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "/* check: cost_exact_set_proofs */" in sql
        ]
        self.assertEqual(len(proof_calls), 1)
        proof_sql, proof_params = proof_calls[0]
        for marker in (
            "/* check: scope_row_count_mismatch */",
            "/* check: missing_read_model_scope */",
            "/* check: duplicate_read_model_identity */",
            "/* check: canonical_expected_set */",
        ):
            self.assertEqual(proof_sql.count(marker), 1)
        self.assertEqual(proof_sql.count("limit %s"), 4)
        self.assertEqual(proof_params, (51, 51, 51, "default", "default", 51))
        self.assertNotIn("bank_source.id::text =", proof_sql)
        self.assertNotIn("or bank_source.legacy_mongo_id", proof_sql)
        self.assertIn("source.id = case", proof_sql)
        self.assertIn("source.legacy_mongo_id = bank_identity.transaction_id", proof_sql)
        self.assertIn("source.id is distinct from case", proof_sql)
        self.assertIn("member_payloads as not materialized", proof_sql)
        self.assertIn("group_row.group_type = 'relation'", proof_sql)
        self.assertIn("group_row.zone in ('paired', 'unpaired')", proof_sql)
        self.assertNotIn("zone = 'paired'", proof_sql)
        self.assertIn("member.member_payload->>'workflow_status'", proof_sql)
        self.assertIn("'已完成'", proof_sql)
        self.assertIn("bank_row.transaction_id || ':oa:' || oa_row.oa_id", proof_sql)
        self.assertIn("bank_row.transaction_id || ':full'", proof_sql)
        self.assertIn("scope_key = relation_scope_key", proof_sql)
        self.assertIn('expense_content collate "C"', proof_sql)
        self.assertIn('applicant collate "C"', proof_sql)

        source = COST_PAGE_AUDIT_PATH.read_text(encoding="utf-8")
        for retired_helper in (
            "def _scope_row_count_mismatch_issues(",
            "def _missing_read_model_scope_issues(",
            "def _duplicate_read_model_identity_issues(",
            "def _canonical_expected_set_issues(",
            "def _proof_query_issues(",
        ):
            self.assertNotIn(retired_helper, source)

    def test_summary_runtime_state_is_one_query_and_remains_fail_closed(self) -> None:
        connection = CostAuditFakeConnection(
            rows_by_check={
                "dirty_scope": [
                    {
                        "scope_type": "cost_statistics",
                        "scope_key": "active:2026-06",
                        "status": "processing",
                        "updated_at": "2026-07-16T10:00:00+08:00",
                        "last_error": None,
                    }
                ],
                "outbox_backlog": [
                    {
                        "event_type": "cost_statistics.read_model.refresh",
                        "scope_key": "active:2026-06",
                        "status": "pending",
                        "updated_at": "2026-07-16T10:00:00+08:00",
                        "last_error": None,
                    }
                ],
            }
        )

        report = audit_cost_statistics_page(connection)

        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "backlog")
        self.assertEqual(report["summary"]["dirty_scope_count"], 1)
        self.assertEqual(report["summary"]["outbox_backlog_count"], 1)
        self.assertEqual(
            set(report["summary"]["issue_sample_counts_by_code"]),
            {"read_model_outbox_not_drained", "read_model_scope_not_fresh"},
        )
        self.assertEqual(len(connection.fetch_one_calls), 1)
        summary_sql = connection.fetch_one_calls[0][0]
        self.assertNotIn("set_config('jit'", summary_sql)
        self.assertIn("dirty_scope_rows as materialized", summary_sql)
        self.assertIn("outbox_backlog_rows as materialized", summary_sql)
        self.assertFalse(
            any(
                "/* check: dirty_scope */" in sql or "/* check: outbox_backlog */" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_source_version_proofs_use_one_query_and_preserve_each_issue_contract(self) -> None:
        connection = CostAuditFakeConnection(
            rows_by_check={
                "cost_source_version_proofs": [
                    {
                        "issue_code": "cost_statistics_row_source_versions_mismatch",
                        "subject_id": "bank-1",
                        "scope_key": "active:2026-06",
                        "details": {
                            "row_source_versions": {"version": 1},
                            "scope_source_versions": {"version": 2},
                        },
                    },
                    {
                        "issue_code": "cost_statistics_upstream_source_versions_mismatch",
                        "subject_id": "all:2026-06",
                        "scope_key": "all:2026-06",
                        "details": {
                            "embedded_workbench_source_versions": {"generation": "old"},
                            "current_workbench_source_versions": {"generation": "new"},
                        },
                    },
                    {
                        "issue_code": "cost_statistics_parent_source_shards_mismatch",
                        "subject_id": "all:all",
                        "scope_key": "all:all",
                        "details": {
                            "expected_shard_count": 2,
                            "present_shard_count": 1,
                        },
                    },
                ]
            }
        )

        report = audit_cost_statistics_page(connection)

        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {
                "cost_statistics_parent_source_shards_mismatch": 1,
                "cost_statistics_row_source_versions_mismatch": 1,
                "cost_statistics_upstream_source_versions_mismatch": 1,
            },
        )
        self.assertEqual(
            {issue["code"]: issue["details"] for issue in report["issues"]},
            {
                "cost_statistics_row_source_versions_mismatch": {
                    "row_source_versions": {"version": 1},
                    "scope_source_versions": {"version": 2},
                },
                "cost_statistics_upstream_source_versions_mismatch": {
                    "embedded_workbench_source_versions": {"generation": "old"},
                    "current_workbench_source_versions": {"generation": "new"},
                },
                "cost_statistics_parent_source_shards_mismatch": {
                    "expected_shard_count": 2,
                    "present_shard_count": 1,
                },
            },
        )
        proof_calls = [
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "/* check: cost_source_version_proofs */" in sql
        ]
        self.assertEqual(len(proof_calls), 1)
        proof_sql, proof_params = proof_calls[0]
        self.assertEqual(proof_sql.count("limit %s"), 3)
        self.assertEqual(proof_params, (51, "default", "default", 51, "default", 51))
        self.assertEqual(proof_sql.count("- 'source_version'"), 4)
        self.assertEqual(proof_sql.count("- 'workbench_relation_source_versions'"), 2)
        self.assertEqual(proof_sql.count("- 'bank_transactions_context_row_count'"), 2)
        self.assertEqual(proof_sql.count("- 'bank_transactions_updated_at'"), 2)
        self.assertNotIn("/* check: source_versions_mismatch */", proof_sql)
        self.assertNotIn("/* check: cost_upstream_source_versions */", proof_sql)
        self.assertNotIn("/* check: cost_parent_source_shards */", proof_sql)
        self.assertIn(
            "source_versions->'workbench_source_versions', '{}'::jsonb)\n"
            "                  - 'source_version'",
            proof_sql,
        )
        self.assertIn(
            "current_workbench_source_versions, '{}'::jsonb)\n"
            "                  - 'source_version'",
            proof_sql,
        )
        for field in (
            "source_version",
            "workbench_relation_source_versions",
            "bank_transactions_context_row_count",
            "bank_transactions_updated_at",
        ):
            self.assertEqual(proof_sql.count(f"- '{field}'"), 2 if field != "source_version" else 4)

    def test_business_value_proofs_use_one_query_and_preserve_each_issue_contract(self) -> None:
        issue_rows = [
            {
                "issue_code": code,
                "subject_id": subject_id,
                "scope_key": "active:2026-06",
                "details": details,
            }
            for code, subject_id, details in (
                (
                    "cost_statistics_key_display_fields_mismatch",
                    "cost-row-1",
                    {"structured_amount": "10", "payload_amount": "9"},
                ),
                (
                    "cost_statistics_summary_recalculation_mismatch",
                    "active:2026-06",
                    {"row_count": 2, "recalculated_total_amount": "30"},
                ),
                (
                    "cost_statistics_group_summaries_mismatch",
                    "active:2026-06:project:项目A",
                    {"summary_kind": "project", "expected_transaction_count": 2},
                ),
                (
                    "cost_statistics_bank_accounts_mismatch",
                    "active:2026-06:银行A:1234",
                    {"expected_source": "settings", "projected_source": ""},
                ),
            )
        ]
        connection = CostAuditFakeConnection(
            rows_by_check={"cost_business_value_proofs": issue_rows}
        )

        report = audit_cost_statistics_page(connection)

        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {row["issue_code"]: 1 for row in issue_rows},
        )
        self.assertEqual(
            {issue["code"]: issue["details"] for issue in report["issues"]},
            {row["issue_code"]: row["details"] for row in issue_rows},
        )
        proof_calls = [
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "/* check: cost_business_value_proofs */" in sql
        ]
        self.assertEqual(len(proof_calls), 1)
        proof_sql, proof_params = proof_calls[0]
        for marker in (
            "/* check: key_display_fields */",
            "/* check: cost_summary_recalculation */",
            "/* check: cost_group_summaries */",
            "/* check: cost_bank_accounts */",
        ):
            self.assertEqual(proof_sql.count(marker), 1)
        self.assertIn("model.scope_key ~ '^(active|all):all$'", proof_sql)
        self.assertEqual(proof_sql.count("limit %s"), 4)
        self.assertEqual(
            proof_params,
            (
                "cost_statistics_key_display_fields_mismatch",
                51,
                "cost_statistics_summary_recalculation_mismatch",
                "default",
                BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                51,
                "cost_statistics_group_summaries_mismatch",
                51,
                "cost_statistics_bank_accounts_mismatch",
                51,
            ),
        )

    def test_bank_statistics_proof_reads_canonical_bank_detail_rows(self) -> None:
        connection = CostAuditFakeConnection()

        audit_cost_statistics_page(connection)

        canonical_sql = next(
            sql
            for sql, _params in connection.fetch_all_calls
            if "/* check: canonical_expected_set */" in sql
        )
        business_sql = next(
            sql
            for sql, _params in connection.fetch_all_calls
            if "/* check: cost_business_value_proofs */" in sql
        )
        queried_sql = canonical_sql + business_sql

        self.assertNotIn("bank_flow_time_rows", queried_sql)
        self.assertNotIn("model.payload->'payload'->'bank_flow_time_rows'", queried_sql)
        self.assertNotIn("cost_statistics_bank_flow_rows", queried_sql)
        self.assertIn("from read_model.bank_detail_rows", business_sql)
        self.assertIn("when 'expense' then '支出'", business_sql)
        self.assertIn("when 'income' then '收入'", business_sql)
        self.assertIn("expected_bank_scope_rows as (", business_sql)
        self.assertIn(
            "select project_scope || ':all' as scope_key",
            business_sql,
        )

    def test_relation_equality_runs_once_and_preserves_both_existing_issue_codes(self) -> None:
        connection = CostAuditFakeConnection(
            rows_by_check={
                "relation_edge_equality": [
                    {
                        "subject_id": "case-cost-1",
                        "scope_key": "2026-06",
                        "row_id": "bank-1",
                        "row_type": "bank_transaction",
                        "mismatch_kind": "canonical_missing_group_edge",
                    }
                ]
            }
        )

        report = audit_cost_statistics_page(connection)

        self.assertEqual(
            set(report["summary"]["issue_sample_counts_by_code"]),
            {
                "cost_statistics_dependency_workbench_reconciliation_workbench_relation_edge_mismatch",
                "cost_statistics_relation_edge_mismatch",
            },
        )
        self.assertEqual(
            sum(
                "/* check: relation_edge_equality */" in sql
                for sql, _params in connection.fetch_all_calls
            ),
            1,
        )

    def test_explicit_caller_snapshot_is_preserved(self) -> None:
        connection = CostAuditFakeConnection()
        snapshot = AuditSnapshot(
            connection=connection,
            consistency="repeatable_read_read_only",
            database_snapshot=True,
        )

        report = audit_cost_statistics_page(connection, audit_snapshot=snapshot)

        self.assertEqual(report["audit_contract"]["snapshot_consistency"], "repeatable_read_read_only")
        self.assertTrue(report["audit_contract"]["database_snapshot"])
        self.assertEqual(connection.executed, [])

    def test_registry_routes_cost_statistics_to_the_only_cost_executor(self) -> None:
        registration = PAGE_AUDIT_REGISTRY["cost-statistics"]

        self.assertEqual(registration.executor, "cost_statistics")
        self.assertIsNone(registration.executor_domain_key)

    def test_operations_and_system_paths_pass_the_same_snapshot_to_cost_owner(self) -> None:
        connection = FakeConnection()
        repository = PostgresOperationsAuditRepository(connection)
        snapshot = AuditSnapshot(
            connection=connection,
            consistency="repeatable_read_read_only",
            database_snapshot=True,
        )
        registration = page_audit_registration("cost-statistics")

        with patch(
            "fin_ops_platform.services.postgres_repositories.operations_audit.audit_cost_statistics_page",
            return_value={"audit_contract": {}},
        ) as audit:
            report = repository._audit_registration(  # noqa: SLF001 - verifies the System Audit dispatch boundary.
                registration,
                tenant_id="tenant-a",
                sample_limit=17,
                audit_snapshot=snapshot,
                system_snapshot_identity="snapshot-a",
            )

        audit.assert_called_once_with(
            connection,
            tenant_id="tenant-a",
            example_limit=17,
            audit_snapshot=snapshot,
        )
        self.assertEqual(report["page_key"], "cost-statistics")
        self.assertEqual(report["audit_contract"]["system_snapshot_identity"], "snapshot-a")

    def test_shared_page_business_repository_has_no_cost_runtime_branch(self) -> None:
        source = SHARED_PAGE_AUDIT_PATH.read_text(encoding="utf-8")

        self.assertNotIn("cost_statistics", source)
        self.assertNotIn("cost-statistics", source)

    def test_generic_read_only_cli_routes_cost_domain_to_the_unique_owner(self) -> None:
        stdout = io.StringIO()

        exit_code = audit_cli.main(
            ["cost_statistics", "--json", "--fail-on-issues"],
            connection=FakeConnection(),
            stdout=stdout,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["domain_key"], "cost_statistics")


class CostStatisticsPageAuditPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        source_versions = {
            "cost_statistics_parent_source": "materialized_shards",
            "source_shards": {},
            "source_shard_count": 0,
        }
        parent_payload = {
            "payload": {
                "summary": {"row_count": 0, "transaction_count": 0, "total_amount": "0"},
                "statistics": {
                    "transaction_count": 0,
                    "expense_transaction_count": 0,
                    "income_transaction_count": 0,
                    "cost_group_count": 0,
                    "tagged_transaction_count": 0,
                    "untagged_transaction_count": 0,
                    "project_count": 0,
                    "expense_type_count": 0,
                    "bank_tag_count": 0,
                    "cost_transaction_count": 0,
                },
                "bank_accounts": [],
                "project_rows": [],
                "expense_type_rows": [],
            }
        }
        for project_scope in ("active", "all"):
            self.connection.execute(
                """
                insert into read_model.cost_statistics_read_models(
                    scope_key, project_scope, scope_month, generated_at, entry_count,
                    source_counts, source_versions, payload, raw_payload
                ) values (%s, %s, null, now(), 0, '{}'::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                """,
                (
                    f"{project_scope}:all",
                    project_scope,
                    json.dumps(source_versions),
                    json.dumps(parent_payload),
                    json.dumps({"normalized_payload": parent_payload}),
                ),
            )

        empty_page_statistics = json.dumps(
            {
                "oa_count": 0,
                "bank_transaction_count": 0,
                "paired_group_count": 0,
                "paired_oa_count": 0,
                "paired_bank_transaction_count": 0,
                "paired_invoice_count": 0,
                "unpaired_object_count": 0,
            }
        )
        for zone in ("paired", "unpaired"):
            self.connection.execute(
                """
                insert into read_model.workbench_generation_stats(
                    generation_id, scope_key, zone, status_bucket, payload
                ) values ('empty-all', 'all', %s, 'all', jsonb_build_object('page_statistics', %s::jsonb))
                """,
                (zone, empty_page_statistics),
            )

    def tearDown(self) -> None:
        truncate_test_database(self.database_url)

    def test_v11_parent_without_row_arrays_passes_real_postgres_audit(self) -> None:
        report = audit_cost_statistics_page(
            self.connection,
            tenant_id="default",
            example_limit=20,
        )

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(
            report["audit_status"],
            {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        )
        self.assertEqual(report["issues"], [])


if __name__ == "__main__":
    unittest.main()
