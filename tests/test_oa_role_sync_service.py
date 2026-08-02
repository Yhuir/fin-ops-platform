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
)


class RecordingExecutor:
    def __init__(self) -> None:
        self.assignments: list[OARoleAssignment] | None = None

    def apply(self, assignments: list[OARoleAssignment]) -> None:
        self.assignments = list(assignments)


class ScriptedCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]], *, fail_on: str | None = None) -> None:
        self._responses = list(responses)
        self._rows: list[tuple[object, ...]] = []
        self._fail_on = fail_on
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> "ScriptedCursor":
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

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)


class ScriptedConnection:
    def __init__(self, cursor: ScriptedCursor) -> None:
        self.cursor_value = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> ScriptedCursor:
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
        readonly_role_key="finops_read_export",
        full_access_role_key="finops_full_access",
        admin_role_key="finops_admin",
        required_permission="finops:app:view",
    )


def _apply_with_connection(connection: ScriptedConnection) -> dict[str, object]:
    connect_kwargs: dict[str, object] = {}

    def connect(**kwargs: object) -> ScriptedConnection:
        connect_kwargs.update(kwargs)
        return connection

    with patch.dict(sys.modules, {"pymysql": SimpleNamespace(connect=connect)}):
        MySQLOARoleSyncExecutor(_settings()).apply(
            [
                OARoleAssignment("READ001", "read_export_only"),
                OARoleAssignment("FULL001", "full_access"),
                OARoleAssignment("YNSYLP005", "admin"),
            ]
        )
    return connect_kwargs


class OARoleSyncServiceTests(unittest.TestCase):
    def test_sync_access_control_builds_expected_assignments(self) -> None:
        executor = RecordingExecutor()
        service = OARoleSyncService(executor=executor)

        service.sync_access_control(
            {
                "allowed_usernames": ["FULL001", "READONLY001", "YNSYLP005"],
                "readonly_export_usernames": ["READONLY001"],
                "admin_usernames": ["YNSYLP005"],
                "full_access_usernames": ["FULL001"],
            }
        )

        self.assertEqual(
            executor.assignments,
            [
                OARoleAssignment(username="READONLY001", tier="read_export_only"),
                OARoleAssignment(username="FULL001", tier="full_access"),
                OARoleAssignment(username="YNSYLP005", tier="admin"),
            ],
        )

    def test_sync_access_control_preserves_canonical_spelling_and_rejects_case_collisions(self) -> None:
        executor = RecordingExecutor()
        service = OARoleSyncService(executor=executor)

        service.sync_access_control(
            {
                "allowed_usernames": ["YNSYLP005", "Full.User"],
                "readonly_export_usernames": [],
                "admin_usernames": ["YNSYLP005"],
                "full_access_usernames": ["Full.User"],
            }
        )

        self.assertIn(OARoleAssignment(username="Full.User", tier="full_access"), executor.assignments or [])

        with self.assertRaises(ValueError):
            service.sync_access_control(
                {
                    "full_access_usernames": ["Full.User"],
                    "readonly_export_usernames": ["full.user"],
                }
            )

    def test_sync_access_control_fails_when_runtime_executor_is_disabled(self) -> None:
        with self.assertRaises(OARoleSyncConfigurationError):
            OARoleSyncService().sync_access_control(
                {
                    "full_access_usernames": ["FULL001"],
                    "readonly_export_usernames": [],
                    "admin_usernames": ["YNSYLP005"],
                }
            )

    def test_mysql_executor_parses_bounded_network_timeouts(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "FIN_OPS_OA_ROLE_SYNC_HOST": "oa-db",
                "FIN_OPS_OA_ROLE_SYNC_DATABASE": "oa",
                "FIN_OPS_OA_ROLE_SYNC_USERNAME": "finops",
                "FIN_OPS_OA_ROLE_SYNC_PASSWORD": "secret",
                "FIN_OPS_OA_ROLE_SYNC_CONNECT_TIMEOUT_SECONDS": "5",
                "FIN_OPS_OA_ROLE_SYNC_READ_TIMEOUT_SECONDS": "10",
                "FIN_OPS_OA_ROLE_SYNC_WRITE_TIMEOUT_SECONDS": "11",
                "FIN_OPS_OA_REQUIRED_PERMISSION": "finops:app:view",
            },
            clear=False,
        ):
            settings = MySQLOARoleSyncExecutor.from_environment()._settings

        self.assertEqual(settings.connect_timeout_seconds, 5)
        self.assertEqual(settings.read_timeout_seconds, 10)
        self.assertEqual(settings.write_timeout_seconds, 11)

    def test_mysql_executor_rejects_non_positive_timeout(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "FIN_OPS_OA_ROLE_SYNC_HOST": "oa-db",
                "FIN_OPS_OA_ROLE_SYNC_DATABASE": "oa",
                "FIN_OPS_OA_ROLE_SYNC_USERNAME": "finops",
                "FIN_OPS_OA_ROLE_SYNC_PASSWORD": "secret",
                "FIN_OPS_OA_ROLE_SYNC_READ_TIMEOUT_SECONDS": "0",
                "FIN_OPS_OA_REQUIRED_PERMISSION": "finops:app:view",
            },
            clear=False,
        ), self.assertRaises(OARoleSyncConfigurationError):
            MySQLOARoleSyncExecutor.from_environment()

    def test_mysql_executor_requires_fixed_oa_only_permission_marker(self) -> None:
        base = {
            "FIN_OPS_OA_ROLE_SYNC_HOST": "oa-db",
            "FIN_OPS_OA_ROLE_SYNC_DATABASE": "oa",
            "FIN_OPS_OA_ROLE_SYNC_USERNAME": "finops",
            "FIN_OPS_OA_ROLE_SYNC_PASSWORD": "secret",
        }
        for marker in (None, "finops:access", " finops:app:view:extra "):
            environment = dict(base)
            if marker is not None:
                environment["FIN_OPS_OA_REQUIRED_PERMISSION"] = marker
            with self.subTest(marker=marker), patch.dict("os.environ", environment, clear=True):
                with self.assertRaises(OARoleSyncConfigurationError):
                    MySQLOARoleSyncExecutor.from_environment()

    def test_mysql_executor_validates_exact_menu_roles_before_replacing_memberships(self) -> None:
        cursor = ScriptedCursor(
            [
                [(11, "finops_read_export"), (12, "finops_full_access"), (13, "finops_admin")],
                [(99,)],
                [(11,), (12,), (13,)],
                [(101, "READ001"), (102, "FULL001"), (103, "YNSYLP005")],
            ]
        )
        connection = ScriptedConnection(cursor)

        connect_kwargs = _apply_with_connection(connection)

        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.closed)
        self.assertEqual(connect_kwargs["connect_timeout"], 5)
        self.assertEqual(connect_kwargs["read_timeout"], 10)
        self.assertEqual(connect_kwargs["write_timeout"], 11)
        menu_select = next(item for item in cursor.executed if "FROM sys_menu" in item[0])
        self.assertEqual(menu_select[1], ("finops:app:view",))
        self.assertTrue(any("FROM sys_role_menu" in sql for sql, _params in cursor.executed))
        mutating_sql = [sql for sql, _params in cursor.executed if sql.lstrip().startswith(("DELETE", "INSERT"))]
        self.assertTrue(mutating_sql)
        self.assertTrue(all("sys_user_role" in sql for sql in mutating_sql))

    def test_mysql_executor_rejects_missing_duplicate_or_drifted_menu_contract_without_writes(self) -> None:
        roles = [(11, "finops_read_export"), (12, "finops_full_access"), (13, "finops_admin")]
        cases = {
            "missing_role": [[(11, "finops_read_export"), (12, "finops_full_access")]],
            "duplicate_role": [[*roles, (14, "finops_admin")]],
            "missing_menu": [roles, []],
            "duplicate_menu": [roles, [(99,), (100,)]],
            "missing_binding": [roles, [(99,)], [(11,), (12,)]],
            "non_dedicated_drift": [roles, [(99,)], [(11,), (12,), (13,), (90,)]],
        }
        for name, responses in cases.items():
            cursor = ScriptedCursor(responses)
            connection = ScriptedConnection(cursor)
            with self.subTest(case=name), self.assertRaises(OARoleSyncExecutionError):
                _apply_with_connection(connection)
            self.assertTrue(connection.rolled_back)
            self.assertFalse(connection.committed)
            self.assertFalse(
                any(sql.lstrip().startswith(("DELETE", "INSERT")) for sql, _params in cursor.executed)
            )

    def test_mysql_executor_wraps_connect_and_transaction_timeouts_and_rolls_back_when_connected(self) -> None:
        with patch.dict(
            sys.modules,
            {"pymysql": SimpleNamespace(connect=lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("connect")))},
        ), self.assertRaises(OARoleSyncExecutionError):
            MySQLOARoleSyncExecutor(_settings()).apply([])

        for fail_on in ("SELECT role_id", "DELETE FROM sys_user_role"):
            cursor = ScriptedCursor(
                [
                    [(11, "finops_read_export"), (12, "finops_full_access"), (13, "finops_admin")],
                    [(99,)],
                    [(11,), (12,), (13,)],
                    [(101, "READ001"), (102, "FULL001"), (103, "YNSYLP005")],
                ],
                fail_on=fail_on,
            )
            connection = ScriptedConnection(cursor)
            with self.subTest(fail_on=fail_on), self.assertRaises(OARoleSyncExecutionError):
                _apply_with_connection(connection)
            self.assertTrue(connection.rolled_back)
            self.assertFalse(connection.committed)
            self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
