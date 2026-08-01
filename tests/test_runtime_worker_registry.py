from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import unittest

from fin_ops_platform.app import worker as worker_app
from fin_ops_platform.tools import runtime_worker_manifest
from fin_ops_platform.services.rabbitmq_runtime import SUPPORTED_EVENT_TYPES
from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.runtime_monitoring import READ_MODEL_EVENT_TYPES
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES
from fin_ops_platform.services.runtime_worker_registry import (
    rabbitmq_dispatch_event_types,
    read_model_event_types,
    registration_by_instance_name,
    required_worker_instance_names,
    worker_check_command_args,
    worker_claim_event_types,
    worker_command_args,
    worker_registrations,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ENSURE_WORKERS_SCRIPT = REPO_ROOT / "deploy/oa/bin/finops-ensure-runtime-workers.sh"
ENV_DIR = REPO_ROOT / "deploy/oa/env"
DISPATCHER_ENV = ENV_DIR / "fin-ops.rabbitmq-dispatcher.env.example"


class RuntimeWorkerRegistryTests(unittest.TestCase):
    def test_direct_canonical_page_workers_are_retired_but_workbench_remains(self) -> None:
        registrations = registration_by_instance_name()

        for instance_name in (
            "bank-detail",
            "bank-account-balance",
            "pending-invoice",
            "invoice-lifecycle",
            "invoice-lifecycle-secondary",
            "invoice-usage-collection",
            "oa-pending-payment",
            "cost-tax",
            "tax-offset",
            "bank-flow-rule-batch",
        ):
            self.assertNotIn(instance_name, registrations)

        self.assertEqual(registrations["workbench"].event_types, ("workbench.read_model.refresh",))
        self.assertNotIn("workbench-secondary", registrations)

    def test_required_workers_match_deploy_helper_defaults(self) -> None:
        script = ENSURE_WORKERS_SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(script, r"required_workers=\"\\$\\{FINOPS_REQUIRED_WORKERS:-")
        self.assertIn("runtime_worker_manifest --required-instances", script)

    def test_required_workers_have_env_examples_and_heartbeat_slos(self) -> None:
        for registration in worker_registrations(required_only=True):
            self.assertTrue(registration.worker_kind)
            self.assertGreater(registration.heartbeat_stale_after_seconds, 0)
            self.assertTrue((ENV_DIR / registration.env_example).exists(), registration.env_example)
            self.assertTrue(registration.handler_flags or registration.event_types)

    def test_registered_worker_env_examples_exist(self) -> None:
        for registration in worker_registrations():
            self.assertTrue((ENV_DIR / registration.env_example).exists(), registration.env_example)
            if registration.rabbitmq_env_example:
                self.assertTrue((ENV_DIR / registration.rabbitmq_env_example).exists(), registration.rabbitmq_env_example)

    def test_rabbitmq_supported_and_default_dispatch_events_are_registry_derived(self) -> None:
        registry_events = rabbitmq_dispatch_event_types()

        self.assertEqual(DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, registry_events)
        self.assertEqual(SUPPORTED_EVENT_TYPES, registry_events)

    def test_rabbitmq_dispatcher_env_example_covers_registry_events(self) -> None:
        dispatcher_env = DISPATCHER_ENV.read_text(encoding="utf-8")

        for event_type in rabbitmq_dispatch_event_types():
            self.assertIn(event_type, dispatcher_env)

    def test_registration_lookup_and_command_args_are_registry_derived(self) -> None:
        registration = registration_by_instance_name()["workbench-relation"]

        self.assertEqual(
            worker_command_args(registration, transport="postgres"),
            (
                "--enable-workbench-relation-read-model-refresh",
                "--event-type",
                "workbench_relation.read_model.refresh",
            ),
        )
        self.assertEqual(
            worker_check_command_args(registration, transport="postgres"),
            (
                "--registration",
                "workbench-relation",
                "--worker-instance",
                "workbench-relation",
                "--check",
            ),
        )

    def test_workbench_page_and_relation_distribution_workers_are_retained(self) -> None:
        registrations = registration_by_instance_name()
        workbench = registrations["workbench"]
        workbench_relation = registrations["workbench-relation"]

        self.assertEqual(workbench.event_types, ("workbench.read_model.refresh",))
        self.assertEqual(workbench.worker_kind, "workbench-read-model")
        self.assertEqual(workbench_relation.event_types, ("workbench_relation.read_model.refresh",))
        self.assertEqual(workbench_relation.worker_kind, "workbench-relation-read-model")
        self.assertEqual(
            worker_command_args(workbench_relation, transport="postgres"),
            (
                "--enable-workbench-relation-read-model-refresh",
                "--event-type",
                "workbench_relation.read_model.refresh",
            ),
        )

    def test_retired_search_and_no_oa_derived_workers_are_absent(self) -> None:
        registrations = registration_by_instance_name()
        self.assertEqual(
            tuple(registrations),
            (
                "oa-sync",
                "workbench-matching",
                "workbench",
                "workbench-relation",
                "import",
                "settings-maintenance",
            ),
        )
        for instance_name in (
            "workbench-secondary",
            "search",
            "search-secondary",
            "search-tertiary",
            "no-oa-bank-batch",
        ):
            self.assertNotIn(instance_name, registrations)
        self.assertNotIn("search", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("no_oa_bank_batch", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("search.read_model.refresh", rabbitmq_dispatch_event_types())
        self.assertNotIn("no_oa_bank_batch.read_model.refresh", rabbitmq_dispatch_event_types())
        self.assertNotIn("pending_invoice", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("tax_offset", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("bank_flow_rule_batch", APP_STATUS_READ_MODEL_REGISTRY)
        self.assertNotIn("cost-statistics", registrations)
        self.assertNotIn("cost-statistics-secondary", registrations)
        self.assertNotIn("cost_statistics", APP_STATUS_READ_MODEL_REGISTRY)

    def test_cost_and_tax_page_workers_are_retired(self) -> None:
        registrations = registration_by_instance_name()
        self.assertNotIn("cost-tax", registrations)
        self.assertNotIn("tax-offset", registrations)
        self.assertNotIn("cost_statistics.read_model.refresh", rabbitmq_dispatch_event_types())
        self.assertNotIn("tax_offset.read_model.refresh", rabbitmq_dispatch_event_types())

    def test_import_claim_events_exclude_deleted_fact_changed_bridge(self) -> None:
        registration = registration_by_instance_name()["import"]

        self.assertEqual(
            worker_claim_event_types(registration, transport="postgres"),
            ("import.process.requested",),
        )
        self.assertEqual(
            worker_claim_event_types(registration, transport="rabbitmq"),
            ("import.process.requested",),
        )
        self.assertIn("import.process.requested", rabbitmq_dispatch_event_types())
        self.assertNotIn("import.fact.changed", rabbitmq_dispatch_event_types())

    def test_read_model_monitoring_events_are_covered_by_registry(self) -> None:
        registry_events = set(rabbitmq_dispatch_event_types())

        self.assertLessEqual(set(READ_MODEL_EVENT_TYPES), registry_events)

    def test_app_status_read_model_registry_matches_worker_and_rabbitmq_contracts(self) -> None:
        registrations = registration_by_instance_name()
        read_model_events = read_model_event_types()
        dispatch_events = set(rabbitmq_dispatch_event_types())

        for read_model_key, definition in APP_STATUS_READ_MODEL_REGISTRY.items():
            with self.subTest(read_model_key=read_model_key):
                self.assertIn(definition.worker_instance, registrations)
                registration = registrations[definition.worker_instance]
                self.assertTrue(registration.required)
                self.assertIn(definition.refresh_event_type, registration.event_types)
                self.assertIn(definition.refresh_event_type, dispatch_events)
                self.assertEqual(
                    read_model_events.get(definition.refresh_event_type),
                    (definition.key, definition.scope_type),
                )

    def test_worker_read_model_registrations_are_visible_to_app_status_registry(self) -> None:
        for event_type, (read_model_key, scope_type) in read_model_event_types().items():
            with self.subTest(event_type=event_type):
                self.assertIn(read_model_key, APP_STATUS_READ_MODEL_REGISTRY)
                definition = APP_STATUS_READ_MODEL_REGISTRY[read_model_key]
                self.assertEqual(definition.scope_type, scope_type)
                self.assertEqual(definition.refresh_event_type, event_type)

    def test_retired_worker_flags_are_not_accepted(self) -> None:
        for retired_flag in (
            "--enable-bank-account-balance-read-model-refresh",
            "--enable-bank-flow-rule-batch-canonical-draft-refresh",
            "--enable-search-read-model-refresh",
            "--enable-no-oa-bank-batch-read-model-refresh",
        ):
            with self.subTest(retired_flag=retired_flag), self.assertRaises(SystemExit):
                worker_app.build_parser().parse_args([retired_flag])

    def test_turnover_ledger_worker_registration_is_removed(self) -> None:
        self.assertNotIn("turnover-ledger", registration_by_instance_name())
        self.assertNotIn("turnover_ledger.read_model.refresh", read_model_event_types())

    def test_worker_registration_check_outputs_registry_derived_configuration(self) -> None:
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = worker_app.main(
                [
                    "--registration",
                    "workbench-relation",
                    "--worker-instance",
                    "workbench-relation",
                    "--check",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["worker_instance"], "workbench-relation")
        self.assertEqual(payload["worker_kind"], "workbench-relation-read-model")
        self.assertEqual(payload["event_types"], ["workbench_relation.read_model.refresh"])
        self.assertEqual(payload["handlers"], ["workbench_relation.read_model.refresh"])
        self.assertEqual(payload["registration"]["instance_name"], "workbench-relation")
        self.assertEqual(payload["registration"]["exclude_claim_scope_keys"], [])

    def test_unknown_worker_registration_fails_fast(self) -> None:
        with self.assertRaises(SystemExit):
            worker_app.main(["--registration", "missing-worker", "--check"])

    def test_manifest_cli_lists_required_instances_and_env_examples(self) -> None:
        stdout = io.StringIO()

        exit_code = runtime_worker_manifest.main(["--instances"], stdout=stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            tuple(stdout.getvalue().split()),
            tuple(registration.instance_name for registration in worker_registrations()),
        )

        stdout = io.StringIO()

        exit_code = runtime_worker_manifest.main(["--required-instances"], stdout=stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(tuple(stdout.getvalue().split()), required_worker_instance_names())

        stdout = io.StringIO()
        exit_code = runtime_worker_manifest.main(["--rabbitmq-required-instances"], stdout=stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            tuple(stdout.getvalue().split()),
            tuple(
                registration.instance_name
                for registration in worker_registrations(required_only=True, rabbitmq_eligible_only=True)
            ),
        )

        stdout = io.StringIO()
        exit_code = runtime_worker_manifest.main(["--rabbitmq-dispatch-event-types"], stdout=stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(tuple(stdout.getvalue().split()), rabbitmq_dispatch_event_types())

        stdout = io.StringIO()
        exit_code = runtime_worker_manifest.main(
            ["--env-example", "workbench-relation"],
            stdout=stdout,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stdout.getvalue().strip(),
            "fin-ops.worker.workbench-relation.env.example",
        )


if __name__ == "__main__":
    unittest.main()
