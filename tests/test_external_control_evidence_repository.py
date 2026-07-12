from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import unittest

from fin_ops_platform.services.external_control_evidence import ExternalControlEvidenceService
from fin_ops_platform.services.postgres_repositories.external_control_evidence import (
    PostgresExternalControlEvidenceRepository,
)
from tests.external_evidence_test_support import bank_item, manifest_payload


class _Transaction:
    def __init__(self, *, existing=None, revoke_row=None) -> None:
        self.existing = existing
        self.revoke_row = revoke_row
        self.fetch_calls: list[tuple[str, tuple]] = []
        self.item_rows: list[tuple] = []

    def fetch_one(self, sql: str, params: tuple = ()):
        self.fetch_calls.append((sql, params))
        normalized = " ".join(sql.split())
        if normalized.startswith("select evidence_id::text as evidence_id, status"):
            return self.existing
        if normalized.startswith("insert into audit.external_control_evidence ("):
            return {
                "evidence_id": "00000000-0000-0000-0000-000000000099",
                "status": "registered",
                "registered_at": datetime(2026, 7, 11, tzinfo=UTC),
            }
        if "for update" in normalized:
            return self.revoke_row
        if normalized.startswith("update audit.external_control_evidence"):
            return {"revoked_at": datetime(2026, 7, 11, 1, tzinfo=UTC)}
        if normalized.startswith("insert into audit.events"):
            return {"audit_id": "audit-1"}
        raise AssertionError(normalized)

    def execute_many_values(self, sql: str, params_seq: list[tuple], *, chunk_size: int = 1000) -> int:
        self.item_rows.extend(params_seq)
        return len(params_seq)


class _Connection:
    def __init__(self, transaction: _Transaction) -> None:
        self.transaction_obj = transaction
        self.inspect_rows: list[dict] = []

    @contextmanager
    def transaction(self):
        yield self.transaction_obj

    def fetch_all(self, sql: str, params: tuple = ()):
        return list(self.inspect_rows)


class PostgresExternalControlEvidenceRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = ExternalControlEvidenceService().validate_manifest(manifest_payload("bank", [bank_item()]))

    def test_register_inserts_header_items_and_secret_safe_audit_in_one_transaction(self) -> None:
        transaction = _Transaction()
        repository = PostgresExternalControlEvidenceRepository(_Connection(transaction))

        result = repository.register(self.manifest, actor="operator", reason="monthly_reconciliation")

        self.assertTrue(result["created"])
        self.assertEqual(result["audit_id"], "audit-1")
        self.assertEqual(len(transaction.item_rows), 1)
        self.assertEqual(transaction.item_rows[0][1], "bank_transaction")
        audit_call = next(call for call in transaction.fetch_calls if "insert into audit.events" in call[0])
        self.assertIn(self.manifest.manifest_fingerprint, audit_call[1][3])
        self.assertNotIn("外部银行对账供应商", audit_call[1][3])

    def test_register_same_fingerprint_is_idempotent_and_does_not_reinsert_items(self) -> None:
        transaction = _Transaction(
            existing={
                "evidence_id": "existing",
                "status": "registered",
                "registered_at": datetime(2026, 7, 11, tzinfo=UTC),
                "revoked_at": None,
            }
        )
        repository = PostgresExternalControlEvidenceRepository(_Connection(transaction))

        result = repository.register(self.manifest, actor="operator", reason="repeat")

        self.assertFalse(result["created"])
        self.assertTrue(result["idempotent_replay"])
        self.assertEqual(transaction.item_rows, [])
        self.assertEqual(len(transaction.fetch_calls), 1)

    def test_revoke_is_audited_and_repeat_revoke_is_idempotent(self) -> None:
        evidence_id = "00000000-0000-0000-0000-000000000099"
        current = {
            "evidence_id": evidence_id,
            "tenant_id": "default",
            "domain": "bank",
            "status": "registered",
            "manifest_fingerprint": self.manifest.manifest_fingerprint,
            "revoked_at": None,
        }
        transaction = _Transaction(revoke_row=current)
        result = PostgresExternalControlEvidenceRepository(_Connection(transaction)).revoke(
            evidence_id,
            actor="operator",
            reason="bad_source_snapshot",
        )
        self.assertTrue(result["revoked"])
        self.assertEqual(result["audit_id"], "audit-1")

        transaction = _Transaction(revoke_row={**current, "status": "revoked", "revoked_at": "now"})
        result = PostgresExternalControlEvidenceRepository(_Connection(transaction)).revoke(
            evidence_id,
            actor="operator",
            reason="repeat",
        )
        self.assertFalse(result["revoked"])
        self.assertTrue(result["idempotent_replay"])
        self.assertEqual(len(transaction.fetch_calls), 1)


if __name__ == "__main__":
    unittest.main()
