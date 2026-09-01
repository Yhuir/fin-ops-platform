import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.services.oa_role_sync_service import (
    MySQLOARoleSyncExecutor,
    OARoleAssignment,
    OARoleSyncConfigurationError,
    OARoleSyncExecutionError,
    OARoleSyncService,
    OARoleSyncSettings,
    OAUserSummary,
)


class RecordingExecutor:
    def __init__(self) -> None:
        self.assignments: list[OARoleAssignment] | None = None

    def apply(self, assignments: list[OARoleAssignment]) -> None:
        self.assignments = list(assignments)

    def resolve_users(self, usernames: list[str]) -> list[OAUserSummary]:
        return [OAUserSummary(username, f"{username} 姓名", True) for username in usernames]

    def search_users(self, query: str, limit: int) -> list[OAUserSummary]:
        return [OAUserSummary(query, f"{query} 姓名", True)][:limit]


class ScriptedCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]], *, fail_on: str | None = None) -> None:
        self._responses = list(responses)
        self._rows: list[tuple[object, ...]] = []
        self._fail_on = fail_on
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = ()) -> None:
        normalized_params = tuple(params or ())
        self.executed.append((sql, normalized_params))
        if self._fail_on and self._fail_on in sql:
            raise TimeoutError("synthetic OA timeout")
        if sql.lstrip().startswith("SELECT"):
            self._rows = self._responses.pop(0)

    def fetchall(self):
        return list(self._rows)


class ScriptedConnection:
    def __init__(self, cursor: ScriptedCursor) -> None:
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


def _settings() -> OARoleSyncSettings:
    return OARoleSyncSettings(
        enabled=True,
        host="oa-db",
        port=3306,
        database="oa",
        username="finops",
        password="secret",
        connect_timeout_seconds=5,
        read_timeout_seconds=10,
        write_timeout_seconds=11,
        user_role_key="finops_app_user",
        admin_role_key="finops_admin",
        required_permission="finops:app:view",
    )


def _with_connection(connection: ScriptedConnection, action):
    connect_kwargs: dict[str, object] = {}

    def connect(**kwargs: object):
        connect_kwargs.update(kwargs)
        return connection

    with patch.dict(sys.modules, {"pymysql": SimpleNamespace(connect=connect)}):
        result = action(MySQLOARoleSyncExecutor(_settings()))
    return result, connect_kwargs


class OARoleSyncServiceTests(unittest.TestCase):
    def test_page_accounts_map_to_one_runtime_user_role_plus_fixed_admin(self) -> None:
        executor = RecordingExecutor()
        service = OARoleSyncService(executor=executor)
        service.sync_access_control(
            {
                "page_access_accounts": [
                    {"username": "USER001", "page_keys": ["bank-details"]},
                    {"username": "USER002", "page_keys": ["pending-invoices"]},
                ],
                "access_control_version": 1,
            }
        )

        self.assertEqual(
            executor.assignments,
            [
                OARoleAssignment("USER001", "user"),
                OARoleAssignment("USER002", "user"),
                OARoleAssignment("YNSYLP005", "admin"),
            ],
        )

    def test_disabled_service_fails_fast_for_sync_and_directory(self) -> None:
        service = OARoleSyncService()
        with self.assertRaises(OARoleSyncConfigurationError):
            service.sync_access_control({"page_access_accounts": [], "access_control_version": 1})
        with self.assertRaises(OARoleSyncConfigurationError):
            service.resolve_users(["USER001"])

    def test_environment_parses_binary_role_contract_and_timeouts(self) -> None:
        with patch.dict("os.environ", {
            "FIN_OPS_OA_ROLE_SYNC_ENABLED": "1",
            "FIN_OPS_OA_ROLE_SYNC_HOST": "oa-db",
            "FIN_OPS_OA_ROLE_SYNC_DATABASE": "oa",
            "FIN_OPS_OA_ROLE_SYNC_USERNAME": "finops",
            "FIN_OPS_OA_ROLE_SYNC_PASSWORD": "secret",
            "FIN_OPS_OA_REQUIRED_PERMISSION": "finops:app:view",
            "FIN_OPS_OA_ROLE_SYNC_READ_TIMEOUT_SECONDS": "7",
        }, clear=True):
            settings = MySQLOARoleSyncExecutor.from_environment()._settings

        self.assertEqual(settings.user_role_key, "finops_app_user")
        self.assertEqual(settings.admin_role_key, "finops_admin")
        self.assertEqual(settings.read_timeout_seconds, 7)

    def test_mysql_apply_validates_exact_two_menu_roles_before_writes(self) -> None:
        cursor = ScriptedCursor([
            [(11, "finops_app_user"), (12, "finops_admin")],
            [(99,)],
            [(11,), (12,)],
            [(101, "USER001"), (102, "YNSYLP005")],
        ])
        connection = ScriptedConnection(cursor)
        _, kwargs = _with_connection(
            connection,
            lambda executor: executor.apply([
                OARoleAssignment("USER001", "user"),
                OARoleAssignment("YNSYLP005", "admin"),
            ]),
        )

        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertEqual(kwargs["connect_timeout"], 5)
        self.assertTrue(all("sys_user_role" in sql for sql, _ in cursor.executed if sql.lstrip().startswith(("DELETE", "INSERT"))))

    def test_mysql_apply_rejects_role_or_binding_drift_without_writes(self) -> None:
        cases = {
            "missing_role": [[(11, "finops_app_user")]],
            "duplicate_menu": [[(11, "finops_app_user"), (12, "finops_admin")], [(99,), (100,)]],
            "extra_binding": [[(11, "finops_app_user"), (12, "finops_admin")], [(99,)], [(11,), (12,), (90,)]],
        }
        for name, responses in cases.items():
            cursor = ScriptedCursor(responses)
            connection = ScriptedConnection(cursor)
            with self.subTest(name=name), self.assertRaises(OARoleSyncExecutionError):
                _with_connection(connection, lambda executor: executor.apply([]))
            self.assertFalse(any(sql.lstrip().startswith(("DELETE", "INSERT")) for sql, _ in cursor.executed))

    def test_directory_resolve_and_search_return_oa_names_and_status(self) -> None:
        resolve_connection = ScriptedConnection(ScriptedCursor([
            [("USER001", "张三", "0", "0"), ("USER002", "李四", "1", "0")],
        ]))
        resolved, _ = _with_connection(
            resolve_connection,
            lambda executor: executor.resolve_users(["USER002", "USER001"]),
        )
        self.assertEqual(resolved[0], OAUserSummary("USER001", "张三", True))
        self.assertEqual(resolved[1], OAUserSummary("USER002", "李四", False))

        search_connection = ScriptedConnection(ScriptedCursor([[('USER001', '张三', '0', '0')]]))
        searched, _ = _with_connection(search_connection, lambda executor: executor.search_users("张", 20))
        self.assertEqual(searched, [OAUserSummary("USER001", "张三", True)])
        sql, params = search_connection.cursor_value.executed[0]
        self.assertIn("nick_name LIKE", sql)
        self.assertEqual(params, ("%张%", "%张%", 20))

    def test_connection_failure_is_wrapped(self) -> None:
        with patch.dict(sys.modules, {"pymysql": SimpleNamespace(connect=lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("connect")))}), self.assertRaises(OARoleSyncExecutionError):
            MySQLOARoleSyncExecutor(_settings()).apply([])


if __name__ == "__main__":
    unittest.main()
