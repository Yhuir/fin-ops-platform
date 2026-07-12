from __future__ import annotations

from types import SimpleNamespace

from fin_ops_platform.services.import_processing_service import ImportProcessingService


def test_import_write_target_envelope_uses_bank_detail_months_for_pending_invoice() -> None:
    result = ImportProcessingService._import_write_target_envelope(
        cost_statistics_scope_keys=[],
        tax_offset_scope_keys=[],
        bank_detail_scope_keys=["2026-07"],
        input_invoice_usage_scope_keys=[],
        output_invoice_collection_scope_keys=[],
    )

    assert {"read_model_key": "pending_invoice", "scope_key": "expense:all:2026-07"} in result["operation_barrier_targets"]
    assert {"read_model_key": "pending_invoice", "scope_key": "income:all:2026-07"} in result["operation_barrier_targets"]
    assert {"read_model_key": "pending_invoice", "scope_key": "income:cash_income:2026-07"} in result["operation_barrier_targets"]
    assert {"read_model_key": "pending_invoice", "scope_key": "expense:all"} not in result["operation_barrier_targets"]


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
        workbench_matching_scope_months_for_import_file_session=lambda _session, _selected_file_ids: ["2026-06"],
        tax_offset_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        cost_statistics_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: ["2026-06"],
        bank_detail_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: ["2026-06"],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: [],
        refresh_after_etc_invoice_link=lambda *args, **kwargs: None,
        etc_import_preview_service=SimpleNamespace(),
    )

    result = service.execute_file_import_confirm_job(
        session_id="session-1",
        selected_file_ids=["file-bank"],
        owner_user_id="user",
        background_job_id="",
    )

    assert result["affected_months"] == ["2026-06"]
    assert {"read_model_key": "bank_detail", "scope_key": "2026-06"} in result["operation_barrier_targets"]
    assert {"read_model_key": "bank_account_balance", "scope_key": "all"} in result["operation_barrier_targets"]
    assert {"read_model_key": "cost_statistics", "scope_key": "active:2026-06"} in result["operation_barrier_targets"]


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
        file_import_service=SimpleNamespace(),
        tax_certified_import_service=SimpleNamespace(),
        etc_service=SimpleNamespace(
            list_business_batches=lambda **_kwargs: [business_batch],
            create_business_batch=lambda **_kwargs: business_batch,
            confirm_business_batch_import=lambda *_args, **_kwargs: (business_batch, import_result),
            list_import_batches=lambda: [SimpleNamespace(id="batch-etc-1")],
        ),
        etc_reconciliation_task_service=SimpleNamespace(
            begin_import=lambda **_kwargs: None,
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
        workbench_matching_scope_months_for_import_file_session=lambda _session, _selected_file_ids: [],
        tax_offset_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        cost_statistics_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        bank_detail_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: ["2026-04"],
        refresh_after_etc_invoice_link=lambda months, **kwargs: refresh_calls.append((list(months), str(kwargs.get("reason")))),
        etc_import_preview_service=SimpleNamespace(
            validate=lambda **_kwargs: SimpleNamespace(uploads=[]),
            mark_status=lambda *_args, **_kwargs: None,
        ),
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
    assert result["affected_scope_keys"] == result["read_model_scope_keys"]
    assert {"read_model_key": "tax_offset", "scope_key": "2026-04"} in result["operation_barrier_targets"]
    assert {"read_model_key": "input_invoice_usage", "scope_key": "2026-04"} in result["operation_barrier_targets"]
    assert {"read_model_key": "workbench_relation", "scope_key": "2026-04"} in result["operation_barrier_targets"]
    assert {"read_model_key": "cost_statistics", "scope_key": "active:2026-04"} in result["operation_barrier_targets"]
