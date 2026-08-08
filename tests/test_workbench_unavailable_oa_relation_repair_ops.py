from __future__ import annotations

from fin_ops_platform.tools import workbench_unavailable_oa_relation_repair_ops as repair


class FakeConnection:
    def __init__(self, existing_oa_row_ids: list[str]) -> None:
        self.existing_oa_row_ids = set(existing_oa_row_ids)
        self.fetch_count = 0

    def fetch_all(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> list[dict[str, str]]:
        self.fetch_count += 1
        assert "from app.oa_applications" in sql
        requested = list(params[0])
        return [
            {"row_id": row_id}
            for row_id in requested
            if row_id in self.existing_oa_row_ids
        ]


class FakeCommandService:
    def __init__(self, relation: dict[str, object]) -> None:
        self.relation = relation
        self.calls: list[dict[str, object]] = []

    def list_active_relations(self) -> list[dict[str, object]]:
        return [self.relation]

    def remove_rows_from_active_relations(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"changed_case_ids": ["case-1"], "affected_months": ["2026-07"]}


def _relation(*, with_invoice: bool = False) -> dict[str, object]:
    row_ids = ["oa-missing", "bank-1"]
    row_types = ["oa", "bank"]
    if with_invoice:
        row_ids.append("invoice-1")
        row_types.append("invoice")
    return {
        "case_id": "case-1",
        "status": "active",
        "version": 7,
        "month_scope": "2026-07",
        "relation_mode": "manual_confirmed",
        "row_ids": row_ids,
        "row_types": row_types,
        "special_metadata": {},
    }


def test_plan_cancels_relation_when_only_one_member_survives() -> None:
    plan = repair._build_plan(FakeConnection([]), _relation())

    assert plan["missing_oa_row_ids"] == ["oa-missing"]
    assert plan["result_action"] == "cancel_relation"
    assert plan["surviving_members"] == [{"row_id": "bank-1", "row_type": "bank"}]


def test_plan_preserves_valid_bank_invoice_relation() -> None:
    plan = repair._build_plan(FakeConnection([]), _relation(with_invoice=True))

    assert plan["result_action"] == "replace_relation"
    assert plan["surviving_members"] == [
        {"row_id": "bank-1", "row_type": "bank"},
        {"row_id": "invoice-1", "row_type": "invoice"},
    ]


def test_discovery_reads_canonical_oa_rows_once_and_returns_only_missing_cases() -> None:
    missing = _relation()
    existing = _relation()
    existing["case_id"] = "case-existing"
    existing["row_ids"] = ["oa-existing", "bank-2"]
    connection = FakeConnection(["oa-existing"])

    summaries = repair._build_repair_summaries(connection, [missing, existing])

    assert connection.fetch_count == 1
    assert [item["case_id"] for item in summaries] == ["case-1"]
    assert summaries[0]["fingerprint"]


def test_execute_uses_relation_command_and_persist_boundary(monkeypatch) -> None:
    service = FakeCommandService(_relation())
    persisted: list[list[str]] = []
    monkeypatch.setattr(repair, "workbench_relation_command_service", lambda app: service)
    monkeypatch.setattr(
        repair,
        "persist_workbench_pair_relations",
        lambda app, case_ids: persisted.append(case_ids),
    )
    dry_run = repair.repair_unavailable_oa_relation(
        app=object(),
        connection=FakeConnection([]),
        case_id="case-1",
        execute=False,
        expected_fingerprint=None,
    )

    result = repair.repair_unavailable_oa_relation(
        app=object(),
        connection=FakeConnection([]),
        case_id="case-1",
        execute=True,
        expected_fingerprint=dry_run["fingerprint"],
    )

    assert result["status"] == "repaired"
    assert service.calls[0]["row_ids"] == ["oa-missing"]
    assert service.calls[0]["actor_id"] == repair.REPAIR_ACTOR_ID
    assert persisted == [["case-1"]]
