from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.bank_batch_application_service import (
    BankBatchPairRelationSnapshotPort,
)
from fin_ops_platform.services.bank_batch_service import (
    BANK_FLOW_RULE_BATCH_ID_PREFIX,
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
    BankBatchService,
)
from fin_ops_platform.services.bank_flow_rule_batch_application_service import (
    BankFlowRuleBatchApplicationService,
)
from fin_ops_platform.services.bank_transaction_category_mutation_writer import (
    BankTransactionCategoryMutationWriter,
)
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.bank_transaction_category import (
    PostgresBankTransactionCategoryRepository,
)
from fin_ops_platform.services.postgres_repositories.bank_flow_rule_batch_canonical_query import (
    BankFlowRuleBatchCanonicalQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_relation import (
    PostgresOaPendingPaymentRelationRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    PostgresOAProjectionRepository,
)
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import (
    PostgresOpsTaxEtcRepository,
)
from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresReadModelRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench import (
    PostgresWorkbenchRepository,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.read_model_freshness import (
    read_model_freshness_token,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryFacade
from fin_ops_platform.services.workbench_query_freshness_service import (
    WorkbenchQueryFreshnessService,
)
from fin_ops_platform.services.workbench_read_model_refresh import (
    WorkbenchReadModelRefreshService,
)
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


@dataclass(frozen=True)
class WriterProofContract:
    mutation_family: str
    production_owner: str
    proof_keys: tuple[str, ...]
    scope_contract: str


WORKBENCH_MUTABLE_WRITER_PROOF_CONTRACTS = (
    WriterProofContract(
        "relation and cross-month member",
        "PostgresWorkbenchRelationRepository.save_workbench_pair_relations",
        ("workbench_pair_relations_updated_at", "bank_transactions_updated_at", "invoices_updated_at"),
        "relation month plus every active member month",
    ),
    WriterProofContract(
        "bank transaction import",
        "PostgresCoreRepository.save_imports",
        ("bank_transactions_updated_at",),
        "transaction month",
    ),
    WriterProofContract(
        "bank category assignment",
        "BankTransactionCategoryMutationWriter.persist",
        ("bank_transaction_categories_updated_at",),
        "transaction month",
    ),
    WriterProofContract(
        "bank category confirmation",
        "BankTransactionCategoryMutationWriter.persist",
        ("bank_transaction_category_confirmations_updated_at",),
        "transaction month",
    ),
    WriterProofContract(
        "invoice import",
        "PostgresCoreRepository.save_invoices",
        ("invoices_updated_at",),
        "invoice month",
    ),
    WriterProofContract(
        "OA projection sync",
        "PostgresOAProjectionRepository.upsert_application_records",
        ("oa_projection_updated_at",),
        "application month",
    ),
    WriterProofContract(
        "amount mismatch exception decision",
        "PostgresWorkbenchRepository.set_workbench_amount_mismatch_decision",
        ("workbench_exception_cases_updated_at",),
        "exception month",
    ),
    WriterProofContract(
        "Workbench row override",
        "PostgresWorkbenchRepository.save_workbench_overrides",
        ("workbench_row_overrides_updated_at",),
        "override month and active member month",
    ),
    WriterProofContract(
        "OA pending-payment bank claim",
        "PostgresOaPendingPaymentRelationRepository.create_active_relation",
        ("oa_pending_payment_bank_claims_updated_at",),
        "claim month",
    ),
    WriterProofContract(
        "ETC submission, business, and invoice state",
        "PostgresOpsTaxEtcRepository.save_etc_state",
        (
            "etc_submission_batches_updated_at",
            "etc_business_batches_updated_at",
            "etc_invoices_updated_at",
        ),
        "ETC fact month",
    ),
    WriterProofContract(
        "ETC batch invoice link",
        "PostgresCoreRepository.upsert_etc_batch_invoice_link",
        ("etc_batch_invoice_links_updated_at",),
        "business batch month and canonical invoice month",
    ),
    WriterProofContract(
        "bank tag rules and account mappings settings",
        "PostgresOpsTaxEtcRepository.save_settings",
        ("bank_auto_tag_rules_version", "bank_account_mappings_fingerprint"),
        "global release/settings proof; all month shards",
    ),
)

WORKBENCH_IMMUTABLE_SOURCE_PROOF_KEYS = {
    "builder",
    "workbench_formal_relation_rule_version",
    "oa_attachment_invoice_parser_version",
    "oa_projection_sync_version",
}


class WorkbenchSourceProofContractTests(unittest.TestCase):
    MAY = "2026-05"
    JUNE = "2026-06"
    JULY = "2026-07"

    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self.core = PostgresCoreRepository(self.connection)
        self.workbench = PostgresWorkbenchRepository(self.connection)
        self.etc = PostgresOpsTaxEtcRepository(self.connection)
        self.builder = WorkbenchSqlProjectionBuilder(
            connection=self.connection,
            read_model_repository=PostgresReadModelRepository(self.connection),
        )

    def tearDown(self) -> None:
        self.connection.close()
        truncate_test_database(self.database_url)

    def _proof(self) -> dict[str, dict[str, object]]:
        return self.builder.source_versions_for_scopes([self.MAY, self.JUNE, self.JULY])

    def _assert_scoped_change(
        self,
        before: dict[str, dict[str, object]],
        after: dict[str, dict[str, object]],
        *,
        keys: tuple[str, ...],
        affected: tuple[str, ...],
        unrelated: tuple[str, ...],
    ) -> None:
        for scope_key in affected:
            for proof_key in keys:
                self.assertNotEqual(
                    before[scope_key][proof_key],
                    after[scope_key][proof_key],
                    f"{proof_key} did not advance for affected scope {scope_key}",
                )
        for scope_key in unrelated:
            self.assertEqual(
                before[scope_key],
                after[scope_key],
                f"unrelated scope {scope_key} changed for {keys}",
            )

    @staticmethod
    def _bank(transaction_id: str, month: str, *, amount: str = "100.00") -> BankTransaction:
        return BankTransaction(
            id=transaction_id,
            account_no="62220000",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="测试供应商",
            amount=Decimal(amount),
            signed_amount=-Decimal(amount),
            txn_date=f"{month}-02",
            source_batch_id="source-proof",
        )

    @staticmethod
    def _invoice(invoice_id: str, month: str) -> Invoice:
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.INPUT,
            invoice_no=f"INV-{invoice_id}",
            counterparty=Counterparty(
                id=f"counterparty-{invoice_id}",
                name="测试供应商",
                normalized_name="测试供应商",
                counterparty_type="vendor",
            ),
            amount=Decimal("100.00"),
            signed_amount=Decimal("100.00"),
            invoice_date=f"{month}-03",
            source_batch_id="source-proof",
        )

    @staticmethod
    def _oa(row_id: str, month: str) -> OAApplicationRecord:
        return OAApplicationRecord(
            id=row_id,
            month=month,
            section="unpaired",
            case_id=None,
            applicant="集成测试",
            project_name="来源证明",
            apply_type="支付申请",
            amount="100.00",
            counterparty_name="测试供应商",
            reason="来源证明",
            relation_code="pending_match",
            relation_label="待匹配",
            relation_tone="warn",
            workflow_status="completed",
            detail_fields={"申请日期": f"{month}-04"},
        )

    def test_projection_proof_keys_are_bidirectionally_owned_by_writer_matrix(self) -> None:
        proof_keys = set(self._proof()[self.MAY])
        mutable_keys = {
            key
            for contract in WORKBENCH_MUTABLE_WRITER_PROOF_CONTRACTS
            for key in contract.proof_keys
        }

        self.assertEqual(proof_keys, mutable_keys | WORKBENCH_IMMUTABLE_SOURCE_PROOF_KEYS)
        self.assertEqual(
            len(WORKBENCH_MUTABLE_WRITER_PROOF_CONTRACTS),
            len({contract.mutation_family for contract in WORKBENCH_MUTABLE_WRITER_PROOF_CONTRACTS}),
            "each canonical mutation family must have exactly one writer contract row",
        )

    def test_real_postgres_writers_advance_exact_source_proof_scopes(self) -> None:
        before = self._proof()
        self.core.save_imports({"transactions": [self._bank("bank-may", self.MAY)]})
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("bank_transactions_updated_at",),
            affected=(self.MAY,),
            unrelated=(self.JUNE, self.JULY),
        )

        before = after
        category_writer = BankTransactionCategoryMutationWriter(
            connection=self.connection,
            repository=PostgresBankTransactionCategoryRepository(self.connection),
        )
        category_writer.persist(
            transaction_id="bank-may",
            mutation_type="manual_assign",
            record={"category_code": "fee", "manual_assignment": True},
            actor_id="source-proof",
            action="source_proof_manual_assign",
            metadata={"test": True},
        )
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("bank_transaction_categories_updated_at",),
            affected=(self.MAY,),
            unrelated=(self.JUNE, self.JULY),
        )

        self.core.save_imports({"transactions": [self._bank("bank-confirm", self.MAY, amount="101.00")]})
        before = self._proof()
        category_writer.persist(
            transaction_id="bank-confirm",
            mutation_type="confirmation_confirm",
            record={
                "category_code": "fee",
                "candidate_category_codes": ["fee"],
                "rule_version": "source-proof-v1",
            },
            actor_id="source-proof",
            action="source_proof_confirmation",
            metadata={"test": True},
        )
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("bank_transaction_category_confirmations_updated_at",),
            affected=(self.MAY,),
            unrelated=(self.JUNE, self.JULY),
        )

        before = after
        self.core.save_invoices([self._invoice("invoice-june", self.JUNE)])
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("invoices_updated_at",),
            affected=(self.JUNE,),
            unrelated=(self.MAY, self.JULY),
        )

        before = after
        PostgresOAProjectionRepository(self.connection).upsert_application_records(
            [self._oa("oa-may", self.MAY)], scope_key=self.MAY
        )
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("oa_projection_updated_at",),
            affected=(self.MAY,),
            unrelated=(self.JUNE, self.JULY),
        )

        before = after
        self.workbench.save_workbench_pair_relations(
            {
                "pair_relations": {
                    "case-cross-month": {
                        "case_id": "case-cross-month",
                        "relation_mode": "manual_confirmed",
                        "status": "active",
                        "version": 1,
                        "month_scope": self.MAY,
                        "row_ids": ["bank-may", "invoice-june"],
                        "row_types": ["bank", "invoice"],
                    }
                }
            },
            changed_case_ids={"case-cross-month"},
        )
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("workbench_pair_relations_updated_at",),
            affected=(self.MAY, self.JUNE),
            unrelated=(self.JULY,),
        )
        self.assertNotEqual(before[self.MAY]["invoices_updated_at"], after[self.MAY]["invoices_updated_at"])
        self.assertNotEqual(before[self.JUNE]["bank_transactions_updated_at"], after[self.JUNE]["bank_transactions_updated_at"])

        before = after
        self.workbench.save_workbench_overrides(
            {
                "row_overrides": {
                    "override-may": {
                        "row_id": "override-may",
                        "row_type": "bank",
                        "scope_month": self.MAY,
                        "status": "active",
                    }
                }
            },
            changed_row_ids={"override-may"},
        )
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("workbench_row_overrides_updated_at",),
            affected=(self.MAY,),
            unrelated=(self.JUNE, self.JULY),
        )

        before = after
        self.workbench.set_workbench_amount_mismatch_decision(
            fingerprint="a" * 64,
            group_id="group-may",
            scope_key=self.MAY,
            actor_id="source-proof",
            ignored=True,
        )
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("workbench_exception_cases_updated_at",),
            affected=(self.MAY,),
            unrelated=(self.JUNE, self.JULY),
        )

        before = after
        PostgresOaPendingPaymentRelationRepository(self.connection).create_active_relation(
            oa_row_ids=["oa-claim-may"],
            bank_transaction_ids=["bank-confirm"],
            actor_id="source-proof",
            month_scope=self.MAY,
            relation_id="claim-may",
        )
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("oa_pending_payment_bank_claims_updated_at",),
            affected=(self.MAY,),
            unrelated=(self.JUNE, self.JULY),
        )

        before = after
        self.etc.save_etc_state(
            {
                "invoices": {
                    "etc-invoice-may": {
                        "invoice_number": "ETC-SOURCE-PROOF",
                        "issue_date": f"{self.MAY}-05",
                        "total_amount": "100.00",
                    }
                },
                "batches": {
                    "etc-submission-may": {
                        "status": "submitted",
                        "issue_start_date": f"{self.MAY}-05",
                        "invoice_ids": ["etc-invoice-may"],
                    }
                },
                "business_batches": {
                    "etc-business-may": {
                        "status": "submitted",
                        "scope_month": self.MAY,
                        "invoice_ids": ["etc-invoice-may"],
                        "submission_batch_id": "etc-submission-may",
                    }
                },
            }
        )
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=(
                "etc_submission_batches_updated_at",
                "etc_business_batches_updated_at",
                "etc_invoices_updated_at",
            ),
            affected=(self.MAY,),
            unrelated=(self.JUNE, self.JULY),
        )

        before = after
        self.core.upsert_etc_batch_invoice_link(
            invoice_id="invoice-june",
            business_batch_id="etc-business-may",
            etc_invoice_id="etc-invoice-may",
            invoice_no="ETC-SOURCE-PROOF",
            invoice_date=f"{self.MAY}-05",
        )
        after = self._proof()
        self._assert_scoped_change(
            before,
            after,
            keys=("etc_batch_invoice_links_updated_at",),
            affected=(self.MAY, self.JUNE),
            unrelated=(self.JULY,),
        )

        before = after
        self.etc.save_settings(
            "app_settings",
            {
                "bank_transaction_tags": {"version": 7, "items": []},
                "bank_account_mappings": [
                    {"bank_name": "测试银行", "last4": "0000"}
                ],
            },
        )
        after = self._proof()
        for scope_key in (self.MAY, self.JUNE, self.JULY):
            self.assertNotEqual(
                before[scope_key]["bank_auto_tag_rules_version"],
                after[scope_key]["bank_auto_tag_rules_version"],
            )
            self.assertNotEqual(
                before[scope_key]["bank_account_mappings_fingerprint"],
                after[scope_key]["bank_account_mappings_fingerprint"],
            )

    def test_bank_flow_application_self_converges_through_status_gateway_and_worker(self) -> None:
        self.etc.save_settings(
            "app_settings",
            {
                "bank_transaction_tags": {
                    "version": 3,
                    "definitions": [
                        {
                            "code": "fee",
                            "label": "手续费",
                            "path": ["费用", "手续费"],
                            "source": "custom",
                            "status": "active",
                            "direction": "expense",
                            "rules": {"match_fields": ["summary_text"]},
                        }
                    ],
                },
                "bank_flow_rule_batch_tag_rules": {
                    "version": 7,
                    "requirements_by_tag_code": {
                        "fee": {"requires_oa": False, "requires_invoice": False}
                    },
                },
            },
        )
        self.core.save_imports(
            {"transactions": [self._bank("bank-flow-may", self.MAY, amount="88.00")]}
        )
        BankTransactionCategoryMutationWriter(
            connection=self.connection,
            repository=PostgresBankTransactionCategoryRepository(self.connection),
        ).persist(
            transaction_id="bank-flow-may",
            mutation_type="manual_assign",
            record={"category_code": "fee", "manual_assignment": True},
            actor_id="source-proof",
            action="source_proof_bank_flow_category",
            metadata={"test": True},
        )

        self.assertTrue(self.builder.rebuild_workbench_read_model_scope(self.MAY)["published"])
        self.assertTrue(self.builder.rebuild_workbench_read_model_scope(self.JULY)["published"])
        generation_before = self.connection.fetch_one(
            """
            select
              max(generation_id) filter (where scope_key = %s) as target_generation_id,
              max(generation_id) filter (where scope_key = %s) as unrelated_generation_id
            from read_model.workbench_generations
            where status = 'active'
            """,
            (self.MAY, self.JULY),
        )
        proof_before = self.builder.source_versions_for_scope(self.MAY)

        canonical_query = BankFlowRuleBatchCanonicalQueryRepository(self.connection)
        source = canonical_query.read_page(
            {"month": self.MAY, "bucket": "unsubmitted"},
            summary_filters={"month": self.MAY},
            page=1,
            page_size=None,
        )
        rows = [
            dict(row)
            for row in list(source.get("candidate_rows") or [])
            if isinstance(row, dict) and str(row.get("id") or "") == "bank-flow-may"
        ]
        self.assertEqual([row["id"] for row in rows], ["bank-flow-may"])
        categories = {
            "bank-flow-may": {
                "transaction_id": "bank-flow-may",
                "category_code": "fee",
                "category_source": "manual",
                "category_version": 1,
            }
        }

        pair_service = WorkbenchPairRelationService()
        pair_port = BankBatchPairRelationSnapshotPort(pair_service)
        with TemporaryDirectory() as temp_dir:
            state_store = PostgresStateStore(
                data_dir=Path(temp_dir),
                connection=self.connection,
            )
            batch_service = BankBatchService(
                schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
                batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
                relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            )
            application = object.__new__(BankFlowRuleBatchApplicationService)
            application._bank_batch_service = batch_service
            application._pair_relation_snapshot_port = pair_port
            application._state_store = state_store
            application._bank_transaction_category_affected_months_provider = (
                lambda _row_ids: [self.MAY]
            )
            application.bank_transaction_rows_by_ids = lambda _row_ids: rows
            application.effective_categories_for_rows = lambda _rows: categories
            application.active_relation_source_bundle_for_bank_rows = (
                lambda _rows, **_kwargs: {"rows": [], "source_versions": {}}
            )
            application.candidate_source_versions_for_scope = lambda **_kwargs: {}
            application._eligible_tag_codes_for_relation_mode = lambda _mode: {"fee"}
            application.resolve_labels = lambda batches, **_kwargs: batches

            def confirm_relation(
                batch: dict[str, object],
                *,
                actor: str,
                note: str | None,
                relation_mode: str,
            ) -> None:
                pair_service.create_active_relation(
                    case_id=str(batch["batch_id"]),
                    row_ids=[str(row_id) for row_id in list(batch["row_ids"])],
                    row_types=["bank"],
                    relation_mode=relation_mode,
                    created_by=actor,
                    month_scope=self.MAY,
                    note=note,
                )

            application._confirm_relation_for_batch = confirm_relation
            result = application.submit_selected_rows(
                row_ids=["bank-flow-may"],
                actor="source-proof",
                note="contract closure",
            )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(
            self.connection.fetch_one(
                """
                select
                  (select count(*)::integer from job.outbox_events) as event_count,
                  (select count(*)::integer from job.read_model_dirty_scopes) as dirty_count
                """
            ),
            {"event_count": 0, "dirty_count": 0},
            "the writer must not enqueue Workbench refresh work",
        )
        proof_after_write = self.builder.source_versions_for_scope(self.MAY)
        self.assertNotEqual(
            proof_before["workbench_pair_relations_updated_at"],
            proof_after_write["workbench_pair_relations_updated_at"],
        )

        read_repository = PostgresReadModelRepository(self.connection)
        queue_repository = RuntimeQueueRepository(self.connection)
        gateway = ReadModelRefreshGateway(queue_repository=queue_repository)

        def stale_reasons(actual: dict[str, object], *, scope_key: str) -> list[str]:
            return source_version_mismatch_reasons(
                expected=self.builder.source_versions_for_scope(scope_key),
                actual=actual,
            )

        freshness = WorkbenchQueryFreshnessService(
            projection_builder=self.builder,
            repository=read_repository,
            single_scope_stale_reasons=stale_reasons,
        )

        def enqueue_refresh(scope_key: str, *, reason: str) -> None:
            expected = self.builder.source_versions_for_scope(scope_key)
            gateway.enqueue_one(
                "workbench",
                scope_key,
                reason=reason,
                metadata={
                    "expected_source_versions": expected,
                    "freshness_token": read_model_freshness_token(
                        scope_type="workbench",
                        scope_key=scope_key,
                        expected_source_versions=expected,
                    ),
                },
            )

        facade = WorkbenchQueryFacade(
            repository=read_repository,
            redis_helper=None,
            enqueue_refresh=enqueue_refresh,
            scope_key_for_month=lambda month: str(month or "all"),
            stale_reasons=stale_reasons,
            emit_status_metric=lambda **_kwargs: None,
            missing_read_model_error=lambda _error: False,
            refresh_status_with_source_freshness=freshness.apply,
        )
        stale_status = facade.refresh_status(self.MAY).payload
        self.assertEqual(stale_status["read_model_status"], "stale")
        self.assertEqual(stale_status["refresh_scope_keys"], [self.MAY])
        active_queue = self.connection.fetch_one(
            """
            select
              count(*) filter (
                where event_type = 'workbench.read_model.refresh'
                  and scope_key = %s and status in ('pending', 'processing')
              )::integer as target_event_count,
              count(*) filter (
                where scope_key = %s and status in ('pending', 'processing')
              )::integer as unrelated_event_count
            from job.outbox_events
            """,
            (self.MAY, self.JULY),
        )
        self.assertEqual(active_queue, {"target_event_count": 1, "unrelated_event_count": 0})

        event = queue_repository.claim_next(
            "source-proof-worker",
            event_types=["workbench.read_model.refresh"],
            scope_keys=[self.MAY],
        )
        self.assertIsNotNone(event)
        worker_result = WorkbenchReadModelRefreshService(
            projection_builder=self.builder,
            queue_repository=queue_repository,
        ).handle_runtime_event(event)
        self.assertTrue(worker_result["published"])
        self.assertTrue(
            queue_repository.ack_event(
                event.event_id,
                "source-proof-worker",
                result_payload=worker_result,
            )
        )

        fresh_status = facade.refresh_status(self.MAY).payload
        self.assertEqual(fresh_status["read_model_status"], "fresh")
        generation_after = self.connection.fetch_one(
            """
            select
              max(generation_id) filter (where scope_key = %s) as target_generation_id,
              max(generation_id) filter (where scope_key = %s) as unrelated_generation_id
            from read_model.workbench_generations
            where status = 'active'
            """,
            (self.MAY, self.JULY),
        )
        self.assertNotEqual(
            generation_before["target_generation_id"],
            generation_after["target_generation_id"],
        )
        self.assertEqual(
            generation_before["unrelated_generation_id"],
            generation_after["unrelated_generation_id"],
        )
        visible_relation = self.connection.fetch_one(
            """
            select count(*)::integer as row_count
            from read_model.workbench_group_rows row
            join read_model.workbench_generations generation
              on generation.generation_id = row.generation_id
             and generation.status = 'active'
            where row.scope_key = %s and row.row_id = %s
            """,
            (self.MAY, "bank-flow-may"),
        )
        self.assertEqual(visible_relation, {"row_count": 1})
if __name__ == "__main__":
    unittest.main()
