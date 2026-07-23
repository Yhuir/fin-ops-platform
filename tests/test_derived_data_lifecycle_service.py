import json
import unittest

from fin_ops_platform.services.derived_data_lifecycle_service import (
    DERIVED_DATA_EVENTS,
    PROTECTED_TARGETS,
    DerivedDataLifecycleService,
)


class DerivedDataLifecycleServiceTests(unittest.TestCase):
    def test_only_explicit_maintenance_events_are_registered(self) -> None:
        self.assertEqual(
            DERIVED_DATA_EVENTS,
            ("etc_business_batch_changed", "settings_reset_completed"),
        )

    def test_historical_etc_repair_can_target_exact_months(self) -> None:
        service = DerivedDataLifecycleService()

        plan = service.plan_event(
            "etc_business_batch_changed",
            months=["2026-03", "2026-04"],
            include_all=False,
        )

        self.assertEqual(plan["affected_scopes"], ["2026-03", "2026-04"])
        domains = [domain["domain"] for domain in plan["domains"]]
        self.assertIn("historical_etc_repair_state", domains)
        self.assertIn("workbench_read_model", domains)
        self.assertIn("tax_offset_read_model", domains)
        self.assertNotIn("all", plan["affected_scopes"])

    def test_settings_reset_is_explicit_full_history_maintenance(self) -> None:
        service = DerivedDataLifecycleService()

        plan = service.plan_event("settings_reset_completed", include_all=True)

        self.assertEqual(plan["affected_scopes"], ["all"])
        domains = [domain["domain"] for domain in plan["domains"]]
        self.assertIn("oa_adapter_records_cache", domains)
        self.assertIn("bank_account_balance_read_model", domains)
        self.assertIn("file_import_sessions", domains)
        self.assertIn("historical_etc_repair_state", domains)

    def test_ordinary_write_events_fail_fast(self) -> None:
        service = DerivedDataLifecycleService()

        for event in (
            "import_state_changed",
            "pair_relation_changed",
            "bank_transaction_category_changed",
            "bank_auto_tag_rules_changed",
            "pending_invoice_rules_changed",
            "bank_flow_rule_batch_changed",
        ):
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, "Unsupported"):
                service.plan_event(event, months=["2026-03"])

    def test_execute_plan_calls_only_registered_domain_executors(self) -> None:
        service = DerivedDataLifecycleService()
        plan = service.plan_event(
            "etc_business_batch_changed",
            months=["2026-03"],
            include_all=False,
            dry_run=False,
        )

        summary = service.execute_plan(
            plan,
            executors={
                "workbench_read_model": lambda domain_plan: {
                    "deleted_counts": {"workbench_read_models": 1},
                    "invalidated_scopes": domain_plan["scope_keys"],
                },
                "search_cache": lambda domain_plan: {
                    "deleted_count": 1,
                    "invalidated_scopes": ["search:2026-03"],
                },
            },
        )

        self.assertEqual(summary["deleted_counts"]["workbench_read_models"], 1)
        self.assertEqual(summary["deleted_counts"]["search_cache"], 1)
        self.assertEqual(summary["invalidated_scopes"], ["2026-03", "search:2026-03"])
        self.assertEqual(summary["errors"], [])
        json.dumps(summary)

    def test_plans_never_delete_protected_targets(self) -> None:
        service = DerivedDataLifecycleService()

        for event in DERIVED_DATA_EVENTS:
            with self.subTest(event=event):
                plan = service.plan_event(event, months=["2026-03"], metadata={"source": "test"})
                delete_targets = {
                    target
                    for domain in plan["domains"]
                    for target in domain.get("delete_targets", [])
                }
                self.assertTrue(delete_targets.isdisjoint(PROTECTED_TARGETS))
                json.dumps(plan)


if __name__ == "__main__":
    unittest.main()
