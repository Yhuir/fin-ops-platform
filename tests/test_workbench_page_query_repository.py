from __future__ import annotations

from typing import Any

import pytest

from fin_ops_platform.services.postgres_repositories.workbench_page_query import (
    _ANOMALY_STATE_CTES,
    _SCOPED_CANONICAL_GROUPS_CTE,
    PostgresWorkbenchPageQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_hydration import (
    WORKBENCH_PAGE_HYDRATION_STATEMENT_BUDGET,
    PostgresWorkbenchPageHydrationRepository,
)
from fin_ops_platform.services.workbench_canonical_rows import (
    WorkbenchCanonicalRowsBuilder,
)
from fin_ops_platform.services.workbench_filter_options import (
    WORKBENCH_FILTER_MISSING_VALUE,
)
from fin_ops_platform.services.workbench_page_cursor import (
    decode_workbench_page_cursor,
    workbench_query_hash,
)
from fin_ops_platform.services.workbench_relation_requirements import (
    evaluate_bank_relation_completion,
)


class _QueryConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.sql = " ".join(sql.split())
        self.params = params
        return list(self.rows)


class _CountingQueryConnection(_QueryConnection):
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__(rows)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.calls.append((" ".join(sql.split()), params))
        return super().fetch_all(sql, params)


def test_groups_page_uses_exact_totals_keyset_and_page_only_hydration() -> None:
    connection = _QueryConnection(
        [
            {
                "internal_key": "row:bank:bank-2",
                "detail_key": "bank-2",
                "group_kind": "unpaired",
                "member_ids": ["bank-2"],
                "member_types": ["bank"],
                "sort_missing": False,
                "sort_value": "2026-07-02",
                "total_count": 7,
                "oa_count": 1,
                "bank_count": 5,
                "invoice_count": 1,
            },
            {
                "internal_key": "row:bank:bank-1",
                "detail_key": "bank-1",
                "group_kind": "unpaired",
                "member_ids": ["bank-1"],
                "member_types": ["bank"],
                "sort_missing": False,
                "sort_value": "2026-07-01",
                "total_count": 7,
                "oa_count": 1,
                "bank_count": 5,
                "invoice_count": 1,
            },
        ]
    )
    repository = PostgresWorkbenchPageQueryRepository(connection, tenant_id="test-tenant")
    hydrated_descriptors: list[dict[str, Any]] = []

    def hydrate(**kwargs: Any) -> list[dict[str, Any]]:
        hydrated_descriptors.extend(kwargs["descriptors"])
        return [{"group_id": "unpaired:bank:hash", "detail_key": "bank-2"}]

    repository._hydrate_groups = hydrate  # type: ignore[method-assign]

    payload = repository._groups_page(
        scope_key="2026-07",
        zone="unpaired",
        page_size=1,
        sort="bank:desc",
    )

    assert payload == {
        "month": "2026-07",
        "scope_key": "2026-07",
        "zone": "unpaired",
        "page_size": 1,
        "total": 7,
        "row_counts": {"oa": 1, "bank": 5, "invoice": 1, "rows": 7},
        "has_more": True,
        "next_cursor": payload["next_cursor"],
        "groups": [{"group_id": "unpaired:bank:hash", "detail_key": "bank-2"}],
    }
    assert [row["detail_key"] for row in hydrated_descriptors] == ["bank-2"]
    assert "exact_totals" in connection.sql
    assert "exact_row_counts" in connection.sql
    assert "offset" not in connection.sql.lower()
    assert "limit %s" in connection.sql.lower()
    decoded = decode_workbench_page_cursor(
        payload["next_cursor"],
        expected_query_hash=workbench_query_hash(
            {
                "scope_key": "2026-07",
                "zone": "unpaired",
                "status": None,
                "source_kind": None,
                "search": None,
                "sort": "bank:desc",
                "column_filters": {},
                "time_filters": {},
                "exception_bucket": None,
            }
        ),
        expected_sort="bank:desc",
    )
    assert decoded is not None
    assert decoded.group_key == "row:bank:bank-2"


def test_initial_page_uses_one_shared_candidate_spine_and_one_combined_hydration() -> None:
    metadata = {
        "summary_oa_count": 1,
        "summary_bank_count": 1,
        "summary_invoice_count": 0,
        "summary_paired_count": 1,
        "summary_unpaired_count": 1,
        "inventory_system_total": 2,
        "unpaired_exception_count": 0,
        "paired_exception_count": 0,
    }
    connection = _CountingQueryConnection(
        [
            {
                **metadata,
                "record_zone": "metadata",
                "internal_key": None,
            },
            {
                "record_zone": "paired",
                "internal_key": "case:case-1",
                "detail_key": "case-1",
                "group_kind": "relation",
                "zone": "paired",
                "member_ids": ["oa-1"],
                "member_types": ["oa"],
                "sort_missing": False,
                "sort_value": "2026-07-02",
                "page_position": 1,
                "total_count": 1,
                "oa_count": 1,
                "bank_count": 0,
                "invoice_count": 0,
            },
            {
                "record_zone": "unpaired",
                "internal_key": "row:bank:bank-1",
                "detail_key": "bank-1",
                "group_kind": "unpaired",
                "zone": "unpaired",
                "member_ids": ["bank-1"],
                "member_types": ["bank"],
                "sort_missing": False,
                "sort_value": "2026-07-01",
                "page_position": 1,
                "total_count": 1,
                "oa_count": 0,
                "bank_count": 1,
                "invoice_count": 0,
            },
        ]
    )
    repository = PostgresWorkbenchPageQueryRepository(connection, tenant_id="test-tenant")
    hydrated_batches: list[list[dict[str, Any]]] = []

    def hydrate(**kwargs: Any) -> list[dict[str, Any]]:
        descriptors = list(kwargs["descriptors"])
        hydrated_batches.append(descriptors)
        return [
            {"group_id": "case:case-1", "detail_key": "case-1"},
            {"group_id": "unpaired:bank:digest", "detail_key": "bank-1"},
        ]

    repository._hydrate_groups = hydrate  # type: ignore[method-assign]

    payload = repository._initial_page(
        scope_key="2026-07",
        paired_query=None,
        unpaired_query=None,
    )

    assert len(connection.calls) == 1
    sql = connection.calls[0][0].lower()
    assert sql.count("requested_scope as") == 1
    assert "paired_filtered_groups" in sql
    assert "unpaired_filtered_groups" in sql
    assert "overall_summary" in sql
    assert "invoice_inventory" in sql
    assert [row["internal_key"] for row in hydrated_batches[0]] == [
        "case:case-1",
        "row:bank:bank-1",
    ]
    assert payload["summary"]["unpaired_exception_count"] == 0
    assert payload["summary"]["paired_exception_count"] == 0
    assert "anomaly_states" in sql
    assert "anomaly_counts" in sql
    assert payload["summary"]["paired_count"] == 1
    assert payload["invoice_inventory"]["system_total"] == 2
    assert payload["paired"]["groups"][0]["detail_key"] == "case-1"
    assert payload["unpaired"]["groups"][0]["detail_key"] == "bank-1"
    page_rows = connection.rows[1:]
    assert all("anomaly_members" not in row for row in page_rows)
    assert all("ignored_anomaly_fingerprints" not in row for row in page_rows)


def test_canonical_spine_materializes_visible_invoice_facts_once() -> None:
    sql = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.lower().split())

    assert sql.count("visible_invoice_facts as materialized") == 1
    assert sql.count("from visible_invoice_facts invoice") == 2
    assert sql.count("join visible_invoice_facts invoice") == 1
    assert sql.count("coalesce(invoice.workbench_visibility, 'visible') <> 'hidden_after_etc_submission'") == 1


def test_set_based_anomaly_query_emits_only_compact_fingerprint_state() -> None:
    sql = " ".join(_ANOMALY_STATE_CTES.split()).lower()

    assert "relation_anomaly_members" in sql
    assert "latest_anomaly_decisions" in sql
    assert "workbench_anomaly_review" in sql
    assert "digest(" in sql
    assert "anomaly_fingerprints" in sql
    assert "anomaly_states" in sql
    assert "state" in sql


def test_detail_queries_are_typed_and_bounded_without_full_scope_spine() -> None:
    connection = _CountingQueryConnection([])
    repository = PostgresWorkbenchPageQueryRepository(connection, tenant_id="test-tenant")

    with pytest.raises(ValueError, match="row_type"):
        repository._row_detail(scope_key="2026-07", row_id="same-id")
    assert repository._row_detail(
        scope_key="2026-07",
        row_id="same-id",
        row_type="bank",
    ) is None
    assert len(connection.calls) == 1
    sql = connection.calls[0][0].lower()
    assert "target_source_candidates" in sql
    assert "unnest(relation.row_ids, relation.row_types)" in sql
    assert "scoped_source_keys" not in sql
    assert "limit 4" in sql

    connection.calls.clear()
    assert repository._group_detail(
        scope_key="2026-07",
        zone="unpaired",
        group_id="unpaired:bank:digest",
    ) is None
    assert connection.calls == []


def test_page_hydration_enforces_fixed_statement_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EmptyConnection:
        def fetch_all(self, _sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
            return []

        def fetch_one(self, _sql: str, _params: tuple[Any, ...] = ()) -> None:
            return None

    class _OverBudgetBuilder:
        def __init__(self, *, connection: Any, **_kwargs: Any) -> None:
            self.connection = connection

        def load_page_rows(
            self, _typed_row_ids: object, **_kwargs: object
        ) -> dict[tuple[str, str], dict[str, Any]]:
            for _ in range(WORKBENCH_PAGE_HYDRATION_STATEMENT_BUDGET + 1):
                self.connection.fetch_all("select 1")
            return {}

    monkeypatch.setattr(
        "fin_ops_platform.services.postgres_repositories.workbench_page_hydration.WorkbenchCanonicalRowsBuilder",
        _OverBudgetBuilder,
    )
    repository = PostgresWorkbenchPageHydrationRepository(_EmptyConnection())

    with pytest.raises(RuntimeError, match="statement budget"):
        repository.hydrate_groups(
            scope_key="2026-07",
            descriptors=[
                {
                    "internal_key": "row:bank:bank-1",
                    "detail_key": "bank-1",
                    "group_kind": "unpaired",
                    "member_ids": ["bank-1"],
                    "member_types": ["bank"],
                }
            ],
            detail_level="full",
        )


def test_scope_spine_prunes_relation_candidates_then_rechecks_typed_membership() -> None:
    normalized = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.split()).lower()

    assert "relation.row_ids && array" in normalized
    assert "relation.month_scope = scope.scope_month" in normalized
    assert "unnest(relation.row_ids, relation.row_types) with ordinality" in normalized
    assert "source_key.row_type = member.row_type" in normalized
    assert "row.pane = member.row_type" in normalized
    assert "row.row_id = member.row_id" in normalized
    assert "cardinality(relation.row_ids)" in normalized
    assert "cardinality(relation.row_types)" in normalized
    assert "relation_shape_guard" in normalized
    assert "relation_member_guard" in normalized
    assert "invoice_identity_guard" in normalized
    assert "oa.normalized_payload::text" not in normalized
    assert "bank.raw_payload::text" not in normalized
    assert "invoice.raw_payload::text" not in normalized
    assert "searchable_text" not in normalized


def test_page_grouping_preserves_cross_pane_same_textual_id() -> None:
    class _NoOverridesConnection:
        def fetch_all(
            self, _sql: str, _params: tuple[Any, ...] = ()
        ) -> list[dict[str, Any]]:
            return []

        def fetch_one(self, _sql: str, _params: tuple[Any, ...] = ()) -> None:
            return None

    rows = {
        ("bank", "same-id"): {
            "id": "same-id",
            "type": "bank",
            "source_kind": "bank",
            "object_identity_key": "bank:same-id",
            "status": "unpaired",
        },
        ("invoice", "same-id"): {
            "id": "same-id",
            "type": "invoice",
            "source_kind": "invoice",
            "object_identity_key": "invoice:same-id",
            "status": "unpaired",
        },
    }
    relation = {
        "case_id": "CASE-TYPED",
        "status": "active",
        "row_ids": ["same-id", "same-id"],
        "row_types": ["bank", "invoice"],
        "special_metadata": {"requires_oa": False, "requires_invoice": True},
    }

    payload = WorkbenchCanonicalRowsBuilder(
        connection=_NoOverridesConnection()
    ).build_page_groups(
        scope_key="2026-07",
        rows_by_typed_id=rows,
        relations=[relation],
    )

    groups = [
        *payload["paired"]["groups"],
        *payload["unpaired"]["groups"],
    ]
    assert len(groups) == 1
    group_rows = PostgresWorkbenchPageHydrationRepository.group_rows(groups[0])
    assert [(row["type"], row["id"]) for row in group_rows] == [
        ("bank", "same-id"),
        ("invoice", "same-id"),
    ]


@pytest.mark.parametrize(
    ("row_types", "statuses", "metadata", "expected_zone", "missing"),
    [
        (["oa"], ["completed"], {}, "unpaired", ["bank"]),
        (["invoice"], [], {}, "paired", []),
        (["bank"], [], {"requires_oa": False, "requires_invoice": False}, "paired", []),
        (["bank"], [], {}, "unpaired", ["oa", "invoice"]),
        (["oa", "bank", "invoice"], ["in_progress"], {}, "unpaired", []),
        (["oa"], ["completed"], {"source": "batch_accounting"}, "paired", []),
    ],
)
def test_direct_relation_zone_fixtures_match_domain_completion_policy(
    row_types: list[str],
    statuses: list[str],
    metadata: dict[str, object],
    expected_zone: str,
    missing: list[str],
) -> None:
    completion = evaluate_bank_relation_completion(
        row_types=row_types,
        oa_workflow_statuses=statuses,
        special_metadata=metadata,
    )

    assert ("paired" if completion["is_complete"] else "unpaired") == expected_zone
    assert completion["missing_row_types"] == missing


def test_filter_sql_escapes_literal_search_and_preserves_and_or_semantics() -> None:
    search_ctes, search_params, search_hit_name = (
        PostgresWorkbenchPageQueryRepository._source_search_hit_ctes(
            prefix="test",
            search="100%_\\",
        )
    )
    where_sql, params = PostgresWorkbenchPageQueryRepository._group_filters(
        zone="unpaired",
        status=None,
        source_kind=None,
        search="100%_\\",
        search_hit_name=search_hit_name,
        column_filters={
            "oa": {"applicant": ["张三", WORKBENCH_FILTER_MISSING_VALUE]},
            "bank": {"amount": ["支出", "招商银行 基本户 1234"]},
        },
        time_filters={"invoice": {"mode": "year", "year": "2026"}},
    )

    assert "search_hit.row_type = search_member.row_type" in where_sql.lower()
    assert "searchable_text" not in where_sql.lower()
    assert "test_source_search_hits" in search_ctes
    assert r"%100\%\_\\%" in search_params
    assert "direction' = any" in where_sql
    assert "paymentAccount' = any" in where_sql
    assert " or " in where_sql
    assert "invoice" in params
    assert "2026-01-01" in params
    assert "2027-01-01" in params
