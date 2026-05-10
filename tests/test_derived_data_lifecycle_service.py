import json
import unittest

from fin_ops_platform.services.derived_data_lifecycle_service import (
    DERIVED_DATA_DOMAINS,
    DERIVED_DATA_EVENTS,
    PROTECTED_TARGETS,
    DerivedDataLifecycleService,
)


class DerivedDataLifecycleServiceTests(unittest.TestCase):
    def test_invoice_import_confirmed_maps_workbench_candidate_tax_cost_and_search_domains(self) -> None:
        service = DerivedDataLifecycleService()

        plan = service.plan_event("invoice_import_confirmed", months=["2026-03"])

        self.assertEqual(plan["event"], "invoice_import_confirmed")
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["affected_scopes"], ["2026-03", "all"])
        self.assertEqual(
            [domain["domain"] for domain in plan["domains"]],
            [
                "workbench_read_model",
                "workbench_matching_dirty_scopes",
                "tax_offset_read_model",
                "tax_offset_month_cache",
                "cost_statistics_read_model",
                "search_cache",
            ],
        )
        self.assertEqual(plan["protected_targets"], list(PROTECTED_TARGETS))
        self.assertIn("workbench_matching", plan["will_enqueue_jobs"])
        self.assertIn("cost_statistics_cache_warmup", plan["will_enqueue_jobs"])
        json.dumps(plan)

    def test_bank_import_confirmed_maps_workbench_candidate_cost_and_search_domains(self) -> None:
        service = DerivedDataLifecycleService()

        plan = service.plan_event("bank_import_confirmed", months=["2026-03"])

        self.assertEqual(plan["affected_scopes"], ["2026-03", "all"])
        self.assertEqual(
            [domain["domain"] for domain in plan["domains"]],
            [
                "workbench_read_model",
                "workbench_matching_dirty_scopes",
                "cost_statistics_read_model",
                "search_cache",
            ],
        )
        self.assertNotIn("tax_offset_read_model", [domain["domain"] for domain in plan["domains"]])

    def test_oa_rebuilt_maps_oa_workbench_candidate_tax_cost_and_historical_reconcile_domains(self) -> None:
        service = DerivedDataLifecycleService()

        plan = service.plan_event("oa_rebuilt", months=["2026-03"])

        self.assertEqual(plan["affected_scopes"], ["2026-03", "all"])
        self.assertEqual(
            [domain["domain"] for domain in plan["domains"]],
            [
                "oa_adapter_records_cache",
                "workbench_read_model",
                "workbench_matching_dirty_scopes",
                "tax_offset_read_model",
                "tax_offset_month_cache",
                "cost_statistics_read_model",
                "historical_etc_repair_state",
                "search_cache",
            ],
        )
        self.assertIn("historical_etc_reconcile", plan["will_enqueue_jobs"])

    def test_manual_cleanup_dry_run_is_json_serializable_and_does_not_plan_protected_deletes(self) -> None:
        service = DerivedDataLifecycleService()

        plan = service.plan_event(
            "manual_derived_cache_cleanup",
            scope_keys=["workbench:2026-03", "import-session:old"],
            include_all=False,
            metadata={"operator": "finance-admin"},
        )

        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["affected_scopes"], ["workbench:2026-03", "import-session:old"])
        self.assertEqual(
            [domain["domain"] for domain in plan["domains"]],
            list(DERIVED_DATA_DOMAINS),
        )
        planned_delete_targets = {
            target
            for domain in plan["domains"]
            for target in domain.get("delete_targets", [])
        }
        self.assertTrue(planned_delete_targets.isdisjoint(PROTECTED_TARGETS))
        json.dumps(plan)

    def test_execute_plan_calls_executors_and_aggregates_summary(self) -> None:
        service = DerivedDataLifecycleService()
        plan = service.plan_event(
            "invoice_import_confirmed",
            months=["2026-03"],
            dry_run=False,
        )
        calls: list[tuple[str, list[str], bool]] = []

        def workbench_executor(domain_plan: dict) -> dict:
            calls.append((domain_plan["domain"], domain_plan["scope_keys"], domain_plan["dry_run"]))
            return {
                "deleted_counts": {"workbench_read_models": 2},
                "invalidated_scopes": ["2026-03", "all"],
                "enqueued_jobs": ["workbench_matching:2026-03"],
            }

        def search_executor(domain_plan: dict) -> dict:
            calls.append((domain_plan["domain"], domain_plan["scope_keys"], domain_plan["dry_run"]))
            return {
                "deleted_count": 1,
                "invalidated_scopes": ["search:all"],
            }

        summary = service.execute_plan(
            plan,
            executors={
                "workbench_read_model": workbench_executor,
                "search_cache": search_executor,
            },
        )

        self.assertFalse(summary["dry_run"])
        self.assertEqual(summary["deleted_counts"]["workbench_read_models"], 2)
        self.assertEqual(summary["deleted_counts"]["search_cache"], 1)
        self.assertEqual(summary["invalidated_scopes"], ["2026-03", "all", "search:all"])
        self.assertEqual(summary["enqueued_jobs"], ["workbench_matching:2026-03"])
        self.assertIn("cost_statistics_read_model", summary["skipped"])
        self.assertEqual(summary["errors"], [])
        self.assertGreaterEqual(summary["duration_ms"], 0)
        self.assertIn(("workbench_read_model", ["2026-03", "all"], False), calls)
        json.dumps(summary)

    def test_unknown_event_fails_fast(self) -> None:
        service = DerivedDataLifecycleService()

        with self.assertRaises(ValueError):
            service.plan_event("unknown_event")

    def test_declares_required_events_and_domains(self) -> None:
        self.assertEqual(
            DERIVED_DATA_EVENTS,
            (
                "invoice_import_confirmed",
                "bank_import_confirmed",
                "etc_import_confirmed",
                "etc_oa_submitted",
                "etc_oa_revoked",
                "oa_rebuilt",
                "oa_attachment_invoice_cache_updated",
                "pair_relation_changed",
                "exception_case_changed",
                "settings_reset_completed",
                "project_scope_changed",
                "manual_derived_cache_cleanup",
                "startup_stale_scan",
            ),
        )
        self.assertEqual(
            DERIVED_DATA_DOMAINS,
            (
                "workbench_read_model",
                "workbench_candidate_matches",
                "workbench_matching_dirty_scopes",
                "cost_statistics_read_model",
                "tax_offset_read_model",
                "tax_offset_month_cache",
                "search_cache",
                "oa_adapter_records_cache",
                "file_import_sessions",
                "tax_certified_import_sessions",
                "background_jobs",
                "historical_etc_repair_state",
            ),
        )


if __name__ == "__main__":
    unittest.main()
