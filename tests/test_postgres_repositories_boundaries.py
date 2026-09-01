from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from fin_ops_platform.services.postgres_repositories.bank_flow_rule_batch_canonical_query import (
    BankFlowRuleBatchCanonicalQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.bank_relation_requirement_recalculation import (
    PostgresBankRelationRequirementRecalculationRequestRepository,
)
from fin_ops_platform.services.postgres_repositories.common import max_numeric_suffix
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.state_store_protocol import (
    SettingsAccessControlCommitOutcomeUnknown,
    SettingsAccessControlVersionConflict,
)


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


def test_requirement_recalculation_request_commits_settings_job_and_event_in_one_transaction() -> None:
    connection = RecordingConnection()
    settings_calls: list[dict[str, object]] = []
    queue_calls: list[dict[str, object]] = []
    state_store = type(
        "StateStore",
        (),
        {
            "save_app_settings_for_bank_flow_rule_version_in_transaction": (
                lambda _self, payload, *, expected_version, transaction: (
                    settings_calls.append(
                        {
                            "payload": payload,
                            "expected_version": expected_version,
                            "transaction": transaction,
                        }
                    )
                    or payload
                )
            )
        },
    )()
    queue = type(
        "Queue",
        (),
        {
            "enqueue_in_transaction": (
                lambda _self, **kwargs: queue_calls.append(dict(kwargs))
            )
        },
    )()
    repository = PostgresBankRelationRequirementRecalculationRequestRepository(
        connection,
        queue,
        state_store,
    )
    next_snapshot = {"bank_flow_rule_batch_tag_rules": {"version": 12}}

    saved = repository.commit(
        next_snapshot=next_snapshot,
        expected_version=11,
        job_payload={
            "job_id": "job-12",
            "type": "bank_relation_requirement_recalculation",
            "owner_user_id": "finance-user",
            "source": {},
            "result_summary": {},
        },
        changed_tag_codes=["sales_income"],
    )

    assert saved == next_snapshot
    assert connection.transaction_enters == 1
    assert connection.transaction_exits == 1
    assert settings_calls[0]["transaction"].parent is connection
    assert any("insert into job.background_jobs" in sql.lower() for sql, _ in connection.executed)
    assert queue_calls[0]["transaction"].parent is connection
    assert queue_calls[0]["payload"]["changed_tag_codes"] == ["sales_income"]


def test_requirement_recalculation_request_does_not_enqueue_when_settings_cas_fails() -> None:
    connection = RecordingConnection()
    queue_calls: list[dict[str, object]] = []
    state_store = type(
        "StateStore",
        (),
        {
            "save_app_settings_for_bank_flow_rule_version_in_transaction": (
                lambda _self, _payload, *, expected_version, transaction: None
            )
        },
    )()
    queue = type(
        "Queue",
        (),
        {
            "enqueue_in_transaction": (
                lambda _self, **kwargs: queue_calls.append(dict(kwargs))
            )
        },
    )()
    repository = PostgresBankRelationRequirementRecalculationRequestRepository(
        connection,
        queue,
        state_store,
    )

    saved = repository.commit(
        next_snapshot={"bank_flow_rule_batch_tag_rules": {"version": 12}},
        expected_version=11,
        job_payload={"job_id": "job-12", "owner_user_id": "finance-user"},
        changed_tag_codes=["sales_income"],
    )

    assert saved is None
    assert queue_calls == []
    assert not any("insert into job.background_jobs" in sql.lower() for sql, _ in connection.executed)


class RawSettingsCursor:
    def __init__(self, connection: "RawSettingsConnection") -> None:
        self.connection = connection
        self.rowcount = 0
        self.row: dict | None = None

    def __enter__(self) -> "RawSettingsCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        normalized = " ".join(sql.lower().split())
        self.connection.statements.append((normalized, params))
        self.row = None
        self.rowcount = 1
        if "select settings_payload from app.app_settings" in normalized:
            self.row = {"settings_payload": dict(self.connection.settings)}
        elif "insert into app.app_settings" in normalized:
            self.connection.settings = dict(params[1].obj)
        elif "insert into audit.events" in normalized:
            audit_payload = dict(params[7].obj)
            self.connection.audits.append(audit_payload)
        elif "from audit.events" in normalized:
            expected = dict(params[0].obj)
            if any(all(audit.get(key) == value for key, value in expected.items()) for audit in self.connection.audits):
                self.row = {"audit_present": 1}

    def fetchone(self) -> dict | None:
        return self.row


class RawSettingsConnection:
    def __init__(self, settings: dict) -> None:
        self.settings = dict(settings)
        self.audits: list[dict] = []
        self.statements: list[tuple[str, tuple]] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_commit_number: int | None = None

    @contextmanager
    def connection(self):
        yield self

    def cursor(self) -> RawSettingsCursor:
        return RawSettingsCursor(self)

    def commit(self) -> None:
        self.commit_count += 1
        if self.fail_commit_number == self.commit_count:
            raise ConnectionError("commit acknowledgement lost")

    def rollback(self) -> None:
        self.rollback_count += 1


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
        normalized_sql = " ".join(sql.split())
        self.fetch_one_calls.append((normalized_sql, params))
        if "insert into job.outbox_events" in normalized_sql:
            return {
                "event_id": "event-1",
                "tenant_id": params[0],
                "event_type": params[1],
                "aggregate_type": params[2],
                "aggregate_id": params[3],
                "scope_type": params[4],
                "scope_key": params[5],
                "dedupe_key": params[6],
                "payload": {},
                "attempts": 0,
                "status": "pending",
                "schema_version": 1,
                "source_version": params[9],
                "priority": params[10],
                "trace_id": params[11],
            }
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


class EtcReconciliationImportSummaryReadConnection:
    def __init__(self) -> None:
        self.sql = ""

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.sql = " ".join(sql.split())
        assert params == ()
        return [
            {
                "task_id": "ETC-RECON-000026",
                "status": "ready_for_import",
                "version": 7,
                "title": "2026-08 ETC",
                "period_start": "2026-08-01",
                "period_end": "2026-08-31",
                "oa_total_amount": "108.40",
                "etc_invoice_count": "8",
                "supplement_count": "1",
                "vehicle_plates": ["云ADA0381"],
                "updated_at": "2026-08-31T10:00:00+00:00",
            }
        ]


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

    assert removed_events_delete_index < removed_batches_delete_index
    assert not any("read_model.no_oa_bank_batch_rows" in sql for sql in executed_sql)
    assert connection.executed[removed_events_delete_index][1] == ("no_oa_bank_batch", ["retained-batch"])
    assert connection.executed[removed_batches_delete_index][1] == ("no_oa_bank_batch", ["retained-batch"])


def test_no_oa_bank_batch_save_bulk_upserts_only_canonical_app_rows() -> None:
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
    assert [len(params_seq) for params_seq in app_upserts] == [2]
    assert not any(sql.startswith("insert into app.no_oa_bank_batches(") for sql, _params in connection.executed)
    assert not any(
        "read_model.no_oa_bank_batch_rows" in sql
        for sql, _params in [*connection.executed, *connection.executed_many_values]
    )


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


def test_bank_flow_rule_settings_version_check_locks_and_saves_in_caller_transaction() -> None:
    connection = RecordingConnection()
    current_settings = {
        "page_access_accounts": [{"username": "concurrent-user", "page_keys": ["bank-flow-rule-batches"]}],
        "access_control_version": 3,
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
        "page_access_accounts": [{"username": "concurrent-user", "page_keys": ["bank-flow-rule-batches"]}],
        "access_control_version": 3,
        "bank_flow_rule_batch_tag_rules": {"version": 2},
    }
    assert conflict is None
    assert len(connection.fetched_one) == 2
    assert all("for update" in sql for sql, _params in connection.fetched_one)
    writes = [(sql, params) for sql, params in connection.executed if "insert into app.app_settings" in sql]
    assert len(writes) == 1
    persisted_payload = writes[0][1][1].obj
    assert persisted_payload["page_access_accounts"] == [
        {"username": "concurrent-user", "page_keys": ["bank-flow-rule-batches"]}
    ]


def test_settings_generic_writer_preserves_acl_under_shared_session_lock() -> None:
    connection = RawSettingsConnection(
        {
            "page_access_accounts": [{"username": "existing", "page_keys": ["settings"]}],
            "access_control_version": 4,
            "workbench_column_layouts": {},
        }
    )
    repository = PostgresOpsTaxEtcRepository(connection)

    repository.save_settings(
        "app_settings",
        {
            "page_access_accounts": [{"username": "attacker", "page_keys": ["settings"]}],
            "access_control_version": 99,
            "workbench_column_layouts": {"invoice": ["amount"]},
        },
    )

    assert connection.settings["page_access_accounts"] == [{"username": "existing", "page_keys": ["settings"]}]
    assert connection.settings["access_control_version"] == 4
    assert connection.settings["workbench_column_layouts"] == {"invoice": ["amount"]}
    sql = [statement for statement, _params in connection.statements]
    assert any("pg_advisory_lock" in statement for statement in sql)
    assert any("for update" in statement for statement in sql)
    assert any("pg_advisory_unlock" in statement for statement in sql)


def test_settings_acl_guard_commits_cas_and_audit_then_recovers_by_mutation_id() -> None:
    connection = RawSettingsConnection(
        {
            "page_access_accounts": [],
            "access_control_version": 1,
        }
    )
    repository = PostgresOpsTaxEtcRepository(connection)

    with repository.begin_settings_acl_critical_section(1) as critical_section:
        committed = critical_section.commit(
            {
                "page_access_accounts": [{"username": "user-a", "page_keys": ["settings"]}],
            },
            {"mutation_id": "mutation-1", "actor_id": "YNSYLP005", "request_id": "request-1"},
        )

    assert committed["access_control_version"] == 2
    assert connection.settings["page_access_accounts"] == [{"username": "user-a", "page_keys": ["settings"]}]
    assert connection.audits[0]["mutation_id"] == "mutation-1"
    assert repository.recover_settings_acl_commit("mutation-1") == {
        "access_control": committed,
        "audit_present": True,
    }
    with pytest.raises(SettingsAccessControlVersionConflict):
        with repository.begin_settings_acl_critical_section(1):
            pass


def test_settings_acl_guard_marks_commit_ack_loss_as_unknown() -> None:
    connection = RawSettingsConnection(
        {
            "page_access_accounts": [],
            "access_control_version": 1,
        }
    )
    repository = PostgresOpsTaxEtcRepository(connection)
    connection.fail_commit_number = 2

    with pytest.raises(SettingsAccessControlCommitOutcomeUnknown):
        with repository.begin_settings_acl_critical_section(1) as critical_section:
            critical_section.commit(
                {
                    "page_access_accounts": [],
                },
                {"mutation_id": "mutation-unknown", "actor_id": "YNSYLP005"},
            )












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


def test_etc_state_persists_business_batch_member_invoice_summary() -> None:
    connection = RecordingConnection()
    repository = PostgresOpsTaxEtcRepository(connection)

    repository.save_etc_state(
        {
            "invoices": {
                "ETC001": {"invoice_number": "ETC001", "total_amount": "13.07"},
                "ETC002": {"invoice_number": "ETC002", "total_amount": "14.07"},
            },
            "batches": {
                "etc_20260520_001": {
                    "status": "submitted_confirmed",
                    "issue_start_date": "2026-05-20",
                    "invoice_ids": ["ETC001", "ETC002"],
                    "oa_total_amount": "1673.30",
                    "total_amount": "1673.30",
                    "etc_invoice_amount": "27.14",
                    "etc_invoice_count": 37,
                }
            },
            "business_batches": {
                "etc_business_batch_0004": {
                    "status": "manually_marked_submitted",
                    "submission_batch_id": "etc_20260520_001",
                    "invoice_ids": ["ETC001", "ETC002"],
                    "created_at": "2026-05-20T09:00:00+08:00",
                }
            },
        }
    )

    business_batch_writes = [
        params
        for sql, params in connection.executed
        if "insert into app.etc_business_batches" in sql
    ]
    assert len(business_batch_writes) == 1
    params = business_batch_writes[0]
    assert params[4] == "2026-05-01"
    assert params[5] == 2
    assert params[6] == "27.14"


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
    assert "('attachment_identity_' || source.source_kind)" in executed_sql
    assert "from app.oa_attachments attachment" in executed_sql
    assert "join app.oa_application_items item" in executed_sql
    assert "target_attachment_sources as" in executed_sql
    assert "app.row_id = any(scope.oa_row_ids)" in executed_sql
    assert "oa_affected_cache_keys as" in executed_sql
    assert "affected_cache_keys as" in executed_sql
    assert "join affected_cache_keys affected" in executed_sql
    assert "unique_identity_owners as" in executed_sql
    assert "cache.parsed_source_attachment_key = attachment.source_attachment_key" in executed_sql
    assert "from attachment_sources exact_attachment" in executed_sql
    assert "having count(distinct (" in executed_sql
    assert "oa_application_id," in executed_sql
    assert "source_attachment_key," in executed_sql
    assert "source_expense_item_id" in executed_sql
    assert "app.status <> 'deleted'" in executed_sql
    assert "discarded_invalid_identity_sources as" in executed_sql
    assert "existing.source_kind like 'attachment_identity_%%'" in executed_sql
    assert "existing.cache_source_attachment_key = affected.cache_source_attachment_key" in executed_sql
    assert any(
        params == (False, [], True, ["cache-key-1"])
        for sql, params in connection.executed
        if "cache_evidence_sources as" in sql
    )
    assert "source.source_kind in ('invoice', 'evidence', 'artifact')" in executed_sql
    assert "is distinct from" in executed_sql


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


def test_requirement_recalculation_query_selects_formal_relation_modes_regardless_of_case_id() -> None:
    connection = WorkbenchReadConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.load_active_bank_requirement_relations_for_tag_codes(["sales_income"])

    assert len(connection.fetched_all) == 1
    sql, params = connection.fetched_all[0]
    assert "relation.relation_mode = any(%s::text[])" in sql
    assert "case_id !~" not in sql
    assert "paired_requirement_source" in sql
    assert "canonical_bank_months" in sql
    assert "from app.bank_transactions bank" in sql
    assert "bank.txn_month is not null" in sql
    assert "manual_confirmed" in params[0]
    assert "bank_flow_rule_batch" in params[0]
    assert params[1:] == (["sales_income"], ["sales_income"])


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
    assert "delete from app.workbench_pair_relation_history" not in executed_sql
    assert "insert into app.workbench_pair_relation_history" in executed_sql
    assert "on conflict (id) do nothing" in executed_sql
    assert "job.read_model_dirty_scopes" not in fetch_all_sql
    assert "job.outbox_events" not in fetch_all_sql


def test_workbench_relation_repository_appends_long_case_history_in_one_statement() -> None:
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
    assert len(history_statements) == 1
    assert "delete from app.workbench_pair_relation_history" not in history_statements[0][0]
    assert "with input(" in history_statements[0][0]
    assert "on conflict (id) do nothing" in history_statements[0][0]
    assert len(history_statements[0][1]) == len(histories) * 9


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
    assert len(history_statements) == 1
    assert "with input(" in history_statements[0][0]
    assert len(history_statements[0][1]) == 2 * 9


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
    assert len(history_statements[0][1]) == 9


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


def test_etc_reconciliation_import_summary_read_avoids_full_task_and_file_payloads() -> None:
    connection = EtcReconciliationImportSummaryReadConnection()
    repository = PostgresOpsTaxEtcRepository(connection)

    summaries = repository.list_etc_reconciliation_import_task_summaries()

    assert summaries == [
        {
            "task_id": "ETC-RECON-000026",
            "status": "ready_for_import",
            "version": 7,
            "title": "2026-08 ETC",
            "period_start": "2026-08-01",
            "period_end": "2026-08-31",
            "oa_total_amount": "108.40",
            "etc_invoice_count": 8,
            "supplement_count": 1,
            "vehicle_plates": ["云ADA0381"],
            "updated_at": "2026-08-31T10:00:00+00:00",
        }
    ]
    assert "from app.etc_reconciliation_tasks" in connection.sql
    assert "from app.etc_reconciliation_files" not in connection.sql
    assert "select task_id, status, version" in connection.sql
