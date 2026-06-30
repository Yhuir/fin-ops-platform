from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest

from fin_ops_platform.services.no_oa_bank_batch_application_service import (
    NoOaBankBatchApplicationService,
    NoOaBankBatchPersistenceError,
    NoOaPairRelationSnapshotPort,
)
from fin_ops_platform.services.no_oa_bank_batch_read_model_repository import NoOaBankBatchReadModelRepositoryPort
from fin_ops_platform.services.no_oa_bank_batch_service import (
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    NoOaBankBatchService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class WriteBlockingNoOaPairRelationService(WorkbenchPairRelationService):
    def create_active_relation(self, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("no-OA relation writes must delegate to WorkbenchRelationCommandService.")

    def cancel_relation(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("no-OA relation writes must delegate to WorkbenchRelationCommandService.")


class RecordingNoOaRelationCommandService:
    def __init__(self) -> None:
        self.preflight_calls: list[dict[str, object]] = []
        self.confirm_calls: list[dict[str, object]] = []
        self.cancel_calls: list[dict[str, object]] = []

    def assert_write_precondition(self, **kwargs: object) -> dict[str, object]:
        self.preflight_calls.append(dict(kwargs))
        return {
            "status": "fresh",
            "read_model_scope_keys": [str(kwargs.get("month_scope") or "all")],
            "stale_reasons": [],
            "refresh_enqueued": False,
        }

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        relation = {
            "case_id": str(kwargs["case_id"]),
            "row_ids": list(kwargs["row_ids"]),
            "row_types": list(kwargs["row_types"]),
            "status": "active",
            "relation_mode": str(kwargs["relation_mode"]),
            "month_scope": str(kwargs.get("month_scope") or "all"),
            "special_metadata": dict(kwargs.get("special_metadata") or {}),
            "display_tags": list(kwargs.get("display_tags") or []),
            "evidence": dict(kwargs.get("evidence") or {}),
            "version": 1,
        }
        return {
            "status": "confirmed",
            "relation": relation,
            "history": {"operation_type": str(kwargs.get("history_operation_type") or "confirm_relation")},
            "changed_case_ids": [relation["case_id"]],
            "affected_months": [relation["month_scope"]],
            "version": 1,
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": [relation["month_scope"]],
            "refresh_enqueued": False,
            "idempotent_replay": False,
        }

    def cancel_relation(self, **kwargs: object) -> dict[str, object]:
        self.cancel_calls.append(dict(kwargs))
        return {
            "status": "cancelled",
            "relation": {
                "case_id": str(kwargs["case_id"]),
                "row_ids": [],
                "status": "cancelled",
                "version": 2,
            },
            "history": {"operation_type": str(kwargs.get("history_operation_type") or "cancel_relation")},
            "changed_case_ids": [str(kwargs["case_id"])],
            "affected_months": ["2026-03"],
            "version": 2,
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": ["2026-03"],
            "refresh_enqueued": False,
            "idempotent_replay": False,
        }


class EmptyWorkbenchRelationFacade:
    def __init__(self) -> None:
        self.last_source_versions: dict[str, object] = {}

    def list_by_month(self, month: str, **_kwargs: object) -> dict[str, object]:
        self.last_source_versions = {"schema_version": 52, "scope_key": month}
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": dict(self.last_source_versions),
            "read_model_scope_keys": [month],
        }

    def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        self.last_source_versions = {"schema_version": 52, "scope_key": "2026-03"}
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": dict(self.last_source_versions),
            "read_model_scope_keys": ["2026-03"],
        }

    def source_versions_for_month(self, month: str, **_kwargs: object) -> dict[str, object]:
        self.last_source_versions = {"schema_version": 52, "scope_key": month}
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": dict(self.last_source_versions),
            "read_model_scope_keys": [month],
        }


def no_oa_bank_row(
    row_id: str,
    *,
    category_code: str,
    debit_amount: str = "",
    credit_amount: str = "",
    account_key: str = "CCB:8106",
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "category_code": category_code,
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
        "amount": debit_amount or credit_amount,
        "direction": "expense" if debit_amount else "income",
        "account_key": account_key,
        "bank_name": account_key.split(":", 1)[0],
        "account_no": f"622200000000{account_key.split(':', 1)[-1]}",
        "account_last4": account_key.split(":", 1)[-1],
        "pay_receive_time": "2026-03-10T09:00:00",
        "counterparty_name": "云南三源",
    }


def no_oa_categories(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    labels = {"fee": "手续费", "salary": "工资", "internal_transfer": "内部往来款"}
    return {
        str(row["id"]): {
            "transaction_id": row["id"],
            "category_code": row["category_code"],
            "category_label": labels.get(str(row["category_code"]), str(row["category_code"])),
            "category_source": "auto",
        }
        for row in rows
    }


class NoOaBankBatchApplicationServiceTests(unittest.TestCase):
    def _application_service(
        self,
        *,
        rows: list[dict[str, object]],
        selected_tag_codes: list[str],
        pair_relation_service: WorkbenchPairRelationService | None = None,
        relation_command_service: object | None = None,
        no_oa_snapshot: dict[str, object] | None = None,
        no_oa_bank_batch_read_model_repository: object | None = None,
        workbench_sql_read_repository: object | None = None,
        read_model_refresh_producer: object | None = None,
        relation_facade: object | None = None,
    ) -> tuple[NoOaBankBatchApplicationService, NoOaBankBatchService, RecordingNoOaRelationCommandService]:
        categories = no_oa_categories(rows)
        pair_service = pair_relation_service or WorkbenchPairRelationService()
        command_service = (
            relation_command_service
            if isinstance(relation_command_service, RecordingNoOaRelationCommandService)
            else RecordingNoOaRelationCommandService()
        )
        no_oa_service = NoOaBankBatchService.from_snapshot(
            no_oa_snapshot,
            pair_relation_service=pair_service,
            relation_command_service=command_service,
        )
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(list_transactions=lambda month="all": deepcopy(rows)),
            effective_category_provider=SimpleNamespace(
                bulk_get_for_rows=lambda bank_rows: {
                    str(row.get("id")): deepcopy(categories[str(row.get("id"))])
                    for row in bank_rows
                    if str(row.get("id")) in categories
                }
            ),
            no_oa_bank_batch_service=no_oa_service,
            app_settings_service=SimpleNamespace(
                get_no_oa_bank_batch_tag_selection_payload=lambda: {
                    "version": 1,
                    "selected_tag_codes": list(selected_tag_codes),
                }
            ),
            bank_transaction_category_service=SimpleNamespace(
                snapshot=lambda: {},
                tag_dictionary_payload=lambda: {"definitions": []},
            ),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(pair_service),
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {}),
            state_store=None,
            relation_facade=relation_facade or EmptyWorkbenchRelationFacade(),
            relation_command_service=command_service,
            no_oa_bank_batch_read_model_repository=no_oa_bank_batch_read_model_repository,
            workbench_sql_read_repository=workbench_sql_read_repository,
            read_model_refresh_producer=read_model_refresh_producer,
        )
        return service, no_oa_service, command_service

    def test_read_model_repository_port_excludes_unrelated_methods(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_no_oa_bank_batch_rows(self, filters: dict[str, object] | None = None) -> list[dict[str, object]]:
                self.calls.append(dict(filters or {}))
                return [{"batch_id": "batch-1"}]

            def no_oa_bank_batch_source_versions_summary(
                self,
                filters: dict[str, object] | None = None,
            ) -> dict[str, object]:
                self.calls.append({"summary_filters": dict(filters or {})})
                return {"read_model_status": "fresh", "row_count": 1, "source_versions": {"schema": "v1"}}

            def list_pending_invoice_rows(self, **_kwargs: object) -> list[dict[str, object]]:
                raise AssertionError("no-OA port must not expose pending invoice methods")

        repository = Repository()
        port = NoOaBankBatchReadModelRepositoryPort(repository)

        self.assertEqual(port.list_no_oa_bank_batch_rows({"month": "2026-06"}), [{"batch_id": "batch-1"}])
        self.assertEqual(
            port.no_oa_bank_batch_source_versions_summary({"month": "2026-06"})["source_versions"],
            {"schema": "v1"},
        )
        self.assertFalse(hasattr(port, "list_pending_invoice_rows"))
        self.assertEqual(repository.calls, [{"month": "2026-06"}, {"summary_filters": {"month": "2026-06"}}])

    def test_submit_batch_delegates_relation_write_to_command_service(self) -> None:
        rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        pair_service = WriteBlockingNoOaPairRelationService()
        service, no_oa_service, relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
            pair_relation_service=pair_service,
        )
        service.refresh_batches()
        batch = no_oa_service.list_batches({"bucket": "unsubmitted"})[0]

        result = service.submit_batch(
            str(batch["batch_id"]),
            actor="finance-user",
            expected_version=int(batch["version"]),
            note="确认",
        )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(len(relation_command.confirm_calls), 1)
        call = relation_command.confirm_calls[0]
        self.assertEqual(call["case_id"], batch["relation_case_id"])
        self.assertEqual(call["row_ids"], ["fee-1"])
        self.assertEqual(call["row_types"], ["bank"])
        self.assertEqual(call["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["special_metadata"]["source"], "no_oa_bank_batch")
        self.assertEqual(call["special_metadata"]["source_batch_id"], batch["batch_id"])
        self.assertEqual(call["special_metadata"]["row_tag_snapshot"]["fee-1"]["category_code"], "fee")
        self.assertEqual(call["special_metadata"]["row_tag_snapshot"]["fee-1"]["category_label"], "手续费")
        self.assertEqual(call["display_tags"], ["免OA", "手续费"])

    def test_submitted_batch_detail_keeps_submitted_row_tags_after_bank_category_changes(self) -> None:
        initial_rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        service, no_oa_service, _relation_command = self._application_service(
            rows=initial_rows,
            selected_tag_codes=["fee", "salary"],
        )
        service.refresh_batches()
        batch = no_oa_service.list_batches({"bucket": "unsubmitted"})[0]
        submitted = service.submit_batch(
            str(batch["batch_id"]),
            actor="finance-user",
            expected_version=int(batch["version"]),
            note="确认",
        )

        changed_rows = [no_oa_bank_row("fee-1", category_code="salary", debit_amount="3.00")]
        service_after_change, _no_oa_after_change, _relation_command_after_change = self._application_service(
            rows=changed_rows,
            selected_tag_codes=["fee", "salary"],
            no_oa_snapshot=no_oa_service.snapshot(),
        )

        detail = service_after_change.detail_payload(str(submitted["batch"]["batch_id"]))

        self.assertEqual(detail["batch"]["status"], "submitted")
        self.assertEqual(detail["batch"]["batch_type"], "fee")
        self.assertEqual(detail["rows"][0]["category_code"], "fee")
        self.assertEqual(detail["rows"][0]["category_label"], "手续费")
        self.assertEqual(detail["categories_by_transaction_id"]["fee-1"]["category_code"], "fee")
        self.assertEqual(detail["categories_by_transaction_id"]["fee-1"]["category_label"], "手续费")

    def test_list_batches_explicit_pagination_protects_first_screen_slo(self) -> None:
        rows = [
            no_oa_bank_row(
                f"fee-{index:03d}",
                category_code="fee",
                debit_amount="1.00",
                account_key=f"CCB:{index:04d}",
            )
            for index in range(250)
        ]
        service, _no_oa_service, _relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
        )
        service.refresh_batches()

        first_page = service.list_batches_payload({"bucket": ["unsubmitted"], "page": ["1"], "page_size": ["200"]})
        second_page = service.list_batches_payload({"bucket": ["unsubmitted"], "page": ["2"], "page_size": ["200"]})

        self.assertEqual(len(first_page["batches"]), 200)
        self.assertEqual(first_page["summary"]["total"], 250)
        self.assertEqual(first_page["pagination"], {"page": 1, "page_size": 200, "pageSize": 200, "total": 250})
        self.assertEqual(len(second_page["batches"]), 50)
        self.assertEqual(second_page["summary"]["total"], 250)
        self.assertEqual(second_page["pagination"], {"page": 2, "page_size": 200, "pageSize": 200, "total": 250})

        with self.assertRaisesRegex(ValueError, "page_size must be <= 200") as context:
            service.list_batches_payload({"page": ["1"], "page_size": ["201"]})
        self.assertEqual(getattr(context.exception, "error_code", ""), "invalid_paging")

    def test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted(self) -> None:
        class ReadRepository:
            def __init__(self) -> None:
                self.rows: list[dict[str, object]] = []

            def list_no_oa_bank_batch_rows(self, _filters: dict[str, object]) -> list[dict[str, object]]:
                return deepcopy(self.rows)

        repository = ReadRepository()
        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee"],
            no_oa_bank_batch_read_model_repository=repository,
        )
        repository.rows = [
            {
                "batch_id": "batch-stale-but-linked",
                "batch_type": "fee",
                "batch_label": "手续费",
                "scope_month": "2026-03",
                "account_key": "CCB:8106",
                "status": "stale",
                "status_bucket": "submitted",
                "row_count": 2,
                "total_amount": "86.00",
                "blocked_reason": "源流水或分类已变化，需要复核后处理。",
                "can_submit": False,
                "can_withdraw": True,
                "version": 4,
                "source_versions": service.no_oa_bank_batch_source_versions(),
            }
        ]

        payload = service.list_batches_payload({"bucket": ["submitted"]})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["summary"]["submitted_count"], 1)
        self.assertEqual(payload["summary"]["stale_count"], 0)
        self.assertEqual(payload["summary"]["categories"][0]["submitted"], 1)
        self.assertEqual(payload["summary"]["categories"][0]["stale"], 0)
        batch = payload["batches"][0]
        self.assertEqual(batch["status"], "submitted")
        self.assertEqual(batch["status_bucket"], "submitted")
        self.assertEqual(batch["relation_backed_status"], "stale")
        self.assertEqual(batch["blocked_reason"], "")
        self.assertEqual(batch["can_submit"], False)
        self.assertEqual(batch["can_withdraw"], True)

    def test_bank_flow_list_uses_relation_mode_read_model_boundary(self) -> None:
        class ReadRepository:
            def __init__(self, service: NoOaBankBatchApplicationService) -> None:
                self.service = service
                self.calls: list[dict[str, object]] = []
                self.rows = [
                    {
                        "batch_id": "legacy-no-oa-submitted",
                        "relation_mode": "no_oa_bank_batch",
                        "batch_type": "fee",
                        "scope_month": "2026-03",
                        "status": "submitted",
                        "status_bucket": "submitted",
                        "row_count": 1,
                        "total_amount": "3.00",
                        "source_versions": self.service.no_oa_bank_batch_source_versions(),
                    },
                    {
                        "batch_id": "bank-flow-submitted",
                        "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                        "batch_type": "fee",
                        "scope_month": "2026-03",
                        "status": "submitted",
                        "status_bucket": "submitted",
                        "row_count": 1,
                        "total_amount": "5.00",
                        "source_versions": self.service.no_oa_bank_batch_source_versions(),
                    },
                ]

            def list_no_oa_bank_batch_rows(self, filters: dict[str, object]) -> list[dict[str, object]]:
                self.calls.append(dict(filters))
                relation_mode = str(filters.get("relation_mode") or "")
                bucket = str(filters.get("bucket") or "")
                rows = [deepcopy(row) for row in self.rows if str(row.get("relation_mode") or "") == relation_mode]
                if bucket:
                    rows = [row for row in rows if str(row.get("status_bucket") or "") == bucket]
                return rows

        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee"],
        )
        repository = ReadRepository(service)
        service._no_oa_bank_batch_read_model_repository = repository

        payload = service.list_batches_payload(
            {"bucket": ["submitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual([batch["batch_id"] for batch in payload["batches"]], ["bank-flow-submitted"])
        self.assertEqual(repository.calls[0]["relation_mode"], BANK_FLOW_RULE_BATCH_RELATION_MODE)
        self.assertEqual(repository.calls[1]["relation_mode"], BANK_FLOW_RULE_BATCH_RELATION_MODE)

    def test_month_missing_read_model_refreshes_month_scope(self) -> None:
        class ReadRepository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_no_oa_bank_batch_rows(self, filters: dict[str, object]) -> None:
                self.calls.append(dict(filters))
                return None

        class RefreshProducer:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def enqueue(self, scope_keys: list[str], *, reason: str, metadata: dict[str, object] | None = None) -> bool:
                self.calls.append({"scope_keys": list(scope_keys), "reason": reason, "metadata": metadata})
                return True

        repository = ReadRepository()
        producer = RefreshProducer()
        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee"],
            no_oa_bank_batch_read_model_repository=repository,
            read_model_refresh_producer=producer,
        )

        payload = service.list_batches_payload(
            {"month": ["2026-06"], "bucket": ["unsubmitted"], "page": ["1"], "page_size": ["200"]}
        )

        self.assertEqual(payload["read_model_status"], "missing")
        self.assertEqual(payload["refresh_reason"], "api_no_oa_read_model_missing")
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(
            producer.calls,
            [{"scope_keys": ["2026-06"], "reason": "api_no_oa_read_model_missing", "metadata": None}],
        )
        self.assertEqual(repository.calls[0], {
            "month": "2026-06",
            "account_key": "",
            "relation_mode": "no_oa_bank_batch",
        })
        self.assertEqual(
            repository.calls[1],
            {
                "month": "2026-06",
                "type": "",
                "status": "",
                "bucket": "unsubmitted",
                "account_key": "",
                "relation_mode": "no_oa_bank_batch",
            },
        )

    def test_month_stale_read_model_refreshes_month_scope(self) -> None:
        class ReadRepository:
            def __init__(self, rows: list[dict[str, object]]) -> None:
                self.rows = rows

            def list_no_oa_bank_batch_rows(self, _filters: dict[str, object]) -> list[dict[str, object]]:
                return deepcopy(self.rows)

        class RefreshProducer:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def enqueue(self, scope_keys: list[str], *, reason: str, metadata: dict[str, object] | None = None) -> bool:
                self.calls.append({"scope_keys": list(scope_keys), "reason": reason, "metadata": metadata})
                return True

        producer = RefreshProducer()
        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee"],
            no_oa_bank_batch_read_model_repository=None,
            read_model_refresh_producer=producer,
        )
        stale_versions = dict(service.no_oa_bank_batch_source_versions())
        stale_versions["no_oa_bank_batch_schema_version"] = "stale"
        repository = ReadRepository(
            [
                {
                    "batch_id": "batch-draft-fee",
                    "batch_type": "fee",
                    "scope_month": "2026-06",
                    "account_key": "CCB:8106",
                    "status": "draft",
                    "status_bucket": "unsubmitted",
                    "row_count": 1,
                    "total_amount": "1.00",
                    "can_submit": True,
                    "can_withdraw": False,
                    "version": 1,
                    "source_versions": stale_versions,
                }
            ]
        )
        service._no_oa_bank_batch_read_model_repository = repository

        payload = service.list_batches_payload({"month": ["2026-06"], "bucket": ["unsubmitted"]})

        self.assertEqual(payload["read_model_status"], "stale")
        self.assertEqual(payload["refresh_reason"], "api_no_oa_source_versions_stale")
        self.assertEqual(
            producer.calls,
            [{"scope_keys": ["2026-06"], "reason": "api_no_oa_source_versions_stale", "metadata": None}],
        )

    def test_month_sql_read_model_loads_relation_source_versions_before_stale_check(self) -> None:
        class RelationFacade:
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.last_source_versions: dict[str, object] = {"scope_key": "2026-01", "source_version": 1}

            def source_versions_for_month(self, month: str, *_args: object, **_kwargs: object) -> dict[str, object]:
                self.calls.append(month)
                self.last_source_versions = {"scope_key": month, "source_version": 2}
                return {
                    "status": "fresh",
                    "rows": [],
                    "groups": [],
                    "source_versions": dict(self.last_source_versions),
                    "read_model_scope_keys": [month],
                }

        class ReadRepository:
            def __init__(self) -> None:
                self.rows: list[dict[str, object]] = []

            def list_no_oa_bank_batch_rows(self, _filters: dict[str, object]) -> list[dict[str, object]]:
                return deepcopy(self.rows)

        relation_facade = RelationFacade()
        repository = ReadRepository()
        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee"],
            no_oa_bank_batch_read_model_repository=repository,
            relation_facade=relation_facade,
        )
        relation_facade.source_versions_for_month("2026-06")
        repository.rows = [
            {
                "batch_id": "batch-fresh-fee",
                "batch_type": "fee",
                "scope_month": "2026-06",
                "account_key": "CCB:8106",
                "status": "draft",
                "status_bucket": "unsubmitted",
                "row_count": 1,
                "total_amount": "12.00",
                "source_versions": service.no_oa_bank_batch_source_versions(),
            }
        ]
        relation_facade.last_source_versions = {"scope_key": "2026-01", "source_version": 1}
        relation_facade.calls = []

        payload = service.list_batches_payload(
            {"month": ["2026-06"], "bucket": ["unsubmitted"], "page": ["1"], "page_size": ["200"]}
        )

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload.get("read_model_stale_reasons", []), [])
        self.assertEqual(relation_facade.calls, ["2026-06"])

    def test_sql_read_model_exception_batches_are_not_public_payload(self) -> None:
        class ReadRepository:
            def __init__(self) -> None:
                self.rows: list[dict[str, object]] = []

            def list_no_oa_bank_batch_rows(self, filters: dict[str, object]) -> list[dict[str, object]]:
                rows = list(self.rows)
                bucket = str(filters.get("bucket") or "").strip()
                if bucket and bucket != "all":
                    rows = [row for row in rows if str(row.get("status_bucket") or "") == bucket]
                return deepcopy(rows)

        repository = ReadRepository()
        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee", "salary", "internal_transfer"],
            no_oa_bank_batch_read_model_repository=repository,
        )
        source_versions = service.no_oa_bank_batch_source_versions()
        repository.rows = [
            {
                "batch_id": "batch-draft-fee",
                "batch_type": "fee",
                "batch_label": "手续费",
                "scope_month": "2026-03",
                "account_key": "CCB:8106",
                "status": "draft",
                "status_bucket": "unsubmitted",
                "row_count": 1,
                "total_amount": "1.00",
                "can_submit": True,
                "can_withdraw": False,
                "version": 1,
                "source_versions": source_versions,
            },
            {
                "batch_id": "batch-conflict-transfer",
                "batch_type": "internal_transfer",
                "batch_label": "内部往来款",
                "scope_month": "2026-03",
                "account_key": "multi",
                "status": "conflict",
                "status_bucket": "unsubmitted",
                "row_count": 1,
                "total_amount": "1.00",
                "conflict_reason": "内部往来存在多解，不能自动形成可提交批次。",
                "can_submit": False,
                "can_withdraw": False,
                "version": 1,
                "source_versions": source_versions,
            },
            {
                "batch_id": "batch-stale-fee",
                "batch_type": "fee",
                "batch_label": "手续费",
                "scope_month": "2026-03",
                "account_key": "CCB:8106",
                "status": "stale",
                "status_bucket": "unsubmitted",
                "row_count": 1,
                "total_amount": "1.00",
                "blocked_reason": "源流水或分类已变化，需要复核后处理。",
                "can_submit": False,
                "can_withdraw": False,
                "version": 2,
                "source_versions": source_versions,
            },
            {
                "batch_id": "batch-submitted-salary",
                "batch_type": "salary",
                "batch_label": "工资",
                "scope_month": "2026-03",
                "account_key": "ICBC:6386",
                "status": "submitted",
                "status_bucket": "submitted",
                "row_count": 1,
                "total_amount": "2.00",
                "can_submit": False,
                "can_withdraw": True,
                "version": 3,
                "source_versions": source_versions,
            },
            {
                "batch_id": "batch-withdrawn-fee",
                "batch_type": "fee",
                "batch_label": "手续费",
                "scope_month": "2026-03",
                "account_key": "CCB:8106",
                "status": "withdrawn",
                "status_bucket": "withdrawn",
                "row_count": 1,
                "total_amount": "3.00",
                "can_submit": False,
                "can_withdraw": False,
                "version": 4,
                "source_versions": source_versions,
            },
        ]

        payload = service.list_batches_payload({"bucket": ["unsubmitted"], "page": ["1"], "page_size": ["200"]})

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual([batch["batch_id"] for batch in payload["batches"]], ["batch-draft-fee"])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 200, "pageSize": 200, "total": 1})
        self.assertEqual(payload["summary"]["total"], 3)
        self.assertEqual(payload["summary"]["draft_count"], 1)
        self.assertEqual(payload["summary"]["submitted_count"], 1)
        self.assertEqual(payload["summary"]["withdrawn_count"], 1)
        self.assertEqual(payload["summary"]["conflict_count"], 0)
        self.assertEqual(payload["summary"]["stale_count"], 0)

    def test_detail_payload_hides_non_public_exception_batches(self) -> None:
        rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="1.00")]
        service, _no_oa_service, _relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
            no_oa_snapshot={
                "batches": {
                    "batch-stale-fee": {
                        "batch_id": "batch-stale-fee",
                        "batch_type": "fee",
                        "batch_label": "手续费",
                        "scope_month": "2026-03",
                        "account_key": "CCB:8106",
                        "bank_name": "CCB",
                        "account_last4": "8106",
                        "status": "stale",
                        "status_bucket": "unsubmitted",
                        "row_ids": ["fee-1"],
                        "row_count": 1,
                        "total_amount": "1.00",
                        "version": 2,
                    }
                },
                "audit_log": [],
            },
        )

        with self.assertRaisesRegex(KeyError, "no_oa_bank_batch_not_found"):
            service.detail_payload("batch-stale-fee")

    def test_withdraw_batch_delegates_relation_cancel_to_command_service(self) -> None:
        rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        setup_pair_service = WorkbenchPairRelationService()
        setup_service = NoOaBankBatchService(pair_relation_service=setup_pair_service)
        draft = setup_service.build_batches(rows, no_oa_categories(rows), [], {})[0]
        submitted = setup_service.submit_batch(
            str(draft["batch_id"]),
            actor="finance-user",
            expected_version=int(draft["version"]),
            note="确认",
        )
        service, _no_oa_service, relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
            pair_relation_service=WriteBlockingNoOaPairRelationService(),
            no_oa_snapshot=setup_service.snapshot(),
        )

        result = service.withdraw_batch(
            str(submitted["batch_id"]),
            actor="finance-user",
            expected_version=int(submitted["version"]),
            reason="误提交",
        )

        self.assertEqual(result["batch"]["status"], "withdrawn")
        self.assertEqual(len(relation_command.cancel_calls), 1)
        call = relation_command.cancel_calls[0]
        self.assertEqual(call["case_id"], submitted["relation_case_id"])
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["reason"], "误提交")
        self.assertEqual(call["history_operation_type"], "no_oa_bank_batch_withdraw")

    def test_internal_transfer_from_workbench_delegates_relation_write_to_command_service(self) -> None:
        rows = [
            no_oa_bank_row(
                "transfer-out",
                category_code="internal_transfer",
                debit_amount="50000.00",
                account_key="CCB:8106",
            ),
            no_oa_bank_row(
                "transfer-in",
                category_code="internal_transfer",
                credit_amount="50000.00",
                account_key="CMB:3847",
            ),
        ]
        service, _no_oa_service, relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["internal_transfer"],
            pair_relation_service=WriteBlockingNoOaPairRelationService(),
        )

        result = service.submit_internal_transfer_rows_from_workbench(
            row_ids=["transfer-out", "transfer-in"],
            actor="finance-user",
            note="关联台确认内部往来",
        )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(len(relation_command.confirm_calls), 1)
        call = relation_command.confirm_calls[0]
        self.assertCountEqual(call["row_ids"], ["transfer-out", "transfer-in"])
        self.assertEqual(call["row_types"], ["bank", "bank"])
        self.assertEqual(call["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["special_metadata"]["batch_type"], "internal_transfer")
        self.assertEqual(call["display_tags"], ["免OA", "内部往来款"])

    def test_after_mutation_persists_changed_cases_and_expanded_workbench_scopes(self) -> None:
        lifecycle_events: list[dict[str, object]] = []
        cache_clears: list[str] = []

        class StateStore:
            def __init__(self) -> None:
                self.saved_mutations: list[dict[str, object]] = []

            def save_no_oa_bank_batch_mutation(self, **kwargs: object) -> None:
                self.saved_mutations.append(dict(kwargs))

        state_store = StateStore()
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(snapshot=lambda: {"batches": {}}),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(SimpleNamespace(
                snapshot=lambda: {"relations": "all"},
                snapshot_case_ids=lambda case_ids: {"relations": list(case_ids)},
            )),
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {"workbench": "snapshot"}),
            state_store=state_store,
            execute_derived_data_lifecycle_event=lambda event_type, **kwargs: lifecycle_events.append(
                {"event_type": event_type, **kwargs}
            ),
            expand_workbench_read_model_scope_keys_for_base_scopes=lambda scope_keys: [
                f"expanded:{scope_key}" for scope_key in scope_keys
            ],
            search_cache_clearer=lambda: cache_clears.append("search"),
        )

        changed = service.after_mutation(
            ["2026-05", "not-a-month", "2026-06"],
            changed_case_ids=["case-001", "case-002"],
            persist=True,
            action_name="no_oa_bank_batch_withdraw",
        )

        self.assertTrue(changed)
        self.assertEqual(
            lifecycle_events,
            [
                {
                    "event_type": "no_oa_bank_batch_changed",
                    "months": ["2026-05", "2026-06"],
                    "metadata": {
                        "source": "no_oa_bank_batch",
                        "action_name": "no_oa_bank_batch_withdraw",
                    },
                    "schedule_cost_warmup": False,
                }
            ],
        )
        self.assertEqual(cache_clears, ["search"])
        self.assertEqual(len(state_store.saved_mutations), 1)
        saved = state_store.saved_mutations[0]
        self.assertEqual(saved["changed_case_ids"], ["case-001", "case-002"])
        self.assertEqual(saved["changed_scope_keys"], ["expanded:all", "expanded:2026-05", "expanded:2026-06"])
        self.assertEqual(saved["pair_relation_snapshot"], {"relations": ["case-001", "case-002"]})
        self.assertEqual(saved["no_oa_bank_batch_snapshot"], {"batches": {}})
        self.assertEqual(saved["workbench_read_model_snapshot"], {"workbench": "snapshot"})

    def test_after_mutation_without_atomic_persistence_boundary_fails_fast(self) -> None:
        class BroadOnlyStateStore:
            def save_workbench_pair_relations(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("no-OA mutation must not fall back to broad pair relation persistence")

            def save_no_oa_bank_batches(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("no-OA mutation must not fall back to broad no-OA batch persistence")

            def save_workbench_read_models(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("no-OA mutation must not fall back to broad workbench read model persistence")

        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(snapshot=lambda: {"batches": {}}),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(SimpleNamespace(
                snapshot=lambda: {"relations": "all"},
                snapshot_case_ids=lambda case_ids: {"relations": list(case_ids)},
            )),
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {"workbench": "snapshot"}),
            state_store=BroadOnlyStateStore(),
            execute_derived_data_lifecycle_event=lambda *_args, **_kwargs: None,
        )

        with self.assertRaisesRegex(
            NoOaBankBatchPersistenceError,
            "save_no_oa_bank_batch_mutation",
        ):
            service.after_mutation(["2026-05"], changed_case_ids=["case-001"], persist=True)

    def test_after_mutation_without_persist_only_emits_lifecycle_event(self) -> None:
        lifecycle_events: list[dict[str, object]] = []

        class StateStore:
            def save_no_oa_bank_batch_mutation(self, **_kwargs: object) -> None:
                raise AssertionError("persist=False must not save no-OA mutation snapshots")

        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(snapshot=lambda: {}),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(
                SimpleNamespace(snapshot=lambda: {}, snapshot_case_ids=lambda _case_ids: {})
            ),
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {}),
            state_store=StateStore(),
            execute_derived_data_lifecycle_event=lambda event_type, **kwargs: lifecycle_events.append(
                {"event_type": event_type, **kwargs}
            ),
        )

        changed = service.after_mutation(["2026-05"], changed_case_ids=["case-001"], persist=False)

        self.assertTrue(changed)
        self.assertEqual(lifecycle_events[0]["event_type"], "no_oa_bank_batch_changed")
        self.assertEqual(lifecycle_events[0]["months"], ["2026-05"])

    def test_enqueue_background_refresh_uses_durable_queue_boundary(self) -> None:
        class QueueRepository:
            def __init__(self) -> None:
                self.enqueued: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.enqueued.append(dict(kwargs))

        queue = QueueRepository()
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(SimpleNamespace()),
            workbench_read_model_service=SimpleNamespace(),
            state_store=None,
            queue_repository=queue,
        )

        enqueued = service.enqueue_background_refresh(["all", "", "2026-05"], reason="unit_test")

        self.assertTrue(enqueued)
        self.assertEqual(
            queue.enqueued,
            [
                {"scope_type": "no_oa_bank_batch", "scope_key": "all", "reason": "unit_test"},
                {"scope_type": "no_oa_bank_batch", "scope_key": "2026-05", "reason": "unit_test"},
            ],
        )

    def test_enqueue_background_refresh_forwards_metadata_to_durable_queue_boundary(self) -> None:
        class QueueRepository:
            def __init__(self) -> None:
                self.enqueued: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.enqueued.append(dict(kwargs))

        queue = QueueRepository()
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(SimpleNamespace()),
            workbench_read_model_service=SimpleNamespace(),
            state_store=None,
            queue_repository=queue,
        )

        enqueued = service.enqueue_background_refresh(
            ["2026-05"],
            reason="unit_test",
            metadata={"action_name": "bank_flow_rule_batch_read_model_refresh"},
        )

        self.assertTrue(enqueued)
        self.assertEqual(
            queue.enqueued,
            [
                {
                    "scope_type": "no_oa_bank_batch",
                    "scope_key": "2026-05",
                    "reason": "unit_test",
                    "metadata": {"action_name": "bank_flow_rule_batch_read_model_refresh"},
                }
            ],
        )

    def test_enqueue_background_refresh_uses_injected_refresh_producer(self) -> None:
        class RefreshProducer:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def enqueue(self, scope_keys: list[str], *, reason: str) -> bool:
                self.calls.append({"scope_keys": list(scope_keys), "reason": reason})
                return True

        producer = RefreshProducer()
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(SimpleNamespace()),
            workbench_read_model_service=SimpleNamespace(),
            state_store=None,
            read_model_refresh_producer=producer,
        )

        enqueued = service.enqueue_background_refresh(["bad", "2026-05"], reason="unit_test")

        self.assertTrue(enqueued)
        self.assertEqual(producer.calls, [{"scope_keys": ["bad", "2026-05"], "reason": "unit_test"}])


if __name__ == "__main__":
    unittest.main()
