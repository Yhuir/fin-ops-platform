from __future__ import annotations

from typing import Any

import pytest

from fin_ops_platform.app.routes_workbench_actions import WorkbenchActionApiRoutes
from fin_ops_platform.services.postgres_repositories.workbench import (
    PostgresWorkbenchRepository,
)
from fin_ops_platform.services.workbench_amount_mismatch_exception_service import (
    WorkbenchAmountMismatchConflict,
    WorkbenchAmountMismatchExceptionService,
)


FINGERPRINT = "a" * 64


class GroupRepository:
    def __init__(self, group: dict[str, object]) -> None:
        self.group = group
        self.calls: list[dict[str, object]] = []

    def get_workbench_group_detail(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return self.group


class DecisionRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def set_workbench_amount_mismatch_decision(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"status": "ignored", "changed": True}


def test_service_uses_actual_month_from_all_scope_group_and_server_actor() -> None:
    group_repository = GroupRepository(
        {
            "group_id": "case:CASE-1",
            "scope_key": "all",
            "source_scope_key": "2026-05",
            "amount_anomaly": {"fingerprint": FINGERPRINT, "state": "active"},
        }
    )
    decision_repository = DecisionRepository()
    service = WorkbenchAmountMismatchExceptionService(
        group_repository=group_repository,
        decision_repository=decision_repository,
    )

    result = service.set_ignored(
        {
            "month": "all",
            "zone": "paired",
            "group_id": "case:CASE-1",
            "fingerprint": FINGERPRINT,
            "expected_read_model_version": "generation-set-1",
        },
        actor_id="YNSYLP005",
        ignored=True,
    )

    assert decision_repository.calls == [
        {
            "fingerprint": FINGERPRINT,
            "group_id": "case:CASE-1",
            "scope_key": "2026-05",
            "actor_id": "YNSYLP005",
            "ignored": True,
        }
    ]
    assert result["affected_scope_keys"] == ["2026-05"]
    assert result["read_model_version"] == "generation-set-1"


def test_service_rejects_stale_or_changed_anomaly() -> None:
    service = WorkbenchAmountMismatchExceptionService(
        group_repository=GroupRepository(
            {"amount_anomaly": {"fingerprint": "b" * 64}, "source_scope_key": "2026-05"}
        ),
        decision_repository=DecisionRepository(),
    )

    with pytest.raises(WorkbenchAmountMismatchConflict, match="已变化或已消失"):
        service.set_ignored(
            {
                "month": "all",
                "zone": "paired",
                "group_id": "case:CASE-1",
                "fingerprint": FINGERPRINT,
                "expected_read_model_version": "generation-set-1",
            },
            actor_id="YNSYLP005",
            ignored=True,
        )


class RecordingConnection:
    def __init__(self, current: dict[str, object] | None = None) -> None:
        self.current = current
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_one(self, _sql: str, _params: tuple[Any, ...] = ()) -> dict[str, object] | None:
        return self.current

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        self.execute_calls.append((" ".join(sql.lower().split()), params))
        return 1


class ReadRecordingConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.fetch_all_calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
        return self.rows


def test_repository_separates_amount_decisions_from_legacy_cases_and_scopes_reads() -> None:
    legacy_connection = ReadRecordingConnection([])
    assert PostgresWorkbenchRepository(legacy_connection).load_workbench_exception_cases() == {}
    legacy_sql, legacy_params = legacy_connection.fetch_all_calls[0]
    assert "scenario is distinct from %s" in legacy_sql
    assert legacy_params == ("oa_invoice_amount_mismatch",)

    decision_connection = ReadRecordingConnection([{"fingerprint": FINGERPRINT, "status": "ignored"}])
    decisions = PostgresWorkbenchRepository(decision_connection).load_workbench_amount_mismatch_decisions(
        scope_key="2026-05"
    )
    assert decisions == {FINGERPRINT: "ignored"}
    decision_sql, decision_params = decision_connection.fetch_all_calls[0]
    assert "scope_month = %s::date" in decision_sql
    assert decision_params == ("oa_invoice_amount_mismatch", "2026-05-01")


def test_repository_write_is_idempotent_and_audits_only_state_changes() -> None:
    changed_connection = RecordingConnection()
    changed = PostgresWorkbenchRepository(changed_connection).set_workbench_amount_mismatch_decision(
        fingerprint=FINGERPRINT,
        group_id="case:CASE-1",
        scope_key="2026-05",
        actor_id="YNSYLP005",
        ignored=True,
    )
    assert changed["changed"] is True
    assert any("insert into app.workbench_exception_case_events" in sql for sql, _ in changed_connection.execute_calls)

    unchanged_connection = RecordingConnection({"status": "ignored", "version": 1})
    unchanged = PostgresWorkbenchRepository(unchanged_connection).set_workbench_amount_mismatch_decision(
        fingerprint=FINGERPRINT,
        group_id="case:CASE-1",
        scope_key="2026-05",
        actor_id="YNSYLP005",
        ignored=True,
    )
    assert unchanged["changed"] is False
    assert not any(
        "insert into app.workbench_exception_case_events" in sql
        for sql, _ in unchanged_connection.execute_calls
    )


def test_action_route_returns_service_contract_without_accepting_client_actor() -> None:
    class AmountService:
        def set_ignored(
            self,
            payload: dict[str, object],
            *,
            actor_id: str,
            ignored: bool,
        ) -> dict[str, object]:
            assert "actor" not in payload
            assert actor_id == "YNSYLP005"
            assert ignored is True
            return {"status": "ignored", "affected_scope_keys": ["2026-05"]}

    routes = WorkbenchActionApiRoutes(
        exception_service=object(),  # type: ignore[arg-type]
        write_facade_provider=lambda: None,
        amount_mismatch_service=AmountService(),  # type: ignore[arg-type]
    )

    status_code, payload = routes.set_amount_mismatch_ignored(
        {"group_id": "case:CASE-1"},
        actor_id="YNSYLP005",
        ignored=True,
    )

    assert status_code == 200
    assert payload == {"status": "ignored", "affected_scope_keys": ["2026-05"]}
