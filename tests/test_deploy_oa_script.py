from __future__ import annotations

import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "deploy_oa.py"
ENSURE_WORKERS_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "deploy" / "oa" / "bin" / "finops-ensure-runtime-workers.sh"
)
DEPLOY_CONTROL_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "deploy" / "oa" / "bin" / "finops-deploy-control.sh"
)


def load_deploy_module():
    spec = importlib.util.spec_from_file_location("deploy_oa_script", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load deploy_oa.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DeployOAScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_deploy_module()

    def _deployment_config(self, root_dir: Path):
        return self.module.DeploymentConfig(
            host="finops-prod",
            user="finops-deploy",
            domain="www.yn-sourcing.com",
            root_dir=root_dir,
            frontend_base_path="/fin-ops/",
            remote_frontend_dir="/www/wwwroot/fin-ops/dist",
            remote_releases_dir="/opt/fin-ops/releases",
            release_name="main-abcdef1-20260524170000",
            deploy_control_path="/usr/local/sbin/finops-deploy-control",
            keep_releases=8,
            skip_build=True,
            activate=False,
            allow_dirty=False,
            replace_release=False,
            dry_run=False,
        )

    def _write_minimal_release_tree(self, root_dir: Path, *, index_html: str) -> None:
        dist_dir = root_dir / "web" / "dist"
        backend_dir = root_dir / "backend"
        dist_dir.mkdir(parents=True)
        backend_dir.mkdir()
        (dist_dir / "index.html").write_text(index_html, encoding="utf-8")
        (dist_dir / "assets").mkdir()
        (dist_dir / "assets" / "index.js").write_text("console.log('ok');", encoding="utf-8")
        (backend_dir / "requirements.txt").write_text("", encoding="utf-8")
        migration = backend_dir / "src/fin_ops_platform/postgres/migrations/0132_settings_access_control_guard.sql"
        migration.parent.mkdir(parents=True)
        migration.write_text("select 1;\n", encoding="utf-8")
        helper = root_dir / "deploy/oa/bin/finops-deploy-control.sh"
        helper.parent.mkdir(parents=True)
        helper.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def test_parser_defaults_match_oa_server(self) -> None:
        parser = self.module.build_parser()
        args = parser.parse_args([])

        self.assertEqual(args.host, "finops-prod")
        self.assertEqual(args.user, "finops-deploy")
        self.assertEqual(args.domain, "www.yn-sourcing.com")
        self.assertEqual(args.remote_releases_dir, "/opt/fin-ops/releases")
        self.assertEqual(args.deploy_control_path, "/usr/local/sbin/finops-deploy-control")
        self.assertEqual(args.runtime_worker_ensure_path, "/usr/local/sbin/finops-ensure-runtime-workers")
        self.assertEqual(args.keep_releases, 4)
        self.assertEqual(args.remote_min_free_mb, 512)
        self.assertFalse(args.skip_build)
        self.assertFalse(args.no_activate)
        self.assertFalse(args.dry_run)

    def test_release_archive_rejects_frontend_assets_outside_configured_base_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            self._write_minimal_release_tree(
                root_dir,
                index_html=(
                    '<!doctype html><script type="module" src="/assets/index.js"></script>'
                    '<link rel="stylesheet" href="/assets/index.css">'
                ),
            )

            with self.assertRaisesRegex(RuntimeError, "frontend dist base path mismatch"):
                self.module.create_versioned_release_archive(self._deployment_config(root_dir))

    def test_release_archive_accepts_frontend_assets_under_configured_base_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            self._write_minimal_release_tree(
                root_dir,
                index_html=(
                    '<!doctype html><script type="module" src="/fin-ops/assets/index.js"></script>'
                    '<link rel="stylesheet" href="/fin-ops/assets/index.css">'
                ),
            )

            archive_path = self.module.create_versioned_release_archive(self._deployment_config(root_dir))

        self.assertTrue(archive_path.exists())
        with tarfile.open(archive_path, "r:gz") as archive:
            metadata_file = archive.extractfile("src/RELEASE.json")
            self.assertIsNotNone(metadata_file)
            metadata = json.loads(metadata_file.read().decode("utf-8"))
        self.assertEqual(
            metadata["settings_access_control"]["capability"],
            "settings-access-control-v1",
        )
        self.assertRegex(metadata["settings_access_control"]["migration_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(metadata["settings_access_control"]["deploy_control_sha256"], r"^[0-9a-f]{64}$")

    def test_release_remote_script_uses_versioned_release_and_deploy_control(self) -> None:
        config = self._deployment_config(Path("/Users/yu/Desktop/fin-ops-platform"))
        config.skip_build = False
        config.activate = True

        remote_script = self.module.build_release_remote_deploy_script(config)

        self.assertIn("finops remote deploy failed at step", remote_script)
        self.assertIn("DEPLOY_STEP='verify deploy-control bootstrap'", remote_script)
        self.assertIn("DEPLOY_STEP='verify runtime worker helper contract'", remote_script)
        self.assertIn("DEPLOY_STEP='verify deploy-control contract'", remote_script)
        self.assertIn("DEPLOY_STEP='preflight cleanup old releases'", remote_script)
        self.assertIn("DEPLOY_STEP='storage preflight'", remote_script)
        self.assertIn('printf "== finops deploy step: %s ==\\n" "$DEPLOY_STEP" >&2', remote_script)
        self.assertIn("RELEASE_DIR=/opt/fin-ops/releases/main-abcdef1-20260524170000", remote_script)
        self.assertIn("REMOTE_MIN_FREE_MB=512", remote_script)
        self.assertIn("assert_finops_release_storage", remote_script)
        self.assertIn("insufficient storage for release deploy", remote_script)
        self.assertIn('df -Pm -- "$path"', remote_script)
        self.assertIn("tar -xzf - -C \"$RELEASE_DIR\"", remote_script)
        self.assertNotIn("self-update", remote_script)
        self.assertIn("sudo -n /usr/local/sbin/finops-deploy-control check-release main-abcdef1-20260524170000", remote_script)
        self.assertNotIn("sudo -n install", remote_script)
        self.assertNotIn("DEPLOY_STEP='install runtime worker ensure helper'", remote_script)
        self.assertNotIn("sudo -n /usr/local/sbin/finops-deploy-control activate ", remote_script)
        self.assertNotIn("sudo -n /usr/local/sbin/finops-deploy-control status", remote_script)
        self.assertIn("verify_finops_deploy_control_contract", remote_script)
        self.assertIn("verify_finops_runtime_worker_ensure_contract", remote_script)
        self.assertIn("deploy-control helper is not readable; cannot verify deploy contract", remote_script)
        self.assertIn("deploy-control helper still loads the retired /root PostgreSQL env", remote_script)
        self.assertIn("deploy-control helper does not load fin-ops.secrets.env", remote_script)
        self.assertIn("deploy-control helper does not reset inherited EnvironmentFile entries", remote_script)
        self.assertIn("deploy-control helper does not archive legacy /opt/fin-ops/current", remote_script)
        self.assertIn("deploy-control helper does not enforce OA session env", remote_script)
        self.assertIn("deploy-control helper does not tolerate non-ready worker readiness polls under set -e", remote_script)
        self.assertIn("deploy-control helper does not preserve worker dependency-not-fresh delay in release drop-ins", remote_script)
        self.assertIn("deploy-control helper does not install versioned runtime queue history retention", remote_script)
        self.assertIn("settings access-control safety contract", remote_script)
        self.assertIn("deploy-control helper does not install versioned OA sync enqueue timer", remote_script)
        self.assertIn("deploy-control helper does not run runtime worker ensure inside activate", remote_script)
        self.assertIn("deploy-control helper does not expose the production-equivalent release gate", remote_script)
        self.assertIn("deploy-control helper still exposes the ungated activate command", remote_script)
        self.assertIn("runtime worker ensure helper is missing or not executable", remote_script)
        self.assertIn("runtime worker ensure helper does not use runtime worker manifest", remote_script)
        self.assertIn("runtime worker ensure helper does not refresh worker unit templates", remote_script)
        self.assertNotIn("runtime worker ensure helper does not migrate Workbench scope split", remote_script)
        self.assertIn("runtime worker ensure helper does not validate worker registrations", remote_script)
        self.assertNotIn('sudo -n /usr/local/sbin/finops-ensure-runtime-workers "$RELEASE_DIR/src"', remote_script)
        self.assertNotIn("wait_finops_backend_ready", remote_script)
        self.assertNotIn("check_finops_session_route", remote_script)
        self.assertLess(
            remote_script.index("verify_finops_deploy_control_bootstrap"),
            remote_script.index('mkdir -p "$RELEASE_DIR"'),
        )
        self.assertLess(
            remote_script.index('tar -xzf - -C "$RELEASE_DIR"'),
            remote_script.index("verify_finops_deploy_control_contract"),
        )
        self.assertLess(
            remote_script.index("verify_finops_deploy_control_contract"),
            remote_script.index("DEPLOY_STEP='deploy-control check-release'"),
        )
        self.assertLess(
            remote_script.index("verify_finops_runtime_worker_ensure_contract"),
            remote_script.index("DEPLOY_STEP='deploy-control check-release'"),
        )
        self.assertNotIn("sudo -n /bin/bash", remote_script)
        self.assertIn("KEEP_RELEASES=8", remote_script)
        self.assertIn("sudo -n /usr/local/sbin/finops-deploy-control cleanup-releases --keep 8", remote_script)
        first_cleanup_index = remote_script.index("sudo -n /usr/local/sbin/finops-deploy-control cleanup-releases --keep 8")
        self.assertLess(first_cleanup_index, remote_script.index("assert_finops_release_storage"))
        self.assertLess(remote_script.index("assert_finops_release_storage"), remote_script.index('mkdir -p "$RELEASE_DIR"'))
        self.assertNotIn("/opt/fin-ops/current/backend", remote_script)
        self.assertNotIn("systemctl restart fin-ops.service", remote_script)
        self.assertNotIn("pip install -r", remote_script)

    def test_activation_uses_separate_fail_closed_release_gate_command(self) -> None:
        config = self._deployment_config(Path("/Users/yu/Desktop/fin-ops-platform"))
        config.skip_build = False
        config.activate = True

        command = self.module.build_release_gate_command(config)

        self.assertEqual(
            command[-1],
            "sudo -n /usr/local/sbin/finops-deploy-control "
            "release-gate-activate main-abcdef1-20260524170000",
        )
        self.assertIn("ControlMaster=no", command)

    def test_activate_existing_is_zero_build_upload_or_self_update(self) -> None:
        parser = self.module.build_parser()
        config = self.module.build_config(
            parser.parse_args(
                ["--activate-existing", "--release-name", "main-abcdef1-20260524170000"]
            ),
            root_dir=Path("/Users/yu/Desktop/fin-ops-platform"),
        )

        with (
            patch.dict(os.environ, {"FIN_OPS_E2E_ADMIN_TOKEN": "secret-token"}, clear=False),
            patch.object(self.module, "run_command") as run_command,
            patch.object(self.module, "ensure_clean_git_tree") as ensure_clean,
            patch.object(self.module, "build_frontend") as build_frontend,
            patch.object(self.module, "create_release_archive") as create_archive,
        ):
            self.module.deploy(config)

        run_command.assert_called_once()
        ensure_clean.assert_not_called()
        build_frontend.assert_not_called()
        create_archive.assert_not_called()
        self.assertEqual(run_command.call_args.kwargs["input_bytes"], b"secret-token\n")
        self.assertIn("release-gate-activate main-abcdef1-20260524170000", run_command.call_args.args[0][-1])

    def test_activate_existing_rejects_upload_and_build_options(self) -> None:
        parser = self.module.build_parser()
        for option in ("--no-activate", "--replace-release", "--skip-build", "--allow-dirty"):
            with self.subTest(option=option), self.assertRaisesRegex(ValueError, "cannot be combined"):
                self.module.build_config(
                    parser.parse_args(
                        ["--activate-existing", "--release-name", "main-safe", option]
                    ),
                    root_dir=Path("/Users/yu/Desktop/fin-ops-platform"),
                )
        with self.assertRaisesRegex(ValueError, "requires --release-name"):
            self.module.build_config(
                parser.parse_args(["--activate-existing"]),
                root_dir=Path("/Users/yu/Desktop/fin-ops-platform"),
            )

    def test_release_gate_input_requires_local_admin_token(self) -> None:
        with patch.dict(
            os.environ,
            {"FIN_OPS_E2E_ADMIN_TOKEN": "", "FIN_OPS_HTTP_SLO_ADMIN_TOKEN": ""},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "production-equivalent release gate"):
                self.module.release_gate_input()

    def test_release_gate_input_uses_admin_token_without_printing_it(self) -> None:
        with patch.dict(os.environ, {"FIN_OPS_E2E_ADMIN_TOKEN": "secret-token"}, clear=False):
            self.assertEqual(self.module.release_gate_input(), b"secret-token\n")

    def test_release_remote_script_can_upload_without_activation(self) -> None:
        config = self._deployment_config(Path("/Users/yu/Desktop/fin-ops-platform"))

        remote_script = self.module.build_release_remote_deploy_script(config)

        self.assertIn("check-release main-abcdef1-20260524170000", remote_script)
        self.assertNotIn("activate main-abcdef1-20260524170000", remote_script)
        self.assertNotIn("finops-ensure-runtime-workers.sh", remote_script)
        self.assertNotIn("cleanup-releases", remote_script)
        self.assertNotIn("DEPLOY_STEP='deploy-control self-update'", remote_script)
        self.assertNotIn("verify_finops_deploy_control_contract", remote_script)
        self.assertIn("assert_finops_release_storage", remote_script)

    def test_remote_command_quotes_multiline_script_for_ssh(self) -> None:
        config = self._deployment_config(Path("/Users/yu/Desktop/fin-ops-platform"))
        remote_script = "set -euo pipefail\necho ok\n"

        command = self.module.build_remote_command(config, remote_script)

        self.assertEqual(command[-1], "bash -lc 'set -euo pipefail\necho ok\n'")
        self.assertNotIn("bash", command[-3:-1])
        self.assertIn("ControlMaster=no", command)
        self.assertNotIn("ControlMaster=auto", command)
        self.assertNotIn("ControlPersist=600", command)
        self.assertFalse(any("fin_ops_mux" in part for part in command))

    def test_legacy_current_deploy_mode_is_removed(self) -> None:
        parser = self.module.build_parser()

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--mode", "legacy-current"])

        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertFalse(hasattr(self.module, "build_legacy_remote_deploy_script"))
        self.assertFalse(hasattr(self.module, "create_legacy_release_archive"))
        self.assertNotIn("legacy-current", source)
        self.assertNotIn("/opt/fin-ops/current/backend", source)
        self.assertNotIn("systemctl restart fin-ops.service", source)

    def test_runtime_worker_ensure_script_defaults_to_full_postgres_worker_matrix(self) -> None:
        script = ENSURE_WORKERS_SCRIPT_PATH.read_text()

        self.assertIn("runtime_worker_manifest --required-instances", script)
        self.assertIn("runtime_worker_manifest --env-example", script)
        self.assertIn("runtime_worker_manifest --worker-check-command", script)
        self.assertNotIn("oa-sync workbench workbench-matching", script)
        self.assertNotIn("case \"$1\" in", script)
        self.assertIn("fin-ops-worker@${worker}.service", script)

    def test_systemd_worker_template_uses_registry_registration_contract(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "deploy/oa/systemd/fin-ops-worker@.service.example").read_text()

        self.assertIn("Environment=FIN_OPS_WORKER_INSTANCE=%i", template)
        self.assertIn("EnvironmentFile=-/etc/fin-ops/fin-ops.rabbitmq-worker.env", template)
        self.assertIn("FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS=0.25", template)
        self.assertIn("--registration ${FIN_OPS_WORKER_INSTANCE}", template)
        self.assertIn("--worker-instance ${FIN_OPS_WORKER_INSTANCE}", template)
        self.assertIn(
            "--dependency-not-fresh-delay-seconds ${FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS}",
            template,
        )

    def test_workbench_requirement_repair_fixed_modes(self) -> None:
        script = DEPLOY_CONTROL_SCRIPT_PATH.read_text()

        self.assertIn("workbench-requirement-repair <release-name> --dry-run", script)
        self.assertIn("--execute --expected-fingerprint <sha256>", script)
        self.assertIn("--rollback-dry-run --expected-fingerprint <sha256>", script)
        self.assertIn("--rollback --expected-fingerprint <sha256>", script)
        self.assertIn("workbench-requirement-repair only permits the four fixed modes", script)
        self.assertIn('case "$mode" in', script)
        self.assertIn("fin_ops_platform.tools.workbench_relation_requirement_repair_ops", script)

    def test_workbench_etc_summary_repair_is_identity_and_fingerprint_guarded(self) -> None:
        script = DEPLOY_CONTROL_SCRIPT_PATH.read_text()

        self.assertIn(
            "workbench-etc-summary-repair <release-name> --case-id ID "
            "--external-etc-batch-id ID --dry-run",
            script,
        )
        self.assertIn("workbench-etc-summary-repair requires a safe --case-id", script)
        self.assertIn("workbench-etc-summary-repair requires a safe --external-etc-batch-id", script)
        self.assertIn("workbench-etc-summary-repair only permits the four fixed modes", script)
        self.assertIn("fin_ops_platform.tools.workbench_etc_summary_relation_repair_ops", script)

    def test_batch_accounting_metadata_cleanup_fixed_modes(self) -> None:
        script = DEPLOY_CONTROL_SCRIPT_PATH.read_text()

        self.assertIn("batch-accounting-metadata-cleanup <release-name> --dry-run", script)
        self.assertIn("batch-accounting-metadata-cleanup only permits the four fixed modes", script)
        self.assertIn("fin_ops_platform.tools.batch_accounting_metadata_cleanup_ops", script)

    def test_batch_accounting_read_only_validation_commands_are_fixed(self) -> None:
        script = DEPLOY_CONTROL_SCRIPT_PATH.read_text()

        self.assertIn("batch-accounting-audit <release-name>", script)
        self.assertIn("batch-accounting-audit accepts only release name", script)
        self.assertIn("audit_page_business_read_model", script)
        self.assertIn("batch_accounting --json --fail-on-issues", script)
        self.assertIn("batch-accounting-read-smoke <release-name> --bank-year YYYY", script)
        self.assertIn("batch-accounting-read-smoke accepts only --bank-year YYYY [--iterations N]", script)
        self.assertIn("fin_ops_platform.tools.batch_accounting_read_smoke", script)

    def test_domain_contract_audit_is_fixed_read_only_release_command(self) -> None:
        script = DEPLOY_CONTROL_SCRIPT_PATH.read_text()

        self.assertIn("domain-contract-audit <release-name>", script)
        self.assertIn("domain-contract-audit accepts only release name", script)
        self.assertIn("fin_ops_platform.tools.domain_contract_audit", script)

    def test_workbench_matching_retry_is_scope_and_fingerprint_guarded(self) -> None:
        script = DEPLOY_CONTROL_SCRIPT_PATH.read_text()

        self.assertIn("workbench-matching-retry <release-name> --scope-month YYYY-MM --dry-run", script)
        self.assertIn("--scope-month YYYY-MM --execute --expected-fingerprint <sha256>", script)
        self.assertIn("workbench-matching-retry only permits dry-run or fingerprint-guarded execute", script)
        self.assertIn("fin_ops_platform.tools.workbench_matching_scope_retry_ops", script)

    def test_deploy_control_script_uses_canonical_etc_finops_secret_contract(self) -> None:
        script = DEPLOY_CONTROL_SCRIPT_PATH.read_text()

        self.assertIn('COMMON_ENV="$ENV_DIR/fin-ops.common.env"', script)
        self.assertIn('SECRETS_ENV="$ENV_DIR/fin-ops.secrets.env"', script)
        self.assertIn("assert_runtime_env_contract", script)
        self.assertIn('MIGRATOR_ENV="$ENV_DIR/fin-ops.postgres-migrator.env"', script)
        self.assertIn('LEGACY_CURRENT_DIR="${FINOPS_LEGACY_CURRENT_DIR:-/opt/fin-ops/current}"', script)
        self.assertIn("archive_legacy_current", script)
        self.assertIn("archived legacy current runtime", script)
        self.assertIn("run_schema_migrations", script)
        self.assertIn("fin_ops_platform.postgres.migrate apply", script)
        self.assertIn("missing PostgreSQL DSN", script)
        self.assertIn("missing OA session runtime env", script)
        self.assertIn("FIN_OPS_OA_BASE_URL", script)
        self.assertIn("FIN_OPS_OA_USER_INFO_PATH", script)
        self.assertIn("FIN_OPS_ALLOWED_USERNAMES", script)
        self.assertNotIn("FIN_OPS_ADMIN_USERNAMES", script)
        self.assertIn("EnvironmentFile=\nEnvironmentFile=$COMMON_ENV", script)
        self.assertGreaterEqual(script.count("EnvironmentFile=\nEnvironmentFile=$COMMON_ENV"), 2)
        self.assertIn("EnvironmentFile=$COMMON_ENV", script)
        self.assertIn("EnvironmentFile=$SECRETS_ENV", script)
        self.assertIn('ENSURE_RUNTIME_WORKERS_HELPER="${FINOPS_ENSURE_RUNTIME_WORKERS_HELPER:-/usr/local/sbin/finops-ensure-runtime-workers}"', script)
        self.assertIn('DEPLOY_CONTROL_HELPER="${FINOPS_DEPLOY_CONTROL_HELPER:-/usr/local/sbin/finops-deploy-control}"', script)
        self.assertIn('WRITE_E2E_BACKUP_ROOT="${FINOPS_WRITE_E2E_BACKUP_ROOT:-/opt/fin-ops/backups/write-operation-e2e}"', script)
        self.assertNotIn("self-update <release-name>", script)
        self.assertIn("repair-active-api-runtime", script)
        self.assertNotIn("install_deploy_control_helper", script)
        self.assertIn("install_runtime_worker_helper", script)
        self.assertIn('install_runtime_worker_helper "$src"', script)
        self.assertIn('ensure_runtime_workers "$src"', script)
        self.assertIn('"$ENSURE_RUNTIME_WORKERS_HELPER" "$src"', script)
        self.assertIn("RuntimeDirectory=fin-ops", script)
        self.assertIn("RuntimeDirectoryMode=0750", script)
        self.assertIn('[[ -f "$src/backend/src/fin_ops_platform/app/wsgi.py"', script)
        self.assertIn("python:fin_ops_platform.app.gunicorn_conf fin_ops_platform.app.wsgi:application", script)
        self.assertIn("fin_ops_platform.app.main --host 127.0.0.1 --port 18001", script)
        self.assertIn('[[ "$#" -eq 0 ]] || die "repair-active-api-runtime accepts no arguments"', script)
        self.assertIn("wait_required_workers_ready", script)
        self.assertIn("rabbitmq-required-worker-cutover <release-name>", script)
        self.assertIn("rabbitmq_required_worker_cutover()", script)
        self.assertIn("runtime_worker_manifest --rabbitmq-required-instances", script)
        self.assertIn("runtime_worker_manifest --rabbitmq-dispatch-event-types", script)
        self.assertIn('RABBITMQ_WORKER_ENV="${FINOPS_RABBITMQ_WORKER_ENV:-', script)
        self.assertIn('RABBITMQ_WORKER_CUTOVER_BACKUP_ROOT="${FINOPS_RABBITMQ_WORKER_CUTOVER_BACKUP_ROOT:-', script)
        self.assertIn("runtime env must be a regular non-symlink file", script)
        self.assertIn("runtime env must be root-owned", script)
        self.assertIn("runtime env must not be group/world writable", script)
        self.assertIn("missing RABBITMQ_URL", script)
        self.assertIn("shared RabbitMQ env must not define FIN_OPS_QUEUE_BACKEND", script)
        self.assertIn("FIN_OPS_QUEUE_BACKEND=rabbitmq", script)
        self.assertIn("restore_rabbitmq_worker_envs", script)
        self.assertIn("wait_rabbitmq_required_queues_drained", script)
        self.assertIn('source "$RABBITMQ_MONITORING_ENV"', script)
        self.assertIn("RuntimeMonitoringRepository(connection).ready_health_summary()", script)
        self.assertIn('"queues_without_consumers": without_consumers', script)
        self.assertIn('"rabbitmq_queue_depth": int(runtime.get("rabbitmq_queue_depth") or 0)', script)
        self.assertIn("original worker env files were restored", script)
        self.assertIn("rollback backup retained", script)
        self.assertIn("release-gate-activate <release-name>", script)
        self.assertIn("release_gate_activate()", script)
        self.assertNotIn("  activate)", script)
        self.assertIn("worker_inventory_report", script)
        self.assertIn("rabbitmq_topology --apply", script)
        self.assertIn("domain_contract_audit", script)
        self.assertIn("runtime_sync_closure_gate", script)
        self.assertIn("--apply-read-model-smoke", script)
        self.assertIn("--read-model-target-ms 5000", script)
        self.assertIn("--write-target-ms 5000", script)
        self.assertIn("--http-target-ms 1000", script)
        self.assertIn('--required-worker-instance "$required_worker_instance"', script)
        self.assertIn("sleep 60", script)
        self.assertIn("sleep 240", script)
        self.assertIn("rollback_release_gate", script)
        self.assertIn("contract-version [--require VERSION]", script)
        self.assertIn("candidate-status <release-name> --json", script)
        self.assertIn("settings-access-control-preflight <release-name>", script)
        self.assertIn("settings-access-control-post-deploy <release-name>", script)
        self.assertIn('assert_settings_access_control_preflight "$release"', script)
        self.assertIn("previous release lacks $SETTINGS_ACL_CONTRACT", script)
        activate = script.split("activate_release() {", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(activate.index("systemctl stop fin-ops.service"), activate.index('run_schema_migrations "$src"'))
        self.assertNotIn("install_deploy_control_helper", activate)
        self.assertIn('"release_gate_status": "PASS"', script)
        self.assertIn('"unknown_worker_count": 0', script)
        self.assertIn('"required_worker_not_ready": 0', script)
        self.assertIn('"dirty_scope_count": 0', script)
        self.assertIn('"pending_outbox_count": 0', script)
        self.assertIn('"publishing_outbox_count": 0', script)
        self.assertNotIn('reconcile_completed_publish_states "$verification_release"', script)
        self.assertNotIn("reconcile_completed_publish_states() {", script)
        self.assertIn('"dead_letter_delta": 0', script)
        self.assertIn('"terminal_publish_reconciliation_count"', script)
        self.assertIn('"terminal_publish_reconciliation_stable": True', script)
        self.assertIn('"runtime_sync_closure_failed_checks"', script)
        self.assertIn('"runtime_sync_closure_failures"', script)
        self.assertIn('"diagnostics": diagnostics or None', script)
        self.assertIn('"snapshot",', script)
        self.assertIn('"page_canonical_audit_status": "pass"', script)
        self.assertIn('"queue_stable_after_300_seconds": True', script)
        self.assertIn("read-model-scope-contract <release-name> [args]", script)
        self.assertIn("workbench-requirement-repair <release-name>", script)
        self.assertIn("workbench_requirement_repair()", script)
        self.assertIn("fin_ops_platform.tools.workbench_relation_requirement_repair_ops", script)
        self.assertIn("--rollback-dry-run --expected-fingerprint <sha256>", script)
        self.assertIn("--rollback --expected-fingerprint <sha256>", script)
        self.assertIn("workbench-requirement-repair only permits the four fixed modes", script)
        self.assertIn("workbench-matching-retry <release-name>", script)
        self.assertIn("workbench_matching_retry()", script)
        self.assertIn("fin_ops_platform.tools.workbench_matching_scope_retry_ops", script)
        self.assertIn('case "$mode" in', script)
        self.assertIn("read_model_scope_contract()", script)
        self.assertIn('run_with_runtime_env "$src" "$src/scripts/check-read-model-scope-contracts.py" "$@"', script)
        self.assertIn("read-model-slo-smoke <release-name> [args]", script)
        self.assertIn("read_model_slo_smoke()", script)
        self.assertIn("read-model-slo-smoke only permits dry-run through deploy-control", script)
        self.assertIn('run_with_runtime_env "$src" -m fin_ops_platform.tools.read_model_slo_smoke "$@"', script)
        self.assertIn("write-operation-restore-point <release-name> <run-id>", script)
        self.assertIn("write_operation_restore_point()", script)
        self.assertIn("write-operation-restore-point run-id must be 1..80 safe filename characters", script)
        self.assertIn("from psycopg.conninfo import conninfo_to_dict", script)
        self.assertIn('source "$MIGRATOR_ENV"', script)
        self.assertIn('os.environ.get("FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL")', script)
        self.assertIn('environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}', script)
        self.assertIn('"password": "PGPASSWORD"', script)
        self.assertIn('environment["PGAPPNAME"] = "finops-write-operation-restore-point"', script)
        self.assertIn('["pg_dump", "--format=custom", "--no-owner", "--no-acl", f"--file={sys.argv[1]}"]', script)

        self.assertIn('pg_restore --list "$temp_path"', script)
        self.assertIn('sha256sum "$dump_path"', script)
        self.assertNotIn('pg_dump "$FIN_OPS_POSTGRES_DATABASE_URL"', script)
        self.assertIn("write-operation-restore-point-delete <run-id> <expected-sha256>", script)
        self.assertIn("write_operation_restore_point_delete()", script)
        self.assertIn("write-operation restore point directory contains unexpected files", script)
        self.assertIn('[[ "$actual_checksum" == "$expected_checksum" ]]', script)
        self.assertIn('rm -f -- "$dump_path" "$manifest_path"', script)
        self.assertIn('rmdir -- "$output_dir"', script)
        self.assertIn(
            "write-operation-e2e-scenario-install <release-name> <temporary-scenario-path>",
            script,
        )
        self.assertIn("write_operation_e2e_scenario_install()", script)
        self.assertIn("from fin_ops_platform.tools.runtime_sync_closure_gate import _load_write_scenarios", script)
        self.assertIn('install -m 0600 -o root -g root "$scenario" "$staged"', script)
        self.assertIn('[[ ! -L "$target_dir" ]]', script)
        self.assertIn('[[ ! -L "$backup" ]]', script)
        self.assertIn('[[ -L "$STANDARD_WRITE_E2E_SCENARIO" ]]', script)
        self.assertIn('mv -f -- "$staged" "$STANDARD_WRITE_E2E_SCENARIO"', script)
        self.assertIn(
            "write-operation-e2e-smoke <release-name> <scenario-path> "
            "[--dry-run|--apply-stdin] [preview-samples]",
            script,
        )
        self.assertIn("write_operation_e2e_smoke()", script)
        self.assertIn("STANDARD_WRITE_E2E_SCENARIO", script)
        self.assertIn(
            "scenario path must be the fixed standard scenario or match /tmp/finops-write-e2e-*.json",
            script,
        )
        self.assertIn("standard scenario must be root-owned with mode 0600", script)
        self.assertIn('IFS= read -r admin_token', script)
        self.assertIn('IFS= read -r approval_ticket', script)
        self.assertIn('export FIN_OPS_HTTP_SLO_ADMIN_TOKEN="$admin_token"', script)
        self.assertIn('export FIN_OPS_WRITE_E2E_APPROVAL_TICKET="$approval_ticket"', script)
        self.assertIn("--write-target-ms 5000", script)
        self.assertIn("--http-target-ms 1000", script)
        self.assertIn('--relation-preview-samples "$preview_samples"', script)
        self.assertIn("preview samples must be an integer between 1 and 20", script)
        self.assertIn('report_path="$(mktemp /tmp/finops-write-e2e-report.XXXXXX.json)"', script)
        self.assertIn("trap 'rm -f -- \"$report_path\"' EXIT", script)
        self.assertIn('--output "$report_path"', script)
        self.assertIn('[[ -s "$report_path" ]] || die "write-operation E2E runner did not produce a JSON report"', script)
        self.assertIn('cat -- "$report_path"', script)
        self.assertIn('exit "$runner_status"', script)
        self.assertIn('write approval ticket stdin is empty', script)
        self.assertIn("write-operation-e2e-smoke accepts at most four arguments", script)
        self.assertIn("api-request-error <request-id>", script)
        self.assertIn("api_request_error()", script)
        self.assertIn("api-request-trace <request-id>", script)
        self.assertIn("api_request_trace()", script)
        self.assertIn("request trace not found in the bounded journal window", script)
        self.assertIn("NR <= 64", script)
        self.assertIn("api-request-timing <request-id>", script)
        self.assertIn("api_request_timing()", script)
        self.assertIn("request timing not found in the bounded journal window", script)
        self.assertIn("request id must be 12 lowercase hexadecimal characters", script)
        self.assertIn("journalctl -u fin-ops.service --since '2 hours ago'", script)
        self.assertIn("request error not found in the bounded journal window", script)
        self.assertIn("read-model-refresh <release-name> [args]", script)
        self.assertNotIn("no-oa-read-model-refresh-drain", script)
        self.assertIn("settings-normalize <release-name> [--dry-run|--execute]", script)
        self.assertIn("import-audit-repair <release-name> [--dry-run|--execute --expected-fingerprint <sha256>]", script)
        self.assertIn("bank-transaction-category-repair <release-name>", script)
        self.assertIn("runtime-queue-resolve-covered <release-name> [args]", script)
        self.assertIn("read_model_refresh()", script)
        self.assertIn("settings_normalize()", script)
        self.assertIn("import_audit_repair()", script)
        self.assertIn("bank_transaction_category_repair()", script)
        self.assertIn("runtime_queue_resolve_covered()", script)
        self.assertIn("enqueue-read-model-refresh", script)
        self.assertNotIn("no_oa_read_model_refresh_drain()", script)
        self.assertNotIn('service="fin-ops-worker@no-oa-bank-batch.service"', script)
        self.assertNotIn("fin-ops-worker@no-oa-bank-batch.service", script)
        self.assertNotIn('--scope "no_oa_bank_batch=$scope_key"', script)
        self.assertNotIn("--enable-no-oa-bank-batch-read-model-refresh", script)
        self.assertNotIn("no-OA worker was not restored after candidate drain", script)
        self.assertIn("fin_ops_platform.tools.settings_normalization_ops", script)
        self.assertIn("fin_ops_platform.tools.import_audit_repair_ops", script)
        self.assertIn("fin_ops_platform.tools.repair_unknown_bank_transaction_categories", script)
        self.assertIn("resolve-covered-dead-letters", script)
        self.assertIn("FINOPS_WORKER_READY_TIMEOUT_SECONDS", script)
        self.assertIn("missing_required_worker_count", script)
        self.assertIn("stale_required_worker_count", script)
        self.assertIn("--dependency-not-fresh-delay-seconds \\${FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS}", script)
        self.assertIn("worker_kind_mismatch", script)
        self.assertIn("worker_event_type_mismatch", script)
        self.assertIn("readiness_status=0", script)
        self.assertIn('|| readiness_status="$?"', script)
        self.assertIn('case "$readiness_status" in', script)
        self.assertIn("--registration \\${FIN_OPS_WORKER_INSTANCE}", script)
        self.assertIn("--worker-instance \\${FIN_OPS_WORKER_INSTANCE}", script)
        self.assertLess(script.rindex('ensure_runtime_workers "$src"'), script.rindex("wait_required_workers_ready"))
        self.assertLess(script.rindex("read_model_scope_contract()"), script.rindex('case "$cmd" in'))
        self.assertLess(script.rindex("read_model_slo_smoke()"), script.rindex('case "$cmd" in'))
        self.assertNotIn("EnvironmentFile=/opt/fin-ops/fin-ops.env", script)
        self.assertNotIn("/root/fin_ops_stage23_postgres_runtime.env", script)
        self.assertNotIn("FIN_OPS_POSTGRES_DATABASE_URL=", script)
        self.assertNotIn("--worker-kind \\${FIN_OPS_WORKER_KIND}", script)

    def test_release_gate_restores_stable_helpers_when_precheck_fails(self) -> None:
        script = DEPLOY_CONTROL_SCRIPT_PATH.read_text()
        start = script.index('if ! release_gate_checkpoint "$previous_release" pre')
        end = script.index('if ! (activate_release "$release")', start)
        pre_failure_branch = script[start:end]

        self.assertIn(
            'release_gate_checkpoint "$previous_release" pre "$admin_token" "$evidence_dir" preflight "$release"',
            script,
        )
        self.assertIn(
            'release_gate_checkpoint "$previous_release" rollback "$admin_token" "$evidence_dir" preflight "$candidate"',
            script,
        )
        self.assertIn('cat "$evidence_dir/$failure_checkpoint/checkpoint.json" >&2 || true', script)
        self.assertIn(
            'release_gate_checkpoint "$release" t0 "$admin_token" "$evidence_dir" full',
            script,
        )
        self.assertIn(
            'release_gate_checkpoint "$release" t300 "$admin_token" "$evidence_dir" stability',
            script,
        )
        self.assertNotIn("install_deploy_control_helper", pre_failure_branch)
        self.assertNotIn("install_runtime_worker_helper", pre_failure_branch)
        self.assertIn('cat "$evidence_dir/pre/checkpoint.json" >&2', pre_failure_branch)
        self.assertIn('"component_statuses": {', script)

    def test_release_gate_loads_rabbitmq_env_without_automatic_business_write(self) -> None:
        script = DEPLOY_CONTROL_SCRIPT_PATH.read_text()
        checkpoint = script.split("release_gate_checkpoint() {", 1)[1].split(
            "\nrelease_gate_checkpoint_passed() {",
            1,
        )[0]

        self.assertIn('RABBITMQ_TOPOLOGY_ENV="${FINOPS_RABBITMQ_TOPOLOGY_ENV:-', script)
        self.assertIn('RABBITMQ_MONITORING_ENV="${FINOPS_RABBITMQ_MONITORING_ENV:-', script)
        self.assertEqual(checkpoint.count('source "$RABBITMQ_TOPOLOGY_ENV"'), 1)
        self.assertEqual(checkpoint.count('source "$RABBITMQ_MONITORING_ENV"'), 2)
        self.assertIn("RabbitMQ topology env is missing or unreadable", checkpoint)
        self.assertIn("RabbitMQ monitoring env is missing or unreadable", checkpoint)
        self.assertNotIn("STANDARD_WRITE_E2E_APPROVAL_TICKET", checkpoint)
        self.assertNotIn("FIN_OPS_WRITE_E2E_APPROVAL_TICKET", checkpoint)
        self.assertNotIn("--apply-write-scenarios", checkpoint)
        self.assertNotIn("--write-scenario", checkpoint)
        self.assertIn("--page-base-url https://www.yn-sourcing.com", checkpoint)
        self.assertIn('if [[ "$profile" == "preflight" ]]', checkpoint)
        self.assertIn('required_worker_instances "$src"', checkpoint)
        self.assertLess(
            checkpoint.index("-m fin_ops_platform.tools.runtime_sync_closure_gate"),
            checkpoint.index('"$API_PYTHON" - "$runtime_report"'),
        )
        self.assertNotIn("reconcile_completed_publish_states", checkpoint)
        self.assertIn("terminal_publish_reconciliation_count", checkpoint)
        self.assertIn("terminal_publish_reconciliation_stable", checkpoint)

    def test_deploy_control_read_model_slo_smoke_refuses_apply_before_release_lookup(self) -> None:
        env = {**os.environ, "FINOPS_RELEASE_ROOT": "/tmp/finops-release-root-does-not-exist"}

        result = subprocess.run(
            [
                str(DEPLOY_CONTROL_SCRIPT_PATH),
                "read-model-slo-smoke",
                "fake-release",
                "--apply",
                "--json",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("read-model-slo-smoke only permits dry-run through deploy-control", result.stderr)
        self.assertNotIn("release src directory not found", result.stderr)

    def test_deploy_control_write_operation_runner_refuses_untrusted_scenario_path(self) -> None:
        result = subprocess.run(
            [
                str(DEPLOY_CONTROL_SCRIPT_PATH),
                "write-operation-e2e-smoke",
                "fake-release",
                "/etc/passwd",
                "--apply-stdin",
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "scenario path must be the fixed standard scenario or match /tmp/finops-write-e2e-*.json",
            result.stderr,
        )
        self.assertNotIn("release src directory not found", result.stderr)

    def test_deploy_control_scenario_install_refuses_untrusted_path_before_release_lookup(self) -> None:
        result = subprocess.run(
            [
                str(DEPLOY_CONTROL_SCRIPT_PATH),
                "write-operation-e2e-scenario-install",
                "fake-release",
                "/etc/passwd",
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "temporary scenario path must match /tmp/finops-write-e2e-*.json",
            result.stderr,
        )
        self.assertNotIn("release src directory not found", result.stderr)

    def test_deploy_control_write_restore_point_refuses_unsafe_run_id_before_release_lookup(self) -> None:
        result = subprocess.run(
            [
                str(DEPLOY_CONTROL_SCRIPT_PATH),
                "write-operation-restore-point",
                "fake-release",
                "../unsafe",
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run-id must be 1..80 safe filename characters", result.stderr)
        self.assertNotIn("release src directory not found", result.stderr)

    def test_deploy_control_restore_point_delete_requires_exact_sha256_before_file_lookup(self) -> None:
        result = subprocess.run(
            [
                str(DEPLOY_CONTROL_SCRIPT_PATH),
                "write-operation-restore-point-delete",
                "safe-run-id",
                "not-a-sha",
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires a lowercase SHA-256 checksum", result.stderr)
        self.assertNotIn("restore point directory is unavailable", result.stderr)


if __name__ == "__main__":
    unittest.main()
