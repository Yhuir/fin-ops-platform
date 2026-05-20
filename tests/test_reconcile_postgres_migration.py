from __future__ import annotations

from fin_ops_platform.tools.reconcile_postgres_migration import mapping_mismatches, markdown_report


def test_markdown_report_lists_core_mismatch() -> None:
    report = {
        "status": "blocked",
        "generated_at": "2026-05-20T00:00:00+00:00",
        "export_id": "export-1",
        "source_database": "fin_ops_platform_app",
        "manifest_sha256": "sha",
        "manifest_total_records": 1,
        "source_counts": {"invoices": 1},
        "target_counts": {"app.invoices": 0},
        "mismatches": [{"kind": "core_count_mismatch", "source_collection": "invoices"}],
    }

    rendered = markdown_report(report)

    assert "Stage 04 Reconciliation" in rendered
    assert "core_count_mismatch" in rendered


def test_stale_id_mappings_from_previous_exports_do_not_block_reconcile() -> None:
    mismatches = mapping_mismatches(
        {
            "total_mappings": 16217,
            "current_export_mappings": 12803,
            "stale_mappings": 3414,
            "conflicting_mappings": 0,
        }
    )

    assert mismatches == []


def test_conflicting_id_mappings_still_block_reconcile() -> None:
    mismatches = mapping_mismatches(
        {
            "total_mappings": 10,
            "current_export_mappings": 9,
            "stale_mappings": 1,
            "conflicting_mappings": 1,
        }
    )

    assert mismatches == [{"kind": "id_mapping_conflicts", "actual": 1}]
