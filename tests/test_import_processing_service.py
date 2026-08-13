from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.services.import_processing_service import ImportProcessingService


def _assert_import_write_result_has_only_affected_scopes() -> None:
    result = ImportProcessingService._write_result_envelope(
        tax_offset_scope_keys=[],
        bank_scope_keys=["2026-07"],
        input_invoice_usage_scope_keys=[],
        output_invoice_collection_scope_keys=[],
    )

    assert result["affected_scope_keys"] == ["2026-07"]


def _assert_file_import_confirm_job_returns_import_write_targets(*, fail_persist: bool = False) -> None:
    events: list[str] = []
    persisted: list[dict[str, object]] = []
    import_state_payload = {"imports": {"batches": {"batch-1": object()}}, "file_imports": {"sessions": {}}}
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

    def persist_confirmed_import_delta(**kwargs: object) -> None:
        events.append("persist")
        persisted.append(dict(kwargs))
        if fail_persist:
            raise RuntimeError("persist failed")

    def schedule_workbench_matching_scopes(*_args: object, **_kwargs: object) -> list[str]:
        events.append("matching")
        return ["2026-06"]

    service = ImportProcessingService(
        file_import_service=SimpleNamespace(
            get_session=lambda _session_id: confirmed_session,
            confirm_session=lambda **_kwargs: confirmed_session,
            confirmed_session_persistence_payload=lambda **_kwargs: import_state_payload,
        ),
        tax_certified_import_service=SimpleNamespace(),
        etc_service=SimpleNamespace(),
        etc_reconciliation_task_service=SimpleNamespace(),
        background_job_service=SimpleNamespace(),
        serialize_value=lambda value: value,
        schedule_workbench_matching_scopes=schedule_workbench_matching_scopes,
        persist_confirmed_import_delta=persist_confirmed_import_delta,
        workbench_matching_scope_months_for_import_file_session=lambda _session, _selected_file_ids: ["2026-06"],
        tax_offset_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        bank_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: ["2026-06"],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: [],
        etc_import_preview_service=SimpleNamespace(),
    )

    if fail_persist:
        try:
            service.execute_file_import_confirm_job(
                session_id="session-1",
                selected_file_ids=["file-bank"],
                background_job_id="",
            )
        except RuntimeError as exc:
            assert str(exc) == "persist failed"
        else:
            raise AssertionError("persistence failure must fail the import job")
        assert events == ["persist"]
        return

    result = service.execute_file_import_confirm_job(
        session_id="session-1",
        selected_file_ids=["file-bank"],
        background_job_id="",
    )

    assert events == ["persist", "matching"]
    assert result["affected_months"] == ["2026-06"]
    assert result["queued_matching_months"] == ["2026-06"]
    assert persisted[0]["import_state_payload"] is import_state_payload
    assert result["affected_scope_keys"] == ["2026-06"]


def _assert_etc_invoice_import_confirm_job_returns_targets_after_changed_months_are_known() -> None:
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
        schedule_workbench_matching_scopes=lambda *args, **kwargs: [],
        persist_confirmed_import_delta=lambda **kwargs: None,
        workbench_matching_scope_months_for_import_file_session=lambda _session, _selected_file_ids: [],
        tax_offset_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        bank_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        link_etc_import_result_to_existing_invoices=lambda _result: ["2026-04"],
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

    assert imported_marks[0]["import_batch_id"] == "batch-etc-1"
    assert result["affected_months"] == ["2026-04"]
    assert result["affected_scope_keys"] == ["2026-04"]


class ImportProcessingServiceTests(unittest.TestCase):
    def test_import_write_result_has_only_affected_scopes(self) -> None:
        _assert_import_write_result_has_only_affected_scopes()

    def test_file_import_confirm_persists_before_publishing_downstream_work(self) -> None:
        _assert_file_import_confirm_job_returns_import_write_targets()

    def test_file_import_confirm_does_not_publish_downstream_work_when_persistence_fails(self) -> None:
        _assert_file_import_confirm_job_returns_import_write_targets(fail_persist=True)

    def test_etc_invoice_import_confirm_job_returns_targets_after_changed_months_are_known(self) -> None:
        _assert_etc_invoice_import_confirm_job_returns_targets_after_changed_months_are_known()
