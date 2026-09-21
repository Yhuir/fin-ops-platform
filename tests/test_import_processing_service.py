from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.services.import_job_queue import ImportJobDataError
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
                row_results=[],
            )
        ],
    )

    def persist_confirmed_import_delta(**kwargs: object) -> dict[str, object]:
        events.append("persist")
        persisted.append(dict(kwargs))
        if fail_persist:
            raise RuntimeError("persist failed")
        return {
            "queued_matching_months": ["2026-06"],
            "oa_attachment_invoice_promotion": {"reason_counts": {}},
        }

    service = ImportProcessingService(
        file_import_service=SimpleNamespace(
            get_session=lambda _session_id: confirmed_session,
            confirm_session=lambda **_kwargs: confirmed_session,
            confirmed_session_persistence_payload=lambda **_kwargs: import_state_payload,
        ),
        etc_service=SimpleNamespace(),
        etc_reconciliation_task_service=SimpleNamespace(),
        serialize_value=lambda value: value,
        persist_confirmed_import_delta=persist_confirmed_import_delta,
        workbench_matching_scope_months_for_import_file_session=lambda _session, _selected_file_ids: ["2026-06"],
        tax_offset_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        bank_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: ["2026-06"],
        input_invoice_usage_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda _session, _selected_file_ids: [],
        etc_import_preview_service=SimpleNamespace(),
    )

    if fail_persist:
        try:
            service.execute_file_import_confirm_job(
                session_id="session-1",
                selected_file_ids=["file-bank"],
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
    )

    assert events == ["persist"]
    assert result["affected_months"] == ["2026-06"]
    assert result["queued_matching_months"] == ["2026-06"]
    assert persisted[0]["import_state_payload"] is import_state_payload
    assert persisted[0]["scope_months"] == ["2026-06"]
    assert result["oa_attachment_invoice_promotion"] == {"reason_counts": {}}
    assert result["affected_scope_keys"] == ["2026-06"]


def _assert_etc_invoice_import_confirm_job_returns_targets_after_changed_months_are_known() -> None:
    commits = []
    completion = object()
    validated = SimpleNamespace(session=SimpleNamespace(task_version=3, confirmed_item_set_hash="hash-1"))
    def commit(**kwargs):
        commits.append(kwargs)
        return {"affected_months": ["2026-04"], "affected_scope_keys": ["2026-04"]}
    service = ImportProcessingService(
        file_import_service=SimpleNamespace(), serialize_value=lambda value: value,
        etc_service=SimpleNamespace(), etc_reconciliation_task_service=SimpleNamespace(),
        persist_confirmed_import_delta=lambda **kwargs: None,
        workbench_matching_scope_months_for_import_file_session=lambda *_args: [],
        tax_offset_scope_keys_for_import_file_session=lambda *_args: [],
        bank_scope_keys_for_import_file_session=lambda *_args: [],
        input_invoice_usage_scope_keys_for_import_file_session=lambda *_args: [],
        output_invoice_collection_scope_keys_for_import_file_session=lambda *_args: [],
        etc_import_preview_service=SimpleNamespace(validate=lambda **_kwargs: validated),
        etc_import_uow=SimpleNamespace(commit=commit),
    )
    result = service.execute_etc_invoice_import_confirm_job(
        session_id="etc-session-1", task_id="task-1", owner_user_id="user", task_version=3,
        confirmed_item_set_hash="hash-1", completion=completion,
    )
    assert commits == [{"validated": validated, "owner_user_id": "user", "completion": completion}]
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

    def test_etc_processor_rejects_missing_or_mismatched_owner_before_io(self) -> None:
        service = object.__new__(ImportProcessingService)
        for owner, payload in [(None, {}), ("owner", {"owner_user_id": "other"})]:
            with self.subTest(owner=owner):
                with self.assertRaisesRegex(ImportJobDataError, "owner"):
                    service.process_etc_invoice_import_confirm_job(SimpleNamespace(
                        created_by=owner, payload=payload,
                    ))
