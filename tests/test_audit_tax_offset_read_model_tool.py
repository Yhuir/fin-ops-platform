from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories import tax_offset_page_audit


class FakeConnection:
    def __init__(self, *, omit_key: tuple[str, str, str] | None = None, stale_versions: bool = False) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.invoices = [
            {
                "scope_key": "2026-05",
                "row_id": "output-1",
                "invoice_type": "output",
                "invoice_no": "OUT-1",
                "invoice_date": "2026-05-02",
                "buyer_name": "购方",
                "buyer_tax_no": "BUY-TAX",
                "tax_amount": "10.00",
                "amount": "100.00",
                "tax_rate": "0.1",
            },
            {
                "scope_key": "2026-05",
                "row_id": "input-1",
                "invoice_type": "input",
                "invoice_no": "IN-1",
                "digital_invoice_no": "DIG-1",
                "invoice_date": "2026-05-03",
                "seller_name": "销方",
                "seller_tax_no": "SELL-TAX",
                "tax_amount": "6.00",
                "amount": "60.00",
                "tax_rate": "0.1",
                "raw_payload": {"risk_level": "低"},
            },
        ]
        self.certified = [
            {
                "scope_key": "2026-05",
                "certified_unique_key": "cert-1",
                "digital_invoice_no": "DIG-1",
                "invoice_no": "IN-1",
                "seller_name": "销方",
                "seller_tax_no": "SELL-TAX",
                "invoice_date": "2026-05-03",
                "amount": "60.00",
                "tax_amount": "6.00",
                "status": "已认证",
            }
        ]
        expected = tax_offset_page_audit._expected_months(self.invoices, self.certified)["2026-05"]
        self.source_versions = {
            "tax_offset_read_model_schema_version": tax_offset_page_audit.TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            "invoice_fact_source_version": "rows:2|max_updated_at:2026-05-10 00:00:00+00",
            "tax_certified_import_source_version": "rows:1|max_updated_at:2026-05-11 00:00:00+00",
            "oa_attachment_invoice_parser_version": tax_offset_page_audit.attachment_invoice_cache_parser_version(),
            "oa_projection_sync_version": tax_offset_page_audit.OA_PROJECTION_SYNC_VERSION,
        }
        model_versions = {"stale": True} if stale_versions else self.source_versions
        payload = {
            "month": "2026-05",
            "output_items": expected["output_items"],
            "input_items": expected["input_plan_items"],
            "input_plan_items": expected["input_plan_items"],
            "certified_items": expected["certified_items"],
            "certified_matched_rows": expected["certified_matched_items"],
            "certified_outside_plan_rows": expected["certified_outside_items"],
            "locked_certified_input_ids": expected["locked_certified_input_ids"],
            "default_selected_output_ids": expected["default_selected_output_ids"],
            "default_selected_input_ids": expected["default_selected_input_ids"],
            "summary": expected["summary"],
        }
        self.models = [
            {
                "scope_key": "2026-05",
                "entry_count": 3,
                "source_versions": model_versions,
                "schema_version": tax_offset_page_audit.TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                "cache_status": "ready",
                "payload": {"payload": payload},
            }
        ]
        self.items: list[dict[str, object]] = []
        for item_type in tax_offset_page_audit.ITEM_TYPES:
            for index, item in enumerate(expected[f"{item_type}_items"]):
                key = ("2026-05", item_type, str(item["id"]))
                if key == omit_key:
                    continue
                self.items.append(
                    {
                        "scope_key": "2026-05",
                        "item_type": item_type,
                        "item_id": item["id"],
                        "item_index": index,
                        "source_versions": model_versions,
                        "payload": dict(item),
                        **dict(item),
                    }
                )

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        if "from app.invoices" in sql and "max(updated_at)" not in sql:
            return [dict(row) for row in self.invoices]
        if "from app.tax_certified_import_records" in sql and "max(updated_at)" not in sql:
            return [dict(row) for row in self.certified]
        if "from read_model.tax_offset_read_models" in sql:
            return [dict(row) for row in self.models]
        if "from read_model.tax_offset_items" in sql:
            return [dict(row) for row in self.items]
        return []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        if "from app.invoices" in sql:
            return {"row_count": 2, "max_updated_at": "2026-05-10 00:00:00+00"}
        return {"row_count": 1, "max_updated_at": "2026-05-11 00:00:00+00"}

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((sql, params))
        raise AssertionError("tax offset audit must be read-only")


class TaxOffsetPageAuditTests(unittest.TestCase):
    def test_clean_registered_facts_pass_without_writes(self) -> None:
        connection = FakeConnection()
        report = tax_offset_page_audit.audit_tax_offset_page(connection)
        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertEqual(connection.executed, [])
        self.assertFalse(report["audit_contract"]["database_snapshot"])

    def test_canonical_invoice_omission_is_blocking(self) -> None:
        report = tax_offset_page_audit.audit_tax_offset_page(FakeConnection(omit_key=("2026-05", "output", "output-1")))
        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"], {"tax_offset_canonical_missing_projection": 1}
        )

    def test_wrong_certified_match_is_blocking(self) -> None:
        connection = FakeConnection()
        row = next(item for item in connection.items if item["item_type"] == "certified_matched")
        row["payload"] = {**dict(row["payload"]), "matched_input_id": "wrong-input"}
        report = tax_offset_page_audit.audit_tax_offset_page(connection)
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"], {"tax_offset_key_display_fields_mismatch": 1}
        )

    def test_stale_source_versions_are_blocking(self) -> None:
        report = tax_offset_page_audit.audit_tax_offset_page(FakeConnection(stale_versions=True))
        self.assertIn("tax_offset_source_versions_mismatch", report["summary"]["issue_sample_counts_by_code"])

    def test_stale_cache_status_and_missing_input_alias_are_blocking(self) -> None:
        connection = FakeConnection()
        connection.models[0]["cache_status"] = "stale"
        connection.models[0]["payload"]["payload"].pop("input_items")

        report = tax_offset_page_audit.audit_tax_offset_page(connection)

        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {
                "tax_offset_cache_status_not_ready": 1,
                "tax_offset_model_payload_set_mismatch": 1,
            },
        )

    def test_duplicate_or_invalid_month_scopes_are_blocking(self) -> None:
        connection = FakeConnection()
        duplicate = dict(connection.models[0])
        invalid = {**dict(connection.models[0]), "scope_key": "2026-13"}
        connection.models.extend([duplicate, invalid])

        report = tax_offset_page_audit.audit_tax_offset_page(connection)

        self.assertIn("tax_offset_duplicate_scope", report["summary"]["issue_sample_counts_by_code"])
        self.assertIn("tax_offset_invalid_scope", report["summary"]["issue_sample_counts_by_code"])

    def test_canonical_invoice_total_is_recalculated(self) -> None:
        connection = FakeConnection()
        connection.invoices[0]["total_with_tax"] = "999.00"

        report = tax_offset_page_audit.audit_tax_offset_page(connection)

        self.assertIn(
            "tax_offset_canonical_invoice_total_mismatch",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_ambiguous_certified_match_is_blocking(self) -> None:
        connection = FakeConnection()
        connection.invoices.append({**connection.invoices[1], "row_id": "input-2"})

        report = tax_offset_page_audit.audit_tax_offset_page(connection)

        self.assertIn("tax_offset_certified_match_ambiguous", report["summary"]["issue_sample_counts_by_code"])


if __name__ == "__main__":
    unittest.main()
