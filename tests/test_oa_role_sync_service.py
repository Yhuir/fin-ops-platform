import unittest
from unittest.mock import patch

from fin_ops_platform.services.oa_role_sync_service import (
    MySQLOARoleSyncExecutor,
    OARoleAssignment,
    OARoleSyncConfigurationError,
    OARoleSyncService,
)


class RecordingExecutor:
    def __init__(self) -> None:
        self.assignments: list[OARoleAssignment] | None = None

    def apply(self, assignments: list[OARoleAssignment]) -> None:
        self.assignments = list(assignments)


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
            },
            clear=False,
        ), self.assertRaises(OARoleSyncConfigurationError):
            MySQLOARoleSyncExecutor.from_environment()


if __name__ == "__main__":
    unittest.main()
