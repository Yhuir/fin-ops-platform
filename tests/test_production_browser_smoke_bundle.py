from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "package_production_browser_smoke.py"


def load_bundle_module():
    spec = importlib.util.spec_from_file_location("production_browser_smoke_bundle", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load package_production_browser_smoke.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ProductionBrowserSmokeBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_bundle_module()

    def test_bundle_contains_only_approved_files_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "production-browser-smoke.tar.gz"
            config = self.module.BundleConfig(
                root_dir=REPO_ROOT,
                output=output,
                release_name="dev-test-release",
                base_url="https://www.yn-sourcing.com",
            )

            manifest = self.module.create_production_browser_smoke_bundle(config)

            self.assertTrue(output.exists())
            with tarfile.open(output, "r:gz") as archive:
                names = sorted(archive.getnames())
                manifest_payload = json.loads(
                    archive.extractfile(self.module.MANIFEST_NAME).read().decode("utf-8")  # type: ignore[union-attr]
                )

        expected_files = [
            path.as_posix()
            for path in self.module.APPROVED_BUNDLE_FILES
            if (REPO_ROOT / path).is_file()
        ]
        self.assertEqual(names, sorted([*expected_files, self.module.MANIFEST_NAME]))
        self.assertEqual(manifest_payload["included_files"], expected_files)
        self.assertEqual(manifest_payload["release_name"], "dev-test-release")
        self.assertEqual(manifest_payload["base_url"], "https://www.yn-sourcing.com")
        self.assertEqual(manifest_payload["production_spec"], "web/e2e/production-route-shell.spec.ts")
        self.assertFalse(manifest_payload["normal_app_release_packaging_changed"])
        self.assertEqual(manifest, manifest_payload)

        for forbidden in (
            "node_modules",
            "web/dist",
            "production-admin-app-health.spec.ts",
            "playwright-report",
            "test-results",
        ):
            self.assertFalse(any(forbidden in name for name in names), forbidden)

    def test_manifest_hashes_match_bundle_sources_and_no_secret_values_are_embedded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "production-browser-smoke.tar.gz"
            config = self.module.BundleConfig(
                root_dir=REPO_ROOT,
                output=output,
                release_name="dev-test-release",
                base_url="https://www.yn-sourcing.com",
            )

            manifest = self.module.create_production_browser_smoke_bundle(config)

        for relative_path, digest in manifest["sha256_by_file"].items():
            self.assertEqual(digest, self.module._sha256(REPO_ROOT / relative_path))

        encoded_manifest = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "Admin-Token",
            "FIN_OPS_E2E_OA_TOKEN=",
            "password",
            "Bearer ",
            "FIN_OPS_POSTGRES",
        ):
            self.assertNotIn(forbidden, encoded_manifest)
        self.assertEqual(manifest["command_contract"]["env"]["FIN_OPS_E2E_OA_TOKEN"], "<in-memory-only>")
        self.assertEqual(manifest["artifact_redaction_contract"]["tokens_cookies_env_values"], "forbidden")


if __name__ == "__main__":
    unittest.main()
