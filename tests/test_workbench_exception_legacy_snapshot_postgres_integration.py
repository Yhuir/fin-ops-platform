from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import os
from threading import Barrier
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_page_query import (
    PostgresWorkbenchPageQueryRepository,
)
from fin_ops_platform.services.workbench_exception_case_service import WorkbenchExceptionCaseService
from fin_ops_platform.tools.repair_workbench_legacy_typed_identities import (
    main as repair_workbench_legacy_typed_identities,
)
from fin_ops_platform.tools.workbench_direct_application_bootstrap_probe import (
    main as workbench_direct_application_bootstrap_probe,
)
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


@contextmanager
def _postgres_app_env(database_url: str):
    updates = {
        "FIN_OPS_APP_STORAGE_BACKEND": "postgres",
        "FIN_OPS_POSTGRES_DATABASE_URL": database_url,
        "FIN_OPS_POSTGRES_POOL_ENABLED": "0",
        "FIN_OPS_POSTGRES_READ_POOL_ENABLED": "0",
        "FIN_OPS_DISABLE_STARTUP_HISTORICAL_ETC_REPAIR": "1",
        "FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED": "0",
        "FIN_OPS_TENANT_ID": "default",
    }
    with patch.dict(os.environ, updates, clear=False):
        yield


class WorkbenchExceptionLegacySnapshotPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self._temp_dir = TemporaryDirectory()

    def tearDown(self) -> None:
        self.connection.close()
        self._temp_dir.cleanup()
        truncate_test_database(self.database_url)

    def test_explicit_repair_fixes_open_three_two_and_settled_four_two_once(self) -> None:
        for row_id in (
            "legacy-open-bank-1",
            "legacy-open-bank-2",
            "legacy-settled-bank-1",
            "legacy-settled-bank-2",
            "legacy-settled-bank-3",
        ):
            self._insert_bank(row_id)
        self._insert_completed_oa("legacy-settled-oa-1")
        self._insert_pending_oa("legacy-open-oa-1", tenant_id="default")

        service = WorkbenchExceptionCaseService()
        open_case = service.create_exception_case(
            rows=[
                self._row("legacy-open-bank-1", "bank"),
                self._row("legacy-open-bank-2", "bank"),
                self._row("legacy-open-oa-1", "oa"),
            ],
            exception_code="manual_review",
            exception_label="人工复核",
            category="manual",
        )
        settled_case = service.create_settlement_case(
            rows=[
                self._row("legacy-settled-bank-1", "bank"),
                self._row("legacy-settled-bank-2", "bank"),
                self._row("legacy-settled-bank-3", "bank"),
                self._row("legacy-settled-oa-1", "oa"),
            ],
            exception_code="personal_advance_repayment_settlement",
            exception_label="还清个人暂借款",
            category="oa_bank_settlement",
        )
        snapshot = service.snapshot()
        snapshot["cases"][open_case["id"]]["status"] = "open"
        snapshot["cases"][open_case["id"]]["row_types"] = ["bank", "oa"]
        snapshot["cases"][settled_case["id"]]["row_types"] = ["bank", "oa"]
        PostgresWorkbenchRepository(self.connection).save_workbench_exception_cases(snapshot)

        first = PostgresWorkbenchRepository(
            self.connection
        ).repair_legacy_workbench_typed_identities(tenant_id="default")
        self.assertEqual(first["exception_repaired"], 2)
        self.assertEqual(
            PostgresWorkbenchRepository(
                self.connection
            ).repair_legacy_workbench_typed_identities(tenant_id="default")[
                "exception_repaired"
            ],
            0,
        )

        app = self._build_app()
        try:
            repaired = app._workbench_exception_case_service.snapshot()  # noqa: SLF001
            self.assertEqual(
                repaired["cases"][open_case["id"]]["row_types"],
                ["bank", "bank", "oa"],
            )
            self.assertEqual(
                repaired["cases"][settled_case["id"]]["row_types"],
                ["bank", "bank", "bank", "oa"],
            )
            self.assertEqual(
                app._workbench_exception_case_service.case_ids_for_typed_rows(  # noqa: SLF001
                    ["legacy-open-bank-1", "legacy-open-oa-1"],
                    ["bank", "oa"],
                ),
                [open_case["id"]],
            )
            self.assertEqual(repaired["cases"][settled_case["id"]]["status"], "settled")
        finally:
            app.close()

        before_restart = self._stored_cases()
        app = self._build_app()
        try:
            restarted = app._workbench_exception_case_service.snapshot()  # noqa: SLF001
            self.assertEqual(
                restarted["cases"][open_case["id"]]["row_types"],
                ["bank", "bank", "oa"],
            )
            self.assertEqual(
                restarted["cases"][settled_case["id"]]["row_types"],
                ["bank", "bank", "bank", "oa"],
            )
        finally:
            app.close()
        self.assertEqual(self._stored_cases(), before_restart)

    def test_new_typed_same_text_cross_pane_snapshot_round_trips_without_repair(self) -> None:
        self._insert_bank("same-text-id")
        self._insert_invoice("same-text-id")
        service = WorkbenchExceptionCaseService()
        case = service.create_exception_case(
            rows=[
                self._row("same-text-id", "bank"),
                self._row("same-text-id", "invoice"),
            ],
            exception_code="manual_review",
            exception_label="人工复核",
            category="manual",
        )
        PostgresWorkbenchRepository(self.connection).save_workbench_exception_cases(
            service.snapshot()
        )
        stored_before_restart = self._stored_cases()

        app = self._build_app()
        try:
            restored = app._workbench_exception_case_service.snapshot()  # noqa: SLF001
            self.assertEqual(restored["cases"][case["id"]]["row_ids"], ["same-text-id", "same-text-id"])
            self.assertEqual(restored["cases"][case["id"]]["row_types"], ["bank", "invoice"])
            self.assertEqual(
                app._workbench_exception_case_service.case_ids_for_typed_rows(  # noqa: SLF001
                    ["same-text-id", "same-text-id"],
                    ["bank", "invoice"],
                ),
                [case["id"]],
            )
        finally:
            app.close()
        self.assertEqual(self._stored_cases(), stored_before_restart)

    def test_explicit_cli_then_read_only_application_bootstrap_succeeds(self) -> None:
        self._insert_bank("cli-bank-1")
        self._insert_completed_oa("cli-oa-1")
        self._insert_legacy_case(
            case_id="WEX-CLI",
            row_ids=["cli-bank-1", "cli-oa-1"],
            row_types=["bank"],
        )
        self._insert_unknown_override("cli-bank-1", handled_exception=True)
        output = StringIO()
        errors = StringIO()
        with _postgres_app_env(self.database_url):
            exit_code = repair_workbench_legacy_typed_identities(
                connection=self.connection,
                stdout=output,
                stderr=errors,
            )
        self.assertEqual(exit_code, 0, errors.getvalue())
        self.assertEqual(
            json.loads(output.getvalue())["counts"],
            {
                "exception_repaired": 1,
                "override_repaired": 1,
                "override_unresolved_missing_source": 0,
            },
        )

        output = StringIO()
        errors = StringIO()
        with _postgres_app_env(self.database_url):
            exit_code = workbench_direct_application_bootstrap_probe(
                application_factory=lambda **_kwargs: build_application(
                    data_dir=Path(self._temp_dir.name),
                    bootstrap_mode="production",
                ),
                stdout=output,
                stderr=errors,
            )
        self.assertEqual(exit_code, 0, errors.getvalue())
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "read_only": True,
                "status": "passed",
                "tool": "workbench_direct_application_bootstrap_probe",
            },
        )

    def test_regular_application_bootstrap_does_not_repair_legacy_state(self) -> None:
        self._insert_bank("boot-bank-1")
        self._insert_completed_oa("boot-oa-1")
        self._insert_legacy_case(
            case_id="WEX-BOOT-UNREPAIRED",
            row_ids=["boot-bank-1", "boot-oa-1"],
            row_types=["bank"],
        )
        before = self._stored_cases()
        with self.assertRaisesRegex(ValueError, "unaligned typed rows"):
            self._build_app()
        self.assertEqual(self._stored_cases(), before)

    def test_repair_fails_closed_for_ambiguous_completed_and_pending_oa(self) -> None:
        self._insert_bank("ambiguous-bank-1")
        self._insert_completed_oa("ambiguous-oa-1")
        self._insert_pending_oa("ambiguous-oa-1", tenant_id="default")
        self._insert_legacy_case(
            case_id="WEX-AMBIGUOUS",
            row_ids=["ambiguous-bank-1", "ambiguous-oa-1"],
            row_types=["bank"],
        )
        before = self._stored_cases()

        repository = PostgresWorkbenchRepository(self.connection)
        with self.assertRaisesRegex(ValueError, "multiple canonical source rows"):
            repository.repair_legacy_workbench_typed_identities(tenant_id="default")

        self.assertEqual(self._stored_cases(), before)

    def test_repair_fails_closed_when_pending_oa_belongs_to_another_tenant(self) -> None:
        self._insert_bank("missing-bank-1")
        self._insert_pending_oa("other-tenant-oa-1", tenant_id="tenant-b")
        self._insert_legacy_case(
            case_id="WEX-MISSING",
            row_ids=["missing-bank-1", "other-tenant-oa-1"],
            row_types=["bank"],
        )
        before = self._stored_cases()

        repository = PostgresWorkbenchRepository(self.connection)
        with self.assertRaisesRegex(ValueError, "has no canonical source row"):
            repository.repair_legacy_workbench_typed_identities(tenant_id="default")

        self.assertEqual(self._stored_cases(), before)

    def test_explicit_repair_upgrades_six_unique_overrides_and_preserves_one_missing(self) -> None:
        for index in range(1, 4):
            self._insert_bank(f"legacy-override-bank-{index}")
            self._insert_completed_oa(f"legacy-override-oa-{index}")
        for row_id in (
            "legacy-override-bank-1",
            "legacy-override-bank-2",
            "legacy-override-bank-3",
            "legacy-override-oa-1",
            "legacy-override-oa-2",
            "legacy-override-oa-3",
            "legacy-override-missing",
        ):
            self._insert_unknown_override(row_id, handled_exception=True)

        first = PostgresWorkbenchRepository(
            self.connection
        ).repair_legacy_workbench_typed_identities(tenant_id="default")
        self.assertEqual(
            first,
            {
                "override_repaired": 6,
                "override_unresolved_missing_source": 1,
                "exception_repaired": 0,
            },
        )

        app = self._build_app()
        try:
            loaded = app._workbench_override_service.snapshot()["row_overrides"]  # noqa: SLF001
            self.assertEqual(len(loaded), 6)
            self.assertFalse(
                any(
                    payload.get("row_id") == "legacy-override-missing"
                    for payload in loaded.values()
                )
            )
        finally:
            app.close()

        rows = self.connection.fetch_all(
            """
            select row_id, row_type, status, legacy_mongo_id,
                   override_payload, raw_payload, xmin::text as row_version
            from app.workbench_row_overrides
            order by row_id
            """
        )
        active = [row for row in rows if row["status"] == "active"]
        typed = [row for row in active if row["row_type"] != "unknown"]
        unresolved = [row for row in active if row["row_type"] == "unknown"]
        self.assertEqual(len(typed), 6)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["row_id"], "legacy-override-missing")
        for row in typed:
            self.assertEqual(row["legacy_mongo_id"], f"{row['row_type']}\x1f{row['row_id']}")
            self.assertEqual(row["override_payload"]["row_id"], row["row_id"])
            self.assertEqual(row["override_payload"]["row_type"], row["row_type"])
            self.assertEqual(
                row["raw_payload"]["normalized_payload"],
                row["override_payload"],
            )
        self.assertNotIn("legacy_identity_repair", unresolved[0]["override_payload"])
        versions_before_restart = {
            str(row["row_id"]): str(row["row_version"])
            for row in rows
        }
        audit_rows = self._repair_audit_rows()
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(
            audit_rows[0]["payload"],
            {
                "contract_schema": "workbench_typed_identity",
                "contract_version": 1,
                "exception_repaired": 0,
                "override_repaired": 6,
                "override_unresolved_missing_source": 1,
            },
        )

        second = PostgresWorkbenchRepository(
            self.connection
        ).repair_legacy_workbench_typed_identities(tenant_id="default")
        self.assertEqual(
            second,
            {
                "override_repaired": 0,
                "override_unresolved_missing_source": 1,
                "exception_repaired": 0,
            },
        )
        self.assertEqual(len(self._repair_audit_rows()), 1)
        self.assertEqual(
            {
                str(row["row_id"]): str(row["row_version"])
                for row in self.connection.fetch_all(
                    "select row_id, xmin::text as row_version from app.workbench_row_overrides"
                )
            },
            versions_before_restart,
        )

    def test_repaired_override_is_visible_in_plain_direct_page_get(self) -> None:
        self._insert_bank("legacy-direct-bank")
        self._insert_unknown_override("legacy-direct-bank", handled_exception=True)
        self._insert_legacy_case(
            case_id="WEX-LEGACY-OVERRIDE",
            row_ids=["legacy-direct-bank"],
            row_types=["bank"],
        )

        counts = PostgresWorkbenchRepository(
            self.connection
        ).repair_legacy_workbench_typed_identities(tenant_id="default")
        self.assertEqual(counts["override_repaired"], 1)

        page = PostgresWorkbenchPageQueryRepository(
            self.connection,
            tenant_id="default",
        ).get_workbench_initial_page(scope_key="2026-05")
        bank_rows = [
            row
            for zone in ("paired", "unpaired")
            for group in list(page[zone].get("groups") or [])
            for row in list(group.get("bank_rows") or [])
            if row.get("id") == "legacy-direct-bank"
        ]
        self.assertEqual(len(bank_rows), 1)
        self.assertTrue(bank_rows[0]["handled_exception"])
        self.assertEqual(bank_rows[0]["exception_case_id"], "WEX-LEGACY-OVERRIDE")
        self.assertEqual(
            sum(
                1
                for zone in ("paired", "unpaired")
                for group in list(page[zone].get("groups") or [])
                for row in list(group.get("bank_rows") or [])
                if row.get("id") == "legacy-direct-bank"
            ),
            1,
        )

    def test_repair_resolves_etc_summary_through_direct_selection_contract(self) -> None:
        self.connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values (
                'etc-legacy-repair', 'oa_submitted', '2026-05-01', 1,
                100,
                '{"normalized_payload":{"external_etc_batch_id":"etc-legacy-repair"}}'::jsonb
            )
            """
        )
        self.connection.execute(
            """
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            ) values (
                'etc-legacy-repair-invoice', 'etc-legacy-repair', 'submitted',
                'ETC-LEGACY-REPAIR', '2026-05-10', 'ETC兼容测试',
                90, 10, 100, '{}'::jsonb
            )
            """
        )
        self._insert_unknown_override(
            "etc-summary-etc-legacy-repair",
            handled_exception=True,
        )

        counts = PostgresWorkbenchRepository(
            self.connection
        ).repair_legacy_workbench_typed_identities(tenant_id="default")

        self.assertEqual(counts["override_repaired"], 1)
        row = self.connection.fetch_one(
            """
            select row_type, row_id
            from app.workbench_row_overrides
            where row_id = 'etc-summary-etc-legacy-repair'
            """
        )
        self.assertEqual(row, {"row_type": "invoice", "row_id": "etc-summary-etc-legacy-repair"})

    def test_override_repair_fails_closed_for_ambiguous_source_and_target_collision(self) -> None:
        self._insert_bank("ambiguous-override")
        self._insert_invoice("ambiguous-override")
        self._insert_unknown_override("ambiguous-override", handled_exception=True)
        repository = PostgresWorkbenchRepository(self.connection)
        with self.assertRaisesRegex(ValueError, "multiple canonical source rows"):
            repository.repair_legacy_workbench_typed_identities(tenant_id="default")
        self.assertEqual(self._active_unknown_override_count(), 1)
        self.assertEqual(self._repair_audit_rows(), [])

        truncate_test_database(self.database_url)
        self._insert_bank("colliding-override")
        self._insert_unknown_override("colliding-override", handled_exception=True)
        self._insert_typed_override("colliding-override", row_type="bank")
        with self.assertRaisesRegex(ValueError, "collides with typed identity"):
            repository.repair_legacy_workbench_typed_identities(tenant_id="default")
        self.assertEqual(self._active_unknown_override_count(), 1)
        self.assertEqual(self._repair_audit_rows(), [])

        truncate_test_database(self.database_url)
        self._insert_bank("cross-pane-override")
        self._insert_unknown_override("cross-pane-override", handled_exception=True)
        self._insert_typed_override("cross-pane-override", row_type="invoice")
        counts = repository.repair_legacy_workbench_typed_identities(tenant_id="default")
        self.assertEqual(counts["override_repaired"], 1)
        identities = self.connection.fetch_all(
            """
            select row_type, row_id, legacy_mongo_id
            from app.workbench_row_overrides
            where row_id = 'cross-pane-override'
            order by row_type
            """
        )
        self.assertEqual(
            [(row["row_type"], row["row_id"]) for row in identities],
            [("bank", "cross-pane-override"), ("invoice", "cross-pane-override")],
        )
        self.assertEqual(len({row["legacy_mongo_id"] for row in identities}), 2)

    def test_concurrent_explicit_repair_runs_once_and_writes_one_audit_event(self) -> None:
        self._insert_bank("concurrent-override")
        self._insert_unknown_override("concurrent-override", handled_exception=True)
        barrier = Barrier(2)

        def repair() -> dict[str, int]:
            connection = PostgresConnection(
                PostgresSettings(database_url=self.database_url, pool_enabled=False)
            )
            try:
                barrier.wait(timeout=5)
                return PostgresWorkbenchRepository(
                    connection
                ).repair_legacy_workbench_typed_identities(tenant_id="default")
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: repair(), range(2)))

        self.assertEqual(
            sorted(result["override_repaired"] for result in results),
            [0, 1],
        )
        self.assertEqual(self._active_unknown_override_count(), 0)
        self.assertEqual(len(self._repair_audit_rows()), 1)

    def _build_app(self):
        with _postgres_app_env(self.database_url):
            return build_application(data_dir=Path(self._temp_dir.name))

    @staticmethod
    def _row(row_id: str, row_type: str) -> dict[str, str]:
        return {"id": row_id, "type": row_type, "month": "2026-05"}

    def _insert_bank(self, row_id: str) -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status, raw_payload
            ) values (%s, '622200001', 'outflow', '兼容性测试', 100, -100,
                      '2026-05-10', '2026-05-01', 'pending', '{}'::jsonb)
            """,
            (row_id,),
        )

    def _insert_invoice(self, row_id: str) -> None:
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, raw_payload
            ) values (%s, 'input', %s, '2026-05-09', '2026-05-01',
                      100, 100, 100, 'pending', '{}'::jsonb)
            """,
            (row_id, f"INV-{row_id}"),
        )

    def _insert_completed_oa(self, row_id: str) -> None:
        self.connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, row_id, status, workflow_status,
                application_date, scope_month, amount, normalized_payload, raw_payload
            ) values (%s, 'payment_request', %s, 'active', 'completed',
                      '2026-05-08', '2026-05-01', 100, '{}'::jsonb, '{}'::jsonb)
            """,
            (f"source-{row_id}", row_id),
        )

    def _insert_pending_oa(self, row_id: str, *, tenant_id: str) -> None:
        self.connection.execute(
            """
            insert into app.oa_pending_payment_admissions(
                tenant_id, scope_key, oa_id, workflow_status, amount,
                source_signature, source_payload, raw_payload
            ) values (%s, '2026-05', %s, 'in_progress', 100, %s, '{}'::jsonb, '{}'::jsonb)
            """,
            (tenant_id, row_id, f"signature-{tenant_id}-{row_id}"),
        )

    def _insert_legacy_case(
        self,
        *,
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
    ) -> None:
        payload = {
            "id": case_id,
            "status": "open",
            "exception_code": "manual_review",
            "exception_label": "人工复核",
            "category": "manual",
            "row_ids": row_ids,
            "row_types": row_types,
            "scope_months": ["2026-05"],
            "created_at": "2026-05-10T00:00:00+00:00",
            "updated_at": "2026-05-10T00:00:00+00:00",
            "history": [],
        }
        self.connection.execute(
            """
            insert into app.workbench_exception_cases(
                case_id, status, version, business_line, scenario,
                scope_month, row_ids, raw_payload
            ) values (%s, 'open', 1, 'manual', 'manual_review',
                      '2026-05-01', %s, %s)
            """,
            (case_id, row_ids, jsonb({"normalized_payload": payload})),
        )

    def _insert_unknown_override(self, row_id: str, *, handled_exception: bool) -> None:
        payload = {
            "row_id": row_id,
            "case_id": "WEX-LEGACY-OVERRIDE",
            "exception_case_id": "WEX-LEGACY-OVERRIDE",
            "handled_exception": handled_exception,
            "relation": {
                "code": "manual_review",
                "label": "人工复核",
                "tone": "danger",
            },
        }
        self.connection.execute(
            """
            insert into app.workbench_row_overrides(
                legacy_mongo_id, row_id, row_type, scope_month, status,
                projection_version, override_payload, raw_payload
            ) values (%s, %s, 'unknown', '2026-05-01', 'active', 1, %s, %s)
            """,
            (
                row_id,
                row_id,
                jsonb(payload),
                jsonb({"normalized_payload": payload}),
            ),
        )

    def _insert_typed_override(self, row_id: str, *, row_type: str) -> None:
        payload = {
            "row_id": row_id,
            "row_type": row_type,
            "handled_exception": False,
        }
        self.connection.execute(
            """
            insert into app.workbench_row_overrides(
                legacy_mongo_id, row_id, row_type, scope_month, status,
                projection_version, override_payload, raw_payload
            ) values (%s, %s, %s, '2026-05-01', 'active', 1, %s, %s)
            """,
            (
                f"{row_type}\x1f{row_id}",
                row_id,
                row_type,
                jsonb(payload),
                jsonb({"normalized_payload": payload}),
            ),
        )

    def _active_unknown_override_count(self) -> int:
        row = self.connection.fetch_one(
            """
            select count(*)::integer as count
            from app.workbench_row_overrides
            where status = 'active' and row_type = 'unknown'
            """
        )
        return int((row or {}).get("count") or 0)

    def _repair_audit_rows(self) -> list[dict[str, object]]:
        return self.connection.fetch_all(
            """
            select event_type, object_type, actor_id, payload
            from audit.events
            where event_type = 'workbench.legacy_typed_identity.repaired'
            order by occurred_at, id
            """
        )

    def _stored_cases(self) -> list[dict[str, object]]:
        return self.connection.fetch_all(
            """
            select case_id, row_ids, raw_payload, xmin::text as row_version
            from app.workbench_exception_cases
            order by case_id
            """
        )


if __name__ == "__main__":
    unittest.main()
