from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
from typing import Any

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


NO_OA_BANK_BATCH_SCHEMA_VERSION = "2026-05-no-oa-bank-batch-v1"
NO_OA_BANK_BATCH_RELATION_MODE = "no_oa_bank_batch"
INTERNAL_TRANSFER_MATCH_WINDOW = timedelta(hours=48)
CENT = Decimal("0.01")
ZERO = Decimal("0.00")

NO_OA_BANK_BATCH_LABELS = {
    "fee": "手续费",
    "salary": "工资",
    "holiday_bonus": "过节费",
    "bonus": "奖金",
    "internal_transfer": "内部往来款",
}
SINGLE_SIDE_BATCH_TYPES = {"fee", "salary", "holiday_bonus", "bonus"}
SUPPORTED_BATCH_TYPES = {*SINGLE_SIDE_BATCH_TYPES, "internal_transfer"}


class NoOaBankBatchService:
    def __init__(
        self,
        *,
        batches: dict[str, dict[str, Any]] | None = None,
        audit_log: list[dict[str, Any]] | None = None,
        pair_relation_service: WorkbenchPairRelationService | None = None,
    ) -> None:
        self._batches = {
            str(batch_id): self._normalize_batch(batch)
            for batch_id, batch in (batches or {}).items()
            if isinstance(batch, dict)
        }
        self._audit_log = [
            self._normalize_audit_entry(entry)
            for entry in list(audit_log or [])
            if isinstance(entry, dict)
        ]
        self._pair_relation_service = pair_relation_service or WorkbenchPairRelationService()

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any] | None,
        *,
        pair_relation_service: WorkbenchPairRelationService | None = None,
    ) -> "NoOaBankBatchService":
        if not isinstance(snapshot, dict):
            return cls(pair_relation_service=pair_relation_service)
        batches = snapshot.get("batches")
        audit_log = snapshot.get("audit_log")
        return cls(
            batches=batches if isinstance(batches, dict) else {},
            audit_log=audit_log if isinstance(audit_log, list) else [],
            pair_relation_service=pair_relation_service,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": NO_OA_BANK_BATCH_SCHEMA_VERSION,
            "batches": deepcopy(self._batches),
            "audit_log": deepcopy(self._audit_log),
        }

    def build_batches(
        self,
        bank_rows: list[dict[str, Any]],
        categories_by_transaction_id: dict[str, dict[str, Any]],
        active_relations: list[dict[str, Any]],
        source_versions: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        rows = [dict(row) for row in list(bank_rows or []) if isinstance(row, dict)]
        categories = categories_by_transaction_id if isinstance(categories_by_transaction_id, dict) else {}
        occupied_row_ids = self._active_relation_row_ids(active_relations)
        source_version_payload = dict(source_versions or {})

        generated: dict[str, dict[str, Any]] = {}
        generated.update(self._build_single_side_batches(rows, categories, occupied_row_ids, source_version_payload))
        generated.update(self._build_internal_transfer_batches(rows, categories, occupied_row_ids, source_version_payload))

        submitted_or_withdrawn = {
            batch_id: deepcopy(batch)
            for batch_id, batch in self._batches.items()
            if batch.get("status") in {"submitted", "withdrawn", "stale"}
        }
        for batch_id, batch in submitted_or_withdrawn.items():
            if batch.get("status") == "withdrawn" and batch_id in generated:
                continue
            if batch.get("status") == "submitted" and not self._submitted_batch_still_current(batch, rows, categories):
                stale = deepcopy(batch)
                stale["status"] = "stale"
                stale["version"] = int(stale.get("version") or 1) + 1
                stale["updated_at"] = self._timestamp()
                generated[batch_id] = stale
            else:
                generated[batch_id] = batch

        self._batches = {batch_id: self._normalize_batch(batch) for batch_id, batch in generated.items()}
        return self.list_batches()

    def list_batches(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        resolved_filters = filters if isinstance(filters, dict) else {}
        batches = list(self._batches.values())
        for field_name, filter_key in (
            ("scope_month", "month"),
            ("batch_type", "type"),
            ("status", "status"),
            ("account_key", "account_key"),
        ):
            value = str(resolved_filters.get(filter_key) or "").strip()
            if value:
                batches = [batch for batch in batches if str(batch.get(field_name) or "") == value]
        return [
            deepcopy(batch)
            for batch in sorted(
                batches,
                key=lambda item: (
                    str(item.get("scope_month") or ""),
                    str(item.get("batch_type") or ""),
                    str(item.get("account_key") or ""),
                    str(item.get("batch_id") or ""),
                ),
            )
        ]

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        resolved_batch_id = str(batch_id or "").strip()
        if not resolved_batch_id or resolved_batch_id not in self._batches:
            raise KeyError("no_oa_bank_batch_not_found")
        return deepcopy(self._batches[resolved_batch_id])

    def submit_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        note: str | None = None,
    ) -> dict[str, Any]:
        batch = self.get_batch(batch_id)
        if batch.get("status") == "submitted":
            return batch
        if batch.get("status") != "draft":
            raise ValueError("only_draft_no_oa_bank_batch_can_be_submitted")
        self._check_expected_version(batch, expected_version)

        timestamp = self._timestamp()
        relation_case_id = str(batch.get("relation_case_id") or batch["batch_id"])
        row_ids = [str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id)]
        relation = self._pair_relation_service.get_active_relation_by_case_id(relation_case_id)
        if relation is None:
            relation = self._pair_relation_service.create_active_relation(
                case_id=relation_case_id,
                row_ids=row_ids,
                row_types=["bank" for _ in row_ids],
                relation_mode=NO_OA_BANK_BATCH_RELATION_MODE,
                created_by=str(actor or ""),
                month_scope=str(batch.get("scope_month") or ""),
                created_at=timestamp,
                note=str(note or "") or f"免OA流水批量处理：{batch.get('batch_label')}",
                special_metadata={
                    "source": "no_oa_bank_batch",
                    "source_batch_id": batch["batch_id"],
                    "batch_type": batch["batch_type"],
                    "batch_label": batch["batch_label"],
                    "cost_policy": "exclude_all" if batch["batch_type"] == "internal_transfer" else "normal",
                    "withdrawable": True,
                    "relation_mode": NO_OA_BANK_BATCH_RELATION_MODE,
                    "display_tags": self._display_tags(str(batch["batch_type"])),
                },
                evidence={
                    "batch_key": batch.get("batch_key"),
                    "category_source": batch.get("category_source"),
                    "row_count": batch.get("row_count"),
                    "total_amount": batch.get("total_amount"),
                    **(deepcopy(batch.get("evidence")) if isinstance(batch.get("evidence"), dict) else {}),
                },
                display_tags=self._display_tags(str(batch["batch_type"])),
            )

        submitted = deepcopy(batch)
        submitted.update(
            {
                "status": "submitted",
                "relation_case_id": relation_case_id,
                "submitted_by": str(actor or ""),
                "submitted_at": timestamp,
                "updated_at": timestamp,
                "version": int(batch.get("version") or 1) + 1,
            }
        )
        self._batches[str(submitted["batch_id"])] = self._normalize_batch(submitted)
        self._append_audit(
            operation="submit",
            batch_id=str(submitted["batch_id"]),
            actor=actor,
            note=note,
            status="submitted",
            relation_case_id=str(relation.get("case_id") or relation_case_id),
        )
        return self.get_batch(str(submitted["batch_id"]))

    def withdraw_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        batch = self.get_batch(batch_id)
        if batch.get("status") == "withdrawn":
            return batch
        if batch.get("status") != "submitted":
            raise ValueError("only_submitted_no_oa_bank_batch_can_be_withdrawn")
        self._check_expected_version(batch, expected_version)

        timestamp = self._timestamp()
        relation_case_id = str(batch.get("relation_case_id") or batch["batch_id"])
        self._pair_relation_service.cancel_relation(relation_case_id, cancelled_at=timestamp)
        withdrawn = deepcopy(batch)
        withdrawn.update(
            {
                "status": "withdrawn",
                "withdrawn_by": str(actor or ""),
                "withdrawn_at": timestamp,
                "withdraw_reason": str(reason or ""),
                "updated_at": timestamp,
                "version": int(batch.get("version") or 1) + 1,
            }
        )
        self._batches[str(withdrawn["batch_id"])] = self._normalize_batch(withdrawn)
        self._append_audit(
            operation="withdraw",
            batch_id=str(withdrawn["batch_id"]),
            actor=actor,
            note=reason,
            status="withdrawn",
            relation_case_id=relation_case_id,
        )
        return self.get_batch(str(withdrawn["batch_id"]))

    def audit_log(self) -> list[dict[str, Any]]:
        return deepcopy(self._audit_log)

    def _build_single_side_batches(
        self,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        occupied_row_ids: set[str],
        source_versions: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            row_id = self._row_id(row)
            if not row_id or row_id in occupied_row_ids:
                continue
            batch_type = self._category_code(row, categories)
            if batch_type not in SINGLE_SIDE_BATCH_TYPES:
                continue
            scope_month = self._scope_month(row)
            account_key = self._account_key(row)
            if not scope_month or not account_key:
                continue
            grouped.setdefault((batch_type, scope_month, account_key), []).append(row)

        batches: dict[str, dict[str, Any]] = {}
        for (batch_type, scope_month, account_key), group_rows in grouped.items():
            sorted_rows = sorted(group_rows, key=self._row_id)
            batch_key = f"single:{batch_type}:{scope_month}:{account_key}"
            row_ids = [self._row_id(row) for row in sorted_rows]
            batches[self._batch_id(batch_key)] = self._draft_batch(
                batch_key=batch_key,
                batch_type=batch_type,
                scope_month=scope_month,
                account_key=account_key,
                rows=sorted_rows,
                row_ids=row_ids,
                total_amount=sum((self._amount(row) or ZERO for row in sorted_rows), ZERO),
                source_versions=source_versions,
                evidence={
                    "matched_fields": ["category_code", "account_key", "scope_month"],
                    "category_sources": self._category_sources(row_ids, categories),
                },
            )
        return batches

    def _build_internal_transfer_batches(
        self,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        occupied_row_ids: set[str],
        source_versions: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        internal_rows = [
            row for row in rows if self._row_id(row) and self._category_code(row, categories) == "internal_transfer"
        ]
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in internal_rows:
            amount = self._amount(row)
            month = self._scope_month(row)
            if amount is None or not month:
                continue
            grouped.setdefault((month, self._format_amount(amount)), []).append(row)

        batches: dict[str, dict[str, Any]] = {}
        for (scope_month, amount_text), group_rows in grouped.items():
            sorted_rows = sorted(group_rows, key=self._row_id)
            row_ids = [self._row_id(row) for row in sorted_rows]
            batch_key = f"internal_transfer:{scope_month}:{amount_text}:{':'.join(row_ids)}"
            occupied = sorted(row_id for row_id in row_ids if row_id in occupied_row_ids)
            if occupied:
                batches[self._batch_id(batch_key)] = self._conflict_batch(
                    batch_key=batch_key,
                    scope_month=scope_month,
                    rows=sorted_rows,
                    row_ids=row_ids,
                    total_amount=Decimal(amount_text),
                    source_versions=source_versions,
                    conflict_code="row_occupied_by_active_relation",
                    conflict_reason="内部往来流水已被 active relation 占用。",
                    evidence={"occupied_row_ids": occupied},
                )
                continue

            inflows = [row for row in sorted_rows if self._direction(row) == "inflow"]
            outflows = [row for row in sorted_rows if self._direction(row) == "outflow"]
            if not inflows or not outflows:
                batches[self._batch_id(batch_key)] = self._conflict_batch(
                    batch_key=batch_key,
                    scope_month=scope_month,
                    rows=sorted_rows,
                    row_ids=row_ids,
                    total_amount=Decimal(amount_text),
                    source_versions=source_versions,
                    conflict_code="missing_internal_transfer_counterpart",
                    conflict_reason="内部往来收入或支出单边缺失。",
                    evidence={"income_row_ids": [self._row_id(row) for row in inflows], "expense_row_ids": [self._row_id(row) for row in outflows]},
                )
                continue

            if len(inflows) != 1 or len(outflows) != 1:
                batches[self._batch_id(batch_key)] = self._conflict_batch(
                    batch_key=batch_key,
                    scope_month=scope_month,
                    rows=sorted_rows,
                    row_ids=row_ids,
                    total_amount=Decimal(amount_text),
                    source_versions=source_versions,
                    conflict_code="multiple_internal_transfer_matches",
                    conflict_reason="内部往来存在多解，不能自动形成可提交批次。",
                    evidence={"income_count": len(inflows), "expense_count": len(outflows)},
                )
                continue

            outflow = outflows[0]
            inflow = inflows[0]
            if self._account_key(outflow) == self._account_key(inflow):
                batches[self._batch_id(batch_key)] = self._conflict_batch(
                    batch_key=batch_key,
                    scope_month=scope_month,
                    rows=sorted_rows,
                    row_ids=row_ids,
                    total_amount=Decimal(amount_text),
                    source_versions=source_versions,
                    conflict_code="same_account_internal_transfer",
                    conflict_reason="内部往来收入和支出不能来自同一账户。",
                    evidence={},
                )
                continue

            outflow_time = self._row_time(outflow)
            inflow_time = self._row_time(inflow)
            if outflow_time is None or inflow_time is None or abs(inflow_time - outflow_time) > INTERNAL_TRANSFER_MATCH_WINDOW:
                batches[self._batch_id(batch_key)] = self._conflict_batch(
                    batch_key=batch_key,
                    scope_month=scope_month,
                    rows=sorted_rows,
                    row_ids=row_ids,
                    total_amount=Decimal(amount_text),
                    source_versions=source_versions,
                    conflict_code="internal_transfer_time_window_exceeded",
                    conflict_reason="内部往来收入和支出不在匹配时间窗口内。",
                    evidence={"match_window_hours": 48},
                )
                continue

            evidence = {
                "rule_code": "internal_transfer_pair",
                "match_window_hours": 48,
                "matched_fields": ["amount", "direction", "account", "transaction_at"],
                "time_delta_seconds": int(abs(inflow_time - outflow_time).total_seconds()),
            }
            batch = self._draft_batch(
                batch_key=batch_key,
                batch_type="internal_transfer",
                scope_month=scope_month,
                account_key="",
                rows=sorted_rows,
                row_ids=row_ids,
                total_amount=Decimal(amount_text),
                source_versions=source_versions,
                evidence=evidence,
            )
            batch["income_row_ids"] = [self._row_id(inflow)]
            batch["expense_row_ids"] = [self._row_id(outflow)]
            batch["account_pairs"] = [
                self._account_payload(outflow),
                self._account_payload(inflow),
            ]
            batches[str(batch["batch_id"])] = batch
        return batches

    def _draft_batch(
        self,
        *,
        batch_key: str,
        batch_type: str,
        scope_month: str,
        account_key: str,
        rows: list[dict[str, Any]],
        row_ids: list[str],
        total_amount: Decimal,
        source_versions: dict[str, Any],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        first_row = rows[0] if rows else {}
        now = self._timestamp()
        batch_id = self._batch_id(batch_key)
        existing = self._batches.get(batch_id, {})
        return self._normalize_batch(
            {
                "batch_id": batch_id,
                "batch_key": batch_key,
                "batch_type": batch_type,
                "batch_label": NO_OA_BANK_BATCH_LABELS[batch_type],
                "scope_month": scope_month,
                "account_key": account_key,
                "bank_name": self._bank_name(first_row),
                "account_last4": self._account_last4(first_row),
                "status": "draft",
                "row_ids": row_ids,
                "row_count": len(row_ids),
                "total_amount": self._format_amount(total_amount),
                "relation_case_id": str(existing.get("relation_case_id") or batch_id),
                "source_versions": deepcopy(source_versions),
                "evidence": deepcopy(evidence),
                "category_source": self._merged_category_source(evidence),
                "created_by": str(existing.get("created_by") or "system"),
                "created_at": str(existing.get("created_at") or now),
                "submitted_by": "",
                "submitted_at": "",
                "withdrawn_by": "",
                "withdrawn_at": "",
                "withdraw_reason": "",
                "version": int(existing.get("version") or 0) + 1 if existing.get("status") == "withdrawn" else 1,
                "updated_at": now,
            }
        )

    def _conflict_batch(
        self,
        *,
        batch_key: str,
        scope_month: str,
        rows: list[dict[str, Any]],
        row_ids: list[str],
        total_amount: Decimal,
        source_versions: dict[str, Any],
        conflict_code: str,
        conflict_reason: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        batch = self._draft_batch(
            batch_key=batch_key,
            batch_type="internal_transfer",
            scope_month=scope_month,
            account_key="",
            rows=rows,
            row_ids=row_ids,
            total_amount=total_amount,
            source_versions=source_versions,
            evidence={
                "rule_code": "internal_transfer_pair",
                "match_window_hours": 48,
                **deepcopy(evidence),
            },
        )
        batch["status"] = "conflict"
        batch["conflict_code"] = conflict_code
        batch["conflict_reason"] = conflict_reason
        batch["income_row_ids"] = [self._row_id(row) for row in rows if self._direction(row) == "inflow"]
        batch["expense_row_ids"] = [self._row_id(row) for row in rows if self._direction(row) == "outflow"]
        batch["account_pairs"] = [self._account_payload(row) for row in rows]
        return self._normalize_batch(batch)

    def _submitted_batch_still_current(
        self,
        batch: dict[str, Any],
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
    ) -> bool:
        rows_by_id = {self._row_id(row): row for row in rows if self._row_id(row)}
        expected_type = str(batch.get("batch_type") or "")
        for row_id in list(batch.get("row_ids") or []):
            row = rows_by_id.get(str(row_id))
            if row is None or self._category_code(row, categories) != expected_type:
                return False
        return True

    def _append_audit(
        self,
        *,
        operation: str,
        batch_id: str,
        actor: str,
        note: str | None,
        status: str,
        relation_case_id: str,
    ) -> None:
        self._audit_log.append(
            self._normalize_audit_entry(
                {
                    "operation": operation,
                    "batch_id": batch_id,
                    "actor": str(actor or ""),
                    "note": str(note or ""),
                    "status": status,
                    "relation_case_id": relation_case_id,
                    "created_at": self._timestamp(),
                }
            )
        )

    @staticmethod
    def _check_expected_version(batch: dict[str, Any], expected_version: int | None) -> None:
        if expected_version is None:
            return
        if int(batch.get("version") or 0) != int(expected_version):
            raise ValueError("no_oa_bank_batch_version_conflict")

    @staticmethod
    def _active_relation_row_ids(active_relations: list[dict[str, Any]]) -> set[str]:
        row_ids: set[str] = set()
        for relation in list(active_relations or []):
            if not isinstance(relation, dict):
                continue
            if str(relation.get("status") or "active") != "active":
                continue
            row_ids.update(str(row_id) for row_id in list(relation.get("row_ids") or []) if str(row_id))
        return row_ids

    @staticmethod
    def _normalize_batch(batch: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(batch)
        normalized["batch_id"] = str(normalized.get("batch_id") or "")
        normalized["batch_key"] = str(normalized.get("batch_key") or normalized["batch_id"])
        normalized["batch_type"] = str(normalized.get("batch_type") or "")
        normalized["batch_label"] = str(normalized.get("batch_label") or NO_OA_BANK_BATCH_LABELS.get(normalized["batch_type"], ""))
        normalized["scope_month"] = str(normalized.get("scope_month") or "")
        normalized["account_key"] = str(normalized.get("account_key") or "")
        normalized["bank_name"] = str(normalized.get("bank_name") or "")
        normalized["account_last4"] = str(normalized.get("account_last4") or "")
        normalized["status"] = str(normalized.get("status") or "draft")
        normalized["row_ids"] = [str(row_id) for row_id in list(normalized.get("row_ids") or []) if str(row_id)]
        normalized["row_count"] = int(normalized.get("row_count") or len(normalized["row_ids"]))
        normalized["total_amount"] = NoOaBankBatchService._format_amount(
            NoOaBankBatchService._decimal(normalized.get("total_amount")) or ZERO
        )
        normalized["relation_case_id"] = str(normalized.get("relation_case_id") or normalized["batch_id"])
        normalized["source_versions"] = deepcopy(normalized.get("source_versions") if isinstance(normalized.get("source_versions"), dict) else {})
        normalized["evidence"] = deepcopy(normalized.get("evidence") if isinstance(normalized.get("evidence"), dict) else {})
        normalized["created_by"] = str(normalized.get("created_by") or "system")
        normalized["created_at"] = str(normalized.get("created_at") or NoOaBankBatchService._timestamp())
        normalized["submitted_by"] = str(normalized.get("submitted_by") or "")
        normalized["submitted_at"] = str(normalized.get("submitted_at") or "")
        normalized["withdrawn_by"] = str(normalized.get("withdrawn_by") or "")
        normalized["withdrawn_at"] = str(normalized.get("withdrawn_at") or "")
        normalized["withdraw_reason"] = str(normalized.get("withdraw_reason") or "")
        normalized["version"] = int(normalized.get("version") or 1)
        normalized["updated_at"] = str(normalized.get("updated_at") or normalized["created_at"])
        if normalized["batch_type"] == "internal_transfer":
            normalized["income_row_ids"] = [str(row_id) for row_id in list(normalized.get("income_row_ids") or []) if str(row_id)]
            normalized["expense_row_ids"] = [str(row_id) for row_id in list(normalized.get("expense_row_ids") or []) if str(row_id)]
            normalized["account_pairs"] = [
                deepcopy(item) for item in list(normalized.get("account_pairs") or []) if isinstance(item, dict)
            ]
        if normalized["status"] == "conflict":
            normalized["conflict_code"] = str(normalized.get("conflict_code") or "")
            normalized["conflict_reason"] = str(normalized.get("conflict_reason") or "")
        return normalized

    @staticmethod
    def _normalize_audit_entry(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation": str(entry.get("operation") or ""),
            "batch_id": str(entry.get("batch_id") or ""),
            "actor": str(entry.get("actor") or ""),
            "note": str(entry.get("note") or ""),
            "status": str(entry.get("status") or ""),
            "relation_case_id": str(entry.get("relation_case_id") or ""),
            "created_at": str(entry.get("created_at") or NoOaBankBatchService._timestamp()),
        }

    @staticmethod
    def _category_code(row: dict[str, Any], categories: dict[str, dict[str, Any]]) -> str:
        row_id = NoOaBankBatchService._row_id(row)
        category = categories.get(row_id) if isinstance(categories, dict) else None
        if isinstance(category, dict):
            value = category.get("category_code") or category.get("effective_category_code")
            if value is not None:
                return str(value).strip()
        return str(row.get("category_code") or row.get("effective_category_code") or "").strip()

    @staticmethod
    def _category_sources(row_ids: list[str], categories: dict[str, dict[str, Any]]) -> dict[str, str]:
        sources: dict[str, str] = {}
        for row_id in row_ids:
            category = categories.get(row_id)
            if isinstance(category, dict):
                sources[row_id] = str(category.get("category_source") or category.get("source") or "")
        return sources

    @staticmethod
    def _merged_category_source(evidence: dict[str, Any]) -> str:
        sources = evidence.get("category_sources")
        if not isinstance(sources, dict) or not sources:
            return ""
        unique = sorted({str(value) for value in sources.values() if str(value)})
        return unique[0] if len(unique) == 1 else ",".join(unique)

    @staticmethod
    def _display_tags(batch_type: str) -> list[str]:
        return ["免OA", NO_OA_BANK_BATCH_LABELS.get(batch_type, batch_type)]

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()

    @staticmethod
    def _scope_month(row: dict[str, Any]) -> str:
        for field_name in ("scope_month", "pay_receive_time", "trade_time", "transaction_at", "txn_date", "posted_at"):
            value = row.get(field_name)
            if value in (None, "", "--", "—"):
                continue
            text = str(value).strip()
            if len(text) >= 7:
                return text[:7]
        return ""

    @staticmethod
    def _account_key(row: dict[str, Any]) -> str:
        explicit = str(row.get("account_key") or "").strip()
        if explicit:
            return explicit
        bank_name = NoOaBankBatchService._bank_name(row)
        last4 = NoOaBankBatchService._account_last4(row)
        return f"{bank_name}:{last4}" if bank_name or last4 else ""

    @staticmethod
    def _bank_name(row: dict[str, Any]) -> str:
        return str(row.get("bank_name") or row.get("bank_short_name") or row.get("account_bank") or "").strip()

    @staticmethod
    def _account_last4(row: dict[str, Any]) -> str:
        explicit = str(row.get("account_last4") or "").strip()
        if explicit:
            return explicit
        account_no = str(row.get("account_no") or row.get("account_number") or "").strip()
        digits = "".join(ch for ch in account_no if ch.isdigit())
        return digits[-4:] if digits else ""

    @staticmethod
    def _account_payload(row: dict[str, Any]) -> dict[str, str]:
        return {
            "account_key": NoOaBankBatchService._account_key(row),
            "bank_name": NoOaBankBatchService._bank_name(row),
            "account_last4": NoOaBankBatchService._account_last4(row),
        }

    @staticmethod
    def _direction(row: dict[str, Any]) -> str:
        debit = NoOaBankBatchService._decimal(row.get("debit_amount"))
        credit = NoOaBankBatchService._decimal(row.get("credit_amount"))
        if debit is not None and debit > ZERO:
            return "outflow"
        if credit is not None and credit > ZERO:
            return "inflow"
        value = str(row.get("txn_direction") or row.get("direction") or "").strip().lower()
        if value in {"inflow", "income", "收", "进"}:
            return "inflow"
        if value in {"outflow", "expense", "支", "出"}:
            return "outflow"
        signed = NoOaBankBatchService._decimal(row.get("signed_amount"))
        if signed is not None:
            return "inflow" if signed > ZERO else "outflow"
        return ""

    @staticmethod
    def _amount(row: dict[str, Any]) -> Decimal | None:
        debit = NoOaBankBatchService._decimal(row.get("debit_amount"))
        if debit is not None and debit > ZERO:
            return debit
        credit = NoOaBankBatchService._decimal(row.get("credit_amount"))
        if credit is not None and credit > ZERO:
            return credit
        amount = NoOaBankBatchService._decimal(row.get("amount"))
        if amount is not None:
            return abs(amount)
        signed = NoOaBankBatchService._decimal(row.get("signed_amount"))
        return abs(signed) if signed is not None else None

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value in (None, "", "--", "—"):
            return None
        try:
            return Decimal(str(value).replace(",", "")).quantize(CENT)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _format_amount(value: Decimal) -> str:
        return f"{value.quantize(CENT):.2f}"

    @staticmethod
    def _row_time(row: dict[str, Any]) -> datetime | None:
        for field_name in ("pay_receive_time", "trade_time", "transaction_at", "txn_date", "posted_at"):
            value = row.get(field_name)
            if value in (None, "", "--", "—"):
                continue
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
        return None

    @staticmethod
    def _batch_id(batch_key: str) -> str:
        digest = hashlib.sha256(batch_key.encode("utf-8")).hexdigest()[:20]
        return f"no_oa_batch_{digest}"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
