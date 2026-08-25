from __future__ import annotations

from copy import deepcopy

import pytest

from fin_ops_platform.services.invoice_expense_item_link_repair_service import (
    build_invoice_expense_item_link_repair_plan,
    build_oa_attachment_invoice_link_audit_plan,
    public_invoice_expense_item_link_repair_report,
    public_oa_attachment_invoice_link_audit_report,
)
from fin_ops_platform.services.oa_attachment_invoice_linking import (
    canonical_oa_expense_item_ids,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    load_oa_attachment_invoice_link_audit_snapshot,
)
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


def _snapshot() -> list[dict[str, object]]:
    return [
        {
            "invoice_id": "invoice-1",
            "digital_invoice_no": "26537000000000000001",
            "total_with_tax": "859.57",
            "source_links": [{"source_type": "manual_invoice_import"}],
        },
        {
            "invoice_id": "invoice-2",
            "digital_invoice_no": "26537000000000000002",
            "total_with_tax": "1178.45",
            "source_links": [],
        },
    ]


def _plan(snapshot: list[dict[str, object]] | None = None) -> dict[str, object]:
    return build_invoice_expense_item_link_repair_plan(
        snapshot if snapshot is not None else _snapshot(),
        invoice_ids=["invoice-1", "invoice-2"],
        case_id="CASE-AUTO-0102",
        oa_row_id="oa-exp-1992",
        expense_item_id="oa-exp-1992:item:0:cceb2198c025",
        expected_total="2038.02",
    )


def test_build_invoice_expense_item_link_repair_plan_is_exact_and_auditable() -> None:
    plan = _plan()

    assert plan["target_count"] == 2
    assert plan["target_total"] == "2038.02"
    assert plan["update_count"] == 2
    assert len(plan["source_fingerprint"]) == 64
    added_link = plan["updates"][0]["source_links"][-1]
    assert added_link == {
        "source_type": "oa_expense_item_invoice",
        "source_workbench_row_id": "oa-exp-1992",
        "derived_from_oa_id": "oa-exp-1992",
        "source_expense_item_id": "oa-exp-1992:item:0:cceb2198c025",
        "source_relation_case_id": "CASE-AUTO-0102",
        "entry_method": "historical_repair",
    }
    report = public_invoice_expense_item_link_repair_report(
        plan,
        mode="dry_run",
        written=False,
    )
    assert report["authorized_write_scope"] == ["app.invoices", "audit.events"]
    assert "rollback_manifest" not in report
    assert report["rollback_manifest_fingerprint"] == plan[
        "rollback_manifest_fingerprint"
    ]
    assert report["rollback_restore_count"] == 2
    assert "oa-exp-1992" not in str(report)
    assert "CASE-AUTO-0102" not in str(report)


def test_build_invoice_expense_item_link_repair_plan_rejects_wrong_total() -> None:
    with pytest.raises(ValueError, match="authorized total"):
        build_invoice_expense_item_link_repair_plan(
            _snapshot(),
            invoice_ids=["invoice-1", "invoice-2"],
            case_id="CASE-AUTO-0102",
            oa_row_id="oa-exp-1992",
            expense_item_id="oa-exp-1992:item:0:cceb2198c025",
            expected_total="2038.03",
        )


def test_build_invoice_expense_item_link_repair_plan_rejects_conflicting_link() -> None:
    snapshot = _snapshot()
    snapshot[0]["source_links"] = [
        {
            "source_type": "oa_expense_item_invoice",
            "derived_from_oa_id": "oa-other",
            "source_expense_item_id": "oa-other:item:0",
        }
    ]

    with pytest.raises(ValueError, match="conflicting"):
        _plan(snapshot)


def test_build_invoice_expense_item_link_repair_plan_is_idempotent() -> None:
    first_plan = _plan()
    snapshot = _snapshot()
    for row in snapshot:
        update = next(
            item for item in first_plan["updates"] if item["invoice_id"] == row["invoice_id"]
        )
        row["source_links"] = update["source_links"]

    assert _plan(snapshot)["update_count"] == 0


def _oa_attachment_audit_row(
    *,
    invoice_id: str,
    source_oa_row_id: str = "oa-exp-old",
    source_expense_item_id: str = "oa-exp-old:item:1:old",
    direct_target: tuple[str, str] | None = None,
    candidates: list[tuple[str, str]] | None = None,
    explicit_targets: list[tuple[str, str]] | None = None,
    workbench_visibility: str = "visible",
    source_parent_is_active: bool = False,
    source_parent_canonical_oa_row_id: str | None = None,
) -> dict[str, object]:
    source_links: list[dict[str, object]] = [
        {
            "source_type": "oa_attachment_invoice",
            "derived_from_oa_id": source_oa_row_id,
            "source_expense_item_id": source_expense_item_id,
            "source_attachment_key": f"legacy-{invoice_id}",
        }
    ]
    explicit_edges = []
    for oa_row_id, expense_item_id in explicit_targets or []:
        source_links.append(
            {
                "source_type": "oa_expense_item_invoice",
                "source_workbench_row_id": oa_row_id,
                "derived_from_oa_id": oa_row_id,
                "source_expense_item_id": expense_item_id,
                "entry_method": "verified_attachment_identity_repair",
            }
        )
        explicit_edges.append(
            {
                "oa_row_id": oa_row_id,
                "canonical_oa_row_id": oa_row_id,
                "expense_item_id": expense_item_id,
                "is_current_owner": True,
            }
        )
    normalized_source_oa_row_id = source_oa_row_id.split(":item:", 1)[0]
    attachment_edge = {
        "source_oa_row_id": normalized_source_oa_row_id,
        "source_oa_row_id_hash": "parent-hash-redacted",
        "source_expense_item_id": source_expense_item_id,
        "source_attachment_key_hash": "attachment-key-hash-redacted",
        "source_parent_is_active": source_parent_is_active,
        "source_parent_canonical_oa_row_id": source_parent_canonical_oa_row_id,
        "oa_row_id": direct_target[0] if direct_target else None,
        "canonical_oa_row_id": direct_target[0] if direct_target else None,
        "expense_item_id": direct_target[1] if direct_target else None,
        "is_current_owner": direct_target is not None,
    }
    return {
        "invoice_id": invoice_id,
        "workbench_visibility": workbench_visibility,
        "source_links": source_links,
        "invoice_identity_hash": "invoice-identity-hash-redacted",
        "attachment_edges": [attachment_edge],
        "explicit_edges": explicit_edges,
        "strong_candidates": [
            {
                "oa_row_id": oa_row_id,
                "canonical_oa_row_id": oa_row_id,
                "expense_item_id": expense_item_id,
                "attachment_key_hashes": [f"current-{index}"],
            }
            for index, (oa_row_id, expense_item_id) in enumerate(candidates or [])
        ],
    }


def test_full_oa_attachment_audit_repairs_unique_oa_target_set_without_case_fact() -> None:
    snapshot = [
        _oa_attachment_audit_row(
            invoice_id="invoice-1",
            candidates=[
                ("oa-exp-current", "oa-exp-current:item:0:a"),
                ("oa-exp-current", "oa-exp-current:item:1:b"),
            ],
        ),
        _oa_attachment_audit_row(
            invoice_id="invoice-2",
            source_oa_row_id="oa-exp-current",
            source_expense_item_id="oa-exp-current:item:0:a",
            direct_target=("oa-exp-current", "oa-exp-current:item:0:a"),
            candidates=[("oa-exp-current", "oa-exp-current:item:0:a")],
        ),
    ]

    plan = build_oa_attachment_invoice_link_audit_plan(snapshot)

    assert plan["audited_invoice_count"] == 2
    assert plan["attachment_edge_count"] == 2
    assert plan["classification_counts"]["repairable"] == 1
    assert plan["classification_counts"]["valid_attachment_owner"] == 1
    assert plan["update_count"] == 1
    repaired_links = plan["updates"][0]["source_links"]
    assert repaired_links[0] == snapshot[0]["source_links"][0]
    assert [link["source_expense_item_id"] for link in repaired_links[1:]] == [
        "oa-exp-current:item:0:a",
        "oa-exp-current:item:1:b",
    ]
    assert all("source_relation_case_id" not in link for link in repaired_links[1:])
    assert canonical_oa_expense_item_ids(
        oa_row={
            "id": "oa-exp-current",
            "expense_items": [
                {"id": "oa-exp-current:item:0:a", "row_index": "0"},
                {"id": "oa-exp-current:item:1:b", "row_index": "1"},
            ],
        },
        invoice_row={"source_links": repaired_links},
    ) == ["oa-exp-current:item:0:a", "oa-exp-current:item:1:b"]
    assert plan["rollback_manifest"]["restore_invoice_source_links"] == [
        {"invoice_id": "invoice-1", "source_links": snapshot[0]["source_links"]}
    ]

    repaired_snapshot = [dict(snapshot[0])]
    repaired_snapshot[0]["source_links"] = repaired_links
    repaired_snapshot[0]["explicit_edges"] = [
        {
            "oa_row_id": link["derived_from_oa_id"],
            "expense_item_id": link["source_expense_item_id"],
            "is_current_owner": True,
        }
        for link in repaired_links[1:]
    ]
    repaired_plan = build_oa_attachment_invoice_link_audit_plan(repaired_snapshot)
    assert repaired_plan["classification_counts"]["valid_explicit"] == 1
    assert repaired_plan["update_count"] == 0


def test_full_oa_attachment_audit_does_not_write_ambiguous_or_conflicting_owners() -> None:
    ambiguous = _oa_attachment_audit_row(
        invoice_id="invoice-ambiguous",
        candidates=[
            ("oa-exp-a", "oa-exp-a:item:0"),
            ("oa-exp-b", "oa-exp-b:item:0"),
        ],
    )
    conflicting = _oa_attachment_audit_row(
        invoice_id="invoice-conflict",
        candidates=[("oa-exp-a", "oa-exp-a:item:0")],
        explicit_targets=[("oa-exp-a", "oa-exp-a:item:1")],
    )

    plan = build_oa_attachment_invoice_link_audit_plan([ambiguous, conflicting])

    assert plan["classification_counts"]["ambiguous"] == 1
    assert plan["classification_counts"]["conflict"] == 1
    assert plan["update_count"] == 0
    assert plan["rollback_manifest"]["restore_invoice_source_links"] == []


def test_full_oa_attachment_audit_completes_same_oa_explicit_candidate_subset() -> None:
    snapshot = [
        _oa_attachment_audit_row(
            invoice_id="invoice-partial-explicit",
            candidates=[
                ("oa-exp-a", "oa-exp-a:item:0"),
                ("oa-exp-a", "oa-exp-a:item:1"),
            ],
            explicit_targets=[("oa-exp-a", "oa-exp-a:item:0")],
        )
    ]

    plan = build_oa_attachment_invoice_link_audit_plan(snapshot)

    assert plan["classification_counts"]["repairable"] == 1
    assert plan["update_count"] == 1
    assert {
        link["source_expense_item_id"]
        for link in plan["updates"][0]["source_links"]
        if link["source_type"] == "oa_expense_item_invoice"
    } == {"oa-exp-a:item:0", "oa-exp-a:item:1"}


def test_full_oa_attachment_audit_appends_missing_target_without_rewriting_existing_edge() -> None:
    row = _oa_attachment_audit_row(
        invoice_id="invoice-partial-provenance",
        candidates=[
            ("oa-exp-a", "oa-exp-a:item:0"),
            ("oa-exp-a", "oa-exp-a:item:1"),
        ],
        explicit_targets=[("oa-exp-a", "oa-exp-a:item:0")],
    )
    existing_link = row["source_links"][1]
    existing_link["source_relation_case_id"] = "CASE-MANUAL-001"
    existing_link["entry_method"] = "manual_confirm"
    existing_link["audit_context"] = {
        "operator_id": "operator-1",
        "confirmed_at": "2026-08-24T12:00:00+08:00",
    }
    before_source_links = deepcopy(row["source_links"])

    first = build_oa_attachment_invoice_link_audit_plan([row])

    repaired_links = first["updates"][0]["source_links"]
    assert repaired_links[: len(before_source_links)] == before_source_links
    appended_link = repaired_links[-1]
    assert appended_link == {
        "source_type": "oa_expense_item_invoice",
        "source_workbench_row_id": "oa-exp-a",
        "derived_from_oa_id": "oa-exp-a",
        "source_expense_item_id": "oa-exp-a:item:1",
        "entry_method": "verified_attachment_identity_repair",
    }

    rerun_row = dict(row)
    rerun_row["source_links"] = repaired_links
    rerun_row["explicit_edges"] = [
        {
            "oa_row_id": "oa-exp-a",
            "expense_item_id": "oa-exp-a:item:0",
            "is_current_owner": True,
        },
        {
            "oa_row_id": "oa-exp-a",
            "expense_item_id": "oa-exp-a:item:1",
            "is_current_owner": True,
        },
    ]
    second = build_oa_attachment_invoice_link_audit_plan([rerun_row])

    assert second["classification_counts"]["valid_explicit"] == 1
    assert second["update_count"] == 0


def test_full_oa_attachment_audit_requires_set_overlap_even_within_same_oa() -> None:
    direct_subset = _oa_attachment_audit_row(
        invoice_id="invoice-direct-subset",
        source_oa_row_id="oa-exp-a",
        source_expense_item_id="oa-exp-a:item:0",
        direct_target=("oa-exp-a", "oa-exp-a:item:0"),
        candidates=[
            ("oa-exp-a", "oa-exp-a:item:0"),
            ("oa-exp-a", "oa-exp-a:item:1"),
        ],
    )
    disjoint = _oa_attachment_audit_row(
        invoice_id="invoice-direct-disjoint",
        source_oa_row_id="oa-exp-a",
        source_expense_item_id="oa-exp-a:item:0",
        direct_target=("oa-exp-a", "oa-exp-a:item:0"),
        candidates=[("oa-exp-a", "oa-exp-a:item:1")],
    )

    plan = build_oa_attachment_invoice_link_audit_plan([direct_subset, disjoint])

    assert plan["classification_counts"]["repairable"] == 1
    assert plan["classification_counts"]["conflict"] == 1
    assert plan["update_count"] == 1


def test_full_oa_attachment_audit_never_moves_invoice_from_different_active_parent() -> None:
    row = _oa_attachment_audit_row(
        invoice_id="invoice-active-parent-conflict",
        source_oa_row_id="oa-exp-active-a:item:legacy-parent",
        source_expense_item_id="oa-exp-active-a:item:legacy",
        source_parent_is_active=True,
        source_parent_canonical_oa_row_id="oa-exp-active-a",
        candidates=[("oa-exp-current-b", "oa-exp-current-b:item:0")],
    )

    plan = build_oa_attachment_invoice_link_audit_plan([row])

    assert plan["classification_counts"]["conflict"] == 1
    assert plan["update_count"] == 0
    assert plan["rollback_manifest"]["restore_invoice_source_links"] == []


def test_full_oa_attachment_audit_accepts_active_parent_alias_to_candidate() -> None:
    row = _oa_attachment_audit_row(
        invoice_id="invoice-active-parent-alias",
        source_oa_row_id="oa-exp-historical-alias:item:legacy-parent",
        source_expense_item_id="oa-exp-historical-alias:item:legacy",
        source_parent_is_active=True,
        source_parent_canonical_oa_row_id="oa-exp-current",
        candidates=[("oa-exp-current", "oa-exp-current:item:0")],
    )

    plan = build_oa_attachment_invoice_link_audit_plan([row])

    assert plan["classification_counts"]["repairable"] == 1
    assert plan["update_count"] == 1
    assert plan["updates"][0]["source_links"][-1]["derived_from_oa_id"] == "oa-exp-current"


def test_full_oa_attachment_audit_marks_explicit_owner_against_active_parent_as_conflict() -> None:
    row = _oa_attachment_audit_row(
        invoice_id="invoice-explicit-active-parent-conflict",
        source_oa_row_id="oa-exp-active-a:item:legacy-parent",
        source_expense_item_id="oa-exp-active-a:item:legacy",
        source_parent_is_active=True,
        source_parent_canonical_oa_row_id="oa-exp-active-a",
        candidates=[("oa-exp-current-b", "oa-exp-current-b:item:0")],
        explicit_targets=[("oa-exp-current-b", "oa-exp-current-b:item:0")],
    )

    plan = build_oa_attachment_invoice_link_audit_plan([row])

    assert plan["classification_counts"]["conflict"] == 1
    assert plan["classification_counts"]["valid_explicit"] == 0
    assert plan["update_count"] == 0


def test_full_oa_attachment_audit_scans_but_never_repairs_hidden_duplicate() -> None:
    hidden = _oa_attachment_audit_row(
        invoice_id="invoice-hidden-duplicate",
        candidates=[("oa-exp-a", "oa-exp-a:item:0")],
        workbench_visibility="hidden",
    )

    plan = build_oa_attachment_invoice_link_audit_plan([hidden])

    assert plan["audited_invoice_count"] == 1
    assert plan["classification_counts"]["protected_noncanonical"] == 1
    assert plan["update_count"] == 0
    report = public_oa_attachment_invoice_link_audit_report(
        plan,
        mode="dry_run",
        written=False,
    )
    assert report["write_scope"] == "visible_canonical_invoices_only"
    assert report["findings"][0]["classification"] == "protected_noncanonical"


def test_full_oa_attachment_audit_keeps_hidden_active_parent_conflict_protected() -> None:
    hidden = _oa_attachment_audit_row(
        invoice_id="invoice-hidden-parent-conflict",
        source_oa_row_id="oa-exp-active-a",
        source_expense_item_id="oa-exp-active-a:item:0",
        candidates=[("oa-exp-b", "oa-exp-b:item:0")],
        workbench_visibility="hidden",
        source_parent_is_active=True,
        source_parent_canonical_oa_row_id="oa-exp-active-a",
    )

    plan = build_oa_attachment_invoice_link_audit_plan([hidden])

    assert plan["classification_counts"]["protected_noncanonical"] == 1
    assert plan["classification_counts"]["conflict"] == 0
    assert plan["update_count"] == 0


def test_full_oa_attachment_audit_is_idempotent_and_preserves_attachment_provenance() -> None:
    snapshot = [
        _oa_attachment_audit_row(
            invoice_id="invoice-1",
            candidates=[("oa-exp-current", "oa-exp-current:item:0")],
        )
    ]
    first = build_oa_attachment_invoice_link_audit_plan(snapshot)
    next_snapshot = [dict(snapshot[0])]
    next_snapshot[0]["source_links"] = first["updates"][0]["source_links"]
    next_snapshot[0]["explicit_edges"] = [
        {
            "oa_row_id": "oa-exp-current",
            "expense_item_id": "oa-exp-current:item:0",
            "is_current_owner": True,
        }
    ]

    second = build_oa_attachment_invoice_link_audit_plan(next_snapshot)

    assert second["classification_counts"]["valid_explicit"] == 1
    assert second["update_count"] == 0
    assert next_snapshot[0]["source_links"][0]["source_type"] == "oa_attachment_invoice"


def test_full_oa_attachment_audit_public_report_exposes_findings_without_raw_lineage_keys() -> None:
    plan = build_oa_attachment_invoice_link_audit_plan(
        [_oa_attachment_audit_row(invoice_id="invoice-unresolved")]
    )

    report = public_oa_attachment_invoice_link_audit_report(
        plan,
        mode="dry_run",
        written=False,
    )

    assert report["authorized_write_scope"] == ["app.invoices", "audit.events"]
    assert report["findings"][0]["classification"] == "unresolved"
    assert "legacy-invoice-unresolved" not in str(report["findings"])
    assert "oa-exp-old" not in str(report)
    assert "oa-exp-old:item:1:old" not in str(report)
    assert "invoice-unresolved" not in str(report)
    assert "rollback_manifest" not in report
    assert report["rollback_manifest_fingerprint"] == plan[
        "rollback_manifest_fingerprint"
    ]
    assert report["rollback_restore_count"] == 0


def test_full_oa_attachment_audit_snapshot_is_one_set_based_query() -> None:
    class Connection:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
            self.calls.append((sql, params))
            return [{"invoice_id": "invoice-1"}]

    connection = Connection()

    assert load_oa_attachment_invoice_link_audit_snapshot(connection) == [
        {"invoice_id": "invoice-1"}
    ]
    assert len(connection.calls) == 1
    sql, params = connection.calls[0]
    assert params == ()
    assert "from app.invoices invoice" in sql
    assert "from app.oa_application_items item" in sql
    assert "join app.oa_attachments attachment" in sql
    assert "current_owned_evidence as materialized" in sql
    assert "split_part(source_parent.raw_source_oa_row_id, ':item:', 1)" in sql
    assert "source_link.value->>'source_expense_item_id' like '%%:item:%%'" in sql
    assert "candidate_alias.alias_row_id = application.row_id" in sql
    assert "candidate_alias.id is null" in sql
    assert "oa_attachment_invoice_cache" not in sql


def test_full_oa_attachment_audit_derives_parent_from_legacy_expense_item_only() -> None:
    database_url = require_postgres_test_database_url()
    apply_test_migrations(database_url)
    truncate_test_database(database_url)
    connection = PostgresConnection(
        PostgresSettings(database_url=database_url, pool_enabled=False)
    )
    try:
        connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, row_id, status, scope_month
            ) values
                ('source-parent-a', 'form-parent-a', 'oa-parent-a', 'completed', '2026-06-01'),
                ('source-parent-b', 'form-parent-b', 'oa-parent-b', 'completed', '2026-06-01')
            """
        )
        connection.execute(
            """
            insert into app.oa_application_items(
                oa_application_id, oa_source_id, form_id, row_id, normalized_payload
            )
            select id, oa_source_id, form_id, 'oa-parent-a:item:0',
                   jsonb_build_object(
                       'attachment_invoices', jsonb_build_array(jsonb_build_object(
                           'digital_invoice_no', '26534000000060092901',
                           'source_attachment_key', 'parent-attachment-a'
                       ))
                   )
            from app.oa_applications where row_id = 'oa-parent-a'
            union all
            select id, oa_source_id, form_id, 'oa-parent-b:item:0',
                   jsonb_build_object(
                       'attachment_invoices', jsonb_build_array(jsonb_build_object(
                           'digital_invoice_no', '26534000000060092902',
                           'source_attachment_key', 'parent-attachment-b'
                       ))
                   )
            from app.oa_applications where row_id = 'oa-parent-b'
            """
        )
        connection.execute(
            """
            insert into app.oa_attachments(
                oa_application_id, oa_source_id, form_id, row_id,
                source_attachment_key, filename, normalized_payload
            )
            select app.id, app.oa_source_id, app.form_id, item.row_id,
                   case app.row_id
                       when 'oa-parent-a' then 'parent-attachment-a'
                       else 'parent-attachment-b'
                   end,
                   'invoice.pdf',
                   jsonb_build_object('source_expense_item_id', item.row_id)
            from app.oa_applications app
            join app.oa_application_items item on item.oa_application_id = app.id
            """
        )
        connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                source_unique_key, amount, signed_amount, status,
                source_links, raw_payload
            ) values
                (
                    'invoice-parentless-same', 'input', '26534000000060092901',
                    '26534000000060092901', '26534000000060092901',
                    100, 100, 'pending',
                    '[{"source_type":"oa_attachment_invoice",'
                    '"source_expense_item_id":"oa-parent-a:item:0",'
                    '"source_attachment_key":"parent-attachment-a"}]'::jsonb,
                    '{}'::jsonb
                ),
                (
                    'invoice-parentless-cross', 'input', '26534000000060092902',
                    '26534000000060092902', '26534000000060092902',
                    200, 200, 'pending',
                    '[{"source_type":"oa_attachment_invoice",'
                    '"source_expense_item_id":"oa-parent-a:item:0",'
                    '"source_attachment_key":"parent-attachment-b"}]'::jsonb,
                    '{}'::jsonb
                )
            """
        )

        snapshot = load_oa_attachment_invoice_link_audit_snapshot(connection)
    finally:
        connection.close()

    rows_by_id = {row["invoice_id"]: row for row in snapshot}
    for invoice_id in ("invoice-parentless-same", "invoice-parentless-cross"):
        edge = rows_by_id[invoice_id]["attachment_edges"][0]
        assert edge["source_oa_row_id"] == "oa-parent-a"
        assert edge["source_parent_is_active"] is True
        assert edge["source_parent_canonical_oa_row_id"] == "oa-parent-a"

    plan = build_oa_attachment_invoice_link_audit_plan(snapshot)
    assert plan["classification_counts"]["valid_attachment_owner"] == 1
    assert plan["classification_counts"]["conflict"] == 1
    assert plan["update_count"] == 0
