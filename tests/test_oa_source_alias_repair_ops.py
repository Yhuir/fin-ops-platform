from __future__ import annotations

from io import StringIO
import json
import unittest

from fin_ops_platform.services.postgres_repositories.oa_source_alias_repair import (
    PostgresOASourceAliasRepairRepository,
)
from fin_ops_platform.tools import oa_source_alias_repair_ops


ALIAS_ID = "oa-exp-2327"
CANONICAL_ID = "oa-exp-current"


def evidence() -> dict[str, object]:
    return {
        "canonical_count": 1,
        "alias_application_count": 0,
        "existing_canonical_row_id": None,
        "existing_status": None,
        "bridge_item_ids": [f"{ALIAS_ID}:item:0:old", f"{ALIAS_ID}:item:1:old"],
        "bridge_row_indexes": ["0", "1"],
        "attachment_key_hashes": ["a" * 64, "b" * 64],
        "invoice_ids": ["invoice-1", "invoice-2"],
        "invoice_item_ids": [f"{ALIAS_ID}:item:0:old", f"{ALIAS_ID}:item:1:old"],
        "invoice_row_indexes": ["0", "1"],
    }


class FakeRepository:
    def __init__(self, candidate: dict[str, object] | None = None) -> None:
        self.candidate = dict(candidate or evidence())
        self.activations: list[dict[str, object]] = []

    def inspect_candidate(self, **_kwargs: object) -> dict[str, object]:
        return dict(self.candidate)

    def activate_alias(self, **kwargs: object) -> bool:
        self.activations.append(dict(kwargs))
        return True


class CaptureConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[object, ...] = ()

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        self.sql = " ".join(sql.split())
        self.params = params
        return evidence()

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.sql = " ".join(sql.split())
        self.params = params
        return 1


class OASourceAliasRepairOpsTests(unittest.TestCase):
    @staticmethod
    def arguments(mode: str, fingerprint: str | None = None) -> list[str]:
        args = [
            "--alias-row-id",
            ALIAS_ID,
            "--canonical-row-id",
            CANONICAL_ID,
            "--expected-bridge-count",
            "2",
            "--expected-invoice-count",
            "2",
            mode,
        ]
        if fingerprint:
            args.extend(["--expected-fingerprint", fingerprint])
        return args

    def test_dry_run_proves_exact_bridge_and_invoice_evidence_without_writing(self) -> None:
        repository = FakeRepository()
        stdout = StringIO()

        exit_code = oa_source_alias_repair_ops.main(
            self.arguments("--dry-run"), repository=repository, stdout=stdout
        )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["bridge_count"], 2)
        self.assertEqual(report["invoice_count"], 2)
        self.assertEqual(report["row_indexes"], ["0", "1"])
        self.assertFalse(report["written"])
        self.assertEqual(repository.activations, [])

    def test_execute_activates_the_fingerprint_guarded_alias(self) -> None:
        repository = FakeRepository()
        dry_stdout = StringIO()
        oa_source_alias_repair_ops.main(
            self.arguments("--dry-run"), repository=repository, stdout=dry_stdout
        )
        fingerprint = json.loads(dry_stdout.getvalue())["fingerprint"]
        execute_stdout = StringIO()

        oa_source_alias_repair_ops.main(
            self.arguments("--execute", fingerprint),
            repository=repository,
            stdout=execute_stdout,
        )

        report = json.loads(execute_stdout.getvalue())
        self.assertTrue(report["written"])
        self.assertEqual(repository.activations[0]["reason"], "verified_attachment_identity_migration")
        self.assertEqual(repository.activations[0]["evidence_hash"], fingerprint)

    def test_mismatched_bridge_and_invoice_items_fail_closed(self) -> None:
        candidate = evidence()
        candidate["invoice_item_ids"] = [f"{ALIAS_ID}:item:0:old", f"{ALIAS_ID}:item:2:foreign"]

        with self.assertRaisesRegex(RuntimeError, "identities disagree"):
            oa_source_alias_repair_ops.main(
                self.arguments("--dry-run"),
                repository=FakeRepository(candidate),
                stdout=StringIO(),
            )

    def test_repository_uses_bounded_exact_key_evidence_and_guarded_insert(self) -> None:
        connection = CaptureConnection()
        repository = PostgresOASourceAliasRepairRepository(connection)

        repository.inspect_candidate(alias_row_id=ALIAS_ID, canonical_row_id=CANONICAL_ID)

        self.assertIn("join canonical_oa oa on oa.id = attachment.oa_application_id", connection.sql)
        self.assertIn("source.source_attachment_key = owned.source_attachment_key", connection.sql)
        self.assertIn("source.cache_source_attachment_key = owned.source_attachment_key", connection.sql)
        self.assertIn("source_link.value->>'source_type' = 'oa_attachment_invoice'", connection.sql)
        self.assertNotIn("project_name =", connection.sql)
        self.assertNotIn("amount =", connection.sql)

        written = repository.activate_alias(
            alias_row_id=ALIAS_ID,
            canonical_row_id=CANONICAL_ID,
            reason="verified",
            evidence_hash="f" * 64,
            reviewed_by="test",
            raw_payload={"contract": "test"},
        )

        self.assertTrue(written)
        self.assertIn("insert into app.oa_source_aliases", connection.sql)
        self.assertIn("not exists ( select 1 from app.oa_source_aliases alias", connection.sql)


if __name__ == "__main__":
    unittest.main()
