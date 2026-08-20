from __future__ import annotations

from typing import Any

import pytest

from fin_ops_platform.app.routes_workbench_actions import WorkbenchActionApiRoutes
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.workbench_anomaly_review_service import (
    WorkbenchAnomalyReviewConflict,
    WorkbenchAnomalyReviewService,
)


class GroupRepository:
    def __init__(self, group: dict[str, object], *, source_scope_key: str = "2026-05") -> None:
        self.group = group
        self.source_scope_key = source_scope_key
        self.calls: list[dict[str, object]] = []

    def get_workbench_group_detail(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"group": self.group, "source_scope_key": self.source_scope_key}


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
            "evidence_item_fingerprints": ["b" * 64, "c" * 64],
            "items": [
                {"fingerprint": "d" * 64, "code": "oa_bank_equal_invoice_more"},
                {"fingerprint": "e" * 64, "code": "oa_invoice_attachment_unparsed"},
            ],
        },
        "oa_rows": [{"source_scope_key": "2026-05"}],
        "bank_rows": [],
        "invoice_rows": [],
    }


def service(
    group: dict[str, object],
    *,
    source_scope_key: str = "2026-05",
) -> tuple[WorkbenchAnomalyReviewService, DecisionRepository, GroupRepository]:
    decisions = DecisionRepository()
    groups = GroupRepository(group, source_scope_key=source_scope_key)
    return (
        WorkbenchAnomalyReviewService(
            group_repository=groups,
            decision_repository=decisions,
        ),
        decisions,
        groups,
    )


def payload(decision: str = "accept_paired") -> dict[str, object]:
    return {
        "month": "2026-05",
        "zone": "unpaired",
        "group_id": "case:CASE-1",
        "fingerprint": "a" * 64,
        "decision": decision,
    }


def test_review_uses_current_server_evidence_and_ignores_client_classification_fields() -> None:
    target, decisions, _groups = service(anomaly_group())
    request = {
        **payload(),
        "reviewed_item_fingerprints": ["f" * 64],
        "review_classification_codes": ["no_anomaly"],
    }

    target.review(request, actor_id="reviewer")

    assert decisions.calls[0]["evidence_item_fingerprints"] == ["b" * 64, "c" * 64]
    assert decisions.calls[0]["detected_classification_codes"] == [
        "oa_bank_equal_invoice_more",
        "oa_invoice_attachment_unparsed",
    ]


def test_accept_paired_persists_auditable_review_for_anomaly_only_blocker() -> None:
    target, decisions, groups = service(anomaly_group())

    result = target.review(payload(), actor_id="reviewer")

    assert result["affected_scope_keys"] == ["2026-05"]
    assert groups.calls == [{
        "scope_key": "2026-05",
        "zone": "unpaired",
        "group_id": "case:CASE-1",
        "detail_key": None,
    }]
    assert decisions.calls[0] == {
        "fingerprint": "a" * 64,
        "group_id": "case:CASE-1",
        "scope_key": "2026-05",
        "actor_id": "reviewer",
        "decision": "accept_paired",
        "note": "",
        "detected_classification_codes": [
            "oa_bank_equal_invoice_more",
            "oa_invoice_attachment_unparsed",
        ],
        "evidence_item_fingerprints": ["b" * 64, "c" * 64],
    }


def test_accept_paired_cannot_bypass_other_relation_blockers() -> None:
    target, decisions, _groups = service(
        anomaly_group(blockers=["anomaly_review_required", "missing_invoice"])
    )

    with pytest.raises(WorkbenchAnomalyReviewConflict, match="不能强制"):
        target.review(payload(), actor_id="reviewer")

    assert decisions.calls == []


def test_keep_unpaired_is_valid_even_when_other_blockers_exist() -> None:
    target, decisions, _groups = service(
        anomaly_group(blockers=["anomaly_review_required", "missing_invoice"])
    )

    target.review(payload("keep_unpaired"), actor_id="reviewer")

    assert decisions.calls[0]["decision"] == "keep_unpaired"


def test_paired_anomaly_can_be_withdrawn_without_client_classification() -> None:
    group = anomaly_group()
    anomaly = group["workbench_anomaly"]
    assert isinstance(anomaly, dict)
    anomaly["review_decision"] = "accept_paired"
    target, decisions, _groups = service(group)

    target.review({**payload("keep_unpaired"), "zone": "paired"}, actor_id="reviewer")

    assert decisions.calls[0]["decision"] == "keep_unpaired"


def test_review_rejects_stale_fingerprint() -> None:
    target, decisions, _groups = service(anomaly_group())

    with pytest.raises(WorkbenchAnomalyReviewConflict, match="已变化"):
        target.review({**payload(), "fingerprint": "f" * 64}, actor_id="reviewer")

    assert decisions.calls == []


def test_review_route_returns_stable_bad_request_contract() -> None:
    target, _decisions, _groups = service(anomaly_group())
    routes = WorkbenchActionApiRoutes(
        write_facade_provider=lambda: object(),
        anomaly_review_service=target,
    )

    status, result = routes.review_anomaly({**payload(), "zone": "invalid"}, actor_id="reviewer")

    assert int(status) == 400
    assert result["error"] == "invalid_workbench_anomaly_review_request"


def test_review_forwards_detail_key_and_persists_cross_month_decision_globally() -> None:
    group = anomaly_group()
    group["oa_rows"] = [{"source_scope_key": "2026-06"}]
    group["bank_rows"] = [
        {"source_scope_key": "2026-06"},
        {"source_scope_key": "2026-04"},
    ]
    target, decisions, groups = service(group, source_scope_key="")
    request = {
        **payload("keep_unpaired"),
        "month": "all",
        "detail_key": "singleton:oa:OA-1",
    }

    result = target.review(request, actor_id="reviewer")

    assert groups.calls[0]["detail_key"] == "singleton:oa:OA-1"
    assert decisions.calls[0]["scope_key"] == "all"
    assert result["affected_scope_keys"] == ["all"]


def test_review_route_returns_specific_blocker_conflict_code() -> None:
    target, _decisions, _groups = service(
        anomaly_group(blockers=["anomaly_review_required", "missing_invoice"])
    )
    routes = WorkbenchActionApiRoutes(
        write_facade_provider=lambda: object(),
        anomaly_review_service=target,
    )

    status, result = routes.review_anomaly(payload(), actor_id="reviewer")

    assert int(status) == 409
    assert result["error"] == "workbench_anomaly_review_blocked"


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
        "note": "已核对",
        "updated_by": "reviewer",
        "updated_at": "2026-08-15T08:00:00+08:00",
    }])
    decisions = PostgresWorkbenchRepository(
        review_connection
    ).load_workbench_anomaly_review_decisions(scope_key="2026-05")

    assert decisions["a" * 64] == {
        "decision": "accept_paired",
        "note": "已核对",
        "reviewed_by": "reviewer",
        "reviewed_at": "2026-08-15T08:00:00+08:00",
    }
    read_sql, read_params = review_connection.fetch_all_calls[0]
    assert "(scope_month = %s::date or scope_month is null)" in read_sql
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
        detected_classification_codes=["oa_bank_equal_invoice_more"],
        evidence_item_fingerprints=["b" * 64],
    )
    assert changed["changed"] is True
    assert any(
        "insert into app.workbench_exception_case_events" in sql
        for sql, _params in changed_connection.execute_calls
    )

    unchanged_connection = WriteRecordingConnection({
        "resolution": "accept_paired",
        "version": 1,
        "scope_month": "2026-05-01",
        "note": "已核对",
        "evidence_item_fingerprints": ["b" * 64],
        "detected_classification_codes": ["oa_bank_equal_invoice_more"],
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
        detected_classification_codes=["oa_bank_equal_invoice_more"],
        evidence_item_fingerprints=["b" * 64],
    )
    assert unchanged["changed"] is False
    assert unchanged_connection.execute_calls == []


def test_repository_promotes_an_existing_monthly_decision_to_global_scope() -> None:
    connection = WriteRecordingConnection({
        "resolution": "accept_paired",
        "version": 1,
        "scope_month": "2026-05-01",
        "note": "已核对",
        "evidence_item_fingerprints": ["b" * 64],
        "detected_classification_codes": ["oa_bank_equal_invoice_more"],
    })

    result = PostgresWorkbenchRepository(connection).set_workbench_anomaly_review_decision(
        fingerprint="a" * 64,
        group_id="case:CASE-1",
        scope_key="all",
        actor_id="reviewer",
        decision="accept_paired",
        note="已核对",
        detected_classification_codes=["oa_bank_equal_invoice_more"],
        evidence_item_fingerprints=["b" * 64],
    )

    assert result["changed"] is True
    decision_write = next(
        params
        for sql, params in connection.execute_calls
        if "insert into app.workbench_exception_cases(" in sql
    )
    assert decision_write[4] is None
