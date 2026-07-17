from __future__ import annotations

from types import SimpleNamespace
import unittest

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


class InvoiceLifecycleSkipConnection:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.pending_versions = {
            "expense:all:2026-05": {"pending_invoice": "expense-v1"},
            "income:all:2026-05": {"pending_invoice": "income-v1"},
        }
        self.input_versions = {"input_invoice_usage": "v1"}
        self.output_versions = {"output_invoice_collection": "v1"}
        self.oa_versions = {"oa_pending_payment": "v1"}
        self.active_dirty_scopes: set[tuple[str, str]] = set()

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from app.app_settings" in normalized:
            return {"settings_payload": {}}
        if "from job.read_model_dirty_scopes" in normalized:
            if (str(params[0]), str(params[1])) in self.active_dirty_scopes:
                return {"status": "pending"}
            return None
        if "from read_model.pending_invoice_scopes" in normalized:
            return {
                "source_versions": dict(self.pending_versions[str(params[0])]),
                "cache_status": "fresh",
            }
        if "from read_model.input_invoice_usage_scopes" in normalized:
            return {"source_versions": dict(self.input_versions), "cache_status": "fresh"}
        if "from read_model.output_invoice_collection_scopes" in normalized:
            return {"source_versions": dict(self.output_versions), "cache_status": "fresh"}
        if "from read_model.oa_pending_payment_scopes" in normalized:
            return {"source_versions": dict(self.oa_versions), "cache_status": "fresh"}
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        raise AssertionError("unchanged invoice lifecycle scope must not rebuild rows")


class InvoiceLifecycleSkipReadRepository:
    def __init__(self) -> None:
        self.relation_calls: list[str] = []
        self.relation_source_version = 7

    def workbench_relation_source_versions(self, *, scope_key: str) -> dict[str, object]:
        self.relation_calls.append(scope_key)
        return {"scope_key": scope_key, "source_version": self.relation_source_version, "source_signature": "relation-v1"}


class FreshInvoiceLifecycleReadModelRepository:
    def __init__(self) -> None:
        self.source_versions: dict[str, object] = {}
        self.listed_months: list[str] = []
        self.summary_months: list[str] = []

    def list_invoice_lifecycle_rows(self, *, month: str) -> dict[str, object]:
        raise AssertionError("unchanged invoice lifecycle scope must not load projected rows")

    def invoice_lifecycle_scope_summary(self, *, month: str) -> dict[str, object]:
        self.summary_months.append(month)
        return {
            "read_model_status": "fresh",
            "source_versions": dict(self.source_versions),
            "row_count": 1,
        }

    def save_invoice_lifecycle_rows(self, **_kwargs: object) -> None:
        raise AssertionError("unchanged invoice lifecycle scope must not be rewritten")


class PendingInvoiceLifecycleSourceRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def list_pending_invoice_lifecycle_source_rows(self, *, month: str, direction: str) -> dict[str, object]:
        self.calls.append({"month": month, "direction": direction})
        return {
            "refresh_status": "fresh",
            "source_versions": {"direction": direction, "version": 7},
            "rows": [
                {
                    "id": f"txn-{direction}",
                    "bank_transaction": {"id": f"txn-{direction}"},
                    "invoice_acquisition_status": {"code": "missing_invoice"},
                }
            ],
        }


class InvoiceLifecycleSqlProjectionTests(unittest.TestCase):
    def test_invoice_lifecycle_reuses_fresh_pending_invoice_month_rows(self) -> None:
        invoice_repository = PendingInvoiceLifecycleSourceRepository()
        builder = InvoiceLifecycleSqlProjectionBuilder(
            connection=SimpleNamespace(),
            read_model_repository=SimpleNamespace(),
            workbench_relation_read_facade=SimpleNamespace(last_source_versions={}),
            invoice_lifecycle_read_model_repository=invoice_repository,
        )

        rows = builder._pending_invoice_lifecycle_rows("2026-05")

        self.assertEqual(
            invoice_repository.calls,
            [
                {"month": "2026-05", "direction": "expense"},
                {"month": "2026-05", "direction": "income"},
            ],
        )
        self.assertEqual([row["subject_id"] for row in rows], ["txn-expense", "txn-income"])
        self.assertEqual(
            builder._read_model_dependency_source_versions["pending_invoice_read_model_source_versions"],
            {
                "expense:all:2026-05": {"direction": "expense", "version": 7},
                "income:all:2026-05": {"direction": "income", "version": 7},
            },
        )

    def test_invoice_lifecycle_reuses_fresh_input_usage_read_model_rows(self) -> None:
        read_repository = FreshInvoiceUsageReadRepository()
        builder = InvoiceLifecycleSqlProjectionBuilder(
            connection=SimpleNamespace(),
            read_model_repository=read_repository,
            workbench_relation_read_facade=SimpleNamespace(last_source_versions={}),
        )

        rows = builder._input_invoice_lifecycle_rows("2026-05")

        self.assertEqual(
            read_repository.calls,
            [
                {
                    "month": "2026-05",
                    "page": 1,
                    "page_size": 200,
                    "sort_field": "invoice_date",
                    "sort_direction": "desc",
                }
            ],
        )
        self.assertEqual(
            rows,
            [
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
            ],
        )
        self.assertEqual(
            builder._read_model_dependency_source_versions,
            {
                "input_invoice_usage_read_model_source_versions": {
                    "workbench_relation_source_versions": {"2026-05": 7}
                }
            },
        )

    def test_invoice_lifecycle_sql_projection_skips_unchanged_scope_without_rebuild(self) -> None:
        connection = InvoiceLifecycleSkipConnection()
        read_repository = InvoiceLifecycleSkipReadRepository()
        invoice_repository = FreshInvoiceLifecycleReadModelRepository()
        builder = InvoiceLifecycleSqlProjectionBuilder(
            connection=connection,
            read_model_repository=read_repository,
            workbench_relation_read_facade=SimpleNamespace(last_source_versions={}),
            invoice_lifecycle_read_model_repository=invoice_repository,
        )
        builder._read_model_dependency_source_versions = builder._dependency_source_versions_for_scope("2026-05")
        invoice_repository.source_versions = builder._source_versions()
        read_repository.relation_calls = []

        result = builder.rebuild_invoice_lifecycle_read_model_scope("2026-05")

        self.assertEqual(result["scope_key"], "2026-05")
        self.assertEqual(result["row_count"], 1)
        self.assertIs(result["skipped"], True)
        self.assertEqual(result["skip_reason"], "source_versions_unchanged")
        self.assertEqual(invoice_repository.summary_months, ["2026-05"])
        self.assertEqual(invoice_repository.listed_months, [])
        self.assertEqual(read_repository.relation_calls, ["2026-05"])
        self.assertFalse(connection.fetch_all_calls)
        self.assertEqual(
            result["source_versions"]["workbench_relation_source_versions"],
            {
                "scope_key": "2026-05",
                "source_signature": "relation-v1",
            },
        )
        self.assertEqual(
            result["source_versions"]["pending_invoice_read_model_source_versions"],
            {
                "expense:all:2026-05": {"pending_invoice": "expense-v1"},
                "income:all:2026-05": {"pending_invoice": "income-v1"},
            },
        )

    def test_invoice_lifecycle_dependency_versions_ignore_runtime_source_version_only(self) -> None:
        connection = InvoiceLifecycleSkipConnection()
        connection.pending_versions = {
            "expense:all:2026-05": {
                "pending_invoice": "expense-v1",
                "bank_detail_source_versions": {
                    "source_version": 1,
                    "bank_detail_source_signature": "bank-same",
                },
            },
            "income:all:2026-05": {
                "pending_invoice": "income-v1",
                "bank_detail_source_versions": {
                    "source_version": 2,
                    "bank_detail_source_signature": "bank-same",
                },
            },
        }
        connection.input_versions = {"source_version": 3, "input_signature": "input-same"}
        connection.output_versions = {"source_version": 4, "output_signature": "output-same"}
        connection.oa_versions = {"source_version": 5, "oa_signature": "oa-same"}
        read_repository = InvoiceLifecycleSkipReadRepository()
        invoice_repository = FreshInvoiceLifecycleReadModelRepository()
        builder = InvoiceLifecycleSqlProjectionBuilder(
            connection=connection,
            read_model_repository=read_repository,
            workbench_relation_read_facade=SimpleNamespace(last_source_versions={}),
            invoice_lifecycle_read_model_repository=invoice_repository,
        )
        builder._read_model_dependency_source_versions = builder._dependency_source_versions_for_scope("2026-05")
        invoice_repository.source_versions = builder._source_versions()
        self.assertFalse(_has_exact_source_version_key(invoice_repository.source_versions))

        connection.pending_versions["expense:all:2026-05"]["bank_detail_source_versions"]["source_version"] = 101  # type: ignore[index]
        connection.pending_versions["income:all:2026-05"]["bank_detail_source_versions"]["source_version"] = 102  # type: ignore[index]
        connection.input_versions["source_version"] = 103
        connection.output_versions["source_version"] = 104
        connection.oa_versions["source_version"] = 105
        read_repository.relation_source_version = 106
        connection.fetch_all_calls = []

        result = builder.rebuild_invoice_lifecycle_read_model_scope("2026-05")

        self.assertIs(result["skipped"], True)
        self.assertEqual(result["skip_reason"], "source_versions_unchanged")
        self.assertFalse(_has_exact_source_version_key(result["source_versions"]))
        self.assertFalse(connection.fetch_all_calls)

    def test_invoice_lifecycle_defers_when_dependency_scope_is_dirty(self) -> None:
        connection = InvoiceLifecycleSkipConnection()
        connection.active_dirty_scopes.add(("input_invoice_usage", "2026-05"))
        builder = InvoiceLifecycleSqlProjectionBuilder(
            connection=connection,
            read_model_repository=InvoiceLifecycleSkipReadRepository(),
            workbench_relation_read_facade=SimpleNamespace(last_source_versions={}),
            invoice_lifecycle_read_model_repository=FreshInvoiceLifecycleReadModelRepository(),
        )

        with self.assertRaisesRegex(RuntimeError, "input_invoice_usage_read_model_not_fresh"):
            builder.rebuild_invoice_lifecycle_read_model_scope("2026-05")

        self.assertFalse(connection.fetch_all_calls)


def _has_exact_source_version_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(str(key) == "source_version" or _has_exact_source_version_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_exact_source_version_key(item) for item in value)
    return False
