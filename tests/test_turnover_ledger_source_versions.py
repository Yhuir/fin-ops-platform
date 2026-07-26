from __future__ import annotations

import unittest

from fin_ops_platform.services.turnover_ledger_source_versions import (
    build_turnover_ledger_source_versions,
    turnover_manual_closure_source_version,
)


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
        closure_source_version: dict[str, object] | None = None,
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
            turnover_manual_closure_source_version_provider=(
                (lambda: dict(closure_source_version))
                if closure_source_version is not None
                else None
            ),
            oa_projection_sync_version=oa_projection_sync_version,
        )

    def test_source_versions_include_all_turnover_and_cross_module_inputs(self) -> None:
        versions = self._versions()

        self.assertIn("turnover_ledger_schema_version", versions)
        self.assertEqual(versions["turnover_ledger_schema_version"], "2026-07-turnover-ledger-v11")
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

        relation_changed = self._versions(
            relation_snapshot={"relations": [{"relation_id": "rel-1", "status": "confirmed"}]}
        )
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

    def test_source_versions_track_canonical_turnover_manual_closure_relations(self) -> None:
        baseline = self._versions(
            closure_source_version={
                "source": "workbench_pair_relations",
                "scope_key": "all",
                "relation_count": 0,
                "relation_updated_at": "",
            }
        )
        changed = self._versions(
            closure_source_version={
                "source": "workbench_pair_relations",
                "scope_key": "all",
                "relation_count": 1,
                "relation_updated_at": "2026-07-23 20:00:00+08",
            }
        )

        self.assertNotEqual(
            baseline["turnover_manual_closure_source_version"],
            changed["turnover_manual_closure_source_version"],
        )

    def test_canonical_closure_source_version_uses_relation_mode_filter(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def workbench_relation_source_summary_from_source(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(dict(kwargs))
                return {
                    "source": "workbench_pair_relations",
                    "scope_key": "all",
                    "relation_count": 2,
                    "relation_updated_at": "2026-07-23 20:00:00+08",
                }

        repository = Repository()

        payload = turnover_manual_closure_source_version(repository)

        self.assertEqual(payload["relation_count"], 2)
        self.assertEqual(
            repository.calls,
            [{"scope_key": "all", "relation_modes": ["turnover_manual_closure"]}],
        )

    def test_relation_projection_version_tracks_active_confirmed_relations_only(self) -> None:
        baseline = self._versions(relation_snapshot={"relations": [], "audit_log": []})
        confirmed = self._versions(
            relation_snapshot={
                "relations": [
                    {"relation_id": "rel-2", "status": "confirmed", "bank_row_ids": ["bank-2"]},
                    {"relation_id": "rel-1", "status": "confirmed", "bank_row_ids": ["bank-1"]},
                ],
                "audit_log": [{"relation_id": "rel-1", "action": "confirm_relation"}],
            }
        )
        confirmed_reordered = self._versions(
            relation_snapshot={
                "relations": [
                    {"relation_id": "rel-1", "status": "confirmed", "bank_row_ids": ["bank-1"]},
                    {"relation_id": "rel-2", "status": "confirmed", "bank_row_ids": ["bank-2"]},
                ],
                "audit_log": [{"relation_id": "rel-2", "action": "confirm_relation"}],
            }
        )
        withdrawn = self._versions(
            relation_snapshot={
                "relations": [{"relation_id": "rel-1", "status": "withdrawn", "bank_row_ids": ["bank-1"]}],
                "audit_log": [
                    {"relation_id": "rel-1", "action": "confirm_relation"},
                    {"relation_id": "rel-1", "action": "withdraw_relation"},
                ],
            }
        )
        audit_only = self._versions(
            relation_snapshot={
                "relations": [],
                "audit_log": [{"relation_id": "rel-old", "action": "withdraw_relation"}],
            }
        )

        self.assertNotEqual(
            baseline["turnover_relation_snapshot_version"],
            confirmed["turnover_relation_snapshot_version"],
        )
        self.assertEqual(
            confirmed["turnover_relation_snapshot_version"],
            confirmed_reordered["turnover_relation_snapshot_version"],
        )
        self.assertEqual(
            baseline["turnover_relation_snapshot_version"],
            withdrawn["turnover_relation_snapshot_version"],
        )
        self.assertEqual(
            baseline["turnover_relation_snapshot_version"],
            audit_only["turnover_relation_snapshot_version"],
        )


if __name__ == "__main__":
    unittest.main()
