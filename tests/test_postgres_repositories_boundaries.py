from __future__ import annotations

from pathlib import Path

from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_repositories.common import max_numeric_suffix
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.postgres_repositories.read_models import _execute_many
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.read_model_scope_policy import DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY


class TransactionRecorder:
    def __init__(self, parent: "RecordingConnection") -> None:
        self.parent = parent

    def __enter__(self) -> "TransactionRecorder":
        self.parent.transaction_enters += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.parent.transaction_exits += 1

    def execute(self, sql: str, params: tuple = ()) -> int:
        return self.parent.execute(sql, params)

    def execute_many(self, sql: str, params_seq: list[tuple]) -> int:
        return self.parent.execute_many(sql, params_seq)

    def execute_many_values(self, sql: str, params_seq: list[tuple], *, chunk_size: int = 200) -> int:
        return self.parent.execute_many_values(sql, params_seq, chunk_size=chunk_size)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        return self.parent.fetch_all(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        return self.parent.fetch_one(sql, params)


class RecordingConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.executed_many: list[tuple[str, list[tuple]]] = []
        self.executed_many_values: list[tuple[str, list[tuple]]] = []
        self.fetched_all: list[tuple[str, tuple]] = []
        self.fetched_one: list[tuple[str, tuple]] = []
        self.transaction_enters = 0
        self.transaction_exits = 0

    def transaction(self) -> TransactionRecorder:
        return TransactionRecorder(self)

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((" ".join(sql.split()), params))
        return 1

    def execute_many(self, sql: str, params_seq: list[tuple]) -> int:
        self.executed_many.append((" ".join(sql.split()), list(params_seq)))
        return len(params_seq)

    def execute_many_values(self, sql: str, params_seq: list[tuple], *, chunk_size: int = 200) -> int:
        _ = chunk_size
        rows = list(params_seq)
        self.executed_many_values.append((" ".join(sql.split()), rows))
        return len(rows)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.fetched_all.append((" ".join(sql.split()), params))
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetched_one.append((" ".join(sql.split()), params))
        return None


def write_sql(connection: RecordingConnection) -> list[str]:
    return [
        *(sql for sql, _params in connection.executed),
        *(sql for sql, _params in connection.executed_many),
        *(sql for sql, _params in connection.executed_many_values),
    ]


class ValuesBulkConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.executed_many_values: list[tuple[str, list[tuple]]] = []

    def transaction(self) -> "ValuesBulkConnection":
        return self

    def __enter__(self) -> "ValuesBulkConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((" ".join(sql.split()), params))
        return 1

    def execute_many_values(self, sql: str, params_seq: list[tuple], *, chunk_size: int = 200) -> int:
        _ = chunk_size
        rows = list(params_seq)
        self.executed_many_values.append((" ".join(sql.split()), rows))
        return len(rows)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        return None


class MappingParamsBulkConnection(ValuesBulkConnection):
    def __init__(self) -> None:
        super().__init__()
        self.executed_many: list[tuple[str, list[dict]]] = []

    def execute_many(self, sql: str, params_seq: list[dict]) -> int:
        rows = list(params_seq)
        self.executed_many.append((" ".join(sql.split()), rows))
        return len(rows)


class WorkbenchRelationWriteConnection(RecordingConnection):
    def __init__(self) -> None:
        super().__init__()
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetch_one_calls.append((" ".join(sql.split()), params))
        return {"source_version": 3}


def _workbench_relation_batch_refresh_rows(connection: WorkbenchRelationWriteConnection) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sql, params in connection.fetched_all:
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
                    "event_type": str(row[7]),
                    "dedupe_key": str(row[8]),
                }
            )
    return rows


class WorkbenchReadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized_sql = " ".join(sql.split())
        if "from app.workbench_pair_relations" in normalized_sql:
            return [
                {
                    "key": "case-1",
                    "raw_payload": {
                        "normalized_payload": {
                            "case_id": "case-1",
                            "row_ids": ["row-1"],
                        }
                    },
                }
            ]
        if "from app.workbench_pair_relation_history" in normalized_sql:
            rows = [
                {
                    "raw_payload": {
                        "normalized_payload": {
                            "case_id": "case-later",
                            "operation": "later",
                            "raw_payload": {"_stage04_child_index": 2},
                        }
                    }
                },
                {
                    "raw_payload": {
                        "normalized_payload": {
                            "case_id": "case-earlier",
                            "operation": "earlier",
                            "raw_payload": {"_stage04_child_index": 1},
                        }
                    }
                },
            ]
            if "_stage04_child_index" in normalized_sql:
                return list(reversed(rows))
            return rows
        return []


class ReadModelReadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "read_model.workbench_candidate_matches" in sql:
            return [
                {
                    "key": "candidate-1",
                    "payload": {
                        "month": "2026-05",
                        "row_ids": [],
                    },
                }
            ]
        return [
            {
                "key": "2026-05",
                "payload": {
                    "month": "2026-05",
                    "rows": [],
                    "rebuildable": True,
                },
            }
        ]


class HistoricalEtcReadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from app.historical_etc_repair_parsed_seeds" in sql:
            return [{"key": "ETC-HIST-2026-01", "parsed_payload": {"_id": "mongo-id", "case_id": "case-1"}}]
        if "from app.historical_etc_repair_states" in sql:
            return [{"key": "ETC-HIST-2026-01", "state_payload": {"_id": "mongo-id", "status": "parsed"}}]
        return []


class EtcReconciliationReadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from app.etc_reconciliation_tasks" in sql:
            return [
                {
                    "key": "ETC-RECON-000026",
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "transform-only-id",
                            "task_id": "ETC-RECON-000026",
                            "source_files": [{"file_id": "etc-recon-file-000060"}],
                            "audit_events": [{"event_id": "audit-event-000007"}],
                        }
                    },
                }
            ]
        if "from app.etc_reconciliation_files" in sql:
            return []
        return []


class EtcReconciliationDeletedFileReadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from app.etc_reconciliation_tasks" in sql:
            return [
                {
                    "key": "ETC-RECON-000026",
                    "raw_payload": {
                        "normalized_payload": {
                            "task_id": "ETC-RECON-000026",
                            "source_files": [],
                            "audit_events": [],
                        }
                    },
                }
            ]
        if "from app.etc_reconciliation_files" in sql:
            return [
                {
                    "task_id": "ETC-RECON-000026",
                    "key": "ETC-RECON-FILE-000061",
                    "status": "stored",
                    "raw_payload": {
                        "normalized_payload": {
                            "task_id": "ETC-RECON-000026",
                            "file_id": "ETC-RECON-FILE-000061",
                        }
                    },
                },
                {
                    "task_id": "ETC-RECON-000026",
                    "key": "ETC-RECON-FILE-000062",
                    "status": "deleted",
                    "raw_payload": {
                        "normalized_payload": {
                            "task_id": "ETC-RECON-000026",
                            "file_id": "ETC-RECON-FILE-000062",
                        }
                    },
                },
            ]
        return []


class RebuildableCandidateReadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        return [
            {
                "key": "candidate-1",
                "payload": {
                    "month": "2026-05",
                    "row_ids": [],
                    "rebuildable": True,
                },
            }
        ]


def test_workbench_category_replaces_events_and_category_in_one_transaction() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_bank_transaction_categories(
        {
            "categories": {"txn-1": {"category_code": "fee", "version": 1}},
            "audit_log": [{"transaction_id": "txn-1", "event_id": "evt-1"}],
        }
    )

    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    executed_sql = [sql for sql, _ in connection.executed]
    assert "delete from app.bank_transaction_category_events" in executed_sql[0]
    assert "delete from app.bank_transaction_categories" in executed_sql[1]
    assert "insert into app.bank_transaction_categories" in executed_sql[2]


def test_no_oa_bank_batch_save_deletes_removed_events_before_removed_batches() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_no_oa_bank_batches(
        {
            "batches": {
                "retained-batch": {
                    "batch_id": "retained-batch",
                    "status": "submitted",
                    "status_bucket": "submitted",
                    "version": 2,
                    "scope_month": "2026-03",
                    "account_key": "acct",
                    "row_ids": ["txn-1"],
                    "total_amount": "10.00",
                }
            },
            "audit_log": [{"batch_id": "retained-batch", "operation": "submitted"}],
        }
    )

    executed_sql = [sql for sql, _ in connection.executed]
    read_model_delete_index = next(
        index for index, sql in enumerate(executed_sql) if "delete from read_model.no_oa_bank_batch_rows" in sql
    )
    removed_events_delete_index = next(
        index
        for index, sql in enumerate(executed_sql)
        if "delete from app.no_oa_bank_batch_events where no_oa_bank_batch_id in" in sql
    )
    removed_batches_delete_index = next(
        index
        for index, sql in enumerate(executed_sql)
        if "delete from app.no_oa_bank_batches" in sql and "not (batch_id = any(%s))" in sql
    )

    assert read_model_delete_index < removed_events_delete_index < removed_batches_delete_index
    assert connection.executed[removed_events_delete_index][1] == ("no_oa_bank_batch", ["retained-batch"])
    assert connection.executed[removed_batches_delete_index][1] == ("no_oa_bank_batch", ["retained-batch"])


def test_no_oa_bank_batch_save_bulk_upserts_app_and_read_model_rows() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_no_oa_bank_batches(
        {
            "batches": {
                "batch-a": {
                    "batch_id": "batch-a",
                    "status": "draft",
                    "status_bucket": "unsubmitted",
                    "version": 1,
                    "scope_month": "2026-03",
                    "account_key": "acct-a",
                    "row_ids": ["txn-a"],
                    "total_amount": "10.00",
                },
                "batch-b": {
                    "batch_id": "batch-b",
                    "status": "submitted",
                    "status_bucket": "submitted",
                    "version": 2,
                    "scope_month": "2026-03",
                    "account_key": "acct-b",
                    "row_ids": ["txn-b"],
                    "total_amount": "20.00",
                },
            },
            "audit_log": [],
        }
    )

    app_upserts = [
        params_seq
        for sql, params_seq in connection.executed_many_values
        if sql.startswith("insert into app.no_oa_bank_batches(")
    ]
    read_model_upserts = [
        params_seq
        for sql, params_seq in connection.executed_many_values
        if sql.startswith("insert into read_model.no_oa_bank_batch_rows(")
    ]
    assert [len(params_seq) for params_seq in app_upserts] == [2]
    assert [len(params_seq) for params_seq in read_model_upserts] == [2]
    assert not any(sql.startswith("insert into app.no_oa_bank_batches(") for sql, _params in connection.executed)
    assert not any(
        sql.startswith("insert into read_model.no_oa_bank_batch_rows(") for sql, _params in connection.executed
    )


def test_read_model_bulk_insert_prefers_multi_values_path_for_allowlisted_tables() -> None:
    connection = ValuesBulkConnection()

    allowlisted_sql = [
        "insert into read_model.workbench_rows(row_id, payload) values (%s, %s)",
        "insert into read_model.workbench_groups(group_id, payload) values (%s, %s)",
        "insert into read_model.workbench_group_rows(group_id, payload) values (%s, %s)",
        "insert into read_model.workbench_relation_rows(row_id, payload) values (%s, %s)",
        "insert into read_model.workbench_relation_groups(group_id, payload) values (%s, %s)",
        "insert into read_model.search_index_rows(row_id, payload) values (%s, %s)",
        "insert into read_model.turnover_ledger_rows(relation_id, payload) values (%s, %s)",
    ]
    for sql in allowlisted_sql:
        _execute_many(
            connection,
            sql,
            [("row-1", {"row_id": "row-1"})],
        )

    assert len(connection.executed_many_values) == len(allowlisted_sql)
    assert all(len(params) == 1 for _sql, params in connection.executed_many_values)
    for sql in allowlisted_sql:
        table_name = sql.split("(")[0]
        assert any(table_name in recorded_sql for recorded_sql, _params in connection.executed_many_values)


def test_read_model_bulk_insert_with_mapping_params_uses_execute_many() -> None:
    connection = MappingParamsBulkConnection()

    _execute_many(
        connection,
        "insert into read_model.input_invoice_usage_rows(row_id, payload) values (%(row_id)s, %(payload)s)",
        [{"row_id": "invoice-1", "payload": {"row_id": "invoice-1"}}],
    )

    assert len(connection.executed_many) == 1
    assert connection.executed_many_values == []


def test_workbench_relation_distribution_save_batches_rows_and_groups() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.save_workbench_relation_distribution(
        scope_key="2026-05",
        groups=[
            {
                "group_id": "case-1",
                "relation_source": "manual",
                "relation_kind": "linked",
                "relation_status": "linked",
                "bank_transaction_ids": ["txn-1"],
                "payload": {"case_id": "case-1", "row_ids": ["txn-1"]},
            }
        ],
        rows=[
            {
                "row_id": "txn-1",
                "row_type": "bank_transaction",
                "relation_status": "linked",
                "group_ids": ["case-1"],
            }
        ],
        source_versions={"source_version": 9},
    )

    bulk_sql = [sql for sql, _params in connection.executed_many_values]
    assert any("insert into read_model.workbench_relation_groups" in sql for sql in bulk_sql)
    assert any("insert into read_model.workbench_relation_rows" in sql for sql in bulk_sql)
    assert not any(
        "insert into read_model.workbench_relation_groups" in sql
        or "insert into read_model.workbench_relation_rows" in sql
        for sql, _params in connection.executed
    )
    assert not any(
        "insert into read_model.workbench_relation_groups" in sql
        or "insert into read_model.workbench_relation_rows" in sql
        for sql, _params in connection.executed_many
    )


def test_workbench_relation_distribution_partial_save_deletes_overlap_and_counts_scope() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.save_workbench_relation_distribution_rows(
        scope_key="2026-05",
        affected_row_ids=["txn-1", "oa-1"],
        groups=[
            {
                "group_id": "case-1",
                "relation_source": "manual",
                "relation_kind": "oa_bank",
                "relation_status": "linked",
                "oa_row_ids": ["oa-1"],
                "bank_transaction_ids": ["txn-1"],
                "payload": {"case_id": "case-1", "row_ids": ["oa-1", "txn-1"]},
            }
        ],
        rows=[
            {
                "row_id": "txn-1",
                "row_type": "bank_transaction",
                "relation_status": "linked",
                "group_ids": ["case-1"],
            },
            {
                "row_id": "oa-1",
                "row_type": "oa",
                "relation_status": "linked",
                "group_ids": ["case-1"],
            },
        ],
        source_versions={"source_version": 10},
    )

    executed_sql = [sql for sql, _params in connection.executed]
    row_delete_index = next(
        index
        for index, sql in enumerate(executed_sql)
        if "delete from read_model.workbench_relation_rows target" in sql
    )
    group_delete_index = next(
        index for index, sql in enumerate(executed_sql) if "delete from read_model.workbench_relation_groups" in sql
    )
    assert row_delete_index < group_delete_index
    row_delete_sql, row_delete_params = connection.executed[row_delete_index]
    assert "with replaced_row_ids(row_id) as ( select unnest(%s::text[]) union select unnest(" in row_delete_sql
    assert "from read_model.workbench_relation_groups" in row_delete_sql
    assert "target.row_id = replacement.row_id" in row_delete_sql
    assert row_delete_params == (
        ["txn-1", "oa-1"],
        "default",
        "2026-05",
        ["case-1"],
        ["txn-1", "oa-1"],
        ["txn-1", "oa-1"],
        ["txn-1", "oa-1"],
        ["txn-1", "oa-1"],
        "default",
        "2026-05",
    )
    assert any("coalesce(bank_transaction_ids, array[]::text[]) && %s::text[]" in sql for sql in executed_sql)
    assert not any("update read_model.workbench_relation_rows" in sql for sql in executed_sql)
    assert not any("update read_model.workbench_relation_groups" in sql for sql in executed_sql)
    assert any(
        "select ( select count(*)::integer from read_model.workbench_relation_rows" in sql
        for sql, _params in connection.fetched_one
    )
    bulk_sql = [sql for sql, _params in connection.executed_many_values]
    assert any("insert into read_model.workbench_relation_groups" in sql for sql in bulk_sql)
    assert any("insert into read_model.workbench_relation_rows" in sql for sql in bulk_sql)


def test_no_oa_bank_batch_empty_snapshot_deletes_events_before_batches() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_no_oa_bank_batches({"batches": {}, "audit_log": []})

    executed_sql = [sql for sql, _ in connection.executed]
    events_delete_index = next(
        index for index, sql in enumerate(executed_sql) if "delete from app.no_oa_bank_batch_events" in sql
    )
    batches_delete_index = next(
        index for index, sql in enumerate(executed_sql) if "delete from app.no_oa_bank_batches" in sql
    )

    assert events_delete_index < batches_delete_index
    assert all(params == ("no_oa_bank_batch",) for _sql, params in connection.executed[:3])


def test_no_oa_bank_batch_scoped_save_deletes_only_target_scope_before_upsert() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_no_oa_bank_batches_scope(
        {
            "batches": {
                "march-batch": {
                    "batch_id": "march-batch",
                    "status": "draft",
                    "status_bucket": "unsubmitted",
                    "version": 1,
                    "scope_month": "2026-03",
                    "account_key": "acct",
                    "row_ids": ["txn-1"],
                    "total_amount": "10.00",
                },
                "april-batch": {
                    "batch_id": "april-batch",
                    "status": "draft",
                    "status_bucket": "unsubmitted",
                    "version": 1,
                    "scope_month": "2026-04",
                    "account_key": "acct",
                    "row_ids": ["txn-2"],
                    "total_amount": "20.00",
                },
                "bank-flow-march-batch": {
                    "batch_id": "bank-flow-march-batch",
                    "status": "submitted",
                    "status_bucket": "submitted",
                    "version": 1,
                    "scope_month": "2026-03",
                    "account_key": "acct",
                    "row_ids": ["txn-3"],
                    "total_amount": "30.00",
                    "relation_mode": "bank_flow_rule_batch",
                },
            },
            "audit_log": [
                {"batch_id": "march-batch", "operation": "refresh"},
                {"batch_id": "april-batch", "operation": "refresh"},
                {"batch_id": "bank-flow-march-batch", "operation": "refresh"},
            ],
        },
        scope_key="2026-03",
    )

    executed_sql = [sql for sql, _ in connection.executed]
    assert "delete from read_model.no_oa_bank_batch_rows where scope_month = %s::date" in executed_sql[0]
    assert "payload->>'relation_mode'" in executed_sql[0]
    assert "delete from app.no_oa_bank_batch_events where no_oa_bank_batch_id in" in executed_sql[1]
    assert "raw_payload->'normalized_payload'->>'relation_mode'" in executed_sql[1]
    assert "delete from app.no_oa_bank_batches where scope_month = %s::date" in executed_sql[2]
    assert connection.executed[0][1] == ("2026-03-01", "no_oa_bank_batch", ["march-batch"])
    assert connection.executed[1][1] == ("2026-03-01", "no_oa_bank_batch", ["march-batch"])
    assert connection.executed[2][1] == ("2026-03-01", "no_oa_bank_batch", ["march-batch"])
    assert not any(
        sql == "delete from read_model.no_oa_bank_batch_rows where not (batch_id = any(%s))" for sql in executed_sql
    )
    upsert_batch_params = [
        params
        for sql, params_seq in connection.executed_many_values
        if sql.startswith("insert into app.no_oa_bank_batches(")
        for params in params_seq
    ]
    assert len(upsert_batch_params) == 1
    assert upsert_batch_params[0][0] == "march-batch"
    assert not any(sql.startswith("insert into app.no_oa_bank_batches(") for sql, _params in connection.executed)
    assert not any(
        sql.startswith("insert into read_model.no_oa_bank_batch_rows(") for sql, _params in connection.executed
    )
    replaced_event_params = [
        params
        for sql, params in connection.executed
        if sql == "delete from app.no_oa_bank_batch_events where batch_id = %s"
    ]
    assert replaced_event_params == [("march-batch",)]


def test_bank_flow_rule_batch_save_uses_dedicated_physical_tables() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_bank_flow_rule_batches(
        {
            "batches": {
                "bank-flow-batch": {
                    "batch_id": "bank-flow-batch",
                    "status": "submitted",
                    "status_bucket": "submitted",
                    "version": 2,
                    "scope_month": "2026-03",
                    "account_key": "acct",
                    "row_ids": ["txn-1"],
                    "total_amount": "10.00",
                    "relation_mode": "bank_flow_rule_batch",
                }
            },
            "audit_log": [{"batch_id": "bank-flow-batch", "operation": "submitted"}],
        }
    )

    executed_sql = write_sql(connection)
    assert any("delete from read_model.bank_flow_rule_batch_rows" in sql for sql in executed_sql)
    assert any("delete from app.bank_flow_rule_batch_events" in sql for sql in executed_sql)
    assert any("delete from app.bank_flow_rule_batches" in sql for sql in executed_sql)
    assert any("insert into app.bank_flow_rule_batches(" in sql for sql in executed_sql)
    assert any("insert into read_model.bank_flow_rule_batch_rows(" in sql for sql in executed_sql)
    assert any("insert into app.bank_flow_rule_batch_events(" in sql for sql in executed_sql)
    assert not any(sql.startswith("insert into app.bank_flow_rule_batches(") for sql, _params in connection.executed)
    assert not any(
        sql.startswith("insert into read_model.bank_flow_rule_batch_rows(") for sql, _params in connection.executed
    )
    forbidden_tables = (
        "app.no_oa_bank_batches",
        "app.no_oa_bank_batch_events",
        "read_model.no_oa_bank_batch_rows",
    )
    assert not any(forbidden in sql for sql in executed_sql for forbidden in forbidden_tables)


def test_bank_flow_rule_batch_delta_save_only_upserts_changed_batch_items() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_bank_flow_rule_batch_items(
        {
            "batches": {
                "changed-batch": {
                    "batch_id": "changed-batch",
                    "relation_case_id": "case-changed",
                    "status": "submitted",
                    "status_bucket": "submitted",
                    "version": 2,
                    "scope_month": "2026-03",
                    "account_key": "acct",
                    "row_ids": ["txn-1"],
                    "total_amount": "10.00",
                    "relation_mode": "bank_flow_rule_batch",
                },
                "unchanged-batch": {
                    "batch_id": "unchanged-batch",
                    "relation_case_id": "case-unchanged",
                    "status": "pending",
                    "status_bucket": "pending",
                    "version": 1,
                    "scope_month": "2026-03",
                    "account_key": "acct",
                    "row_ids": ["txn-2"],
                    "total_amount": "20.00",
                    "relation_mode": "bank_flow_rule_batch",
                },
            },
            "audit_log": [
                {"batch_id": "changed-batch", "operation": "submitted"},
                {"batch_id": "unchanged-batch", "operation": "created"},
            ],
        },
        batch_ids={"case-changed"},
    )

    executed_sql = write_sql(connection)
    assert not any("delete from read_model.bank_flow_rule_batch_rows" in sql for sql in executed_sql)
    assert not any("delete from app.bank_flow_rule_batches" in sql for sql in executed_sql)
    upsert_batch_params = [
        params
        for sql, params_seq in connection.executed_many_values
        if sql.startswith("insert into app.bank_flow_rule_batches(")
        for params in params_seq
    ]
    upsert_read_model_params = [
        params
        for sql, params_seq in connection.executed_many_values
        if sql.startswith("insert into read_model.bank_flow_rule_batch_rows(")
        for params in params_seq
    ]
    assert [params[0] for params in upsert_batch_params] == ["changed-batch"]
    assert [params[0] for params in upsert_read_model_params] == ["changed-batch"]
    assert [
        params
        for sql, params in connection.executed
        if sql == "delete from app.bank_flow_rule_batch_events where batch_id = %s"
    ] == [("changed-batch",)]
    assert not any(
        params[2] == "unchanged-batch"
        for sql, params in connection.executed
        if sql.startswith("insert into app.bank_flow_rule_batch_events(")
    )


def test_no_oa_bank_batch_save_does_not_touch_bank_flow_physical_tables() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_no_oa_bank_batches(
        {
            "batches": {
                "no-oa-batch": {
                    "batch_id": "no-oa-batch",
                    "status": "submitted",
                    "status_bucket": "submitted",
                    "version": 2,
                    "scope_month": "2026-03",
                    "account_key": "acct",
                    "row_ids": ["txn-1"],
                    "total_amount": "10.00",
                }
            },
            "audit_log": [{"batch_id": "no-oa-batch", "operation": "submitted"}],
        }
    )

    executed_sql = write_sql(connection)
    forbidden_tables = (
        "app.bank_flow_rule_batches",
        "app.bank_flow_rule_batch_events",
        "read_model.bank_flow_rule_batch_rows",
    )
    assert not any(forbidden in sql for sql in executed_sql for forbidden in forbidden_tables)


def test_bank_flow_rule_batch_read_model_queries_dedicated_table_without_relation_mode_predicate() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.list_bank_flow_rule_batch_rows(
        {
            "month": "2026-03",
            "bucket": "submitted",
            "batch_id": "bank-flow-batch",
            "relation_mode": "bank_flow_rule_batch",
        }
    )
    repository.bank_flow_rule_batch_source_versions_summary(
        {"month": "2026-03", "relation_mode": "bank_flow_rule_batch"}
    )

    read_sql = [*(sql for sql, _ in connection.fetched_all), *(sql for sql, _ in connection.fetched_one)]
    assert any("from read_model.bank_flow_rule_batch_rows" in sql for sql in read_sql)
    assert any("batch_id = %s" in sql for sql in read_sql)
    assert any("count(distinct source_versions)" in sql for sql in read_sql)
    assert not any("from read_model.no_oa_bank_batch_rows" in sql for sql in read_sql)
    assert not any("payload->>'relation_mode'" in sql for sql in read_sql)


def test_workbench_category_confirmation_uses_confirmation_fact_table() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_bank_transaction_categories(
        {
            "categories": {
                "txn-1": {
                    "category_code": "fee",
                    "source": "auto_confirmation",
                    "candidate_category_codes": ["fee", "salary"],
                    "rule_version": "bank-auto-tag-rules:2",
                    "version": 3,
                    "updated_by": "reviewer",
                }
            },
            "audit_log": [],
        }
    )

    executed_sql = [sql for sql, _ in connection.executed]
    assert any("update app.bank_transaction_category_confirmations" in sql for sql in executed_sql)
    assert any("insert into app.bank_transaction_category_confirmations" in sql for sql in executed_sql)
    assert all("insert into app.bank_transaction_categories" not in sql for sql in executed_sql)


def test_workbench_category_confirmation_revoke_updates_confirmation_fact_table() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRepository(connection)

    repository.save_bank_transaction_categories(
        {
            "categories": {
                "txn-1": {
                    "category_code": None,
                    "source": "auto_confirmation_revoked",
                    "version": 4,
                    "updated_by": "reviewer",
                }
            },
            "audit_log": [],
        }
    )

    executed_sql = [sql for sql, _ in connection.executed]
    assert any("update app.bank_transaction_category_confirmations" in sql for sql in executed_sql)
    assert all("insert into app.bank_transaction_categories" not in sql for sql in executed_sql)


def test_read_model_tax_save_uses_entry_count_column_and_transaction() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.save_tax_offset_read_models(
        {"read_models": {"2026-03": {"entries": [{"id": "row-1"}], "generated_at": "2026-03-02T00:00:00+00:00"}}}
    )

    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    assert len(connection.executed) == 1
    sql = connection.executed[0][0]
    assert "insert into read_model.tax_offset_read_models" in sql
    assert "entry_count" in sql
    assert "row_count" not in sql


def test_read_model_tax_save_counts_inner_tax_items_for_entry_count() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.save_tax_offset_read_models(
        {
            "read_models": {
                "2026-03": {
                    "payload": {
                        "output_items": [{"id": "output-1"}],
                        "input_plan_items": [{"id": "input-1"}],
                        "certified_items": [{"id": "certified-1"}],
                        "certified_matched_rows": [{"id": "certified-1", "matched_input_id": "input-1"}],
                        "certified_outside_plan_rows": [],
                    },
                    "generated_at": "2026-03-02T00:00:00+00:00",
                }
            }
        }
    )

    model_insert = next(
        params for sql, params in connection.executed if "insert into read_model.tax_offset_read_models" in sql
    )
    assert model_insert[3] == 3


def test_read_model_tax_save_rewrites_structured_amounts_from_item_payload() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.save_tax_offset_read_models(
        {
            "read_models": {
                "2026-03": {
                    "payload": {
                        "input_plan_items": [
                            {
                                "id": "input-1",
                                "issue_date": "2026-03-02",
                                "tax_amount": "159.66",
                                "total_with_tax": "2,820.72",
                            }
                        ]
                    },
                    "generated_at": "2026-03-02T00:00:00+00:00",
                }
            }
        }
    )

    item_insert = next(
        params for sql, params in connection.executed if "insert into read_model.tax_offset_items" in sql
    )
    assert item_insert[15] == "159.66"
    assert item_insert[16] == "2820.72"


def test_invoice_lifecycle_rows_are_saved_in_batch_and_scope_is_updated() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.save_invoice_lifecycle_rows(
        scope_key="2026-04",
        rows=[
            {
                "subject_id": "invoice-1",
                "subject_type": "input_invoice",
                "scope_month": "2026-04",
                "invoice_identity_key": "input:invoice-1",
                "lifecycle_status": "paid",
                "payment_status": {"code": "paid"},
            },
            {
                "subject_id": "bank-1",
                "subject_type": "bank_transaction",
                "scope_month": "2026-04",
                "lifecycle_status": "missing_invoice",
                "acquisition_status": {"code": "missing_invoice"},
            },
        ],
        source_versions={"invoice_lifecycle_read_model_schema_version": 1},
    )

    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    executed_sql = [sql for sql, _ in connection.executed]
    assert any("delete from read_model.invoice_lifecycle_rows" in sql for sql in executed_sql)
    assert len(connection.executed_many) == 1
    batch_sql, batch_params = connection.executed_many[0]
    assert "insert into read_model.invoice_lifecycle_rows" in batch_sql
    assert len(batch_params) == 2
    assert batch_params[0][1] == "invoice-1"
    assert batch_params[0][2] == "input_invoice"
    assert batch_params[1][1] == "bank-1"
    assert batch_params[1][2] == "bank_transaction"
    assert any("insert into read_model.invoice_lifecycle_scopes" in sql for sql in executed_sql)


def test_pending_invoice_rows_save_updates_scope_inside_transaction() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.save_pending_invoice_rows(
        scope_key="expense:all:2026-04",
        rows=[
            {
                "id": "pending-1",
                "bank_transaction": {
                    "trade_time": "2026-04-03",
                    "counterparty_name": "counterparty",
                    "amount": "12.34",
                },
                "status": {"code": "missing_invoice"},
                "invoices": [],
                "can_create_invoice": True,
            }
        ],
        source_versions={"pending_invoice_read_model_schema_version": 1},
    )

    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    executed_sql = [sql for sql, _ in connection.executed]
    assert any("delete from read_model.pending_invoice_rows" in sql for sql in executed_sql)
    assert any("insert into read_model.pending_invoice_rows" in sql for sql in executed_sql)
    assert any("insert into read_model.pending_invoice_scopes" in sql for sql in executed_sql)


def test_cost_statistics_rows_are_saved_in_batch() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.save_cost_statistics_read_models(
        {
            "read_models": {
                "active:2026-04": {
                    "scope_key": "active:2026-04",
                    "month": "2026-04",
                    "project_scope": "active",
                    "generated_at": "2026-04-02T00:00:00+00:00",
                    "source_versions": {"cost_statistics_read_model_schema_version": 1},
                    "payload": {
                        "month": "2026-04",
                        "project_scope": "active",
                        "time_rows": [
                            {
                                "row_key": "cost-row-1",
                                "transaction_id": "bank-1",
                                "trade_time": "2026-04-01T10:00:00+08:00",
                                "trade_date": "2026-04-01",
                                "project_name": "项目一",
                                "expense_type": "材料费",
                                "amount": "100.00",
                            },
                            {
                                "row_key": "cost-row-2",
                                "transaction_id": "bank-2",
                                "trade_time": "2026-04-02T10:00:00+08:00",
                                "trade_date": "2026-04-02",
                                "project_name": "项目二",
                                "expense_type": "服务费",
                                "amount": "200.00",
                            },
                        ],
                    },
                }
            }
        },
        changed_scope_keys={"active:2026-04"},
    )

    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    executed_sql = [sql for sql, _ in connection.executed]
    assert any("delete from read_model.cost_statistics_rows" in sql for sql in executed_sql)
    assert len(connection.executed_many) == 1
    batch_sql, batch_params = connection.executed_many[0]
    assert "insert into read_model.cost_statistics_rows" in batch_sql
    assert len(batch_params) == 2
    assert batch_params[0][3] == "cost-row-1"
    assert batch_params[0][4] == "bank-1"
    assert batch_params[1][3] == "cost-row-2"
    assert batch_params[1][4] == "bank-2"


def test_ops_tax_etc_multi_table_saves_use_transactions() -> None:
    connection = RecordingConnection()
    repository = PostgresOpsTaxEtcRepository(connection)

    repository.save_etc_reconciliation_state(
        {
            "tasks": {
                "task-1": {
                    "status": "draft",
                    "source_files": [{"file_id": "file-1", "source_kind": "etc"}],
                }
            }
        }
    )

    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    executed_sql = " ".join(sql for sql, _ in connection.executed)
    assert "insert into app.etc_reconciliation_tasks" in executed_sql
    assert "insert into app.etc_reconciliation_files" in executed_sql
    assert "update app.etc_reconciliation_files set status = 'deleted'" in executed_sql
    stale_file_update = next(
        (sql, params)
        for sql, params in connection.executed
        if "update app.etc_reconciliation_files" in sql
    )
    assert stale_file_update[1] == ("task-1", ["file-1"])


def test_ops_tax_etc_deleted_reconciliation_task_clears_formal_file_rows() -> None:
    connection = RecordingConnection()
    repository = PostgresOpsTaxEtcRepository(connection)

    repository.save_etc_reconciliation_state(
        {
            "tasks": {
                "task-1": {
                    "status": "deleted",
                    "source_files": [{"file_id": "file-1", "source_kind": "etc"}],
                }
            }
        }
    )

    executed_sql = " ".join(sql for sql, _ in connection.executed)
    assert "insert into app.etc_reconciliation_tasks" in executed_sql
    assert "delete from app.etc_reconciliation_files where task_id = %s" in executed_sql
    assert "insert into app.etc_reconciliation_files" not in executed_sql


def test_ops_tax_etc_attachment_cache_save_updates_source_lookup_rows() -> None:
    connection = RecordingConnection()
    repository = PostgresOpsTaxEtcRepository(connection)

    repository.save_oa_attachment_invoice_cache_entry(
        "cache-key-1",
        {
            "parser_version": "v1",
            "cache_schema_version": "s1",
            "invoices": [
                {
                    "source_attachment_key": "actual-attachment-key",
                    "source_expense_item_id": "item-1",
                    "source_attachment_name": "invoice.pdf",
                    "invoice_no": "INV-001",
                }
            ],
            "evidences": [],
            "artifacts": [],
        },
    )

    executed_sql = " ".join(sql for sql, _ in connection.executed)
    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    assert "insert into app.oa_attachment_invoice_cache" in executed_sql
    assert "delete from app.oa_attachment_invoice_cache_sources" in executed_sql
    assert "insert into app.oa_attachment_invoice_cache_sources" in executed_sql
    assert any(
        params[1] == "actual-attachment-key"
        for sql, params in connection.executed
        if "insert into app.oa_attachment_invoice_cache_sources" in sql
    )
    assert "attachment_identity_invoice" in executed_sql
    assert "from app.oa_attachments attachment" in executed_sql
    assert any(
        params == ("cache-key-1",) for sql, params in connection.executed if "attachment_identity_invoice" in sql
    )


def test_workbench_pair_history_load_preserves_original_mongo_array_order() -> None:
    repository = PostgresWorkbenchRelationRepository(WorkbenchReadConnection())

    snapshot = repository.load_workbench_pair_relations()

    assert [item["operation"] for item in snapshot["pair_relation_history"]] == ["earlier", "later"]


def test_workbench_relation_repository_save_writes_relation_history_and_refresh_scopes() -> None:
    connection = WorkbenchRelationWriteConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        {
            "pair_relations": {
                "case-1": {
                    "case_id": "case-1",
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "month_scope": "2026-05",
                    "row_ids": ["oa-1", "bank-1"],
                    "row_types": ["oa", "bank"],
                }
            },
            "pair_relation_history": [
                {
                    "case_id": "case-1",
                    "operation_type": "manual_confirmed",
                    "before_relations": [],
                    "after_relations": [{"case_id": "case-1"}],
                }
            ],
        },
        changed_case_ids={"case-1"},
    )

    executed_sql = " ".join(sql for sql, _params in connection.executed)
    fetch_all_sql = " ".join(sql for sql, _params in connection.fetched_all)
    refresh_rows = _workbench_relation_batch_refresh_rows(connection)
    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    assert "insert into app.workbench_pair_relations" in executed_sql
    assert "delete from app.workbench_pair_relation_history" in executed_sql
    assert "insert into app.workbench_pair_relation_history" in executed_sql
    assert "insert into job.read_model_dirty_scopes" in fetch_all_sql
    assert "insert into job.outbox_events" in fetch_all_sql
    assert any(row["scope_type"] == "workbench_relation" and row["scope_key"] == "2026-05" for row in refresh_rows)
    assert any(row["event_type"] == "workbench_relation.read_model.refresh" for row in refresh_rows)
    assert any(row["event_type"] == "cost_statistics.read_model.refresh" for row in refresh_rows)


def test_workbench_relation_transactional_refresh_scopes_match_scope_policy_contracts() -> None:
    connection = WorkbenchRelationWriteConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        {
            "pair_relations": {
                "case-1": {
                    "case_id": "case-1",
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "month_scope": "2026-05",
                    "row_ids": ["oa-1", "bank-1"],
                    "row_types": ["oa", "bank"],
                }
            },
            "pair_relation_history": [],
        },
        changed_case_ids={"case-1"},
    )

    refresh_rows = _workbench_relation_batch_refresh_rows(connection)
    dirty_scopes = [(row["scope_type"], row["scope_key"]) for row in refresh_rows]
    outbox_scopes = [(row["scope_type"], row["scope_key"]) for row in refresh_rows]

    assert dirty_scopes
    assert dirty_scopes == outbox_scopes
    for scope_type, scope_key in dirty_scopes:
        normalized = DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY.normalize_and_validate(scope_type, [scope_key])
        assert normalized == [scope_key]


def test_workbench_repository_delegates_pair_relation_load_to_relation_repository() -> None:
    repository = PostgresWorkbenchRepository(WorkbenchReadConnection())

    snapshot = repository.load_workbench_pair_relations()

    assert [item["operation"] for item in snapshot["pair_relation_history"]] == ["earlier", "later"]


def test_workbench_repository_no_longer_owns_pair_relation_sql() -> None:
    repository_source = (
        Path(__file__).resolve().parents[1] / "backend/src/fin_ops_platform/services/postgres_repositories/workbench.py"
    ).read_text(encoding="utf-8")
    forbidden_snippets = {
        "from app.workbench_pair_relations",
        "insert into app.workbench_pair_relations",
        "app.workbench_pair_relation_history",
        "_workbench_relation_dirty_scope_keys",
        "_enqueue_read_model_refresh_in_transaction",
    }

    assert {snippet for snippet in forbidden_snippets if snippet in repository_source} == set()


def test_read_model_loaders_strip_export_only_rebuildable_marker() -> None:
    repository = PostgresReadModelRepository(ReadModelReadConnection())

    assert "rebuildable" not in repository.load_workbench_read_models()["read_models"]["2026-05"]
    assert "rebuildable" not in repository.load_workbench_candidate_matches()["candidates"]["candidate-1"]
    assert "rebuildable" not in repository.load_cost_statistics_read_models()["read_models"]["2026-05"]
    assert "rebuildable" not in repository.load_tax_offset_read_models()["read_models"]["2026-05"]


def test_candidate_match_loader_drops_rebuildable_transform_cache_rows() -> None:
    repository = PostgresReadModelRepository(RebuildableCandidateReadConnection())

    assert repository.load_workbench_candidate_matches() == {}


def test_max_numeric_suffix_supports_dash_and_underscore_identifiers() -> None:
    assert max_numeric_suffix({"ETC-RECON-000026": {}, "file_000060": {}, "audit-event-7": {}}) == 60


def test_historical_etc_repair_loaders_strip_mongo_document_ids() -> None:
    repository = PostgresOpsTaxEtcRepository(HistoricalEtcReadConnection())

    assert "_id" not in repository.load_historical_etc_repair_parsed_seeds()["ETC-HIST-2026-01"]
    assert "_id" not in repository.load_historical_etc_repair_states()["ETC-HIST-2026-01"]


def test_etc_reconciliation_load_derives_counters_from_task_payload_and_strips_transform_id() -> None:
    repository = PostgresOpsTaxEtcRepository(EtcReconciliationReadConnection())

    snapshot = repository.load_etc_reconciliation_state()

    assert snapshot["task_counter"] == 26
    assert snapshot["file_counter"] == 60
    assert snapshot["audit_counter"] == 7
    assert "id" not in snapshot["tasks"]["ETC-RECON-000026"]


def test_etc_reconciliation_load_ignores_deleted_formal_files_without_reusing_ids() -> None:
    repository = PostgresOpsTaxEtcRepository(EtcReconciliationDeletedFileReadConnection())

    snapshot = repository.load_etc_reconciliation_state()

    assert snapshot["tasks"]["ETC-RECON-000026"]["source_files"] == [
        {
            "task_id": "ETC-RECON-000026",
            "file_id": "ETC-RECON-FILE-000061",
        }
    ]
    assert snapshot["file_counter"] == 62
