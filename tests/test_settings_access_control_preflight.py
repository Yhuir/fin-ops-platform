from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import fin_ops_platform.tools.settings_access_control_preflight as preflight_module
from fin_ops_platform.tools.settings_access_control_preflight import (
    build_report,
    collect_database_facts,
    run_post_deploy,
)
from fin_ops_platform.services.postgres_connection import PostgresSettings


class _ReadOnlyConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def fetch_one(self, sql: str, params: tuple[object, ...]):
        self.queries.append(sql)
        if "settings_payload from app.app_settings" in sql:
            return {
                "settings_payload": {
                    "allowed_usernames": ["YNSYLP005", "FULL001"],
                    "readonly_export_usernames": [],
                    "full_access_usernames": ["FULL001"],
                    "admin_usernames": ["YNSYLP005"],
                    "access_control_version": 2,
                }
            }
        if "schema_migrations" in sql:
            return {"applied": True}
        return {"present": True, "convalidated": True}


def _session(
    username: str,
    tier: str,
    admin: bool,
    *,
    credential_source: str | None = None,
) -> dict[str, object]:
    return {
        "user": {"username": username},
        "permissions": [] if admin else ["finops:app:view"],
        "access_tier": tier,
        "can_admin_access": admin,
        "_preflight_http_status": 200,
        "_preflight_credential_source": credential_source or (
            "admin_stdin" if admin else "dedicated_bearer_stdin"
        ),
    }


class SettingsAccessControlPreflightTests(unittest.TestCase):
    @staticmethod
    def _oa_inventory(*, extra_bindings: list[dict[str, object]] | None = None):
        return {
            "enabled": True,
            "required_permission": "finops:app:view",
            "menu_ids": [101],
            "role_ids": {
                "read_export_only": [201],
                "full_access": [202],
                "admin": [203],
            },
            "bindings": [
                {"role_id": 201, "menu_id": 101, "role_key": "finops_read_export"},
                {"role_id": 202, "menu_id": 101, "role_key": "finops_full_access"},
                {"role_id": 203, "menu_id": 101, "role_key": "finops_admin"},
                *(extra_bindings or []),
            ],
            "members": {
                "read_export_only": [],
                "full_access": ["FULL001"],
                "admin": ["YNSYLP005"],
            },
        }

    def _report(self, **overrides):
        arguments = {
            "release": "main-security-test",
            "database": {
                "settings_payload": {
                    "allowed_usernames": ["YNSYLP005", "FULL001"],
                    "readonly_export_usernames": [],
                    "full_access_usernames": ["FULL001"],
                    "admin_usernames": ["YNSYLP005"],
                    "access_control_version": 2,
                },
                "migration_0132_applied": True,
                "constraint_present": True,
                "constraint_validated": True,
            },
            "environment": {},
            "oa_roles": self._oa_inventory(),
            "admin_session": _session("YNSYLP005", "admin", True),
            "bearer_session": _session("YNSYLP006", "denied", False),
        }
        arguments.update(overrides)
        return build_report(**arguments)

    def test_eligible_report_contains_only_hashed_nonprotected_identities(self) -> None:
        report = self._report()

        self.assertTrue(report["eligible"])
        self.assertTrue(report["cutover_eligible"])
        self.assertEqual(report["state"], "steady")
        self.assertEqual(report["blockers"], [])
        rendered = str(report)
        self.assertNotIn("FULL001", rendered)
        self.assertNotIn("YNSYLP006", rendered)
        self.assertNotIn("postgresql://", rendered)
        self.assertEqual(report["protected_administrator"], "YNSYLP005")
        self.assertTrue(report["oa"]["matches_target"])

    def test_illegal_admin_is_reported_as_dry_run_cleanup_without_becoming_runtime_admin(self) -> None:
        database = dict(self._report()["database"])
        database["settings_payload"] = {
            "allowed_usernames": ["YNSYLP005", "ATTACKER"],
            "readonly_export_usernames": [],
            "full_access_usernames": [],
            "admin_usernames": ["YNSYLP005", "ATTACKER"],
            "access_control_version": 1,
        }

        report = self._report(database=database, oa_roles={"enabled": False, "members": {}})

        self.assertFalse(report["eligible"])
        self.assertTrue(report["dry_run_cleanup"]["required"])
        self.assertEqual(report["dry_run_cleanup"]["removed_admin_count"], 1)
        self.assertNotIn("ATTACKER", str(report))

    def test_wrong_or_reused_http_identities_fail_closed(self) -> None:
        cases = (
            {"admin_session": _session("OTHER", "admin", True)},
            {"bearer_session": _session("YNSYLP005", "denied", False)},
            {"bearer_session": _session("SLO_FULL", "full_access", False)},
            {"bearer_session": _session("YNSYLP005", "admin", True)},
            {
                "bearer_session": _session(
                    "SLO_DENIED",
                    "denied",
                    False,
                    credential_source="admin_stdin",
                )
            },
        )
        for override in cases:
            with self.subTest(override=override):
                self.assertFalse(self._report(**override)["eligible"])

    def test_representative_bearer_requires_exact_006_with_menu_permission(self) -> None:
        wrong_username = _session("SLO_DENIED", "denied", False)
        missing_permission = _session("YNSYLP006", "denied", False)
        missing_permission["permissions"] = []

        self.assertFalse(self._report(bearer_session=wrong_username)["eligible"])
        self.assertFalse(self._report(bearer_session=missing_permission)["eligible"])
        self.assertTrue(self._report()["sessions"]["bearer"]["oa_menu_permission_present"])

    def test_database_guard_only_fails_closed_until_0132_check_is_validated(self) -> None:
        with (
            patch.object(
                preflight_module,
                "collect_database_facts",
                return_value={
                    "migration_0132_applied": True,
                    "constraint_present": True,
                    "constraint_validated": False,
                },
            ),
            patch.object(preflight_module, "_postgres_settings", return_value=object()),
            patch.object(preflight_module, "PostgresConnection", return_value=object()),
        ):
            status = preflight_module.main(
                ["--release", "main-safe", "--database-guard-only", "--json"]
            )

        self.assertEqual(status, 2)

    def test_oa_role_drift_fails_closed(self) -> None:
        oa_roles = self._oa_inventory()
        oa_roles["members"]["admin"] = ["YNSYLP005", "ATTACKER"]
        report = self._report(oa_roles=oa_roles)

        self.assertFalse(report["eligible"])
        self.assertFalse(report["oa"]["matches_target"])
        self.assertNotIn("ATTACKER", str(report))

    def test_fixed_menu_inventory_emits_exact_hashed_cleanup_and_rollback_targets(self) -> None:
        report = self._report(
            oa_roles=self._oa_inventory(
                extra_bindings=[
                    {"role_id": 987654, "menu_id": 101, "role_key": "business_accounting"}
                ]
            )
        )

        self.assertFalse(report["eligible"])
        self.assertTrue(report["oa"]["cleanup_eligible"])
        cleanup = report["oa"]["menu_binding_cleanup"]
        self.assertEqual(cleanup["target_count"], 1)
        self.assertEqual(cleanup["rollback_target_hashes"], cleanup["target_hashes"])
        self.assertRegex(cleanup["before_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(cleanup["after_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(cleanup["target_hashes"][0], r"^[0-9a-f]{64}$")
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("business_accounting", rendered)
        self.assertNotIn("987654", rendered)

    def test_selector_role_sync_menu_roles_bindings_and_members_fail_closed(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = []

        disabled = self._oa_inventory()
        disabled["enabled"] = False
        cases.append(("disabled", disabled))

        for selector in ("", "finops:other:view"):
            inventory = self._oa_inventory()
            inventory["required_permission"] = selector
            cases.append((f"selector={selector!r}", inventory))

        duplicate_menu = self._oa_inventory()
        duplicate_menu["menu_ids"] = [101, 102]
        cases.append(("duplicate menu", duplicate_menu))

        duplicate_role = self._oa_inventory()
        duplicate_role["role_ids"]["admin"] = [203, 204]
        cases.append(("duplicate role", duplicate_role))

        missing_binding = self._oa_inventory()
        missing_binding["bindings"] = missing_binding["bindings"][:-1]
        cases.append(("missing binding", missing_binding))

        member_drift = self._oa_inventory()
        member_drift["members"]["full_access"] = []
        cases.append(("member drift", member_drift))

        for name, oa_roles in cases:
            with self.subTest(name=name):
                report = self._report(oa_roles=oa_roles)
                self.assertFalse(report["eligible"])
                self.assertFalse(report["oa"]["cleanup_eligible"])

    def test_retired_app_admission_environment_presence_blocks_release(self) -> None:
        for name in (
            "FIN_OPS_ALLOWED_USERNAMES",
            "FIN_OPS_ALLOWED_ROLES",
            "FIN_OPS_READONLY_EXPORT_USERNAMES",
        ):
            with self.subTest(name=name):
                report = self._report(environment={"retired_admission_env_present": {name: True}})
                self.assertFalse(report["eligible"])
                self.assertEqual(report["environment"]["retired_admission_env_present"], [name])

    def test_exact_legacy_runtime_state_is_cutover_eligible_before_migration_and_env_cleanup(self) -> None:
        report = self._report(
            database={
                "settings_payload": {
                    "allowed_usernames": ["YNSYLP005", "FULL001"],
                    "readonly_export_usernames": [],
                    "full_access_usernames": ["FULL001"],
                    "admin_usernames": ["YNSYLP005"],
                    "access_control_version": 2,
                },
                "migration_0132_applied": False,
                "constraint_present": False,
                "constraint_validated": False,
            },
            environment={
                "admin_usernames": ["YNSYLP005"],
                "retired_admission_env_present": {
                    "FIN_OPS_ALLOWED_USERNAMES": True,
                    "FIN_OPS_ALLOWED_ROLES": True,
                    "FIN_OPS_READONLY_EXPORT_USERNAMES": True,
                },
            },
            bearer_session=_session("YNSYLP006", "full_access", False),
        )

        self.assertFalse(report["eligible"])
        self.assertTrue(report["cutover_eligible"])
        self.assertEqual(report["state"], "cutover")
        self.assertEqual(report["database"]["state"], "pending")
        self.assertEqual(report["environment"]["state"], "cutover")
        self.assertTrue(report["sessions"]["bearer"]["absent_from_canonical_acl"])
        self.assertNotIn("YNSYLP006", json.dumps(report, sort_keys=True))

    def test_cutover_blocks_representative_bearer_present_in_any_canonical_acl_list(self) -> None:
        for field in (
            "allowed_usernames",
            "readonly_export_usernames",
            "full_access_usernames",
            "admin_usernames",
        ):
            with self.subTest(field=field):
                settings = {
                    "allowed_usernames": ["YNSYLP005", "FULL001"],
                    "readonly_export_usernames": [],
                    "full_access_usernames": ["FULL001"],
                    "admin_usernames": ["YNSYLP005"],
                    "access_control_version": 2,
                }
                settings[field] = [*settings[field], "YNSYLP006"]
                report = self._report(
                    database={
                        "settings_payload": settings,
                        "migration_0132_applied": False,
                        "constraint_present": False,
                        "constraint_validated": False,
                    },
                    bearer_session=_session("YNSYLP006", "full_access", False),
                )

                self.assertFalse(report["cutover_eligible"])
                self.assertIn("bearer_present_in_canonical_acl", report["blockers"])

    def test_cutover_blocks_partial_0132_database_state(self) -> None:
        report = self._report(
            database={
                "settings_payload": {
                    "allowed_usernames": ["YNSYLP005", "FULL001"],
                    "readonly_export_usernames": [],
                    "full_access_usernames": ["FULL001"],
                    "admin_usernames": ["YNSYLP005"],
                    "access_control_version": 2,
                },
                "migration_0132_applied": True,
                "constraint_present": False,
                "constraint_validated": False,
            }
        )

        self.assertFalse(report["cutover_eligible"])
        self.assertEqual(report["database"]["state"], "partial")
        self.assertIn("database_partial", report["blockers"])

    def test_cutover_allows_only_empty_or_fixed_legacy_admin_environment(self) -> None:
        fixed = self._report(environment={"admin_usernames": ["YNSYLP005"]})
        other = self._report(environment={"admin_usernames": ["ATTACKER"]})

        self.assertTrue(fixed["cutover_eligible"])
        self.assertFalse(other["cutover_eligible"])
        self.assertIn("legacy_admin_not_fixed", other["blockers"])
        self.assertNotIn("ATTACKER", str(other))

    def test_cutover_blocks_unknown_retired_environment_keys_without_disclosing_name(self) -> None:
        report = self._report(
            environment={"retired_admission_env_present": {"FIN_OPS_UNKNOWN_ADMISSION": True}}
        )

        self.assertFalse(report["cutover_eligible"])
        self.assertIn("retired_env_unknown", report["blockers"])
        self.assertEqual(report["environment"]["unknown_retired_admission_env_count"], 1)
        self.assertNotIn("FIN_OPS_UNKNOWN_ADMISSION", str(report))

    def test_legacy_runtime_admin_environment_fails_closed_and_is_redacted(self) -> None:
        report = self._report(environment={"admin_usernames": ["ATTACKER"]})

        self.assertFalse(report["eligible"])
        self.assertEqual(report["environment"]["legacy_admin_member_count"], 1)
        self.assertNotIn("ATTACKER", str(report))

    def test_database_collector_executes_only_select_statements(self) -> None:
        connection = _ReadOnlyConnection()

        facts = collect_database_facts(connection)

        self.assertTrue(facts["migration_0132_applied"])
        self.assertTrue(facts["constraint_validated"])
        self.assertEqual(len(connection.queries), 3)
        for query in connection.queries:
            normalized = " ".join(query.lower().split())
            self.assertTrue(normalized.startswith("select"))
            self.assertNotRegex(normalized, r"\b(update|insert|delete|alter|drop|create)\b")

    def test_oa_collector_executes_only_fixed_selector_selects(self) -> None:
        queries: list[tuple[str, tuple[object, ...]]] = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, sql: str, params: tuple[object, ...]):
                queries.append((sql, params))

            def fetchall(self):
                sql = " ".join(queries[-1][0].lower().split())
                if "from sys_menu" in sql and "sys_role_menu" not in sql:
                    return [(101,)]
                if "from sys_role where" in sql:
                    return [(203, "finops_admin"), (202, "finops_full_access"), (201, "finops_read_export")]
                if "from sys_role_menu" in sql:
                    return [
                        (201, 101, "finops_read_export"),
                        (202, 101, "finops_full_access"),
                        (203, 101, "finops_admin"),
                    ]
                return [("FULL001", "finops_full_access"), ("YNSYLP005", "finops_admin")]

        class Connection:
            def cursor(self):
                return Cursor()

            def close(self):
                return None

        pymysql = types.ModuleType("pymysql")
        pymysql.connect = lambda **_kwargs: Connection()
        environment = {
            "FIN_OPS_OA_ROLE_SYNC_ENABLED": "1",
            "FIN_OPS_OA_REQUIRED_PERMISSION": "finops:app:view",
            "FIN_OPS_OA_ROLE_SYNC_HOST": "oa-db",
            "FIN_OPS_OA_ROLE_SYNC_DATABASE": "oa",
            "FIN_OPS_OA_ROLE_SYNC_USERNAME": "reader",
            "FIN_OPS_OA_ROLE_SYNC_PASSWORD": "secret",
        }
        with (
            patch.dict(preflight_module.os.environ, environment, clear=True),
            patch.dict(sys.modules, {"pymysql": pymysql}),
        ):
            facts = preflight_module.collect_oa_role_facts()

        self.assertTrue(facts["configured"])
        self.assertEqual(facts["menu_ids"], [101])
        self.assertEqual(len(queries), 4)
        for sql, params in queries:
            normalized = " ".join(sql.lower().split())
            self.assertTrue(normalized.startswith("select"))
            self.assertNotRegex(normalized, r"\b(update|insert|delete|alter|drop|create)\b")
            if "sys_menu" in normalized:
                self.assertIn("finops:app:view", params)

    def test_preflight_prefers_root_only_migrator_database_url(self) -> None:
        runtime = PostgresSettings(database_url="postgresql://runtime")
        with (
            patch.object(preflight_module.PostgresSettings, "from_env", return_value=runtime),
            patch.dict(
                preflight_module.os.environ,
                {"FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL": "postgresql://migrator"},
            ),
        ):
            settings = preflight_module._postgres_settings()

        self.assertEqual(settings.database_url, "postgresql://migrator")

    def test_post_deploy_role_matrix_restores_bearer_and_emits_redacted_evidence(self) -> None:
        state = {
            "tier": "denied",
            "version": 1,
            "accounts": [{"username": "FULL001", "access_tier": "full_access"}],
            "request": 0,
        }

        def response(status: int, payload: dict[str, object] | None = None, request_id: str = ""):
            return {"status": status, "payload": payload or {}, "elapsed_ms": 1.0, "request_id": request_id}

        def http_request(*, method: str, path: str, token: str, payload=None, **_kwargs):
            if path == "/api/session/me":
                if token == "admin-token":
                    return response(
                        200,
                        {
                            "user": {"username": "YNSYLP005"},
                            "access_tier": "admin",
                            "can_admin_access": True,
                            "can_mutate_data": True,
                            "can_access_app": True,
                        },
                    )
                tier = state["tier"]
                return response(
                    200,
                    {
                        "user": {"username": "YNSYLP006"},
                        "permissions": ["finops:app:view"],
                        "access_tier": tier,
                        "can_admin_access": False,
                        "can_mutate_data": tier == "full_access",
                        "can_access_app": tier != "denied",
                    },
                )
            if path == "/system/menu/getRouters":
                visible = token == "admin-token" or state["tier"] != "denied"
                return response(
                    200,
                    {
                        "code": 200,
                        "data": (
                            [
                                {
                                    "path": "https://www.yn-sourcing.com/fin-ops/?embedded=oa",
                                    "meta": {"title": "财务运营平台"},
                                }
                            ]
                            if visible
                            else []
                        ),
                    },
                )
            if path == "/api/workbench/settings/access-control" and method == "GET":
                return response(
                    200,
                    {
                        "version": state["version"],
                        "administrator": {
                            "username": "YNSYLP005",
                            "access_tier": "admin",
                            "protected": True,
                        },
                        "accounts": list(state["accounts"]),
                    },
                )
            if path == "/api/workbench/settings/access-control" and method == "PUT":
                if token != "admin-token":
                    return response(403, {"error": "admin_only"})
                state["accounts"] = list(payload["accounts"])
                account = next(
                    (item for item in state["accounts"] if item["username"] == "YNSYLP006"),
                    None,
                )
                state["tier"] = account["access_tier"] if account else "denied"
                state["version"] += 1
                state["request"] += 1
                return response(
                    200,
                    {"changed": True, "version": state["version"]},
                    f"{state['request']:012x}",
                )
            if path == "/api/workbench/settings" and method == "GET":
                return response(
                    200,
                    {
                        "projects": {"completed_project_ids": []},
                        "bank_account_mappings": [],
                        "workbench_column_layouts": {},
                        "oa_retention": {},
                        "oa_import": {},
                        "oa_invoice_offset": {},
                    },
                )
            if path == "/api/workbench/settings" and method == "POST":
                if state["tier"] != "full_access":
                    return response(403, {"error": "permission_denied"})
                if "admin_usernames" in payload:
                    return response(400, {"error": "access_control_write_forbidden"})
                return response(200, {})
            if token != "admin-token":
                return response(403, {"error": "admin_only"})
            if path == "/api/workbench/settings/data-reset/jobs":
                return response(400, {"error": "invalid_workbench_settings_reset_request"})
            return response(200, {})

        def oa_facts():
            inventory = self._oa_inventory()
            inventory["members"] = {
                "admin": ["YNSYLP005"],
                "full_access": sorted(
                    item["username"]
                    for item in state["accounts"]
                    if item["access_tier"] == "full_access"
                ),
                "read_export_only": sorted(
                    item["username"]
                    for item in state["accounts"]
                    if item["access_tier"] == "read_export_only"
                ),
            }
            return inventory

        class _AuditConnection:
            def fetch_one(self, _sql, _params):
                return {"present": 1}

        approved = build_report(
            release="main-safe",
            database={
                "settings_payload": {
                    "allowed_usernames": ["YNSYLP005", "FULL001"],
                    "readonly_export_usernames": [],
                    "full_access_usernames": ["FULL001"],
                    "admin_usernames": ["YNSYLP005"],
                    "access_control_version": 1,
                }
            },
            environment={},
            oa_roles=oa_facts(),
            admin_session=_session("YNSYLP005", "admin", True),
            bearer_session=_session("YNSYLP006", "denied", False),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            preflight_path = Path(temp_dir) / "preflight.json"
            output_path = Path(temp_dir) / "post.json"
            preflight_path.write_text(json.dumps(approved), encoding="utf-8")
            with (
                patch.object(preflight_module, "_http_request", side_effect=http_request),
                patch.object(preflight_module, "collect_oa_role_facts", side_effect=oa_facts),
                patch.object(
                    preflight_module,
                    "collect_database_facts",
                    return_value={
                        "migration_0132_applied": True,
                        "constraint_present": True,
                        "constraint_validated": True,
                    },
                ),
                patch.object(preflight_module.PostgresSettings, "from_env", return_value=object()),
                patch.object(preflight_module, "PostgresConnection", return_value=_AuditConnection()),
            ):
                report, status = run_post_deploy(
                    release="main-safe",
                    base_url="http://127.0.0.1:18001",
                    preflight_path=str(preflight_path),
                    output_path=str(output_path),
                    admin_token="admin-token",
                    bearer_token="bearer-token",
                    oa_base_url="https://www.yn-sourcing.com/oa-api",
                )

            rendered = output_path.read_text(encoding="utf-8")

        self.assertEqual(status, 0)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["restore"]["accounts_restored"])
        self.assertTrue(report["restore"]["oa_router_restored"])
        self.assertEqual(
            report["checks"]["oa_router_visibility"],
            {
                "admin": True,
                "initial_denied": False,
                "full_access": True,
                "read_export_only": True,
                "denied": False,
            },
        )
        self.assertEqual(state["tier"], "denied")
        self.assertNotIn("YNSYLP006", rendered)
        self.assertNotIn("admin-token", rendered)
        self.assertNotIn("bearer-token", rendered)


if __name__ == "__main__":
    unittest.main()
