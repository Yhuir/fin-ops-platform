from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from fin_ops_platform.services.bank_details_canonical_query import (
    PostgresBankDetailsCanonicalQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_query import (
    _ANOMALY_STATE_CTES,
    _SCOPED_CANONICAL_GROUPS_CTE,
    PostgresWorkbenchPageQueryRepository,
    WORKBENCH_GROUP_PAGE_SIZE,
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
    normalize_workbench_column_filters,
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
    assert "filter_option_anomaly_groups" not in connection.sql
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
    group_summary_sql = sql.split(
        "overall_group_summary as materialized (", 1
    )[1].split("overall_unique_members as materialized (", 1)[0]
    unique_members_sql = sql.split(
        "overall_unique_members as materialized (", 1
    )[1].split("overall_member_summary as materialized (", 1)[0]
    member_summary_sql = sql.split(
        "overall_member_summary as materialized (", 1
    )[1].split("overall_summary as materialized (", 1)[0]
    assert "canonical_group_members" not in group_summary_sql
    assert "count(distinct groups.internal_key)" not in group_summary_sql
    assert "canonical_group_members" in unique_members_sql
    assert "group by member.row_type, member.row_id" in unique_members_sql
    assert "from overall_unique_members member" in member_summary_sql
    assert "count(distinct (member.row_type, member.row_id))" not in member_summary_sql
    assert "select summary_paired_count::bigint as total_count" in sql
    assert "select summary_unpaired_count::bigint as total_count" in sql
    assert "where member.in_paired and member.row_type = 'oa'" in sql
    assert "where member.in_unpaired and member.row_type = 'oa'" in sql
    assert "invoice_inventory" in sql
    assert WORKBENCH_GROUP_PAGE_SIZE == 10
    assert connection.calls[0][1].count(WORKBENCH_GROUP_PAGE_SIZE + 1) == 2
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
    assert "oa_identity_aliases as materialized" in sql
    assert "jsonb_typeof(member.invoice_source_links)" in sql
    assert "jsonb_agg" not in sql
    assert "jsonb_build_object" not in sql
    assert "oa_payload" not in sql
    assert "latest_anomaly_decisions" in sql
    assert "workbench_anomaly_review" in sql
    assert "digest(" in sql
    assert "anomaly_fingerprints" in sql
    assert "anomaly_states" in sql
    assert "state" in sql


def test_set_based_anomaly_query_nets_bank_refunds_inside_a_relation() -> None:
    sql = " ".join(_ANOMALY_STATE_CTES.split()).lower()

    assert "member.bank_direction = direction.direction" in sql
    assert "member.bank_direction <> direction.direction" in sql
    assert "member.bank_direction in ('payment', 'receipt')" in sql


def test_set_based_anomaly_query_uses_turnover_principal_for_exact_closure() -> None:
    sql = " ".join(_ANOMALY_STATE_CTES.split()).lower()

    assert "relation.relation_mode" in sql
    assert "totals.relation_mode = 'turnover_manual_closure'" in sql
    assert "totals.bank_gross_total = totals.bank_contra_total" in sql
    assert "then totals.bank_gross_total" in sql
    assert "else totals.bank_gross_total - totals.bank_contra_total" in sql
    assert sql.count("member.bank_direction = direction.direction") == 1
    assert sql.count("member.bank_direction <> direction.direction") == 1


def test_set_based_anomaly_query_bridges_historical_oa_attachment_parent_aliases() -> None:
    canonical_sql = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.split())
    anomaly_sql = " ".join(_ANOMALY_STATE_CTES.split())

    assert "source_identity_aliases" in anomaly_sql
    assert "'Mongo文档ID'" in canonical_sql
    assert "'oa-exp-' || value" in anomaly_sql


def test_anomaly_query_reuses_canonical_source_facts_without_rescanning_sources() -> None:
    sql = " ".join(_ANOMALY_STATE_CTES.split()).lower()

    assert "member.oa_expense_items" in sql
    assert "member.invoice_source_links" in sql
    assert "left join app.oa_applications" not in sql
    assert "left join app.oa_pending_payment_admissions" not in sql
    assert "left join app.bank_transactions" not in sql
    assert "left join app.invoices invoice" not in sql


def test_canonical_spine_rolls_relation_members_once_for_zone_evaluation() -> None:
    sql = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.split()).lower()

    assert "all_active_relation_member_rollups as materialized" in sql
    assert "array_agg(member.row_type order by member.ordinality)" in sql
    assert "in_progress_oa_relation_ids as materialized" in sql
    assert "when in_progress_oa.relation_id is not null then 'unpaired'" in sql


def test_compact_summary_removes_repeated_internal_row_metadata() -> None:
    group = {
        "group_id": "case:CASE-1",
        "amount_check": {"status": "mismatch", "bank_total": "10.00"},
        "oa_rows": [
            {
                "id": "oa-1",
                "type": "oa",
                "relation_amount_check": {"status": "mismatch"},
                "object_identity_key": "oa-1",
                "source_identity_aliases": ["legacy-oa-1"],
                "special_metadata": {
                    "row_alignment": {"links": []},
                    "source_batch_id": "batch-1",
                    "batch_version": 2,
                },
            }
        ],
        "bank_rows": [],
        "invoice_rows": [],
    }

    compact = PostgresWorkbenchPageHydrationRepository._compact_group(group)

    assert compact["amount_check"] == group["amount_check"]
    assert compact["oa_rows"] == [
        {
            "id": "oa-1",
            "type": "oa",
            "special_metadata": {
                "source_batch_id": "batch-1",
                "batch_version": 2,
            },
        }
    ]


def test_compact_etc_summary_keeps_only_the_first_real_invoice_preview() -> None:
    group = {
        "group_id": "case:ETC-68",
        "invoice_rows": [
            {"id": "etc-summary-ETC-68", "type": "invoice", "source_kind": "etc_invoice_summary"}
        ],
        "collapsed_rows": {
            "invoice": [
                {
                    "id": "etc-invoice-1",
                    "type": "invoice",
                    "source_kind": "etc_invoice",
                    "detail_fields": [{"label": "冗余", "value": "不进入列表"}],
                },
                {"id": "etc-invoice-2", "type": "invoice", "source_kind": "etc_invoice"},
            ]
        },
        "collapsed_row_counts": {"invoice": 68},
    }

    compact = PostgresWorkbenchPageHydrationRepository._compact_group(group)

    assert compact["collapsed_rows"] == {
        "invoice": [
            {"id": "etc-invoice-1", "type": "invoice", "source_kind": "etc_invoice"}
        ]
    }
    assert compact["collapsed_row_counts"] == {"invoice": 68}


def test_compact_hydration_exposes_the_same_external_oa_identity_aliases() -> None:
    class _CaptureConnection:
        def __init__(self) -> None:
            self.sql = ""

        def fetch_all(
            self, sql: str, _params: tuple[Any, ...] = ()
        ) -> list[dict[str, Any]]:
            self.sql = " ".join(sql.split())
            return []

    connection = _CaptureConnection()
    repository = PostgresWorkbenchPageHydrationRepository(connection)

    with pytest.raises(ValueError, match="changed during hydration"):
        repository.hydrate_groups(
            scope_key="2026-05",
            descriptors=[
                {
                    "internal_key": "case:CASE-1",
                    "detail_key": "CASE-1",
                    "group_kind": "relation",
                    "member_ids": ["oa-exp-1"],
                    "member_types": ["oa"],
                }
            ],
            detail_level="summary",
        )

    assert "'source_identity_aliases'" in connection.sql
    assert "'Mongo文档ID'" in connection.sql
    assert "oa.normalized_payload->'detail_fields'->>'Mongo文档ID'" in connection.sql
    assert "oa.normalized_payload->>'expense_type'" in connection.sql
    assert "admission.source_payload->>'expense_type'" in connection.sql
    assert "'supporting_documents'" not in connection.sql


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

        def load_page_etc_summaries(
            self,
            _relations: object,
            **_kwargs: object,
        ) -> dict[str, dict[str, Any]]:
            return {}

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


def test_page_etc_summary_loader_batches_explicit_and_relation_identities() -> None:
    class _EmptyConnection:
        pass

    builder = WorkbenchCanonicalRowsBuilder(connection=_EmptyConnection())
    requested: list[set[str]] = []

    def load_missing(external_batch_ids: set[str]) -> dict[str, dict[str, Any]]:
        requested.append(set(external_batch_ids))
        return {
            "ETC-B": {
                "id": "etc-summary-ETC-B",
                "type": "invoice",
                "etc_batch_id": "ETC-B",
            }
        }

    builder._etc_invoice_summary_rows_for_page = load_missing  # type: ignore[method-assign]

    result = builder.load_page_etc_summaries(
        [
            {"special_metadata": {"external_etc_batch_id": "ETC-A"}},
        ],
        required_external_batch_ids={"ETC-B"},
    )

    assert requested == [{"ETC-A", "ETC-B"}]
    assert set(result) == {"ETC-B"}


def test_full_page_hydration_passes_prefetched_etc_summaries_to_grouping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    relation = {
        "case_id": "CASE-ETC",
        "status": "active",
        "row_ids": ["oa-1"],
        "row_types": ["oa"],
        "special_metadata": {"external_etc_batch_id": "ETC-1"},
    }
    oa_row = {
        "id": "oa-1",
        "type": "oa",
        "status": "unpaired",
        "expense_items": [],
    }
    etc_summary = {
        "id": "etc-summary-ETC-1",
        "type": "invoice",
        "etc_batch_id": "ETC-1",
    }

    class _PageBuilder:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def load_page_etc_summaries(
            self,
            relations: list[dict[str, Any]],
            *,
            required_external_batch_ids: set[str],
        ) -> dict[str, dict[str, Any]]:
            captured["relations"] = relations
            captured["required_external_batch_ids"] = required_external_batch_ids
            return {"ETC-1": dict(etc_summary)}

        def load_page_rows(
            self,
            _typed_row_ids: object,
            **kwargs: object,
        ) -> dict[tuple[str, str], dict[str, Any]]:
            captured["row_etc_summaries"] = kwargs.get("page_etc_summaries")
            return {("oa", "oa-1"): dict(oa_row)}

        def build_page_groups(self, **kwargs: Any) -> dict[str, Any]:
            captured["page_etc_summaries"] = kwargs.get("page_etc_summaries")
            return {
                "paired": {"groups": []},
                "unpaired": {
                    "groups": [
                        {
                            "group_id": "case:CASE-ETC",
                            "zone": "unpaired",
                            "status": "unpaired",
                            "oa_rows": [dict(oa_row)],
                            "bank_rows": [],
                            "invoice_rows": [],
                        }
                    ]
                },
            }

    monkeypatch.setattr(
        "fin_ops_platform.services.postgres_repositories.workbench_page_hydration.WorkbenchCanonicalRowsBuilder",
        _PageBuilder,
    )
    repository = PostgresWorkbenchPageHydrationRepository(object())
    repository._load_relations = lambda *_args, **_kwargs: ([relation], {})  # type: ignore[method-assign]

    groups = repository.hydrate_groups(
        scope_key="2026-07",
        descriptors=[
            {
                "internal_key": "case:CASE-ETC",
                "detail_key": "CASE-ETC",
                "group_kind": "relation",
                "member_ids": ["oa-1"],
                "member_types": ["oa"],
                "external_etc_batch_id": "ETC-1",
            }
        ],
        detail_level="full",
    )

    assert groups[0]["group_id"] == "case:CASE-ETC"
    assert captured["relations"] == [relation]
    assert captured["required_external_batch_ids"] == set()
    assert captured["row_etc_summaries"] == {"ETC-1": etc_summary}
    assert captured["page_etc_summaries"] == {"ETC-1": etc_summary}


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
    assert "requested_settings as materialized" in normalized
    assert "settings.settings_payload->'bank_account_mappings'" in normalized
    assert "'accountlast4', right(bank.account_no, 4)" in normalized
    assert "when '供应商付款申请' then '支付申请'" in normalized


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
        anomaly_review_decisions={},
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
            "oa": {
                "applicant": [
                    "applicant:张三",
                    f"applicant:{WORKBENCH_FILTER_MISSING_VALUE}",
                ]
            },
            "bank": {"amount": ["direction:expense", "account:1234"]},
        },
        time_filters={"invoice": {"mode": "year", "year": "2026"}},
    )

    assert "search_hit.row_type = search_member.row_type" in where_sql.lower()
    assert "searchable_text" not in where_sql.lower()
    assert "test_source_search_hits" in search_ctes
    assert r"%100\%\_\\%" in search_params
    assert "direction' = any" in where_sql
    assert "accountLast4' = any" in where_sql
    assert " or " in where_sql
    assert "invoice" in params
    assert "2026-01-01" in params
    assert "2027-01-01" in params


def test_etc_summary_search_uses_batch_ids_invoice_numbers_and_exact_amount() -> None:
    search_ctes, search_params, _hit_name = (
        PostgresWorkbenchPageQueryRepository._source_search_hit_ctes(
            prefix="etc",
            search="1549.00",
        )
    )
    normalized_sql = " ".join(search_ctes.split()).lower()

    assert "etc_batch.business_batch_id" in normalized_sql
    assert "submission_batch_id" in normalized_sql
    assert "from app.etc_invoices etc_invoice" in normalized_sql
    assert "etc_invoice.invoice_no" in normalized_sql
    assert "etc_batch.total_amount = %s::numeric" in normalized_sql
    assert Decimal("1549.00") in search_params


def test_grouped_filter_contract_rejects_legacy_flat_values() -> None:
    with pytest.raises(ValueError, match="unsupported grouped option"):
        normalize_workbench_column_filters({"bank": {"amount": ["支出"]}})

    assert normalize_workbench_column_filters(
        {
            "oa": {
                "applicant": ["oaType:支付申请", "workflow:completed"],
                "projectName": ["expenseType:交通费", "project:大理项目"],
            },
            "bank": {
                "amount": [
                    "direction:expense",
                    "account:8106",
                    "bankTag:expense-project",
                ]
            },
        }
    ) == {
        "oa": {
            "applicant": ["oaType:支付申请", "workflow:completed"],
            "projectName": ["expenseType:交通费", "project:大理项目"],
        },
        "bank": {
            "amount": [
                "account:8106",
                "bankTag:expense-project",
                "direction:expense",
            ]
        },
    }


def test_oa_grouped_filter_options_include_type_status_expense_and_project() -> None:
    applicant_connection = _QueryConnection(
        [
            {
                "row_id": "oa-1",
                "column_values": {
                    "applicationType": "支付申请",
                    "workflowStatus": "completed",
                    "applicant": "杨丽萍",
                },
                "oa_expense_items": [],
            }
        ]
    )
    applicant_repository = PostgresWorkbenchPageQueryRepository(
        applicant_connection,
        tenant_id="test-tenant",
    )
    applicant = applicant_repository._filter_options(
        scope_key="all",
        zone="unpaired",
        pane="oa",
        facet="column",
        column="applicant",
    )
    assert applicant["options"] == [
        {
            "value": "oaType:支付申请",
            "label": "支付申请",
            "missing": False,
            "group": "OA 类型",
        },
        {
            "value": "oaType:日常报销",
            "label": "日常报销",
            "missing": False,
            "group": "OA 类型",
        },
        {
            "value": "workflow:completed",
            "label": "已完成",
            "missing": False,
            "group": "流程状态",
        },
        {
            "value": "workflow:in_progress",
            "label": "进行中",
            "missing": False,
            "group": "流程状态",
        },
        {
            "value": "applicant:杨丽萍",
            "label": "杨丽萍",
            "missing": False,
            "group": "申请人",
        },
    ]
    assert "from filter_option_anomaly_groups groups" in applicant_connection.sql
    assert applicant_connection.params[4] == "oa"

    project_repository = PostgresWorkbenchPageQueryRepository(
        _QueryConnection(
            [
                {
                    "row_id": "oa-1",
                    "column_values": {"projectName": "多个项目"},
                    "oa_expense_items": [
                        {"project_name": "大理项目", "expense_type": "交通费"},
                        {"project_name": "曲靖项目", "expense_type": "车辆使用费"},
                    ],
                }
            ]
        ),
        tenant_id="test-tenant",
    )
    project = project_repository._filter_options(
        scope_key="all",
        zone="unpaired",
        pane="oa",
        facet="column",
        column="projectName",
    )
    assert [option["group"] for option in project["options"]] == [
        "OA 费用类型",
        "OA 费用类型",
        "项目名称",
        "项目名称",
    ]
    assert {option["value"] for option in project["options"]} == {
        "expenseType:交通费",
        "expenseType:车辆使用费",
        "project:大理项目",
        "project:曲靖项目",
    }


def test_plain_filter_options_also_narrow_anomalies_to_the_target_pane() -> None:
    connection = _QueryConnection(
        [{"facet_value": "云南供应商", "facet_label": "云南供应商"}]
    )

    payload = PostgresWorkbenchPageQueryRepository(
        connection,
        tenant_id="test-tenant",
    )._filter_options(
        scope_key="all",
        zone="unpaired",
        pane="bank",
        facet="column",
        column="counterparty",
    )

    assert payload["options"] == [
        {"value": "云南供应商", "label": "云南供应商", "missing": False}
    ]
    assert "from filter_option_anomaly_groups groups" in connection.sql
    assert connection.params[4] == "bank"


def test_project_and_expense_type_share_one_oa_expense_item() -> None:
    clauses, params = PostgresWorkbenchPageQueryRepository._member_filter_clauses(
        pane="oa",
        pane_filters={
            "projectName": ["project:大理项目", "expenseType:交通费"]
        },
        time_filter=None,
        alias="member",
        bank_tag_row_ids=None,
    )

    assert len(clauses) == 1
    assert "jsonb_array_elements(member.oa_expense_items)" in clauses[0]
    assert " and " in clauses[0]
    assert params == [
        ["大理项目"],
        ["交通费"],
        ["大理项目"],
        ["交通费"],
    ]


def test_bank_grouped_options_use_account_mapping_and_canonical_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BankOptionConnection(_QueryConnection):
        def fetch_one(
            self, _sql: str, _params: tuple[Any, ...] = ()
        ) -> dict[str, object]:
            return {"settings_payload": {"bank_account_mappings": []}}

    connection = _BankOptionConnection(
        [
            {
                "row_id": "bank-1",
                "column_values": {
                    "direction": "支出",
                    "accountLast4": "8106",
                    "paymentAccount": "建设银行 基本户 8106",
                },
                "oa_expense_items": [],
            }
        ]
    )
    monkeypatch.setattr(
        PostgresBankDetailsCanonicalQueryRepository,
        "workbench_category_projection_rows",
        lambda *_args, **_kwargs: {
            "bank-1": {
                "category_code": "expense-project",
                "category_label": "员工报销",
                "category_label_path": ["项目开销", "员工报销"],
            }
        },
    )
    payload = PostgresWorkbenchPageQueryRepository(
        connection,
        tenant_id="test-tenant",
    )._filter_options(
        scope_key="all",
        zone="unpaired",
        pane="bank",
        facet="column",
        column="amount",
    )

    assert payload["options"] == [
        {
            "value": "direction:expense",
            "label": "支出",
            "missing": False,
            "group": "收支方向",
        },
        {
            "value": "account:8106",
            "label": "建设银行 基本户 8106",
            "missing": False,
            "group": "银行账户",
        },
        {
            "value": "bankTag:expense-project",
            "label": "项目开销 / 员工报销",
            "missing": False,
            "group": "流水标签",
        },
    ]
    assert "from filter_option_anomaly_groups groups" in connection.sql
    assert connection.params[4] == "bank"


def test_bank_tag_filter_resolves_only_canonical_matching_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BankTagConnection(_QueryConnection):
        def fetch_one(
            self, _sql: str, _params: tuple[Any, ...] = ()
        ) -> dict[str, object]:
            return {"settings_payload": {}}

    connection = _BankTagConnection([{"row_id": "bank-1"}, {"row_id": "bank-2"}])
    monkeypatch.setattr(
        PostgresBankDetailsCanonicalQueryRepository,
        "workbench_category_projection_rows",
        lambda *_args, **_kwargs: {
            "bank-1": {"category_code": "expense-project"},
            "bank-2": {"category_code": "income-refund"},
        },
    )
    repository = PostgresWorkbenchPageQueryRepository(
        connection,
        tenant_id="test-tenant",
    )

    assert repository._resolve_bank_tag_filter_row_ids(
        scope_key="all",
        zone="unpaired",
        status=None,
        source_kind=None,
        search=None,
        column_filters={
            "bank": {
                "amount": ["direction:expense", "bankTag:expense-project"]
            }
        },
        time_filters={},
        exception_bucket=None,
    ) == ["bank-1"]
    assert "bankTag:" not in str(connection.params)
    assert "from filter_option_anomaly_groups groups" in connection.sql
    assert connection.params[4] == "bank"
