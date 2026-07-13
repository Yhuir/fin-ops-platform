from __future__ import annotations

import json
import os
import pickle
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.services.cost_statistics_read_model_service import COST_STATISTICS_READ_MODEL_SCHEMA_VERSION
from fin_ops_platform.services.import_file_service import FileImportPreviewItem
from fin_ops_platform.services.runtime_paths import default_data_dir
from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.tax_offset_read_model_service import TAX_OFFSET_READ_MODEL_SCHEMA_VERSION


class StateStoreTests(unittest.TestCase):
    def test_default_data_dir_honors_environment_override(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"FIN_OPS_DATA_DIR": temp_dir}):
                self.assertEqual(default_data_dir(), Path(temp_dir))

    def test_local_manual_oa_imports_are_persisted_idempotently_and_removable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))

            first = store.add_manual_oa_imports(["oa-exp-1981", "oa-exp-1981"], "tester", {"source": "unit"})
            second = store.add_manual_oa_imports(["oa-exp-1981"], "tester", {"source": "unit"})
            removed = store.remove_manual_oa_import("oa-exp-1981", "tester")
            loaded = store.load_manual_oa_imports()

        self.assertEqual(first["imported"], ["oa-exp-1981"])
        self.assertEqual(first["already_imported"], [])
        self.assertEqual(second["imported"], [])
        self.assertEqual(second["already_imported"], ["oa-exp-1981"])
        self.assertTrue(removed)
        self.assertEqual(loaded["row_ids"], [])
        self.assertEqual(loaded["entries"], {})
        self.assertEqual([event["operation"] for event in loaded["audit_log"]], ["import", "import", "remove"])

    def test_state_store_load_ignores_app_mongo_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            store = ApplicationStateStore(data_dir)

        self.assertEqual(store.storage_backend, "local_pickle")
        self.assertEqual(store.storage_mode, "local_pickle")
        self.assertIsNone(store.mongo_database_name)

    def test_serialize_file_import_preview_item_tolerates_missing_new_fields_from_old_pickle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            item = FileImportPreviewItem(
                id="import_file_0001",
                file_name="old.xlsx",
                template_code=None,
                batch_type=None,
                status="unrecognized_template",
                message="无法识别文件模板。",
                row_count=0,
            )
            delattr(item, "selected_bank_short_name")

            serialized = store._serialize_value(item)

        self.assertIn("selected_bank_short_name", serialized)
        self.assertIsNone(serialized["selected_bank_short_name"])

    def test_etc_files_persist_locally_and_reject_legacy_gridfs_refs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            reconciliation_path = store.store_etc_reconciliation_file(
                task_id="task-1",
                file_id="file-1",
                file_name="source.xlsx",
                content=b"source",
            )
            invoice_path = store.store_etc_invoice_file(
                invoice_number="INV/1",
                file_name="invoice.pdf",
                content=b"invoice",
            )

            self.assertEqual(store.read_etc_reconciliation_file(reconciliation_path), b"source")
            self.assertEqual(store.read_etc_invoice_file(invoice_path), b"invoice")
            self.assertTrue(store.etc_invoice_file_exists(invoice_path))
            self.assertFalse(store.etc_invoice_file_exists("gridfs://legacy-id/file.pdf"))
            with self.assertRaisesRegex(RuntimeError, "Legacy GridFS ETC invoice file access is disabled"):
                store.read_etc_invoice_file("gridfs://legacy-id/file.pdf")

            store.delete_etc_invoice_file(invoice_path)

        self.assertFalse(Path(invoice_path).exists())

    def test_etc_states_persist_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)

            store.save_etc_state({"business_batches": {"batch-1": {"status": "submitted"}}})
            store.save_etc_reconciliation_state({"tasks": {"task-1": {"status": "completed"}}})

            reloaded = ApplicationStateStore(data_dir)

            self.assertEqual(
                reloaded.load_etc_state(),
                {"business_batches": {"batch-1": {"status": "submitted"}}},
            )
            self.assertEqual(
                reloaded.load_etc_reconciliation_state(),
                {"tasks": {"task-1": {"status": "completed"}}},
            )

    def test_historical_etc_repair_persists_locally_and_rejects_legacy_gridfs_refs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)

            bundle = store.save_historical_etc_repair_bundle(
                bundle_id="bundle-1",
                file_name="seed.zip",
                content=b"seed-content",
                metadata={"source": "test"},
            )
            parsed_seed = store.save_historical_etc_repair_parsed_seed(
                bundle_id="bundle-1",
                parsed_seed={"invoice_count": 2},
            )
            store.save_historical_etc_repair_states({"bundle-1": {"status": "completed"}})

            reloaded = ApplicationStateStore(data_dir)

            self.assertEqual(Path(bundle["stored_file_path"]).read_bytes(), b"seed-content")
            self.assertEqual(
                reloaded.read_historical_etc_repair_bundle("bundle-1")["content"],
                b"seed-content",
            )
            self.assertEqual(reloaded.load_historical_etc_repair_parsed_seed("bundle-1"), parsed_seed)
            self.assertEqual(reloaded.load_historical_etc_repair_states(), {"bundle-1": {"status": "completed"}})

            metadata = reloaded.load_historical_etc_repair_bundle_metadata()
            metadata["legacy"] = {
                "_id": "legacy",
                "bundle_id": "legacy",
                "file_name": "legacy.zip",
                "stored_file_path": "gridfs://legacy-id/legacy.zip",
            }
            (data_dir / "historical_etc_repair" / "bundles.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "Legacy GridFS historical ETC repair bundle access is disabled"):
                reloaded.read_historical_etc_repair_bundle("legacy")

    def test_state_store_persists_and_loads_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            payload = {
                "imports": {"batch_counter": 4},
                "file_imports": {"session_counter": 2},
                "matching": {"run_counter": 2},
            }
            store = ApplicationStateStore(data_dir)

            store.save(payload)
            loaded = ApplicationStateStore(data_dir).load()

            self.assertEqual(store.storage_backend, "local_pickle")
            self.assertIsNone(store.mongo_database_name)
            self.assertEqual(loaded, payload)

    def test_narrow_invoice_persistence_merges_without_replacing_other_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            store.save(
                {
                    "imports": {
                        "batch_counter": 2,
                        "invoices": [{"id": "invoice-1", "amount": "10.00"}],
                    },
                    "file_imports": {"session_counter": 3},
                }
            )

            store.save_invoice_etc_metadata(
                [
                    {"id": "invoice-1", "amount": "10.00", "etc_invoice_id": "etc-1"},
                    {"id": "invoice-2", "amount": "20.00"},
                ]
            )

            loaded = store.load()
            self.assertEqual(loaded["file_imports"], {"session_counter": 3})
            self.assertEqual(loaded["imports"]["batch_counter"], 2)
            self.assertEqual(
                loaded["imports"]["invoices"],
                [
                    {"id": "invoice-1", "amount": "10.00", "etc_invoice_id": "etc-1"},
                    {"id": "invoice-2", "amount": "20.00"},
                ],
            )

    def test_import_delta_merges_batches_facts_and_sessions_without_replacing_existing_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            store.save(
                {
                    "imports": {
                        "batch_counter": 1,
                        "batches": {"batch-1": {"id": "batch-1"}},
                        "invoices": [{"id": "invoice-1"}],
                        "transactions": [],
                    },
                    "file_imports": {
                        "session_counter": 1,
                        "sessions": {"session-1": {"id": "session-1"}},
                    },
                    "matching": {"run_counter": 4},
                }
            )

            store.save_import_delta(
                {
                    "imports": {
                        "batch_counter": 2,
                        "batches": {"batch-2": {"id": "batch-2"}},
                        "invoices": [],
                        "transactions": [{"id": "transaction-2"}],
                    },
                    "file_imports": {
                        "session_counter": 2,
                        "sessions": {"session-2": {"id": "session-2"}},
                    },
                }
            )

            loaded = store.load()
            self.assertEqual(set(loaded["imports"]["batches"]), {"batch-1", "batch-2"})
            self.assertEqual(loaded["imports"]["invoices"], [{"id": "invoice-1"}])
            self.assertEqual(loaded["imports"]["transactions"], [{"id": "transaction-2"}])
            self.assertEqual(set(loaded["file_imports"]["sessions"]), {"session-1", "session-2"})
            self.assertEqual(loaded["matching"], {"run_counter": 4})

    def test_application_state_store_ignores_app_mongo_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            legacy_payload = {"imports": {"batch_counter": 9}, "file_imports": {"session_counter": 3}}
            with (data_dir / "state.pkl").open("wb") as handle:
                pickle.dump(legacy_payload, handle)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            store = ApplicationStateStore(data_dir)
            loaded = store.load()

            self.assertEqual(store.storage_backend, "local_pickle")
            self.assertEqual(loaded, legacy_payload)

    def test_save_workbench_overrides_persists_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "case_counter": 3,
                "row_overrides": {
                    "txn_imported_0001": {
                        "case_id": "CASE-API-0001",
                        "relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                        "available_actions": ["detail"],
                    }
                },
            }

            store = ApplicationStateStore(data_dir)
            store.save_workbench_overrides(snapshot)

            loaded = ApplicationStateStore(data_dir).load()

        self.assertEqual(loaded["workbench_overrides"], snapshot)

    def test_save_workbench_overrides_accepts_changed_rows_for_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "case_counter": 7,
                "row_overrides": {
                    "row_a": {"case_id": "CASE-A", "detail_note": "new a"},
                    "row_b": {"case_id": "CASE-B", "detail_note": "old b"},
                },
            }

            store = ApplicationStateStore(data_dir)
            store.save_workbench_overrides(snapshot, changed_row_ids=["row_a"])

            loaded = ApplicationStateStore(data_dir).load()

        self.assertEqual(loaded["workbench_overrides"], snapshot)

    def test_save_workbench_exception_cases_persists_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {"cases": {"case-1": {"case_id": "case-1", "status": "active"}}}

            store = ApplicationStateStore(data_dir)
            store.save_workbench_exception_cases(snapshot)

            loaded = ApplicationStateStore(data_dir).load()

        self.assertEqual(loaded["workbench_exception_cases"], snapshot)

    def test_bank_transaction_categories_persist_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "records": {
                    "txn-1": {
                        "transaction_id": "txn-1",
                        "category": "service_fee",
                        "source": "manual",
                    }
                }
            }

            store = ApplicationStateStore(data_dir)
            store.save_bank_transaction_categories(snapshot)

            reloaded = ApplicationStateStore(data_dir)

            self.assertEqual(reloaded.load_bank_transaction_categories(), snapshot)

    def test_save_workbench_pair_relations_persists_and_loads_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "pair_relations": {
                    "CASE-PAIR-001": {
                        "case_id": "CASE-PAIR-001",
                        "row_ids": ["oa-001", "bk-001"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "all",
                        "created_by": "YNSYLP005",
                        "created_at": "2026-04-08T10:00:00+00:00",
                        "updated_at": "2026-04-08T10:00:00+00:00",
                    }
                }
            }

            store = ApplicationStateStore(data_dir)
            store.save_workbench_pair_relations(snapshot)
            loaded = ApplicationStateStore(data_dir).load_workbench_pair_relations()

            self.assertEqual(loaded, snapshot)

    def test_save_workbench_pair_relations_can_incrementally_update_changed_case_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            store.save_workbench_pair_relations(
                {
                    "pair_relations": {
                        "CASE-A": {"case_id": "CASE-A", "status": "active"},
                        "CASE-B": {"case_id": "CASE-B", "status": "active"},
                    }
                }
            )
            store.save_workbench_pair_relations(
                {"pair_relations": {"CASE-A": {"case_id": "CASE-A", "status": "cancelled"}}},
                changed_case_ids=["CASE-A"],
            )

            loaded = ApplicationStateStore(data_dir).load_workbench_pair_relations()

        self.assertEqual(loaded["pair_relations"]["CASE-A"]["status"], "cancelled")
        self.assertEqual(loaded["pair_relations"]["CASE-B"]["status"], "active")

    def test_save_workbench_pair_relations_persists_history_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "pair_relations": {
                    "CASE-A": {
                        "case_id": "CASE-A",
                        "row_ids": ["oa-1", "bk-1"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                    }
                },
                "pair_relation_history": [
                    {
                        "operation_id": "op-1",
                        "operation_type": "confirm_link",
                        "before_relations": [],
                        "after_relations": [{"case_id": "CASE-A", "row_ids": ["oa-1", "bk-1"]}],
                        "affected_row_ids": ["oa-1", "bk-1"],
                        "note": "金额不一致说明",
                        "amount_check": {"status": "mismatch"},
                        "created_by": "test",
                        "created_at": "2026-05-02T00:00:00+00:00",
                    }
                ],
            }
            store = ApplicationStateStore(data_dir)
            store.save_workbench_pair_relations(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load_workbench_pair_relations()

        self.assertEqual(loaded["pair_relation_history"][0]["operation_type"], "confirm_link")
        self.assertEqual(loaded["pair_relation_history"][0]["amount_check"]["status"], "mismatch")

    def test_save_submitted_no_oa_bank_batches_persists_and_loads_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "schema_version": "2026-05-no-oa-bank-batch-v1",
                "batches": {
                    "no_oa_batch_001": {
                        "batch_id": "no_oa_batch_001",
                        "batch_type": "fee",
                        "status": "draft",
                        "row_ids": ["bk-fee-001"],
                    }
                },
                "audit_log": [{"operation": "submit", "batch_id": "no_oa_batch_001"}],
            }

            store = ApplicationStateStore(data_dir)
            store.save_no_oa_bank_batches(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load_no_oa_bank_batches()

        self.assertEqual(loaded, snapshot)

    def test_bank_flow_rule_batches_use_independent_local_snapshot_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            no_oa_snapshot = {"batches": {"no-oa": {"batch_id": "no-oa"}}}
            bank_flow_snapshot = {
                "batches": {
                    "bank-flow": {
                        "batch_id": "bank-flow",
                        "relation_mode": "bank_flow_rule_batch",
                    }
                }
            }

            store = ApplicationStateStore(data_dir)
            store.save_no_oa_bank_batches(no_oa_snapshot)
            store.save_bank_flow_rule_batches(bank_flow_snapshot)
            reloaded = ApplicationStateStore(data_dir)

            self.assertEqual(reloaded.load_no_oa_bank_batches(), no_oa_snapshot)
            self.assertEqual(reloaded.load_bank_flow_rule_batches(), bank_flow_snapshot)

    def test_oa_pending_payment_bank_relations_persist_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "relations": {
                    "relation-1": {
                        "relation_id": "relation-1",
                        "status": "confirmed",
                    }
                }
            }

            store = ApplicationStateStore(data_dir)
            store.save_oa_pending_payment_bank_relations(snapshot)

            reloaded = ApplicationStateStore(data_dir)

            self.assertEqual(reloaded.load_oa_pending_payment_bank_relations(), snapshot)

    def test_tax_imports_and_offset_plan_persist_locally(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            tax_imports = {
                "sessions": {"session-1": {"status": "completed"}},
                "batches": {},
                "records": {},
            }
            plan = {"id": "plan-1", "idempotency_key": "idem-1", "amount": "100.00"}

            store.save_tax_certified_imports(tax_imports)
            saved_plan = store.save_tax_offset_plan(plan)
            duplicate_plan = store.save_tax_offset_plan({"id": "plan-2", "idempotency_key": "idem-1"})

            reloaded = ApplicationStateStore(data_dir)

            self.assertEqual(reloaded.load_tax_certified_imports(), tax_imports)
            self.assertEqual(saved_plan, plan)
            self.assertEqual(duplicate_plan, plan)

    def test_save_no_oa_bank_batches_persists_and_loads_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "schema_version": "2026-05-no-oa-bank-batch-v1",
                "batches": {
                    "no_oa_batch_001": {
                        "batch_id": "no_oa_batch_001",
                        "batch_type": "fee",
                        "status": "submitted",
                        "row_ids": ["bk-fee-001"],
                    }
                },
                "audit_log": [{"operation": "submit", "batch_id": "no_oa_batch_001"}],
            }

            store = ApplicationStateStore(data_dir)
            store.save_no_oa_bank_batches(snapshot)
            loaded = ApplicationStateStore(data_dir).load_no_oa_bank_batches()

            self.assertEqual(loaded, snapshot)

    def test_save_workbench_read_models_persists_and_loads_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "read_models": {
                    "all": {
                        "scope_key": "all",
                        "scope_type": "all_time",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 3}},
                    }
                }
            }

            store = ApplicationStateStore(data_dir)
            store.save_workbench_read_models(snapshot)
            loaded = ApplicationStateStore(data_dir).load_workbench_read_models()

            self.assertEqual(loaded, snapshot)

    def test_save_no_oa_bank_batch_mutation_uses_explicit_local_boundary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)

            store.save_no_oa_bank_batch_mutation(
                pair_relation_snapshot={
                    "pair_relations": {
                        "CASE-1": {"case_id": "CASE-1", "row_ids": ["bank-1"]},
                    }
                },
                no_oa_bank_batch_snapshot={
                    "batches": {
                        "batch-1": {"batch_id": "batch-1", "status": "submitted"},
                    }
                },
                workbench_read_model_snapshot={
                    "read_models": {
                        "2026-05": {"scope_key": "2026-05", "payload": {"rows": []}},
                    }
                },
                changed_case_ids=["CASE-1"],
                changed_scope_keys=["2026-05"],
            )

            reloaded = ApplicationStateStore(data_dir)
            pair_snapshot = reloaded.load_workbench_pair_relations()
            no_oa_snapshot = reloaded.load_no_oa_bank_batches()
            workbench_snapshot = reloaded.load_workbench_read_models()

        self.assertEqual(pair_snapshot["pair_relations"]["CASE-1"]["row_ids"], ["bank-1"])
        self.assertEqual(no_oa_snapshot["batches"]["batch-1"]["status"], "submitted")
        self.assertEqual(workbench_snapshot["read_models"]["2026-05"]["scope_key"], "2026-05")

    def test_save_bank_flow_rule_batch_mutation_uses_local_bank_flow_boundary_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)

            store.save_bank_flow_rule_batch_mutation(
                pair_relation_snapshot={
                    "pair_relations": {
                        "CASE-1": {"case_id": "CASE-1", "row_ids": ["bank-1"]},
                    }
                },
                bank_flow_rule_batch_snapshot={
                    "batches": {
                        "batch-1": {"batch_id": "batch-1", "status": "submitted"},
                    }
                },
                changed_case_ids=["CASE-1"],
                changed_scope_keys=["all", "visibility:paired:2026-05"],
            )

            reloaded = ApplicationStateStore(data_dir)
            pair_snapshot = reloaded.load_workbench_pair_relations()
            bank_flow_snapshot = reloaded.load_bank_flow_rule_batches()
            workbench_snapshot = reloaded.load_workbench_read_models()

        self.assertEqual(pair_snapshot["pair_relations"]["CASE-1"]["row_ids"], ["bank-1"])
        self.assertEqual(bank_flow_snapshot["batches"]["batch-1"]["status"], "submitted")
        self.assertEqual(workbench_snapshot, {})

    def test_local_snapshot_persists_and_loads_workbench_candidate_matches(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "imports": {},
                "file_imports": {},
                "matching": {},
                "workbench_candidate_matches": {
                    "candidates": {
                        "candidate:001": {
                            "candidate_key": "candidate:001",
                            "scope_month": "2026-05",
                            "status": "needs_review",
                        }
                    }
                },
            }

            store = ApplicationStateStore(data_dir)
            store.save(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load()

        self.assertEqual(loaded["workbench_candidate_matches"], snapshot["workbench_candidate_matches"])

    def test_save_workbench_candidate_matches_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "candidates": {
                    "candidate:001": {
                        "candidate_id": "candidate:001",
                        "candidate_key": "candidate:001",
                        "scope_month": "2026-05",
                        "candidate_type": "oa_bank_invoice",
                        "status": "needs_review",
                        "confidence": "medium",
                        "rule_code": "same_amount",
                        "row_ids": ["oa-001", "bank-001"],
                        "generated_at": "2026-05-06T10:00:00+00:00",
                    }
                }
            }

            store = ApplicationStateStore(data_dir)
            store.save_workbench_candidate_matches(snapshot)
            loaded = ApplicationStateStore(data_dir).load_workbench_candidate_matches()

            self.assertEqual(loaded, snapshot)

    def test_save_turnover_relations_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "schema_version": "test",
                "relations": [
                    {
                        "relation_id": "turnover_rel_001",
                        "status": "suggested",
                        "bank_row_ids": ["txn-1"],
                        "sync_to_workbench": False,
                    }
                ],
                "audit_log": [
                    {
                        "relation_id": "turnover_rel_001",
                        "action": "seed",
                        "actor": "YNSYLP005",
                    }
                ],
            }

            store = ApplicationStateStore(data_dir)
            store.save_turnover_relations(snapshot)
            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load_turnover_relations()
            audit_log = reloaded.load_turnover_relation_audit_log()

            self.assertEqual(loaded, snapshot)
            self.assertEqual(audit_log, snapshot["audit_log"])

    def test_save_turnover_ledger_extras_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "version": 1,
                "extras": [
                    {
                        "relation_id": "turnover_rel_001",
                        "interest_rate_type": "annual",
                        "interest_rate_value": "0.060000",
                        "interest_paid_amount": "0.00",
                        "interest_paid_date": None,
                        "interest_payment_method": "",
                        "note": "页面内维护备注",
                        "updated_at": "2026-05-12T10:00:00+08:00",
                        "updated_by": "YNSYLP005",
                    }
                ],
            }

            store = ApplicationStateStore(data_dir)
            store.save_turnover_ledger_extras(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load_turnover_ledger_extras()

        self.assertEqual(loaded, snapshot)

    def test_save_workbench_candidate_matches_accepts_changed_months_for_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            snapshot = {
                "scope_runs": {},
                "candidates": {
                    "candidate:new-mar": {
                        "candidate_id": "candidate:new-mar",
                        "candidate_key": "candidate:new-mar",
                        "scope_month": "2026-03",
                    },
                    "candidate:keep-apr": {
                        "candidate_id": "candidate:keep-apr",
                        "candidate_key": "candidate:keep-apr",
                        "scope_month": "2026-04",
                    },
                },
            }

            store.save_workbench_candidate_matches(snapshot, changed_scope_months=["2026-03"])
            loaded = ApplicationStateStore(data_dir).load_workbench_candidate_matches()

        self.assertEqual(loaded, snapshot)

    def test_save_workbench_read_models_accepts_changed_scopes_for_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            snapshot = {
                "read_models": {
                    "all": {"scope_key": "all", "payload": {"summary": {"paired_count": 9}}},
                    "2026-03": {"scope_key": "2026-03", "payload": {"summary": {"paired_count": 2}}},
                }
            }

            store.save_workbench_read_models(snapshot, changed_scope_keys=["all"])
            loaded = ApplicationStateStore(data_dir).load_workbench_read_models()

        self.assertEqual(loaded, snapshot)

    def test_save_workbench_matching_dirty_scopes_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "dirty_scopes": {
                    "2026-03": {
                        "scope_month": "2026-03",
                        "reasons": ["manual_category_dirty"],
                    }
                }
            }

            store = ApplicationStateStore(data_dir)
            store.save_workbench_matching_dirty_scopes(snapshot)
            loaded = ApplicationStateStore(data_dir).load().get("workbench_matching_dirty_scopes")

        self.assertEqual(loaded, snapshot)

    def test_save_cost_statistics_read_models_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "read_models": {
                    "active:2026-05": {
                        "scope_key": "active:2026-05",
                        "scope_type": "month",
                        "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                        "month": "2026-05",
                        "project_scope": "active",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "entry_count": 3,
                        "payload": {"summary": {"transaction_count": 3}},
                        "source_scope_keys": ["workbench:2026-05"],
                    }
                }
            }
            store = ApplicationStateStore(data_dir)
            store.save_cost_statistics_read_models(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load_cost_statistics_read_models()

        self.assertEqual(loaded, snapshot)

    def test_save_cost_statistics_read_models_accepts_changed_scopes_for_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            snapshot = {
                "read_models": {
                    "active:2026-04": {
                        "scope_key": "active:2026-04",
                        "payload": {"summary": {"transaction_count": 1}},
                    },
                    "active:2026-05": {
                        "scope_key": "active:2026-05",
                        "scope_type": "month",
                        "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                        "month": "2026-05",
                        "project_scope": "active",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "entry_count": 9,
                        "payload": {"summary": {"transaction_count": 9}},
                    },
                }
            }

            store.save_cost_statistics_read_models(snapshot, changed_scope_keys=["active:2026-05"])
            loaded = ApplicationStateStore(data_dir).load_cost_statistics_read_models()

            self.assertEqual(loaded, snapshot)
            self.assertEqual(loaded["read_models"]["active:2026-05"]["entry_count"], 9)

    def test_save_tax_offset_read_models_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "scope_type": "month",
                        "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                        "month": "2026-05",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "output_count": 2,
                        "input_plan_count": 1,
                        "certified_count": 3,
                        "payload": {
                            "output_items": [{"id": "output-1"}, {"id": "output-2"}],
                            "input_plan_items": [{"id": "input-1"}],
                            "certified_items": [{"id": "cert-1"}, {"id": "cert-2"}, {"id": "cert-3"}],
                        },
                        "source_scope_keys": ["tax-offset:source:2026-05"],
                    }
                }
            }
            store = ApplicationStateStore(data_dir)
            store.save_tax_offset_read_models(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load_tax_offset_read_models()

        self.assertEqual(loaded, snapshot)

    def test_save_tax_offset_read_models_accepts_changed_scopes_for_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            snapshot = {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "scope_type": "month",
                        "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                        "month": "2026-05",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "output_count": 2,
                        "input_plan_count": 1,
                        "certified_count": 3,
                        "payload": {
                            "output_items": [{"id": "output-1"}, {"id": "output-2"}],
                            "input_plan_items": [{"id": "input-1"}],
                            "certified_items": [
                                {"id": "cert-1"},
                                {"id": "cert-2"},
                                {"id": "cert-3"},
                            ],
                        },
                        "source_scope_keys": ["tax-offset:source:2026-05"],
                    }
                }
            }

            store.save_tax_offset_read_models(snapshot, changed_scope_keys=["2026-05", "2026-04"])
            loaded = ApplicationStateStore(data_dir).load_tax_offset_read_models()

            self.assertEqual(loaded, snapshot)
            self.assertEqual(loaded["read_models"]["2026-05"]["certified_count"], 3)

    def test_store_import_file_round_trips_locally(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)

            stored_path = store.store_import_file(
                session_id="import_session_0001",
                file_id="import_file_0001",
                file_name="全量发票查询导出结果-2026年1月.xlsx",
                content=b"invoice-content",
            )
            loaded = store.read_import_file(stored_path)

            self.assertTrue(Path(stored_path).exists())
            self.assertEqual(loaded, b"invoice-content")
            with self.assertRaises(RuntimeError):
                store.read_import_file("gridfs://legacy-file/invoice.xlsx")
            self.assertEqual(store.delete_import_files([stored_path, "gridfs://legacy-file/invoice.xlsx"]), 1)
            self.assertFalse(Path(stored_path).exists())

    def test_pending_invoice_commands_persist_locally(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {"req-1": {"request_id": "req-1", "status": "pending"}}

            ApplicationStateStore(data_dir).save_pending_invoice_commands(snapshot)
            loaded = ApplicationStateStore(data_dir).load_pending_invoice_commands()

            self.assertEqual(loaded, snapshot)

    def test_oa_attachment_invoice_cache_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            store.save_oa_attachment_invoice_cache_entry(
                "cache-key-001",
                {"invoices": [{"invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}]},
            )

            reloaded_store = ApplicationStateStore(data_dir)
            cached = reloaded_store.load_oa_attachment_invoice_cache_entry("cache-key-001")

        self.assertEqual(
            cached,
            {
                "cache_key": "cache-key-001",
                "invoices": [{"invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}],
            },
        )

    def test_oa_sync_state_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            store.save_oa_sync_state({"poll_fingerprints": {"2026-03": "fingerprint-001", "all": "fingerprint-all"}})

            reloaded_store = ApplicationStateStore(data_dir)
            state = reloaded_store.load_oa_sync_state()

        self.assertEqual(state["poll_fingerprints"], {"2026-03": "fingerprint-001", "all": "fingerprint-all"})

    def test_background_jobs_persist_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            snapshot = {
                "job-1": {
                    "job_id": "job-1",
                    "type": "import",
                    "status": "running",
                }
            }

            store.save_background_jobs(snapshot)
            reloaded_store = ApplicationStateStore(data_dir)

            self.assertEqual(reloaded_store.load_background_jobs(), snapshot)

    def test_app_health_alerts_persist_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            snapshot = {
                "records": {
                    "alert_1": {
                        "alert_id": "alert_1",
                        "kind": "dependency_unavailable",
                        "severity": "critical",
                        "status": "active",
                    }
                }
            }

            store.save_app_health_alerts(snapshot)
            reloaded_store = ApplicationStateStore(data_dir)

            self.assertEqual(reloaded_store.load_app_health_alerts(), snapshot)

    def test_app_health_alerts_save_and_load_local_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {"records": {"alert_1": {"alert_id": "alert_1", "status": "active"}}}

            store = ApplicationStateStore(data_dir)
            store.save_app_health_alerts(snapshot)
            loaded = ApplicationStateStore(data_dir).load_app_health_alerts()

            self.assertEqual(loaded, snapshot)

    def test_oa_attachment_invoice_cache_save_load_and_clear_locally(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            store.save_oa_attachment_invoice_cache_entry(
                "cache-key-001",
                {"invoices": [{"invoice_no": "40512344"}]},
            )
            cached = ApplicationStateStore(data_dir).load_oa_attachment_invoice_cache_entry("cache-key-001")
            deleted_count = ApplicationStateStore(data_dir).clear_oa_attachment_invoice_cache()

            self.assertEqual(cached, {"cache_key": "cache-key-001", "invoices": [{"invoice_no": "40512344"}]})
            self.assertEqual(deleted_count, 1)
            self.assertIsNone(ApplicationStateStore(data_dir).load_oa_attachment_invoice_cache_entry("cache-key-001"))


if __name__ == "__main__":
    unittest.main()
