from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.state_store_protocol import settings_access_control_from_payload


def unwrap_jsonb(value):
    return getattr(value, "obj", value)


class ContractFakePostgresConnection:
    def __init__(self) -> None:
        self.settings: dict[str, dict] = {}
        self.rows: dict[str, dict[str, dict]] = {}

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        if "from app.app_settings" in sql:
            payload = self.settings.get(params[0])
            return {"settings_payload": payload} if payload is not None else None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized_sql = " ".join(sql.lower().split())
        if "from job.background_jobs" in normalized_sql:
            return [
                {"job_id": key, "raw_payload": payload}
                for key, payload in sorted(self.rows.get("job.background_jobs", {}).items())
            ]
        if "from app.workbench_pair_relations" in normalized_sql:
            return [
                {"key": key, "raw_payload": payload}
                for key, payload in sorted(self.rows.get("app.workbench_pair_relations", {}).items())
            ]
        if "from app.workbench_pair_relation_history" in normalized_sql:
            return []
        if "from audit.app_health_alerts" in normalized_sql:
            return [
                {"alert_id": key, "raw_payload": payload}
                for key, payload in sorted(self.rows.get("audit.app_health_alerts", {}).items())
            ]
        if "from app.no_oa_bank_batches" in normalized_sql:
            return [
                {"key": key, "raw_payload": payload}
                for key, payload in sorted(self.rows.get("app.no_oa_bank_batches", {}).items())
            ]
        if "from app.no_oa_bank_batch_events" in normalized_sql:
            return []
        if "from app.manual_oa_imports" in normalized_sql:
            return [
                {"row_id": key, "source": payload.get("source"), "raw_payload": {"normalized_payload": payload}}
                for key, payload in sorted(self.rows.get("app.manual_oa_imports", {}).items())
            ]
        if "from app.turnover_relations" in normalized_sql:
            return [
                {"key": key, "raw_payload": payload}
                for key, payload in sorted(self.rows.get("app.turnover_relations", {}).items())
            ]
        if "from app.turnover_relation_events" in normalized_sql:
            return []
        if "from app.tax_certified_import_sessions" in normalized_sql:
            return [
                {"key": key, "raw_payload": payload}
                for key, payload in sorted(self.rows.get("app.tax_certified_import_sessions", {}).items())
            ]
        if "from app.tax_certified_import_batches" in normalized_sql:
            return [
                {"key": key, "raw_payload": payload}
                for key, payload in sorted(self.rows.get("app.tax_certified_import_batches", {}).items())
            ]
        if "from app.tax_certified_import_records" in normalized_sql:
            return [
                {"key": key, "raw_payload": payload}
                for key, payload in sorted(self.rows.get("app.tax_certified_import_records", {}).items())
            ]
        return []

    def execute(self, sql: str, params: tuple = ()) -> int:
        normalized_sql = " ".join(sql.lower().split())
        if "insert into app.app_settings" in normalized_sql:
            self.settings[params[0]] = unwrap_jsonb(params[1])
            return 1
        if "insert into job.background_jobs" in normalized_sql:
            self._store_row("job.background_jobs", params[0], params[13])
            return 1
        if "insert into app.workbench_pair_relations" in normalized_sql:
            self._store_row("app.workbench_pair_relations", params[0], params[-1])
            return 1
        if "insert into audit.app_health_alerts" in normalized_sql:
            self._store_row("audit.app_health_alerts", params[0], params[-1])
            return 1
        if "insert into app.no_oa_bank_batches" in normalized_sql:
            self._store_row("app.no_oa_bank_batches", params[0], params[-1])
            return 1
        if "insert into app.manual_oa_imports" in normalized_sql:
            self._store_row("app.manual_oa_imports", params[0], params[-1])
            return 1
        if "update app.manual_oa_imports set status = 'inactive'" in normalized_sql:
            active_row_ids = set(params[0]) if params else set()
            if active_row_ids:
                self.rows["app.manual_oa_imports"] = {
                    key: payload
                    for key, payload in self.rows.get("app.manual_oa_imports", {}).items()
                    if key in active_row_ids
                }
            else:
                self.rows["app.manual_oa_imports"] = {}
            return 1
        if "insert into app.turnover_relations" in normalized_sql:
            self._store_row("app.turnover_relations", params[0], params[-1])
            return 1
        if "insert into app.tax_certified_import_sessions" in normalized_sql:
            self._store_row("app.tax_certified_import_sessions", params[1], params[-1])
            return 1
        if "insert into app.tax_certified_import_batches" in normalized_sql:
            self._store_row("app.tax_certified_import_batches", params[1], params[-1])
            return 1
        if "insert into app.tax_certified_import_records" in normalized_sql:
            self._store_row("app.tax_certified_import_records", params[1], params[-1])
            return 1
        return 1

    def _store_row(self, table: str, key: object, payload: object) -> None:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return
        self.rows.setdefault(table, {})[normalized_key] = unwrap_jsonb(payload)


class StateStoreContractTests(unittest.TestCase):
    def test_settings_access_control_uses_casefold_comparison_and_preserves_canonical_spelling(self) -> None:
        normalized = settings_access_control_from_payload(
            {
                "allowed_usernames": ["YNSYLP005", "Full.User", "Read.User"],
                "full_access_usernames": ["Full.User"],
                "readonly_export_usernames": ["Read.User"],
                "admin_usernames": ["YNSYLP005"],
            }
        )

        self.assertEqual(normalized["full_access_usernames"], ["Full.User"])
        self.assertEqual(normalized["readonly_export_usernames"], ["Read.User"])
        self.assertEqual(normalized["allowed_usernames"], ["YNSYLP005", "Full.User", "Read.User"])

    def test_settings_access_control_rejects_invalid_or_ambiguous_usernames(self) -> None:
        invalid_payloads = (
            {"full_access_usernames": [""]},
            {"full_access_usernames": ["FULL\x00USER"]},
            {"full_access_usernames": ["Full.User", "full.user"]},
            {
                "full_access_usernames": ["Full.User"],
                "readonly_export_usernames": ["full.user"],
            },
            {"full_access_usernames": ["ynsylp005"]},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                settings_access_control_from_payload(payload)

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
                self.assertEqual(settings["admin_usernames"], ["YNSYLP005"])
                self.assertIn("YNSYLP005", settings["allowed_usernames"])
                settings["admin_usernames"] = ["attacker"]
                store.save_app_settings(settings)
                self.assertEqual(store.load_app_settings()["admin_usernames"], ["YNSYLP005"])

                store.save({"workbench_pair_relations": {"pair_relations": {"case-1": {"case_id": "case-1"}}}})
                self.assertEqual(store.load()["workbench_pair_relations"]["pair_relations"]["case-1"]["case_id"], "case-1")

                manual_result = store.add_manual_oa_imports(["row-1", "row-1"], actor_id="tester", audit={})
                self.assertEqual(manual_result["imported"], ["row-1"])
                self.assertEqual(store.load_manual_oa_imports()["row_ids"], ["row-1"])
                self.assertTrue(store.remove_manual_oa_import("row-1", actor_id="tester"))
                self.assertEqual(store.load_manual_oa_imports()["row_ids"], [])

    def test_local_settings_acl_guard_uses_cas_and_mutation_proof(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))

            with store.begin_settings_acl_critical_section(1) as critical_section:
                self.assertEqual(critical_section.locked_current["access_control_version"], 1)
                committed = critical_section.commit(
                    {
                        "allowed_usernames": ["YNSYLP005", "user-a"],
                        "readonly_export_usernames": [],
                        "admin_usernames": ["YNSYLP005"],
                        "full_access_usernames": ["user-a"],
                    },
                    {"mutation_id": "mutation-1", "actor_id": "YNSYLP005"},
                )

            self.assertEqual(committed["access_control_version"], 2)
            self.assertEqual(store.load_app_settings()["full_access_usernames"], ["user-a"])
            recovery = store.recover_settings_acl_commit("mutation-1")
            self.assertTrue(recovery["audit_present"])
            self.assertEqual(recovery["access_control"], committed)

            with self.assertRaisesRegex(RuntimeError, "version conflict"):
                with store.begin_settings_acl_critical_section(1):
                    pass

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
                turnover_relations = store.load_turnover_relations()["relations"]
                if isinstance(turnover_relations, dict):
                    turnover_relation = turnover_relations["rel-1"]
                else:
                    turnover_relation = next(item for item in turnover_relations if item["relation_id"] == "rel-1")
                self.assertEqual(turnover_relation["relation_id"], "rel-1")

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
