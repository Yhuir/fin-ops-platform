from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


class RecordingConnection:
    def __init__(
        self,
        *,
        invoice_types: list[str] | None = None,
        bank_directions: list[str] | None = None,
        bank_scope_keys: list[str] | None = None,
        invoice_scope_keys: list[str] | None = None,
        oa_scope_keys: list[str] | None = None,
        workbench_scope_keys: list[str] | None = None,
    ) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fetch_one_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.invoice_types = list(invoice_types or [])
        self.bank_directions = list(bank_directions or [])
        self.bank_scope_keys = list(["2026-05"] if bank_scope_keys is None else bank_scope_keys)
        self.invoice_scope_keys = list(["2026-05"] if invoice_scope_keys is None else invoice_scope_keys)
        self.oa_scope_keys = list([] if oa_scope_keys is None else oa_scope_keys)
        self.workbench_scope_keys = list([] if workbench_scope_keys is None else workbench_scope_keys)

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        normalized_sql = " ".join(sql.lower().split())
        if "select distinct invoice_type" in normalized_sql:
            return [{"invoice_type": invoice_type} for invoice_type in self.invoice_types]
        if "select distinct txn_direction" in normalized_sql:
            return [{"txn_direction": direction} for direction in self.bank_directions]
        if "select distinct to_char(txn_month, 'yyyy-mm') as scope_key from app.bank_transactions" in normalized_sql:
            return [{"scope_key": scope_key} for scope_key in self.bank_scope_keys]
        if "select distinct to_char(invoice_month, 'yyyy-mm') as scope_key from app.invoices" in normalized_sql:
            return [{"scope_key": scope_key} for scope_key in self.invoice_scope_keys]
        if "select distinct to_char(date_trunc('month', application_date)::date, 'yyyy-mm') as scope_key from app.oa_applications" in normalized_sql:
            return [{"scope_key": scope_key} for scope_key in self.oa_scope_keys]
        if "select distinct to_char(scope_month, 'yyyy-mm') as scope_key from read_model.workbench_rows" in normalized_sql:
            return [{"scope_key": scope_key} for scope_key in self.workbench_scope_keys]
        return []

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, object]:
        self.fetch_one_calls.append((sql, params))
        return {"source_version": 1}

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        self.execute_calls.append((sql, params))
        return 1


def _snapshot(
    *,
    relation_mode: str = "manual_confirmed",
    row_types: list[str] | None = None,
    month_scope: str = "2026-05",
) -> dict[str, object]:
    return {
        "pair_relations": {
            "CASE-1": {
                "case_id": "CASE-1",
                "relation_mode": relation_mode,
                "status": "active",
                "version": 1,
                "month_scope": month_scope,
                "row_ids": ["bank-1", "invoice-1"],
                "row_types": list(row_types or ["bank", "invoice"]),
            }
        },
        "pair_relation_history": [],
    }


def _json_payload(value: object) -> dict[str, object]:
    payload = getattr(value, "obj", value)
    return payload if isinstance(payload, dict) else {}


def _dirty_refresh_rows(connection: RecordingConnection) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sql, params in connection.fetch_one_calls:
        if "insert into job.read_model_dirty_scopes" not in " ".join(sql.lower().split()):
            continue
        rows.append(
            {
                "scope_type": str(params[1]),
                "scope_key": str(params[2]),
                "reason": str(params[3]),
                "payload": _json_payload(params[4]),
                "priority": str(params[-1]),
            }
        )
    rows.extend(_batch_refresh_rows(connection))
    return rows


def _outbox_refresh_rows(connection: RecordingConnection) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sql, params in connection.execute_calls:
        if "insert into job.outbox_events" not in " ".join(sql.lower().split()):
            continue
        rows.append(
            {
                "event_type": str(params[1]),
                "scope_type": str(params[3]),
                "scope_key": str(params[4]),
                "dedupe_key": str(params[5]),
                "priority": str(params[7]),
                "payload": _json_payload(params[8]),
            }
        )
    rows.extend(_batch_refresh_rows(connection))
    return rows


def _batch_refresh_rows(connection: RecordingConnection) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sql, params in connection.fetch_all_calls:
        normalized_sql = " ".join(sql.lower().split())
        if "with input(" not in normalized_sql or "insert into job.read_model_dirty_scopes" not in normalized_sql:
            continue
        for start in range(0, len(params), 9):
            row = params[start : start + 9]
            if len(row) != 9:
                continue
            rows.append(
                {
                    "scope_type": str(row[2]),
                    "scope_key": str(row[3]),
                    "reason": str(row[4]),
                    "priority": str(row[5]),
                    "payload": _json_payload(row[6]),
                    "event_type": str(row[7]),
                    "dedupe_key": str(row[8]),
                }
            )
    return rows


def _refresh_by_scope_type(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["scope_type"]): row for row in rows}


def _batch_queue_write_calls(connection: RecordingConnection) -> list[tuple[str, tuple[Any, ...]]]:
    return [
        (sql, params)
        for sql, params in connection.fetch_all_calls
        if "with input(" in " ".join(sql.lower().split())
        and "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]


def test_scoped_relation_load_uses_row_overlap_and_case_limited_history() -> None:
    class ScopedLoadConnection(RecordingConnection):
        def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
            self.fetch_all_calls.append((sql, params))
            normalized_sql = " ".join(sql.lower().split())
            if "from app.workbench_pair_relations" in normalized_sql:
                assert "row_ids && %s::text[]" in normalized_sql
                assert "case_id = any(%s::text[])" in normalized_sql
                assert params == (["bank-1"], ["CASE-1"])
                return [
                    {
                        "key": "CASE-1",
                        "raw_payload": {
                            "case_id": "CASE-1",
                            "row_ids": ["bank-1", "oa-1"],
                            "row_types": ["bank", "oa"],
                            "status": "active",
                        },
                    }
                ]
            if "from app.workbench_pair_relation_history" in normalized_sql:
                assert "where case_id = any(%s::text[])" in normalized_sql
                assert params == (["CASE-1"],)
                return [
                    {
                        "raw_payload": {
                            "normalized_payload": {
                                "operation_type": "confirm_link",
                                "after_relations": [{"case_id": "CASE-1"}],
                            }
                        }
                    }
                ]
            return super().fetch_all(sql, params)

    connection = ScopedLoadConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    snapshot = repository.load_workbench_pair_relations_for_row_ids(["bank-1"], case_ids=["CASE-1"])

    assert sorted(snapshot["pair_relations"]) == ["CASE-1"]
    assert snapshot["pair_relation_history"][0]["operation_type"] == "confirm_link"
    assert len(connection.fetch_all_calls) == 2


def test_relation_change_enqueues_relation_read_model_before_relevant_downstream_by_priority() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(_snapshot(), changed_case_ids={"CASE-1"})

    assert all("read_model.workbench_rows" not in sql for sql, _params in connection.fetch_all_calls)

    dirty_by_scope_type = _refresh_by_scope_type(_dirty_refresh_rows(connection))
    outbox_by_scope_type = _refresh_by_scope_type(_outbox_refresh_rows(connection))

    assert dirty_by_scope_type["workbench_relation"]["priority"] == "high"
    assert dirty_by_scope_type["workbench"]["priority"] == "high"
    assert dirty_by_scope_type["bank_detail"]["priority"] == "high"
    assert dirty_by_scope_type["invoice_lifecycle"]["priority"] == "high"
    assert dirty_by_scope_type["input_invoice_usage"]["priority"] == "high"
    assert dirty_by_scope_type["output_invoice_collection"]["priority"] == "high"
    assert dirty_by_scope_type["search"]["priority"] == "high"
    assert "tax_offset" not in dirty_by_scope_type
    assert "cost_statistics" not in dirty_by_scope_type
    assert "oa_pending_payment" not in dirty_by_scope_type
    assert "no_oa_bank_batch" not in dirty_by_scope_type
    assert outbox_by_scope_type["workbench_relation"]["priority"] == "high"
    assert outbox_by_scope_type["workbench"]["priority"] == "high"
    assert outbox_by_scope_type["bank_detail"]["priority"] == "high"
    assert outbox_by_scope_type["invoice_lifecycle"]["priority"] == "high"
    assert outbox_by_scope_type["search"]["priority"] == "high"
    assert not [
        row
        for row in _outbox_refresh_rows(connection)
        if str(row["scope_type"]) == "workbench" and str(row["scope_key"]) == "all"
    ]
    refresh_metadata = dirty_by_scope_type["workbench_relation"]["payload"]["metadata"]
    assert refresh_metadata["row_ids"] == ["bank-1", "invoice-1"]
    assert refresh_metadata["case_ids"] == ["CASE-1"]


def test_relation_repository_can_persist_without_refresh_fanout_for_uow_boundary() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection, enqueue_refreshes=False)

    repository.save_workbench_pair_relations(_snapshot(), changed_case_ids={"CASE-1"})

    normalized_fetch_all_sql = [" ".join(sql.lower().split()) for sql, _params in connection.fetch_all_calls]
    normalized_fetch_one_sql = [" ".join(sql.lower().split()) for sql, _params in connection.fetch_one_calls]
    normalized_execute_sql = [" ".join(sql.lower().split()) for sql, _params in connection.execute_calls]

    assert not normalized_fetch_all_sql
    assert not normalized_fetch_one_sql
    assert any("insert into app.workbench_pair_relations" in sql for sql in normalized_execute_sql)
    assert not any("insert into job.outbox_events" in sql for sql in normalized_execute_sql)


def test_no_oa_relation_change_keeps_no_oa_read_model_in_downstream_scope() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(relation_mode="no_oa_bank_batch", row_types=["bank"]),
        changed_case_ids={"CASE-1"},
    )

    dirty_by_scope_type = _refresh_by_scope_type(_dirty_refresh_rows(connection))

    assert dirty_by_scope_type["workbench_relation"]["priority"] == "high"
    assert dirty_by_scope_type["bank_detail"]["priority"] == "high"
    assert dirty_by_scope_type["cost_statistics"]["priority"] == "high"
    assert dirty_by_scope_type["search"]["priority"] == "high"
    assert dirty_by_scope_type["no_oa_bank_batch"]["priority"] == "high"
    assert dirty_by_scope_type["no_oa_bank_batch"]["payload"]["relation_mode"] == "no_oa_bank_batch"
    no_oa_outbox_rows = [
        row for row in _outbox_refresh_rows(connection) if str(row["scope_type"]) == "no_oa_bank_batch"
    ]
    assert no_oa_outbox_rows[-1]["dedupe_key"] == (
        "no_oa_bank_batch.read_model.refresh:no_oa_bank_batch:2026-05:no_oa_bank_batch"
    )
    assert no_oa_outbox_rows[-1]["payload"]["relation_mode"] == "no_oa_bank_batch"
    assert "input_invoice_usage" not in dirty_by_scope_type
    assert "output_invoice_collection" not in dirty_by_scope_type
    assert "tax_offset" not in dirty_by_scope_type
    assert "oa_pending_payment" not in dirty_by_scope_type


def test_bank_flow_relation_change_enqueues_bank_flow_read_model_refresh() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(relation_mode="bank_flow_rule_batch", row_types=["bank"]),
        changed_case_ids={"CASE-1"},
    )

    dirty_by_scope_type = _refresh_by_scope_type(_dirty_refresh_rows(connection))
    bank_flow_outbox_rows = [
        row for row in _outbox_refresh_rows(connection) if str(row["scope_type"]) == "bank_flow_rule_batch"
    ]

    assert "no_oa_bank_batch" not in dirty_by_scope_type
    normalized_fetch_sql = [" ".join(sql.lower().split()) for sql, _params in connection.fetch_all_calls]
    assert not any("from app.invoices" in sql for sql in normalized_fetch_sql)
    assert not any("from app.oa_applications" in sql for sql in normalized_fetch_sql)
    assert not any("select distinct to_char(txn_month, 'yyyy-mm') as scope_key" in sql for sql in normalized_fetch_sql)
    assert dirty_by_scope_type["bank_flow_rule_batch"]["priority"] == "high"
    assert dirty_by_scope_type["bank_flow_rule_batch"]["payload"]["relation_mode"] == "bank_flow_rule_batch"
    assert bank_flow_outbox_rows[-1]["dedupe_key"] == (
        "bank_flow_rule_batch.read_model.refresh:bank_flow_rule_batch:2026-05:bank_flow_rule_batch"
    )
    assert bank_flow_outbox_rows[-1]["payload"]["relation_mode"] == "bank_flow_rule_batch"
    assert dirty_by_scope_type["cost_statistics"]["priority"] == "high"


def test_relation_refresh_fanout_uses_one_batch_queue_write() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(relation_mode="bank_flow_rule_batch", row_types=["bank"]),
        changed_case_ids={"CASE-1"},
    )

    assert len(_batch_queue_write_calls(connection)) == 1
    assert "dirty_input as" in " ".join(_batch_queue_write_calls(connection)[0][0].lower().split())
    assert not any(
        "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
        for sql, _params in connection.fetch_one_calls
    )
    assert not any(
        "insert into job.outbox_events" in " ".join(sql.lower().split())
        for sql, _params in connection.execute_calls
    )


def test_input_expense_relation_change_skips_output_and_income_downstream_scopes() -> None:
    connection = RecordingConnection(invoice_types=["input"], bank_directions=["outflow"])
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(_snapshot(), changed_case_ids={"CASE-1"})

    dirty_rows = _dirty_refresh_rows(connection)
    dirty_by_scope_type = _refresh_by_scope_type(dirty_rows)
    pending_scope_keys = {
        str(row["scope_key"])
        for row in dirty_rows
        if str(row["scope_type"]) == "pending_invoice"
    }

    assert "input_invoice_usage" in dirty_by_scope_type
    assert "output_invoice_collection" not in dirty_by_scope_type
    assert "oa_pending_payment" not in dirty_by_scope_type
    assert pending_scope_keys == {
        "expense:all:2026-05",
        "expense:requires_invoice:2026-05",
        "expense:bank_statement_as_invoice:2026-05",
        "expense:no_invoice_required:2026-05",
    }


def test_pending_invoice_relation_refresh_uses_bank_month_not_invoice_month() -> None:
    connection = RecordingConnection(
        invoice_types=["input"],
        bank_directions=["outflow"],
        bank_scope_keys=["2026-02"],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(month_scope="2026-01"),
        changed_case_ids={"CASE-1"},
    )

    dirty_rows = _dirty_refresh_rows(connection)
    pending_scope_keys = {
        str(row["scope_key"])
        for row in dirty_rows
        if str(row["scope_type"]) == "pending_invoice"
    }

    assert pending_scope_keys == {
        "expense:all:2026-02",
        "expense:requires_invoice:2026-02",
        "expense:bank_statement_as_invoice:2026-02",
        "expense:no_invoice_required:2026-02",
    }


def test_relation_downstream_refresh_routes_scope_keys_by_row_domain() -> None:
    connection = RecordingConnection(
        invoice_types=["input"],
        bank_directions=["outflow"],
        bank_scope_keys=["2026-02"],
        invoice_scope_keys=["2026-01"],
        workbench_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(month_scope="2026-02"),
        changed_case_ids={"CASE-1"},
    )

    dirty_rows = _dirty_refresh_rows(connection)
    scope_keys_by_type: dict[str, set[str]] = {}
    for row in dirty_rows:
        scope_keys_by_type.setdefault(str(row["scope_type"]), set()).add(str(row["scope_key"]))

    assert scope_keys_by_type["workbench_relation"] == {"2026-01", "2026-02"}
    assert scope_keys_by_type["workbench"] == {"2026-01", "2026-02"}
    assert scope_keys_by_type["bank_detail"] == {"2026-02"}
    assert scope_keys_by_type["invoice_lifecycle"] == {"2026-01"}
    assert scope_keys_by_type["input_invoice_usage"] == {"2026-01"}
    assert "tax_offset" not in scope_keys_by_type
    assert scope_keys_by_type["search"] == {"2026-01", "2026-02"}
    assert "cost_statistics" not in scope_keys_by_type
    assert scope_keys_by_type["pending_invoice"] == {
        "expense:all:2026-02",
        "expense:requires_invoice:2026-02",
        "expense:bank_statement_as_invoice:2026-02",
        "expense:no_invoice_required:2026-02",
    }
    workbench_all_outbox_rows = [
        row
        for row in _outbox_refresh_rows(connection)
        if str(row["scope_type"]) == "workbench" and str(row["scope_key"]) == "all"
    ]
    assert not workbench_all_outbox_rows


def test_relation_refresh_uses_full_workbench_all_only_when_scope_is_unknown() -> None:
    connection = RecordingConnection(
        invoice_types=["input"],
        bank_directions=["outflow"],
        bank_scope_keys=[],
        invoice_scope_keys=[],
        oa_scope_keys=[],
        workbench_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(month_scope=""),
        changed_case_ids={"CASE-1"},
    )

    dirty_rows = _dirty_refresh_rows(connection)
    scope_keys_by_type: dict[str, set[str]] = {}
    for row in dirty_rows:
        scope_keys_by_type.setdefault(str(row["scope_type"]), set()).add(str(row["scope_key"]))

    assert scope_keys_by_type["workbench"] == {"all"}
    workbench_all_outbox_payloads = [
        dict(row["payload"])
        for row in _outbox_refresh_rows(connection)
        if str(row["scope_type"]) == "workbench" and str(row["scope_key"]) == "all"
    ]
    assert workbench_all_outbox_payloads
    assert "aggregate_only" not in workbench_all_outbox_payloads[-1]


def test_relation_downstream_refresh_enqueues_all_scope_when_oa_month_is_unresolved() -> None:
    connection = RecordingConnection(
        bank_scope_keys=["2026-04"],
        invoice_scope_keys=[],
        oa_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank", "oa"], month_scope="2026-04"),
        changed_case_ids={"CASE-1"},
    )

    dirty_rows = _dirty_refresh_rows(connection)
    scope_keys_by_type: dict[str, set[str]] = {}
    for row in dirty_rows:
        scope_keys_by_type.setdefault(str(row["scope_type"]), set()).add(str(row["scope_key"]))

    assert scope_keys_by_type["workbench_relation"] == {"2026-04"}
    assert scope_keys_by_type["oa_pending_payment"] == {"all"}


def test_relation_downstream_refresh_enqueues_all_scope_when_invoice_month_is_unresolved() -> None:
    connection = RecordingConnection(
        invoice_types=["input"],
        bank_directions=["outflow"],
        bank_scope_keys=["2026-04"],
        invoice_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank", "invoice"], month_scope="2026-04"),
        changed_case_ids={"CASE-1"},
    )

    dirty_rows = _dirty_refresh_rows(connection)
    scope_keys_by_type: dict[str, set[str]] = {}
    for row in dirty_rows:
        scope_keys_by_type.setdefault(str(row["scope_type"]), set()).add(str(row["scope_key"]))

    assert scope_keys_by_type["workbench_relation"] == {"2026-04"}
    assert scope_keys_by_type["input_invoice_usage"] == {"all"}
    assert scope_keys_by_type["oa_pending_payment"] == {"2026-04"}
    assert "tax_offset" not in scope_keys_by_type


def test_relation_downstream_refresh_routes_cost_statistics_by_bank_month_for_cost_bearing_relation() -> None:
    connection = RecordingConnection(
        bank_scope_keys=["2026-02"],
        oa_scope_keys=["2026-01"],
        workbench_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank", "oa"], month_scope="2026-02"),
        changed_case_ids={"CASE-1"},
    )

    dirty_rows = _dirty_refresh_rows(connection)
    cost_scope_keys = {
        str(row["scope_key"])
        for row in dirty_rows
        if str(row["scope_type"]) == "cost_statistics"
    }

    assert cost_scope_keys == {"active:2026-02", "all:2026-02"}


def test_relation_downstream_refresh_preserves_workbench_scope_fallback_for_legacy_rows() -> None:
    connection = RecordingConnection(
        invoice_types=[],
        bank_directions=["outflow"],
        bank_scope_keys=[],
        invoice_scope_keys=[],
        workbench_scope_keys=["2026-04"],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank"], month_scope=""),
        changed_case_ids={"CASE-1"},
    )

    dirty_rows = _dirty_refresh_rows(connection)
    scope_keys_by_type: dict[str, set[str]] = {}
    for row in dirty_rows:
        scope_keys_by_type.setdefault(str(row["scope_type"]), set()).add(str(row["scope_key"]))

    assert scope_keys_by_type["workbench_relation"] == {"2026-04"}
    assert scope_keys_by_type["bank_detail"] == {"2026-04"}
    assert scope_keys_by_type["search"] == {"2026-04"}
    assert "cost_statistics" not in scope_keys_by_type
    assert scope_keys_by_type["pending_invoice"] == {
        "expense:all:2026-04",
        "expense:requires_invoice:2026-04",
        "expense:bank_statement_as_invoice:2026-04",
        "expense:no_invoice_required:2026-04",
    }
