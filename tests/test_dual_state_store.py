from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from fin_ops_platform.services.dual_state_store import (
    PRIMARY_ONLY_FILE_WRITE_METHODS,
    DualStateStore,
    DualWriteMirrorError,
)


class FakeStore:
    def __init__(self, *, fail_methods: dict[str, Exception] | None = None, name: str = "store") -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.fail_methods = fail_methods or {}
        self.name = name
        self.data_dir = Path("/tmp/fake")
        self.storage_backend = f"{name}_backend"
        self.storage_mode = f"{name}_mode"
        self.mongo_database_name = None

    def _record(self, method: str, *args: Any, **kwargs: Any) -> str:
        self.calls.append((method, args, kwargs))
        failure = self.fail_methods.get(method)
        if failure is not None:
            raise failure
        return f"{self.name}:{method}:ok"

    def load_app_settings(self) -> dict[str, Any]:
        self.calls.append(("load_app_settings", (), {}))
        return {"source": self.name}

    def save_app_settings(self, *args: Any, **kwargs: Any) -> str:
        return self._record("save_app_settings", *args, **kwargs)

    def save_background_jobs(self, *args: Any, **kwargs: Any) -> str:
        return self._record("save_background_jobs", *args, **kwargs)

    def save_workbench_read_models(self, *args: Any, **kwargs: Any) -> str:
        return self._record("save_workbench_read_models", *args, **kwargs)

    def store_import_file(self, *args: Any, **kwargs: Any) -> str:
        return self._record("store_import_file", *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        if name == "save" or name.startswith("save_") or name.startswith("store_"):
            return lambda *args, **kwargs: self._record(name, *args, **kwargs)
        raise AttributeError(name)


class DualStateStoreTests(unittest.TestCase):
    def test_non_strict_mirror_failure_returns_primary_success_and_records_summary(self) -> None:
        primary = FakeStore(name="primary")
        mirror = FakeStore(
            name="mirror",
            fail_methods={"save_app_settings": RuntimeError("mirror unavailable")},
        )
        events: list[dict[str, Any]] = []
        store = DualStateStore(primary, mirror, callback=events.append, operation_id_factory=lambda: "op-1")

        result = store.save_app_settings({"admin_usernames": ["admin"]})

        self.assertEqual(result, "primary:save_app_settings:ok")
        self.assertEqual(primary.calls[0][0], "save_app_settings")
        self.assertEqual(mirror.calls[0][0], "save_app_settings")
        self.assertEqual(
            store.dual_write_summary(),
            {
                "primary_success": 1,
                "primary_failed": 0,
                "mirror_success": 0,
                "mirror_failed": 1,
                "strict_failures": 0,
                "last_failure": {
                    "operation_id": "op-1",
                    "method": "save_app_settings",
                    "stage": "mirror",
                    "error": "RuntimeError: mirror unavailable",
                    "strict": False,
                },
                "primary_only": 0,
                "primary_only_methods": [],
            },
        )
        self.assertEqual(events[-1]["status"], "mirror_failed")

    def test_strict_mirror_failure_raises_clear_exception(self) -> None:
        primary = FakeStore(name="primary")
        mirror = FakeStore(
            name="mirror",
            fail_methods={"save_background_jobs": RuntimeError("mirror refused")},
        )
        store = DualStateStore(primary, mirror, strict=True, operation_id_factory=lambda: "op-2")

        with self.assertRaisesRegex(DualWriteMirrorError, "Dual write mirror failed"):
            store.save_background_jobs({"job-1": {"status": "queued"}})

        summary = store.dual_write_summary()
        self.assertEqual(summary["primary_success"], 1)
        self.assertEqual(summary["mirror_failed"], 1)
        self.assertEqual(summary["strict_failures"], 1)
        self.assertEqual(summary["last_failure"]["stage"], "mirror")

    def test_primary_failure_does_not_call_mirror(self) -> None:
        primary = FakeStore(
            name="primary",
            fail_methods={"save_app_settings": RuntimeError("primary unavailable")},
        )
        mirror = FakeStore(name="mirror")
        store = DualStateStore(primary, mirror, operation_id_factory=lambda: "op-3")

        with self.assertRaisesRegex(RuntimeError, "primary unavailable"):
            store.save_app_settings({"admin_usernames": []})

        self.assertEqual(mirror.calls, [])
        summary = store.dual_write_summary()
        self.assertEqual(summary["primary_failed"], 1)
        self.assertEqual(summary["mirror_success"], 0)
        self.assertEqual(summary["last_failure"]["stage"], "primary")

    def test_write_preserves_args_and_kwargs_for_primary_and_mirror(self) -> None:
        primary = FakeStore(name="primary")
        mirror = FakeStore(name="mirror")
        store = DualStateStore(primary, mirror)
        payload = {"rows": {"case-1": {"case_id": "case-1"}}}
        changed_scope_keys = {"2026-05"}

        store.save_workbench_candidate_matches(payload, changed_scope_keys=changed_scope_keys)

        self.assertEqual(primary.calls, mirror.calls)
        self.assertIs(primary.calls[0][1][0], payload)
        self.assertIs(primary.calls[0][2]["changed_scope_keys"], changed_scope_keys)
        summary = store.dual_write_summary()
        self.assertEqual(summary["primary_success"], 1)
        self.assertEqual(summary["mirror_success"], 1)

    def test_all_required_write_methods_are_mirrored(self) -> None:
        methods = [
            "save",
            "save_app_settings",
            "save_tax_certified_imports",
            "save_etc_state",
            "save_etc_reconciliation_state",
            "save_workbench_pair_relations",
            "save_no_oa_bank_batches",
            "save_bank_transaction_categories",
            "save_turnover_relations",
            "save_workbench_candidate_matches",
            "save_background_jobs",
            "save_app_health_alerts",
        ]
        primary = FakeStore(name="primary")
        mirror = FakeStore(name="mirror")
        store = DualStateStore(primary, mirror)

        for method_name in methods:
            getattr(store, method_name)({"method": method_name})

        self.assertEqual([call[0] for call in primary.calls], methods)
        self.assertEqual([call[0] for call in mirror.calls], methods)
        summary = store.dual_write_summary()
        self.assertEqual(summary["primary_success"], len(methods))
        self.assertEqual(summary["mirror_success"], len(methods))

    def test_reads_delegate_to_primary_only(self) -> None:
        primary = FakeStore(name="primary")
        mirror = FakeStore(name="mirror")
        store = DualStateStore(primary, mirror)

        self.assertEqual(store.load_app_settings(), {"source": "primary"})

        self.assertEqual(primary.calls, [("load_app_settings", (), {})])
        self.assertEqual(mirror.calls, [])

    def test_file_writes_are_primary_only_and_summarized(self) -> None:
        primary = FakeStore(name="primary")
        mirror = FakeStore(name="mirror")
        operation_ids = iter(f"op-file-{index}" for index in range(10))
        store = DualStateStore(primary, mirror, operation_id_factory=lambda: next(operation_ids))

        for method_name in sorted(PRIMARY_ONLY_FILE_WRITE_METHODS):
            with self.subTest(method_name=method_name):
                result = getattr(store, method_name)(
                    session_id="session-1",
                    file_id="file-1",
                    file_name="upload.xlsx",
                    content=b"payload",
                )

                self.assertEqual(result, f"primary:{method_name}:ok")

        self.assertEqual([call[0] for call in primary.calls], sorted(PRIMARY_ONLY_FILE_WRITE_METHODS))
        self.assertEqual(mirror.calls, [])
        summary = store.dual_write_summary()
        self.assertEqual(summary["primary_success"], len(PRIMARY_ONLY_FILE_WRITE_METHODS))
        self.assertEqual(summary["mirror_success"], 0)
        self.assertEqual(summary["primary_only"], len(PRIMARY_ONLY_FILE_WRITE_METHODS))
        self.assertEqual(summary["primary_only_methods"], sorted(PRIMARY_ONLY_FILE_WRITE_METHODS))

    def test_failure_summary_redacts_secret_values(self) -> None:
        primary = FakeStore(name="primary")
        mirror = FakeStore(
            name="mirror",
            fail_methods={
                "save_app_settings": RuntimeError(
                    "failed postgresql://user:secret-password@db.example/fin_ops?token=abc"
                )
            },
        )
        store = DualStateStore(primary, mirror, operation_id_factory=lambda: "op-secret")

        store.save_app_settings({"database_url": "postgresql://user:secret-password@db.example/fin_ops"})

        summary_text = repr(store.dual_write_summary())
        self.assertNotIn("secret-password", summary_text)
        self.assertNotIn("token=abc", summary_text)
        self.assertIn("<redacted-uri>", summary_text)


if __name__ == "__main__":
    unittest.main()
