from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import (
    OAPaymentStatusConfigurationError,
    OAPaymentStatusExecutionError,
    MySQLOAPaymentStatusRepository,
    OAPaymentStatusRecord,
    OAPaymentStatusSettings,
    PAY_STATUS_PAID,
    PAY_STATUS_PENDING,
    oa_flow_id_candidates,
)


class ScriptedCursor:
    def __init__(self, connection: "ScriptedConnection") -> None:
        self._connection = connection
        self._last_result: object = None

    def __enter__(self) -> "ScriptedCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self._connection.executed.append((" ".join(sql.split()), params))
        if self._connection.raise_on_execute is not None:
            raise self._connection.raise_on_execute
        self._last_result = self._connection.results.pop(0) if self._connection.results else None

    def fetchone(self) -> object:
        if isinstance(self._last_result, list):
            return self._last_result[0] if self._last_result else None
        return self._last_result

    def fetchall(self) -> list[object]:
        if isinstance(self._last_result, list):
            return list(self._last_result)
        if self._last_result is None:
            return []
        return [self._last_result]


class ScriptedConnection:
    def __init__(
        self,
        results: list[object] | None = None,
        *,
        raise_on_execute: Exception | None = None,
    ) -> None:
        self.results = list(results or [])
        self.raise_on_execute = raise_on_execute
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> ScriptedCursor:
        return ScriptedCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class OAPaymentStatusServiceTests(unittest.TestCase):
    def test_flow_id_candidates_prefer_mongo_document_id_for_payment_status_table(self) -> None:
        record = _oa_record(
            "oa-pay-2047",
            case_id="CASE-2047",
            detail_fields={
                "流程实例ID": "proc-2047",
                "流程ID": "ignored-duplicate-source",
                "Mongo文档ID": "mongo-doc-1",
                "流程请求ID": "2047",
                "OA单号": "PAY-2047",
            },
        )

        candidates = oa_flow_id_candidates(record)

        self.assertEqual(candidates.payment_flow_ids[0], "mongo-doc-1")

    def test_resolve_flow_id_returns_mongo_document_id_without_connecting(self) -> None:
        repository = MySQLOAPaymentStatusRepository(
            _settings(),
            connection_factory=lambda: (_ for _ in ()).throw(AssertionError("connection should not be opened")),
        )

        flow_id = repository.resolve_flow_id(
            _oa_record(
                "oa-pay-2047",
                detail_fields={"流程实例ID": "proc-2047", "Mongo文档ID": "mongo-doc-2047"},
            )
        )

        self.assertEqual(flow_id, "mongo-doc-2047")

    def test_resolve_flow_id_uses_oa_row_id_suffix_when_mongo_detail_is_missing(self) -> None:
        repository = MySQLOAPaymentStatusRepository(
            _settings(),
            connection_factory=lambda: (_ for _ in ()).throw(AssertionError("connection should not be opened")),
        )

        flow_id = repository.resolve_flow_id(
            _oa_record("oa-pay-507f1f77bcf86cd799439011", detail_fields={"流程实例ID": "proc-2047"})
        )

        self.assertEqual(flow_id, "507f1f77bcf86cd799439011")

    def test_resolve_flow_id_does_not_use_process_or_flow_request_id_as_payment_key(self) -> None:
        repository = MySQLOAPaymentStatusRepository(
            _settings(),
            connection_factory=lambda: (_ for _ in ()).throw(AssertionError("connection should not be opened")),
        )

        flow_id = repository.resolve_flow_id(
            _oa_record(
                "",
                detail_fields={
                    "流程实例ID": "proc-2047",
                    "流程请求ID": "2047",
                    "OA单号": "PAY-2047",
                },
            )
        )

        self.assertIsNone(flow_id)

    def test_get_payment_status_reads_latest_status_for_flow_id(self) -> None:
        connection = ScriptedConnection([("507f1f77bcf86cd799439011", PAY_STATUS_PAID)])
        repository = MySQLOAPaymentStatusRepository(_settings(), connection_factory=lambda: connection)

        record = repository.get_payment_status("507f1f77bcf86cd799439011")

        self.assertEqual(record, OAPaymentStatusRecord(flow_id="507f1f77bcf86cd799439011", pay_status=PAY_STATUS_PAID))
        self.assertEqual(record.label if record else "", "已支付")
        self.assertIn("ORDER BY create_time DESC, id DESC", connection.executed[0][0])
        self.assertTrue(connection.closed)

    def test_mark_paid_updates_all_existing_rows_for_flow_id(self) -> None:
        connection = ScriptedConnection(
            [
                [
                    (10, "507f1f77bcf86cd799439011", PAY_STATUS_PENDING),
                    (9, "507f1f77bcf86cd799439011", PAY_STATUS_PAID),
                ],
            ]
        )
        repository = MySQLOAPaymentStatusRepository(_settings(), connection_factory=lambda: connection)

        record = repository.mark_paid("507f1f77bcf86cd799439011")

        self.assertEqual(record, OAPaymentStatusRecord(flow_id="507f1f77bcf86cd799439011", pay_status=PAY_STATUS_PAID))
        self.assertIn("FOR UPDATE", connection.executed[0][0])
        self.assertIn("UPDATE t_payment_simple SET pay_status", connection.executed[1][0])
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.closed)

    def test_mark_paid_inserts_row_when_flow_id_has_no_payment_status_record(self) -> None:
        connection = ScriptedConnection([[]])
        repository = MySQLOAPaymentStatusRepository(_settings(), connection_factory=lambda: connection)

        record = repository.mark_paid("507f1f77bcf86cd799439012")

        self.assertEqual(record.pay_status, PAY_STATUS_PAID)
        self.assertIn("INSERT INTO t_payment_simple", connection.executed[1][0])
        self.assertTrue(connection.committed)

    def test_mark_paid_rolls_back_and_closes_connection_on_write_error(self) -> None:
        connection = ScriptedConnection(raise_on_execute=RuntimeError("mysql down"))
        repository = MySQLOAPaymentStatusRepository(_settings(), connection_factory=lambda: connection)

        with self.assertRaises(OAPaymentStatusExecutionError):
            repository.mark_paid("507f1f77bcf86cd799439011")

        self.assertTrue(connection.rolled_back)
        self.assertFalse(connection.committed)
        self.assertTrue(connection.closed)

    def test_from_environment_is_disabled_by_default_and_requires_enabled_config(self) -> None:
        env_keys = [
            "FIN_OPS_OA_PAYMENT_STATUS_ENABLED",
            "FIN_OPS_OA_PAYMENT_STATUS_HOST",
            "FIN_OPS_OA_PAYMENT_STATUS_DATABASE",
            "FIN_OPS_OA_PAYMENT_STATUS_USERNAME",
            "FIN_OPS_OA_PAYMENT_STATUS_PASSWORD",
        ]
        with patch.dict(os.environ, {key: "" for key in env_keys}, clear=True):
            self.assertIsNone(MySQLOAPaymentStatusRepository.from_environment())

        with patch.dict(os.environ, {"FIN_OPS_OA_PAYMENT_STATUS_ENABLED": "1"}, clear=True):
            with self.assertRaises(OAPaymentStatusConfigurationError):
                MySQLOAPaymentStatusRepository.from_environment()


def _settings() -> OAPaymentStatusSettings:
    return OAPaymentStatusSettings(
        enabled=True,
        host="127.0.0.1",
        port=3306,
        database="smart_oa",
        username="root",
        password="secret",
        connect_timeout_seconds=5,
    )


def _oa_record(
    record_id: str,
    *,
    case_id: str | None = None,
    detail_fields: dict[str, object] | None = None,
) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=record_id,
        month="2026-06",
        section="open",
        case_id=case_id,
        applicant="刘际涛",
        project_name="测试项目",
        apply_type="支付申请",
        amount="199.00",
        counterparty_name="测试供应商",
        reason="测试付款",
        relation_code="pending_match",
        relation_label="待找流水",
        relation_tone="warn",
        workflow_status="in_progress",
        detail_fields=dict(detail_fields or {}),
    )
