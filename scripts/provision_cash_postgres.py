"""One-time explicit cash role provisioning. Never installs env files or touches data."""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


CASH_TABLES = (
    "accounts", "bill_labels", "categories", "deleted_submission_ids", "flows", "items",
    "settings", "settlements", "task_occurrences", "task_templates",
)
ADMIN_ENV = "FIN_OPS_CASH_PROVISION_ADMIN_DATABASE_URL"
CASH_ENV = "FIN_OPS_CASH_POSTGRES_DATABASE_URL"
ORDINARY_ENV = "FIN_OPS_CASH_ORDINARY_DATABASE_URLS"


class ProvisionError(RuntimeError):
    def __init__(self, code: str, *, committed: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.committed = committed


def _connection_info(dsn: str) -> dict:
    if not isinstance(dsn, str) or not dsn:
        raise ProvisionError("explicit_database_connection_required")
    try:
        info = conninfo_to_dict(dsn)
    except psycopg.Error:
        raise ProvisionError("invalid_database_connection") from None
    if any(not info.get(key) for key in ("host", "dbname", "user")):
        raise ProvisionError("explicit_host_database_and_user_required")
    if any(key in info for key in ("options", "service")):
        raise ProvisionError("connection_role_or_service_overrides_forbidden")
    if "," in info["host"] or len(info["user"].encode()) > 63:
        raise ProvisionError("single_endpoint_and_exact_role_name_required")
    return info


def _validate_connections(admin_dsn: str, cash_dsn: str, ordinary_dsns: list[str]) -> tuple[dict, list[dict]]:
    if not isinstance(ordinary_dsns, list) or not ordinary_dsns:
        raise ProvisionError("ordinary_runtime_connections_required")
    admin, cash = _connection_info(admin_dsn), _connection_info(cash_dsn)
    ordinary = [_connection_info(dsn) for dsn in ordinary_dsns]
    endpoint = lambda info: (info["host"], info.get("hostaddr"), info.get("port", "5432"), info["dbname"])
    if any(endpoint(info) != endpoint(admin) for info in [cash, *ordinary]):
        raise ProvisionError("all_connections_must_target_the_same_database_endpoint")
    if not cash.get("password"):
        raise ProvisionError("cash_login_password_required")
    if cash["user"] in {admin["user"], *(info["user"] for info in ordinary)}:
        raise ProvisionError("cash_role_must_be_separate")
    return cash, ordinary


def _role(connection, role: str):
    return connection.execute(
        "SELECT oid, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname=%s", (role,),
    ).fetchone()


def _cash_tables(connection) -> None:
    rows = connection.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='cash' AND c.relkind IN ('r','p','v','m','f') ORDER BY c.relname",
    ).fetchall()
    if [row[0] for row in rows] != list(CASH_TABLES):
        raise ProvisionError("cash_migration_0166_exact_tables_required")


def _assert_login_identity(connection, dsn: str) -> None:
    expected = _connection_info(dsn)
    identity = connection.execute("SELECT current_user, session_user, current_database()").fetchone()
    if identity != (expected["user"], expected["user"], expected["dbname"]):
        raise ProvisionError("connection_identity_does_not_match_explicit_dsn")


def _assert_restricted_cash(connection, cash_role: str) -> None:
    role = _role(connection, cash_role)
    if role is None or not role[1] or any(role[2:]):
        raise ProvisionError("cash_role_must_be_an_unprivileged_login")
    if connection.execute("SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=%s)", (role[0],)).fetchone()[0]:
        raise ProvisionError("cash_role_memberships_forbidden")
    if connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspowner=%s OR "
        "(nspname NOT LIKE 'pg_%%' AND nspname<>'information_schema' AND has_schema_privilege(%s,oid,'CREATE'))) "
        "OR EXISTS(SELECT 1 FROM pg_class WHERE relowner=%s) "
        "OR EXISTS(SELECT 1 FROM pg_database WHERE datdba=%s) "
        "OR has_database_privilege(%s,current_database(),'CREATE')",
        (role[0], cash_role, role[0], role[0], cash_role),
    ).fetchone()[0]:
        raise ProvisionError("cash_role_must_not_own_objects_or_create_schema_objects")
    if connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname NOT IN ('information_schema','cash') "
        "AND c.relkind IN ('r','p','v','m','f') "
        "AND has_table_privilege(%s,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))",
        (cash_role,),
    ).fetchone()[0]:
        raise ProvisionError("cash_role_has_other_business_table_privileges")
    if connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE p.prosecdef AND n.nspname NOT LIKE 'pg_%%' AND n.nspname<>'information_schema' "
        "AND has_schema_privilege(%s,n.oid,'USAGE') AND has_function_privilege(%s,p.oid,'EXECUTE'))",
        (cash_role, cash_role),
    ).fetchone()[0]:
        raise ProvisionError("cash_role_has_security_definer_execution")
    if connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='cash' AND c.relkind IN ('r','p','v','m','f') "
        "AND has_table_privilege(%s,c.oid,'TRUNCATE,REFERENCES,TRIGGER,SELECT WITH GRANT OPTION,"
        "INSERT WITH GRANT OPTION,UPDATE WITH GRANT OPTION,DELETE WITH GRANT OPTION'))", (cash_role,),
    ).fetchone()[0]:
        raise ProvisionError("cash_role_has_more_than_cash_dml")


def _assert_ordinary_denied(connection, ordinary_roles: list[str], cash_role: str) -> None:
    for role_name in ordinary_roles:
        role = _role(connection, role_name)
        if role is None or not role[1] or any(role[2:]):
            raise ProvisionError("ordinary_runtime_role_missing_or_privileged")
        if connection.execute("SELECT pg_has_role(%s,%s,'MEMBER')", (role_name, cash_role)).fetchone()[0]:
            raise ProvisionError("ordinary_runtime_is_a_cash_role_member")
        if connection.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid<>%s AND pg_has_role(%s,r.oid,'MEMBER') "
            "AND (r.rolsuper OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls "
            "OR has_schema_privilege(r.oid,'cash','USAGE,CREATE') OR EXISTS("
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='cash' AND c.relkind IN ('r','p','v','m','f') "
            "AND has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))))",
            (role[0], role_name),
        ).fetchone()[0]:
            raise ProvisionError("ordinary_runtime_can_assume_cash_privileged_role")
        if connection.execute(
            "SELECT has_schema_privilege(%s,'cash','USAGE,CREATE') OR EXISTS("
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='cash' AND c.relkind IN ('r','p','v','m','f') "
            "AND has_table_privilege(%s,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))",
            (role_name, role_name),
        ).fetchone()[0]:
            raise ProvisionError("ordinary_runtime_has_cash_privileges")


def _assert_cash_dml(connection, cash_role: str) -> None:
    if not connection.execute("SELECT has_schema_privilege(%s,'cash','USAGE')", (cash_role,)).fetchone()[0]:
        raise ProvisionError("cash_schema_usage_missing")
    for table in CASH_TABLES:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            if not connection.execute("SELECT has_table_privilege(%s,%s,%s)", (cash_role, "cash." + table, privilege)).fetchone()[0]:
                raise ProvisionError("cash_table_dml_missing")


def provision(admin_dsn: str, cash_dsn: str, ordinary_dsns: list[str], *, apply: bool = False) -> dict:
    """Provision grants transactionally, then verify the actual login connections."""
    cash, ordinary = _validate_connections(admin_dsn, cash_dsn, ordinary_dsns)
    cash_role = cash["user"]
    ordinary_roles = sorted({info["user"] for info in ordinary})
    committed, created = False, False
    try:
        with psycopg.connect(admin_dsn, connect_timeout=5) as connection:
            if not apply:
                connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL lock_timeout='5s'")
            connection.execute("SET LOCAL statement_timeout='10s'")
            _assert_login_identity(connection, admin_dsn)
            _cash_tables(connection)
            existing = _role(connection, cash_role)
            if existing is None:
                if not apply:
                    raise ProvisionError("cash_role_not_provisioned")
                admin = _role(connection, connection.info.user)
                if not admin or not (admin[2] or admin[4]):
                    raise ProvisionError("administrator_createrole_privilege_required")
                # libpq's native SCRAM credential verifier keeps the plain password
                # out of SQL. This is PostgreSQL authentication, not a business hash.
                verifier = connection.pgconn.encrypt_password(cash["password"].encode(), cash_role.encode(), b"scram-sha-256").decode()
                connection.execute(sql.SQL(
                    "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(cash_role), sql.Literal(verifier)))
                created = True
            _assert_restricted_cash(connection, cash_role)
            _assert_ordinary_denied(connection, ordinary_roles, cash_role)
            if apply:
                connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(cash["dbname"]), sql.Identifier(cash_role)))
                connection.execute(sql.SQL("GRANT USAGE ON SCHEMA cash TO {}").format(sql.Identifier(cash_role)))
                connection.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {} TO {}").format(
                    sql.SQL(", ").join(sql.Identifier("cash", table) for table in CASH_TABLES), sql.Identifier(cash_role),
                ))
            _assert_cash_dml(connection, cash_role)
            _assert_ordinary_denied(connection, ordinary_roles, cash_role)
        committed = apply
        with psycopg.connect(cash_dsn, connect_timeout=5, autocommit=True) as connection:
            connection.execute("SET statement_timeout='10s'")
            _assert_login_identity(connection, cash_dsn)
            _assert_restricted_cash(connection, cash_role)
            _assert_cash_dml(connection, cash_role)
            connection.execute("SELECT 1 FROM cash.flows LIMIT 0")
        for dsn in ordinary_dsns:
            with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as connection:
                connection.execute("SET statement_timeout='10s'")
                _assert_login_identity(connection, dsn)
                try:
                    connection.execute("SELECT 1 FROM cash.flows LIMIT 0")
                except psycopg.errors.InsufficientPrivilege:
                    continue
                raise ProvisionError("ordinary_connection_can_read_cash")
    except ProvisionError as error:
        error.committed = committed
        raise
    except (psycopg.Error, ValueError):
        raise ProvisionError("database_connection_or_operation_failed", committed=committed) from None
    return {"status": "verified", "created_cash_role": created, "cash_table_count": len(CASH_TABLES),
            "ordinary_role_count": len(ordinary_roles), "database_changes_committed": committed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only effective privilege and actual connection verification")
    mode.add_argument("--apply", action="store_true", help="Create/validate the explicit cash role and grant only cash DML")
    args = parser.parse_args()
    try:
        if any(not os.environ.get(key) for key in (ADMIN_ENV, CASH_ENV, ORDINARY_ENV)):
            raise ProvisionError("explicit_admin_cash_and_ordinary_environment_required")
        try:
            ordinary = json.loads(os.environ[ORDINARY_ENV])
        except json.JSONDecodeError:
            raise ProvisionError("ordinary_connections_must_be_a_json_array") from None
        report = provision(os.environ[ADMIN_ENV], os.environ[CASH_ENV], ordinary, apply=args.apply)
    except ProvisionError as error:
        print(json.dumps({"status": "failed", "error": error.code, "database_changes_committed": error.committed}), file=sys.stderr)
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
