from __future__ import annotations

from types import SimpleNamespace

from fin_ops_platform.services.invoice_lifecycle_sql_projection import InvoiceLifecycleSqlProjectionBuilder


class FreshInvoiceUsageReadRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def list_input_invoice_usage_rows(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {
            "refresh_status": "fresh",
            "source_versions": {"workbench_relation_source_versions": {"2026-05": 7}},
            "pagination": {"page": 1, "pageSize": 200, "total": 1},
            "rows": [
                {
                    "invoiceId": "input-invoice-1",
                    "invoiceIdentityKey": "identity-1",
                    "paymentStatus": {"code": "paid", "label": "已支付"},
                }
            ],
        }


def test_invoice_lifecycle_reuses_fresh_input_usage_read_model_rows() -> None:
    read_repository = FreshInvoiceUsageReadRepository()
    builder = InvoiceLifecycleSqlProjectionBuilder(
        connection=SimpleNamespace(),
        read_model_repository=read_repository,
        workbench_relation_read_facade=SimpleNamespace(last_source_versions={}),
    )

    rows = builder._input_invoice_lifecycle_rows("2026-05")

    assert read_repository.calls == [
        {
            "month": "2026-05",
            "page": 1,
            "page_size": 200,
            "sort_field": "invoice_date",
            "sort_direction": "desc",
        }
    ]
    assert rows == [
        {
            "subject_id": "input-invoice-1",
            "subject_type": "input_invoice",
            "scope_key": "2026-05",
            "scope_month": "2026-05",
            "invoice_identity_key": "identity-1",
            "lifecycle_status": "paid",
            "acquisition_status": {},
            "payment_status": {"code": "paid", "label": "已支付"},
            "collection_status": {},
            "certification_status": {},
        }
    ]
    assert builder._read_model_dependency_source_versions == {
        "input_invoice_usage_read_model_source_versions": {"workbench_relation_source_versions": {"2026-05": 7}}
    }
