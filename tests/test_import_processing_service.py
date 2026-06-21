from __future__ import annotations

from types import SimpleNamespace

from fin_ops_platform.services.import_processing_service import ImportProcessingService


def test_general_import_confirm_passes_bank_detail_scope_keys_to_persist_state() -> None:
    persisted: list[dict[str, object]] = []
    preview = SimpleNamespace(row_results=[], normalized_rows=[{"trade_time": "2026-06-02 10:00:00"}])
    service = ImportProcessingService(
        import_service=SimpleNamespace(confirm_import=lambda _batch_id: {"id": "batch-1"}, get_batch=lambda _batch_id: preview),
        file_import_service=SimpleNamespace(),
        tax_certified_import_service=SimpleNamespace(),
        etc_service=SimpleNamespace(),
        etc_reconciliation_task_service=SimpleNamespace(),
        background_job_service=SimpleNamespace(),
        serialize_value=lambda value: value,
        execute_derived_data_lifecycle_event=lambda *args, **kwargs: None,
        schedule_or_run_workbench_auto_matching_for_scopes=lambda *args, **kwargs: None,
        enqueue_workbench_auto_matching_for_scopes=lambda *args, **kwargs: None,
        persist_state_with_workbench_invalidation=lambda **kwargs: persisted.append(dict(kwargs)),
        invalidate_tax_offset_read_model_scopes=lambda *args, **kwargs: None,
        workbench_matching_scope_months_for_import_preview=lambda _preview: ["2026-06"],
        workbench_matching_scope_months_for_import_file_session=lambda _session, _selected_file_ids: [],
        tax_offset_scope_keys_for_import_preview=lambda _preview: [],
        tax_offset_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        cost_statistics_scope_keys_for_import_preview=lambda _preview: ["2026-06"],
        cost_statistics_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        bank_detail_scope_keys_for_import_preview=lambda _preview: ["2026-06"],
        bank_detail_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        input_invoice_usage_scope_keys_for_import_preview=lambda _preview: ["2026-06"],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_preview=lambda _preview: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: [],
        refresh_after_etc_invoice_link=lambda *args, **kwargs: None,
    )

    service.execute_general_import_confirm("batch-1")

    assert persisted == [
        {
            "cost_statistics_scope_keys": ["2026-06"],
            "bank_detail_scope_keys": ["2026-06"],
            "input_invoice_usage_scope_keys": ["2026-06"],
            "output_invoice_collection_scope_keys": [],
        }
    ]


def test_general_invoice_import_confirm_uses_bulk_read_model_invalidations_once() -> None:
    calls: list[tuple[str, object, str | None]] = []
    preview = SimpleNamespace(
        row_results=[SimpleNamespace(), SimpleNamespace(), SimpleNamespace()],
        normalized_rows=[
            {"invoice_date": "2026-04-01"},
            {"invoice_date": "2026-04-15"},
            {"invoice_date": "2026-05-03"},
        ],
    )
    service = ImportProcessingService(
        import_service=SimpleNamespace(confirm_import=lambda _batch_id: {"id": "batch-1"}, get_batch=lambda _batch_id: preview),
        file_import_service=SimpleNamespace(),
        tax_certified_import_service=SimpleNamespace(),
        etc_service=SimpleNamespace(),
        etc_reconciliation_task_service=SimpleNamespace(),
        background_job_service=SimpleNamespace(),
        serialize_value=lambda value: value,
        execute_derived_data_lifecycle_event=lambda *args, **kwargs: None,
        schedule_or_run_workbench_auto_matching_for_scopes=lambda scopes, **kwargs: calls.append(("matching", list(scopes), kwargs.get("reason"))),
        enqueue_workbench_auto_matching_for_scopes=lambda *args, **kwargs: None,
        persist_state_with_workbench_invalidation=lambda **kwargs: calls.append(("persist", dict(kwargs), None)),
        invalidate_tax_offset_read_model_scopes=lambda scopes, **kwargs: calls.append(("tax_offset", list(scopes), kwargs.get("reason"))),
        workbench_matching_scope_months_for_import_preview=lambda _preview: ["2026-04", "2026-05"],
        workbench_matching_scope_months_for_import_file_session=lambda _session, _selected_file_ids: [],
        tax_offset_scope_keys_for_import_preview=lambda _preview: ["2026-04", "2026-05"],
        tax_offset_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        cost_statistics_scope_keys_for_import_preview=lambda _preview: ["2026-04", "2026-05"],
        cost_statistics_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        bank_detail_scope_keys_for_import_preview=lambda _preview: [],
        bank_detail_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        input_invoice_usage_scope_keys_for_import_preview=lambda _preview: ["2026-04", "2026-05"],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_preview=lambda _preview: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: [],
        refresh_after_etc_invoice_link=lambda *args, **kwargs: None,
    )

    service.execute_general_import_confirm("batch-1")

    assert calls == [
        ("tax_offset", ["2026-04", "2026-05"], "invoice_import_confirm"),
        ("matching", ["2026-04", "2026-05"], "import_confirm"),
        (
            "persist",
            {
                "cost_statistics_scope_keys": ["2026-04", "2026-05"],
                "bank_detail_scope_keys": [],
                "input_invoice_usage_scope_keys": ["2026-04", "2026-05"],
                "output_invoice_collection_scope_keys": [],
            },
            None,
        ),
    ]
