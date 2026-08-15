from __future__ import annotations

from typing import Any

import pytest

from fin_ops_platform.app.routes_workbench_actions import WorkbenchActionApiRoutes
from fin_ops_platform.services.workbench_anomaly_review_service import (
    WorkbenchAnomalyReviewConflict,
    WorkbenchAnomalyReviewService,
)
from fin_ops_platform.services.postgres_repositories.workbench import (
    PostgresWorkbenchRepository,
)


class GroupRepository:
    def __init__(self, group: dict[str, object]) -> None:
        self.group = group

    def get_workbench_group_detail(self, **_kwargs: object) -> dict[str, object]:
        return {"group": self.group, "source_scope_key": "2026-05"}


class DecisionRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def set_workbench_anomaly_review_decision(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"changed": True, **kwargs}


def anomaly_group(*, blockers: list[str] | None = None) -> dict[str, object]:
    return {
        "group_id": "case:CASE-1",
        "completion": {
            "is_complete": False,
            "blocking_reasons": blockers or ["anomaly_review_required"],
        },
        "workbench_anomaly": {
            "fingerprint": "a" * 64,
            "items": [
                {"fingerprint": "b" * 64, "code": "oa_bank_amount_mismatch"},
                {"fingerprint": "c" * 64, "code": "bank_invoice_amount_mismatch"},
            ],
        },
        "oa_rows": [{"source_scope_key": "2026-05"}],
        "bank_rows": [],
        "invoice_rows": [],
    }


def service(group: dict[str, object]) -> tuple[WorkbenchAnomalyReviewService, DecisionRepository]:
    decisions = DecisionRepository()
    return (
        WorkbenchAnomalyReviewService(
            group_repository=GroupRepository(group),
            decision_repository=decisions,
        ),
        decisions,
    )


def payload(decision: str = "accept_paired") -> dict[str, object]:
    return {
        "month": "2026-05",
        "zone": "unpaired",
        "group_id": "case:CASE-1",
        "fingerprint": "a" * 64,
        "decision": decision,
        "review_classification_codes": [
            "oa_bank_amount_mismatch",
            "bank_invoice_amount_mismatch",
        ],
        "reviewed_item_fingerprints": ["c" * 64, "b" * 64],
    }


def test_review_requires_every_current_anomaly_item() -> None:
    target, decisions = service(anomaly_group())
    request = payload()
    request["reviewed_item_fingerprints"] = ["b" * 64]

    with pytest.raises(ValueError, match="每一项"):
        target.review(request, actor_id="reviewer")

    assert decisions.calls == []


def test_accept_paired_persists_auditable_review_for_anomaly_only_blocker() -> None:
    target, decisions = service(anomaly_group())

    result = target.review(payload(), actor_id="reviewer")

    assert result["affected_scope_keys"] == ["2026-05"]
    assert decisions.calls == [{
        "fingerprint": "a" * 64,
        "group_id": "case:CASE-1",
        "scope_key": "2026-05",
        "actor_id": "reviewer",
        "decision": "accept_paired",
        "note": "",
        "review_classification_codes": [
            "bank_invoice_amount_mismatch",
            "oa_bank_amount_mismatch",
        ],
        "reviewed_item_fingerprints": ["b" * 64, "c" * 64],
    }]


def test_accept_paired_cannot_bypass_other_relation_blockers() -> None:
    target, decisions = service(
        anomaly_group(blockers=["anomaly_review_required", "missing_invoice"])
    )

    with pytest.raises(WorkbenchAnomalyReviewConflict, match="不能强制"):
        target.review(payload(), actor_id="reviewer")

    assert decisions.calls == []


def test_keep_unpaired_is_valid_even_when_other_blockers_exist() -> None:
    target, decisions = service(
        anomaly_group(blockers=["anomaly_review_required", "missing_invoice"])
    )

    target.review(payload("keep_unpaired"), actor_id="reviewer")

    assert decisions.calls[0]["decision"] == "keep_unpaired"


def test_legacy_paired_amount_anomaly_can_be_withdrawn_without_a_classification() -> None:
    group = anomaly_group()
    anomaly = group["workbench_anomaly"]
    assert isinstance(anomaly, dict)
    anomaly["review_decision"] = "accept_paired"
    target, decisions = service(group)
    request = payload("keep_unpaired")
    request["zone"] = "paired"
    request["review_classification_codes"] = []

    target.review(request, actor_id="reviewer")

    assert decisions.calls[0]["decision"] == "keep_unpaired"
    assert decisions.calls[0]["review_classification_codes"] == []


def test_review_rejects_stale_fingerprint() -> None:
    target, decisions = service(anomaly_group())
    request = payload()
    request["fingerprint"] = "d" * 64

    with pytest.raises(WorkbenchAnomalyReviewConflict, match="已变化"):
        target.review(request, actor_id="reviewer")

    assert decisions.calls == []


def test_review_requires_one_manual_amount_classification_and_keeps_no_anomaly_exclusive() -> None:
    target, decisions = service(anomaly_group())
    request = payload()
    request["review_classification_codes"] = []

    with pytest.raises(ValueError, match="人工金额判断"):
        target.review(request, actor_id="reviewer")

    request["review_classification_codes"] = [
        "no_anomaly",
        "oa_bank_amount_mismatch",
    ]
    with pytest.raises(ValueError, match="不能与"):
        target.review(request, actor_id="reviewer")

    assert decisions.calls == []


def test_review_route_returns_stable_bad_request_contract() -> None:
    target, _decisions = service(anomaly_group())
    routes = WorkbenchActionApiRoutes(
        exception_service=object(),  # type: ignore[arg-type]
        write_facade_provider=lambda: object(),
        anomaly_review_service=target,
    )
    request = payload()
    request["reviewed_item_fingerprints"] = []

    status, result = routes.review_anomaly(request, actor_id="reviewer")

    assert int(status) == 400
    assert result["error"] == "invalid_workbench_anomaly_review_request"
    assert "每一项" in str(result["message"])


class ReadRecordingConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.fetch_all_calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
        return self.rows


class WriteRecordingConnection:
    def __init__(self, current: dict[str, object] | None = None) -> None:
        self.current = current
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_one(self, _sql: str, _params: tuple[Any, ...] = ()) -> dict[str, object] | None:
        return self.current

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        self.execute_calls.append((" ".join(sql.lower().split()), params))
        return 1


def test_repository_reads_latest_scoped_anomaly_review_and_excludes_it_from_legacy_cases() -> None:
    legacy_connection = ReadRecordingConnection([])
    assert PostgresWorkbenchRepository(legacy_connection).load_workbench_exception_cases() == {}
    legacy_sql, legacy_params = legacy_connection.fetch_all_calls[0]
    assert "scenario not in (%s, %s)" in legacy_sql
    assert legacy_params == ("oa_invoice_amount_mismatch", "workbench_anomaly_review")

    review_connection = ReadRecordingConnection([{
        "fingerprint": "a" * 64,
        "resolution": "accept_paired",
        "reviewed_item_fingerprints": ["b" * 64],
        "review_classification_codes": ["oa_bank_amount_mismatch"],
        "note": "已核对",
        "updated_by": "reviewer",
        "updated_at": "2026-08-15T08:00:00+08:00",
    }])
    decisions = PostgresWorkbenchRepository(
        review_connection
    ).load_workbench_anomaly_review_decisions(scope_key="2026-05")

    assert decisions["a" * 64] == {
        "decision": "accept_paired",
        "reviewed_item_fingerprints": ["b" * 64],
        "review_classification_codes": ["oa_bank_amount_mismatch"],
        "note": "已核对",
        "reviewed_by": "reviewer",
        "reviewed_at": "2026-08-15T08:00:00+08:00",
    }
    read_sql, read_params = review_connection.fetch_all_calls[0]
    assert "scope_month = %s::date" in read_sql
    assert "row_number() over" in read_sql
    assert read_params == ("workbench_anomaly_review", "2026-05-01")


def test_repository_anomaly_review_is_idempotent_and_audits_only_changes() -> None:
    changed_connection = WriteRecordingConnection()
    changed = PostgresWorkbenchRepository(
        changed_connection
    ).set_workbench_anomaly_review_decision(
        fingerprint="a" * 64,
        group_id="case:CASE-1",
        scope_key="2026-05",
        actor_id="reviewer",
        decision="accept_paired",
        note="已核对",
        review_classification_codes=["oa_bank_amount_mismatch"],
        reviewed_item_fingerprints=["b" * 64],
    )
    assert changed["changed"] is True
    assert any(
        "insert into app.workbench_exception_case_events" in sql
        for sql, _params in changed_connection.execute_calls
    )

    unchanged_connection = WriteRecordingConnection({
        "resolution": "accept_paired",
        "version": 1,
        "note": "已核对",
        "reviewed_item_fingerprints": ["b" * 64],
        "review_classification_codes": ["oa_bank_amount_mismatch"],
    })
    unchanged = PostgresWorkbenchRepository(
        unchanged_connection
    ).set_workbench_anomaly_review_decision(
        fingerprint="a" * 64,
        group_id="case:CASE-1",
        scope_key="2026-05",
        actor_id="reviewer",
        decision="accept_paired",
        note="已核对",
        review_classification_codes=["oa_bank_amount_mismatch"],
        reviewed_item_fingerprints=["b" * 64],
    )
    assert unchanged["changed"] is False
    assert unchanged_connection.execute_calls == []


def test_exception_apply_uses_authenticated_actor_instead_of_client_payload() -> None:
    captured: dict[str, object] = {}

    class WriteFacade:
        def apply_exception(
            self,
            request_payload: dict[str, object],
            *,
            actor: str,
            tenant_id: str,
            request_id: str | None,
            action_name: str,
        ) -> object:
            captured.update({
                "payload": request_payload,
                "actor": actor,
                "tenant_id": tenant_id,
                "request_id": request_id,
                "action_name": action_name,
            })
            return object()

    routes = WorkbenchActionApiRoutes(
        exception_service=object(),  # type: ignore[arg-type]
        write_facade_provider=WriteFacade,
        anomaly_review_service=object(),  # type: ignore[arg-type]
    )
    spoofed = {"actor": "spoofed-user", "confirmed_by": "spoofed-confirmed-by"}

    routes.exception_apply(
        spoofed,
        actor_id="YNSYLP005",
        tenant_id="default",
        request_id="req-exception-apply",
    )

    assert captured == {
        "payload": spoofed,
        "actor": "YNSYLP005",
        "tenant_id": "default",
        "request_id": "req-exception-apply",
        "action_name": "exception_apply",
    }
