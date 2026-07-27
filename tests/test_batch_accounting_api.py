from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
from time import perf_counter
import unittest

from fin_ops_platform.app.auth import OAUserIdentity
from fin_ops_platform.app.routes_batch_accounting import BatchAccountingApiRoutes
from fin_ops_platform.services.batch_accounting_service import (
    BatchAccountingError,
    BatchAccountingService,
)
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from tests.app_test_support import build_local_state_application as build_application


BANK_ROW_ID = "txn_imported_202601_batch_001"
OA_ROW_ID = "oa-exp-ba-001"
INVOICE_ROW_ID = "oa-att-inv-oa-exp-ba-001-01"
RELATION_ID = f"CASE-BATCH-{BANK_ROW_ID}"


def bank_row(
    *,
    row_id: str = BANK_ROW_ID,
    amount: str = "1200.00",
    trade_time: str = "2026-01-07T15:54:00+08:00",
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "trade_time": trade_time,
        "counterparty_name": "批量账务集中处理",
        "debit_amount": amount,
        "signed_amount": f"-{amount}",
        "direction": "outflow",
        "account_name": "建行基本户",
        "account_no": "6227000012348106",
        "version": 1,
    }


def oa_row(
    *,
    row_id: str = OA_ROW_ID,
    amount: str = "1200.00",
    apply_time: str = "2026-01-06",
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "applicant": "刘晨",
        "apply_time": apply_time,
        "project_name": "品牌广告投放",
        "amount": amount,
        "reason": "日常报销",
        "apply_type": "日常报销",
        "expense_type": "",
    }


def invoice_row(
    *,
    row_id: str = INVOICE_ROW_ID,
    source_oa_id: str = OA_ROW_ID,
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "invoice",
        "source_kind": "oa_attachment_invoice",
        "source_oa_id": source_oa_id,
        "derived_from_oa_id": source_oa_id,
        "issue_date": "2026-01-05",
        "total_with_tax": "1200.00",
    }


def active_relation(
    *,
    relation_id: str = RELATION_ID,
    bank_id: str = BANK_ROW_ID,
    oa_id: str = OA_ROW_ID,
    invoice_id: str = INVOICE_ROW_ID,
    version: int = 1,
) -> dict[str, object]:
    return {
        "case_id": relation_id,
        "relation_mode": "batch_accounting",
        "status": "active",
        "version": version,
        "month_scope": "2026-01",
        "row_ids": [bank_id, oa_id, invoice_id],
        "row_types": ["bank", "oa", "invoice"],
        "note": "日常报销批量账务管理提交",
        "amount_check": {
            "status": "matched",
            "direction": "expense",
            "bank_amount": "1200.00",
            "oa_amount": "1200.00",
            "amount_delta": "0.00",
            "requires_note": False,
        },
        "special_metadata": {
            "source": "batch_accounting",
            "bank_row_id": bank_id,
            "oa_row_ids": [oa_id],
            "invoice_row_ids": [invoice_id],
            "bank_year": "2026",
            "affected_scope_keys": ["2026-01"],
        },
    }


class FakeBatchAccountingQueryRepository:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []
        self.submission_calls: list[dict[str, object]] = []
        self.list_payload: dict[str, object] = {
            "summary": {
                "unsubmitted_count": 1,
                "submitted_count": 0,
                "oa_count": 1,
            },
            "bank_rows": [bank_row()],
            "oa_rows": [oa_row()],
            "invoice_rows": [invoice_row()],
            "relations": [],
            "member_rows": [],
            "pagination": {
                "bank_rows": {"page": 1, "page_size": 200, "pageSize": 200, "total": 1},
                "oa_rows": {"page": 1, "page_size": 200, "pageSize": 200, "total": 1},
            },
        }
        self.submission_payload: dict[str, object] = {
            "bank_rows": [bank_row()],
            "oa_rows": [oa_row()],
            "invoice_rows": [invoice_row()],
        }

    def list_snapshot(self, **kwargs: object) -> dict[str, object]:
        self.list_calls.append(dict(kwargs))
        return deepcopy(self.list_payload)

    def load_submission_context(self, **kwargs: object) -> dict[str, object]:
        self.submission_calls.append(dict(kwargs))
        return deepcopy(self.submission_payload)


class RecordingRelationCommandService:
    def __init__(self) -> None:
        self.confirm_calls: list[dict[str, object]] = []
        self.cancel_calls: list[dict[str, object]] = []
        self.active_relation_calls: list[list[str]] = []
        self.active_relations: list[dict[str, object]] = []
        self.relation_by_case_id: dict[str, object] | None = None
        self.confirm_error: WorkbenchRelationCommandError | None = None

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        self.active_relation_calls.append(list(row_ids))
        row_id_set = set(row_ids)
        return [
            deepcopy(relation)
            for relation in self.active_relations
            if row_id_set.intersection(set(relation.get("row_ids") or []))
        ]

    def get_active_relation_by_case_id(self, case_id: str) -> dict[str, object] | None:
        relation = self.relation_by_case_id
        if isinstance(relation, dict) and relation.get("case_id") == case_id:
            return deepcopy(relation)
        return None

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(deepcopy(kwargs))
        if self.confirm_error is not None:
            raise self.confirm_error
        relation = {
            "case_id": kwargs["case_id"],
            "relation_mode": kwargs["relation_mode"],
            "status": "active",
            "version": 1,
            "month_scope": kwargs["month_scope"],
            "row_ids": list(kwargs["row_ids"]),
            "row_types": list(kwargs["row_types"]),
            "note": kwargs["note"],
            "amount_check": dict(kwargs["amount_check"]),
            "special_metadata": dict(kwargs["special_metadata"]),
        }
        self.relation_by_case_id = relation
        self.active_relations = [relation]
        return {"relation": relation, "changed_case_ids": [str(kwargs["case_id"])]}

    def cancel_relation(self, **kwargs: object) -> dict[str, object]:
        self.cancel_calls.append(dict(kwargs))
        relation = self.relation_by_case_id or {}
        self.relation_by_case_id = None
        self.active_relations = []
        return {
            "affected_row_ids": list(relation.get("row_ids") or []),
            "restored_relations": [],
            "changed_case_ids": [str(kwargs["case_id"])],
        }


def service(
    repository: FakeBatchAccountingQueryRepository | None = None,
    command_service: RecordingRelationCommandService | None = None,
) -> BatchAccountingService:
    return BatchAccountingService(
        query_repository=repository or FakeBatchAccountingQueryRepository(),
        relation_command_service=command_service or RecordingRelationCommandService(),
    )


class BatchAccountingServiceTests(unittest.TestCase):
    def test_unsubmitted_payload_uses_page_repository_and_has_no_read_model_contract(self) -> None:
        repository = FakeBatchAccountingQueryRepository()
        timings: list[tuple[str, float]] = []

        payload = service(repository).build_payload(
            bank_year="2026",
            bucket="unsubmitted",
            bank_page=2,
            bank_page_size=50,
            oa_page=3,
            oa_page_size=40,
            oa_search="刘晨",
            timing_observer=lambda phase, duration: timings.append((phase, duration)),
        )

        self.assertEqual(
            repository.list_calls,
            [
                {
                    "bank_year": "2026",
                    "bucket": "unsubmitted",
                    "bank_page": 2,
                    "bank_page_size": 50,
                    "oa_page": 3,
                    "oa_page_size": 40,
                    "oa_search": "刘晨",
                }
            ],
        )
        self.assertEqual(payload["summary"]["unsubmitted_count"], 1)
        self.assertEqual(payload["bank_rows"][0]["bank_name"], "建行基本户")
        self.assertEqual(payload["bank_rows"][0]["account_last4"], "8106")
        self.assertEqual(payload["oa_rows"][0]["linked_invoice_row_ids"], [INVOICE_ROW_ID])
        self.assertEqual(payload["pagination"]["bank_rows"]["total"], 1)
        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("read_model_scope_keys", payload)
        self.assertNotIn("refresh_enqueued", payload)
        self.assertEqual([phase for phase, _duration in timings], ["canonical_snapshot", "payload_assembly"])

    def test_empty_snapshot_returns_observable_empty_lists_and_totals(self) -> None:
        repository = FakeBatchAccountingQueryRepository()
        repository.list_payload = {
            "summary": {"unsubmitted_count": 0, "submitted_count": 0, "oa_count": 0},
            "bank_rows": [],
            "oa_rows": [],
            "invoice_rows": [],
            "relations": [],
            "member_rows": [],
            "pagination": {
                "bank_rows": {"page": 1, "page_size": 100, "pageSize": 100, "total": 0},
                "oa_rows": {"page": 1, "page_size": 100, "pageSize": 100, "total": 0},
            },
        }

        payload = service(repository).build_payload(bank_year="2026", bucket="unsubmitted")

        self.assertEqual(payload["bank_rows"], [])
        self.assertEqual(payload["oa_rows"], [])
        self.assertEqual(payload["summary"]["submitted_count"], 0)
        self.assertEqual(payload["pagination"]["oa_rows"]["total"], 0)

    def test_maximum_page_payload_assembly_is_bounded(self) -> None:
        repository = FakeBatchAccountingQueryRepository()
        repository.list_payload = {
            "summary": {"unsubmitted_count": 200, "submitted_count": 0, "oa_count": 200},
            "bank_rows": [bank_row(row_id=f"bank-{index}") for index in range(200)],
            "oa_rows": [oa_row(row_id=f"oa-{index}") for index in range(200)],
            "invoice_rows": [
                invoice_row(row_id=f"invoice-{index}", source_oa_id=f"oa-{index}")
                for index in range(200)
            ],
            "relations": [],
            "member_rows": [],
            "pagination": {
                "bank_rows": {"page": 1, "page_size": 200, "pageSize": 200, "total": 200},
                "oa_rows": {"page": 1, "page_size": 200, "pageSize": 200, "total": 200},
            },
        }

        started_at = perf_counter()
        status, payload = BatchAccountingApiRoutes(lambda: service(repository)).list_payload(
            {
                "bank_year": ["2026"],
                "bucket": ["unsubmitted"],
                "bank_page_size": ["200"],
                "oa_page_size": ["200"],
            }
        )
        duration_ms = (perf_counter() - started_at) * 1000

        self.assertEqual(status, 200)
        self.assertEqual(len(payload["bank_rows"]), 200)
        self.assertEqual(len(payload["oa_rows"]), 200)
        self.assertLess(duration_ms, 500)

    def test_submitted_payload_uses_active_batch_relation_and_canonical_members(self) -> None:
        repository = FakeBatchAccountingQueryRepository()
        relation = active_relation()
        repository.list_payload = {
            "summary": {"unsubmitted_count": 0, "submitted_count": 1, "oa_count": 0},
            "bank_rows": [{**bank_row(), "relation_id": RELATION_ID, "version": 3}],
            "oa_rows": [],
            "relations": [{**relation, "bank_row": {**bank_row(), "relation_id": RELATION_ID, "version": 3}}],
            "member_rows": [
                {"member_type": "oa", "id": OA_ROW_ID, "payload": oa_row()},
                {"member_type": "invoice", "id": INVOICE_ROW_ID, "payload": invoice_row()},
            ],
            "pagination": {
                "bank_rows": {"page": 1, "page_size": 200, "pageSize": 200, "total": 1}
            },
        }

        payload = service(repository).build_payload(bank_year="2026", bucket="submitted")

        self.assertEqual(payload["summary"]["submitted_count"], 1)
        self.assertEqual(payload["bank_rows"][0]["relation_id"], RELATION_ID)
        self.assertEqual(payload["bank_rows"][0]["version"], 1)
        bucket = payload["relations_by_bank_row_id"][BANK_ROW_ID]
        self.assertEqual(bucket["relation"]["relation_mode"], "batch_accounting")
        self.assertEqual(bucket["relation"]["relation_id"], RELATION_ID)
        self.assertEqual(bucket["oa_rows"][0]["id"], OA_ROW_ID)
        self.assertEqual(bucket["oa_rows"][0]["linked_invoice_row_ids"], [INVOICE_ROW_ID])

    def test_invalid_year_bucket_paging_and_search_fail_fast(self) -> None:
        cases = (
            ({"bank_year": "26", "bucket": "unsubmitted"}, "invalid_batch_accounting_year"),
            ({"bank_year": "2026", "bucket": "unknown"}, "invalid_batch_accounting_bucket"),
            ({"bank_year": "2026", "bucket": "unsubmitted", "bank_page": 0}, "invalid_paging"),
            ({"bank_year": "2026", "bucket": "unsubmitted", "oa_page_size": 201}, "invalid_paging"),
            (
                {"bank_year": "2026", "bucket": "unsubmitted", "oa_search": "x" * 201},
                "invalid_batch_accounting_search",
            ),
        )
        for kwargs, code in cases:
            with self.subTest(code=code), self.assertRaises(BatchAccountingError) as context:
                service().build_payload(**kwargs)
            self.assertEqual(context.exception.code, code)

    def test_submit_deduplicates_rows_and_delegates_canonical_command(self) -> None:
        repository = FakeBatchAccountingQueryRepository()
        command = RecordingRelationCommandService()

        result = service(repository, command).submit(
            bank_year="2026",
            bank_row_id=BANK_ROW_ID,
            oa_row_ids=[OA_ROW_ID, OA_ROW_ID],
            actor="finance-user",
            expected_version=1,
        )

        self.assertEqual(
            repository.submission_calls,
            [{"bank_year": "2026", "bank_row_id": BANK_ROW_ID, "oa_row_ids": [OA_ROW_ID]}],
        )
        self.assertEqual(
            command.active_relation_calls,
            [[BANK_ROW_ID, OA_ROW_ID, INVOICE_ROW_ID]],
        )
        call = command.confirm_calls[0]
        self.assertEqual(call["relation_mode"], "batch_accounting")
        self.assertEqual(call["row_ids"], [BANK_ROW_ID, OA_ROW_ID, INVOICE_ROW_ID])
        self.assertEqual(call["row_types"], ["bank", "oa", "invoice"])
        self.assertEqual(call["special_metadata"]["affected_scope_keys"], ["2026-01"])
        self.assertEqual(result["relation_id"], RELATION_ID)

    def test_submit_requires_note_for_amount_mismatch_and_rejects_stale_version(self) -> None:
        repository = FakeBatchAccountingQueryRepository()
        repository.submission_payload["oa_rows"] = [oa_row(amount="1000.00")]
        with self.assertRaises(BatchAccountingError) as missing_note:
            service(repository).submit(
                bank_year="2026",
                bank_row_id=BANK_ROW_ID,
                oa_row_ids=[OA_ROW_ID],
                actor="finance-user",
                note=" ",
            )
        self.assertEqual(missing_note.exception.code, "batch_accounting_note_required")
        self.assertEqual(missing_note.exception.payload["amount_check"]["amount_delta"], "200.00")

        with self.assertRaises(BatchAccountingError) as stale:
            service().submit(
                bank_year="2026",
                bank_row_id=BANK_ROW_ID,
                oa_row_ids=[OA_ROW_ID],
                actor="finance-user",
                expected_version=2,
            )
        self.assertEqual(stale.exception.code, "batch_accounting_version_conflict")

    def test_submit_preserves_cross_month_relation_scope_and_oa_years(self) -> None:
        repository = FakeBatchAccountingQueryRepository()
        repository.submission_payload["oa_rows"] = [oa_row(apply_time="2025-12-31")]
        command = RecordingRelationCommandService()

        result = service(repository, command).submit(
            bank_year="2026",
            bank_row_id=BANK_ROW_ID,
            oa_row_ids=[OA_ROW_ID],
            actor="finance-user",
        )

        metadata = command.confirm_calls[0]["special_metadata"]
        self.assertEqual(command.confirm_calls[0]["month_scope"], "all")
        self.assertEqual(metadata["affected_scope_keys"], ["2025-12", "2026-01"])
        self.assertEqual(metadata["oa_years"], ["2025"])
        self.assertEqual(result["affected_scope_keys"], ["2025-12", "2026-01"])

    def test_submit_rejects_bank_or_oa_linked_to_another_bank_but_allows_invoice_only_oa_relation(self) -> None:
        command = RecordingRelationCommandService()
        command.active_relations = [
            {
                "case_id": "CASE-OTHER-BANK",
                "status": "active",
                "relation_mode": "manual_confirmed",
                "row_ids": [BANK_ROW_ID, "oa-other"],
                "row_types": ["bank", "oa"],
            }
        ]
        with self.assertRaises(BatchAccountingError) as bank_conflict:
            service(command_service=command).submit(
                bank_year="2026",
                bank_row_id=BANK_ROW_ID,
                oa_row_ids=[OA_ROW_ID],
                actor="finance-user",
            )
        self.assertEqual(bank_conflict.exception.code, "batch_accounting_bank_row_already_linked")

        command.active_relations = [
            {
                "case_id": "CASE-INVOICE-ONLY",
                "status": "active",
                "relation_mode": "existing_case",
                "row_ids": [OA_ROW_ID, INVOICE_ROW_ID],
                "row_types": ["oa", "invoice"],
            }
        ]
        result = service(command_service=command).submit(
            bank_year="2026",
            bank_row_id=BANK_ROW_ID,
            oa_row_ids=[OA_ROW_ID],
            actor="finance-user",
        )
        self.assertTrue(result["success"])
        self.assertEqual(command.confirm_calls[-1]["before_relations"][0]["case_id"], "CASE-INVOICE-ONLY")

        command.active_relations = [
            {
                "case_id": "CASE-OA-BANK",
                "status": "active",
                "relation_mode": "manual_confirmed",
                "row_ids": ["bank-other", OA_ROW_ID],
                "row_types": ["bank", "oa"],
            }
        ]
        with self.assertRaises(BatchAccountingError) as oa_conflict:
            service(command_service=command).submit(
                bank_year="2026",
                bank_row_id=BANK_ROW_ID,
                oa_row_ids=[OA_ROW_ID],
                actor="finance-user",
            )
        self.assertEqual(oa_conflict.exception.code, "invalid_batch_accounting_oa_row")

    def test_command_conflict_is_exposed_as_batch_conflict(self) -> None:
        command = RecordingRelationCommandService()
        command.confirm_error = WorkbenchRelationCommandError(
            "workbench_relation_active_row_conflict",
            "conflict",
            payload={"conflicting_row_ids": [OA_ROW_ID]},
        )
        with self.assertRaises(BatchAccountingError) as context:
            service(command_service=command).submit(
                bank_year="2026",
                bank_row_id=BANK_ROW_ID,
                oa_row_ids=[OA_ROW_ID],
                actor="finance-user",
            )
        self.assertEqual(context.exception.code, "batch_accounting_relation_conflict")
        self.assertEqual(context.exception.payload["conflicting_row_ids"], [OA_ROW_ID])

    def test_withdraw_requires_reason_active_batch_relation_and_matching_version(self) -> None:
        command = RecordingRelationCommandService()
        command.relation_by_case_id = active_relation(version=3)
        target = service(command_service=command)

        with self.assertRaises(BatchAccountingError) as no_reason:
            target.withdraw(relation_id=RELATION_ID, actor="finance-user", reason=" ")
        self.assertEqual(no_reason.exception.code, "batch_accounting_withdraw_reason_required")

        with self.assertRaises(BatchAccountingError) as conflict:
            target.withdraw(
                relation_id=RELATION_ID,
                actor="finance-user",
                reason="更正",
                expected_version=2,
            )
        self.assertEqual(conflict.exception.code, "batch_accounting_version_conflict")

        result = target.withdraw(
            relation_id=RELATION_ID,
            actor="finance-user",
            reason="更正",
            expected_version=3,
        )
        self.assertTrue(result["success"])
        self.assertEqual(command.cancel_calls[0]["history_operation_type"], "withdraw_link")
        self.assertEqual(result["affected_scope_keys"], ["2026-01"])

    def test_missing_query_or_command_dependency_fails_closed(self) -> None:
        with self.assertRaises(BatchAccountingError) as query:
            BatchAccountingService().build_payload(bank_year="2026", bucket="unsubmitted")
        self.assertEqual(query.exception.code, "batch_accounting_canonical_query_unavailable")

        with self.assertRaises(BatchAccountingError) as command:
            BatchAccountingService(query_repository=FakeBatchAccountingQueryRepository()).submit(
                bank_year="2026",
                bank_row_id=BANK_ROW_ID,
                oa_row_ids=[OA_ROW_ID],
                actor="finance-user",
            )
        self.assertEqual(command.exception.code, "batch_accounting_relation_command_unavailable")


class BatchAccountingApiRouteTests(unittest.TestCase):
    @staticmethod
    def _session() -> SimpleNamespace:
        return SimpleNamespace(identity=SimpleNamespace(username="finance-user", user_id="42"))

    def test_list_parses_dual_paging_and_search_and_returns_canonical_shape(self) -> None:
        repository = FakeBatchAccountingQueryRepository()
        routes = BatchAccountingApiRoutes(lambda: service(repository))

        status, payload = routes.list_payload(
            {
                "bank_year": ["2026"],
                "bucket": ["unsubmitted"],
                "bank_page": ["2"],
                "bank_page_size": ["50"],
                "oa_page": ["3"],
                "oa_page_size": ["40"],
                "oa_search": ["项目"],
            }
        )

        self.assertEqual(status, 200)
        self.assertEqual(repository.list_calls[0]["bank_page"], 2)
        self.assertEqual(repository.list_calls[0]["oa_search"], "项目")
        self.assertEqual(
            set(payload),
            {"summary", "bank_rows", "oa_rows", "relations_by_bank_row_id", "pagination"},
        )

    def test_route_maps_invalid_query_conflict_and_unavailable_dependencies(self) -> None:
        routes = BatchAccountingApiRoutes(lambda: BatchAccountingService())
        invalid_status, invalid_payload = routes.list_payload(
            {"bank_year": ["2026"], "bucket": ["unsubmitted"], "bank_page": ["0"]}
        )
        unavailable_status, unavailable_payload = routes.list_payload(
            {"bank_year": ["2026"], "bucket": ["unsubmitted"]}
        )
        command = RecordingRelationCommandService()
        command.confirm_error = WorkbenchRelationCommandError(
            "workbench_relation_active_row_conflict",
            "conflict",
        )
        conflict_routes = BatchAccountingApiRoutes(lambda: service(command_service=command))
        conflict_status, conflict_payload = conflict_routes.submit(
            {
                "bank_year": "2026",
                "bank_row_id": BANK_ROW_ID,
                "oa_row_ids": [OA_ROW_ID],
            },
            session=self._session(),
        )

        self.assertEqual(invalid_status, 400)
        self.assertEqual(invalid_payload["error"], "invalid_paging")
        self.assertEqual(unavailable_status, 503)
        self.assertEqual(unavailable_payload["error"], "batch_accounting_canonical_query_unavailable")
        self.assertEqual(conflict_status, 409)
        self.assertEqual(conflict_payload["error"], "batch_accounting_relation_conflict")

    def test_mutation_response_has_scopes_without_read_model_targets(self) -> None:
        command = RecordingRelationCommandService()
        routes = BatchAccountingApiRoutes(lambda: service(command_service=command))

        status, payload = routes.submit(
            {
                "bank_year": "2026",
                "bank_row_id": BANK_ROW_ID,
                "oa_row_ids": [OA_ROW_ID],
            },
            session=self._session(),
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["affected_months"], ["2026-01"])
        for old_field in (
            "read_model_status",
            "read_model_scope_keys",
            "refresh_enqueued",
            "freshness_targets",
            "operation_barrier_targets",
        ):
            self.assertNotIn(old_field, payload)

    def test_read_export_only_session_cannot_submit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="202",
                username="READONLY001",
                nickname="只读用户",
                display_name="只读用户",
                roles=["finance"],
                permissions=[],
            )
            response = app.handle_request(
                "POST",
                "/api/batch-accounting/submit",
                body=json.dumps(
                    {
                        "bank_year": "2026",
                        "bank_row_id": BANK_ROW_ID,
                        "oa_row_ids": [OA_ROW_ID],
                    }
                ),
                headers={"Authorization": "Bearer readonly-user"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.body)["error"], "permission_denied")


if __name__ == "__main__":
    unittest.main()
