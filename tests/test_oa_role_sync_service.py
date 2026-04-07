import unittest

from fin_ops_platform.services.oa_role_sync_service import OARoleAssignment, OARoleSyncService


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


if __name__ == "__main__":
    unittest.main()
