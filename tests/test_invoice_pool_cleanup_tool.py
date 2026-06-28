from __future__ import annotations

import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import invoice_pool_cleanup


class _FakeConnection:
    def __init__(
        self,
        *,
        app_invoices: int = 638,
        app_etc_invoices: int = 259,
        final_metrics: dict[str, int] | None = None,
        final_identity_keys: set[str] | None = None,
    ) -> None:
        self.app_invoices = app_invoices
        self.app_etc_invoices = app_etc_invoices
        self.final_metrics = final_metrics
        self.final_identity_keys = final_identity_keys
        self.executed_sql: list[str] = []

    def fetch_all(self, query: str) -> list[dict[str, object]]:
        normalized_query = " ".join(str(query).lower().split())
        if "select distinct identity_key" in normalized_query:
            identity_keys = self.final_identity_keys
            if identity_keys is None:
                identity_keys = _expected_identity_keys() if self.app_invoices == 391 else _expected_identity_keys() | {"EXTRA-001"}
            return [{"identity_key": key} for key in sorted(identity_keys)]
        if "with invoice_rows as" in normalized_query:
            return [
                {
                    "app_invoices": self.app_invoices,
                    "unique_identity_count": self.app_invoices,
                    "missing_identity_rows": 0,
                    "input_invoices": 371,
                    "output_invoices": 20,
                    "duplicate_identity_groups": 0,
                    "etc_only_canonical_rows": 0,
                    **dict(self.final_metrics or {}),
                }
            ]
        return [
            {"table_name": "app.invoices", "row_count": self.app_invoices},
            {"table_name": "app.etc_invoices", "row_count": self.app_etc_invoices},
            {"table_name": "app.input_invoice_usage_oa_reverse_batches", "row_count": 7},
            {"table_name": "read_model.input_invoice_usage_rows", "row_count": 616},
            {"table_name": "read_model.output_invoice_collection_rows", "row_count": 22},
        ]

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed_sql.append(sql)
        return 1


class InvoicePoolCleanupToolTests(unittest.TestCase):
    def test_preflight_blocks_soft_reference_strategy_before_execute(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=True)

            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(),
            )

            self.assertEqual(plan["gate_recommendation"], "BLOCKED_SOFT_REFERENCE_STRATEGY_REQUIRED")
            self.assertEqual(plan["count_guard"]["status"], "pass")
            self.assertEqual(
                [blocker["required_decision"] for blocker in plan["soft_reference_blockers"]],
                [
                    "archive_or_rebuild_oa_reverse_batches_before_canonical_pool_reset",
                    "rebuild_workbench_active_generation_after_reimport",
                ],
            )

    def test_preflight_blocks_when_app_invoice_count_changed_since_dry_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=False)

            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(app_invoices=639),
            )

            self.assertEqual(plan["gate_recommendation"], "BLOCKED_COUNT_GUARD")
            self.assertEqual(plan["count_guard"]["actual_app_invoices"], 639)

    def test_preflight_blocks_when_app_etc_invoice_count_changed_since_dry_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=False)

            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(app_etc_invoices=260),
            )

            self.assertEqual(plan["gate_recommendation"], "BLOCKED_COUNT_GUARD")
            self.assertEqual(plan["count_guard"]["reason"], "app_etc_invoices_count_changed_since_dry_run")
            self.assertEqual(plan["count_guard"]["actual_app_etc_invoices"], 260)

    def test_preflight_passes_when_soft_reference_strategies_are_explicit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=True)

            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(),
                oa_reverse_batch_strategy="archive_legacy_polluted_history",
            )

            self.assertEqual(plan["gate_recommendation"], "PASS_READY_TO_EXECUTE")
            self.assertEqual(plan["soft_reference_blockers"], [])
            self.assertEqual(
                [action["action"] for action in plan["resolved_soft_reference_actions"]],
                ["archive_legacy_polluted_oa_reverse_batches_before_canonical_pool_reset"],
            )
            self.assertEqual(
                plan["soft_reference_strategies"],
                {"oa_reverse_batch_strategy": "archive_legacy_polluted_history"},
            )
            actions_by_name = {action["action"]: action for action in plan["planned_actions"]}
            legacy_cleanup = actions_by_name["remove_legacy_etc_created_canonical_pollution"]
            self.assertTrue(legacy_cleanup["preserve_formal_excel_and_oa_canonical_invoices"])
            self.assertEqual(
                legacy_cleanup["legacy_match_rule"],
                "invoice_source='ETC导入' and invoice_kind='ETC发票' without non-ETC source links",
            )

    def test_preflight_accepts_scoped_backup_artifact_names(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(
                Path(temp_dir),
                include_blockers=True,
                backup_variant="scoped",
            )

            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(),
                oa_reverse_batch_strategy="archive_legacy_polluted_history",
            )

            self.assertEqual(plan["gate_recommendation"], "PASS_READY_TO_EXECUTE")
            accepted_files = {
                check["file"]
                for check in plan["backup_files"]
                if check.get("accepted")
            }
            self.assertEqual(
                accepted_files,
                {
                    "invoice_fact_tables.dump",
                    "invoice_related_schema.sql",
                    "backup_summary.json",
                    "checksums.tsv",
                },
            )

    def test_preflight_accepts_scoped_backup_with_separate_dry_run_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dry_run_owner = _write_backup_dir(root, include_blockers=True)
            backup_dir = _write_backup_dir(
                root,
                run_id="20260621050130",
                include_blockers=True,
                backup_variant="scoped",
                write_dry_run=False,
            )

            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                dry_run_dir=dry_run_owner / "cleanup_dry_run",
                connection=_FakeConnection(),
                oa_reverse_batch_strategy="archive_legacy_polluted_history",
            )

            self.assertEqual(plan["gate_recommendation"], "PASS_READY_TO_EXECUTE")
            self.assertEqual(plan["backup_dir"], str(backup_dir.resolve()))
            self.assertEqual(plan["dry_run_dir"], str((dry_run_owner / "cleanup_dry_run").resolve()))
            self.assertEqual(
                {
                    check["file"]
                    for check in plan["backup_files"]
                    if check.get("accepted")
                },
                {
                    "invoice_fact_tables.dump",
                    "invoice_related_schema.sql",
                    "backup_summary.json",
                    "checksums.tsv",
                },
            )

    def test_default_resolution_uses_latest_backup_and_latest_available_dry_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            older = _write_backup_dir(root, run_id="20260621031938", include_blockers=False)
            latest_backup = _write_backup_dir(
                root,
                run_id="20260621050130",
                include_blockers=False,
                backup_variant="scoped",
                write_dry_run=False,
            )

            with patch.object(invoice_pool_cleanup, "DEFAULT_AUDIT_ROOT", root):
                resolved_backup = invoice_pool_cleanup.resolve_backup_dir(None)
                resolved_dry_run = invoice_pool_cleanup.resolve_dry_run_dir(resolved_backup, None)

            self.assertEqual(resolved_backup, latest_backup)
            self.assertEqual(resolved_dry_run, older / "cleanup_dry_run")

    def test_preflight_blocks_when_backup_data_dump_alternatives_are_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(
                Path(temp_dir),
                include_blockers=False,
                backup_variant="scoped",
                omit_backup_files={"invoice_fact_tables.dump"},
            )

            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(),
                oa_reverse_batch_strategy="archive_legacy_polluted_history",
            )

            self.assertEqual(plan["gate_recommendation"], "BLOCKED_BACKUP_ARTIFACT_MISSING")
            data_dump_checks = [
                check
                for check in plan["backup_files"]
                if check.get("group") == "data_dump"
            ]
            self.assertTrue(data_dump_checks)
            self.assertTrue(all(not check.get("accepted") for check in data_dump_checks))

    def test_cli_execute_requires_guards_and_never_runs_from_blocked_plan(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=True)
            stdout = StringIO()
            stderr = StringIO()

            with patch.dict("os.environ", {}, clear=True):
                exit_code = invoice_pool_cleanup.main(
                    ["--backup-dir", str(backup_dir), "--execute"],
                    stdout=stdout,
                    stderr=stderr,
                    connection=_FakeConnection(),
                )

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["gate_recommendation"], "BLOCKED_EXECUTE_GUARD")
            self.assertIn("FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTE=1_required", payload["execute_errors"])
            self.assertIn("FIN_OPS_INVOICE_POOL_BACKUP_CONFIRMED=1_required", payload["execute_errors"])
            self.assertIn("confirm_token_mismatch", payload["execute_errors"])
            self.assertIn("preflight_not_ready_to_execute", payload["execute_errors"])

    def test_cli_execute_requires_sql_artifact_after_preflight_passes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=True)
            stdout = StringIO()
            stderr = StringIO()

            with patch.dict(
                "os.environ",
                {
                    "FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTE": "1",
                    "FIN_OPS_INVOICE_POOL_BACKUP_CONFIRMED": "1",
                },
                clear=True,
            ):
                exit_code = invoice_pool_cleanup.main(
                    [
                        "--backup-dir",
                        str(backup_dir),
                        "--execute",
                        "--confirm-token",
                        invoice_pool_cleanup.CONFIRM_TOKEN,
                        "--oa-reverse-batch-strategy",
                        "archive_legacy_polluted_history",
                    ],
                    stdout=stdout,
                    stderr=stderr,
                    connection=_FakeConnection(),
                )

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["gate_recommendation"], "BLOCKED_EXECUTE_SQL_GUARD")
            self.assertEqual(
                payload["execute_errors"],
                ["execution_sql_file_required", "execution_sql_sha256_required"],
            )

    def test_cli_execute_blocks_sql_checksum_mismatch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backup_dir = _write_backup_dir(root, include_blockers=True)
            sql_path = root / "cleanup.sql"
            sql_path.write_text(_executable_sql(), encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()

            with patch.dict(
                "os.environ",
                {
                    "FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTE": "1",
                    "FIN_OPS_INVOICE_POOL_BACKUP_CONFIRMED": "1",
                },
                clear=True,
            ):
                exit_code = invoice_pool_cleanup.main(
                    [
                        "--backup-dir",
                        str(backup_dir),
                        "--execute",
                        "--confirm-token",
                        invoice_pool_cleanup.CONFIRM_TOKEN,
                        "--oa-reverse-batch-strategy",
                        "archive_legacy_polluted_history",
                        "--execution-sql-file",
                        str(sql_path),
                        "--execution-sql-sha256",
                        "0" * 64,
                    ],
                    stdout=stdout,
                    stderr=stderr,
                    connection=_FakeConnection(),
                )

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["gate_recommendation"], "BLOCKED_EXECUTE_SQL_GUARD")
            self.assertEqual(payload["execute_errors"], ["execution_sql_sha256_mismatch"])

    def test_cli_execute_rejects_review_only_sql_artifact(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backup_dir = _write_backup_dir(root, include_blockers=True)
            sql_path = root / "review.sql"
            review_sql = "-- REVIEW ONLY. DO NOT RUN AS A PRODUCTION CLEANUP SCRIPT.\nbegin;\nrollback;\n"
            sql_path.write_text(review_sql, encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()

            with patch.dict(
                "os.environ",
                {
                    "FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTE": "1",
                    "FIN_OPS_INVOICE_POOL_BACKUP_CONFIRMED": "1",
                },
                clear=True,
            ):
                exit_code = invoice_pool_cleanup.main(
                    [
                        "--backup-dir",
                        str(backup_dir),
                        "--execute",
                        "--confirm-token",
                        invoice_pool_cleanup.CONFIRM_TOKEN,
                        "--oa-reverse-batch-strategy",
                        "archive_legacy_polluted_history",
                        "--execution-sql-file",
                        str(sql_path),
                        "--execution-sql-sha256",
                        _sha256(review_sql),
                    ],
                    stdout=stdout,
                    stderr=stderr,
                    connection=_FakeConnection(),
                )

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["gate_recommendation"], "BLOCKED_EXECUTE_SQL_GUARD")
            self.assertEqual(
                payload["execute_errors"],
                [
                    "execution_sql_marker_required",
                    "execution_sql_review_only_forbidden",
                    "execution_sql_rollback_forbidden",
                ],
            )

    def test_cli_execute_runs_only_marker_sql_with_exact_checksum(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backup_dir = _write_backup_dir(root, include_blockers=True)
            sql_path = root / "cleanup.sql"
            executable_sql = _executable_sql()
            sql_path.write_text(executable_sql, encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()
            connection = _FakeConnection()

            with patch.dict(
                "os.environ",
                {
                    "FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTE": "1",
                    "FIN_OPS_INVOICE_POOL_BACKUP_CONFIRMED": "1",
                },
                clear=True,
            ):
                exit_code = invoice_pool_cleanup.main(
                    [
                        "--backup-dir",
                        str(backup_dir),
                        "--execute",
                        "--confirm-token",
                        invoice_pool_cleanup.CONFIRM_TOKEN,
                        "--oa-reverse-batch-strategy",
                        "archive_legacy_polluted_history",
                        "--execution-sql-file",
                        str(sql_path),
                        "--execution-sql-sha256",
                        _sha256(executable_sql),
                    ],
                    stdout=stdout,
                    stderr=stderr,
                    connection=connection,
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["gate_recommendation"], "PASS_EXECUTED")
            self.assertTrue(payload["executed"])
            self.assertEqual(payload["execute_errors"], [])
            self.assertEqual(connection.executed_sql, [executable_sql])

    def test_verify_final_invoice_pool_passes_clean_reimport_invariants(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=True)
            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(app_invoices=638),
                oa_reverse_batch_strategy="archive_legacy_polluted_history",
            )

            result = invoice_pool_cleanup.verify_final_invoice_pool(
                plan,
                connection=_FakeConnection(app_invoices=391),
            )

            self.assertEqual(result["gate_recommendation"], "PASS_FINAL_INVARIANTS")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["final_invariants"]["failures"], [])
            self.assertEqual(
                result["final_invariants"]["identity_set_check"]["actual"]["missing_excel_identity_count"],
                0,
            )
            self.assertEqual(
                result["final_invariants"]["identity_set_check"]["actual"]["extra_identity_count"],
                0,
            )

    def test_verify_final_invoice_pool_can_use_excel_files_as_expected_identity_source(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backup_dir = _write_backup_dir(root, include_blockers=True)
            input_path = root / "input.xlsx"
            output_path = root / "output.xlsx"
            input_path.write_bytes(b"input")
            output_path.write_bytes(b"output")

            with (
                patch.object(invoice_pool_cleanup, "read_xlsx_rows", side_effect=[[["input"]], [["output"]]]),
                patch.object(
                    invoice_pool_cleanup,
                    "parse_invoice_rows",
                    side_effect=[
                        [
                            {"digital_invoice_no": "INPUT-001"},
                            {"invoice_code": "053001", "invoice_no": "90010001"},
                        ],
                        [
                            {"digital_invoice_no": "OUTPUT-001"},
                        ],
                    ],
                ),
            ):
                expected_source = invoice_pool_cleanup.build_expected_invoice_source(
                    dry_run_dir=backup_dir / "cleanup_dry_run",
                    input_invoice_xlsx=input_path,
                    output_invoice_xlsx=output_path,
                )

            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(),
                oa_reverse_batch_strategy="archive_legacy_polluted_history",
            )
            result = invoice_pool_cleanup.verify_final_invoice_pool(
                plan,
                connection=_FakeConnection(
                    app_invoices=3,
                    final_identity_keys={"INPUT-001", "053001:90010001", "OUTPUT-001"},
                    final_metrics={
                        "unique_identity_count": 3,
                        "input_invoices": 2,
                        "output_invoices": 1,
                    },
                ),
                expected_source=expected_source,
            )

            self.assertEqual(expected_source["source"], "excel_files")
            self.assertEqual(expected_source["input_rows"], 2)
            self.assertEqual(expected_source["output_rows"], 1)
            self.assertEqual(result["gate_recommendation"], "PASS_FINAL_INVARIANTS")
            self.assertEqual(result["final_invariants"]["expected_identity_source"], "excel_files")

    def test_verify_input_invoice_files_passes_for_expected_rows_and_unique_identities(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.xlsx"
            output_path = root / "output.xlsx"
            input_path.write_bytes(b"input")
            output_path.write_bytes(b"output")

            with (
                patch.object(invoice_pool_cleanup, "read_xlsx_rows", side_effect=[[["input"]], [["output"]]]),
                patch.object(
                    invoice_pool_cleanup,
                    "parse_invoice_rows",
                    side_effect=[
                        [
                            {"digital_invoice_no": "INPUT-001", "invoice_date": "2026-01-01"},
                            {"invoice_code": "053001", "invoice_no": "90010001", "invoice_date": "2026-02-01"},
                        ],
                        [
                            {"digital_invoice_no": "OUTPUT-001", "invoice_date": "2026-03-01"},
                        ],
                    ],
                ),
            ):
                result = invoice_pool_cleanup.verify_input_invoice_files(
                    input_invoice_xlsx=input_path,
                    output_invoice_xlsx=output_path,
                    expected_input_rows=2,
                    expected_output_rows=1,
                )

            self.assertEqual(result["gate_recommendation"], "PASS_INPUT_FILES")
            self.assertEqual(result["summary"]["parsed_total_rows"], 3)
            self.assertEqual(result["summary"]["unique_identity_count"], 3)
            self.assertEqual(result["files"][0]["month_counts"], {"2026-01": 1, "2026-02": 1})

    def test_verify_input_invoice_files_blocks_missing_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.xlsx"
            input_path.write_bytes(b"input")

            with (
                patch.object(invoice_pool_cleanup, "read_xlsx_rows", return_value=[["input"]]),
                patch.object(
                    invoice_pool_cleanup,
                    "parse_invoice_rows",
                    return_value=[{"digital_invoice_no": "INPUT-001"}],
                ),
            ):
                result = invoice_pool_cleanup.verify_input_invoice_files(
                    input_invoice_xlsx=input_path,
                    output_invoice_xlsx=root / "missing-output.xlsx",
                    expected_input_rows=1,
                    expected_output_rows=1,
                )

            self.assertEqual(result["gate_recommendation"], "BLOCKED_INPUT_FILES")
            self.assertEqual(result["errors"][0]["code"], "invoice_xlsx_not_found")

    def test_verify_input_invoice_files_blocks_duplicate_or_missing_identity(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.xlsx"
            output_path = root / "output.xlsx"
            input_path.write_bytes(b"input")
            output_path.write_bytes(b"output")

            with (
                patch.object(invoice_pool_cleanup, "read_xlsx_rows", side_effect=[[["input"]], [["output"]]]),
                patch.object(
                    invoice_pool_cleanup,
                    "parse_invoice_rows",
                    side_effect=[
                        [
                            {"digital_invoice_no": "DUP-001", "invoice_date": "2026-01-01"},
                            {"invoice_date": "2026-01-02"},
                        ],
                        [
                            {"digital_invoice_no": "DUP-001", "invoice_date": "2026-03-01"},
                        ],
                    ],
                ),
            ):
                result = invoice_pool_cleanup.verify_input_invoice_files(
                    input_invoice_xlsx=input_path,
                    output_invoice_xlsx=output_path,
                    expected_input_rows=2,
                    expected_output_rows=1,
                )

            self.assertEqual(result["gate_recommendation"], "BLOCKED_INPUT_FILES")
            error_codes = [error["code"] for error in result["errors"]]
            self.assertIn("missing_strong_identity_rows", error_codes)
            self.assertIn("duplicate_identity_keys_across_input_files", error_codes)

    def test_cli_verify_input_files_does_not_require_backup_dir_or_database(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.xlsx"
            output_path = root / "output.xlsx"
            input_path.write_bytes(b"input")
            output_path.write_bytes(b"output")
            stdout = StringIO()

            with (
                patch.object(invoice_pool_cleanup, "resolve_backup_dir") as resolve_backup_dir,
                patch.object(invoice_pool_cleanup, "build_connection_from_env") as build_connection_from_env,
                patch.object(invoice_pool_cleanup, "read_xlsx_rows", side_effect=[[["input"]], [["output"]]]),
                patch.object(
                    invoice_pool_cleanup,
                    "parse_invoice_rows",
                    side_effect=[
                        [{"digital_invoice_no": "INPUT-001", "invoice_date": "2026-01-01"}],
                        [{"digital_invoice_no": "OUTPUT-001", "invoice_date": "2026-02-01"}],
                    ],
                ),
            ):
                exit_code = invoice_pool_cleanup.main(
                    [
                        "--verify-input-files",
                        "--input-invoice-xlsx",
                        str(input_path),
                        "--output-invoice-xlsx",
                        str(output_path),
                        "--expected-input-rows",
                        "1",
                        "--expected-output-rows",
                        "1",
                    ],
                    stdout=stdout,
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("PASS_INPUT_FILES", stdout.getvalue())
            resolve_backup_dir.assert_not_called()
            build_connection_from_env.assert_not_called()

    def test_verify_final_invoice_pool_blocks_polluted_current_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=True)
            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(),
                oa_reverse_batch_strategy="archive_legacy_polluted_history",
            )

            result = invoice_pool_cleanup.verify_final_invoice_pool(
                plan,
                connection=_FakeConnection(
                    final_metrics={
                        "app_invoices": 638,
                        "unique_identity_count": 614,
                        "input_invoices": 616,
                        "output_invoices": 22,
                        "duplicate_identity_groups": 22,
                        "etc_only_canonical_rows": 225,
                    },
                    final_identity_keys=_expected_identity_keys() | {"EXTRA-001", "EXTRA-002"},
                ),
            )

            self.assertEqual(result["gate_recommendation"], "BLOCKED_FINAL_INVARIANTS")
            failures = {failure["name"]: failure for failure in result["final_invariants"]["failures"]}
            self.assertEqual(failures["app_invoices"]["actual"], 638)
            self.assertEqual(failures["unique_identity_count"]["actual"], 614)
            self.assertEqual(failures["etc_only_canonical_rows"]["actual"], 225)
            self.assertEqual(failures["extra_identity_count"]["actual"], 2)

    def test_verify_final_invoice_pool_blocks_when_excel_identity_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=True)
            plan = invoice_pool_cleanup.build_cleanup_preflight_plan(
                backup_dir,
                connection=_FakeConnection(),
                oa_reverse_batch_strategy="archive_legacy_polluted_history",
            )

            result = invoice_pool_cleanup.verify_final_invoice_pool(
                plan,
                connection=_FakeConnection(
                    app_invoices=391,
                    final_identity_keys=_expected_identity_keys() - {"EXCEL-391"},
                ),
            )

            self.assertEqual(result["gate_recommendation"], "BLOCKED_FINAL_INVARIANTS")
            failures = {failure["name"]: failure for failure in result["final_invariants"]["failures"]}
            self.assertEqual(failures["missing_excel_identity_count"]["actual"], 1)
            self.assertEqual(failures["missing_excel_identity_count"]["examples"], ["EXCEL-391"])

    def test_cli_verify_final_requires_database_connection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backup_dir = _write_backup_dir(Path(temp_dir), include_blockers=True)
            stdout = StringIO()
            stderr = StringIO()

            exit_code = invoice_pool_cleanup.main(
                [
                    "--backup-dir",
                    str(backup_dir),
                    "--verify-final",
                    "--oa-reverse-batch-strategy",
                    "archive_legacy_polluted_history",
                ],
                stdout=stdout,
                stderr=stderr,
                connection=None,
            )

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["gate_recommendation"], "BLOCKED_FINAL_INVARIANTS")
            self.assertEqual(payload["final_invariants"]["reason"], "database_connection_required")


def _write_backup_dir(
    root: Path,
    *,
    include_blockers: bool,
    run_id: str = "20260621031938",
    backup_variant: str = "legacy",
    omit_backup_files: set[str] | None = None,
    write_dry_run: bool = True,
) -> Path:
    backup_dir = root / run_id
    backup_dir.mkdir(parents=True)
    if backup_variant == "legacy":
        backup_files = invoice_pool_cleanup.REQUIRED_BACKUP_FILES
    elif backup_variant == "scoped":
        backup_files = (
            "invoice_fact_tables.dump",
            "invoice_related_schema.sql",
            "backup_summary.json",
            "checksums.tsv",
        )
    else:
        raise ValueError(f"unsupported backup variant: {backup_variant}")
    omitted = omit_backup_files or set()
    for filename in backup_files:
        if filename in omitted:
            continue
        (backup_dir / filename).write_text("backup-artifact\n", encoding="utf-8")
    if not write_dry_run:
        return backup_dir
    dry_run_dir = backup_dir / "cleanup_dry_run"
    dry_run_dir.mkdir()
    summary = {
        "current_app_invoices_rows": 638,
        "app_etc_invoices_rows": 259,
        "recommended_full_reset_delete_app_invoices_rows": 638,
        "excel_unique_identity_keys": 391,
    }
    (dry_run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    for filename in invoice_pool_cleanup.DRY_RUN_FILES:
        path = dry_run_dir / filename
        if path.name == "summary.json":
            continue
        if path.name == "candidate_keep_excel_identities.csv":
            rows = ["identity_key,invoice_type"]
            rows.extend(f"{identity_key},input" for identity_key in sorted(_expected_identity_keys()))
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        elif path.name == "soft_reference_inventory.csv":
            rows = [
                "table_schema,table_name,column_name,data_type,udt_name,probe_kind,matching_rows,query_error",
            ]
            if include_blockers:
                rows.extend(
                    [
                        "app,input_invoice_usage_oa_reverse_batches,invoice_ids,ARRAY,_text,invoice_id_array,7,",
                    ]
                )
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        else:
            path.write_text("artifact\n", encoding="utf-8")
    return backup_dir


def _expected_identity_keys() -> set[str]:
    return {f"EXCEL-{index:03d}" for index in range(1, 392)}


def _executable_sql() -> str:
    return (
        f"-- {invoice_pool_cleanup.EXECUTABLE_SQL_MARKER}\n"
        "begin;\n"
        "select 1;\n"
        "commit;\n"
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
