"""Check the cash connection's effective database privileges, never business rows."""

from fin_ops_platform.services.cash_domain import CashError


def assert_cash_runtime_identity(connection, ordinary_role: str) -> None:
    row = connection.fetch_one("""
        SELECT r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication AS privileged,
          pg_has_role(current_user, %s, 'MEMBER') AS ordinary_member,
          has_schema_privilege(current_user, 'cash', 'USAGE') AS cash_usage,
          has_schema_privilege(current_user, 'cash', 'CREATE') AS cash_ddl,
          has_database_privilege(current_user,current_database(),'CREATE') AS database_ddl,
          EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS inherited_roles,
          EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='cash' AND c.relowner=r.oid) AS cash_owner,
          EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname IN ('app','audit','job','staging') AND c.relkind IN ('r','p','v','m')
              AND has_schema_privilege(current_user,n.oid,'USAGE')
              AND has_table_privilege(current_user,c.oid,'SELECT,INSERT,UPDATE,DELETE')
          ) AS ordinary_access,
          (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='cash' AND c.relkind='r'
              AND has_table_privilege(current_user,c.oid,'SELECT')
              AND has_table_privilege(current_user,c.oid,'INSERT')
              AND has_table_privilege(current_user,c.oid,'UPDATE')
              AND has_table_privilege(current_user,c.oid,'DELETE')) AS writable_tables
        FROM pg_roles r WHERE r.rolname=current_user
        """, (ordinary_role,))
    if (not row or row['privileged'] or row['ordinary_member'] or row['ordinary_access']
            or row['cash_ddl'] or row['database_ddl'] or row['inherited_roles'] or row['cash_owner']
            or not row['cash_usage'] or row['writable_tables'] != 10):
        raise CashError("cash_dependency_unavailable", "现金数据库运行身份未达到数据隔离要求。", 503)
