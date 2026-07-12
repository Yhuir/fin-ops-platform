from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from fin_ops_platform.services.external_control_evidence import ExternalControlEvidenceService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.external_control_evidence import (
    PostgresExternalControlEvidenceRepository,
)
from fin_ops_platform.services.postgres_repositories.external_control_evidence_audit import (
    audit_external_control_evidence,
)
from tests.external_evidence_test_support import (
    bank_item,
    etc_invoice_item,
    invoice_item,
    manifest_payload,
    oa_application_item,
    oa_attachment_item,
    oa_detail_item,
)
from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class _Connection:
    def __init__(self, manifests: dict[str, object], canonical: dict[str, list[dict]]) -> None:
        self.headers: list[dict] = []
        self.items: dict[str, list[dict]] = {}
        self.canonical = canonical
        for index, (domain, manifest) in enumerate(manifests.items(), start=1):
            evidence_id = f"00000000-0000-0000-0000-{index:012d}"
            self.headers.append(
                {
                    "evidence_id": evidence_id,
                    "tenant_id": manifest.tenant_id,
                    "domain": domain,
                    "contract_version": manifest.contract_version,
                    "coverage_mode": manifest.coverage_mode,
                    "scope_key": manifest.scope_key,
                    "source_system": manifest.source_system,
                    "source_snapshot_id": manifest.source_snapshot_id,
                    "observed_at": manifest.observed_at,
                    "valid_until": manifest.valid_until,
                    "artifact_sha256": manifest.artifact_sha256,
                    "artifact_size_bytes": manifest.artifact_size_bytes,
                    "collector_name": manifest.collector_name,
                    "collector_version": manifest.collector_version,
                    "manifest_fingerprint": manifest.manifest_fingerprint,
                    "declared_controls": manifest.controls,
                    "item_count": len(manifest.items),
                    "status": "registered",
                    "registered_at": manifest.observed_at,
                    "revoked_at": None,
                }
            )
            self.items[evidence_id] = [
                {
                    "item_kind": item.item_kind,
                    "item_key": item.item_key,
                    "content_fingerprint": item.content_fingerprint,
                    "normalized_fields": item.normalized_fields,
                }
                for item in manifest.items
            ]

    def fetch_all(self, sql: str, params: tuple = ()):
        if "distinct on (domain)" in sql:
            return list(self.headers)
        if "external_control_evidence_items" in sql:
            return list(self.items.get(str(params[0]), []))
        if "from app.bank_transactions" in sql:
            return list(self.canonical.get("bank_transaction", []))
        if "from app.oa_application_items" in sql:
            return list(self.canonical.get("oa_item", []))
        if "from app.oa_attachments" in sql:
            return list(self.canonical.get("oa_attachment", []))
        if "from app.oa_applications" in sql:
            return list(self.canonical.get("oa_application", []))
        if "from app.invoices" in sql:
            return list(self.canonical.get("invoice", []))
        if "from app.tax_certified_import_records" in sql:
            return list(self.canonical.get("tax_certified_invoice", []))
        if "from app.etc_import_session_files" in sql:
            return list(self.canonical.get("etc_archive", []))
        if "from app.etc_invoices" in sql:
            return list(self.canonical.get("etc_invoice", []))
        raise AssertionError(sql)


def _fixture():
    service = ExternalControlEvidenceService()
    raw = {
        "bank": [bank_item()],
        "oa": [oa_application_item(), oa_detail_item(), oa_attachment_item()],
        "invoice": [invoice_item()],
        "etc": [etc_invoice_item()],
    }
    manifests = {domain: service.validate_manifest(manifest_payload(domain, items)) for domain, items in raw.items()}
    canonical: dict[str, list[dict]] = {}
    for manifest in manifests.values():
        for item in manifest.items:
            canonical.setdefault(item.item_kind, []).append(dict(item.normalized_fields))
    return manifests, canonical


class ExternalControlEvidenceAuditTests(unittest.TestCase):
    def test_four_exact_complete_snapshots_pass_with_bounded_as_of_claim(self) -> None:
        manifests, canonical = _fixture()
        report = audit_external_control_evidence(
            _Connection(manifests, canonical),
            tenant_id="default",
            as_of="2026-07-11T12:00:00+00:00",
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["end_to_end_source_truth"], "proven_as_of_external_evidence")
        self.assertEqual(report["summary"]["passed_domain_count"], 4)
        self.assertTrue(all(domain["issue_count"] == 0 for domain in report["domains"]))
        self.assertIn("does not prove", report["claim_boundary"])

    def test_missing_domain_stays_unknown_and_cannot_claim_end_to_end_truth(self) -> None:
        manifests, canonical = _fixture()
        del manifests["oa"]
        report = audit_external_control_evidence(
            _Connection(manifests, canonical),
            tenant_id="default",
            as_of="2026-07-11T12:00:00+00:00",
        )

        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["end_to_end_source_truth"], "unproven")
        oa = next(row for row in report["domains"] if row["domain"] == "oa")
        self.assertEqual(oa["reason"], "external_control_evidence_not_registered")

    def test_same_count_and_amount_substitution_is_blocked_by_exact_item_set(self) -> None:
        manifests, canonical = _fixture()
        replacement = ExternalControlEvidenceService().validate_manifest(
            manifest_payload("bank", [bank_item(serial="SERIAL-REPLACED")])
        ).items[0]
        canonical["bank_transaction"] = [dict(replacement.normalized_fields)]
        report = audit_external_control_evidence(
            _Connection(manifests, canonical),
            tenant_id="default",
            as_of="2026-07-11T12:00:00+00:00",
        )

        bank = next(row for row in report["domains"] if row["domain"] == "bank")
        self.assertEqual(bank["manifest_controls"], bank["canonical_controls"])
        self.assertEqual(bank["status"], "fail")
        codes = {issue["code"] for issue in bank["issues"]}
        self.assertIn("external_evidence_item_missing_from_app", codes)
        self.assertIn("external_evidence_uncovered_app_item", codes)

    def test_nonidentity_field_drift_missing_extra_and_manifest_corruption_fail(self) -> None:
        manifests, canonical = _fixture()
        canonical["bank_transaction"][0]["summary"] = "changed"
        canonical["invoice"].append(dict(canonical["invoice"][0]))
        connection = _Connection(manifests, canonical)
        oa_header = next(row for row in connection.headers if row["domain"] == "oa")
        connection.items[oa_header["evidence_id"]] = connection.items[oa_header["evidence_id"]][:-1]
        report = audit_external_control_evidence(
            connection,
            tenant_id="default",
            as_of="2026-07-11T12:00:00+00:00",
        )

        codes = {issue["code"] for row in report["domains"] for issue in row.get("issues", [])}
        self.assertIn("external_evidence_item_field_mismatch", codes)
        self.assertIn("external_evidence_canonical_duplicate_item_identity", codes)
        self.assertIn("external_evidence_header_item_count_mismatch", codes)

    def test_latest_revoked_or_expired_evidence_fails_without_old_version_fallback(self) -> None:
        manifests, canonical = _fixture()
        connection = _Connection(manifests, canonical)
        bank_header = next(row for row in connection.headers if row["domain"] == "bank")
        bank_header["status"] = "revoked"
        invoice_header = next(row for row in connection.headers if row["domain"] == "invoice")
        invoice_header["valid_until"] = datetime(2026, 7, 11, 1, tzinfo=UTC)
        report = audit_external_control_evidence(
            connection,
            tenant_id="default",
            as_of="2026-07-11T12:00:00+00:00",
        )

        codes = {issue["code"] for row in report["domains"] for issue in row.get("issues", [])}
        self.assertIn("external_evidence_revoked", codes)
        self.assertIn("external_evidence_expired", codes)
        self.assertEqual(report["status"], "fail")


class ExternalControlEvidenceAuditPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))

    def test_full_migration_exact_pass_field_drift_and_revoked_latest_fail_closed(self) -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                account_no, txn_direction, counterparty_name_raw, amount, signed_amount,
                txn_date, txn_month, trade_time, bank_serial_no, balance, currency,
                summary, remark, status, raw_payload
            ) values (
                '622200001234', 'outflow', '外部银行对账供应商', 100, -100,
                '2026-07-10', '2026-07-01', '2026-07-10T01:02:03+00:00',
                'SERIAL-001', 900, 'CNY', '采购付款', '独立清单', 'active', '{}'::jsonb
            )
            """
        )
        now = datetime.now(UTC)
        service = ExternalControlEvidenceService(PostgresExternalControlEvidenceRepository(self.connection))
        payloads = {
            "bank": manifest_payload("bank", [bank_item()], observed_at=now - timedelta(minutes=1), valid_until=now + timedelta(hours=1)),
            "oa": manifest_payload("oa", [], observed_at=now - timedelta(minutes=1), valid_until=now + timedelta(hours=1)),
            "invoice": manifest_payload("invoice", [], observed_at=now - timedelta(minutes=1), valid_until=now + timedelta(hours=1)),
            "etc": manifest_payload("etc", [], observed_at=now - timedelta(minutes=1), valid_until=now + timedelta(hours=1)),
        }
        results = {
            domain: service.register(payload, actor="test-operator", reason="postgres-exact-set-proof")
            for domain, payload in payloads.items()
        }

        clean = audit_external_control_evidence(
            self.connection,
            tenant_id="default",
            as_of=now,
        )
        self.assertEqual(clean["status"], "pass")

        self.connection.execute("update app.bank_transactions set summary = '字段漂移'")
        drift = audit_external_control_evidence(self.connection, tenant_id="default", as_of=now)
        bank = next(row for row in drift["domains"] if row["domain"] == "bank")
        self.assertIn("external_evidence_item_field_mismatch", {issue["code"] for issue in bank["issues"]})

        self.connection.execute("update app.bank_transactions set summary = '采购付款'")
        service.revoke(
            results["bank"]["evidence_id"],
            actor="test-operator",
            reason="source_snapshot_withdrawn",
        )
        revoked = audit_external_control_evidence(self.connection, tenant_id="default", as_of=now)
        bank = next(row for row in revoked["domains"] if row["domain"] == "bank")
        self.assertIn("external_evidence_revoked", {issue["code"] for issue in bank["issues"]})


if __name__ == "__main__":
    unittest.main()
