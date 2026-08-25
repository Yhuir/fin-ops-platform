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
    invoice_source_kinds,
)
from fin_ops_platform.services.workbench_anomaly_contract import AMOUNT_EXCEPTION_CODES
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


def test_invoice_source_kinds_are_stable_deduplicated_evidence_not_ownership() -> None:
    assert invoice_source_kinds(
        [
            {"source_type": "oa_attachment_invoice"},
            {"source_type": "custom_source"},
            {"source_type": "manual_invoice_import"},
            {"source_type": "oa_expense_item_invoice"},
            {"source_type": "oa_attachment_invoice"},
        ]
    ) == [
        "manual_invoice_import",
        "oa_attachment_invoice",
        "oa_expense_item_invoice",
        "custom_source",
    ]


def test_invoice_source_kinds_keep_legacy_scalar_in_full_and_both_summary_dtos() -> None:
    source_links = [
        {"source_type": "oa_attachment_invoice", "source_expense_item_id": "item-1"},
        {"source_type": "manual_invoice_import", "source_id": "file-1"},
        {"source_type": "oa_expense_item_invoice", "source_expense_item_id": "item-1"},
        {"source_type": "oa_attachment_invoice", "source_expense_item_id": "item-1"},
    ]
    full = WorkbenchCanonicalRowsBuilder(
        connection=object()
    )._invoice_row_from_sql({
        "row_id": "invoice-1",
        "invoice_type": "input",
        "invoice_no": "26539150014000401220",
        "invoice_date": "2026-06-29",
        "amount": "145.00",
        "total_with_tax": "145.00",
        "source_links": source_links,
        "raw_payload": {"normalized_payload": {}},
        "tags": [],
    })

    assert full is not None
    assert full["source_kind"] == "oa_attachment_invoice"
    assert full["source_kinds"] == [
        "manual_invoice_import",
        "oa_attachment_invoice",
        "oa_expense_item_invoice",
    ]
    for _route in ("initial", "groups"):
        summary = PostgresWorkbenchPageHydrationRepository._compact_group({
            "group_id": "unpaired:invoice:invoice-1",
            "oa_rows": [],
            "bank_rows": [],
            "invoice_rows": [full],
        })
        assert summary["invoice_rows"][0]["source_kind"] == "oa_attachment_invoice"
        assert summary["invoice_rows"][0]["source_kinds"] == full["source_kinds"]


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
    assert "exception_counts" not in connection.sql
    assert "offset" not in connection.sql.lower()
    assert "limit %s" in connection.sql.lower()
    filtered_groups_sql = connection.sql.split(
        "filtered_groups as materialized (", 1
    )[1].split("keyed_groups as materialized (", 1)[0]
    assert "left join canonical_group_members member" in filtered_groups_sql
    assert "max(member.sort_date)" in filtered_groups_sql
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


def test_groups_page_default_sort_skips_member_sort_aggregation_but_keeps_exists_filters() -> None:
    connection = _QueryConnection([])
    repository = PostgresWorkbenchPageQueryRepository(connection, tenant_id="test-tenant")

    payload = repository._groups_page(
        scope_key="2026-07",
        zone="unpaired",
        source_kind="bank_transaction",
        column_filters={
            "oa": {"applicant": ["applicant:张三"]},
        },
    )

    assert payload["groups"] == []
    filtered_groups_sql = connection.sql.split(
        "filtered_groups as materialized (", 1
    )[1].split("keyed_groups as materialized (", 1)[0]
    assert "from effective_groups groups" in filtered_groups_sql
    assert "left join canonical_group_members member" not in filtered_groups_sql
    assert "min(member.sort_date)" not in filtered_groups_sql
    assert "null::date as oa_sort_min" in filtered_groups_sql
    assert "exists (select 1 from canonical_group_members source_member" in filtered_groups_sql
    assert "exists (select 1 from canonical_group_members filter_member" in filtered_groups_sql


def test_exception_amount_view_returns_additive_counts_and_auto_code_cursor() -> None:
    selected_code = "oa_bank_equal_invoice_more"
    metadata = {
        "internal_key": "case:case-amount-1",
        "detail_key": "case-amount-1",
        "group_kind": "relation",
        "member_ids": ["oa-1", "bank-1", "invoice-1"],
        "member_types": ["oa", "bank", "invoice"],
        "sort_missing": False,
        "sort_value": "2026-07-02",
        "total_count": 2,
        "oa_count": 2,
        "bank_count": 2,
        "invoice_count": 2,
        "exception_total": 4,
        "amount_exception_total": 3,
        "document_only_exception_total": 1,
        "selected_exception_code": selected_code,
        f"exception_count_{selected_code}": 2,
        "exception_count_all_amounts_different": 1,
    }
    connection = _CountingQueryConnection([metadata, {**metadata, "internal_key": "case:more"}])
    repository = PostgresWorkbenchPageQueryRepository(connection, tenant_id="test-tenant")
    repository._hydrate_groups = lambda **kwargs: [  # type: ignore[method-assign]
        {"group_id": str(row["internal_key"])} for row in kwargs["descriptors"]
    ]

    payload = repository._groups_page(
        scope_key="2026-07",
        zone="unpaired",
        page_size=1,
        exception_bucket="unpaired",
        exception_view="amount",
    )

    assert payload["total"] == 2
    assert payload["selected_exception_code"] == selected_code
    assert payload["exception_counts"] == {
        "total": 4,
        "amount_total": 3,
        "document_only": 1,
        "by_code": {
            code: (
                2
                if code == selected_code
                else 1
                if code == "all_amounts_different"
                else 0
            )
            for code in AMOUNT_EXCEPTION_CODES
        },
    }
    assert len(connection.calls) == 1
    assert "base_filtered_groups" in connection.sql
    assert "exception_counts" in connection.sql
    assert "selected_exception" in connection.sql
    assert payload["next_cursor"] is not None
    decoded = decode_workbench_page_cursor(
        payload["next_cursor"],
        expected_query_hash=workbench_query_hash(
            {
                "scope_key": "2026-07",
                "zone": "unpaired",
                "status": None,
                "source_kind": None,
                "search": None,
                "sort": "default:desc",
                "column_filters": {},
                "time_filters": {},
                "exception_bucket": "unpaired",
                "exception_view": "amount",
            }
        ),
        expected_sort="default:desc",
    )
    assert decoded is not None
    assert decoded.partition == selected_code

    next_code = "oa_bank_equal_invoice_less"
    connection.rows = [{
        **metadata,
        f"exception_count_{selected_code}": 0,
        f"exception_count_{next_code}": 2,
        "selected_exception_code": selected_code,
    }]
    continued = repository._groups_page(
        scope_key="2026-07",
        zone="unpaired",
        page_size=1,
        cursor=payload["next_cursor"],
        exception_bucket="unpaired",
        exception_view="amount",
    )
    assert continued["selected_exception_code"] == selected_code
    assert selected_code in connection.params
    assert "cursor_exception_code" in connection.sql
    with pytest.raises(ValueError, match="cursor"):
        repository._groups_page(
            scope_key="2026-07",
            zone="unpaired",
            page_size=1,
            cursor=payload["next_cursor"],
            exception_bucket="unpaired",
            exception_view="amount",
            exception_code=selected_code,
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"exception_bucket": "paired"}, "must match zone"),
        ({"exception_bucket": "unpaired", "exception_view": "unknown"}, "exception_view"),
        (
            {
                "exception_bucket": "unpaired",
                "exception_view": "amount",
                "exception_code": "unknown",
            },
            "exception_code",
        ),
        ({"exception_view": "amount"}, "requires exception_bucket"),
        (
            {
                "exception_bucket": "unpaired",
                "exception_view": "document_only",
                "exception_code": "oa_bank_equal_invoice_more",
            },
            "requires exception_view=amount",
        ),
    ],
)
def test_exception_view_query_rejects_invalid_contract(
    kwargs: dict[str, str],
    message: str,
) -> None:
    repository = PostgresWorkbenchPageQueryRepository(_QueryConnection([]), tenant_id="test-tenant")

    with pytest.raises(ValueError, match=message):
        repository._groups_page(scope_key="2026-07", zone="unpaired", **kwargs)


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
    paired_filtered_sql = sql.split(
        "paired_filtered_groups as materialized (", 1
    )[1].split("paired_keyed_groups as materialized (", 1)[0]
    unpaired_filtered_sql = sql.split(
        "unpaired_filtered_groups as materialized (", 1
    )[1].split("unpaired_keyed_groups as materialized (", 1)[0]
    assert "left join canonical_group_members member" not in paired_filtered_sql
    assert "left join canonical_group_members member" not in unpaired_filtered_sql
    assert "null::date as oa_sort_min" in paired_filtered_sql
    assert "null::date as oa_sort_min" in unpaired_filtered_sql
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
    assert "paired_oa_count::bigint as oa_count" in sql
    assert "paired_bank_count::bigint as bank_count" in sql
    assert "paired_invoice_count::bigint as invoice_count" in sql
    assert "unpaired_oa_count::bigint as oa_count" in sql
    assert "unpaired_bank_count::bigint as bank_count" in sql
    assert "unpaired_invoice_count::bigint as invoice_count" in sql
    assert sql.count("from overall_unique_members member") == 1
    assert "invoice_inventory" in sql
    invoice_inventory_sql = sql.split(
        "invoice_inventory as materialized (", 1
    )[1].split("batch_inventory as materialized (", 1)[0]
    assert invoice_inventory_sql.count("jsonb_array_elements(") == 1
    assert "source_flags.has_manual_import" in invoice_inventory_sql
    assert "source_flags.has_oa_attachment" in invoice_inventory_sql
    assert WORKBENCH_GROUP_PAGE_SIZE == 10
    assert connection.calls[0][1].count(WORKBENCH_GROUP_PAGE_SIZE + 1) == 2
    assert [row["internal_key"] for row in hydrated_batches[0]] == [
        "case:case-1",
        "row:bank:bank-1",
    ]
    assert payload["summary"]["unpaired_exception_count"] == 0
    assert payload["summary"]["paired_exception_count"] == 0
    assert "anomaly_states" in sql
    assert "anomaly_counts as materialized" not in sql
    assert "left join anomaly_states anomaly" in group_summary_sql
    assert payload["summary"]["paired_count"] == 1
    assert payload["invoice_inventory"]["system_total"] == 2
    assert payload["paired"]["groups"][0]["detail_key"] == "case-1"
    assert payload["unpaired"]["groups"][0]["detail_key"] == "bank-1"
    page_rows = connection.rows[1:]
    assert all("anomaly_members" not in row for row in page_rows)
    assert all("ignored_anomaly_fingerprints" not in row for row in page_rows)


def test_initial_page_keeps_member_sort_aggregation_only_for_explicitly_sorted_zone() -> None:
    connection = _CountingQueryConnection(
        [{"record_zone": "metadata", "internal_key": None}]
    )
    repository = PostgresWorkbenchPageQueryRepository(connection, tenant_id="test-tenant")

    payload = repository._initial_page(
        scope_key="2026-07",
        paired_query={"sort": "bank:desc"},
        unpaired_query=None,
    )

    assert payload["paired"]["groups"] == []
    assert payload["unpaired"]["groups"] == []
    sql = connection.calls[0][0].lower()
    paired_filtered_sql = sql.split(
        "paired_filtered_groups as materialized (", 1
    )[1].split("paired_keyed_groups as materialized (", 1)[0]
    unpaired_filtered_sql = sql.split(
        "unpaired_filtered_groups as materialized (", 1
    )[1].split("unpaired_keyed_groups as materialized (", 1)[0]
    assert "left join canonical_group_members member" in paired_filtered_sql
    assert "max(member.sort_date)" in paired_filtered_sql
    assert "left join canonical_group_members member" not in unpaired_filtered_sql
    assert "min(member.sort_date)" not in unpaired_filtered_sql
    assert "null::date as oa_sort_min" in unpaired_filtered_sql


def test_canonical_spine_materializes_visible_invoice_facts_once() -> None:
    sql = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.lower().split())
    visible_invoice_sql = sql.split(
        "visible_invoice_facts as materialized (", 1
    )[1].split("scoped_source_keys as materialized (", 1)[0]

    assert sql.count("visible_invoice_facts as materialized") == 1
    assert sql.count("from visible_invoice_facts invoice") == 3
    assert sql.count("join visible_invoice_facts invoice") == 1
    assert sql.count("coalesce(invoice.workbench_visibility, 'visible') <> 'hidden_after_etc_submission'") == 1
    assert visible_invoice_sql.count("jsonb_array_elements(") == 1
    assert "source_flags.has_direct_oa_attachment" in visible_invoice_sql
    assert "source_flags.has_manual_import" in visible_invoice_sql


def test_canonical_spine_rolls_active_invoice_relation_members_once() -> None:
    sql = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.lower().split())
    active_member_sql = sql.split(
        "active_invoice_relation_members as materialized (", 1
    )[1].split("invoice_candidates as materialized (", 1)[0]
    invoice_candidate_sql = sql.split(
        "invoice_candidates as materialized (", 1
    )[1].split("ranked_invoices as materialized (", 1)[0]

    assert sql.count("active_invoice_relation_members as materialized") == 1
    assert "select distinct member.row_id" in active_member_sql
    assert "relation.status = 'active'" in active_member_sql
    assert "cardinality(relation.row_ids) = cardinality(relation.row_types)" in active_member_sql
    assert "cross join lateral unnest(relation.row_ids, relation.row_types)" in active_member_sql
    assert "when 'etc_invoice_summary' then 'invoice'" in active_member_sql
    assert "left join active_invoice_relation_members active_member" in invoice_candidate_sql
    assert "active_member.row_id is not null as active_relation_member" in invoice_candidate_sql
    assert "from app.workbench_pair_relations owner_relation" not in invoice_candidate_sql
    assert "owner_relation.row_ids @> array[invoice.row_id]" not in invoice_candidate_sql


def test_page_members_are_narrow_and_anomalies_rehydrate_by_typed_identity() -> None:
    spine_sql = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.lower().split())
    member_sql = spine_sql.split("canonical_group_members as materialized (", 1)[1]
    anomaly_sql = " ".join(_ANOMALY_STATE_CTES.lower().split())
    anomaly_members = anomaly_sql.split(
        "relation_anomaly_members as materialized (", 1
    )[1].split("oa_exact_identity_aliases as materialized (", 1)[0]

    assert "row.oa_source_aliases" not in member_sql
    assert "row.invoice_source_links" not in member_sql
    assert "join canonical_rows canonical_row" in anomaly_members
    assert "canonical_row.pane = member.row_type" in anomaly_members
    assert "canonical_row.row_id = member.row_id" in anomaly_members


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
    assert "bool_or(item.has_document_anomaly)" in sql
    assert "max(item.exception_code)" in sql
    assert "document_anomaly_groups" not in sql
    assert "left join relation_amount_classifications classification" not in sql
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
    assert "from app.oa_application_items item" in canonical_sql
    assert "from app.oa_attachments attachment" in canonical_sql
    assert "from app.oa_source_aliases alias_row" in canonical_sql


def test_canonical_spine_defers_supporting_documents_to_page_hydration() -> None:
    canonical_sql = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.split())

    assert "workbench_oa_supporting_documents" not in canonical_sql
    assert "normalized_payload->'expense_items'" in canonical_sql
    assert "source_payload->'expense_items'" in canonical_sql


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


def test_canonical_spine_rolls_source_owned_relation_placements_once() -> None:
    sql = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.split()).lower()
    rollup_sql = sql.split(
        "source_owned_relation_placement_rollups as materialized (", 1
    )[1].split("relation_groups as materialized (", 1)[0]
    relation_group_sql = sql.split(
        "relation_groups as materialized (", 1
    )[1].split("source_owned_unpaired_groups as materialized (", 1)[0]

    assert "group by placement.owner_relation_case_id" in rollup_sql
    assert "array_agg( placement.invoice_row_id order by placement.invoice_row_id )" in rollup_sql
    assert "array_agg( 'invoice'::text order by placement.invoice_row_id )" in rollup_sql
    assert "left join source_owned_relation_placement_rollups placement_rollup" in relation_group_sql
    assert "placement_rollup.invoice_row_ids" in relation_group_sql
    assert "placement_rollup.invoice_row_types" in relation_group_sql
    assert "select array_agg" not in relation_group_sql


def test_source_owner_resolution_precedes_group_filters_counts_and_cursor_limit() -> None:
    spine_sql = " ".join(_SCOPED_CANONICAL_GROUPS_CTE.split()).lower()

    owner_index = spine_sql.index("scoped_invoice_unique_owners as materialized")
    placement_index = spine_sql.index("source_owned_invoice_placements as materialized")
    source_group_index = spine_sql.index("source_owned_unpaired_groups as materialized")
    group_index = spine_sql.index("canonical_groups as materialized")
    member_index = spine_sql.index("canonical_group_members as materialized")
    assert owner_index < placement_index < source_group_index < group_index < member_index
    assert "or not exists ( select 1 from jsonb_array_elements(" in spine_sql
    assert "= 'oa_expense_item_invoice'" in spine_sql
    assert "having bool_and(resolution.resolved_oa_row_id is not null)" in spine_sql
    assert "count(distinct resolution.resolved_oa_row_id) = 1" in spine_sql
    assert "having count(distinct owner_relation.case_id) <= 1" in spine_sql
    assert "invoice_relation.row_type = 'invoice'" in spine_sql
    assert "source_owned_invoice_placements placement" in spine_sql
    assert "source.source_expense_item_id = item.current_item_id" in spine_sql
    assert "count(distinct item_identity.value)" in spine_sql
    assert "source_parent_oa_id" not in spine_sql
    assert "current_row_index" not in spine_sql
    assert "from app.oa_attachment_invoice_cache" not in spine_sql

    connection = _QueryConnection([])
    repository = PostgresWorkbenchPageQueryRepository(
        connection,
        tenant_id="test-tenant",
    )
    repository._groups_page(
        scope_key="2026-07",
        zone="unpaired",
        page_size=2,
    )
    page_sql = connection.sql.lower()
    assert page_sql.index("source_owned_unpaired_groups as materialized") < page_sql.index(
        "filtered_groups as materialized"
    )
    assert page_sql.index("filtered_groups as materialized") < page_sql.index(
        "page_groups as materialized"
    )
    assert page_sql.index("page_groups as materialized") < page_sql.rindex("limit %s")


def test_relation_anomaly_members_use_only_formal_relation_members() -> None:
    sql = " ".join(_ANOMALY_STATE_CTES.split()).lower()
    relation_members_sql = sql.split(
        "relation_anomaly_members as materialized (", 1
    )[1].split("oa_exact_identity_aliases as materialized (", 1)[0]

    assert "join all_active_relation_members member" in relation_members_sql
    assert "join canonical_group_members member" not in relation_members_sql
    assert "member.relation_id = relation.id" in relation_members_sql


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


def test_compact_etc_summary_builds_first_real_invoice_preview() -> None:
    summary = PostgresWorkbenchPageHydrationRepository._compact_etc_summary_row(
        row_id="etc-summary-ETC-68",
        external_batch_id="ETC-68",
        payload={
            "invoice_count": 68,
            "total_amount": "3740.82",
            "issue_date_min": "2026-05-28",
            "issue_date_max": "2026-06-28",
            "seller_name": "云南省交通投资建设集团有限公司",
            "first_invoice": {
                "row_id": "etc-invoice-1",
                "invoice_no": "26537912210500678556",
                "invoice_code": "032002300111",
                "invoice_date": "2026-05-28",
                "seller_name": "云南省交通投资建设集团有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "amount": "72.86",
                "tax_rate": "3%",
                "tax_amount": "2.19",
                "total_with_tax": "75.05",
                "invoice_type": "进项发票",
            },
        },
    )

    assert summary["etc_invoice_detail_count"] == 68
    assert summary["etc_invoice_detail_rows"] == [
        {
            "id": "etc-invoice-1",
            "type": "invoice",
            "source_kind": "etc_invoice",
            "status": "paired",
            "seller_tax_no": "ETC发票",
            "seller_name": "云南省交通投资建设集团有限公司",
            "buyer_tax_no": "ETC-68",
            "buyer_name": "云南溯源科技有限公司",
            "invoice_code": "032002300111",
            "invoice_no": "26537912210500678556",
            "digital_invoice_no": "26537912210500678556",
            "issue_date": "2026-05-28",
            "amount": "75.05",
            "amount_value": "75.05",
            "tax_rate": "3%",
            "tax_amount": "2.19",
            "total_with_tax": "75.05",
            "invoice_type": "进项发票",
            "tags": ["ETC", "ETC发票明细"],
            "etc_batch_id": "ETC-68",
            "invoice_bank_relation": {
                "code": "etc_batch_detail",
                "label": "ETC批次明细",
                "tone": "neutral",
            },
            "available_actions": ["detail"],
            "summary_fields": {
                "ETC批次": "ETC-68",
                "发票号码": "26537912210500678556",
                "销方": "云南省交通投资建设集团有限公司",
                "金额": "75.05",
                "开票日期": "2026-05-28",
            },
            "detail_fields": {
                "ETC批次": "ETC-68",
                "发票号码": "26537912210500678556",
                "销方": "云南省交通投资建设集团有限公司",
                "金额": "75.05",
                "开票日期": "2026-05-28",
            },
        }
    ]


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
    assert "from app.oa_application_items item" in connection.sql
    assert "from app.oa_attachments attachment" in connection.sql
    assert "from app.oa_source_aliases alias_row" in connection.sql
    assert "oa.normalized_payload->>'expense_type'" in connection.sql
    assert "admission.source_payload->>'expense_type'" in connection.sql
    assert connection.sql.count("'oa_expense_item_invoice'") >= 3
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


def test_oa_invoice_and_relation_details_use_one_target_bounded_set_query() -> None:
    connection = _CountingQueryConnection([])
    repository = PostgresWorkbenchPageQueryRepository(
        connection,
        tenant_id="test-tenant",
    )

    assert repository._row_group_descriptors(
        scope_key="2026-07",
        row_id="invoice-1",
        row_type="invoice",
    ) == []
    assert repository._relation_descriptor_for_case(
        scope_key="2026-07",
        case_id="CASE-1",
    ) == []

    assert len(connection.calls) == 2
    for sql, params in connection.calls:
        lowered = sql.lower()
        assert "requested_target as" in lowered
        assert "target_source_candidates as materialized" in lowered
        assert "target_relation_seeds as materialized" in lowered
        assert "target_owner_oa_ids as materialized" in lowered
        assert "target_owner_item_ids as materialized" in lowered
        assert "target_source_owned_invoice_months as materialized" in lowered
        assert "target_invoice_scope_months as materialized" in lowered
        assert lowered.index("target_source_owned_invoice_months as materialized") < lowered.index(
            "target_invoice_scope_months as materialized"
        )
        assert "scope.scope_key = 'all'" in lowered
        assert "target.case_id is not null" in lowered
        assert "count(distinct item_identity.value)" in lowered
        assert "scoped_invoice_facts as materialized" in lowered
        assert "invoice.invoice_month = invoice_scope.scope_month" in lowered
        assert "scope.scope_key = 'all' or invoice.invoice_month" not in lowered
        assert "source_owned_invoice_placements as materialized" in lowered
        assert "relation.row_ids as formal_member_ids" in lowered
        assert "relation.normalized_row_types as formal_member_types" in lowered
        assert "relation.version as relation_version" in lowered
        assert "scoped_source_keys" not in lowered
        assert "canonical_groups as materialized" not in lowered
        assert "canonical_group_members" not in lowered
        assert "oa_attachment_invoice_cache" not in lowered
        assert "limit 4" in lowered
        assert params[:4] == (
            "2026-07",
            "2026-07",
            "2026-07-01",
            "test-tenant",
        )


def test_source_owned_group_detail_accepts_oa_anchor_inside_multi_member_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail_key = "v1:2026-07:oa:" + "oa-owner".encode().hex()
    connection = _QueryConnection(
        [
            {
                "internal_key": "source-owned:oa:oa-owner",
                "detail_key": detail_key,
                "group_kind": "unpaired",
                "zone": "unpaired",
                "member_ids": ["oa-owner", "invoice-1"],
                "member_types": ["oa", "invoice"],
                "formal_member_ids": [],
                "formal_member_types": [],
                "scope_month": "2026-07-01",
            }
        ]
    )
    repository = PostgresWorkbenchPageQueryRepository(
        connection,
        tenant_id="test-tenant",
    )
    monkeypatch.setattr(
        repository,
        "_hydrate_groups",
        lambda **_kwargs: [
            {
                "group_id": "source-owned:oa:digest",
                "zone": "unpaired",
                "oa_rows": [{"id": "oa-owner", "type": "oa"}],
                "bank_rows": [],
                "invoice_rows": [{"id": "invoice-1", "type": "invoice"}],
            }
        ],
    )

    detail = repository._group_detail(
        scope_key="2026-07",
        zone="unpaired",
        group_id="source-owned:oa:digest",
        detail_key=detail_key,
    )

    assert detail is not None
    assert detail["group"]["invoice_rows"][0]["id"] == "invoice-1"
    assert "requested_target as" in connection.sql.lower()


def test_full_hydration_restores_source_owned_members_with_one_set_read() -> None:
    class _Hydration:
        calls: list[dict[str, set[str]]] = []

        def hydrate_rows(
            self,
            typed_row_ids: dict[str, set[str]],
        ) -> dict[tuple[str, str], dict[str, Any]]:
            self.calls.append(typed_row_ids)
            return {
                ("invoice", "invoice-1"): {
                    "id": "invoice-1",
                    "type": "invoice",
                    "object_identity_key": "invoice:1",
                    "status": "unpaired",
                }
            }

    descriptor = {
        "internal_key": "source-owned:oa:oa-owner",
        "detail_key": "v1:2026-07:oa:" + "oa-owner".encode().hex(),
        "group_kind": "unpaired",
        "member_ids": ["oa-owner", "invoice-1"],
        "member_types": ["oa", "invoice"],
    }
    owner_singleton = {
        "group_id": "unpaired:oa:old-digest",
        "group_type": "unpaired",
        "zone": "unpaired",
        "oa_rows": [
            {
                "id": "oa-owner",
                "type": "oa",
                "object_identity_key": "oa:owner",
                "status": "unpaired",
            }
        ],
        "bank_rows": [],
        "invoice_rows": [],
    }
    hydration = _Hydration()

    restored = PostgresWorkbenchPageQueryRepository._restore_descriptor_owned_members(
        descriptors=[descriptor],
        groups=[owner_singleton],
        hydration=hydration,  # type: ignore[arg-type]
    )

    assert hydration.calls == [
        {"oa": set(), "bank": set(), "invoice": {"invoice-1"}}
    ]
    assert restored[0]["group_id"].startswith("source-owned:oa:")
    assert restored[0]["reason"] == "oa_attachment_item_owner"
    assert restored[0]["row_counts"] == {
        "oa": 1,
        "bank": 0,
        "invoice": 1,
        "rows": 2,
    }
    assert restored[0]["invoice_rows"][0]["id"] == "invoice-1"
    assert owner_singleton["invoice_rows"] == []


def test_full_hydration_restores_relation_display_without_formal_state_pollution() -> None:
    class _Hydration:
        calls: list[dict[str, set[str]]] = []

        def hydrate_rows(
            self,
            typed_row_ids: dict[str, set[str]],
        ) -> dict[tuple[str, str], dict[str, Any]]:
            self.calls.append(typed_row_ids)
            return {
                ("invoice", "invoice-display"): {
                    "id": "invoice-display",
                    "type": "invoice",
                    "object_identity_key": "invoice:display",
                    "case_id": "stale-case",
                    "relation_mode": "stale-mode",
                    "relation_amount_check": {"status": "stale"},
                    "available_actions": ["confirm_relation", "withdraw"],
                }
            }

    descriptor = {
        "internal_key": "case:CASE-1",
        "detail_key": "CASE-1",
        "group_kind": "relation",
        "member_ids": ["oa-1", "bank-1", "invoice-display"],
        "member_types": ["oa", "bank", "invoice"],
        "formal_member_ids": ["oa-1", "bank-1"],
        "formal_member_types": ["oa", "bank"],
        "relation_version": 7,
    }
    relation_group = {
        "group_id": "case:CASE-1",
        "group_type": "relation",
        "zone": "unpaired",
        "status": "unpaired",
        "case_id": "CASE-1",
        "formal_member_ids": ["oa-1", "bank-1"],
        "formal_member_types": ["oa", "bank"],
        "completion": {
            "is_complete": False,
            "blocking_reasons": ["anomaly_review_required"],
        },
        "workbench_anomaly": {"fingerprint": "formal-only"},
        "can_withdraw": True,
        "oa_rows": [
            {
                "id": "oa-1",
                "type": "oa",
                "object_identity_key": "oa:1",
                "available_actions": ["detail", "withdraw"],
            }
        ],
        "bank_rows": [
            {
                "id": "bank-1",
                "type": "bank",
                "object_identity_key": "bank:1",
                "available_actions": ["detail", "withdraw"],
            }
        ],
        "invoice_rows": [],
    }
    hydration = _Hydration()

    restored = PostgresWorkbenchPageQueryRepository._restore_descriptor_owned_members(
        descriptors=[descriptor],
        groups=[relation_group],
        hydration=hydration,  # type: ignore[arg-type]
    )[0]

    assert hydration.calls == [
        {"oa": set(), "bank": set(), "invoice": {"invoice-display"}}
    ]
    assert restored["formal_member_ids"] == ["oa-1", "bank-1"]
    assert restored["formal_member_types"] == ["oa", "bank"]
    assert restored["relation_version"] == 7
    assert restored["completion"] == relation_group["completion"]
    assert restored["workbench_anomaly"] == relation_group["workbench_anomaly"]
    assert restored["can_withdraw"] is True
    assert restored["oa_rows"][0]["available_actions"] == ["detail", "withdraw"]
    assert restored["bank_rows"][0]["available_actions"] == ["detail", "withdraw"]
    assert restored["display_only_member_ids"] == ["invoice-display"]
    display = restored["invoice_rows"][0]
    assert display["workbench_membership_role"] == "source_owned_display"
    assert display["source_owner_case_id"] == "CASE-1"
    assert display["available_actions"] == ["detail"]
    assert "case_id" not in display
    assert "relation_mode" not in display
    assert "relation_amount_check" not in display
    assert relation_group["invoice_rows"] == []


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


def test_source_search_projection_matches_visible_grid_fields_only() -> None:
    search_ctes, _search_params, _hit_name = (
        PostgresWorkbenchPageQueryRepository._source_search_hit_ctes(
            prefix="visible_fields",
            search="张丽芬",
        )
    )
    normalized_sql = " ".join(search_ctes.split()).lower()

    for visible_expression in (
        "project_name_display",
        "detail_fields,申请类型",
        "expense_type",
        "counterparty_name",
        "detail_fields,往来单位",
        "fee_content",
        "fee_description",
        "pending.source_payload->>'counterparty_name'",
        "bank.counterparty_name_raw",
        "bank.trade_time",
        "bank.account_no",
        "invoice.seller_name",
        "invoice.seller_tax_no",
        "invoice.buyer_name",
        "invoice.buyer_tax_no",
        "invoice.tax_rate",
        "invoice.tax_amount",
    ):
        assert visible_expression.lower() in normalized_sql

    assert "oa.normalized_payload->>'workflow_no'" not in normalized_sql
    assert "bank.project_id" not in normalized_sql
    assert "invoice.counterparty_name" not in normalized_sql
    assert "source_payload::text" not in normalized_sql
    assert "normalized_payload::text" not in normalized_sql


def test_source_search_uses_canonical_invoice_source_labels_and_flow_aliases() -> None:
    oa_attachment_sql, _params, _hit_name = (
        PostgresWorkbenchPageQueryRepository._source_search_hit_ctes(
            prefix="oa_source_label",
            search="OA附件",
        )
    )
    manual_sql, _params, _hit_name = (
        PostgresWorkbenchPageQueryRepository._source_search_hit_ctes(
            prefix="manual_source_label",
            search="人工导入",
        )
    )
    input_sql, _params, _hit_name = (
        PostgresWorkbenchPageQueryRepository._source_search_hit_ctes(
            prefix="input_flow_label",
            search="进",
        )
    )

    assert "invoice.source_links" in oa_attachment_sql
    assert "oa_attachment_invoice" in oa_attachment_sql
    assert "invoice.raw_payload->'source_links'" not in oa_attachment_sql
    assert "manual_invoice_import" in manual_sql
    assert "not (exists" in " ".join(manual_sql.split()).lower()
    assert "purchase" in input_sql
    assert "invoice.invoice_type like '%%进%%'" in input_sql


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
                "application_type": "支付申请",
                "workflow_status": "completed",
                "applicant": "杨丽萍",
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
    projection_sql = applicant_connection.sql.split(
        "filtered_groups as materialized (", 1
    )[1]
    assert "distinct on (member.row_id)" not in projection_sql
    assert "order by member.row_id" not in projection_sql

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
    assert "groups.group_kind = 'relation'" in connection.sql
    assert "and groups.zone = 'paired'" in connection.sql
    assert connection.params[4] == "bank"


def test_oa_applicant_options_keep_unknown_workflow_and_empty_applicant() -> None:
    connection = _QueryConnection(
        [
            {
                "application_type": "差旅申请",
                "workflow_status": "returned",
                "applicant": WORKBENCH_FILTER_MISSING_VALUE,
            },
            {
                "application_type": "差旅申请",
                "workflow_status": "returned",
                "applicant": "--",
            },
            {
                "application_type": "差旅申请",
                "workflow_status": "returned",
                "applicant": "—",
            },
        ]
    )
    payload = PostgresWorkbenchPageQueryRepository(
        connection, tenant_id="test-tenant"
    )._filter_options(
        scope_key="all", zone="unpaired", pane="oa",
        facet="column", column="applicant",
    )

    options = {option["value"]: option for option in payload["options"]}
    assert options["oaType:差旅申请"]["label"] == "差旅申请"
    assert options["workflow:returned"]["label"] == "returned"
    assert options[f"applicant:{WORKBENCH_FILTER_MISSING_VALUE}"]["missing"] is True
    assert "applicant:--" not in options
    assert "applicant:—" not in options


def test_unpaired_exception_options_scan_both_relation_base_zones() -> None:
    connection = _QueryConnection(
        [{"facet_value": "云南供应商", "facet_label": "云南供应商"}]
    )
    PostgresWorkbenchPageQueryRepository(
        connection, tenant_id="test-tenant"
    )._filter_options(
        scope_key="all", zone="unpaired", pane="invoice",
        facet="column", column="sellerName", exception_bucket=" unpaired ",
    )

    candidate_sql = connection.sql.split(
        "filter_option_anomaly_groups as materialized (", 1
    )[1].split("latest_anomaly_decisions as materialized (", 1)[0]
    assert "groups.group_kind = 'relation'" in candidate_sql
    assert "groups.zone = 'paired'" not in candidate_sql


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
