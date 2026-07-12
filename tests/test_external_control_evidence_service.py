from __future__ import annotations

import unittest

from fin_ops_platform.services.external_control_evidence import ExternalControlEvidenceService
from tests.external_evidence_test_support import bank_item, invoice_item, manifest_payload


class _Repository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def register(self, manifest, *, actor: str, reason: str):
        self.calls.append(("register", (manifest, actor, reason)))
        return {"evidence_id": "evidence-1", "created": True}

    def revoke(self, evidence_id: str, *, actor: str, reason: str):
        self.calls.append(("revoke", (evidence_id, actor, reason)))
        return {"evidence_id": evidence_id, "revoked": True}

    def inspect(self, *, tenant_id: str, domain: str | None = None):
        self.calls.append(("inspect", (tenant_id, domain)))
        return []


class ExternalControlEvidenceServiceTests(unittest.TestCase):
    def test_validates_complete_manifest_and_recomputes_all_fingerprints(self) -> None:
        manifest = ExternalControlEvidenceService().validate_manifest(manifest_payload("bank", [bank_item()]))

        self.assertEqual(manifest.domain, "bank")
        self.assertEqual(manifest.controls["item_count"], 1)
        self.assertEqual(manifest.controls["amount_totals_by_kind"], {"bank_transaction": "100"})
        self.assertRegex(manifest.items[0].item_key, r"^bank_transaction:[0-9a-f]{64}$")
        self.assertRegex(manifest.items[0].content_fingerprint, r"^[0-9a-f]{64}$")
        self.assertRegex(manifest.manifest_fingerprint, r"^[0-9a-f]{64}$")

    def test_rejects_partial_coverage_duplicate_identity_wrong_domain_and_false_controls(self) -> None:
        service = ExternalControlEvidenceService()
        partial = manifest_payload("bank", [bank_item()])
        partial["coverage_mode"] = "partial"
        with self.assertRaisesRegex(ValueError, "only accepts"):
            service.validate_manifest(partial)

        duplicate = manifest_payload("bank", [bank_item(), bank_item()])
        with self.assertRaisesRegex(ValueError, "duplicate item identity"):
            service.validate_manifest(duplicate)

        wrong_domain = manifest_payload("invoice", [invoice_item()])
        wrong_domain["domain"] = "bank"
        with self.assertRaisesRegex(ValueError, "does not belong"):
            service.validate_manifest(wrong_domain)

        false_controls = manifest_payload("bank", [bank_item()])
        false_controls["controls"]["item_count"] = 2
        with self.assertRaisesRegex(ValueError, "declared controls"):
            service.validate_manifest(false_controls)

    def test_rejects_caller_supplied_key_or_fingerprint_that_disagrees(self) -> None:
        payload = manifest_payload("bank", [bank_item()])
        payload["items"][0]["key"] = "bank_transaction:wrong"
        with self.assertRaisesRegex(ValueError, "supplied key"):
            ExternalControlEvidenceService().validate_manifest(payload)

        payload = manifest_payload("bank", [bank_item()])
        payload["items"][0]["fingerprint"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "supplied fingerprint"):
            ExternalControlEvidenceService().validate_manifest(payload)

    def test_same_controls_with_substituted_item_changes_manifest_fingerprint(self) -> None:
        first = ExternalControlEvidenceService().validate_manifest(manifest_payload("bank", [bank_item(serial="SERIAL-001")]))
        second_payload = manifest_payload("bank", [bank_item(serial="SERIAL-002")])
        second = ExternalControlEvidenceService().validate_manifest(second_payload)

        self.assertEqual(first.controls, second.controls)
        self.assertNotEqual(first.items[0].item_key, second.items[0].item_key)
        self.assertNotEqual(first.manifest_fingerprint, second.manifest_fingerprint)

    def test_repository_commands_require_explicit_actor_and_reason(self) -> None:
        repository = _Repository()
        service = ExternalControlEvidenceService(repository)
        payload = manifest_payload("bank", [bank_item()])

        result = service.register(payload, actor="operator", reason="monthly_reconciliation")
        self.assertTrue(result["created"])
        with self.assertRaisesRegex(ValueError, "actor"):
            service.register(payload, actor="", reason="monthly_reconciliation")
        with self.assertRaisesRegex(ValueError, "reason"):
            service.revoke("evidence-1", actor="operator", reason="")


if __name__ == "__main__":
    unittest.main()
