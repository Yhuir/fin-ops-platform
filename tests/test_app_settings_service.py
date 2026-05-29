import json
import tempfile
import unittest
from pathlib import Path

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.oa_role_sync_service import OARoleAssignment
from fin_ops_platform.services.state_store import ApplicationStateStore


class FakeMongoCollection:
    def __init__(self) -> None:
        self.document: dict[str, object] | None = None

    def update_one(self, _filter: dict[str, object], update: dict[str, object], upsert: bool = False) -> None:
        del upsert
        current = dict(self.document or {})
        current.update(dict(update.get("$set") or {}))
        current["_id"] = _filter.get("_id")
        self.document = current

    def find_one(self, _filter: dict[str, object]) -> dict[str, object] | None:
        if self.document is None:
            return None
        if self.document.get("_id") != _filter.get("_id"):
            return None
        return dict(self.document)


class RecordingSyncService:
    def __init__(self) -> None:
        self.assignments: list[OARoleAssignment] | None = None

    def sync_access_control(self, snapshot: dict[str, object]) -> None:
        readonly = [
            OARoleAssignment(username=str(username), tier="read_export_only")
            for username in list(snapshot.get("readonly_export_usernames") or [])
        ]
        full_access = [
            OARoleAssignment(username=str(username), tier="full_access")
            for username in list(snapshot.get("full_access_usernames") or [])
        ]
        admin = [
            OARoleAssignment(username=str(username), tier="admin")
            for username in list(snapshot.get("admin_usernames") or [])
        ]
        self.assignments = [*readonly, *full_access, *admin]


class AppSettingsServiceTests(unittest.TestCase):
    def test_file_rule_replacement_detaches_pending_invoice_and_no_oa_archived_codes_atomically(self) -> None:
        fixture = json.loads(
            Path("fixtures/bank_auto_tag_rules/bank_flow_tag_rules_ui2.normalized.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            current = app._app_settings_service.get_settings_payload()
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                bank_transaction_tags=current["bank_transaction_tags"],
                pending_invoice_tag_groups={
                    "version": current["pending_invoice_tag_groups"]["version"],
                    "groups": {
                        "requires_invoice": {"tag_codes": ["salary"]},
                        "bank_statement_as_invoice": {"tag_codes": []},
                        "no_invoice_required": {"tag_codes": []},
                    },
                },
                actor_id="settings-owner",
            )
            selection = app._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
            app._app_settings_service.update_no_oa_bank_batch_tag_selection(
                {"expected_version": selection["version"], "selected_tag_codes": ["salary"]},
                actor_id="settings-owner",
            )

            result = app._app_settings_service.replace_bank_auto_tag_rules_from_file_source(
                fixture,
                actor_id="settings-owner",
            )

            settings = app._app_settings_service.get_settings_payload()

        self.assertEqual(result["version"], current["bank_transaction_tags"]["version"] + 2)
        self.assertEqual(settings["pending_invoice_tag_groups"]["groups"]["requires_invoice"]["tag_codes"], [])
        self.assertEqual(settings["no_oa_bank_batch_tag_selection"]["selected_tag_codes"], [])
        self.assertEqual(
            settings["no_oa_bank_batch_tag_selection"]["version"],
            3,
        )
        audit = app._audit_service.as_dicts()[-1]
        self.assertEqual(audit["action"], "bank_auto_tag_rules_updated")
        self.assertEqual(
            audit["metadata"]["detached_pending_invoice_tag_references"],
            [{"group_id": "requires_invoice", "label": "需要开票", "tag_code": "salary"}],
        )
        self.assertEqual(
            audit["metadata"]["detached_no_oa_bank_batch_tag_references"],
            [{"tag_code": "salary"}],
        )
        self.assertEqual(audit["metadata"]["source"]["source_name"], "银行流水标签ui2.numbers")

    def test_settings_payload_includes_bank_transaction_tags_and_pending_invoice_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = app._app_settings_service.get_settings_payload()

        definitions_by_code = {
            definition["code"]: definition
            for definition in payload["bank_transaction_tags"]["definitions"]
        }
        self.assertEqual(payload["bank_transaction_tags"]["version"], 1)
        self.assertEqual(definitions_by_code["fee"]["output_primary_label"], "费用")
        self.assertEqual(definitions_by_code["fee"]["output_sub_label"], "手续费")
        self.assertEqual(
            definitions_by_code["borrow_in_company_pending_repayment"],
            {
                "code": "borrow_in_company_pending_repayment",
                "label": "公司暂借款：待还款",
                "path": ["借入", "公司往来款", "待还款"],
                "source": "system",
                "status": "active",
                "output_primary_label": "公司暂借款：待还款",
                "output_sub_label": "",
            },
        )
        self.assertEqual(
            sorted(payload["pending_invoice_tag_groups"]["groups"].keys()),
            [
                "bank_statement_as_invoice",
                "no_invoice_required",
                "requires_invoice",
            ],
        )
        self.assertEqual(payload["pending_invoice_tag_groups"]["version"], 1)

    def test_bank_transaction_tags_and_pending_invoice_mapping_changes_increment_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            initial = app._app_settings_service.get_settings_payload()

            tag_changed = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                bank_transaction_tags={
                    "definitions": [
                        {
                            "code": "custom_no_invoice_meal",
                            "label": "餐费无需发票",
                            "path": ["自定义", "餐费"],
                            "source": "custom",
                            "status": "active",
                        }
                    ],
                },
                pending_invoice_tag_groups=initial["pending_invoice_tag_groups"],
                actor_id="settings-owner",
            )

            mapping_changed = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                bank_transaction_tags=tag_changed["bank_transaction_tags"],
                pending_invoice_tag_groups={
                    "groups": {
                        "requires_invoice": {"tag_codes": ["borrow_in_company_pending_repayment"]},
                        "bank_statement_as_invoice": {"tag_codes": []},
                        "no_invoice_required": {"tag_codes": ["custom_no_invoice_meal"]},
                    }
                },
                actor_id="settings-owner",
            )

        self.assertEqual(tag_changed["bank_transaction_tags"]["version"], 2)
        self.assertEqual(tag_changed["pending_invoice_tag_groups"]["version"], 2)
        self.assertEqual(mapping_changed["bank_transaction_tags"]["version"], 3)
        self.assertEqual(mapping_changed["pending_invoice_tag_groups"]["version"], 3)

    def test_settings_accepts_frontend_tags_alias_before_pending_invoice_mapping_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                bank_transaction_tags={
                    "version": 1,
                    "tags": [
                        {
                            "code": "custom_1779265822964",
                            "label": "利息",
                            "path": ["自定义", "利息"],
                            "source": "custom",
                            "status": "active",
                        }
                    ],
                },
                pending_invoice_tag_groups={
                    "groups": {
                        "requires_invoice": {"tag_codes": []},
                        "bank_statement_as_invoice": {"tag_codes": ["custom_1779265822964"]},
                        "no_invoice_required": {"tag_codes": []},
                    }
                },
                actor_id="settings-owner",
            )

        definitions_by_code = {
            definition["code"]: definition
            for definition in payload["bank_transaction_tags"]["definitions"]
        }
        self.assertIn("custom_1779265822964", definitions_by_code)
        self.assertEqual(
            payload["pending_invoice_tag_groups"]["groups"]["bank_statement_as_invoice"]["tag_codes"],
            ["custom_1779265822964"],
        )

    def test_invalid_pending_invoice_group_mappings_do_not_audit_or_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            finalize_calls: list[dict[str, object]] = []

            with self.assertRaises(AppSettingsValidationError) as unknown_context:
                app._app_settings_service.update_settings(
                    completed_project_ids=[],
                    bank_account_mappings=[],
                    allowed_usernames=[],
                    readonly_export_usernames=[],
                    admin_usernames=[],
                    pending_invoice_tag_groups={
                        "groups": {
                            "requires_invoice": {"tag_codes": ["not_a_real_tag"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    },
                    actor_id="settings-owner",
                    after_bank_transaction_tag_settings_saved=finalize_calls.append,
                )

            with self.assertRaises(AppSettingsValidationError) as archived_context:
                app._app_settings_service.update_settings(
                    completed_project_ids=[],
                    bank_account_mappings=[],
                    allowed_usernames=[],
                    readonly_export_usernames=[],
                    admin_usernames=[],
                    bank_transaction_tags={
                        "definitions": [
                            {
                                "code": "custom_archived",
                                "label": "停用标签",
                                "path": ["自定义"],
                                "source": "custom",
                                "status": "archived",
                            }
                        ],
                    },
                    pending_invoice_tag_groups={
                        "groups": {
                            "requires_invoice": {"tag_codes": ["custom_archived"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    },
                    actor_id="settings-owner",
                    after_bank_transaction_tag_settings_saved=finalize_calls.append,
                )

            with self.assertRaises(AppSettingsValidationError) as duplicate_context:
                app._app_settings_service.update_settings(
                    completed_project_ids=[],
                    bank_account_mappings=[],
                    allowed_usernames=[],
                    readonly_export_usernames=[],
                    admin_usernames=[],
                    pending_invoice_tag_groups={
                        "groups": {
                            "requires_invoice": {"tag_codes": ["fee"]},
                            "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    },
                    actor_id="settings-owner",
                    after_bank_transaction_tag_settings_saved=finalize_calls.append,
                )

        self.assertEqual(unknown_context.exception.error_code, "unknown_bank_transaction_tag")
        self.assertEqual(archived_context.exception.error_code, "archived_bank_transaction_tag")
        self.assertEqual(duplicate_context.exception.error_code, "duplicate_pending_invoice_tag_mapping")
        self.assertEqual(finalize_calls, [])
        self.assertEqual(app._audit_service.as_dicts(), [])

    def test_archiving_pending_invoice_mapped_tag_fails_with_in_use_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            finalize_calls: list[dict[str, object]] = []
            configured = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                bank_transaction_tags={
                    "version": 1,
                    "definitions": [
                        {
                            "code": "custom_mapped_pending_invoice",
                            "label": "待找发票映射标签",
                            "path": ["自定义"],
                            "source": "custom",
                            "status": "active",
                        }
                    ],
                },
                pending_invoice_tag_groups={
                    "groups": {
                        "requires_invoice": {"tag_codes": ["custom_mapped_pending_invoice"]},
                        "bank_statement_as_invoice": {"tag_codes": []},
                        "no_invoice_required": {"tag_codes": []},
                    }
                },
                actor_id="settings-owner",
            )

            with self.assertRaises(AppSettingsValidationError) as context:
                app._app_settings_service.update_settings(
                    completed_project_ids=[],
                    bank_account_mappings=[],
                    allowed_usernames=[],
                    readonly_export_usernames=[],
                    admin_usernames=[],
                    bank_transaction_tags={
                        "version": configured["bank_transaction_tags"]["version"],
                        "definitions": [
                            {
                                "code": "custom_mapped_pending_invoice",
                                "label": "待找发票映射标签",
                                "path": ["自定义"],
                                "source": "custom",
                                "status": "archived",
                            }
                        ],
                    },
                    pending_invoice_tag_groups=configured["pending_invoice_tag_groups"],
                    actor_id="settings-owner",
                    after_bank_transaction_tag_settings_saved=finalize_calls.append,
                )

            current = app._app_settings_service.get_settings_payload()

        self.assertEqual(
            context.exception.error_code,
            "bank_transaction_tag_in_use_by_pending_invoice_filter",
        )
        self.assertEqual(finalize_calls, [])
        self.assertEqual(current["bank_transaction_tags"]["version"], configured["bank_transaction_tags"]["version"])
        definitions_by_code = {
            definition["code"]: definition
            for definition in current["bank_transaction_tags"]["definitions"]
        }
        self.assertEqual(definitions_by_code["custom_mapped_pending_invoice"]["status"], "active")

    def test_stale_bank_transaction_tags_save_fails_with_version_conflict_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            current = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                bank_transaction_tags={
                    "version": 1,
                    "definitions": [
                        {
                            "code": "custom_current_tag",
                            "label": "当前标签",
                            "path": ["自定义"],
                            "source": "custom",
                            "status": "active",
                        }
                    ],
                },
                pending_invoice_tag_groups={
                    "groups": {
                        "requires_invoice": {"tag_codes": []},
                        "bank_statement_as_invoice": {"tag_codes": []},
                        "no_invoice_required": {"tag_codes": []},
                    }
                },
                actor_id="settings-owner",
            )

            with self.assertRaises(AppSettingsValidationError) as context:
                app._app_settings_service.update_settings(
                    completed_project_ids=[],
                    bank_account_mappings=[],
                    allowed_usernames=[],
                    readonly_export_usernames=[],
                    admin_usernames=[],
                    bank_transaction_tags={
                        "version": 1,
                        "definitions": [
                            {
                                "code": "custom_stale_tag",
                                "label": "旧页面标签",
                                "path": ["自定义"],
                                "source": "custom",
                                "status": "active",
                            }
                        ],
                    },
                    pending_invoice_tag_groups=current["pending_invoice_tag_groups"],
                    actor_id="settings-owner",
                )

            after_conflict = app._app_settings_service.get_settings_payload()

        self.assertEqual(context.exception.error_code, "bank_transaction_tags_version_conflict")
        definitions_by_code = {
            definition["code"]: definition
            for definition in after_conflict["bank_transaction_tags"]["definitions"]
        }
        self.assertIn("custom_current_tag", definitions_by_code)
        self.assertNotIn("custom_stale_tag", definitions_by_code)
        self.assertEqual(after_conflict["bank_transaction_tags"]["version"], current["bank_transaction_tags"]["version"])

    def test_tag_and_mapping_saves_audit_and_finalize_with_actor_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            finalize_calls: list[dict[str, object]] = []

            payload = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                bank_transaction_tags={
                    "definitions": [
                        {
                            "code": "custom_no_invoice_taxi",
                            "label": "打车无需发票",
                            "path": ["自定义", "打车"],
                            "source": "custom",
                            "status": "active",
                        }
                    ],
                },
                pending_invoice_tag_groups={
                    "groups": {
                        "requires_invoice": {"tag_codes": ["borrow_in_company_pending_repayment"]},
                        "bank_statement_as_invoice": {"tag_codes": []},
                        "no_invoice_required": {"tag_codes": ["custom_no_invoice_taxi"]},
                    }
                },
                actor_id="settings-owner",
                after_bank_transaction_tag_settings_saved=finalize_calls.append,
            )

        audit_entries = app._audit_service.as_dicts()
        self.assertEqual(payload["bank_transaction_tags"]["version"], 2)
        self.assertEqual([entry["actor_id"] for entry in audit_entries], ["settings-owner", "settings-owner"])
        self.assertEqual(
            [entry["action"] for entry in audit_entries],
            ["bank_transaction_tags_updated", "pending_invoice_tag_groups_updated"],
        )
        self.assertEqual(audit_entries[0]["metadata"]["new_version"], 2)
        self.assertIn("before_summary", audit_entries[0]["metadata"])
        self.assertIn("after_summary", audit_entries[0]["metadata"])
        self.assertEqual(
            audit_entries[1]["metadata"]["affected_groups"],
            ["no_invoice_required", "requires_invoice"],
        )
        self.assertEqual(len(finalize_calls), 1)
        self.assertEqual(finalize_calls[0]["actor_id"], "settings-owner")
        self.assertEqual(finalize_calls[0]["new_version"], 2)
        self.assertEqual(
            finalize_calls[0]["affected_groups"],
            ["no_invoice_required", "requires_invoice"],
        )

    def test_bank_transaction_tags_and_pending_invoice_groups_survive_state_store_reload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            app = build_application(data_dir=data_dir)

            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                bank_transaction_tags={
                    "definitions": [
                        {
                            "code": "custom_no_invoice_parking",
                            "label": "停车费无需发票",
                            "path": ["自定义", "停车费"],
                            "source": "custom",
                            "status": "active",
                        }
                    ],
                },
                pending_invoice_tag_groups={
                    "groups": {
                        "requires_invoice": {"tag_codes": ["borrow_in_company_pending_repayment"]},
                        "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                        "no_invoice_required": {"tag_codes": ["custom_no_invoice_parking"]},
                    }
                },
                actor_id="settings-owner",
            )

            reloaded_payload = build_application(data_dir=data_dir)._app_settings_service.get_settings_payload()

        definitions_by_code = {
            definition["code"]: definition
            for definition in reloaded_payload["bank_transaction_tags"]["definitions"]
        }
        self.assertIn("custom_no_invoice_parking", definitions_by_code)
        self.assertEqual(reloaded_payload["bank_transaction_tags"]["version"], 2)
        self.assertEqual(reloaded_payload["pending_invoice_tag_groups"]["version"], 2)
        self.assertEqual(
            reloaded_payload["pending_invoice_tag_groups"]["groups"]["no_invoice_required"]["tag_codes"],
            ["custom_no_invoice_parking"],
        )

    def test_historical_invalid_pending_invoice_mappings_survive_reload_for_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            store.save_app_settings(
                {
                    "bank_transaction_tags": {
                        "version": 7,
                        "definitions": [
                            {
                                "code": "custom_archived_history",
                                "label": "历史停用标签",
                                "path": ["自定义"],
                                "source": "custom",
                                "status": "archived",
                            }
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "version": 7,
                        "groups": {
                            "requires_invoice": {"tag_codes": ["missing_history_tag", "custom_archived_history"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        },
                    },
                }
            )

            app = build_application(data_dir=data_dir)
            payload = app._app_settings_service.get_settings_payload()

            with self.assertRaises(AppSettingsValidationError) as context:
                app._app_settings_service.update_settings(
                    completed_project_ids=[],
                    bank_account_mappings=[],
                    allowed_usernames=[],
                    readonly_export_usernames=[],
                    admin_usernames=[],
                    bank_transaction_tags=payload["bank_transaction_tags"],
                    pending_invoice_tag_groups=payload["pending_invoice_tag_groups"],
                    actor_id="settings-owner",
                )

        self.assertEqual(
            payload["pending_invoice_tag_groups"]["groups"]["requires_invoice"]["tag_codes"],
            ["missing_history_tag", "custom_archived_history"],
        )
        self.assertEqual(context.exception.error_code, "unknown_bank_transaction_tag")

    def test_historical_duplicate_pending_invoice_mappings_survive_reload_for_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            store.save_app_settings(
                {
                    "bank_transaction_tags": {
                        "version": 7,
                        "definitions": [
                            {
                                "code": "fee",
                                "label": "手续费",
                                "path": ["自动识别", "手续费"],
                                "source": "system",
                                "status": "active",
                            }
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "version": 7,
                        "groups": {
                            "requires_invoice": {"tag_codes": ["fee"]},
                            "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                            "no_invoice_required": {"tag_codes": []},
                        },
                    },
                }
            )

            app = build_application(data_dir=data_dir)
            payload = app._app_settings_service.get_settings_payload()

            with self.assertRaises(AppSettingsValidationError) as context:
                app._app_settings_service.update_settings(
                    completed_project_ids=[],
                    bank_account_mappings=[],
                    allowed_usernames=[],
                    readonly_export_usernames=[],
                    admin_usernames=[],
                    bank_transaction_tags=payload["bank_transaction_tags"],
                    pending_invoice_tag_groups=payload["pending_invoice_tag_groups"],
                    actor_id="settings-owner",
                )

        self.assertEqual(
            payload["pending_invoice_tag_groups"]["groups"]["requires_invoice"]["tag_codes"],
            ["fee"],
        )
        self.assertEqual(
            payload["pending_invoice_tag_groups"]["groups"]["bank_statement_as_invoice"]["tag_codes"],
            ["fee"],
        )
        self.assertEqual(context.exception.error_code, "duplicate_pending_invoice_tag_mapping")

    def test_state_store_mongo_app_settings_round_trips_bank_tags_and_pending_invoice_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            fake_collection = FakeMongoCollection()
            store._mongo_database = object()
            store._mongo_detailed_collections = {"app_settings": fake_collection}

            store.save_app_settings(
                {
                    "bank_transaction_tags": {
                        "version": 3,
                        "definitions": [
                            {
                                "code": "custom_mongo_tag",
                                "label": "Mongo 标签",
                                "path": ["自定义"],
                                "source": "custom",
                                "status": "active",
                            }
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "version": 3,
                        "groups": {
                            "requires_invoice": {"tag_codes": ["custom_mongo_tag"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        },
                    },
                }
            )

            loaded = store.load_app_settings()

        self.assertEqual(loaded["bank_transaction_tags"]["version"], 3)
        self.assertEqual(
            loaded["bank_transaction_tags"]["definitions"][0]["code"],
            "custom_mongo_tag",
        )
        self.assertEqual(
            loaded["pending_invoice_tag_groups"]["groups"]["requires_invoice"]["tag_codes"],
            ["custom_mongo_tag"],
        )

    def test_update_settings_normalizes_access_control_lists_and_keeps_admin_in_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FULL001", "READONLY001"],
                readonly_export_usernames=["READONLY001", "OUTSIDER001", "YNSYLP005"],
                admin_usernames=["ADMIN002"],
            )

        access_control = payload["access_control"]
        self.assertEqual(
            access_control["allowed_usernames"],
            ["ADMIN002", "FULL001", "READONLY001", "YNSYLP005"],
        )
        self.assertEqual(access_control["readonly_export_usernames"], ["READONLY001"])
        self.assertEqual(access_control["admin_usernames"], ["ADMIN002", "YNSYLP005"])
        self.assertEqual(access_control["full_access_usernames"], ["FULL001"])

    def test_update_settings_persists_access_control_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FULL001"],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_retention={"cutoff_date": "2026-01-01"},
                workbench_column_layouts={"oa": ["projectName", "applicant"]},
            )

            reloaded_app = build_application(data_dir=Path(temp_dir))
            payload = reloaded_app._app_settings_service.get_settings_payload()

        access_control = payload["access_control"]
        self.assertEqual(access_control["allowed_usernames"], ["FULL001", "YNSYLP005"])
        self.assertEqual(access_control["readonly_export_usernames"], [])
        self.assertEqual(access_control["admin_usernames"], ["YNSYLP005"])
        self.assertEqual(access_control["full_access_usernames"], ["FULL001"])
        self.assertEqual(
            payload["workbench_column_layouts"]["oa"],
            ["projectName", "applicant", "amount", "counterparty", "reason"],
        )
        self.assertEqual(payload["oa_retention"], {"cutoff_date": "2026-01-01"})

    def test_update_settings_persists_bank_account_short_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[
                    {
                        "id": "bank_mapping_8826",
                        "last4": "8826",
                        "bank_name": "中国光大银行股份有限公司",
                        "short_name": "光大",
                    }
                ],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
            )

            payload = build_application(data_dir=Path(temp_dir))._app_settings_service.get_settings_payload()

        self.assertEqual(
            payload["bank_account_mappings"],
            [
                {
                    "id": "bank_mapping_8826",
                    "last4": "8826",
                    "bank_name": "中国光大银行股份有限公司",
                    "short_name": "光大",
                }
            ],
        )

    def test_invalid_oa_retention_cutoff_date_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_retention={"cutoff_date": "2026-99-99"},
                workbench_column_layouts={},
            )

        self.assertEqual(payload["oa_retention"], {"cutoff_date": "2026-01-01"})

    def test_oa_import_defaults_and_normalizes_to_supported_form_type_and_status_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            default_payload = app._app_settings_service.get_settings_payload()
            updated_payload = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_import={
                    "form_types": ["expense_claim", "ticket_type", "payment_request", "payment_request"],
                    "statuses": ["in_progress", "REJECTED", "completed", "0", "completed"],
                },
                workbench_column_layouts={},
            )
            reloaded_payload = build_application(data_dir=Path(temp_dir))._app_settings_service.get_settings_payload()

        expected_available_form_types = [
            {"id": "payment_request", "label": "支付申请"},
            {"id": "expense_claim", "label": "日常报销"},
        ]
        expected_available_statuses = [
            {"id": "completed", "label": "已完成"},
            {"id": "in_progress", "label": "进行中"},
        ]
        self.assertEqual(
            default_payload["oa_import"],
            {
                "form_types": ["payment_request", "expense_claim"],
                "statuses": ["completed"],
                "available_form_types": expected_available_form_types,
                "available_statuses": expected_available_statuses,
            },
        )
        self.assertEqual(
            updated_payload["oa_import"],
            {
                "form_types": ["payment_request", "expense_claim"],
                "statuses": ["completed", "in_progress"],
                "available_form_types": expected_available_form_types,
                "available_statuses": expected_available_statuses,
            },
        )
        self.assertEqual(reloaded_payload["oa_import"], updated_payload["oa_import"])

    def test_update_settings_persists_oa_invoice_offset_applicants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            updated_payload = app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_invoice_offset={"applicant_names": [" 周洁莹 ", "周洁莹", "李四"]},
                workbench_column_layouts={},
            )
            reloaded_payload = build_application(data_dir=Path(temp_dir))._app_settings_service.get_settings_payload()

        self.assertEqual(updated_payload["oa_invoice_offset"], {"applicant_names": ["周洁莹", "李四"]})
        self.assertEqual(reloaded_payload["oa_invoice_offset"], updated_payload["oa_invoice_offset"])

    def test_update_settings_triggers_oa_role_sync_with_normalized_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            sync_service = RecordingSyncService()
            app._app_settings_service._oa_role_sync_service = sync_service

            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FULL001", "READONLY001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )

        self.assertEqual(
            sync_service.assignments,
            [
                OARoleAssignment(username="READONLY001", tier="read_export_only"),
                OARoleAssignment(username="FULL001", tier="full_access"),
                OARoleAssignment(username="YNSYLP005", tier="admin"),
            ],
        )

    def test_workbench_settings_api_accepts_and_returns_access_control_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            update_response = app.handle_request(
                "POST",
                "/api/workbench/settings",
                body=json.dumps(
                    {
                        "completed_project_ids": [],
                        "bank_account_mappings": [],
                        "allowed_usernames": ["FULL001", "READONLY001"],
                        "readonly_export_usernames": ["READONLY001"],
                        "admin_usernames": [],
                        "oa_retention": {"cutoff_date": "2026-01-01"},
                        "oa_import": {
                            "form_types": ["payment_request"],
                            "statuses": ["completed"],
                        },
                        "workbench_column_layouts": {
                            "oa": ["projectName", "applicant"],
                            "bank": ["amount", "counterparty"],
                        },
                    }
                ),
            )
            updated_payload = json.loads(update_response.body)

            get_response = app.handle_request("GET", "/api/workbench/settings")
            get_payload = json.loads(get_response.body)

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(
            updated_payload["access_control"],
            {
                "allowed_usernames": ["FULL001", "READONLY001", "YNSYLP005"],
                "readonly_export_usernames": ["READONLY001"],
                "admin_usernames": ["YNSYLP005"],
                "full_access_usernames": ["FULL001"],
            },
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_payload["access_control"], updated_payload["access_control"])
        self.assertEqual(updated_payload["oa_retention"], {"cutoff_date": "2026-01-01"})
        self.assertEqual(get_payload["oa_retention"], updated_payload["oa_retention"])
        self.assertEqual(
            updated_payload["oa_import"],
            {
                "form_types": ["payment_request"],
                "statuses": ["completed"],
                "available_form_types": [
                    {"id": "payment_request", "label": "支付申请"},
                    {"id": "expense_claim", "label": "日常报销"},
                ],
                "available_statuses": [
                    {"id": "completed", "label": "已完成"},
                    {"id": "in_progress", "label": "进行中"},
                ],
            },
        )
        self.assertEqual(get_payload["oa_import"], updated_payload["oa_import"])
        self.assertEqual(
            updated_payload["workbench_column_layouts"],
            {
                "oa": ["projectName", "applicant", "amount", "counterparty", "reason"],
                "bank": ["amount", "counterparty", "loanRepaymentDate", "note"],
                "invoice": ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"],
            },
        )
        self.assertEqual(get_payload["workbench_column_layouts"], updated_payload["workbench_column_layouts"])

    def test_sync_oa_projects_returns_source_and_status_in_settings_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = app._app_settings_service.sync_oa_projects(actor_id="settings_test")
            active_projects = payload["projects"]["active"]

        self.assertGreaterEqual(len(active_projects), 2)
        project = next(item for item in active_projects if item["project_code"] == "PJT-001")
        self.assertEqual(project["project_name"], "华东改造项目")
        self.assertEqual(project["project_status"], "active")
        self.assertEqual(project["source"], "oa")
        self.assertEqual(project["department_name"], "交付中心")
        self.assertEqual(project["owner_name"], "张三")

    def test_synced_oa_projects_persist_across_reload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            synced_payload = app._app_settings_service.sync_oa_projects(actor_id="settings_test")
            reloaded_payload = build_application(data_dir=Path(temp_dir))._app_settings_service.get_settings_payload()

        self.assertEqual(
            [project["project_code"] for project in reloaded_payload["projects"]["active"]],
            [project["project_code"] for project in synced_payload["projects"]["active"]],
        )
        self.assertEqual(
            [project["project_name"] for project in reloaded_payload["projects"]["active"]],
            [project["project_name"] for project in synced_payload["projects"]["active"]],
        )

    def test_create_manual_project_persists_and_defaults_to_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            created_payload = app._app_settings_service.create_manual_project(
                actor_id="settings_test",
                project_code="LOCAL-001",
                project_name="本地测试项目",
                department_name="财务部",
                owner_name="王五",
            )
            reloaded_payload = build_application(data_dir=Path(temp_dir))._app_settings_service.get_settings_payload()

        created_project = created_payload["projects"]["active"][0]
        self.assertEqual(created_project["project_code"], "LOCAL-001")
        self.assertEqual(created_project["project_name"], "本地测试项目")
        self.assertEqual(created_project["project_status"], "active")
        self.assertEqual(created_project["source"], "manual")
        self.assertEqual(created_project["department_name"], "财务部")
        self.assertEqual(created_project["owner_name"], "王五")
        self.assertEqual(reloaded_payload["projects"]["active"][0], created_project)

    def test_delete_manual_project_removes_only_local_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created_payload = app._app_settings_service.create_manual_project(
                actor_id="settings_test",
                project_code="LOCAL-001",
                project_name="本地测试项目",
            )
            project_id = created_payload["projects"]["active"][0]["id"]

            deleted_payload = app._app_settings_service.delete_project(project_id)
            reloaded_payload = build_application(data_dir=Path(temp_dir))._app_settings_service.get_settings_payload()

        self.assertEqual(deleted_payload["projects"]["active"], [])
        self.assertEqual(reloaded_payload["projects"]["active"], [])
        self.assertEqual(reloaded_payload["projects"]["completed_project_ids"], [])

    def test_delete_oa_project_local_override_does_not_remove_oa_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            synced_payload = app._app_settings_service.sync_oa_projects(actor_id="settings_test")
            project_id = synced_payload["projects"]["active"][0]["id"]
            app._app_settings_service.update_settings(
                completed_project_ids=[project_id],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
            )

            deleted_payload = app._app_settings_service.delete_project(project_id)

        self.assertIn(
            project_id,
            [project["id"] for project in deleted_payload["projects"]["active"]],
        )
        self.assertNotIn(project_id, deleted_payload["projects"]["completed_project_ids"])


if __name__ == "__main__":
    unittest.main()
