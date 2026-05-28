from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "deploy_oa.py"
ENSURE_WORKERS_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "deploy" / "oa" / "bin" / "finops-ensure-runtime-workers.sh"
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

    def test_parser_defaults_match_oa_server(self) -> None:
        parser = self.module.build_parser()
        args = parser.parse_args([])

        self.assertEqual(args.mode, "release")
        self.assertEqual(args.host, "finops-prod")
        self.assertEqual(args.user, "finops-deploy")
        self.assertEqual(args.domain, "www.yn-sourcing.com")
        self.assertEqual(args.remote_releases_dir, "/opt/fin-ops/releases")
        self.assertEqual(args.deploy_control_path, "/usr/local/sbin/finops-deploy-control")
        self.assertEqual(args.keep_releases, 8)
        self.assertFalse(args.skip_build)
        self.assertFalse(args.skip_pip)
        self.assertFalse(args.reload_nginx)
        self.assertFalse(args.no_activate)
        self.assertFalse(args.dry_run)

    def test_release_remote_script_uses_versioned_release_and_deploy_control(self) -> None:
        config = self.module.DeploymentConfig(
            mode="release",
            host="finops-prod",
            user="finops-deploy",
            domain="www.yn-sourcing.com",
            root_dir=Path("/Users/yu/Desktop/fin-ops-platform"),
            frontend_base_path="/fin-ops/",
            remote_frontend_dir="/www/wwwroot/fin-ops/dist",
            remote_backend_dir="/opt/fin-ops/current/backend",
            remote_data_dir="/opt/fin-ops/data",
            remote_service_name="fin-ops.service",
            remote_extract_root="/tmp/fin-ops-release",
            remote_releases_dir="/opt/fin-ops/releases",
            release_name="main-abcdef1-20260524170000",
            deploy_control_path="/usr/local/sbin/finops-deploy-control",
            keep_releases=8,
            skip_build=False,
            skip_pip=False,
            reload_nginx=True,
            activate=True,
            allow_dirty=False,
            replace_release=False,
            dry_run=False,
        )

        remote_script = self.module.build_release_remote_deploy_script(config)

        self.assertIn("RELEASE_DIR=/opt/fin-ops/releases/main-abcdef1-20260524170000", remote_script)
        self.assertIn("tar -xzf - -C \"$RELEASE_DIR\"", remote_script)
        self.assertIn("sudo -n /usr/local/sbin/finops-deploy-control check-release main-abcdef1-20260524170000", remote_script)
        self.assertIn("sudo -n /usr/local/sbin/finops-deploy-control activate main-abcdef1-20260524170000", remote_script)
        self.assertIn("sudo -n /usr/local/sbin/finops-deploy-control status", remote_script)
        self.assertIn(
            'sudo -n /bin/bash "$RELEASE_DIR/src/deploy/oa/bin/finops-ensure-runtime-workers.sh" "$RELEASE_DIR/src"',
            remote_script,
        )
        self.assertIn("KEEP_RELEASES=8", remote_script)
        self.assertIn("sudo -n /usr/local/sbin/finops-deploy-control cleanup-releases --keep 8", remote_script)
        self.assertNotIn("/opt/fin-ops/current/backend", remote_script)
        self.assertNotIn("systemctl restart fin-ops.service", remote_script)
        self.assertNotIn("pip install -r", remote_script)

    def test_release_remote_script_can_upload_without_activation(self) -> None:
        config = self.module.DeploymentConfig(
            mode="release",
            host="finops-prod",
            user="finops-deploy",
            domain="www.yn-sourcing.com",
            root_dir=Path("/Users/yu/Desktop/fin-ops-platform"),
            frontend_base_path="/fin-ops/",
            remote_frontend_dir="/www/wwwroot/fin-ops/dist",
            remote_backend_dir="/opt/fin-ops/current/backend",
            remote_data_dir="/opt/fin-ops/data",
            remote_service_name="fin-ops.service",
            remote_extract_root="/tmp/fin-ops-release",
            remote_releases_dir="/opt/fin-ops/releases",
            release_name="main-abcdef1-20260524170000",
            deploy_control_path="/usr/local/sbin/finops-deploy-control",
            keep_releases=8,
            skip_build=True,
            skip_pip=True,
            reload_nginx=False,
            activate=False,
            allow_dirty=False,
            replace_release=False,
            dry_run=False,
        )

        remote_script = self.module.build_release_remote_deploy_script(config)

        self.assertIn("check-release main-abcdef1-20260524170000", remote_script)
        self.assertNotIn("activate main-abcdef1-20260524170000", remote_script)
        self.assertNotIn("finops-ensure-runtime-workers.sh", remote_script)
        self.assertNotIn("cleanup-releases", remote_script)

    def test_remote_command_quotes_multiline_script_for_ssh(self) -> None:
        config = self.module.DeploymentConfig(
            mode="release",
            host="finops-prod",
            user="finops-deploy",
            domain="www.yn-sourcing.com",
            root_dir=Path("/Users/yu/Desktop/fin-ops-platform"),
            frontend_base_path="/fin-ops/",
            remote_frontend_dir="/www/wwwroot/fin-ops/dist",
            remote_backend_dir="/opt/fin-ops/current/backend",
            remote_data_dir="/opt/fin-ops/data",
            remote_service_name="fin-ops.service",
            remote_extract_root="/tmp/fin-ops-release",
            remote_releases_dir="/opt/fin-ops/releases",
            release_name="main-abcdef1-20260524170000",
            deploy_control_path="/usr/local/sbin/finops-deploy-control",
            keep_releases=8,
            skip_build=True,
            skip_pip=True,
            reload_nginx=False,
            activate=False,
            allow_dirty=False,
            replace_release=False,
            dry_run=False,
        )
        remote_script = "set -euo pipefail\necho ok\n"

        command = self.module.build_remote_command(config, remote_script)

        self.assertEqual(command[-1], "bash -lc 'set -euo pipefail\necho ok\n'")
        self.assertNotIn("bash", command[-3:-1])

    def test_legacy_remote_script_keeps_previous_current_deploy_behavior(self) -> None:
        config = self.module.DeploymentConfig(
            mode="legacy-current",
            host="139.155.5.132",
            user="root",
            domain="www.yn-sourcing.com",
            root_dir=Path("/Users/yu/Desktop/fin-ops-platform"),
            frontend_base_path="/fin-ops/",
            remote_frontend_dir="/www/wwwroot/fin-ops/dist",
            remote_backend_dir="/opt/fin-ops/current/backend",
            remote_data_dir="/opt/fin-ops/data",
            remote_service_name="fin-ops.service",
            remote_extract_root="/tmp/fin-ops-release",
            remote_releases_dir="/opt/fin-ops/releases",
            release_name="main-abcdef1-20260524170000",
            deploy_control_path="/usr/local/sbin/finops-deploy-control",
            keep_releases=8,
            skip_build=True,
            skip_pip=True,
            reload_nginx=False,
            activate=True,
            allow_dirty=True,
            replace_release=False,
            dry_run=False,
        )

        remote_script = self.module.build_legacy_remote_deploy_script(config)

        self.assertNotIn("pip install -r", remote_script)
        self.assertNotIn("nginx -s reload", remote_script)
        self.assertIn("systemctl restart fin-ops.service", remote_script)
        self.assertIn("/opt/fin-ops/current/backend", remote_script)

    def test_runtime_worker_ensure_script_defaults_to_full_postgres_worker_matrix(self) -> None:
        script = ENSURE_WORKERS_SCRIPT_PATH.read_text()

        self.assertIn(
            "oa-sync workbench workbench-matching bank-detail search-pending invoice-usage-collection cost-tax import",
            script,
        )
        for instance_name in (
            "oa-sync",
            "workbench",
            "workbench-matching",
            "bank-detail",
            "search-pending",
            "invoice-usage-collection",
            "cost-tax",
            "import",
        ):
            self.assertIn(f"fin-ops.worker.{instance_name}.env.example", script)
            self.assertIn(f"fin-ops-worker@${{worker}}.service", script)


if __name__ == "__main__":
    unittest.main()
