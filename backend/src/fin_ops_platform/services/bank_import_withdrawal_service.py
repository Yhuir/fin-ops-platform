from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Callable

from fin_ops_platform.services.postgres_repositories.bank_import_withdrawal import (
    PostgresBankImportWithdrawalRepository,
)


class BankImportWithdrawalConflict(ValueError):
    def __init__(self, message: str, *, blockers: dict[str, int] | None = None) -> None:
        super().__init__(message)
        self.blockers = dict(blockers or {})


class BankImportWithdrawalService:
    def __init__(
        self,
        *,
        repository: PostgresBankImportWithdrawalRepository,
        relation_service_for_transaction: Callable[[Any], Any],
    ) -> None:
        self._repository = repository
        self._relation_service_for_transaction = relation_service_for_transaction

    def withdraw(
        self,
        *,
        batch_id: str,
        actor_id: str,
        reason: str = "撤回误导入的银行流水",
        request_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_batch_id = str(batch_id or "").strip()
        normalized_actor_id = str(actor_id or "").strip()
        normalized_reason = str(reason or "").strip()
        if not normalized_batch_id:
            raise ValueError("batch_id is required")
        if not normalized_actor_id:
            raise ValueError("actor_id is required")
        if not normalized_reason:
            raise ValueError("reason is required")
        if len(normalized_reason) > 500:
            raise ValueError("reason must be 500 characters or fewer")

        with self._repository.transaction() as repository:
            batch = repository.lock_batch(normalized_batch_id)
            if batch is None:
                raise KeyError(normalized_batch_id)
            if str(batch.get("batch_type") or "") != "bank_transaction":
                raise BankImportWithdrawalConflict("仅银行流水导入批次支持撤回。")
            if str(batch.get("status") or "") == "withdrawn":
                stored = repository.withdrawal_payload(batch) or {}
                return {
                    "status": "withdrawn",
                    "batch_id": normalized_batch_id,
                    "withdrawn_count": int(stored.get("withdrawn_count") or 0),
                    "idempotent_replay": True,
                    "withdrawal": stored,
                }
            if str(batch.get("status") or "") not in {"completed", "completed_with_errors"}:
                raise BankImportWithdrawalConflict("只有已完成的银行流水导入批次可以撤回。")
            if int(batch.get("updated_count") or 0) > 0:
                raise BankImportWithdrawalConflict("该批次更新过既有流水，缺少更新前快照，不能安全撤回。")

            transactions = repository.created_transactions(
                str(batch["batch_uuid"]),
                normalized_batch_id,
            )
            expected_count = int(batch.get("success_count") or 0)
            if len(transactions) != expected_count:
                raise BankImportWithdrawalConflict(
                    "导入成功数与本批次独占创建的流水数不一致，已停止撤回。",
                    blockers={"ownership_mismatch": abs(expected_count - len(transactions)) or 1},
                )
            if not transactions:
                raise BankImportWithdrawalConflict("该批次没有可证明由其独占创建的银行流水。")
            if any(Decimal(str(row.get("written_off_amount") or 0)) != Decimal("0") for row in transactions):
                raise BankImportWithdrawalConflict(
                    "该批次存在已核销流水，不能直接撤回。",
                    blockers={"written_off_transactions": 1},
                )

            transaction_uuids = [str(row["transaction_uuid"]) for row in transactions]
            row_ids = [str(row["row_id"]) for row in transactions]
            blockers = repository.blocking_references(
                row_ids=row_ids,
            ) if row_ids else {}
            active_blockers = {key: value for key, value in blockers.items() if value > 0}
            if active_blockers:
                raise BankImportWithdrawalConflict(
                    "该批次流水仍被其他已生效业务单据使用，请先解除这些业务关系。",
                    blockers=active_blockers,
                )

            relation_service = self._relation_service_for_transaction(repository.transaction_connection)
            relation_result = relation_service.remove_rows_from_active_relations(
                row_ids=row_ids,
                actor_id=normalized_actor_id,
                reason=normalized_reason,
                replace_history_operation_type="remove_withdrawn_bank_import_fact",
                cancel_history_operation_type="cancel_relation_for_withdrawn_bank_import_fact",
            ) if row_ids else {"changed_case_ids": [], "affected_months": []}
            cleanup_counts = repository.cleanup_removable_state(
                transaction_uuids=transaction_uuids,
                row_ids=row_ids,
            ) if row_ids else {}
            deleted_count = repository.delete_transactions(
                transaction_uuids=transaction_uuids,
                actor_id=normalized_actor_id,
                reason=normalized_reason,
            ) if transaction_uuids else 0
            if deleted_count != len(transaction_uuids):
                raise RuntimeError("bank import withdrawal deleted an unexpected number of rows")

            summary = {
                "batch_id": normalized_batch_id,
                "source_name": str(batch.get("source_name") or ""),
                "withdrawn_count": deleted_count,
                "relation_case_count": len(relation_result.get("changed_case_ids") or []),
                "cleanup_counts": cleanup_counts,
                "withdrawn_by": normalized_actor_id,
                "withdrawn_at": datetime.now(UTC).isoformat(),
                "reason": normalized_reason,
            }
            repository.mark_withdrawn(batch_uuid=str(batch["batch_uuid"]), summary=summary)
            repository.append_audit_event(
                batch_id=normalized_batch_id,
                actor_id=normalized_actor_id,
                reason=normalized_reason,
                request_id=request_id,
                summary=summary,
            )

            return {
                "status": "withdrawn",
                "batch_id": normalized_batch_id,
                "withdrawn_count": deleted_count,
                "idempotent_replay": False,
                "withdrawal": summary,
            }
