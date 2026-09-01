import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fin_ops_platform.tools.settings_access_control_preflight as preflight
from fin_ops_platform.tools.settings_access_control_preflight import build_report, collect_database_facts


def _session(username: str, *, admin: bool, allowed: bool) -> dict[str, object]:
    return {
        "user": {"username": username},
        "can_access_app": allowed,
        "can_admin_access": admin,
        "allowed_page_keys": ["bank-details"] if allowed else [],
        "_preflight_http_status": 200,
        "_preflight_credential_source": "admin_stdin" if admin else "dedicated_bearer_stdin",
    }


class _ReadOnlyConnection:
    def fetch_one(self, sql: str, _params: tuple[object, ...]):
        if "settings_payload" in sql:
            return {"settings_payload": {"page_access_accounts": [], "access_control_version": 1}}
        if "schema_migrations" in sql:
            return {"applied": True}
        return {"present": True, "convalidated": True}


class _Cursor:
    def __init__(self, responses: list[list[tuple[object, ...]]]) -> None:
        self.responses = list(responses)
        self.rows: list[tuple[object, ...]] = []
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, params: object = ()) -> None:
        self.executed.append((sql, tuple(params or ())))
        if sql.lstrip().lower().startswith("select"):
            self.rows = self.responses.pop(0)

    def fetchall(self):
        return list(self.rows)


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_value = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class SettingsAccessControlPreflightTests(unittest.TestCase):
    def test_legacy_exact_state_is_cutover_eligible_and_secret_safe(self) -> None:
        report = build_report(
            release="main-page-access",
            database={
                "settings_payload": {
                    "full_access_usernames": ["YNSYLP006", "FULL001"],
                    "readonly_export_usernames": ["READ001"],
                    "admin_usernames": ["YNSYLP005"],
                },
                "migration_0165_applied": False,
                "constraint_present": False,
                "constraint_validated": False,
            },
            environment={"retired_admission_env_present": {}},
            oa_roles={
                "topology": "legacy",
                "user_members": ["FULL001", "YNSYLP006"],
                "admin_members": ["YNSYLP005"],
            },
            admin_session=_session("YNSYLP005", admin=True, allowed=True),
            bearer_session=_session("YNSYLP006", admin=False, allowed=True),
        )

        self.assertTrue(report["eligible"])
        self.assertEqual(report["state"], "cutover")
        self.assertTrue(report["oa"]["migration_required"])
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("FULL001", rendered)
        self.assertNotIn("YNSYLP006", rendered)

    def test_page_access_steady_state_requires_migration_guard(self) -> None:
        base = {
            "settings_payload": {
                "page_access_accounts": [{"username": "USER001", "page_keys": ["bank-details"]}],
                "access_control_version": 2,
            },
            "migration_0165_applied": True,
            "constraint_present": True,
            "constraint_validated": True,
        }
        report = build_report(
            release="main-page-access",
            database=base,
            environment={"retired_admission_env_present": {}},
            oa_roles={"topology": "page_access", "user_members": ["USER001"], "admin_members": ["YNSYLP005"]},
            admin_session=_session("YNSYLP005", admin=True, allowed=True),
            bearer_session=_session("YNSYLP006", admin=False, allowed=False),
        )
        self.assertTrue(report["eligible"])
        self.assertEqual(report["state"], "steady")

        report = build_report(
            release="main-page-access",
            database={**base, "constraint_validated": False},
            environment={"retired_admission_env_present": {}},
            oa_roles={"topology": "page_access", "user_members": ["USER001"], "admin_members": ["YNSYLP005"]},
            admin_session=_session("YNSYLP005", admin=True, allowed=True),
            bearer_session=_session("YNSYLP006", admin=False, allowed=False),
        )
        self.assertFalse(report["eligible"])
        self.assertIn("database_guard_incomplete", report["blockers"])

    def test_wrong_admin_or_oa_membership_blocks(self) -> None:
        report = build_report(
            release="main-page-access",
            database={
                "settings_payload": {"page_access_accounts": [], "access_control_version": 1},
                "migration_0165_applied": True,
                "constraint_present": True,
                "constraint_validated": True,
            },
            environment={"retired_admission_env_present": {}},
            oa_roles={"topology": "page_access", "user_members": ["ATTACKER"], "admin_members": ["ATTACKER"]},
            admin_session=_session("ATTACKER", admin=True, allowed=True),
            bearer_session=_session("YNSYLP006", admin=False, allowed=False),
        )
        self.assertFalse(report["eligible"])
        self.assertIn("admin_session_invalid", report["blockers"])
        self.assertIn("oa_membership_mismatch", report["blockers"])
        self.assertNotIn("ATTACKER", json.dumps(report, sort_keys=True))

    def test_database_facts_use_0165_guard(self) -> None:
        facts = collect_database_facts(_ReadOnlyConnection())
        self.assertTrue(facts["migration_0165_applied"])
        self.assertTrue(facts["constraint_present"])
        self.assertTrue(facts["constraint_validated"])

    def test_legacy_oa_topology_migrates_transactionally(self) -> None:
        cursor = _Cursor([
            [(99,)],
            [
                (10, "finops_read_export"),
                (11, "finops_full_access"),
                (12, "finops_admin"),
            ],
            [(10,), (11,), (12,)],
        ])
        connection = _Connection(cursor)
        with patch.object(preflight, "_oa_connect", return_value=connection):
            result = preflight.migrate_oa_role_topology()

        self.assertEqual(result, "migrated")
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        statements = "\n".join(sql for sql, _ in cursor.executed)
        self.assertIn("update sys_role set role_key", statements)
        self.assertIn("delete from sys_user_role", statements)

    def test_database_guard_cli_fails_closed_when_constraint_is_not_validated(self) -> None:
        with (
            patch.object(preflight, "collect_database_facts", return_value={
                "migration_0165_applied": True,
                "constraint_present": True,
                "constraint_validated": False,
            }),
            patch.object(preflight, "_postgres_settings", return_value=object()),
            patch.object(preflight, "PostgresConnection", return_value=object()),
        ):
            status = preflight.main(["--release", "main-safe", "--database-guard-only", "--json"])
        self.assertEqual(status, 2)

    def test_post_deploy_writes_secret_safe_failure_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            preflight_path = Path(temp_dir) / "preflight.json"
            output_path = Path(temp_dir) / "post.json"
            preflight_path.write_text(json.dumps({"release": "r1", "eligible": False}), encoding="utf-8")
            report, status = preflight.run_post_deploy(
                release="r1",
                base_url="http://127.0.0.1:1",
                preflight_path=str(preflight_path),
                output_path=str(output_path),
                admin_token="admin-secret",
                bearer_token="bearer-secret",
                oa_base_url="https://oa.example.test",
            )
            rendered = output_path.read_text(encoding="utf-8")
        self.assertEqual(status, 2)
        self.assertEqual(report["status"], "fail")
        self.assertNotIn("admin-secret", rendered)
        self.assertNotIn("bearer-secret", rendered)


if __name__ == "__main__":
    unittest.main()
