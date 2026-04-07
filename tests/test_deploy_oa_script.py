from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "deploy_oa.py"


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

        self.assertEqual(args.host, "139.155.5.132")
        self.assertEqual(args.user, "root")
        self.assertEqual(args.domain, "www.yn-sourcing.com")
        self.assertFalse(args.skip_build)
        self.assertFalse(args.skip_pip)
        self.assertFalse(args.reload_nginx)
        self.assertFalse(args.dry_run)

    def test_remote_script_uses_expected_targets(self) -> None:
        config = self.module.DeploymentConfig(
            host="139.155.5.132",
            user="root",
            domain="www.yn-sourcing.com",
            root_dir=Path("/Users/yu/Desktop/fin-ops-platform"),
            frontend_base_path="/fin-ops/",
            remote_frontend_dir="/www/wwwroot/fin-ops/dist",
            remote_backend_dir="/opt/fin-ops/current/backend",
            remote_service_name="fin-ops.service",
            remote_extract_root="/tmp/fin-ops-release",
            skip_build=False,
            skip_pip=False,
            reload_nginx=True,
            dry_run=False,
        )

        remote_script = self.module.build_remote_deploy_script(config)

        self.assertIn("/www/wwwroot/fin-ops/dist", remote_script)
        self.assertIn("/opt/fin-ops/current/backend", remote_script)
        self.assertIn("systemctl restart fin-ops.service", remote_script)
        self.assertIn("nginx -t", remote_script)
        self.assertIn("nginx -s reload", remote_script)
        self.assertIn("python3 -m venv /opt/fin-ops/venv", remote_script)

    def test_remote_script_can_skip_pip_and_nginx_reload(self) -> None:
        config = self.module.DeploymentConfig(
            host="139.155.5.132",
            user="root",
            domain="www.yn-sourcing.com",
            root_dir=Path("/Users/yu/Desktop/fin-ops-platform"),
            frontend_base_path="/fin-ops/",
            remote_frontend_dir="/www/wwwroot/fin-ops/dist",
            remote_backend_dir="/opt/fin-ops/current/backend",
            remote_service_name="fin-ops.service",
            remote_extract_root="/tmp/fin-ops-release",
            skip_build=True,
            skip_pip=True,
            reload_nginx=False,
            dry_run=False,
        )

        remote_script = self.module.build_remote_deploy_script(config)

        self.assertNotIn("pip install -r", remote_script)
        self.assertNotIn("nginx -s reload", remote_script)
        self.assertIn("systemctl restart fin-ops.service", remote_script)


if __name__ == "__main__":
    unittest.main()
