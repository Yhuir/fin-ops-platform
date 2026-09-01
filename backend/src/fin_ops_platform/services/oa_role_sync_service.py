from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Literal, Protocol

from fin_ops_platform.services.state_store_protocol import settings_access_control_from_payload


OARoleKind = Literal["user", "admin"]
OA_MENU_PERMISSION = "finops:app:view"


class OARoleSyncError(RuntimeError):
    pass


class OARoleSyncConfigurationError(OARoleSyncError):
    pass


class OARoleSyncExecutionError(OARoleSyncError):
    pass


@dataclass(slots=True, frozen=True)
class OARoleAssignment:
    username: str
    role: OARoleKind


@dataclass(slots=True, frozen=True)
class OAUserSummary:
    username: str
    display_name: str
    active: bool


class OARoleSyncExecutor(Protocol):
    def apply(self, assignments: list[OARoleAssignment]) -> None: ...

    def resolve_users(self, usernames: list[str]) -> list[OAUserSummary]: ...

    def search_users(self, query: str, limit: int) -> list[OAUserSummary]: ...


@dataclass(slots=True, frozen=True)
class OARoleSyncSettings:
    enabled: bool
    host: str
    port: int
    database: str
    username: str
    password: str
    connect_timeout_seconds: int
    user_role_key: str
    admin_role_key: str
    required_permission: str
    read_timeout_seconds: int = 10
    write_timeout_seconds: int = 10


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _positive_timeout(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise OARoleSyncConfigurationError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise OARoleSyncConfigurationError(f"{name} must be a positive integer.")
    return value


def _build_assignments_from_snapshot(snapshot: dict[str, Any]) -> list[OARoleAssignment]:
    normalized = settings_access_control_from_payload(snapshot)
    return [
        *[
            OARoleAssignment(username=str(account["username"]), role="user")
            for account in normalized["page_access_accounts"]
        ],
        OARoleAssignment(username="YNSYLP005", role="admin"),
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
            raise OARoleSyncConfigurationError("OA role sync is disabled or not configured.")
        self._executor.apply(self.build_assignments(snapshot))

    def resolve_users(self, usernames: list[str]) -> list[OAUserSummary]:
        if self._executor is None:
            raise OARoleSyncConfigurationError("OA user directory is disabled or not configured.")
        return self._executor.resolve_users(usernames)

    def search_users(self, query: str, *, limit: int = 20) -> list[OAUserSummary]:
        if self._executor is None:
            raise OARoleSyncConfigurationError("OA user directory is disabled or not configured.")
        normalized_limit = min(max(int(limit), 1), 50)
        return self._executor.search_users(str(query or "").strip(), normalized_limit)


class MySQLOARoleSyncExecutor:
    def __init__(self, settings: OARoleSyncSettings) -> None:
        if settings.required_permission != OA_MENU_PERMISSION:
            raise OARoleSyncConfigurationError(
                f"FIN_OPS_OA_REQUIRED_PERMISSION must equal {OA_MENU_PERMISSION}."
            )
        role_keys = {
            settings.user_role_key,
            settings.admin_role_key,
        }
        if len(role_keys) != 2:
            raise OARoleSyncConfigurationError("OA role sync requires two distinct dedicated role keys.")
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
        required_permission = os.getenv("FIN_OPS_OA_REQUIRED_PERMISSION", "").strip()
        if required_permission != OA_MENU_PERMISSION:
            raise OARoleSyncConfigurationError(
                f"FIN_OPS_OA_REQUIRED_PERMISSION must equal {OA_MENU_PERMISSION}."
            )
        return cls(
            OARoleSyncSettings(
                enabled=True,
                host=required["host"],
                port=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_PORT", "3306")),
                database=required["database"],
                username=required["username"],
                password=required["password"],
                connect_timeout_seconds=_positive_timeout("FIN_OPS_OA_ROLE_SYNC_CONNECT_TIMEOUT_SECONDS", 5),
                read_timeout_seconds=_positive_timeout("FIN_OPS_OA_ROLE_SYNC_READ_TIMEOUT_SECONDS", 10),
                write_timeout_seconds=_positive_timeout("FIN_OPS_OA_ROLE_SYNC_WRITE_TIMEOUT_SECONDS", 10),
                user_role_key=os.getenv("FIN_OPS_OA_ROLE_SYNC_USER_ROLE_KEY", "finops_app_user").strip()
                or "finops_app_user",
                admin_role_key=os.getenv("FIN_OPS_OA_ROLE_SYNC_ADMIN_ROLE_KEY", "finops_admin").strip()
                or "finops_admin",
                required_permission=required_permission,
            )
        )

    def apply(self, assignments: list[OARoleAssignment]) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                role_ids = self._load_role_ids(cursor)
                menu_id = self._load_menu_id(cursor)
                self._validate_menu_bindings(cursor, menu_id, role_ids)
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

    def resolve_users(self, usernames: list[str]) -> list[OAUserSummary]:
        normalized = sorted({str(username or "").strip() for username in usernames if str(username or "").strip()})
        if not normalized:
            return []
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    (
                        "SELECT user_name, nick_name, status, del_flag FROM sys_user "
                        f"WHERE user_name IN ({_placeholders(len(normalized))}) ORDER BY user_name"
                    ),
                    normalized,
                )
                return [_user_summary_from_row(row) for row in list(cursor.fetchall() or [])]
        except Exception as exc:  # pragma: no cover - exercised in deployed env
            raise OARoleSyncExecutionError("Failed to resolve OA users.") from exc
        finally:
            connection.close()

    def search_users(self, query: str, limit: int) -> list[OAUserSummary]:
        normalized_query = str(query or "").strip()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                pattern = f"%{normalized_query}%"
                cursor.execute(
                    (
                        "SELECT user_name, nick_name, status, del_flag FROM sys_user "
                        "WHERE del_flag = '0' AND status = '0' "
                        "AND (user_name LIKE %s OR nick_name LIKE %s) "
                        "ORDER BY user_name LIMIT %s"
                    ),
                    (pattern, pattern, int(limit)),
                )
                return [_user_summary_from_row(row) for row in list(cursor.fetchall() or [])]
        except Exception as exc:  # pragma: no cover - exercised in deployed env
            raise OARoleSyncExecutionError("Failed to search OA users.") from exc
        finally:
            connection.close()

    def _connect(self):
        try:
            import pymysql  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised in deployed env
            raise OARoleSyncConfigurationError(
                "PyMySQL is required for OA role sync. Install backend requirements first."
            ) from exc
        try:
            return pymysql.connect(
                host=self._settings.host,
                port=self._settings.port,
                user=self._settings.username,
                password=self._settings.password,
                database=self._settings.database,
                charset="utf8mb4",
                autocommit=False,
                connect_timeout=self._settings.connect_timeout_seconds,
                read_timeout=self._settings.read_timeout_seconds,
                write_timeout=self._settings.write_timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - exercised in deployed env
            raise OARoleSyncExecutionError("Failed to connect to OA role database.") from exc

    def _load_role_ids(self, cursor) -> dict[str, int]:
        role_keys = [
            self._settings.user_role_key,
            self._settings.admin_role_key,
        ]
        cursor.execute(
            f"SELECT role_id, role_key FROM sys_role WHERE role_key IN ({_placeholders(len(role_keys))}) FOR UPDATE",
            role_keys,
        )
        rows = list(cursor.fetchall() or [])
        role_ids = {str(role_key): int(role_id) for role_id, role_key in rows}
        missing = sorted(set(role_keys).difference(role_ids))
        if missing:
            raise OARoleSyncExecutionError("Missing OA roles: " + ", ".join(missing))
        if len(rows) != len(role_keys):
            raise OARoleSyncExecutionError("OA dedicated role keys must each resolve exactly once.")
        return role_ids

    def _load_menu_id(self, cursor) -> int:
        cursor.execute(
            "SELECT menu_id FROM sys_menu WHERE perms = %s FOR UPDATE",
            (self._settings.required_permission,),
        )
        rows = list(cursor.fetchall() or [])
        if len(rows) != 1:
            raise OARoleSyncExecutionError(
                f"OA menu permission {self._settings.required_permission} must resolve exactly once."
            )
        return int(rows[0][0])

    def _validate_menu_bindings(self, cursor, menu_id: int, role_ids: dict[str, int]) -> None:
        cursor.execute(
            "SELECT role_id FROM sys_role_menu WHERE menu_id = %s FOR UPDATE",
            (menu_id,),
        )
        rows = list(cursor.fetchall() or [])
        actual_role_ids = [int(row[0]) for row in rows]
        expected_role_ids = set(role_ids.values())
        if len(actual_role_ids) != len(expected_role_ids) or set(actual_role_ids) != expected_role_ids:
            raise OARoleSyncExecutionError(
                "OA fin-ops menu bindings must contain exactly the two dedicated roles."
            )

    def _load_user_ids(self, cursor, assignments: list[OARoleAssignment]) -> dict[str, int]:
        usernames = [assignment.username for assignment in assignments]
        if not usernames:
            return {}
        cursor.execute(
            (
                f"SELECT user_id, user_name FROM sys_user WHERE user_name IN ({_placeholders(len(usernames))}) "
                "AND status = '0' AND del_flag = '0'"
            ),
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
            role_ids[self._settings.user_role_key],
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
            role_id = role_ids[self._role_key_for_assignment(assignment.role)]
            user_id = user_ids[assignment.username]
            cursor.execute(
                (
                    "INSERT INTO sys_user_role (user_id, role_id) "
                    "SELECT %s, %s FROM DUAL "
                    "WHERE NOT EXISTS (SELECT 1 FROM sys_user_role WHERE user_id = %s AND role_id = %s)"
                ),
                (user_id, role_id, user_id, role_id),
            )

    def _role_key_for_assignment(self, role: OARoleKind) -> str:
        return self._settings.admin_role_key if role == "admin" else self._settings.user_role_key


def _placeholders(count: int) -> str:
    return ", ".join(["%s"] * count)


def _user_summary_from_row(row: tuple[Any, ...]) -> OAUserSummary:
    username, display_name, status, deleted = row
    return OAUserSummary(
        username=str(username or "").strip(),
        display_name=str(display_name or username or "").strip(),
        active=str(status or "0") == "0" and str(deleted or "0") == "0",
    )
