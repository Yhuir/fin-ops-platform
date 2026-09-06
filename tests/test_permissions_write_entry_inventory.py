from __future__ import annotations

import inspect
from pathlib import Path
import re
import unittest

from fin_ops_platform.app.route_access_policy import missing_page_keys, registered_page_keys
from fin_ops_platform.services.access_control_service import (
    ALL_PAGE_KEYS,
    ASSIGNABLE_PAGE_KEYS,
    AccessControlService,
)
from fin_ops_platform.services.app_settings_service import AppSettingsService


REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_REGISTRY_PATH = REPO_ROOT / "web/src/app/pageRegistry.tsx"


def _frontend_page_keys() -> set[str]:
    registry = PAGE_REGISTRY_PATH.read_text(encoding="utf-8")
    definitions = re.search(
        r"export const appPageDefinitions: AppPageDefinition\[] = \[(?P<body>.*?)\];",
        registry,
        re.DOTALL,
    )
    if definitions is None:
        raise AssertionError("Could not find appPageDefinitions in pageRegistry.tsx")
    return set(re.findall(r'pageKey:\s*"([^"]+)"', definitions.group("body")))


class PermissionsWriteEntryInventoryTests(unittest.TestCase):
    def test_page_keys_have_one_frontend_and_backend_contract(self) -> None:
        # Cash backend ships before its UI. No ordinary page may disappear or
        # silently gain an unregistered backend permission during this rollout.
        self.assertEqual(_frontend_page_keys(), set(ALL_PAGE_KEYS) - {"cash"})
        self.assertEqual(registered_page_keys(), ALL_PAGE_KEYS)
        self.assertEqual(missing_page_keys(), frozenset())
        self.assertNotIn("operation-history", ASSIGNABLE_PAGE_KEYS)

    def test_authorization_uses_only_the_canonical_page_snapshot(self) -> None:
        evaluator_source = inspect.getsource(AccessControlService.evaluate)
        provider_source = inspect.getsource(AccessControlService._load_access_control_snapshot)

        self.assertEqual(provider_source.count("provider()"), 1)
        for token in ("identity.roles", "identity.permissions", "os.getenv"):
            with self.subTest(token=token):
                self.assertNotIn(token, evaluator_source)

    def test_legacy_tier_fields_are_absent_from_the_runtime_authorization_chain(self) -> None:
        runtime_paths = (
            REPO_ROOT / "backend/src/fin_ops_platform/app/auth.py",
            REPO_ROOT / "backend/src/fin_ops_platform/app/server.py",
            REPO_ROOT / "backend/src/fin_ops_platform/services/access_control_service.py",
            REPO_ROOT / "backend/src/fin_ops_platform/services/state_store_protocol.py",
            REPO_ROOT / "web/src/features/session/api.ts",
            REPO_ROOT / "web/src/contexts/SessionContext.tsx",
        )
        source = "\n".join(path.read_text(encoding="utf-8") for path in runtime_paths)
        for token in ("access_tier", "can_mutate_data", "read_export_only", "full_access"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_acl_authorization_adds_no_cache_queue_or_worker_io(self) -> None:
        evaluator_source = inspect.getsource(AccessControlService.evaluate)
        generic_save_source = inspect.getsource(AppSettingsService.update_settings)
        acl_save_source = inspect.getsource(AppSettingsService.update_access_control)

        self.assertNotIn("_oa_role_sync_service", generic_save_source)
        no_op_return = acl_save_source.index('return {"changed": False')
        self.assertLess(no_op_return, acl_save_source.index("sync_access_control"))
        self.assertLess(no_op_return, acl_save_source.index("critical_section.commit"))
        for token in (
            "enqueue_read_model_refresh",
            "outbox_events",
            "read_model_dirty_scopes",
            "redis",
            "cache",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, evaluator_source + acl_save_source)


if __name__ == "__main__":
    unittest.main()
