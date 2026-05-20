from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.shadow_state_store import ShadowStateStore


class FakeStore:
    storage_backend = "fake"
    storage_mode = "fake"
    mongo_database_name = None

    def __init__(self, *, data_dir: Path, snapshot: dict[str, object] | None = None, fail_shadow: bool = False) -> None:
        self.data_dir = data_dir
        self.snapshot = dict(snapshot or {})
        self.fail_shadow = fail_shadow
        self.calls: list[tuple[str, object]] = []

    def load_background_jobs(self) -> dict[str, object]:
        self.calls.append(("load_background_jobs", None))
        if self.fail_shadow:
            raise RuntimeError("shadow failed for postgresql://user:pass@db/app")
        return dict(self.snapshot)

    def save_background_jobs(self, snapshot: dict[str, object]) -> None:
        self.calls.append(("save_background_jobs", dict(snapshot)))
        self.snapshot = dict(snapshot)

    def read_import_file(self, stored_file_path: str) -> bytes:
        self.calls.append(("read_import_file", stored_file_path))
        if self.fail_shadow:
            raise RuntimeError("read failed")
        return b"primary-bytes" if self.snapshot.get("bytes") == "primary" else b"shadow-bytes"

    def import_batch_exists(self, batch_id: str) -> bool:
        self.calls.append(("import_batch_exists", batch_id))
        return bool(self.snapshot.get(batch_id))


class ShadowStateStoreTests(unittest.TestCase):
    def test_read_returns_primary_and_records_shadow_match(self) -> None:
        with TemporaryDirectory() as temp_dir:
            primary = FakeStore(data_dir=Path(temp_dir), snapshot={"job-1": {"status": "done"}})
            shadow = FakeStore(data_dir=Path(temp_dir), snapshot={"job-1": {"status": "done"}})
            store = ShadowStateStore(primary=primary, shadow=shadow, compare_enabled=True)

            self.assertEqual(store.load_background_jobs(), {"job-1": {"status": "done"}})
            self.assertEqual(
                store.shadow_summary(),
                {
                    "compared": 1,
                    "matched": 1,
                    "mismatched": 0,
                    "shadow_errors": 0,
                    "last_mismatch": None,
                    "last_error": None,
                },
            )

    def test_shadow_mismatch_does_not_block_primary_read(self) -> None:
        with TemporaryDirectory() as temp_dir:
            primary = FakeStore(data_dir=Path(temp_dir), snapshot={"job-1": {"status": "done"}})
            shadow = FakeStore(data_dir=Path(temp_dir), snapshot={"job-1": {"status": "failed"}})
            store = ShadowStateStore(primary=primary, shadow=shadow, compare_enabled=True)

            self.assertEqual(store.load_background_jobs(), {"job-1": {"status": "done"}})
            summary = store.shadow_summary()
            self.assertEqual(summary["compared"], 1)
            self.assertEqual(summary["matched"], 0)
            self.assertEqual(summary["mismatched"], 1)
            self.assertEqual(summary["shadow_errors"], 0)
            self.assertIsNotNone(summary["last_mismatch"])
            self.assertEqual(summary["last_mismatch"]["domain"], "load_background_jobs")

    def test_shadow_error_does_not_block_primary_read_and_is_redacted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            primary = FakeStore(data_dir=Path(temp_dir), snapshot={"job-1": {"status": "done"}})
            shadow = FakeStore(data_dir=Path(temp_dir), fail_shadow=True)
            store = ShadowStateStore(primary=primary, shadow=shadow, compare_enabled=True)

            self.assertEqual(store.load_background_jobs(), {"job-1": {"status": "done"}})
            summary = store.shadow_summary()
            self.assertEqual(summary["compared"], 0)
            self.assertEqual(summary["shadow_errors"], 1)
            self.assertIn("<redacted-uri>", summary["last_error"])
            self.assertNotIn("user:pass", summary["last_error"])

    def test_write_methods_are_primary_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            primary = FakeStore(data_dir=Path(temp_dir))
            shadow = FakeStore(data_dir=Path(temp_dir))
            store = ShadowStateStore(primary=primary, shadow=shadow, compare_enabled=True)

            store.save_background_jobs({"job-1": {"status": "done"}})

            self.assertEqual(primary.snapshot, {"job-1": {"status": "done"}})
            self.assertEqual(shadow.snapshot, {})
            self.assertEqual([call[0] for call in primary.calls], ["save_background_jobs"])
            self.assertEqual(shadow.calls, [])
            self.assertEqual(store.shadow_summary()["compared"], 0)

    def test_compare_disabled_skips_shadow_read(self) -> None:
        with TemporaryDirectory() as temp_dir:
            primary = FakeStore(data_dir=Path(temp_dir), snapshot={"job-1": {"status": "done"}})
            shadow = FakeStore(data_dir=Path(temp_dir), fail_shadow=True)
            store = ShadowStateStore(primary=primary, shadow=shadow, compare_enabled=False)

            self.assertEqual(store.load_background_jobs(), {"job-1": {"status": "done"}})
            self.assertEqual(shadow.calls, [])
            self.assertEqual(store.shadow_summary()["shadow_errors"], 0)

    def test_compare_sample_rate_can_skip_shadow_read(self) -> None:
        with TemporaryDirectory() as temp_dir:
            primary = FakeStore(data_dir=Path(temp_dir), snapshot={"job-1": {"status": "done"}})
            shadow = FakeStore(data_dir=Path(temp_dir), fail_shadow=True)
            store = ShadowStateStore(
                primary=primary,
                shadow=shadow,
                compare_enabled=True,
                compare_sample_rate=0.25,
                sample_decider=lambda: 0.75,
            )

            self.assertEqual(store.load_background_jobs(), {"job-1": {"status": "done"}})
            self.assertEqual(shadow.calls, [])
            self.assertEqual(store.shadow_summary()["shadow_errors"], 0)

    def test_exists_methods_are_compared(self) -> None:
        with TemporaryDirectory() as temp_dir:
            primary = FakeStore(data_dir=Path(temp_dir), snapshot={"batch-1": True})
            shadow = FakeStore(data_dir=Path(temp_dir), snapshot={"batch-1": False})
            store = ShadowStateStore(primary=primary, shadow=shadow, compare_enabled=True)

            self.assertTrue(store.import_batch_exists("batch-1"))

            summary = store.shadow_summary()
            self.assertEqual(summary["mismatched"], 1)
            self.assertEqual(summary["last_mismatch"]["domain"], "import_batch_exists")


if __name__ == "__main__":
    unittest.main()
