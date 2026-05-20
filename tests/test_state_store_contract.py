from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.state_store import ApplicationStateStore


def unwrap_jsonb(value):
    return getattr(value, "obj", value)


class ContractFakePostgresConnection:
    def __init__(self) -> None:
        self.settings: dict[str, dict] = {}
        self.rows: dict[str, list[dict]] = {}

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        if "from app.app_settings" in sql:
            payload = self.settings.get(params[0])
            return {"settings_payload": payload} if payload is not None else None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        return []

    def execute(self, sql: str, params: tuple = ()) -> int:
        if "insert into app.app_settings" in sql:
            self.settings[params[0]] = unwrap_jsonb(params[1])
            return 1
        return 1


class StateStoreContractTests(unittest.TestCase):
    def _with_stores(self):
        temp_dirs: list[TemporaryDirectory] = []
        try:
            local_dir = TemporaryDirectory()
            temp_dirs.append(local_dir)
            yield "local", ApplicationStateStore(Path(local_dir.name))

            postgres_dir = TemporaryDirectory()
            temp_dirs.append(postgres_dir)
            yield "postgres", PostgresStateStore(
                data_dir=Path(postgres_dir.name),
                connection=ContractFakePostgresConnection(),
            )
        finally:
            for temp_dir in temp_dirs:
                temp_dir.cleanup()

    def test_state_store_basic_contract_round_trips(self) -> None:
        for name, store in self._with_stores():
            with self.subTest(store=name):
                settings = store.load_app_settings()
                self.assertEqual(settings["admin_usernames"], [])
                settings["admin_usernames"] = ["admin"]
                store.save_app_settings(settings)
                self.assertEqual(store.load_app_settings()["admin_usernames"], ["admin"])

                store.save({"workbench_pair_relations": {"pair_relations": {"case-1": {"case_id": "case-1"}}}})
                self.assertEqual(store.load()["workbench_pair_relations"]["pair_relations"]["case-1"]["case_id"], "case-1")

                manual_result = store.add_manual_oa_imports(["row-1", "row-1"], actor_id="tester", audit={})
                self.assertEqual(manual_result["imported"], ["row-1"])
                self.assertEqual(store.load_manual_oa_imports()["row_ids"], ["row-1"])
                self.assertTrue(store.remove_manual_oa_import("row-1", actor_id="tester"))
                self.assertEqual(store.load_manual_oa_imports()["row_ids"], [])

    def test_state_store_domain_snapshot_contract_round_trips(self) -> None:
        for name, store in self._with_stores():
            with self.subTest(store=name):
                store.save_background_jobs({"job-1": {"id": "job-1", "status": "running"}})
                self.assertEqual(store.load_background_jobs()["job-1"]["status"], "running")

                store.save_app_health_alerts({"records": {"alert-1": {"id": "alert-1", "status": "active"}}})
                self.assertEqual(store.load_app_health_alerts()["records"]["alert-1"]["status"], "active")

                store.save_workbench_pair_relations({"pair_relations": {"case-1": {"case_id": "case-1"}}})
                self.assertEqual(store.load_workbench_pair_relations()["pair_relations"]["case-1"]["case_id"], "case-1")

                store.save_no_oa_bank_batches({"batches": {"batch-1": {"batch_id": "batch-1"}}})
                self.assertEqual(store.load_no_oa_bank_batches()["batches"]["batch-1"]["batch_id"], "batch-1")

                store.save_turnover_relations({"relations": {"rel-1": {"relation_id": "rel-1"}}, "audit_log": []})
                self.assertEqual(store.load_turnover_relations()["relations"]["rel-1"]["relation_id"], "rel-1")

                store.save_tax_certified_imports({"sessions": {"session-1": {"id": "session-1"}}})
                self.assertEqual(store.load_tax_certified_imports()["sessions"]["session-1"]["id"], "session-1")

    def test_state_store_file_contract_round_trips_owned_files(self) -> None:
        for name, store in self._with_stores():
            with self.subTest(store=name):
                stored_path = store.store_import_file(
                    session_id="session-1",
                    file_id="file-1",
                    file_name="upload.xlsx",
                    content=b"payload",
                )
                self.assertEqual(store.read_import_file(stored_path), b"payload")
                self.assertEqual(store.delete_import_files([stored_path, stored_path]), 1)


if __name__ == "__main__":
    unittest.main()
