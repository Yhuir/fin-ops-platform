from __future__ import annotations

import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from fin_ops_platform.app.cash_runtime import CashRuntime
from scripts.provision_cash_postgres import CASH_TABLES, ProvisionError, main, provision


class CashProvisionInputTests(unittest.TestCase):
    def test_different_database_and_same_role_are_rejected_before_connection(self) -> None:
        admin = "postgresql://admin:secret@localhost:5432/test"
        ordinary = ["postgresql://ordinary:secret@localhost:5432/test"]
        for cash, code in (("postgresql://cash:secret@elsewhere:5432/test", "all_connections_must_target_the_same_database_endpoint"),
                           ("postgresql://ordinary:secret@localhost:5432/test", "cash_role_must_be_separate"),
                           ("postgresql://cash@localhost:5432/test", "cash_login_password_required")):
            with self.subTest(code=code), patch("scripts.provision_cash_postgres.psycopg.connect") as connect:
                with self.assertRaises(ProvisionError) as error:
                    provision(admin, cash, ordinary, apply=True)
                self.assertEqual(error.exception.code, code)
                connect.assert_not_called()

    def test_cli_missing_environment_and_database_errors_never_print_secret(self) -> None:
        stderr = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch("sys.argv", ["provision_cash_postgres.py", "--check"]), redirect_stderr(stderr):
            self.assertEqual(main(), 1)
        self.assertEqual(json.loads(stderr.getvalue())["error"], "explicit_admin_cash_and_ordinary_environment_required")
        with patch("scripts.provision_cash_postgres.psycopg.connect", side_effect=psycopg.OperationalError("password=NEVER-PRINT")):
            with self.assertRaises(ProvisionError) as error:
                provision("postgresql://admin:secret@localhost/test", "postgresql://cash:secret@localhost/test",
                          ["postgresql://ordinary:secret@localhost/test"], apply=True)
        self.assertNotIn("NEVER-PRINT", str(error.exception))


class CashPostgresPermissionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cluster_dsn = os.environ.get("FIN_OPS_CASH_PROVISION_TEST_ADMIN_URL", "")
        if not cls.cluster_dsn:
            raise RuntimeError("Set explicit FIN_OPS_CASH_PROVISION_TEST_ADMIN_URL for cash permission tests; no production DSN or skip fallback is used.")
        cls.database_name = "cash_provision_test_" + uuid4().hex[:12]
        with psycopg.connect(cls.cluster_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.database_name)))
        cls.addClassCleanup(cls.drop_test_database)
        cls.admin_dsn = make_conninfo(cls.cluster_dsn, dbname=cls.database_name)
        with psycopg.connect(cls.admin_dsn) as connection:
            connection.execute("CREATE SCHEMA app; CREATE TABLE app.private_finance(id integer)")
            migration = Path("backend/src/fin_ops_platform/postgres/migrations/0166_cash_ledger.sql").read_text()
            connection.execute(migration)

    @classmethod
    def drop_test_database(cls) -> None:
        with psycopg.connect(cls.cluster_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(cls.database_name)))

    def setUp(self) -> None:
        suffix = uuid4().hex[:12]
        self.cash_role, self.ordinary_role = "cash_probe_" + suffix, "ordinary_probe_" + suffix
        self.test_roles = [self.cash_role, self.ordinary_role]
        self.cash_dsn = make_conninfo(self.admin_dsn, user=self.cash_role, password="temporary-test-secret")
        self.ordinary_dsn = make_conninfo(self.admin_dsn, user=self.ordinary_role, password="temporary-test-secret")
        self.addCleanup(self.drop_test_roles)
        with psycopg.connect(self.admin_dsn) as admin:
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'temporary-test-secret'").format(sql.Identifier(self.ordinary_role)))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA app TO {}").format(sql.Identifier(self.ordinary_role)))
            admin.execute(sql.SQL("GRANT SELECT, INSERT ON app.private_finance TO {}").format(sql.Identifier(self.ordinary_role)))

    def drop_test_roles(self) -> None:
        with psycopg.connect(self.admin_dsn) as admin:
            # Targets are unique roles created by this test, never production or
            # environment-provided role names. Release all grants before drop.
            for role in self.test_roles:
                if admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                    admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))

    def apply(self) -> dict:
        return provision(self.admin_dsn, self.cash_dsn, [self.ordinary_dsn], apply=True)

    def test_new_role_real_login_dml_and_bidirectional_denial_then_repeat(self) -> None:
        result = self.apply()
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["created_cash_role"])
        self.assertEqual(result["cash_table_count"], 10)
        with psycopg.connect(self.cash_dsn, autocommit=True) as cash:
            for table in CASH_TABLES:
                cash.execute(sql.SQL("SELECT 1 FROM {} LIMIT 0").format(sql.Identifier("cash", table)))
            identity = uuid4()
            cash.execute("INSERT INTO cash.categories(id,name,\"group\") VALUES(%s,'temporary','receipt')", (identity,))
            cash.execute("UPDATE cash.categories SET name='changed' WHERE id=%s", (identity,))
            cash.execute("DELETE FROM cash.categories WHERE id=%s", (identity,))
            for statement in ("SELECT * FROM app.private_finance", "CREATE TABLE cash.forbidden(id integer)", "TRUNCATE cash.flows"):
                with self.subTest(statement=statement), self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cash.execute(statement)
        with psycopg.connect(self.ordinary_dsn, autocommit=True) as ordinary:
            ordinary.execute("SELECT 1 FROM app.private_finance LIMIT 0")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                ordinary.execute("SELECT 1 FROM cash.flows LIMIT 0")
        self.assertFalse(self.apply()["created_cash_role"])
        self.assertFalse(provision(self.admin_dsn, self.cash_dsn, [self.ordinary_dsn])["database_changes_committed"])

    def test_check_does_not_create_a_role(self) -> None:
        with self.assertRaises(ProvisionError) as error:
            provision(self.admin_dsn, self.cash_dsn, [self.ordinary_dsn])
        self.assertEqual(error.exception.code, "cash_role_not_provisioned")
        with psycopg.connect(self.admin_dsn) as admin:
            self.assertIsNone(admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (self.cash_role,)).fetchone())

    def test_real_restricted_runtime_routes_create_read_delete_flow(self) -> None:
        self.apply()
        session = SimpleNamespace(
            can_admin_access=False, allowed_page_keys=frozenset({"cash"}), token="unused-test-token",
            identity=SimpleNamespace(username="cash-runtime-test", display_name="Synthetic operator"),
        )
        account_id, category_id, flow_id = (str(uuid4()) for _ in range(3))
        with patch.dict(os.environ, {
            "FIN_OPS_CASH_POSTGRES_DATABASE_URL": self.cash_dsn,
            "FIN_OPS_POSTGRES_DATABASE_URL": self.ordinary_dsn,
        }), patch("fin_ops_platform.app.cash_runtime.load_mongo_oa_settings", return_value=None):
            runtime = CashRuntime(None)
            try:
                self.assertEqual(runtime.connection.fetch_one("SELECT current_user AS role")["role"], self.cash_role)
                self.assertTrue(runtime.connection.settings.pool_enabled)
                self.assertEqual(runtime.connection.settings.pool_max_size, 2)
                routes = runtime.routes(session, lambda status, payload, headers: SimpleNamespace(
                    status=status, payload=payload, headers=headers,
                ))

                def call(method, path, expected_status, *, payload=None, query=None):
                    response = routes.route(method, path, query or {},
                        json.dumps(payload) if payload is not None else None, session=session)
                    self.assertEqual(response.status, expected_status, response.payload)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    return response.payload

                account = call("POST", "/api/cash/settings/accounts", 201, payload={
                    "id": account_id, "name": "Synthetic runtime account", "kind": "cash",
                    "opening_date": "2026-01-01", "opening_amount": "100.00",
                })
                self.assertEqual(account["account"]["id"], account_id)
                category = call("POST", "/api/cash/settings/categories", 201, payload={
                    "id": category_id, "name": "Synthetic runtime receipt", "group": "receipt",
                })
                self.assertEqual(category["category"]["id"], category_id)
                created = call("POST", "/api/cash/flows", 201, payload={
                    "id": flow_id, "kind": "receipt", "amount": "12.30", "occurred_on": "2026-01-15",
                    "to_account_id": account_id, "category_id": category_id,
                    "project_mode": "selection", "content": "Synthetic runtime receipt",
                })
                self.assertEqual(created["flow"]["id"], flow_id)
                self.assertEqual(created["flow"]["amount"], "12.30")
                self.assertEqual(created["flow"]["source_kind"], "manual")
                period = {"date_from": ["2026-01-01"], "date_to": ["2026-01-31"], "account_id": [account_id]}
                listed = call("GET", "/api/cash/flows", 200, query=period)
                self.assertEqual(listed["pagination"]["total"], 1)
                self.assertEqual([row["id"] for row in listed["rows"]], [flow_id])
                self.assertEqual(listed["summary"]["filtered_totals"]["income_amount"], "12.30")
                self.assertEqual(listed["summary"]["account_balances"][0]["ending_balance"], "112.30")
                deleted = call("POST", f"/api/cash/flows/{flow_id}/delete", 200,
                               payload={"expected_version": created["version"]})
                self.assertTrue(deleted["deleted"])
                empty = call("GET", "/api/cash/flows", 200, query=period)
                self.assertEqual(empty["rows"], [])
                self.assertEqual(empty["pagination"]["total"], 0)
                self.assertEqual(empty["summary"]["filtered_totals"]["income_amount"], "0.00")
                self.assertEqual(empty["summary"]["account_balances"][0]["ending_balance"], "100.00")
            finally:
                # Close the real pool before per-test DROP ROLE / class DROP DATABASE.
                runtime.close()

    def test_existing_unsafe_role_is_not_silently_demoted_or_fixed(self) -> None:
        with psycopg.connect(self.admin_dsn) as admin:
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN CREATEDB PASSWORD 'temporary-test-secret'").format(sql.Identifier(self.cash_role)))
        with self.assertRaises(ProvisionError) as error:
            self.apply()
        self.assertEqual(error.exception.code, "cash_role_must_be_an_unprivileged_login")
        with psycopg.connect(self.admin_dsn) as admin:
            self.assertTrue(admin.execute("SELECT rolcreatedb FROM pg_roles WHERE rolname=%s", (self.cash_role,)).fetchone()[0])

    def test_existing_cash_cross_pool_privilege_is_rejected_not_revoked(self) -> None:
        self.apply()
        with psycopg.connect(self.admin_dsn) as admin:
            admin.execute(sql.SQL("GRANT SELECT ON app.private_finance TO {}").format(sql.Identifier(self.cash_role)))
        with self.assertRaises(ProvisionError) as error:
            self.apply()
        self.assertEqual(error.exception.code, "cash_role_has_other_business_table_privileges")

    def test_ordinary_cash_grants_stop_provision_and_new_role_creation_rolls_back(self) -> None:
        with psycopg.connect(self.admin_dsn) as admin:
            admin.execute(sql.SQL("GRANT SELECT ON cash.flows TO {}").format(sql.Identifier(self.ordinary_role)))
        with self.assertRaises(ProvisionError) as error:
            self.apply()
        self.assertEqual(error.exception.code, "ordinary_runtime_has_cash_privileges")
        self.assertFalse(error.exception.committed)
        with psycopg.connect(self.admin_dsn) as admin:
            self.assertIsNone(admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (self.cash_role,)).fetchone())

    def test_cash_role_membership_is_rejected_even_noinherit(self) -> None:
        self.apply()
        with psycopg.connect(self.admin_dsn) as admin:
            admin.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(self.ordinary_role), sql.Identifier(self.cash_role)))
        with self.assertRaises(ProvisionError) as error:
            self.apply()
        self.assertEqual(error.exception.code, "cash_role_memberships_forbidden")

    def test_existing_cash_database_create_privilege_is_rejected(self) -> None:
        self.apply()
        with psycopg.connect(self.admin_dsn) as admin:
            admin.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                sql.Identifier(self.database_name), sql.Identifier(self.cash_role),
            ))
        with self.assertRaises(ProvisionError) as error:
            self.apply()
        self.assertEqual(error.exception.code, "cash_role_must_not_own_objects_or_create_schema_objects")

    def test_noinherit_ordinary_cannot_assume_a_cash_privileged_role(self) -> None:
        self.apply()
        privilege_role = "cash_privilege_probe_" + uuid4().hex[:12]
        self.test_roles.append(privilege_role)
        with psycopg.connect(self.admin_dsn) as admin:
            admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(privilege_role)))
            admin.execute(sql.SQL("GRANT SELECT ON cash.flows TO {}").format(sql.Identifier(privilege_role)))
            admin.execute(sql.SQL("ALTER ROLE {} NOINHERIT").format(sql.Identifier(self.ordinary_role)))
            admin.execute(sql.SQL("GRANT {} TO {} WITH INHERIT FALSE").format(
                sql.Identifier(privilege_role), sql.Identifier(self.ordinary_role),
            ))
        with self.assertRaises(ProvisionError) as error:
            self.apply()
        self.assertEqual(error.exception.code, "ordinary_runtime_can_assume_cash_privileged_role")

    def test_runtime_database_owner_cannot_be_used_as_ordinary_role(self) -> None:
        info = conninfo_to_dict(self.admin_dsn)
        self.assertNotEqual(info["user"], self.cash_role)
        with self.assertRaises(ProvisionError) as error:
            provision(self.admin_dsn, self.cash_dsn, [self.admin_dsn], apply=True)
        self.assertEqual(error.exception.code, "ordinary_runtime_role_missing_or_privileged")


if __name__ == "__main__":
    unittest.main()
