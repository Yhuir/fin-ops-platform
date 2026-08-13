from __future__ import annotations

import gzip
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock
from time import sleep
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import http_slo_probe


class HttpSloProbeTests(unittest.TestCase):
    def test_default_workbench_probes_are_unique_direct_canonical_reads(self) -> None:
        probes = [
            probe
            for probe in http_slo_probe.DEFAULT_API_PROBES
            if probe.name.startswith("workbench_") and probe.name != "workbench_settings"
        ]

        self.assertEqual(
            {probe.name for probe in probes},
            {
                "workbench_initial_all",
                "workbench_groups_all_paired",
                "workbench_groups_all_unpaired",
                "workbench_filter_options_all_paired",
            },
        )
        self.assertEqual(len({probe.name for probe in probes}), len(probes))
        self.assertEqual(len({probe.path for probe in probes}), len(probes))
        self.assertTrue(all(probe.expected_statuses == (200,) for probe in probes))
        self.assertTrue(all("page=" not in probe.path for probe in probes))
        self.assertTrue(all("/refresh-status" not in probe.path for probe in probes))

    def test_capacity_targets_are_derived_from_anonymous_rolling_sixty_second_counts(self) -> None:
        counts = [1] * 19_152 + [5] * 1_008

        result = http_slo_probe.derive_capacity_targets(
            {
                "mode": "access_evidence",
                "source": "nginx_authenticated_refresh_status_access",
                "source_version": "access-log-v3",
                "source_proof": "sha256:aggregate-query",
                "window": {
                    "started_at": "2026-07-22T00:00:00+08:00",
                    "completed_at": "2026-08-05T00:00:00+08:00",
                },
                "method": "rolling_60s_unique_visible_clients",
                "rolling_60s_unique_visible_clients": counts,
            }
        )

        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["c_normal"], 1)
        self.assertEqual(result["c_peak"], 5)
        self.assertEqual(result["n_normal"], 4)
        self.assertEqual(result["n_peak"], 8)
        self.assertEqual(result["aggregate_sample_count"], 20_160)
        self.assertFalse(result["raw_client_data_retained"])
        self.assertNotIn("rolling_60s_unique_visible_clients", result)

    def test_capacity_contract_requires_source_version_and_approver(self) -> None:
        measured = http_slo_probe.derive_capacity_targets(
            {
                "mode": "capacity_contract",
                "source": "approved-visible-client-capacity",
                "contract_version": "capacity-v1",
                "approved_by": "FINOPS-CAPACITY-20260806",
                "c_normal": 3,
                "c_peak": 6,
            }
        )
        unavailable = http_slo_probe.derive_capacity_targets(
            {
                "mode": "capacity_contract",
                "source": "approved-visible-client-capacity",
                "c_normal": 3,
                "c_peak": 6,
            }
        )

        self.assertEqual(measured["status"], "measured")
        self.assertEqual(measured["n_normal"], 4)
        self.assertEqual(measured["n_peak"], 8)
        self.assertEqual(unavailable["status"], "not_measured")
        self.assertTrue(unavailable["release_blocked"])

    def test_capacity_contract_rejects_non_integer_client_counts(self) -> None:
        result = http_slo_probe.derive_capacity_targets(
            {
                "mode": "capacity_contract",
                "source": "approved-visible-client-capacity",
                "contract_version": "capacity-v1",
                "approved_by": "FINOPS-CAPACITY-20260806",
                "c_normal": 3.5,
                "c_peak": 6,
            }
        )

        self.assertEqual(result["status"], "not_measured")
        self.assertTrue(result["release_blocked"])

    def test_capacity_tier_without_evidence_fails_before_http_sampling(self) -> None:
        stdout = StringIO()

        exit_code = http_slo_probe.main(["--capacity-tier", "normal"], stdout=stdout)
        report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "not_measured")
        self.assertTrue(report["release_blocked"])

    def test_default_peak_capacity_run_fails_when_iterations_cannot_reach_target(self) -> None:
        stdout = StringIO()
        with TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "capacity.json"
            evidence_path.write_text(json.dumps({
                "mode": "capacity_contract",
                "source": "approved-visible-client-capacity",
                "contract_version": "capacity-v1",
                "approved_by": "FINOPS-CAPACITY-20260806",
                "c_normal": 3,
                "c_peak": 6,
            }), encoding="utf-8")

            exit_code = http_slo_probe.main(
                ["--capacity-evidence", str(evidence_path), "--capacity-tier", "peak"],
                stdout=stdout,
            )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["iterations"], http_slo_probe.DEFAULT_ITERATIONS)
        self.assertEqual(report["target_concurrency"], 8)
        self.assertTrue(report["release_blocked"])

    def test_peak_capacity_cli_runs_eight_overlapping_requests(self) -> None:
        stdout = StringIO()
        active = 0
        observed_peak = 0
        lock = Lock()
        all_started = Event()

        def overlapping_request(_url, _headers, _timeout):
            nonlocal active, observed_peak
            with lock:
                active += 1
                observed_peak = max(observed_peak, active)
                if active == 8:
                    all_started.set()
            if not all_started.wait(timeout=1):
                raise AssertionError("all eight capacity requests did not overlap")
            try:
                return http_slo_probe.HttpProbeResponse(
                    status_code=200,
                    headers={"content-type": "application/json"},
                    body=b"{}",
                )
            finally:
                with lock:
                    active -= 1

        with TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "capacity.json"
            probe_path = Path(directory) / "probes.json"
            evidence_path.write_text(json.dumps({
                "mode": "capacity_contract",
                "source": "approved-visible-client-capacity",
                "contract_version": "capacity-v1",
                "approved_by": "FINOPS-CAPACITY-20260806",
                "c_normal": 3,
                "c_peak": 6,
            }), encoding="utf-8")
            probe_path.write_text(json.dumps({
                "probes": [{"name": "capacity", "path": "/api/capacity"}],
            }), encoding="utf-8")
            with patch.object(http_slo_probe, "_urllib_request", side_effect=overlapping_request):
                exit_code = http_slo_probe.main([
                    "--capacity-evidence", str(evidence_path),
                    "--capacity-tier", "peak",
                    "--iterations", "8",
                    "--warmup", "0",
                    "--replace-default-probes",
                    "--no-default-page-probe",
                    "--probe-config", str(probe_path),
                    "--allow-unauthenticated",
                ], stdout=stdout)

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(observed_peak, 8)
        self.assertEqual(report["concurrency"], report["target_concurrency"])
        self.assertEqual(report["observed_peak_concurrency"], report["target_concurrency"])
        self.assertTrue(report["capacity_concurrency_pass"])

    def test_peak_capacity_run_blocks_release_when_observed_peak_is_lower(self) -> None:
        stdout = StringIO()
        with TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "capacity.json"
            evidence_path.write_text(json.dumps({
                "mode": "capacity_contract",
                "source": "approved-visible-client-capacity",
                "contract_version": "capacity-v1",
                "approved_by": "FINOPS-CAPACITY-20260806",
                "c_normal": 3,
                "c_peak": 6,
            }), encoding="utf-8")
            with patch.object(http_slo_probe, "collect_http_slo", return_value={
                "status": "pass",
                "concurrency": 8,
                "observed_peak_concurrency": 7,
            }):
                exit_code = http_slo_probe.main([
                    "--capacity-evidence", str(evidence_path),
                    "--capacity-tier", "peak",
                    "--iterations", "8",
                ], stdout=stdout)

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["concurrency"], 8)
        self.assertEqual(report["observed_peak_concurrency"], 7)
        self.assertFalse(report["capacity_concurrency_pass"])
        self.assertTrue(report["release_blocked"])

    def test_capacity_access_evidence_requires_exact_fourteen_day_window(self) -> None:
        result = http_slo_probe.derive_capacity_targets(
            {
                "mode": "access_evidence",
                "source": "nginx_authenticated_refresh_status_access",
                "source_version": "access-log-v3",
                "source_proof": "sha256:aggregate-query",
                "window": {
                    "started_at": "2026-07-23T00:00:00+08:00",
                    "completed_at": "2026-08-05T00:00:00+08:00",
                },
                "method": "rolling_60s_unique_visible_clients",
                "rolling_60s_unique_visible_clients": [1, 2, 3],
            }
        )

        self.assertEqual(result["status"], "not_measured")
        self.assertTrue(result["release_blocked"])

    def test_capacity_access_evidence_requires_every_rolling_minute_bucket(self) -> None:
        result = http_slo_probe.derive_capacity_targets(
            {
                "mode": "access_evidence",
                "source": "nginx_authenticated_refresh_status_access",
                "source_version": "access-log-v3",
                "source_proof": "sha256:aggregate-query",
                "window": {
                    "started_at": "2026-07-22T00:00:00+08:00",
                    "completed_at": "2026-08-05T00:00:00+08:00",
                },
                "method": "rolling_60s_unique_visible_clients",
                "rolling_60s_unique_visible_clients": [1, 2, 3],
            }
        )

        self.assertEqual(result["status"], "not_measured")
        self.assertTrue(result["release_blocked"])

    def test_capacity_access_evidence_rejects_non_integer_bucket_counts(self) -> None:
        counts = [1] * 20_160
        counts[-1] = 1.5
        result = http_slo_probe.derive_capacity_targets(
            {
                "mode": "access_evidence",
                "source": "nginx_authenticated_refresh_status_access",
                "source_version": "access-log-v3",
                "source_proof": "sha256:aggregate-query",
                "window": {
                    "started_at": "2026-07-22T00:00:00+08:00",
                    "completed_at": "2026-08-05T00:00:00+08:00",
                },
                "method": "rolling_60s_unique_visible_clients",
                "rolling_60s_unique_visible_clients": counts,
            }
        )

        self.assertEqual(result["status"], "not_measured")
        self.assertTrue(result["release_blocked"])

    def test_default_probes_cover_page_domains_and_known_slow_endpoints(self) -> None:
        api_probe_names = {probe.name for probe in http_slo_probe.DEFAULT_API_PROBES}

        self.assertGreaterEqual(len(http_slo_probe.DEFAULT_PAGE_PATHS), 17)
        for path in (
            "/fin-ops/",
            "/fin-ops/bank-details",
            "/fin-ops/pending-invoices",
            "/fin-ops/input-invoice-usage",
            "/fin-ops/oa-pending-payments",
            "/fin-ops/output-invoice-collections",
            "/fin-ops/tax-offset",
            "/fin-ops/cost-statistics",
            "/fin-ops/bank-flow-rule-batches",
            "/fin-ops/batch-accounting",
            "/fin-ops/turnover-ledger",
            "/fin-ops/etc-tickets",
            "/fin-ops/imports/bank-transactions",
            "/fin-ops/imports/invoices",
            "/fin-ops/imports/etc-invoices",
            "/fin-ops/settings",
            "/fin-ops/operations/app-health",
        ):
            self.assertIn(path, http_slo_probe.DEFAULT_PAGE_PATHS)

        for name in (
            "workbench_initial_all",
            "workbench_groups_all_paired",
            "workbench_groups_all_unpaired",
            "workbench_filter_options_all_paired",
            "operations_app_health_dashboard",
            "pending_invoices_rows",
            "input_invoice_usage_rows",
            "input_invoice_usage_filter_options",
            "oa_pending_payments_rows",
            "output_invoice_collections_rows",
            "output_invoice_collections_filter_options",
            "cost_statistics_explorer_all",
            "bank_flow_rule_batches",
            "batch_accounting",
            "turnover_ledger_grouped",
            "etc_business_batches",
            "import_facts_batches",
            "workbench_settings",
            "background_jobs_active",
        ):
            self.assertIn(name, api_probe_names)
        self.assertNotIn("etc_batches", api_probe_names)
        probe_paths = {probe.name: probe.path for probe in http_slo_probe.DEFAULT_API_PROBES}
        self.assertNotIn("/api/etc/batches", "\n".join(probe_paths.values()))
        self.assertIn("date_from=", probe_paths["bank_details_transactions"])
        self.assertIn("include_statistics=false", probe_paths["cost_statistics_explorer_all"])
        self.assertIn("date_to=", probe_paths["bank_details_transactions"])
        self.assertNotIn("page=", probe_paths["workbench_groups_all_paired"])
        self.assertNotIn("page=", probe_paths["workbench_groups_all_unpaired"])
        self.assertNotIn("page=", probe_paths["workbench_filter_options_all_paired"])
        self.assertIn("page_size=50", probe_paths["workbench_groups_all_paired"])
        self.assertIn("detail_level=summary", probe_paths["workbench_groups_all_paired"])
        self.assertIn("zone=unpaired", probe_paths["workbench_groups_all_unpaired"])
        self.assertIn("page_size=50", probe_paths["workbench_groups_all_unpaired"])
        self.assertIn("detail_level=summary", probe_paths["workbench_groups_all_unpaired"])
        self.assertIn("column=applicant", probe_paths["workbench_filter_options_all_paired"])
        self.assertIn("page_size=100", probe_paths["workbench_filter_options_all_paired"])
        self.assertIn("page=1", probe_paths["pending_invoices_rows"])
        self.assertIn("page_size=50", probe_paths["pending_invoices_rows"])
        self.assertIn("include_statistics=false", probe_paths["pending_invoices_rows"])
        self.assertNotIn("pending_invoices_filter_options", probe_paths)
        self.assertIn("page=1", probe_paths["input_invoice_usage_rows"])
        self.assertIn("page_size=20", probe_paths["input_invoice_usage_rows"])
        self.assertIn("page=1", probe_paths["oa_pending_payments_rows"])
        self.assertIn("page_size=20", probe_paths["oa_pending_payments_rows"])
        self.assertIn("page=1", probe_paths["output_invoice_collections_rows"])
        self.assertIn("page_size=20", probe_paths["output_invoice_collections_rows"])
        self.assertIn("month=2026-03", probe_paths["tax_offset_rows"])
        self.assertIn("scope=2026-03", probe_paths["cost_statistics_explorer_all"])
        self.assertIn("view=time", probe_paths["cost_statistics_explorer_all"])
        self.assertIn("project_scope=active", probe_paths["cost_statistics_explorer_all"])
        self.assertIn("bucket=unsubmitted", probe_paths["bank_flow_rule_batches"])
        self.assertIn("page=1", probe_paths["bank_flow_rule_batches"])
        self.assertIn("page_size=200", probe_paths["bank_flow_rule_batches"])
        self.assertEqual(probe_paths["bank_flow_rule_batches_tag_rules"], "/api/bank-flow-rule-batches/tag-rules")
        self.assertIn("bank_year=", probe_paths["batch_accounting"])
        self.assertIn("bank_page=1", probe_paths["batch_accounting"])
        self.assertIn("bank_page_size=200", probe_paths["batch_accounting"])
        self.assertIn("oa_page=1", probe_paths["batch_accounting"])
        self.assertIn("oa_page_size=200", probe_paths["batch_accounting"])
        self.assertIn("batch_type=bank_transaction", probe_paths["import_facts_batches"])
        self.assertNotIn("search_all", probe_paths)
        self.assertNotIn("workbench_refresh_status_all", probe_paths)
        self.assertNotIn("/api/workbench/refresh-status", "\n".join(probe_paths.values()))
        admin_probe = next(probe for probe in http_slo_probe.DEFAULT_API_PROBES if probe.name == "operations_app_health_dashboard")
        self.assertEqual(admin_probe.auth_scope, "admin")

    def test_configured_default_page_probes_have_stable_page_names(self) -> None:
        args = http_slo_probe.build_parser().parse_args(["--target-ms", "5000"])

        probes = http_slo_probe._configured_probes(args)
        page_probes = [probe for probe in probes if probe.kind == "page"]

        self.assertEqual(len(page_probes), len(http_slo_probe.DEFAULT_PAGE_PATHS))
        self.assertEqual(page_probes[0].name, "page_shell_home")
        self.assertIn(
            http_slo_probe.HttpProbe(
                name="page_shell_pending_invoices",
                path="/fin-ops/pending-invoices",
                kind="page",
                expected_statuses=(200,),
                target_ms=5000.0,
            ),
            page_probes,
        )

    def test_public_page_shell_smoke_args_exclude_default_api_probes(self) -> None:
        args = http_slo_probe.build_parser().parse_args(
            [
                "--allow-unauthenticated",
                "--replace-default-probes",
                "--iterations",
                "3",
                "--target-ms",
                "1000",
            ]
        )

        probes = http_slo_probe._configured_probes(args)

        self.assertTrue(args.allow_unauthenticated)
        self.assertEqual(len(probes), len(http_slo_probe.DEFAULT_PAGE_PATHS))
        self.assertTrue(all(probe.kind == "page" for probe in probes))
        self.assertTrue(all(probe.expected_statuses == (200,) for probe in probes))
        self.assertTrue(all(probe.target_ms == 1000.0 for probe in probes))
        default_api_names = {probe.name for probe in http_slo_probe.DEFAULT_API_PROBES}
        self.assertFalse(default_api_names.intersection({probe.name for probe in probes}))

    def test_requires_auth_by_default_without_sampling(self) -> None:
        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("session", "/api/session/me")],
            headers={},
        )

        self.assertEqual(report["status"], "auth_missing")
        self.assertFalse(report["auth_configured"])

    def test_collects_samples_with_api_prefix_without_leaking_auth(self) -> None:
        observed: list[tuple[str, dict[str, str]]] = []

        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            observed.append((url, dict(headers)))
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"read_model_status": "fresh", "cache_status": "fresh"}).encode("utf-8"),
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            probes=[http_slo_probe.HttpProbe("workbench", "/api/workbench?month=all")],
            headers={"Authorization": "Bearer secret-token"},
            iterations=2,
            warmup=1,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["sample_count"], 2)
        self.assertEqual(observed[0][0], "https://example.test/fin-ops-api/api/workbench?month=all")
        self.assertEqual(observed[0][1]["Accept-Encoding"], "gzip")
        self.assertTrue(report["auth_configured"])
        self.assertNotIn("secret-token", json.dumps(report))
        self.assertEqual(report["probes"][0]["read_model_statuses"], {"fresh": 2})
        self.assertEqual(report["probes"][0]["cache_statuses"], {"fresh": 2})

    def test_collects_measured_requests_with_bounded_concurrency_and_response_sizes(self) -> None:
        lock = Lock()
        active = 0
        peak_active = 0

        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
            sleep(0.01)
            with lock:
                active -= 1
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"status":"ok"}',
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("session", "/api/session/me")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=6,
            warmup=1,
            concurrency=3,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["concurrency"], 3)
        self.assertEqual(report["summary"]["sample_count"], 6)
        self.assertEqual(report["summary"]["response_bytes_total"], 90)
        self.assertEqual(report["summary"]["request_count"], 6)
        self.assertEqual(report["summary"]["error_count"], 0)
        self.assertEqual(report["probes"][0]["request_count"], 6)
        self.assertEqual(report["probes"][0]["error_count"], 0)
        self.assertEqual(report["probes"][0]["error_counts"], {})
        self.assertEqual(report["probes"][0]["response_bytes"]["p95"], 15.0)
        self.assertEqual(peak_active, 3)

    def test_concurrency_is_capped_at_the_supported_peak_gate(self) -> None:
        active = 0
        peak_active = 0
        lock = Lock()

        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
            sleep(0.02)
            with lock:
                active -= 1
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b"{}",
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("session", "/api/session/me")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=16,
            warmup=0,
            concurrency=64,
            request_fn=request_fn,
        )

        self.assertEqual(report["concurrency"], 8)
        self.assertLessEqual(peak_active, 8)

    def test_error_distribution_and_evidence_window_are_reported_without_payloads(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=503,
                headers={"content-type": "application/json"},
                body=b'{"error":"database_backpressure","secret":"must-not-be-reported"}',
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("session", "/api/session/me")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=2,
            warmup=0,
            evidence_environment="current-production",
            request_fn=request_fn,
        )

        self.assertEqual(report["evidence_environment"], "current-production")
        self.assertLessEqual(report["evidence_window"]["started_at"], report["evidence_window"]["completed_at"])
        self.assertEqual(report["summary"]["request_count"], 2)
        self.assertEqual(report["summary"]["error_count"], 2)
        self.assertEqual(report["probes"][0]["error_counts"], {"unexpected_status:503": 2})
        self.assertNotIn("must-not-be-reported", json.dumps(report))

    def test_gzip_json_response_is_decoded_for_metadata(self) -> None:
        payload = gzip.compress(b'{"read_model_status":"fresh","cache_status":"fresh"}')

        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json", "content-encoding": "gzip"},
                body=payload,
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("workbench", "/api/workbench?month=all")],
            headers={"Authorization": "Bearer secret-token"},
            iterations=1,
            warmup=0,
            request_fn=request_fn,
            include_samples=True,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["probes"][0]["read_model_statuses"], {"fresh": 1})
        self.assertEqual(report["probes"][0]["cache_statuses"], {"fresh": 1})
        self.assertEqual(report["samples"][0]["response_bytes"], len(payload))

    def test_admin_scoped_probe_uses_admin_headers_without_overriding_user_probes(self) -> None:
        observed: list[tuple[str, dict[str, str]]] = []

        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            observed.append((url, dict(headers)))
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"read_model_status":"fresh"}',
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[
                http_slo_probe.HttpProbe("session", "/api/session/me"),
                http_slo_probe.HttpProbe("operations", "/api/operations/app-health-dashboard", auth_scope="admin"),
            ],
            headers={"Authorization": "Bearer user-token"},
            admin_headers={"Authorization": "Bearer admin-token", "Cookie": "Admin-Token=admin-token"},
            iterations=1,
            warmup=0,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(observed[0][1]["Authorization"], "Bearer user-token")
        self.assertEqual(observed[1][1]["Authorization"], "Bearer admin-token")
        self.assertEqual(observed[1][1]["Cookie"], "Admin-Token=admin-token")

    def test_plain_status_field_does_not_count_as_read_model_status(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"status":"ok"}',
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("session", "/api/session/me")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=1,
            warmup=0,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["probes"][0]["read_model_statuses"], {})

    def test_probe_fails_when_p95_passes_but_p99_exceeds_ceiling(self) -> None:
        probe = http_slo_probe.HttpProbe("tail_latency", "/api/tail-latency")
        samples = [
            http_slo_probe.HttpProbeSample(
                name=probe.name,
                path=probe.path,
                url=f"https://example.test{probe.path}",
                kind=probe.kind,
                iteration=index + 1,
                warmup=False,
                elapsed_ms=1.0 if index < 95 else 3_000.0,
                status_code=200,
                response_bytes=2,
                content_type="application/json",
                ok=True,
            )
            for index in range(100)
        ]

        summary = http_slo_probe._summarize_probe(probe, samples)

        self.assertEqual(summary["duration_ms"]["p95"], 1.0)
        self.assertEqual(summary["duration_ms"]["p99"], 3_000.0)
        self.assertTrue(summary["p95_pass"])
        self.assertFalse(summary["p99_pass"])
        self.assertFalse(summary["slo_pass"])
        self.assertEqual(summary["status"], "fail")

    def test_non_fresh_read_model_or_refresh_enqueue_fails_probe(self) -> None:
        responses = [
            {"read_model_status": "missing", "refresh_enqueued": True},
            {"read_model_status": "fresh", "refresh_enqueued": False},
        ]

        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            payload = responses.pop(0)
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(payload).encode("utf-8"),
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("no_oa", "/api/no-oa-bank-batches")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=2,
            warmup=0,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["probes"][0]["freshness_pass"])
        self.assertEqual(report["probes"][0]["non_fresh_read_model_statuses"], {"missing": 1})
        self.assertEqual(report["probes"][0]["refresh_enqueued_count"], 1)

    def test_unexpected_status_fails_probe(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=401,
                headers={"content-type": "application/json"},
                body=b'{"error":"invalid_oa_session"}',
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("session", "/api/session/me")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=1,
            warmup=0,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["probes"][0]["status_counts"], {"401": 1})
        self.assertEqual(report["probes"][0]["errors"], ["unexpected_status:401"])

    def test_api_probe_rejects_html_shell_response(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=b"<!doctype html><html><body>fin ops</body></html>",
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            api_prefix="/wrong-prefix",
            probes=[http_slo_probe.HttpProbe("ready", "/api/health/ready")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=1,
            warmup=0,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["probes"][0]["success_count"], 0)
        self.assertEqual(report["probes"][0]["errors"], ["html_response_for_api_probe"])

    def test_unexpected_html_status_keeps_status_error(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=401,
                headers={"content-type": "text/html; charset=utf-8"},
                body=b"<!doctype html><html><body>login</body></html>",
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("session", "/api/session/me")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=1,
            warmup=0,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["probes"][0]["status_counts"], {"401": 1})
        self.assertEqual(report["probes"][0]["errors"], ["unexpected_status:401"])

    def test_page_probe_allows_html_shell_response(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=b"<!doctype html><html><body>fin ops</body></html>",
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("home", "/fin-ops/", kind="page")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=1,
            warmup=0,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["probes"][0]["success_count"], 1)
        self.assertEqual(report["probes"][0]["errors"], [])

    def test_cli_auth_missing_exit_code(self) -> None:
        from io import StringIO

        stdout = StringIO()
        exit_code = http_slo_probe.main(
            ["--base-url", "https://example.test", "--iterations", "1"],
            stdout=stdout,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "auth_missing")


if __name__ == "__main__":
    unittest.main()
