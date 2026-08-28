from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable, Protocol

from fin_ops_platform.services.imports import clean_string
from fin_ops_platform.services.oa_adapter import OAApplicationRecord


PAY_STATUS_PENDING = 0
PAY_STATUS_PAID = 1
PAY_STATUS_FAILED = 2
_EMPTY_TEXT_VALUES = {"", "--", "—", "-", "——", "nan", "NaN", "None"}


class OAPaymentStatusError(RuntimeError):
    pass


class OAPaymentStatusConfigurationError(OAPaymentStatusError):
    pass


class OAPaymentStatusExecutionError(OAPaymentStatusError):
    pass


@dataclass(slots=True, frozen=True)
class OAPaymentStatusSettings:
    enabled: bool
    host: str
    port: int
    database: str
    username: str
    password: str
    connect_timeout_seconds: int


@dataclass(slots=True, frozen=True)
class OAPaymentStatusRecord:
    flow_id: str
    pay_status: int

    @property
    def label(self) -> str:
        if self.pay_status == PAY_STATUS_PAID:
            return "已支付"
        if self.pay_status == PAY_STATUS_FAILED:
            return "支付失败"
        return "待支付"


@dataclass(slots=True, frozen=True)
class OAFlowIdCandidates:
    payment_flow_ids: tuple[str, ...]


class OAPaymentStatusRepository(Protocol):
    def resolve_flow_id(self, record: OAApplicationRecord) -> str | None: ...

    def list_payment_statuses(self) -> dict[str, OAPaymentStatusRecord]: ...

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None: ...

    def mark_paid(self, flow_id: str) -> OAPaymentStatusRecord: ...

    def mark_pending(self, flow_id: str) -> OAPaymentStatusRecord: ...


def oa_flow_id_candidates(record: OAApplicationRecord) -> OAFlowIdCandidates:
    detail_fields = record.detail_fields if isinstance(record.detail_fields, dict) else {}
    payment_flow_ids = _dedupe_texts(
        detail_fields.get("支付状态FlowID"),
        detail_fields.get("支付状态flow_id"),
        detail_fields.get("paymentFlowId"),
        detail_fields.get("payment_flow_id"),
        detail_fields.get("Mongo文档ID"),
        detail_fields.get("mongo_id"),
        _row_id_suffix(record.id),
    )
    return OAFlowIdCandidates(
        payment_flow_ids=payment_flow_ids,
    )


class MySQLOAPaymentStatusRepository:
    def __init__(
        self,
        settings: OAPaymentStatusSettings,
        *,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._connection_factory = connection_factory

    @classmethod
    def from_environment(cls) -> "MySQLOAPaymentStatusRepository | None":
        if not _is_truthy(os.getenv("FIN_OPS_OA_PAYMENT_STATUS_ENABLED")):
            return None
        required = {
            "host": os.getenv("FIN_OPS_OA_PAYMENT_STATUS_HOST", "").strip(),
            "database": os.getenv("FIN_OPS_OA_PAYMENT_STATUS_DATABASE", "").strip(),
            "username": os.getenv("FIN_OPS_OA_PAYMENT_STATUS_USERNAME", "").strip(),
            "password": os.getenv("FIN_OPS_OA_PAYMENT_STATUS_PASSWORD", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise OAPaymentStatusConfigurationError(
                "Missing OA payment status configuration: " + ", ".join(sorted(missing))
            )
        return cls(
            OAPaymentStatusSettings(
                enabled=True,
                host=required["host"],
                port=int(os.getenv("FIN_OPS_OA_PAYMENT_STATUS_PORT", "3306")),
                database=required["database"],
                username=required["username"],
                password=required["password"],
                connect_timeout_seconds=max(int(os.getenv("FIN_OPS_OA_PAYMENT_STATUS_CONNECT_TIMEOUT_SECONDS", "5")), 1),
            )
        )

    def resolve_flow_id(self, record: OAApplicationRecord) -> str | None:
        candidates = oa_flow_id_candidates(record)
        if candidates.payment_flow_ids:
            return candidates.payment_flow_ids[0]
        return None

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None:
        normalized_flow_id = _required_text(flow_id, "flow_id")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT flow_id, pay_status
                    FROM t_payment_simple
                    WHERE flow_id = %s
                    ORDER BY create_time DESC, id DESC
                    LIMIT 1
                    """,
                    (normalized_flow_id,),
                )
                row = cursor.fetchone()
            return _payment_status_record(row)
        except Exception as exc:  # pragma: no cover - deployed dependency path
            if isinstance(exc, OAPaymentStatusError):
                raise
            raise OAPaymentStatusExecutionError(f"Failed to read OA payment status: {exc}") from exc
        finally:
            connection.close()

    def list_payment_statuses(self) -> dict[str, OAPaymentStatusRecord]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT flow_id, pay_status
                    FROM t_payment_simple
                    WHERE flow_id IS NOT NULL AND flow_id <> ''
                    ORDER BY create_time DESC, id DESC
                    """
                )
                rows = list(cursor.fetchall() or [])
            statuses: dict[str, OAPaymentStatusRecord] = {}
            for row in rows:
                record = _payment_status_record(row)
                if record is not None and record.flow_id not in statuses:
                    statuses[record.flow_id] = record
            return statuses
        except Exception as exc:  # pragma: no cover - deployed dependency path
            if isinstance(exc, OAPaymentStatusError):
                raise
            raise OAPaymentStatusExecutionError(f"Failed to list OA payment statuses: {exc}") from exc
        finally:
            connection.close()

    def mark_paid(self, flow_id: str) -> OAPaymentStatusRecord:
        normalized_flow_id = _required_text(flow_id, "flow_id")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, flow_id, pay_status
                    FROM t_payment_simple
                    WHERE flow_id = %s
                    ORDER BY create_time DESC, id DESC
                    FOR UPDATE
                    """,
                    (normalized_flow_id,),
                )
                rows = list(cursor.fetchall() or [])
                _assert_not_failed(rows, normalized_flow_id)
                if rows:
                    cursor.execute(
                        "UPDATE t_payment_simple SET pay_status = %s WHERE flow_id = %s AND pay_status <> %s",
                        (PAY_STATUS_PAID, normalized_flow_id, PAY_STATUS_PAID),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO t_payment_simple(flow_id, pay_status) VALUES (%s, %s)",
                        (normalized_flow_id, PAY_STATUS_PAID),
                    )
            connection.commit()
            return OAPaymentStatusRecord(flow_id=normalized_flow_id, pay_status=PAY_STATUS_PAID)
        except Exception as exc:  # pragma: no cover - deployed dependency path
            connection.rollback()
            if isinstance(exc, OAPaymentStatusError):
                raise
            raise OAPaymentStatusExecutionError(f"Failed to mark OA payment status as paid: {exc}") from exc
        finally:
            connection.close()

    def mark_pending(self, flow_id: str) -> OAPaymentStatusRecord:
        normalized_flow_id = _required_text(flow_id, "flow_id")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, flow_id, pay_status
                    FROM t_payment_simple
                    WHERE flow_id = %s
                    ORDER BY create_time DESC, id DESC
                    FOR UPDATE
                    """,
                    (normalized_flow_id,),
                )
                rows = list(cursor.fetchall() or [])
                _assert_not_failed(rows, normalized_flow_id)
                if rows:
                    cursor.execute(
                        "UPDATE t_payment_simple SET pay_status = %s WHERE flow_id = %s AND pay_status <> %s",
                        (PAY_STATUS_PENDING, normalized_flow_id, PAY_STATUS_PENDING),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO t_payment_simple(flow_id, pay_status) VALUES (%s, %s)",
                        (normalized_flow_id, PAY_STATUS_PENDING),
                    )
            connection.commit()
            return OAPaymentStatusRecord(flow_id=normalized_flow_id, pay_status=PAY_STATUS_PENDING)
        except Exception as exc:  # pragma: no cover - deployed dependency path
            connection.rollback()
            if isinstance(exc, OAPaymentStatusError):
                raise
            raise OAPaymentStatusExecutionError(f"Failed to mark OA payment status as pending: {exc}") from exc
        finally:
            connection.close()

    def _connect(self) -> Any:
        if self._connection_factory is not None:
            return self._connection_factory()
        try:
            import pymysql  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised in deployed env
            raise OAPaymentStatusConfigurationError(
                "PyMySQL is required for OA payment status sync. Install backend requirements first."
            ) from exc
        return pymysql.connect(
            host=self._settings.host,
            port=self._settings.port,
            user=self._settings.username,
            password=self._settings.password,
            database=self._settings.database,
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=self._settings.connect_timeout_seconds,
        )


def _payment_status_record(row: Any) -> OAPaymentStatusRecord | None:
    flow_id = _first_row_text(row, 0, "flow_id")
    pay_status = _first_row_text(row, 1, "pay_status")
    if not flow_id or pay_status == "":
        return None
    return OAPaymentStatusRecord(flow_id=flow_id, pay_status=int(pay_status))


def _assert_not_failed(rows: list[Any], flow_id: str) -> None:
    if any(_first_row_text(row, 2, "pay_status") == str(PAY_STATUS_FAILED) for row in rows):
        raise OAPaymentStatusExecutionError(
            f"OA payment status is failed and requires explicit handling: {flow_id}"
        )


def _first_row_text(row: Any, index: int, key: str) -> str:
    if row is None:
        return ""
    if isinstance(row, dict):
        if key in row:
            return _optional_text(row.get(key))
        lowered_key = key.lower()
        if lowered_key in row:
            return _optional_text(row.get(lowered_key))
        return ""
    try:
        return _optional_text(row[index])
    except (IndexError, TypeError):
        return ""


def _required_text(value: Any, field_name: str) -> str:
    normalized = _optional_text(value)
    if not normalized:
        raise OAPaymentStatusExecutionError(f"{field_name} is required.")
    return normalized


def _row_id_suffix(row_id: Any) -> str:
    normalized = _optional_text(row_id)
    for prefix in ("oa-pay-", "oa-exp-"):
        if normalized.startswith(prefix):
            return normalized.removeprefix(prefix)
    return normalized


def _dedupe_texts(*values: Any) -> tuple[str, ...]:
    deduped: list[str] = []
    for value in values:
        normalized = _optional_text(value)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return tuple(deduped)


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    normalized = clean_string(value)
    if normalized in _EMPTY_TEXT_VALUES:
        return ""
    return normalized


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
