from __future__ import annotations

from contextlib import contextmanager
import unittest
from unittest.mock import MagicMock, patch

import pytest

from fin_ops_platform.services.confirmed_invoice_import_uow import (
    ConfirmedInvoiceImportUnitOfWork,
)
from fin_ops_platform.services.oa_attachment_invoice_cache import (
    ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
    attachment_invoice_cache_parser_version,
)


class _Connection:
    def __init__(self) -> None:
        self.transaction = MagicMock(side_effect=self._transaction)
        self.tx = MagicMock()

    @contextmanager
    def _transaction(self):
        yield self.tx


def _assert_confirmed_invoice_uow_orders_lock_save_link_and_one_expanded_dirty_write() -> None:
    connection = _Connection()
    events: list[str] = []
    core = MagicMock()
    core.prepare_confirmed_invoice_upserts_in_transaction.side_effect = (
        lambda *_args, **_kwargs: events.append("prepare")
    )
    core.save_import_delta_in_transaction.side_effect = (
        lambda *_args, **_kwargs: events.append("save")
    )
    promoter = MagicMock()
    promoter.promote_confirmed_invoice_identity_keys.side_effect = (
        lambda *_args, **_kwargs: events.append("promote") or {"reason_counts": {}}
    )

    with (
        patch(
            "fin_ops_platform.services.confirmed_invoice_import_uow.PostgresCoreRepository",
            return_value=core,
        ),
        patch(
            "fin_ops_platform.services.confirmed_invoice_import_uow.OAAttachmentInvoicePromotionService",
            return_value=promoter,
        ) as promotion_type,
        patch(
            "fin_ops_platform.services.confirmed_invoice_import_uow."
            "PostgresWorkbenchMatchingQueueRepository."
            "mark_workbench_matching_dirty_scopes_in_transaction",
            side_effect=lambda **_kwargs: events.append("dirty")
            or ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"],
        ) as mark_dirty,
    ):
        promotion_type.strong_identity_key = staticmethod(
            lambda invoice: invoice.get("digital_invoice_no")
        )
        result = ConfirmedInvoiceImportUnitOfWork(connection).execute(
            normalized_payload={
                "imports": {
                    "invoices": {
                        "invoice-338": {
                            "digital_invoice_no": "26537000000000000338"
                        }
                    }
                },
                "file_imports": {"sessions": {}},
            },
            scope_months=["2026-08"],
            promotion_mode="create_missing",
            source_versions={"rule": "v1"},
        )

    assert events == ["prepare", "save", "promote", "dirty"]
    promoter.promote_confirmed_invoice_identity_keys.assert_called_once_with(
        {"26537000000000000338"},
        configured_mode="create_missing",
        parser_version=attachment_invoice_cache_parser_version(),
        cache_schema_version=ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
        apply=True,
    )
    assert mark_dirty.call_args.kwargs["scope_months"] == [
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
    ]
    assert result["queued_matching_months"] == [
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
    ]


def _assert_generic_bank_confirm_keeps_same_uow_and_rolls_back_before_dirty_on_failure() -> None:
    connection = _Connection()
    core = MagicMock()
    core.save_import_delta_in_transaction.side_effect = RuntimeError("save failed")
    with (
        patch(
            "fin_ops_platform.services.confirmed_invoice_import_uow.PostgresCoreRepository",
            return_value=core,
        ),
        patch(
            "fin_ops_platform.services.confirmed_invoice_import_uow.OAAttachmentInvoicePromotionService"
        ) as promoter,
        patch(
            "fin_ops_platform.services.confirmed_invoice_import_uow."
            "PostgresWorkbenchMatchingQueueRepository."
            "mark_workbench_matching_dirty_scopes_in_transaction"
        ) as mark_dirty,
    ):
        with pytest.raises(RuntimeError, match="save failed"):
            ConfirmedInvoiceImportUnitOfWork(connection).execute(
                normalized_payload={
                    "imports": {"transactions": {"bank-1": {"id": "bank-1"}}},
                    "file_imports": {"sessions": {}},
                },
                scope_months=["2026-08"],
                promotion_mode="link_existing_only",
                source_versions={},
            )

    promoter.assert_not_called()
    mark_dirty.assert_not_called()


def _assert_generic_bank_confirm_does_not_query_oa_cache() -> None:
    connection = _Connection()
    core = MagicMock()
    with (
        patch(
            "fin_ops_platform.services.confirmed_invoice_import_uow.PostgresCoreRepository",
            return_value=core,
        ),
        patch(
            "fin_ops_platform.services.confirmed_invoice_import_uow."
            "PostgresWorkbenchMatchingQueueRepository."
            "mark_workbench_matching_dirty_scopes_in_transaction",
            return_value=["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"],
        ),
    ):
        ConfirmedInvoiceImportUnitOfWork(connection).execute(
            normalized_payload={
                "imports": {"transactions": {"bank-1": {"id": "bank-1"}}},
                "file_imports": {"sessions": {}},
            },
            scope_months=["2026-08"],
            promotion_mode="create_missing",
            source_versions={},
        )

    connection.tx.fetch_all.assert_not_called()


class ConfirmedInvoiceImportUnitOfWorkTests(unittest.TestCase):
    def test_orders_lock_save_link_and_one_expanded_dirty_write(self) -> None:
        _assert_confirmed_invoice_uow_orders_lock_save_link_and_one_expanded_dirty_write()

    def test_generic_bank_confirm_rolls_back_before_dirty_on_failure(self) -> None:
        _assert_generic_bank_confirm_keeps_same_uow_and_rolls_back_before_dirty_on_failure()

    def test_generic_bank_confirm_does_not_query_oa_cache(self) -> None:
        _assert_generic_bank_confirm_does_not_query_oa_cache()
