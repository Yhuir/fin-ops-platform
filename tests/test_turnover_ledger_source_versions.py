from __future__ import annotations

import unittest

from fin_ops_platform.services.turnover_ledger_source_versions import build_turnover_ledger_source_versions


class FakeRelationService:
    def __init__(self, snapshot: dict[str, object]) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> dict[str, object]:
        return self._snapshot


class FakeAppSettingsService:
    def __init__(self, *, tag_selection: dict[str, object], bank_rules_version: int = 1) -> None:
        self._tag_selection = tag_selection
        self._bank_rules_version = bank_rules_version

    def get_turnover_ledger_tag_selection_payload(self) -> dict[str, object]:
        return self._tag_selection

    def get_bank_auto_tag_rules_payload(self) -> dict[str, object]:
        return {"version": self._bank_rules_version}


class FakeBankTransactionCategoryService:
    def __init__(self, snapshot: dict[str, object]) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> dict[str, object]:
        return self._snapshot


class TurnoverLedgerSourceVersionsTests(unittest.TestCase):
    def _versions(
        self,
        *,
        relation_snapshot: dict[str, object] | None = None,
        extra_snapshot: dict[str, object] | None = None,
        tag_selection: dict[str, object] | None = None,
        bank_category_snapshot: dict[str, object] | None = None,
        bank_rules_version: int = 1,
        oa_projection_sync_version: str | None = "oa-v1",
    ) -> dict[str, object]:
        return build_turnover_ledger_source_versions(
            relation_service=FakeRelationService(relation_snapshot or {"relations": []}),
            extra_snapshot_provider=lambda: extra_snapshot or {"extras": []},
            app_settings_service=FakeAppSettingsService(
                tag_selection=tag_selection or {"version": 1, "selected_tag_codes": []},
                bank_rules_version=bank_rules_version,
            ),
            bank_transaction_category_service=FakeBankTransactionCategoryService(
                bank_category_snapshot or {"categories": []}
            ),
            oa_projection_sync_version=oa_projection_sync_version,
        )

    def test_source_versions_include_all_turnover_and_cross_module_inputs(self) -> None:
        versions = self._versions()

        self.assertIn("turnover_ledger_schema_version", versions)
        self.assertEqual(versions["turnover_ledger_schema_version"], "2026-07-turnover-ledger-v6")
        self.assertIn("turnover_relation_schema_version", versions)
        self.assertIn("bank_transaction_category_schema_version", versions)
        self.assertIn("bank_auto_tag_rules_version", versions)
        self.assertIn("turnover_relation_snapshot_version", versions)
        self.assertIn("turnover_ledger_extras_snapshot_version", versions)
        self.assertIn("turnover_ledger_tag_selection_snapshot_version", versions)
        self.assertIn("bank_transaction_category_snapshot_version", versions)
        self.assertEqual(versions["oa_projection_sync_version"], "oa-v1")

    def test_source_versions_change_when_relation_extras_tags_categories_or_rules_change(self) -> None:
        baseline = self._versions()

        relation_changed = self._versions(relation_snapshot={"relations": [{"relation_id": "rel-1"}]})
        extras_changed = self._versions(extra_snapshot={"extras": [{"relation_id": "rel-1", "note": "changed"}]})
        tag_selection_changed = self._versions(tag_selection={"version": 2, "selected_tag_codes": ["turnover"]})
        category_changed = self._versions(bank_category_snapshot={"categories": [{"transaction_id": "bank-1"}]})
        rules_changed = self._versions(bank_rules_version=2)
        oa_changed = self._versions(oa_projection_sync_version="oa-v2")

        self.assertNotEqual(
            baseline["turnover_relation_snapshot_version"],
            relation_changed["turnover_relation_snapshot_version"],
        )
        self.assertNotEqual(
            baseline["turnover_ledger_extras_snapshot_version"],
            extras_changed["turnover_ledger_extras_snapshot_version"],
        )
        self.assertNotEqual(
            baseline["turnover_ledger_tag_selection_snapshot_version"],
            tag_selection_changed["turnover_ledger_tag_selection_snapshot_version"],
        )
        self.assertNotEqual(
            baseline["bank_transaction_category_snapshot_version"],
            category_changed["bank_transaction_category_snapshot_version"],
        )
        self.assertNotEqual(baseline["bank_auto_tag_rules_version"], rules_changed["bank_auto_tag_rules_version"])
        self.assertNotEqual(baseline["oa_projection_sync_version"], oa_changed["oa_projection_sync_version"])


if __name__ == "__main__":
    unittest.main()
