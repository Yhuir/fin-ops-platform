from __future__ import annotations

from pathlib import Path
from fin_ops_platform.services.postgres_repositories.bank_flow_rule_batch_canonical_query import (
    BankFlowRuleBatchCanonicalQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_repositories.common import max_numeric_suffix
from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresReadModelRepository,
    _execute_many,
)
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


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


class CostStatisticsPublishConnection(RecordingConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetched_one.append((" ".join(sql.split()), params))
        if "from job.read_model_dirty_scopes" in sql.lower():
            return {"source_version": 7}
        return None


class WorkbenchReadConnection:
    def __init__(self) -> None:
        self.fetched_all: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized_sql = " ".join(sql.split())
        self.fetched_all.append((normalized_sql, params))
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


def test_workbench_category_snapshot_writer_stays_removed() -> None:
    assert not hasattr(PostgresWorkbenchRepository, "load_bank_transaction_categories")
    assert not hasattr(PostgresWorkbenchRepository, "save_bank_transaction_categories")


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
        "insert into read_model.workbench_relation_rows(row_id, payload) values (%s, %s)",
        "insert into read_model.workbench_relation_groups(group_id, payload) values (%s, %s)",
        "insert into read_model.search_index_rows(row_id, payload) values (%s, %s)",
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


def test_workbench_relation_distribution_empty_scope_updates_scope_metadata() -> None:
    connection = RecordingConnection()
    repository = PostgresReadModelRepository(connection)

    repository.mark_workbench_relation_scope_empty(
        scope_key="2026-05",
        source_versions={"source_version": 11},
    )

    executed_sql = [sql for sql, _params in connection.executed]
    assert "delete from read_model.workbench_relation_rows where tenant_id = %s and scope_key = %s" in executed_sql
    assert "delete from read_model.workbench_relation_groups where tenant_id = %s and scope_key = %s" in executed_sql
    assert any("insert into read_model.workbench_relation_scopes" in sql for sql in executed_sql)


def test_workbench_relation_row_id_aliases_resolve_storage_and_legacy_ids() -> None:
    class AliasConnection(RecordingConnection):
        def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
            self.fetched_all.append((" ".join(sql.split()), params))
            return [
                {
                    "storage_id": "781cbe29-c790-4ad4-b6fb-7b4530813fa6",
                    "legacy_mongo_id": "txn_imported_0412",
                    "canonical_id": "txn_imported_0412",
                }
            ]

    connection = AliasConnection()
    repository = PostgresReadModelRepository(connection)

    result = repository.workbench_relation_row_id_aliases(
        ["781cbe29-c790-4ad4-b6fb-7b4530813fa6", "txn_imported_0412", "oa-1"],
    )

    assert result == {
        "781cbe29-c790-4ad4-b6fb-7b4530813fa6": "txn_imported_0412",
        "txn_imported_0412": "txn_imported_0412",
        "oa-1": "oa-1",
    }
    sql, params = connection.fetched_all[0]
    assert "from app.bank_transactions" in sql
    assert "from app.invoices" in sql
    normalized_ids = [
        "781cbe29-c790-4ad4-b6fb-7b4530813fa6",
        "txn_imported_0412",
        "oa-1",
    ]
    assert params == (normalized_ids, normalized_ids, normalized_ids, normalized_ids)


def test_workbench_relation_source_reads_can_exclude_turnover_closure_mode() -> None:
    class RelationSourceConnection(RecordingConnection):
        def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
            self.fetched_one.append((" ".join(sql.split()), params))
            return {"relation_count": 0, "relation_updated_at": ""}

        def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
            self.fetched_all.append((" ".join(sql.split()), params))
            return []

    connection = RelationSourceConnection()
    repository = PostgresReadModelRepository(connection)

    repository.workbench_relation_source_summary_from_source(
        scope_key="2026-05",
        row_ids=["txn-1"],
        include_row_ids=True,
        exclude_relation_modes=["turnover_manual_closure"],
    )
    repository.list_active_workbench_relation_source_rows(
        row_ids=["txn-1"],
        exclude_relation_modes=["turnover_manual_closure"],
    )

    summary_sql, summary_params = connection.fetched_one[0]
    rows_sql, rows_params = connection.fetched_all[0]
    assert "not (relation_mode = any(%s::text[]))" in summary_sql
    assert summary_params == (
        ["turnover_manual_closure"],
        "2026-05-01",
        ["txn-1"],
    )
    assert "not (relation_mode = any(%s::text[]))" in rows_sql
    assert rows_params == (["txn-1"], ["turnover_manual_closure"])


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
    assert [params[0] for params in upsert_batch_params] == ["changed-batch"]
    assert not any(
        "read_model.bank_flow_rule_batch_rows" in sql
        for sql in executed_sql
    )
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


def test_bank_flow_rule_batch_query_reads_canonical_tables_without_page_projection() -> None:
    connection = RecordingConnection()
    repository = BankFlowRuleBatchCanonicalQueryRepository(connection)

    repository.read_page(
        {"month": "2026-03", "bucket": "submitted"},
        summary_filters={"month": "2026-03"},
        page=2,
        page_size=50,
    )

    read_sql = [*(sql for sql, _ in connection.fetched_all), *(sql for sql, _ in connection.fetched_one)]
    assert any("from app.bank_flow_rule_batches batch" in sql for sql in read_sql)
    assert any("from app.workbench_pair_relations relation" in sql for sql in read_sql)
    assert not any("limit %s offset %s" in sql for sql in read_sql)
    assert not any("read_model.bank_flow_rule_batch_rows" in sql for sql in read_sql)
    assert not any("from read_model.no_oa_bank_batch_rows" in sql for sql in read_sql)


def test_bank_flow_rule_batch_affected_scope_lookup_is_one_set_based_query() -> None:
    connection = RecordingConnection()
    connection.fetch_all = lambda sql, params=(): (  # type: ignore[method-assign]
        connection.fetched_all.append((" ".join(sql.split()), params))
        or [{"scope_key": "2026-05"}, {"scope_key": "2026-07"}]
    )
    repository = BankFlowRuleBatchCanonicalQueryRepository(connection)

    scopes = repository.affected_scope_keys_for_tag_codes(["fee", "fee", "salary"])

    assert scopes == ["2026-05", "2026-07"]
    assert len(connection.fetched_all) == 1
    sql, params = connection.fetched_all[0]
    assert "from app.bank_transactions bank" in sql
    assert "from app.bank_flow_rule_batches batch" not in sql
    assert "in ('draft', 'unsubmitted')" not in sql
    assert params == (["fee", "salary"],)


def test_bank_flow_rule_settings_version_check_locks_and_saves_in_caller_transaction() -> None:
    connection = RecordingConnection()
    current_settings = {
        "allowed_usernames": ["concurrent-user"],
        "bank_flow_rule_batch_tag_rules": {"version": 1},
    }
    connection.fetch_one = lambda sql, params=(): (  # type: ignore[method-assign]
        connection.fetched_one.append((" ".join(sql.split()), params))
        or {"settings_payload": current_settings}
    )
    repository = PostgresOpsTaxEtcRepository(connection)
    transaction = connection.transaction()

    saved = repository.save_app_settings_for_bank_flow_rule_version_in_transaction(
        {"bank_flow_rule_batch_tag_rules": {"version": 2}},
        expected_version=1,
        transaction=transaction,
    )
    conflict = repository.save_app_settings_for_bank_flow_rule_version_in_transaction(
        {"bank_flow_rule_batch_tag_rules": {"version": 8}},
        expected_version=7,
        transaction=transaction,
    )

    assert saved == {
        "allowed_usernames": ["concurrent-user"],
        "bank_flow_rule_batch_tag_rules": {"version": 2},
    }
    assert conflict is None
    assert len(connection.fetched_one) == 2
    assert all("for update" in sql for sql, _params in connection.fetched_one)
    assert len(connection.executed) == 1
    assert "insert into app.app_settings" in connection.executed[0][0]
    persisted_payload = connection.executed[0][1][1].obj
    assert persisted_payload["allowed_usernames"] == ["concurrent-user"]












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


def test_ops_tax_etc_oa_draft_save_locks_and_compares_the_target_version() -> None:
    class VersionedConnection(RecordingConnection):
        def __init__(self, version: int) -> None:
            super().__init__()
            self.version = version

        def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
            self.fetched_one.append((" ".join(sql.split()), params))
            if "from app.etc_business_batches" in sql:
                return {"version": self.version}
            return None

    snapshot = {
        "business_batches": {
            "batch-1": {
                "business_batch_id": "batch-1",
                "task_id": "task-1",
                "status": "oa_confirmation_pending",
                "version": 8,
            }
        }
    }
    matching = VersionedConnection(version=7)
    stale = VersionedConnection(version=8)

    saved = PostgresOpsTaxEtcRepository(matching).save_etc_oa_draft_attempt(
        snapshot,
        business_batch_id="batch-1",
        expected_version=7,
    )
    rejected = PostgresOpsTaxEtcRepository(stale).save_etc_oa_draft_attempt(
        snapshot,
        business_batch_id="batch-1",
        expected_version=7,
    )

    assert saved is True
    assert rejected is False
    assert any("for update" in sql for sql, _params in matching.fetched_one)
    assert any("insert into app.etc_business_batches" in sql for sql, _params in matching.executed)
    assert stale.executed == []


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


def test_workbench_active_relation_case_load_is_one_history_free_query() -> None:
    connection = WorkbenchReadConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    relation = repository.load_active_workbench_pair_relation_by_case_id("case-1")

    assert relation == {"case_id": "case-1", "row_ids": ["row-1"]}
    assert len(connection.fetched_all) == 1
    sql, params = connection.fetched_all[0]
    assert "from app.workbench_pair_relations" in sql
    assert "status = 'active'" in sql
    assert "workbench_pair_relation_history" not in sql
    assert params == ("case-1",)


def test_workbench_active_relation_overlap_load_is_one_history_free_query() -> None:
    connection = WorkbenchReadConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    snapshot = repository.load_active_workbench_pair_relations_for_row_ids(
        ["row-1"],
        case_ids=["case-1"],
    )

    assert sorted(snapshot["pair_relations"]) == ["case-1"]
    assert len(connection.fetched_all) == 1
    sql, params = connection.fetched_all[0]
    assert "from app.workbench_pair_relations" in sql
    assert "status = 'active'" in sql
    assert "workbench_pair_relation_history" not in sql
    assert params == (["row-1"], ["case-1"])


def test_workbench_relation_repository_save_writes_only_relation_facts_and_history() -> None:
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
    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    assert "insert into app.workbench_pair_relations" in executed_sql
    assert "delete from app.workbench_pair_relation_history" in executed_sql
    assert "insert into app.workbench_pair_relation_history" in executed_sql
    assert "job.read_model_dirty_scopes" not in fetch_all_sql
    assert "job.outbox_events" not in fetch_all_sql


def test_workbench_relation_repository_replaces_long_case_history_with_two_statements() -> None:
    connection = WorkbenchRelationWriteConnection()
    repository = PostgresWorkbenchRelationRepository(connection)
    histories = [
        {
            "case_id": "case-1",
            "operation_type": f"operation-{index}",
            "before_relations": [],
            "after_relations": [{"case_id": "case-1"}],
        }
        for index in range(25)
    ]

    repository.save_workbench_pair_relations(
        {
            "pair_relations": {
                "case-1": {
                    "case_id": "case-1",
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "month_scope": "2026-05",
                    "row_ids": ["bank-1"],
                    "row_types": ["bank"],
                }
            },
            "pair_relation_history": histories,
        },
        changed_case_ids={"case-1"},
    )

    history_statements = [
        (sql, params)
        for sql, params in connection.executed
        if "app.workbench_pair_relation_history" in sql
    ]
    assert len(history_statements) == 2
    assert "delete from app.workbench_pair_relation_history" in history_statements[0][0]
    assert "with input(" in history_statements[1][0]
    assert len(history_statements[1][1]) == len(histories) * 8


def test_workbench_relation_repository_deduplicates_reloaded_multi_case_history() -> None:
    connection = WorkbenchRelationWriteConnection()
    repository = PostgresWorkbenchRelationRepository(connection)
    shared_history = {
        "operation_id": "shared-operation",
        "operation_type": "replace_link",
        "before_relations": [{"case_id": "case-1"}],
        "after_relations": [{"case_id": "case-2"}],
    }

    repository.save_workbench_pair_relations(
        {
            "pair_relations": {
                "case-1": {
                    "case_id": "case-1",
                    "relation_mode": "manual_confirmed",
                    "status": "cancelled",
                    "month_scope": "2026-05",
                    "row_ids": ["bank-1"],
                    "row_types": ["bank"],
                },
                "case-2": {
                    "case_id": "case-2",
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "month_scope": "2026-05",
                    "row_ids": ["bank-1", "oa-1"],
                    "row_types": ["bank", "oa"],
                },
            },
            # PostgreSQL stores a cross-case event once per case; loading the
            # raw payload therefore legitimately reconstructs both copies.
            "pair_relation_history": [dict(shared_history), dict(shared_history)],
        },
        changed_case_ids={"case-1", "case-2"},
    )

    history_statements = [
        (sql, params)
        for sql, params in connection.executed
        if "app.workbench_pair_relation_history" in sql
    ]
    assert len(history_statements) == 2
    assert "with input(" in history_statements[1][0]
    assert len(history_statements[1][1]) == 2 * 8


def test_workbench_relation_delta_appends_one_history_event_without_delete() -> None:
    connection = WorkbenchRelationWriteConnection()
    repository = PostgresWorkbenchRelationRepository(connection)
    history = {
        "case_id": "case-1",
        "operation_id": "new-operation",
        "operation_type": "manual_confirmed",
        "before_relations": [],
        "after_relations": [{"case_id": "case-1"}],
    }

    repository.save_workbench_pair_relation_delta(
        {
            "pair_relations": {
                "case-1": {
                    "case_id": "case-1",
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "month_scope": "2026-05",
                    "row_ids": ["bank-1"],
                    "row_types": ["bank"],
                }
            },
            "pair_relation_history": [history],
        },
        changed_case_ids={"case-1"},
    )

    history_statements = [
        (sql, params)
        for sql, params in connection.executed
        if "app.workbench_pair_relation_history" in sql
    ]
    assert len(history_statements) == 1
    assert "delete from app.workbench_pair_relation_history" not in history_statements[0][0]
    assert "with input(" in history_statements[0][0]
    assert len(history_statements[0][1]) == 8


def test_workbench_relation_transaction_does_not_write_page_refresh_scopes() -> None:
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

    all_sql = " ".join(
        sql
        for calls in (connection.executed, connection.fetched_one, connection.fetched_all)
        for sql, _params in calls
    )
    assert "job.read_model_dirty_scopes" not in all_sql
    assert "job.outbox_events" not in all_sql


def test_workbench_repository_delegates_pair_relation_load_to_relation_repository() -> None:
    repository = PostgresWorkbenchRepository(WorkbenchReadConnection())

    snapshot = repository.load_workbench_pair_relations()

    assert [item["operation"] for item in snapshot["pair_relation_history"]] == ["earlier", "later"]


def test_workbench_repository_uses_pair_relations_only_for_canonical_bank_flow_proof() -> None:
    repository_source = (
        Path(__file__).resolve().parents[1] / "backend/src/fin_ops_platform/services/postgres_repositories/workbench.py"
    ).read_text(encoding="utf-8")
    forbidden_snippets = {
        "insert into app.workbench_pair_relations",
        "app.workbench_pair_relation_history",
        "_workbench_relation_dirty_scope_keys",
        "_enqueue_read_model_refresh_in_transaction",
    }

    assert {snippet for snippet in forbidden_snippets if snippet in repository_source} == set()
    assert "from app.workbench_pair_relations relation" not in repository_source


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
