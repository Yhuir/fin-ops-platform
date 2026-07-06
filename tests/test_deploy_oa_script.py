from __future__ import annotations

import contextlib
import io
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


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

    def test_release_remote_script_uses_versioned_release_and_deploy_control(self) -> None:
        config = self._deployment_config(Path("/Users/yu/Desktop/fin-ops-platform"))
        config.skip_build = False
        config.activate = True

        remote_script = self.module.build_release_remote_deploy_script(config)

        self.assertIn("finops remote deploy failed at step", remote_script)
        self.assertIn("DEPLOY_STEP='verify deploy-control bootstrap'", remote_script)
        self.assertIn("DEPLOY_STEP='verify runtime worker helper contract'", remote_script)
        self.assertIn("DEPLOY_STEP='deploy-control self-update'", remote_script)
        self.assertIn("DEPLOY_STEP='verify deploy-control contract'", remote_script)
        self.assertIn("DEPLOY_STEP='deploy-control activate'", remote_script)
        self.assertIn("DEPLOY_STEP='preflight cleanup old releases'", remote_script)
        self.assertIn("DEPLOY_STEP='storage preflight'", remote_script)
        self.assertIn("DEPLOY_STEP='cleanup old releases'", remote_script)
        self.assertIn('printf "== finops deploy step: %s ==\\n" "$DEPLOY_STEP" >&2', remote_script)
        self.assertIn("RELEASE_DIR=/opt/fin-ops/releases/main-abcdef1-20260524170000", remote_script)
        self.assertIn("REMOTE_MIN_FREE_MB=512", remote_script)
        self.assertIn("assert_finops_release_storage", remote_script)
        self.assertIn("insufficient storage for release deploy", remote_script)
        self.assertIn('df -Pm -- "$path"', remote_script)
        self.assertIn("tar -xzf - -C \"$RELEASE_DIR\"", remote_script)
        self.assertIn('sudo -n "$DEPLOY_CONTROL" self-update "$RELEASE_NAME"', remote_script)
        self.assertIn("deploy-control helper cannot self-update; run initial root bootstrap", remote_script)
        self.assertIn("sudo -n /usr/local/sbin/finops-deploy-control check-release main-abcdef1-20260524170000", remote_script)
        self.assertNotIn("sudo -n install", remote_script)
        self.assertNotIn("DEPLOY_STEP='install runtime worker ensure helper'", remote_script)
        self.assertIn("sudo -n /usr/local/sbin/finops-deploy-control activate main-abcdef1-20260524170000", remote_script)
        self.assertIn("sudo -n /usr/local/sbin/finops-deploy-control status", remote_script)
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
        self.assertIn("deploy-control helper does not install versioned Workbench generation retention", remote_script)
        self.assertIn("deploy-control helper does not install versioned runtime queue history retention", remote_script)
        self.assertIn("deploy-control helper does not self-update from versioned releases", remote_script)
        self.assertIn("deploy-control helper does not install versioned OA sync enqueue timer", remote_script)
        self.assertIn("deploy-control helper does not run runtime worker ensure inside activate", remote_script)
        self.assertIn("runtime worker ensure helper is missing or not executable", remote_script)
        self.assertIn("runtime worker ensure helper does not use runtime worker manifest", remote_script)
        self.assertIn("runtime worker ensure helper does not refresh worker unit templates", remote_script)
        self.assertIn("runtime worker ensure helper does not migrate Workbench scope split", remote_script)
        self.assertIn("runtime worker ensure helper does not validate worker registrations", remote_script)
        self.assertNotIn('sudo -n /usr/local/sbin/finops-ensure-runtime-workers "$RELEASE_DIR/src"', remote_script)
        self.assertIn("wait_finops_backend_ready", remote_script)
        self.assertIn("check_finops_session_route /fin-ops-api/api/session/me", remote_script)
        self.assertIn("check_finops_session_route /fin-ops/api/session/me", remote_script)
        self.assertIn("session API route is not proxied as JSON", remote_script)
        self.assertLess(
            remote_script.index("wait_finops_backend_ready"),
            remote_script.index("check_finops_session_route /fin-ops-api/api/session/me"),
        )
        self.assertLess(
            remote_script.index("verify_finops_deploy_control_bootstrap"),
            remote_script.index('mkdir -p "$RELEASE_DIR"'),
        )
        self.assertLess(
            remote_script.index('tar -xzf - -C "$RELEASE_DIR"'),
            remote_script.index("DEPLOY_STEP='deploy-control self-update'"),
        )
        self.assertLess(
            remote_script.index("DEPLOY_STEP='deploy-control self-update'"),
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
        self.assertLess(
            remote_script.index("verify_finops_runtime_worker_ensure_contract"),
            remote_script.index("DEPLOY_STEP='deploy-control activate'"),
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

    def test_release_remote_script_waits_for_backend_before_public_route_smoke(self) -> None:
        config = self._deployment_config(Path("/Users/yu/Desktop/fin-ops-platform"))
        config.skip_build = False
        config.activate = True

        remote_script = self.module.build_release_remote_deploy_script(config)

        self.assertIn("curl -fsS --max-time 5 http://127.0.0.1:18001/health/ready", remote_script)
        self.assertIn("backend did not become ready after release activation", remote_script)
        self.assertIn("route_deadline=$((SECONDS + 60))", remote_script)
        self.assertIn("return 0", remote_script)
        self.assertLess(
            remote_script.index("wait_finops_backend_ready"),
            remote_script.index("check_finops_session_route /fin-ops-api/api/session/me"),
        )

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
        self.assertIn("FIN_OPS_ADMIN_USERNAMES", script)
        self.assertIn("EnvironmentFile=\nEnvironmentFile=$COMMON_ENV", script)
        self.assertGreaterEqual(script.count("EnvironmentFile=\nEnvironmentFile=$COMMON_ENV"), 2)
        self.assertIn("EnvironmentFile=$COMMON_ENV", script)
        self.assertIn("EnvironmentFile=$SECRETS_ENV", script)
        self.assertIn('ENSURE_RUNTIME_WORKERS_HELPER="${FINOPS_ENSURE_RUNTIME_WORKERS_HELPER:-/usr/local/sbin/finops-ensure-runtime-workers}"', script)
        self.assertIn('DEPLOY_CONTROL_HELPER="${FINOPS_DEPLOY_CONTROL_HELPER:-/usr/local/sbin/finops-deploy-control}"', script)
        self.assertIn("self-update <release-name>", script)
        self.assertIn("install_deploy_control_helper", script)
        self.assertIn("install_runtime_worker_helper", script)
        self.assertIn('install_runtime_worker_helper "$src"', script)
        self.assertIn('ensure_runtime_workers "$src"', script)
        self.assertIn('"$ENSURE_RUNTIME_WORKERS_HELPER" "$src"', script)
        self.assertIn("wait_required_workers_ready", script)
        self.assertIn("read-model-scope-contract <release-name> [args]", script)
        self.assertIn("read_model_scope_contract()", script)
        self.assertIn('run_with_runtime_env "$src" "$src/scripts/check-read-model-scope-contracts.py" "$@"', script)
        self.assertIn("read-model-slo-smoke <release-name> [args]", script)
        self.assertIn("read_model_slo_smoke()", script)
        self.assertIn("read-model-slo-smoke only permits dry-run through deploy-control", script)
        self.assertIn('run_with_runtime_env "$src" -m fin_ops_platform.tools.read_model_slo_smoke "$@"', script)
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


if __name__ == "__main__":
    unittest.main()
