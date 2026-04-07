from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Literal, Protocol


OARoleTier = Literal["read_export_only", "full_access", "admin"]


class OARoleSyncError(RuntimeError):
    pass


class OARoleSyncConfigurationError(OARoleSyncError):
    pass


class OARoleSyncExecutionError(OARoleSyncError):
    pass


@dataclass(slots=True, frozen=True)
class OARoleAssignment:
    username: str
    tier: OARoleTier


class OARoleSyncExecutor(Protocol):
    def apply(self, assignments: list[OARoleAssignment]) -> None: ...


@dataclass(slots=True, frozen=True)
class OARoleSyncSettings:
    enabled: bool
    host: str
    port: int
    database: str
    username: str
    password: str
    connect_timeout_seconds: int
    readonly_role_key: str
    full_access_role_key: str
    admin_role_key: str


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _build_assignments_from_snapshot(snapshot: dict[str, Any]) -> list[OARoleAssignment]:
    readonly = [str(item).strip() for item in list(snapshot.get("readonly_export_usernames") or []) if str(item).strip()]
    full_access = [str(item).strip() for item in list(snapshot.get("full_access_usernames") or []) if str(item).strip()]
    admin = [str(item).strip() for item in list(snapshot.get("admin_usernames") or []) if str(item).strip()]
    return [
        *[OARoleAssignment(username=item, tier="read_export_only") for item in readonly],
        *[OARoleAssignment(username=item, tier="full_access") for item in full_access],
        *[OARoleAssignment(username=item, tier="admin") for item in admin],
    ]


class OARoleSyncService:
    def __init__(self, *, executor: OARoleSyncExecutor | None = None) -> None:
        self._executor = executor

    @classmethod
    def from_environment(cls) -> "OARoleSyncService":
        if not _is_truthy(os.getenv("FIN_OPS_OA_ROLE_SYNC_ENABLED")):
            return cls()
        return cls(executor=MySQLOARoleSyncExecutor.from_environment())

    @property
    def enabled(self) -> bool:
        return self._executor is not None

    @staticmethod
    def build_assignments(snapshot: dict[str, Any]) -> list[OARoleAssignment]:
        return _build_assignments_from_snapshot(snapshot)

    def sync_access_control(self, snapshot: dict[str, Any]) -> None:
        if self._executor is None:
            return
        self._executor.apply(self.build_assignments(snapshot))


class MySQLOARoleSyncExecutor:
    def __init__(self, settings: OARoleSyncSettings) -> None:
        self._settings = settings

    @classmethod
    def from_environment(cls) -> "MySQLOARoleSyncExecutor":
        required = {
            "host": os.getenv("FIN_OPS_OA_ROLE_SYNC_HOST", "").strip(),
            "database": os.getenv("FIN_OPS_OA_ROLE_SYNC_DATABASE", "").strip(),
            "username": os.getenv("FIN_OPS_OA_ROLE_SYNC_USERNAME", "").strip(),
            "password": os.getenv("FIN_OPS_OA_ROLE_SYNC_PASSWORD", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise OARoleSyncConfigurationError(
                "Missing OA role sync configuration: " + ", ".join(sorted(missing))
            )
        return cls(
            OARoleSyncSettings(
                enabled=True,
                host=required["host"],
                port=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_PORT", "3306")),
                database=required["database"],
                username=required["username"],
                password=required["password"],
                connect_timeout_seconds=max(int(os.getenv("FIN_OPS_OA_ROLE_SYNC_CONNECT_TIMEOUT_SECONDS", "5")), 1),
                readonly_role_key=os.getenv("FIN_OPS_OA_ROLE_SYNC_READONLY_ROLE_KEY", "finops_read_export").strip()
                or "finops_read_export",
                full_access_role_key=os.getenv("FIN_OPS_OA_ROLE_SYNC_FULL_ACCESS_ROLE_KEY", "finops_full_access").strip()
                or "finops_full_access",
                admin_role_key=os.getenv("FIN_OPS_OA_ROLE_SYNC_ADMIN_ROLE_KEY", "finops_admin").strip()
                or "finops_admin",
            )
        )

    def apply(self, assignments: list[OARoleAssignment]) -> None:
        try:
            import pymysql  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised in deployed env
            raise OARoleSyncConfigurationError(
                "PyMySQL is required for OA role sync. Install backend requirements first."
            ) from exc

        connection = pymysql.connect(
            host=self._settings.host,
            port=self._settings.port,
            user=self._settings.username,
            password=self._settings.password,
            database=self._settings.database,
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=self._settings.connect_timeout_seconds,
        )
        try:
            with connection.cursor() as cursor:
                role_ids = self._load_role_ids(cursor)
                user_ids = self._load_user_ids(cursor, assignments)
                self._delete_obsolete_assignments(cursor, role_ids, user_ids)
                self._insert_assignments(cursor, role_ids, user_ids, assignments)
            connection.commit()
        except Exception as exc:  # pragma: no cover - exercised in deployed env
            connection.rollback()
            if isinstance(exc, OARoleSyncError):
                raise
            raise OARoleSyncExecutionError(f"Failed to sync OA roles: {exc}") from exc
        finally:
            connection.close()

    def _load_role_ids(self, cursor) -> dict[str, int]:
        role_keys = [
            self._settings.readonly_role_key,
            self._settings.full_access_role_key,
            self._settings.admin_role_key,
        ]
        cursor.execute(
            f"SELECT role_id, role_key FROM sys_role WHERE role_key IN ({_placeholders(len(role_keys))})",
            role_keys,
        )
        rows = cursor.fetchall()
        role_ids = {str(role_key): int(role_id) for role_id, role_key in rows}
        missing = sorted(set(role_keys).difference(role_ids))
        if missing:
            raise OARoleSyncExecutionError("Missing OA roles: " + ", ".join(missing))
        return role_ids

    def _load_user_ids(self, cursor, assignments: list[OARoleAssignment]) -> dict[str, int]:
        usernames = [assignment.username for assignment in assignments]
        if not usernames:
            return {}
        cursor.execute(
            f"SELECT user_id, user_name FROM sys_user WHERE user_name IN ({_placeholders(len(usernames))})",
            usernames,
        )
        rows = cursor.fetchall()
        user_ids = {str(username): int(user_id) for user_id, username in rows}
        missing = sorted(set(usernames).difference(user_ids))
        if missing:
            raise OARoleSyncExecutionError("OA users not found: " + ", ".join(missing))
        return user_ids

    def _delete_obsolete_assignments(self, cursor, role_ids: dict[str, int], user_ids: dict[str, int]) -> None:
        finops_role_ids = [
            role_ids[self._settings.readonly_role_key],
            role_ids[self._settings.full_access_role_key],
            role_ids[self._settings.admin_role_key],
        ]
        if user_ids:
            target_user_ids = list(user_ids.values())
            cursor.execute(
                (
                    f"DELETE FROM sys_user_role WHERE role_id IN ({_placeholders(len(finops_role_ids))}) "
                    f"AND user_id NOT IN ({_placeholders(len(target_user_ids))})"
                ),
                [*finops_role_ids, *target_user_ids],
            )
            cursor.execute(
                (
                    f"DELETE FROM sys_user_role WHERE role_id IN ({_placeholders(len(finops_role_ids))}) "
                    f"AND user_id IN ({_placeholders(len(target_user_ids))})"
                ),
                [*finops_role_ids, *target_user_ids],
            )
            return
        cursor.execute(
            f"DELETE FROM sys_user_role WHERE role_id IN ({_placeholders(len(finops_role_ids))})",
            finops_role_ids,
        )

    def _insert_assignments(
        self,
        cursor,
        role_ids: dict[str, int],
        user_ids: dict[str, int],
        assignments: list[OARoleAssignment],
    ) -> None:
        for assignment in assignments:
            role_id = role_ids[self._role_key_for_tier(assignment.tier)]
            user_id = user_ids[assignment.username]
            cursor.execute(
                (
                    "INSERT INTO sys_user_role (user_id, role_id) "
                    "SELECT %s, %s FROM DUAL "
                    "WHERE NOT EXISTS (SELECT 1 FROM sys_user_role WHERE user_id = %s AND role_id = %s)"
                ),
                (user_id, role_id, user_id, role_id),
            )

    def _role_key_for_tier(self, tier: OARoleTier) -> str:
        if tier == "read_export_only":
            return self._settings.readonly_role_key
        if tier == "full_access":
            return self._settings.full_access_role_key
        return self._settings.admin_role_key


def _placeholders(count: int) -> str:
    return ", ".join(["%s"] * count)
