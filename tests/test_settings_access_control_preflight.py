from __future__ import annotations

import json
from pathlib import Path
import tempfile
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
        "access_tier": tier,
        "can_admin_access": admin,
        "_preflight_http_status": 200,
        "_preflight_credential_source": credential_source or (
            "admin_stdin" if admin else "dedicated_bearer_stdin"
        ),
    }


class SettingsAccessControlPreflightTests(unittest.TestCase):
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
            "environment": {"allowed_usernames": ["YNSYLP005"], "readonly_usernames": []},
            "oa_roles": {
                "enabled": True,
                "members": {
                    "read_export_only": [],
                    "full_access": ["FULL001"],
                    "admin": ["YNSYLP005"],
                },
            },
            "admin_session": _session("YNSYLP005", "admin", True),
            "bearer_session": _session("SLO_DENIED", "denied", False),
        }
        arguments.update(overrides)
        return build_report(**arguments)

    def test_eligible_report_contains_only_hashed_nonprotected_identities(self) -> None:
        report = self._report()

        self.assertTrue(report["eligible"])
        rendered = str(report)
        self.assertNotIn("FULL001", rendered)
        self.assertNotIn("SLO_DENIED", rendered)
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

        self.assertTrue(report["eligible"])
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

    def test_oa_role_drift_fails_closed(self) -> None:
        report = self._report(oa_roles={
            "enabled": True,
            "members": {
                "read_export_only": [],
                "full_access": ["FULL001"],
                "admin": ["YNSYLP005", "ATTACKER"],
            },
        })

        self.assertFalse(report["eligible"])
        self.assertFalse(report["oa"]["matches_target"])
        self.assertNotIn("ATTACKER", str(report))

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
                        "user": {"username": "SLO_DENIED"},
                        "access_tier": tier,
                        "can_admin_access": False,
                        "can_mutate_data": tier == "full_access",
                        "can_access_app": tier != "denied",
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
                    (item for item in state["accounts"] if item["username"] == "SLO_DENIED"),
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
            return {
                "enabled": True,
                "members": {
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
                },
            }

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
            bearer_session=_session("SLO_DENIED", "denied", False),
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
                )

            rendered = output_path.read_text(encoding="utf-8")

        self.assertEqual(status, 0)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["restore"]["accounts_restored"])
        self.assertEqual(state["tier"], "denied")
        self.assertNotIn("SLO_DENIED", rendered)
        self.assertNotIn("admin-token", rendered)
        self.assertNotIn("bearer-token", rendered)


if __name__ == "__main__":
    unittest.main()
