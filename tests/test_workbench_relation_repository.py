from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


class RecordingConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fetch_one_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return []

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, object]:
        self.fetch_one_calls.append((sql, params))
        return {}

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        self.execute_calls.append((sql, params))
        return 1


def _snapshot(*, case_ids: tuple[str, ...] = ("CASE-1",)) -> dict[str, object]:
    relations = {
        case_id: {
            "case_id": case_id,
            "relation_mode": "manual_confirmed",
            "status": "active",
            "version": 1,
            "month_scope": "2026-05",
            "row_ids": [f"bank-{index}", f"invoice-{index}"],
            "row_types": ["bank", "invoice"],
        }
        for index, case_id in enumerate(case_ids, start=1)
    }
    return {
        "pair_relations": relations,
        "pair_relation_history": [
            {
                "case_id": case_id,
                "operation_type": "confirm_link",
                "before_relations": [],
                "after_relations": [{"case_id": case_id}],
            }
            for case_id in case_ids
        ],
    }


def _normalized_sql(calls: list[tuple[str, tuple[Any, ...]]]) -> list[str]:
    return [" ".join(sql.lower().split()) for sql, _params in calls]


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
            return []

    connection = ScopedLoadConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    snapshot = repository.load_workbench_pair_relations_for_row_ids(["bank-1"], case_ids=["CASE-1"])

    assert sorted(snapshot["pair_relations"]) == ["CASE-1"]
    assert snapshot["pair_relation_history"][0]["operation_type"] == "confirm_link"
    assert len(connection.fetch_all_calls) == 2


def test_relation_save_persists_only_canonical_facts_and_history() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(_snapshot(), changed_case_ids={"CASE-1"})

    execute_sql = _normalized_sql(connection.execute_calls)
    assert any("insert into app.workbench_pair_relations" in sql for sql in execute_sql)
    assert not any("delete from app.workbench_pair_relation_history" in sql for sql in execute_sql)
    assert any("insert into app.workbench_pair_relation_history" in sql for sql in execute_sql)
    assert any("on conflict (id) do nothing" in sql for sql in execute_sql)
    assert not connection.fetch_one_calls
    assert not connection.fetch_all_calls
    assert not any("job.read_model_dirty_scopes" in sql or "job.outbox_events" in sql for sql in execute_sql)


def test_relation_save_filters_to_changed_case_ids_without_page_fan_out() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(case_ids=("CASE-1", "CASE-2")),
        changed_case_ids={"CASE-2"},
    )

    relation_params = [
        params
        for sql, params in connection.execute_calls
        if "insert into app.workbench_pair_relations" in " ".join(sql.lower().split())
    ]
    assert len(relation_params) == 1
    assert relation_params[0][0] == "CASE-2"
    assert not connection.fetch_one_calls
    assert not connection.fetch_all_calls


def test_relation_delta_save_has_the_same_canonical_only_io_boundary() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relation_delta(_snapshot(), changed_case_ids={"CASE-1"})

    all_sql = _normalized_sql(connection.execute_calls + connection.fetch_one_calls + connection.fetch_all_calls)
    assert any("insert into app.workbench_pair_relations" in sql for sql in all_sql)
    assert not any("job.read_model_dirty_scopes" in sql or "job.outbox_events" in sql for sql in all_sql)


def test_relation_repository_registers_runtime_publication_with_uow_callback() -> None:
    callbacks: list[object] = []
    repository = PostgresWorkbenchRelationRepository(RecordingConnection())
    repository.bind_post_commit_callback_registrar(callbacks.append)

    published: list[str] = []
    registered = repository.register_post_commit_callback(lambda: published.append("runtime"))

    assert registered is True
    assert published == []
    assert len(callbacks) == 1
    callback = callbacks[0]
    assert callable(callback)
    callback()
    assert published == ["runtime"]


def test_requirement_relation_load_attaches_canonical_bank_months_in_one_query() -> None:
    class RequirementLoadConnection(RecordingConnection):
        def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
            self.fetch_all_calls.append((sql, params))
            return [
                {
                    "raw_payload": {
                        "case_id": "CASE-LEGACY",
                        "row_ids": ["bank-1", "invoice-1"],
                        "row_types": ["bank", "invoice"],
                        "status": "active",
                    },
                    "canonical_bank_months": ["2026-05", "2026-07", "2026-05"],
                }
            ]

    connection = RequirementLoadConnection()
    relations = PostgresWorkbenchRelationRepository(
        connection
    ).load_active_bank_requirement_relations_for_tag_codes(["sales_income"])

    assert relations == [
        {
            "case_id": "CASE-LEGACY",
            "row_ids": ["bank-1", "invoice-1"],
            "row_types": ["bank", "invoice"],
            "status": "active",
            "_canonical_bank_months": ["2026-05", "2026-07"],
        }
    ]
    assert len(connection.fetch_all_calls) == 1


def test_canonical_relation_member_lock_reports_deleted_member_and_locks_existing_rows() -> None:
    class CanonicalLockConnection(RecordingConnection):
        def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
            self.fetch_all_calls.append((sql, params))
            normalized_sql = " ".join(sql.lower().split())
            assert "for key share" in normalized_sql
            if "from app.oa_applications" in normalized_sql:
                assert "from app.oa_pending_payment_admissions" in normalized_sql
                assert params == (
                    ["oa-deleted", "oa-present"],
                    "tenant-a",
                    ["oa-deleted", "oa-present"],
                )
                return [{"row_id": "oa-present", "source_count": 1}]
            if "from app.bank_transactions" in normalized_sql:
                return [{"row_id": "bank-present"}]
            if "from app.invoices" in normalized_sql:
                return [{"row_id": "invoice-present"}]
            return []

    connection = CanonicalLockConnection()
    missing = PostgresWorkbenchRelationRepository(connection).lock_canonical_relation_members(
        ["oa-present", "oa-deleted", "bank-present", "invoice-present"],
        row_types=["oa", "oa", "bank", "invoice"],
        tenant_id="tenant-a",
    )

    assert missing == ["oa:oa-deleted"]
    assert len(connection.fetch_all_calls) == 3


def test_canonical_relation_member_lock_accepts_submitted_etc_summary_member() -> None:
    class EtcSummaryLockConnection(RecordingConnection):
        def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
            self.fetch_all_calls.append((sql, params))
            normalized_sql = " ".join(sql.lower().split())
            if "from app.invoices" in normalized_sql:
                return []
            if "from app.etc_business_batches" in normalized_sql:
                assert "for key share of batch" in normalized_sql
                assert "from app.etc_invoices invoice" in normalized_sql
                assert params == (["etc-summary-etc_20260520_001"],)
                return [{"row_id": "etc-summary-etc_20260520_001"}]
            return []

    connection = EtcSummaryLockConnection()
    missing = PostgresWorkbenchRelationRepository(connection).lock_canonical_relation_members(
        ["etc-summary-etc_20260520_001"],
        row_types=["invoice"],
        tenant_id="tenant-a",
    )

    assert missing == []
    assert len(connection.fetch_all_calls) == 2


def test_relation_member_lock_includes_case_identity_and_persisted_members_in_stable_order() -> None:
    class RelationLockConnection(RecordingConnection):
        def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
            self.fetch_all_calls.append((sql, params))
            normalized_sql = " ".join(sql.lower().split())
            if "from app.workbench_pair_relations" in normalized_sql:
                return [
                    {
                        "case_id": "CASE-1",
                        "row_ids": ["invoice-1", "bank-1"],
                        "row_types": ["invoice", "bank"],
                    }
                ]
            if "pg_advisory_xact_lock" in normalized_sql:
                assert params == (
                    ["bank:bank-1", "case:CASE-1", "invoice:invoice-1"],
                )
            return []

    connection = RelationLockConnection()
    locked = PostgresWorkbenchRelationRepository(connection).acquire_relation_member_locks(
        [],
        case_ids=["CASE-1"],
    )

    assert locked == ["bank:bank-1", "case:CASE-1", "invoice:invoice-1"]
    assert len(connection.fetch_all_calls) == 2
