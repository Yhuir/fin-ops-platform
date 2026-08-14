from __future__ import annotations

from http import HTTPStatus
from types import SimpleNamespace
import unittest
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
    PostgresWorkbenchIdempotencyRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_selection import (
    PostgresWorkbenchPageSelectionRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation import (
    PostgresWorkbenchRelationRepository,
)
from fin_ops_platform.services.workbench_exception_application_service import (
    WorkbenchExceptionApplicationService,
)
from fin_ops_platform.services.workbench_exception_case_service import (
    WorkbenchExceptionCaseService,
)
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandService,
)
from fin_ops_platform.services.workbench_uow import WorkbenchWriteUnitOfWork
from fin_ops_platform.services.workbench_write_facade import (
    WorkbenchWriteFacade,
    WorkbenchWriteRelationReadSnapshotPort,
    WorkbenchWriteRelationSpecialMetadataMutationPort,
)
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


_ROWS: list[dict[str, object]] = [
    {
        "id": "oa-exception-atomic-1",
        "type": "oa",
        "month": "2026-05",
        "apply_type": "付款申请",
        "amount": "100.00",
        "counterparty_name": "原子事务供应商",
    },
    {
        "id": "bank-exception-atomic-1",
        "type": "bank",
        "month": "2026-05",
        "pay_receive_time": "2026-05-11 09:00:00",
        "debit_amount": "100.00",
        "credit_amount": "",
        "summary": "支付原子事务供应商",
        "counterparty_name": "原子事务供应商",
    },
    {
        "id": "invoice-exception-atomic-1",
        "type": "invoice",
        "month": "2026-05",
        "issue_date": "2026-05-10",
        "total_with_tax": "100.00",
        "invoice_type": "进项发票",
        "seller_name": "原子事务供应商",
    },
]

_REQUEST: dict[str, object] = {
    "month": "2026-05",
    "row_ids": [str(row["id"]) for row in _ROWS],
    "row_types": [str(row["type"]) for row in _ROWS],
    "scenario_code": "expense_all_equal",
    "action_code": "confirm_closed",
    "payload": {},
}


class _FailAfterRelationRepository:
    def __init__(self, delegate: Any, *, enabled: bool) -> None:
        self._delegate = delegate
        self._enabled = enabled

    def save_workbench_pair_relation_delta(self, *args: object, **kwargs: object) -> None:
        self._delegate.save_workbench_pair_relation_delta(*args, **kwargs)
        if self._enabled:
            raise RuntimeError("injected relation persistence failure")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class _FailAfterWorkbenchRepository:
    def __init__(self, delegate: Any, *, failure_stage: str | None) -> None:
        self._delegate = delegate
        self._failure_stage = failure_stage

    def save_workbench_exception_cases(self, *args: object, **kwargs: object) -> None:
        self._delegate.save_workbench_exception_cases(*args, **kwargs)
        if self._failure_stage == "case":
            raise RuntimeError("injected case persistence failure")

    def save_workbench_overrides(self, *args: object, **kwargs: object) -> None:
        self._delegate.save_workbench_overrides(*args, **kwargs)
        if self._failure_stage == "override":
            raise RuntimeError("injected override persistence failure")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class _FailAfterIdempotencyCommit:
    def __init__(self, delegate: PostgresWorkbenchIdempotencyRepository, *, enabled: bool) -> None:
        self._delegate = delegate
        self._enabled = enabled

    def for_transaction(self, transaction: Any) -> "_FailAfterIdempotencyCommit":
        return _FailAfterIdempotencyCommit(
            PostgresWorkbenchIdempotencyRepository(transaction),
            enabled=self._enabled,
        )

    def commit(self, **kwargs: object) -> object:
        result = self._delegate.commit(**kwargs)
        if self._enabled:
            raise RuntimeError("injected idempotency commit failure")
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class WorkbenchExceptionAtomicPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self._insert_canonical_rows()

    def tearDown(self) -> None:
        self.connection.close()
        truncate_test_database(self.database_url)

    def _insert_canonical_rows(self) -> None:
        self.connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            ) values (
                'oa-source-exception-atomic', 'payment_request', '付款申请',
                'oa-exception-atomic-1', 'active', 'completed', '测试用户',
                '2026-05-10', '2026-05-01', '原子事务项目', 100, 'CNY',
                '{"id":"oa-exception-atomic-1","month":"2026-05","amount":"100.00"}'::jsonb,
                '{}'::jsonb
            )
            """
        )
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values (
                'bank-exception-atomic-1', '6222000011119999', '基本户', 'outflow',
                '原子事务供应商', 100, -100, '2026-05-11', '2026-05-01',
                '2026-05-11 09:00:00+08', '支付原子事务供应商', '{}'::jsonb, 'active'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, workbench_visibility,
                source_links, raw_payload
            ) values (
                'invoice-exception-atomic-1', 'input', 'INV-EXCEPTION-ATOMIC-1',
                '2026-05-10', '2026-05-01', 100, 100, 100, 'active', 'visible',
                '[]'::jsonb, '{}'::jsonb
            )
            """
        )

    @staticmethod
    def _rows_provider(
        _month: str,
        row_ids: list[str],
        row_types: list[str],
    ) -> list[dict[str, object]]:
        by_identity = {
            (str(row["type"]), str(row["id"])): row
            for row in _ROWS
        }
        return [
            dict(by_identity[(row_type, row_id)])
            for row_type, row_id in zip(row_types, row_ids, strict=True)
        ]

    def _facade(
        self,
        *,
        failure_stage: str | None = None,
    ) -> WorkbenchWriteFacade:
        case_service = WorkbenchExceptionCaseService()
        override_service = WorkbenchOverrideService()
        pair_service = WorkbenchPairRelationService()

        def relation_command(repository: Any | None = None) -> WorkbenchRelationCommandService:
            return WorkbenchRelationCommandService(
                relation_repository=WorkbenchRelationCommandRepositoryAdapter(
                    pair_relation_service=pair_service,
                    repository=repository,
                ),
            )

        exception_service = WorkbenchExceptionApplicationService(
            row_provider=self._rows_provider,
            case_service=case_service,
            relation_command_service=relation_command(),
            source_versions_provider=lambda: {
                "workbench_exception_rules_version": "exception_rules_v1"
            },
        )

        def repository_factory(transaction: Any) -> SimpleNamespace:
            workbench_repository = _FailAfterWorkbenchRepository(
                PostgresWorkbenchRepository(transaction),
                failure_stage=failure_stage,
            )
            return SimpleNamespace(
                pair_relations=_FailAfterRelationRepository(
                    PostgresWorkbenchRelationRepository(transaction),
                    enabled=failure_stage == "relation",
                ),
                exception_cases=workbench_repository,
                row_overrides=workbench_repository,
                canonical_query=PostgresWorkbenchPageSelectionRepository(
                    transaction,
                    tenant_id="default",
                ),
            )

        idempotency_store = _FailAfterIdempotencyCommit(
            PostgresWorkbenchIdempotencyRepository(self.connection),
            enabled=failure_stage == "idempotency",
        )
        uow = WorkbenchWriteUnitOfWork(
            connection=self.connection,
            repository_factory=repository_factory,
            idempotency_store=idempotency_store,
        )
        facade = WorkbenchWriteFacade(
            relation_read_snapshot_port=WorkbenchWriteRelationReadSnapshotPort(pair_service),
            relation_special_metadata_mutation_port=WorkbenchWriteRelationSpecialMetadataMutationPort(pair_service),
            exception_service=exception_service,
            exception_case_service=case_service,
            override_service=override_service,
            next_case_id=lambda: "CASE-UNUSED",
            normalize_row_ids=lambda values: [str(value) for value in values],
            relation_preview_selection=lambda *_args, **_kwargs: None,
            expand_confirm_link_row_ids_for_existing_context=lambda **_kwargs: [],
            resolve_rows_for_amount_check=lambda row_ids, *, row_types, month: self._rows_provider(
                month,
                list(row_ids),
                list(row_types),
            ),
            merge_relation_snapshots=lambda *values: [item for value in values for item in value],
            synthetic_existing_case_relations=lambda *_args, **_kwargs: [],
            month_scope_for_selected_row_ids=lambda **kwargs: str(kwargs.get("month") or "all"),
            scope_keys_for_row_ids=lambda **kwargs: {str(kwargs.get("month") or "all")},
            scope_keys_for_rows=lambda **kwargs: [str(kwargs.get("month") or "all")],
            resolve_live_rows_direct=lambda row_ids, **_kwargs: self._rows_provider(
                "2026-05",
                list(row_ids),
                [
                    str(next(row["type"] for row in _ROWS if row["id"] == row_id))
                    for row_id in row_ids
                ],
            ),
            relation_groups=lambda *_args, **_kwargs: [],
            withdraw_rows_and_after_relations=lambda **_kwargs: ([], [], []),
            amount_check_for_rows_by_type=lambda _rows: {},
            transaction_amount_for_row_id=lambda _row_id: 0,
            list_ignored_rows=lambda _month: [],
            save_exception_cases_snapshot=lambda: None,
            persist_pair_relations=lambda **_kwargs: None,
            save_overrides_snapshot=lambda **_kwargs: None,
            restore_exception_write_snapshots=lambda **_kwargs: None,
            restore_exception_override_snapshots=lambda **_kwargs: None,
            restore_exception_pair_snapshots=lambda **_kwargs: None,
            schedule_pair_relation_persist=lambda **_kwargs: None,
            restore_pair_relation_snapshot=lambda *_args, **_kwargs: None,
            emit_action_timing=lambda **_kwargs: None,
            confirm_link_uow=uow,
            relation_command_service=relation_command(),
            relation_command_service_factory=lambda repository=None: relation_command(repository),
        )
        if failure_stage == "response":
            facade._finalize_exception_apply_transaction_result = (  # type: ignore[method-assign]
                lambda _result: (_ for _ in ()).throw(
                    RuntimeError("injected response construction failure")
                )
            )
        return facade

    def _persistent_counts(self) -> dict[str, int]:
        row = self.connection.fetch_one(
            """
            select
                (select count(*) from app.workbench_pair_relations) as relations,
                (select count(*) from app.workbench_pair_relation_history) as history,
                (select count(*) from app.workbench_exception_cases) as cases,
                (select count(*) from app.workbench_row_overrides) as overrides,
                (select count(*) from app.workbench_idempotency_records) as idempotency
            """
        ) or {}
        return {key: int(row.get(key) or 0) for key in (
            "relations", "history", "cases", "overrides", "idempotency"
        )}

    def test_each_persistence_or_response_failure_rolls_back_the_complete_postgres_write(self) -> None:
        for failure_stage in ("relation", "case", "override", "idempotency", "response"):
            with self.subTest(failure_stage=failure_stage):
                truncate_test_database(self.database_url)
                self._insert_canonical_rows()
                result = self._facade(failure_stage=failure_stage).apply_exception(
                    dict(_REQUEST),
                    actor="finance-atomic-test",
                )

                self.assertEqual(result.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
                self.assertEqual(
                    self._persistent_counts(),
                    {
                        "relations": 0,
                        "history": 0,
                        "cases": 0,
                        "overrides": 0,
                        "idempotency": 0,
                    },
                )

    def test_success_commits_once_and_durable_idempotency_replays_without_duplicate_rows(self) -> None:
        facade = self._facade()

        first = facade.apply_exception(dict(_REQUEST), actor="finance-atomic-test")
        second = facade.apply_exception(dict(_REQUEST), actor="finance-atomic-test")

        self.assertEqual(first.status_code, HTTPStatus.OK, first.payload)
        self.assertEqual(second.status_code, HTTPStatus.OK, second.payload)
        self.assertFalse(first.payload["idempotent"])
        self.assertTrue(second.payload["idempotent"])
        self.assertEqual(first.payload["case"]["id"], second.payload["case"]["id"])
        self.assertEqual(
            self._persistent_counts(),
            {
                "relations": 1,
                "history": 1,
                "cases": 1,
                "overrides": 3,
                "idempotency": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
