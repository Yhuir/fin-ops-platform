from __future__ import annotations

from types import SimpleNamespace

from fin_ops_platform.services.import_processing_service import ImportProcessingService


def test_general_import_confirm_uses_direct_bank_detail_without_refresh_scope() -> None:
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
        input_invoice_usage_scope_keys_for_import_preview=lambda _preview: ["2026-06"],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_preview=lambda _preview: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: [],
        refresh_after_etc_invoice_link=lambda *args, **kwargs: None,
    )

    result = service.execute_general_import_confirm("batch-1")

    assert persisted == [
        {
            "cost_statistics_scope_keys": ["2026-06"],
            "input_invoice_usage_scope_keys": ["2026-06"],
            "output_invoice_collection_scope_keys": [],
        }
    ]
    assert "2026-06" in result["affected_scope_keys"]
    assert "active:2026-06" in result["affected_scope_keys"]
    assert "all:2026-06" in result["affected_scope_keys"]
    assert "read_model_scope_keys" not in result
    assert "operation_barrier_targets" not in result
    assert "freshness_targets" not in result


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
        input_invoice_usage_scope_keys_for_import_preview=lambda _preview: ["2026-04", "2026-05"],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_preview=lambda _preview: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: [],
        refresh_after_etc_invoice_link=lambda *args, **kwargs: None,
    )

    result = service.execute_general_import_confirm("batch-1")

    assert calls == [
        ("tax_offset", ["2026-04", "2026-05"], "invoice_import_confirm"),
        ("matching", ["2026-04", "2026-05"], "import_confirm"),
        (
            "persist",
            {
                "cost_statistics_scope_keys": ["2026-04", "2026-05"],
                "input_invoice_usage_scope_keys": ["2026-04", "2026-05"],
                "output_invoice_collection_scope_keys": [],
            },
            None,
        ),
    ]
    assert "2026-04" in result["affected_scope_keys"]
    assert "2026-05" in result["affected_scope_keys"]
    assert "read_model_scope_keys" not in result
    assert "operation_barrier_targets" not in result
    assert "freshness_targets" not in result


def test_file_import_confirm_job_returns_import_write_targets() -> None:
    confirmed_session = SimpleNamespace(
        id="session-1",
        files=[
            SimpleNamespace(
                id="file-bank",
                status="confirmed",
                batch_type="bank_transaction",
                normalized_rows=[{"trade_time": "2026-06-02 10:00:00", "account_no": "6222"}],
            )
        ],
    )
    service = ImportProcessingService(
        import_service=SimpleNamespace(),
        file_import_service=SimpleNamespace(
            get_session=lambda _session_id: confirmed_session,
            confirm_session=lambda **_kwargs: confirmed_session,
        ),
        tax_certified_import_service=SimpleNamespace(),
        etc_service=SimpleNamespace(),
        etc_reconciliation_task_service=SimpleNamespace(),
        background_job_service=SimpleNamespace(),
        serialize_value=lambda value: value,
        execute_derived_data_lifecycle_event=lambda *args, **kwargs: None,
        schedule_or_run_workbench_auto_matching_for_scopes=lambda *args, **kwargs: None,
        enqueue_workbench_auto_matching_for_scopes=lambda *args, **kwargs: None,
        persist_state_with_workbench_invalidation=lambda **kwargs: None,
        invalidate_tax_offset_read_model_scopes=lambda *args, **kwargs: None,
        workbench_matching_scope_months_for_import_preview=lambda _preview: [],
        workbench_matching_scope_months_for_import_file_session=lambda _session, _selected_file_ids: ["2026-06"],
        tax_offset_scope_keys_for_import_preview=lambda _preview: [],
        tax_offset_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        cost_statistics_scope_keys_for_import_preview=lambda _preview: [],
        cost_statistics_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: ["2026-06"],
        input_invoice_usage_scope_keys_for_import_preview=lambda _preview: [],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_preview=lambda _preview: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: [],
        refresh_after_etc_invoice_link=lambda *args, **kwargs: None,
    )

    result = service.execute_file_import_confirm_job(
        session_id="session-1",
        selected_file_ids=["file-bank"],
        owner_user_id="user",
        background_job_id="",
    )

    assert result["affected_months"] == ["2026-06"]
    assert "2026-06" in result["affected_scope_keys"]
    assert "active:2026-06" in result["affected_scope_keys"]
    assert "all:2026-06" in result["affected_scope_keys"]
    assert "read_model_scope_keys" not in result
    assert "operation_barrier_targets" not in result
    assert "freshness_targets" not in result


def test_etc_invoice_import_confirm_job_returns_targets_after_changed_months_are_known() -> None:
    refresh_calls: list[tuple[list[str], str]] = []
    imported_marks: list[dict[str, object]] = []
    business_batch = SimpleNamespace(
        business_batch_id="business-1",
        import_batch_ids=["batch-etc-1"],
        version=3,
        is_active=True,
    )
    import_result = SimpleNamespace(imported=2, attachments_completed=1, duplicates_skipped=0, failed=0)
    service = ImportProcessingService(
        import_service=SimpleNamespace(),
        file_import_service=SimpleNamespace(),
        tax_certified_import_service=SimpleNamespace(),
        etc_service=SimpleNamespace(
            list_business_batches=lambda **_kwargs: [business_batch],
            create_business_batch=lambda **_kwargs: business_batch,
            confirm_business_batch_import=lambda *_args, **_kwargs: (business_batch, import_result),
            list_import_batches=lambda: [SimpleNamespace(id="batch-etc-1")],
        ),
        etc_reconciliation_task_service=SimpleNamespace(
            mark_imported=lambda **kwargs: imported_marks.append(dict(kwargs)),
            mark_import_failed=lambda **_kwargs: None,
        ),
        background_job_service=SimpleNamespace(),
        serialize_value=lambda value: value,
        execute_derived_data_lifecycle_event=lambda *args, **kwargs: None,
        schedule_or_run_workbench_auto_matching_for_scopes=lambda *args, **kwargs: None,
        enqueue_workbench_auto_matching_for_scopes=lambda *args, **kwargs: None,
        persist_state_with_workbench_invalidation=lambda **kwargs: None,
        invalidate_tax_offset_read_model_scopes=lambda *args, **kwargs: None,
        workbench_matching_scope_months_for_import_preview=lambda _preview: [],
        workbench_matching_scope_months_for_import_file_session=lambda _session, _selected_file_ids: [],
        tax_offset_scope_keys_for_import_preview=lambda _preview: [],
        tax_offset_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        cost_statistics_scope_keys_for_import_preview=lambda _preview: [],
        cost_statistics_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        input_invoice_usage_scope_keys_for_import_preview=lambda _preview: [],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_preview=lambda _preview: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: ["2026-04"],
        refresh_after_etc_invoice_link=lambda months, **kwargs: refresh_calls.append((list(months), str(kwargs.get("reason")))),
    )

    result = service.execute_etc_invoice_import_confirm_job(
        session_id="etc-session-1",
        task_id="task-1",
        owner_user_id="user",
        background_job_id="",
        task_version=3,
        confirmed_item_set_hash="hash-1",
        total=3,
    )

    assert refresh_calls == [(["2026-04"], "etc_invoice_import_confirm")]
    assert imported_marks[0]["import_batch_id"] == "batch-etc-1"
    assert result["affected_months"] == ["2026-04"]
    assert "2026-04" in result["affected_scope_keys"]
    assert "active:2026-04" in result["affected_scope_keys"]
    assert "read_model_scope_keys" not in result
    assert "operation_barrier_targets" not in result
    assert "freshness_targets" not in result
