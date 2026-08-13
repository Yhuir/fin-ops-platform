from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.runtime_worker_registry import RUNTIME_WORKER_REGISTRY


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_CONTROL = REPO_ROOT / "deploy/oa/bin/finops-deploy-control.sh"
ENSURE_RUNTIME_WORKERS = REPO_ROOT / "deploy/oa/bin/finops-ensure-runtime-workers.sh"
WORKER_SERVICE = REPO_ROOT / "deploy/oa/systemd/fin-ops-worker@.service.example"
DISPATCHER_SERVICE = REPO_ROOT / "deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example"
RUNTIME_QUEUE_PRUNE_SERVICE = REPO_ROOT / "deploy/oa/systemd/finops-prune-runtime-queue-history.service.example"
RUNTIME_QUEUE_PRUNE_TIMER = REPO_ROOT / "deploy/oa/systemd/finops-prune-runtime-queue-history.timer.example"
OA_SYNC_ENQUEUE_SERVICE = REPO_ROOT / "deploy/oa/systemd/finops-enqueue-oa-sync.service.example"
OA_SYNC_ENQUEUE_TIMER = REPO_ROOT / "deploy/oa/systemd/finops-enqueue-oa-sync.timer.example"
DISPATCHER_ENV = REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example"
RABBITMQ_WORKER_ENV = REPO_ROOT / "deploy/oa/env/fin-ops.rabbitmq-worker.env.example"
COMMON_ENV = REPO_ROOT / "deploy/oa/env/fin-ops.common.env.example"
WORKER_ENV_DIR = REPO_ROOT / "deploy/oa/env"
DEPLOYMENT_DOC = REPO_ROOT / "docs/operations/deployment.md"
OA_DEPLOY_README = REPO_ROOT / "deploy/oa/README.md"
RUNTIME_QUEUE_PRUNE_HELPER = REPO_ROOT / "deploy/oa/bin/finops-prune-runtime-queue-history.sh"
OA_SYNC_ENQUEUE_HELPER = REPO_ROOT / "deploy/oa/bin/finops-enqueue-oa-sync.sh"
WORKBENCH_GENERATION_PRUNE_HELPER = REPO_ROOT / "deploy/oa/bin/finops-prune-workbench-generations.sh"
WORKBENCH_GENERATION_PRUNE_SERVICE = REPO_ROOT / "deploy/oa/systemd/finops-prune-workbench-generations.service.example"
WORKBENCH_GENERATION_PRUNE_TIMER = REPO_ROOT / "deploy/oa/systemd/finops-prune-workbench-generations.timer.example"


class DeployRuntimeExampleTests(unittest.TestCase):
    def test_rabbitmq_dispatcher_systemd_uses_env_allowlist_for_all_runtime_events(self) -> None:
        service = DISPATCHER_SERVICE.read_text()

        self.assertNotIn("--event-type", service)
        self.assertIn(
            "RABBITMQ_DISPATCH_EVENT_TYPES",
            DISPATCHER_ENV.read_text(),
        )

    def test_rabbitmq_dispatcher_poll_interval_is_env_controlled_and_fast_by_default(self) -> None:
        service = DISPATCHER_SERVICE.read_text()
        env_example = DISPATCHER_ENV.read_text()
        deploy_control = DEPLOY_CONTROL.read_text()

        self.assertIn("RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.05", env_example)
        self.assertIn("Environment=RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.05", service)
        self.assertIn("--poll-interval-seconds ${RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS}", service)
        self.assertIn("Environment=RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.05", deploy_control)
        self.assertIn("--poll-interval-seconds \\${RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS}", deploy_control)
        self.assertNotIn("--poll-interval-seconds 5", service)
        self.assertNotIn("--poll-interval-seconds 5", deploy_control)

    def test_deploy_control_worker_dropin_preserves_per_worker_throughput_env(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text()
        worker_service = WORKER_SERVICE.read_text()

        self.assertIn("--max-events-per-iteration \\${FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION}", deploy_control)
        self.assertIn(
            "--dependency-not-fresh-delay-seconds \\${FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS}",
            deploy_control,
        )
        self.assertNotIn("Environment=FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=1", deploy_control)
        self.assertIn("--max-events-per-iteration ${FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION}", worker_service)
        self.assertIn(
            "--dependency-not-fresh-delay-seconds ${FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS}",
            worker_service,
        )
        self.assertNotIn("Environment=FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=1", worker_service)

    def test_systemd_examples_do_not_pin_retired_current_backend_path(self) -> None:
        systemd_examples = sorted((REPO_ROOT / "deploy/oa/systemd").glob("*.service.example"))
        violations = [
            example.name
            for example in systemd_examples
            if "/opt/fin-ops/current/backend" in example.read_text(encoding="utf-8")
        ]

        self.assertEqual([], violations)

    def test_required_worker_env_examples_define_max_events_per_iteration(self) -> None:
        missing_examples: list[str] = []
        for registration in RUNTIME_WORKER_REGISTRY:
            if not registration.required or not registration.env_example:
                continue
            env_example = WORKER_ENV_DIR / registration.env_example
            content = env_example.read_text(encoding="utf-8")
            if "FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=" not in content:
                missing_examples.append(registration.env_example)

        self.assertEqual([], missing_examples)

    def test_runtime_env_examples_pin_standard_write_operation_smoke_inputs(self) -> None:
        content = COMMON_ENV.read_text(encoding="utf-8")

        self.assertIn(
            "FIN_OPS_WRITE_E2E_SCENARIO=/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json",
            content,
        )
        self.assertIn(
            "FIN_OPS_WRITE_E2E_APPROVAL_TICKET=FINOPS-WRITE-SMOKE-STANDING-20260702",
            content,
        )

    def test_required_worker_env_examples_do_not_pin_legacy_slow_poll_interval(self) -> None:
        slow_examples: list[str] = []
        for registration in RUNTIME_WORKER_REGISTRY:
            if not registration.required or not registration.env_example:
                continue
            env_example = WORKER_ENV_DIR / registration.env_example
            content = env_example.read_text(encoding="utf-8")
            if "--poll-interval-seconds 2" in content:
                slow_examples.append(registration.env_example)
            if registration.instance_name != "workbench-matching" and "--poll-interval-seconds 0.1" in content:
                slow_examples.append(registration.env_example)
            if registration.instance_name != "workbench-matching" and "--poll-interval-seconds 5" in content:
                slow_examples.append(registration.env_example)

        self.assertEqual([], slow_examples)

    def test_runtime_worker_env_install_uses_only_registered_worker_examples(self) -> None:
        helper = ENSURE_RUNTIME_WORKERS.read_text(encoding="utf-8")

        self.assertIn("install_if_missing", helper)
        self.assertIn("migrate_legacy_worker_poll_interval", helper)
        self.assertNotIn("migrate_workbench_aggregate_drain", helper)
        self.assertIn('source_poll="$(grep -oE -- "--poll-interval-seconds [0-9.]+"', helper)
        self.assertIn("--poll-interval-seconds (2|0\\\\.25|0\\\\.1|0\\\\.05)([^0-9.]|$)", helper)
        self.assertIn("--poll-interval-seconds ${source_poll}", helper)
        self.assertIn('[ "$worker" = "workbench-matching" ]', helper)
        self.assertIn("--poll-interval-seconds 5([^0-9.]|$)", helper)
        self.assertIn('required_existing_worker_envs="${FINOPS_REQUIRE_EXISTING_WORKER_ENVS:-}"', helper)
        self.assertIn("worker_env_must_already_exist", helper)
        self.assertIn('[[ " $required_existing_worker_envs " == *" $worker "* ]]', helper)
        self.assertIn("required existing worker env is missing or not a regular file", helper)
        self.assertIn('if ! worker_env_must_already_exist "$worker"; then', helper)
        self.assertFalse((WORKER_ENV_DIR / "fin-ops.worker.workbench.env.example").exists())

    def test_bank_flow_draft_worker_runtime_is_absent(self) -> None:
        helper = ENSURE_RUNTIME_WORKERS.read_text(encoding="utf-8")

        self.assertNotIn("migrate_bank_flow_rule_batch_canonical_draft", helper)
        self.assertNotIn("FIN_OPS_WORKER_KIND=bank-flow-rule-batch-canonical-draft", helper)
        self.assertNotIn("--enable-bank-flow-rule-batch-canonical-draft-refresh", helper)
        self.assertNotIn("bank_flow_rule_batch.canonical_draft.refresh", helper)
        self.assertFalse((WORKER_ENV_DIR / "fin-ops.worker.bank-flow-rule-batch.env.example").exists())

    def test_retired_invoice_page_worker_examples_are_absent(self) -> None:
        helper = ENSURE_RUNTIME_WORKERS.read_text(encoding="utf-8")
        self.assertFalse((WORKER_ENV_DIR / "fin-ops.worker.invoice-usage-collection.env.example").exists())
        self.assertFalse((WORKER_ENV_DIR / "fin-ops.worker.oa-pending-payment.env.example").exists())
        registered_events = {
            event_type
            for registration in RUNTIME_WORKER_REGISTRY
            for event_type in registration.event_types
        }
        self.assertNotIn("input_invoice_usage.read_model.refresh", registered_events)
        self.assertNotIn("output_invoice_collection.read_model.refresh", registered_events)
        self.assertNotIn("oa_pending_payment.read_model.refresh", registered_events)
        self.assertNotIn("fin-ops.worker.invoice-usage-collection.env.example", helper)

    def test_runtime_worker_docs_use_registry_manifest_instead_of_manual_matrix(self) -> None:
        for doc_path in (DEPLOYMENT_DOC, OA_DEPLOY_README):
            content = doc_path.read_text(encoding="utf-8")
            self.assertIn("runtime_worker_manifest", content, doc_path.name)
            self.assertNotIn("sudo systemctl enable --now fin-ops-worker@", content, doc_path.name)
            self.assertNotIn("| `worker-", content, doc_path.name)
            self.assertNotIn("file migration", content.lower(), doc_path.name)

    def test_deploy_control_retires_unregistered_workers_before_runtime_restart(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")
        activate_case = deploy_control.split("activate_release() {", 1)[1].split("\n}", 1)[0]

        self.assertIn("runtime_worker_manifest --instances", deploy_control)
        self.assertIn("stop_runtime_worker_services_for_activation", deploy_control)
        self.assertIn("retire_unregistered_worker_services", deploy_control)
        self.assertIn('registered_workers=" $(registered_worker_instances "$src") "', deploy_control)
        self.assertIn('systemctl disable "$service"', deploy_control)
        self.assertIn('systemctl stop "$service"', deploy_control)
        self.assertIn("assert_retired_page_runtime_quiesced", deploy_control)
        self.assertIn("from fin_ops_platform.services.read_model_manifest import READ_MODEL_MANIFEST", deploy_control)
        self.assertIn('where event_type = %s', deploy_control)
        self.assertIn('"workbench.read_model.refresh"', deploy_control)
        self.assertIn('where scope_type = %s', deploy_control)
        self.assertIn('"event_pending_count", "event_processing_count", "event_publishing_count"', deploy_control)
        self.assertIn('"event_failed_count"', deploy_control)
        self.assertIn('"event_dead_lettered_count"', deploy_control)
        self.assertIn("terminalize_retired_page_runtime_history", deploy_control)
        self.assertIn("workbench_page_read_model_runtime_retired", deploy_control)
        self.assertIn("retirement_resolution", deploy_control)
        self.assertIn("FINOPS_RETIRED_PAGE_RUNTIME_TERMINAL_BATCH_SIZE", deploy_control)
        self.assertIn("FINOPS_RETIRED_PAGE_RUNTIME_TERMINAL_MAX_ROWS", deploy_control)
        self.assertIn("for update skip locked", deploy_control)
        self.assertIn("terminal history exceeds the bounded resolution cap", deploy_control)
        self.assertIn('"original_publish_status"', deploy_control)
        self.assertIn('"original_publish_attempts"', deploy_control)
        self.assertIn('"original_publish_last_error"', deploy_control)
        self.assertNotIn("publish_status = case when publish_status", deploy_control)
        self.assertIn("must be an integer from 2 through 60", deploy_control)
        self.assertIn("status = %s", deploy_control)
        self.assertIn('"superseded", "{}", ["retirement_resolution"]', deploy_control)
        self.assertIn('where event_type = %s', deploy_control)
        self.assertIn('where scope_type = %s', deploy_control)
        self.assertIn('stable_fields = (', deploy_control)
        self.assertIn('"event_latest_created_at"', deploy_control)
        self.assertIn('"scope_latest_created_at"', deploy_control)
        self.assertIn('"terminal_history": {', deploy_control)
        self.assertIn('"disposition": "terminalized_in_place_for_retired_page_runtime"', deploy_control)
        self.assertIn('"final": final', deploy_control)
        self.assertIn('retired-workbench-page-runtime.json', deploy_control)
        self.assertIn('"retired_workbench_page_runtime": retired_page_runtime', deploy_control)
        self.assertLess(
            activate_case.index("systemctl stop fin-ops-rabbitmq-dispatcher.service"),
            activate_case.index("stop_runtime_worker_services_for_activation"),
        )
        self.assertLess(
            activate_case.index("stop_runtime_worker_services_for_activation"),
            activate_case.index('run_schema_migrations "$src"'),
        )
        self.assertLess(
            activate_case.index('run_schema_migrations "$src"'),
            activate_case.index('retire_unregistered_worker_services "$src"'),
        )
        self.assertLess(
            activate_case.index("systemctl stop fin-ops-rabbitmq-dispatcher.service"),
            activate_case.index('sync_rabbitmq_dispatcher_event_types "$src"'),
        )
        self.assertLess(
            activate_case.index('retire_unregistered_worker_services "$src"'),
            activate_case.index('assert_retired_page_runtime_quiesced'),
        )
        self.assertLess(
            activate_case.index("retire_workbench_generation_retention"),
            activate_case.index('assert_retired_page_runtime_quiesced'),
        )
        self.assertLess(
            activate_case.index('assert_retired_page_runtime_quiesced'),
            activate_case.index('ensure_runtime_workers "$src"'),
        )

    def test_release_gate_proves_retired_workbench_page_runtime_zero_delta_across_candidate_window(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")
        release_gate = deploy_control.split("release_gate_activate() {", 1)[1].split(
            '\ncmd="${1:-}"', 1
        )[0]
        observer = deploy_control.split("start_retired_workbench_page_runtime_window() {", 1)[1].split(
            "\nfinish_retired_workbench_page_runtime_window() {", 1
        )[0]

        self.assertIn("retired-workbench-page-runtime-window-v1", observer)
        self.assertIn('"event_total_count"', observer)
        self.assertIn('"event_latest_created_at"', observer)
        self.assertIn('"scope_total_count"', observer)
        self.assertIn('"scope_latest_created_at"', observer)
        self.assertIn("pg_stat_statements_info", observer)
        self.assertIn("projection_statements", observer)
        self.assertIn("projection_table_stats", observer)
        self.assertIn("pg_stat_user_tables", observer)
        self.assertIn('"workbench_generation_stats"', observer)
        self.assertIn('"workbench_group_rows"', observer)
        self.assertIn('"workbench_snapshots"', observer)
        self.assertIn('"workbench_summary"', observer)
        self.assertIn('"mode": "source_owner_absent"', observer)
        self.assertIn('"retired_source_paths_absent"', observer)
        self.assertIn('"active_call_markers_absent"', observer)
        self.assertIn('"page_runtime_registration_absent"', observer)
        self.assertIn('"page_read_model_registration_absent"', observer)
        self.assertNotIn("client.monitor()", observer)
        self.assertNotIn("MONITOR", observer)
        self.assertLess(
            release_gate.index("start_retired_workbench_page_runtime_window"),
            release_gate.index('release_gate_checkpoint "$release" t0'),
        )
        self.assertGreater(
            release_gate.index("finish_retired_workbench_page_runtime_window"),
            release_gate.index('release_gate_checkpoint "$release" t300'),
        )
        self.assertLess(
            release_gate.index("finish_retired_workbench_page_runtime_window"),
            release_gate.index("discard_workbench_page_worker_env_rollback_backup"),
        )
        self.assertIn('"retired_workbench_page_runtime_zero_delta": True', release_gate)

    def test_deploy_control_stops_api_and_workers_before_acl_migration(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")
        activate_case = deploy_control.split("activate_release() {", 1)[1].split("\n}", 1)[0]

        self.assertIn("set -Eeuo pipefail", deploy_control)
        self.assertNotIn("  activate)", deploy_control)
        self.assertIn("  release-gate-activate)", deploy_control)
        self.assertLess(
            activate_case.index("systemctl stop fin-ops.service"),
            activate_case.index("stop_runtime_worker_services_for_activation"),
        )
        self.assertLess(
            activate_case.index("stop_runtime_worker_services_for_activation"),
            activate_case.index('run_schema_migrations "$src"'),
        )

    def test_frontend_activation_restarts_the_workers_captured_before_stop(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")
        activate_case = deploy_control.split("activate_release() {", 1)[1].split("\n}", 1)[0]
        restart_case = deploy_control.split("restart_services() {", 1)[1].split("\n}", 1)[0]

        self.assertLess(
            activate_case.index('active_workers="$(active_worker_services)"'),
            activate_case.index("stop_runtime_worker_services_for_activation"),
        )
        self.assertIn('restart_services "$active_workers"', activate_case)
        self.assertIn('worker_services="$(active_worker_services)"', restart_case)
        self.assertIn('done <<<"$worker_services"', restart_case)

    def test_deploy_control_exposes_guarded_exact_etc_recovery_commands(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")

        self.assertIn("etc-deleted-batch-restore", deploy_control)
        self.assertIn("restore_deleted_etc_business_batch", deploy_control)
        self.assertIn("--expected-fingerprint", deploy_control)
        self.assertIn("etc-batch-invoice-link-backfill", deploy_control)
        self.assertIn("backfill_etc_batch_invoice_links", deploy_control)
        self.assertIn("--expected-auto-backfill-count", deploy_control)

    def test_workbench_page_worker_is_retired_while_matching_and_relation_remain(self) -> None:
        required = {registration.instance_name: registration for registration in RUNTIME_WORKER_REGISTRY if registration.required}

        self.assertEqual(
            list(required),
            ["oa-sync", "workbench-matching", "workbench-relation", "import", "settings-maintenance"],
        )
        self.assertNotIn("workbench", required)
        self.assertNotIn("workbench-secondary", required)
        self.assertNotIn("workbench-aggregate", required)
        self.assertIn("workbench-matching", required)
        self.assertIn("workbench-relation", required)
        self.assertFalse((WORKER_ENV_DIR / "fin-ops.worker.workbench.env.example").exists())

        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")
        self.assertIn('"registered_read_models": ["workbench_relation"]', deploy_control)
        self.assertIn('"registered_read_model_count": 1', deploy_control)

    def test_rabbitmq_dispatcher_env_excludes_retired_page_events(self) -> None:
        env_example = DISPATCHER_ENV.read_text()

        self.assertIn("workbench_relation.read_model.refresh", env_example)
        self.assertNotIn("workbench.read_model.refresh", env_example)
        self.assertNotIn("search.read_model.refresh", env_example)
        self.assertNotIn("no_oa_bank_batch.read_model.refresh", env_example)
        for retired_event in (
            "invoice_lifecycle.read_model.refresh",
            "input_invoice_usage.read_model.refresh",
            "output_invoice_collection.read_model.refresh",
            "oa_pending_payment.read_model.refresh",
        ):
            self.assertNotIn(retired_event, env_example)

    def test_shared_rabbitmq_worker_env_does_not_switch_all_workers_to_rabbitmq(self) -> None:
        env_example = RABBITMQ_WORKER_ENV.read_text(encoding="utf-8")

        self.assertNotRegex(env_example, r"(?m)^\s*FIN_OPS_QUEUE_BACKEND=", msg=env_example)
        self.assertIn("RABBITMQ_URL=", env_example)
        self.assertIn("RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS=0.05", env_example)

    def test_runtime_worker_env_install_migrates_rabbitmq_consumer_drain_interval(self) -> None:
        helper = ENSURE_RUNTIME_WORKERS.read_text(encoding="utf-8")

        self.assertIn("migrate_rabbitmq_worker_drain_interval", helper)
        self.assertIn("RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS=0.05", helper)

    def test_retired_search_workers_are_absent(self) -> None:
        self.assertFalse((REPO_ROOT / "deploy/oa/env/fin-ops.worker.search-pending.env.example").exists())
        self.assertFalse((REPO_ROOT / "deploy/oa/env/fin-ops.worker.search-pending-rabbitmq.env.example").exists())
        self.assertFalse((REPO_ROOT / "deploy/oa/env/fin-ops.worker.search.env.example").exists())
        self.assertFalse((REPO_ROOT / "deploy/oa/env/fin-ops.worker.search-secondary.env.example").exists())
        self.assertFalse((REPO_ROOT / "deploy/oa/env/fin-ops.worker.search-tertiary.env.example").exists())
        dispatcher_env = DISPATCHER_ENV.read_text()
        self.assertNotIn("search.read_model.refresh", dispatcher_env)
        self.assertNotIn("pending_invoice.read_model.refresh", dispatcher_env)

    def test_workbench_generation_prune_runtime_is_removed_idempotently(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")

        self.assertFalse((REPO_ROOT / "deploy/oa/bin/finops-prune-workbench-generations.sh").exists())
        self.assertFalse(
            (REPO_ROOT / "deploy/oa/systemd/finops-prune-workbench-generations.service.example").exists()
        )
        self.assertFalse(
            (REPO_ROOT / "deploy/oa/systemd/finops-prune-workbench-generations.timer.example").exists()
        )
        self.assertIn("retire_workbench_generation_retention", deploy_control)
        self.assertIn('systemctl disable --now "$timer_unit"', deploy_control)
        self.assertIn('rm -f --', deploy_control)
        self.assertNotIn("reconcile_workbench_generation_retention", deploy_control)
        self.assertNotIn("install_workbench_generation_retention", deploy_control)
        self.assertIn("restore_previous_workbench_generation_retention_for_rollback", deploy_control)
        self.assertIn("audited previous-page-runtime mode requires a page read-model release", deploy_control)
        self.assertIn("release_has_workbench_page_read_model", deploy_control)

    def test_candidate_retires_live_page_worker_and_syncs_dispatcher_allowlist(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")

        self.assertIn("retire_workbench_page_runtime_assets", deploy_control)
        self.assertIn("systemctl disable --now fin-ops-worker@workbench.service", deploy_control)
        self.assertIn('rm -f -- "$WORKBENCH_PAGE_WORKER_ENV" "$WORKBENCH_PAGE_WORKER_UNIT"', deploy_control)
        self.assertIn("sync_rabbitmq_dispatcher_event_types", deploy_control)
        self.assertIn('assert_root_owned_runtime_env "$RABBITMQ_DISPATCHER_ENV"', deploy_control)
        self.assertIn('rabbitmq_dispatch_event_types "$src"', deploy_control)
        self.assertIn('chown --reference="$RABBITMQ_DISPATCHER_ENV"', deploy_control)
        self.assertIn('chmod --reference="$RABBITMQ_DISPATCHER_ENV"', deploy_control)

    def test_direct_candidate_repairs_legacy_identity_and_bootstraps_before_workers(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")
        activate = deploy_control.split("activate_release() {", 1)[1].split(
            "\nrepair_active_api_runtime() {", 1
        )[0]
        compatibility = deploy_control.split(
            "run_workbench_direct_compatibility_preflight() {", 1
        )[1].split("\nassert_retired_page_runtime_quiesced() {", 1)[0]

        self.assertIn("repair_workbench_legacy_typed_identities", compatibility)
        self.assertEqual(
            compatibility.count("repair_workbench_legacy_typed_identities"),
            2,
        )
        self.assertIn("Workbench compatibility repair is not idempotent", compatibility)
        self.assertIn("workbench_direct_application_bootstrap_probe", compatibility)
        self.assertIn('chmod 0600 "$temporary"', compatibility)
        self.assertLess(
            activate.index("sync_python_envs"),
            activate.index("run_workbench_direct_compatibility_preflight"),
        )
        self.assertLess(
            activate.index("run_workbench_direct_compatibility_preflight"),
            activate.index("install_runtime_worker_helper"),
        )
        self.assertLess(
            activate.index("run_workbench_direct_compatibility_preflight"),
            activate.index("ensure_runtime_workers"),
        )

    def test_rollback_rehydrates_previous_page_runtime_before_activation(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")
        rollback = deploy_control.split("rollback_release_gate() {", 1)[1].split("\n}", 1)[0]
        prepare = deploy_control.split("prepare_previous_workbench_page_runtime() {", 1)[1].split(
            "\nworkbench_audit_identity() {", 1
        )[0]

        self.assertIn('"$src/scripts/rehydrate-workbench-read-models.py" --json', prepare)
        self.assertIn('seed_previous_workbench_rehydrate_scopes "$src"', prepare)
        self.assertIn('rollback-workbench-seed.json', prepare)
        self.assertIn("rollback rehydrate seed did not cover every month shard and all", prepare)
        self.assertIn('status.get("read_model_status") != "fresh"', prepare)
        self.assertIn('status.get("active_generation_id")', prepare)
        self.assertIn('status.get("building_generation_id")', prepare)
        self.assertIn('status.get("consistency_failures")', prepare)
        self.assertIn('status.get("all_scope_parent_failures")', prepare)
        self.assertIn('status.get("dirty_scopes")', prepare)
        self.assertIn("page refresh outbox is not quiesced after offline rehydrate", prepare)
        self.assertIn("retirement_history", prepare)
        self.assertIn("before_active_generations", prepare)
        self.assertIn("after_active_generations", prepare)
        self.assertIn("did not create a new Workbench generation", prepare)
        self.assertIn("new Workbench generation is not active", prepare)
        self.assertLess(
            rollback.index("enter_runtime_maintenance"),
            rollback.index('prepare_previous_workbench_page_runtime "$previous_release" "$evidence_dir"'),
        )
        self.assertLess(
            rollback.index('prepare_previous_workbench_page_runtime "$previous_release" "$evidence_dir"'),
            rollback.index('activate_release "$previous_release"'),
        )
        self.assertIn("audited-previous-page-runtime", rollback)
        self.assertIn("rollback_page_runtime_mode=direct-only", rollback)
        self.assertIn('rollback_page_runtime_mode=audited-previous-page-runtime', rollback)
        self.assertIn('"$rollback_page_runtime_mode"', rollback)
        self.assertIn('"$rollback_page_runtime_evidence"', rollback)
        self.assertIn("assert_previous_workbench_rollback_evidence", deploy_control)
        self.assertIn('payload.get("previous_release") != release', deploy_control)
        self.assertIn("enter_runtime_maintenance", rollback)
        self.assertIn("production remains in maintenance", rollback)

    def test_workbench_page_worker_env_has_exact_cutover_and_rollback_lifecycle(self) -> None:
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")
        activate = deploy_control.split("activate_release() {", 1)[1].split(
            "\nrepair_active_api_runtime() {", 1
        )[0]
        rollback = deploy_control.split("rollback_release_gate() {", 1)[1].split(
            "\nrelease_gate_activate() {", 1
        )[0]
        release_gate = deploy_control.split("release_gate_activate() {", 1)[1].split(
            '\ncmd="${1:-}"', 1
        )[0]

        self.assertIn("capture_workbench_page_worker_env_for_cutover", deploy_control)
        self.assertIn("workbench-page-worker-env-rollback-v1", deploy_control)
        self.assertIn('install -d -m 0700 "$backup_dir"', deploy_control)
        self.assertIn('install -m 0600 "$WORKBENCH_PAGE_WORKER_ENV" "$backup_temp"', deploy_control)
        self.assertIn("hashlib.sha256(path.read_bytes()).hexdigest()", deploy_control)
        self.assertIn("restore_previous_workbench_page_worker_env", activate)
        self.assertLess(
            activate.index("restore_previous_workbench_page_worker_env"),
            activate.index('ensure_runtime_workers "$src" "$required_existing_worker_envs"'),
        )
        self.assertIn('required_existing_worker_envs="workbench"', activate)
        self.assertIn('runtime_worker_helper_src="$(release_src "$rollback_candidate_release")"', activate)
        self.assertLess(
            activate.index('install_runtime_worker_helper "$runtime_worker_helper_src"'),
            activate.index("restore_previous_workbench_page_worker_env"),
        )
        self.assertIn('FINOPS_REQUIRE_EXISTING_WORKER_ENVS="$required_existing_worker_envs"', deploy_control)
        self.assertLess(
            release_gate.index("capture_workbench_page_worker_env_for_cutover"),
            release_gate.index('activate_release "$release"'),
        )
        self.assertGreater(
            release_gate.index("discard_workbench_page_worker_env_rollback_backup"),
            release_gate.index("release gate evidence contract failed"),
        )
        self.assertGreater(
            release_gate.index("discard_workbench_page_worker_env_rollback_backup"),
            release_gate.index('release_gate_checkpoint "$release" t300'),
        )
        self.assertIn("backup_cleanup", release_gate)
        self.assertGreater(
            rollback.index("discard_workbench_page_worker_env_rollback_backup"),
            rollback.index('if [[ "$rolled_back" == true ]]'),
        )
        self.assertIn("enter_runtime_maintenance", rollback)
        self.assertNotIn('cat "$backup_path"', deploy_control)

    def test_retired_workbench_generation_prune_env_is_absent(self) -> None:
        common_env = COMMON_ENV.read_text(encoding="utf-8")
        self.assertNotIn("FINOPS_WORKBENCH_PRUNE_", common_env)

    def test_runtime_queue_history_prune_helper_uses_controlled_retention_defaults(self) -> None:
        helper = RUNTIME_QUEUE_PRUNE_HELPER.read_text(encoding="utf-8")
        service = RUNTIME_QUEUE_PRUNE_SERVICE.read_text(encoding="utf-8")
        timer = RUNTIME_QUEUE_PRUNE_TIMER.read_text(encoding="utf-8")
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")

        self.assertIn("KEEP_DAYS=\"${FINOPS_RUNTIME_QUEUE_PRUNE_KEEP_DAYS:-30}\"", helper)
        self.assertIn("KEEP_RECENT_PER_TYPE=\"${FINOPS_RUNTIME_QUEUE_PRUNE_KEEP_RECENT_PER_TYPE:-512}\"", helper)
        self.assertIn("LIMIT=\"${FINOPS_RUNTIME_QUEUE_PRUNE_LIMIT:-20000}\"", helper)
        self.assertIn("FIN_OPS_POSTGRES_DATABASE_URL=\"$FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL\"", helper)
        self.assertIn("-m fin_ops_platform.tools.runtime_queue_ops prune-history", helper)
        self.assertIn("--execute", helper)

        self.assertIn("ExecStart=/usr/local/sbin/finops-prune-runtime-queue-history", service)
        self.assertIn("OnCalendar=*-*-* 03:55:00", timer)
        self.assertIn("install_runtime_queue_history_retention", deploy_control)
        self.assertIn("finops-prune-runtime-queue-history.sh", deploy_control)
        self.assertIn("systemctl enable --now \"$timer_unit\"", deploy_control)

    def test_oa_sync_enqueue_timer_uses_durable_queue_cli(self) -> None:
        helper = OA_SYNC_ENQUEUE_HELPER.read_text(encoding="utf-8")
        service = OA_SYNC_ENQUEUE_SERVICE.read_text(encoding="utf-8")
        timer = OA_SYNC_ENQUEUE_TIMER.read_text(encoding="utf-8")
        deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")

        self.assertIn("SCOPE=\"${FINOPS_OA_SYNC_SCOPE:-all}\"", helper)
        self.assertIn("REASON=\"${FINOPS_OA_SYNC_REASON:-scheduled_oa_sync}\"", helper)
        self.assertIn("-m fin_ops_platform.tools.runtime_queue_ops enqueue-oa-sync", helper)
        self.assertIn("--scope \"$SCOPE\"", helper)
        self.assertIn("ExecStart=/usr/local/sbin/finops-enqueue-oa-sync", service)
        self.assertIn("OnUnitActiveSec=5m", timer)
        self.assertIn("install_oa_sync_enqueue_timer", deploy_control)
        self.assertIn("finops-enqueue-oa-sync.sh", deploy_control)


if __name__ == "__main__":
    unittest.main()
