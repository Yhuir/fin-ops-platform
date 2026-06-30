from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
from typing import Any

from fin_ops_platform.services.bank_internal_transfer_detector import INTERNAL_TRANSFER_MATCH_WINDOW
from fin_ops_platform.services.no_oa_legacy_relation_migration_service import NoOaLegacyRelationMigrationService
from fin_ops_platform.services.no_oa_managed_rule_policy import (
    NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
    NO_OA_MANAGED_LABELS,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


NO_OA_BANK_BATCH_SCHEMA_VERSION = "2026-05-no-oa-bank-batch-v1"
NO_OA_BANK_BATCH_RELATION_MODE = "no_oa_bank_batch"
BANK_FLOW_RULE_BATCH_RELATION_MODE = "bank_flow_rule_batch"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")

NO_OA_BANK_BATCH_LABELS = dict(NO_OA_MANAGED_LABELS)
SINGLE_SIDE_BATCH_TYPES = set(NO_OA_MANAGED_LABELS) - {"internal_transfer"}
SUPPORTED_BATCH_TYPES = {*SINGLE_SIDE_BATCH_TYPES, "internal_transfer"}
NO_OA_BANK_BATCH_STATUS_BUCKETS = {
    "draft": "unsubmitted",
    "conflict": "unsubmitted",
    "stale": "unsubmitted",
    "submitted": "submitted",
    "superseded": "superseded",
    "withdrawn": "withdrawn",
}


class NoOaRelationRepairReadPort:
    def __init__(self, pair_relation_service: WorkbenchPairRelationService) -> None:
        self._pair_relation_service = pair_relation_service

    def active_relation_by_case_id(self, case_id: str) -> dict[str, Any] | None:
        relation = self._pair_relation_service.get_active_relation_by_case_id(case_id)
        return deepcopy(relation) if isinstance(relation, dict) else None

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        return [
            deepcopy(relation)
            for relation in self._pair_relation_service.active_relations_for_row_ids(row_ids)
            if isinstance(relation, dict)
        ]


class NoOaBankBatchService:
    def __init__(
        self,
        *,
        batches: dict[str, dict[str, Any]] | None = None,
        audit_log: list[dict[str, Any]] | None = None,
        pair_relation_service: WorkbenchPairRelationService | None = None,
        relation_read_port: NoOaRelationRepairReadPort | None = None,
        relation_command_service: Any | None = None,
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
        self._relation_read_port = relation_read_port or NoOaRelationRepairReadPort(
            pair_relation_service or WorkbenchPairRelationService()
        )
        self._relation_command_service = relation_command_service
        self._legacy_migration_service = NoOaLegacyRelationMigrationService(
            relation_command_service=self._relation_command_service,
        )
        self._last_legacy_migration_result: dict[str, Any] = self._empty_legacy_migration_result()

    @staticmethod
    def _empty_legacy_migration_result() -> dict[str, Any]:
        return {
            "changed": False,
            "changed_case_ids": [],
            "affected_months": [],
            "migrated_batch_ids": [],
            "skipped": [],
        }

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any] | None,
        *,
        pair_relation_service: WorkbenchPairRelationService | None = None,
        relation_read_port: NoOaRelationRepairReadPort | None = None,
        relation_command_service: Any | None = None,
    ) -> "NoOaBankBatchService":
        if not isinstance(snapshot, dict):
            return cls(
                pair_relation_service=pair_relation_service,
                relation_read_port=relation_read_port,
                relation_command_service=relation_command_service,
            )
        batches = snapshot.get("batches")
        audit_log = snapshot.get("audit_log")
        return cls(
            batches=batches if isinstance(batches, dict) else {},
            audit_log=audit_log if isinstance(audit_log, list) else [],
            pair_relation_service=pair_relation_service,
            relation_read_port=relation_read_port,
            relation_command_service=relation_command_service,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": NO_OA_BANK_BATCH_SCHEMA_VERSION,
            "batches": deepcopy(self._batches),
            "audit_log": deepcopy(self._audit_log),
        }

    def public_snapshot(self) -> dict[str, Any]:
        public_batches: dict[str, dict[str, Any]] = {}
        for batch in self.list_batches():
            status = str(batch.get("status") or "").strip()
            status_bucket = str(batch.get("status_bucket") or "").strip()
            if status == "unsubmitted" and status_bucket == "unsubmitted":
                batch = {
                    **deepcopy(batch),
                    "status": "draft",
                    "status_bucket": "unsubmitted",
                    "can_submit": True,
                    "can_withdraw": False,
                    "blocked_reason": "",
                }
                status = "draft"
            if status not in {"draft", "submitted", "withdrawn"}:
                continue
            batch_id = str(batch.get("batch_id") or "").strip()
            if not batch_id:
                continue
            public_batches[batch_id] = deepcopy(batch)
        return {
            "schema_version": NO_OA_BANK_BATCH_SCHEMA_VERSION,
            "batches": public_batches,
            "audit_log": deepcopy(self._audit_log),
        }

    def build_batches(
        self,
        bank_rows: list[dict[str, Any]],
        categories_by_transaction_id: dict[str, dict[str, Any]],
        active_relations: list[dict[str, Any]],
        source_versions: dict[str, Any] | None,
        eligible_batch_types: set[str] | list[str] | tuple[str, ...] | None = None,
        apply_relation_repairs: bool = True,
        refresh_scope_key: str = "all",
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> list[dict[str, Any]]:
        normalized_refresh_scope_key = str(refresh_scope_key or "all").strip() or "all"
        normalized_relation_mode = self._normalize_relation_mode(relation_mode)
        if self._is_month_scope_key(normalized_refresh_scope_key):
            return self._build_batches_for_month_scope(
                refresh_scope_key=normalized_refresh_scope_key,
                bank_rows=bank_rows,
                categories_by_transaction_id=categories_by_transaction_id,
                active_relations=active_relations,
                source_versions=source_versions,
                eligible_batch_types=eligible_batch_types,
                apply_relation_repairs=apply_relation_repairs,
                relation_mode=normalized_relation_mode,
            )

        rows = [dict(row) for row in list(bank_rows or []) if isinstance(row, dict)]
        categories = categories_by_transaction_id if isinstance(categories_by_transaction_id, dict) else {}
        source_version_payload = dict(source_versions or {})
        eligible_types = self._eligible_batch_types(eligible_batch_types)
        self._last_legacy_migration_result = self._empty_legacy_migration_result()

        if apply_relation_repairs and normalized_relation_mode == NO_OA_BANK_BATCH_RELATION_MODE:
            self._migrate_legacy_active_relations(
                rows=rows,
                categories=categories,
                active_relations=active_relations,
                source_versions=source_version_payload,
                eligible_batch_types=eligible_types,
            )
            self._consolidate_submitted_single_side_batches(
                rows=rows,
                categories=categories,
                source_versions=source_version_payload,
            )
            self._prune_submitted_single_side_batches_for_category_drift(
                rows=rows,
                categories=categories,
            )
            self._repair_submitted_no_oa_relation_consistency(
                rows=rows,
                categories=categories,
            )
        effective_active_relations = self._effective_active_relations_after_migration(
            active_relations,
            rows,
            categories,
            relation_mode=normalized_relation_mode,
        )
        occupied_row_ids = self._active_relation_row_ids(effective_active_relations)
        relation_backed_submitted_batches = self._relation_backed_submitted_batches(
            effective_active_relations,
            rows,
            categories,
            source_version_payload,
            relation_mode=normalized_relation_mode,
        )

        generated: dict[str, dict[str, Any]] = {}
        single_side_batches = self._build_single_side_batches(rows, categories, occupied_row_ids, source_version_payload, eligible_types)
        self._assign_relation_mode(single_side_batches, normalized_relation_mode)
        generated.update(single_side_batches)
        internal_transfer_batches = self._build_internal_transfer_batches(
            rows,
            categories,
            occupied_row_ids,
            source_version_payload,
            eligible_types,
        )
        self._assign_relation_mode(internal_transfer_batches, normalized_relation_mode)
        generated.update(internal_transfer_batches)

        submitted_or_withdrawn = {
            batch_id: deepcopy(batch)
            for batch_id, batch in self._batches.items()
            if batch.get("status") in {"submitted", "withdrawn", "stale", "superseded"}
            and self._batch_relation_mode(batch) == normalized_relation_mode
        }
        for batch_id, batch in submitted_or_withdrawn.items():
            if batch.get("status") == "superseded":
                generated[batch_id] = batch
                continue
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

        repaired_relation_backed_batches: list[dict[str, Any]] = []
        for batch_id, relation_backed_batch in relation_backed_submitted_batches.items():
            existing_batch = self._batches.get(batch_id)
            current_generated = generated.get(batch_id)
            if (
                isinstance(current_generated, dict)
                and str(current_generated.get("status") or "") == "submitted"
                and self._batch_relation_mode(current_generated) == normalized_relation_mode
            ):
                continue
            if (
                not isinstance(existing_batch, dict)
                or str(existing_batch.get("status") or "") != "submitted"
            ):
                repaired_relation_backed_batches.append(relation_backed_batch)
            generated[batch_id] = relation_backed_batch
        if repaired_relation_backed_batches:
            self._merge_legacy_migration_result(
                changed_case_ids=[
                    str(batch.get("relation_case_id") or batch.get("batch_id") or "")
                    for batch in repaired_relation_backed_batches
                ],
                affected_months=[
                    month
                    for batch in repaired_relation_backed_batches
                    for month in self._batch_affected_months(batch)
                ],
                migrated_batch_ids=[
                    str(batch.get("batch_id") or "")
                    for batch in repaired_relation_backed_batches
                ],
            )

        for batch in generated.values():
            if isinstance(batch, dict):
                batch["source_versions"] = deepcopy(source_version_payload)
        self._batches = {batch_id: self._normalize_batch(batch) for batch_id, batch in generated.items()}
        return self.list_batches()

    def _build_batches_for_month_scope(
        self,
        *,
        refresh_scope_key: str,
        bank_rows: list[dict[str, Any]],
        categories_by_transaction_id: dict[str, dict[str, Any]],
        active_relations: list[dict[str, Any]],
        source_versions: dict[str, Any] | None,
        eligible_batch_types: set[str] | list[str] | tuple[str, ...] | None,
        apply_relation_repairs: bool,
        relation_mode: str,
    ) -> list[dict[str, Any]]:
        original_batches = deepcopy(self._batches)
        original_audit_log = deepcopy(self._audit_log)
        scoped_batches = {
            batch_id: deepcopy(batch)
            for batch_id, batch in original_batches.items()
            if self._batch_scope_month(batch) == refresh_scope_key
        }
        scoped_service = NoOaBankBatchService(
            batches=scoped_batches,
            audit_log=[],
            relation_read_port=self._relation_read_port,
            relation_command_service=self._relation_command_service,
        )
        scoped_service.build_batches(
            bank_rows,
            categories_by_transaction_id,
            active_relations,
            source_versions,
            eligible_batch_types=eligible_batch_types,
            apply_relation_repairs=apply_relation_repairs,
            refresh_scope_key="all",
            relation_mode=relation_mode,
        )
        scoped_snapshot = scoped_service.snapshot()
        scoped_snapshot_batches = scoped_snapshot.get("batches") if isinstance(scoped_snapshot, dict) else {}
        merged_batches = {
            batch_id: deepcopy(batch)
            for batch_id, batch in original_batches.items()
            if self._batch_scope_month(batch) != refresh_scope_key
        }
        merged_batches.update(
            {
                str(batch_id): deepcopy(batch)
                for batch_id, batch in dict(scoped_snapshot_batches or {}).items()
                if isinstance(batch, dict)
            }
        )
        self._batches = {
            str(batch_id): self._normalize_batch(batch)
            for batch_id, batch in merged_batches.items()
            if isinstance(batch, dict)
        }
        scoped_audit_log = scoped_service.audit_log()
        self._audit_log = [
            *original_audit_log,
            *[
                deepcopy(entry)
                for entry in scoped_audit_log
                if isinstance(entry, dict) and entry not in original_audit_log
            ],
        ]
        self._last_legacy_migration_result = scoped_service.last_legacy_migration_result()
        return self.list_batches()

    def submit_selected_rows(
        self,
        *,
        bank_rows: list[dict[str, Any]],
        categories_by_transaction_id: dict[str, dict[str, Any]],
        active_relations: list[dict[str, Any]],
        source_versions: dict[str, Any] | None,
        eligible_batch_types: set[str] | list[str] | tuple[str, ...],
        row_ids: list[str],
        actor: str,
        note: str | None = None,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> dict[str, Any]:
        normalized_relation_mode = self._normalize_relation_mode(relation_mode)
        rows_by_id = {self._row_id(row): dict(row) for row in list(bank_rows or []) if self._row_id(row)}
        selected_row_ids = [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]
        if not selected_row_ids:
            raise ValueError("no_oa_bank_batch_selection_empty")
        if len(set(selected_row_ids)) != len(selected_row_ids):
            raise ValueError("no_oa_bank_batch_selection_duplicate_rows")
        selected_rows = [rows_by_id.get(row_id) for row_id in selected_row_ids]
        if any(row is None for row in selected_rows):
            raise ValueError("no_oa_bank_batch_selection_unknown_row")
        resolved_rows = [row for row in selected_rows if isinstance(row, dict)]
        occupied_row_ids = self._active_relation_row_ids(active_relations)
        if any(row_id in occupied_row_ids for row_id in selected_row_ids):
            raise ValueError("no_oa_bank_batch_selection_occupied")
        categories = categories_by_transaction_id if isinstance(categories_by_transaction_id, dict) else {}
        eligible_types = self._eligible_batch_types(eligible_batch_types)
        batch_types = {self._category_code(row, categories) for row in resolved_rows}
        batch_types.discard("")
        if len(batch_types) != 1:
            raise ValueError("no_oa_bank_batch_selection_cross_tag")
        batch_type = next(iter(batch_types))
        if batch_type not in eligible_types:
            raise ValueError("no_oa_bank_batch_selection_unselected_tag")
        scope_months = {self._scope_month(row) for row in resolved_rows}
        scope_months.discard("")
        if len(scope_months) != 1:
            raise ValueError("no_oa_bank_batch_selection_cross_month")
        account_keys = {self._account_key(row) for row in resolved_rows}
        account_keys.discard("")
        if len(account_keys) != 1:
            raise ValueError("no_oa_bank_batch_selection_cross_bank")
        scope_month = next(iter(scope_months))
        account_key = next(iter(account_keys))
        sorted_rows = sorted(resolved_rows, key=self._row_id)
        sorted_row_ids = [self._row_id(row) for row in sorted_rows]
        batch_key = f"selection:{batch_type}:{scope_month}:{account_key}:{self._row_set_digest(sorted_row_ids)}"
        evidence = {
            "matched_fields": ["selected_transaction_ids", "category_code", "account_key", "scope_month"],
            "category_sources": self._category_sources(sorted_row_ids, categories),
            "selected_transaction_ids": sorted_row_ids,
        }
        draft = self._draft_batch(
            batch_key=batch_key,
            batch_type=batch_type,
            scope_month=scope_month,
            account_key=account_key,
            rows=sorted_rows,
            row_ids=sorted_row_ids,
            total_amount=sum((self._amount(row) or ZERO for row in sorted_rows), ZERO),
            categories=categories,
            source_versions=dict(source_versions or {}),
            evidence=evidence,
        )
        draft["relation_mode"] = normalized_relation_mode
        self._batches[str(draft["batch_id"])] = self._normalize_batch(draft)
        return self.submit_batch(
            str(draft["batch_id"]),
            actor=actor,
            expected_version=int(draft.get("version") or 1),
            note=note,
        )

    def last_legacy_migration_result(self) -> dict[str, Any]:
        return deepcopy(self._last_legacy_migration_result)

    def _effective_active_relations_after_migration(
        self,
        original_active_relations: list[dict[str, Any]],
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        *,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> list[dict[str, Any]]:
        migrated_case_ids = {
            str(case_id).strip()
            for case_id in list(self._last_legacy_migration_result.get("changed_case_ids") or [])
            if str(case_id).strip()
        }
        effective_by_case_id: dict[str, dict[str, Any]] = {}
        for relation in list(original_active_relations or []):
            if not isinstance(relation, dict):
                continue
            case_id = str(relation.get("case_id") or "").strip()
            if case_id and case_id in migrated_case_ids:
                continue
            effective_by_case_id[case_id] = deepcopy(relation)

        for relation in self._submitted_batch_relation_facts(
            rows,
            categories,
            relation_mode=relation_mode,
        ):
            case_id = str(relation.get("case_id") or "").strip()
            if case_id:
                effective_by_case_id[case_id] = relation
        return list(effective_by_case_id.values())

    def _submitted_batch_relation_facts(
        self,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        *,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> list[dict[str, Any]]:
        normalized_relation_mode = self._normalize_relation_mode(relation_mode)
        facts: list[dict[str, Any]] = []
        for batch in self._batches.values():
            if str(batch.get("status") or "") != "submitted":
                continue
            if self._batch_relation_mode(batch) != normalized_relation_mode:
                continue
            if not self._submitted_batch_still_current(batch, rows, categories):
                continue
            relation_case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
            row_ids = [
                str(row_id).strip()
                for row_id in list(batch.get("row_ids") or [])
                if str(row_id).strip()
            ]
            if not relation_case_id or not row_ids:
                continue
            facts.append(
                {
                    "case_id": relation_case_id,
                    "row_ids": row_ids,
                    "row_types": ["bank" for _ in row_ids],
                    "relation_mode": normalized_relation_mode,
                    "status": "active",
                    "month_scope": str(batch.get("scope_month") or "all"),
                    "created_by": str(batch.get("submitted_by") or batch.get("created_by") or ""),
                    "created_at": str(batch.get("submitted_at") or batch.get("created_at") or self._timestamp()),
                    "updated_at": str(batch.get("updated_at") or batch.get("submitted_at") or self._timestamp()),
                    "special_metadata": self._no_oa_relation_metadata(batch),
                    "evidence": deepcopy(batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}),
                    "display_tags": self._display_tags(str(batch.get("batch_type") or "")),
                }
            )
        return facts

    def list_batches(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        resolved_filters = filters if isinstance(filters, dict) else {}
        batches = [
            self._enrich_batch(batch)
            for batch in self._batches.values()
            if str(batch.get("status") or "").strip() != "superseded"
        ]
        for field_name, filter_key in (
            ("scope_month", "month"),
            ("batch_type", "type"),
            ("status", "status"),
            ("account_key", "account_key"),
        ):
            value = str(resolved_filters.get(filter_key) or "").strip()
            if value:
                batches = [batch for batch in batches if str(batch.get(field_name) or "") == value]
        relation_mode = str(resolved_filters.get("relation_mode") or "").strip()
        if relation_mode:
            target_relation_mode = self._normalize_relation_mode(relation_mode)
            batches = [batch for batch in batches if self._batch_relation_mode(batch) == target_relation_mode]
        bucket = str(resolved_filters.get("bucket") or "").strip()
        if bucket and bucket != "all":
            batches = [batch for batch in batches if str(batch.get("status_bucket") or "") == bucket]
        return sorted(
            batches,
            key=lambda item: (
                str(item.get("scope_month") or ""),
                str(item.get("batch_type") or ""),
                str(item.get("account_key") or ""),
                str(item.get("batch_id") or ""),
            ),
        )

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        resolved_batch_id = str(batch_id or "").strip()
        if not resolved_batch_id or resolved_batch_id not in self._batches:
            raise KeyError("no_oa_bank_batch_not_found")
        return self._enrich_batch(self._batches[resolved_batch_id])

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
            relation_case_id=relation_case_id,
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
        if batch.get("status") not in {"submitted", "stale"}:
            raise ValueError("only_submitted_no_oa_bank_batch_can_be_withdrawn")
        if batch.get("status") == "stale" and not self._has_active_relation_for_batch(batch):
            raise ValueError("stale_no_oa_bank_batch_has_no_active_relation_to_withdraw")
        self._check_expected_version(batch, expected_version)

        timestamp = self._timestamp()
        relation_case_id = str(batch.get("relation_case_id") or batch["batch_id"])
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

    def relation_command_payload_for_batch(self, batch: dict[str, Any], *, note: str | None = None) -> dict[str, Any]:
        batch_payload = dict(batch)
        batch_type = str(batch_payload.get("batch_type") or "")
        row_ids = [
            str(row_id).strip()
            for row_id in list(batch_payload.get("row_ids") or [])
            if str(row_id).strip()
        ]
        evidence = {
            "batch_key": batch_payload.get("batch_key"),
            "category_source": batch_payload.get("category_source"),
            "row_count": batch_payload.get("row_count"),
            "total_amount": batch_payload.get("total_amount"),
            **(deepcopy(batch_payload.get("evidence")) if isinstance(batch_payload.get("evidence"), dict) else {}),
        }
        return {
            "case_id": str(batch_payload.get("relation_case_id") or batch_payload.get("batch_id") or ""),
            "row_ids": row_ids,
            "row_types": ["bank" for _ in row_ids],
            "relation_mode": NO_OA_BANK_BATCH_RELATION_MODE,
            "month_scope": str(batch_payload.get("scope_month") or "all"),
            "note": str(note or "") or f"免OA流水批量处理：{batch_payload.get('batch_label')}",
            "special_metadata": self._no_oa_relation_metadata(batch_payload),
            "evidence": evidence,
            "display_tags": self._display_tags(batch_type),
        }

    def _require_relation_command_service(self) -> Any:
        if self._relation_command_service is None:
            raise ValueError("no_oa_relation_command_unavailable")
        return self._relation_command_service

    def _confirm_no_oa_relation(
        self,
        *,
        case_id: str,
        row_ids: list[str],
        month_scope: str,
        occurred_at: str,
        note: str,
        special_metadata: dict[str, Any],
        evidence: dict[str, Any] | None = None,
        display_tags: list[str] | None = None,
        history_operation_type: str,
    ) -> tuple[dict[str, Any], list[str]]:
        command_service = self._require_relation_command_service()
        try:
            result = command_service.confirm_relation(
                case_id=case_id,
                row_ids=row_ids,
                row_types=["bank" for _ in row_ids],
                relation_mode=NO_OA_BANK_BATCH_RELATION_MODE,
                actor_id=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                month_scope=month_scope,
                occurred_at=occurred_at,
                note=note,
                special_metadata=deepcopy(special_metadata),
                evidence=deepcopy(evidence if isinstance(evidence, dict) else {}),
                display_tags=[
                    str(tag).strip()
                    for tag in list(display_tags or [])
                    if str(tag).strip()
                ],
                history_operation_type=history_operation_type,
            )
        except WorkbenchRelationCommandError as exc:
            raise ValueError(exc.error_code) from exc
        relation = result.get("relation") if isinstance(result, dict) else None
        raw_changed_case_ids = result.get("changed_case_ids") if isinstance(result, dict) else []
        changed_case_ids = [
            str(case_id).strip()
            for case_id in list(raw_changed_case_ids or [])
            if str(case_id).strip()
        ]
        return deepcopy(relation) if isinstance(relation, dict) else {}, changed_case_ids

    def _cancel_no_oa_relation(
        self,
        case_id: str,
        *,
        occurred_at: str,
        reason: str,
        history_operation_type: str,
    ) -> list[str]:
        command_service = self._require_relation_command_service()
        try:
            result = command_service.cancel_relation(
                case_id=case_id,
                actor_id=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                reason=reason,
                occurred_at=occurred_at,
                history_operation_type=history_operation_type,
            )
        except WorkbenchRelationCommandError as exc:
            if exc.error_code == "workbench_relation_not_found":
                return []
            raise ValueError(exc.error_code) from exc
        raw_changed_case_ids = result.get("changed_case_ids") if isinstance(result, dict) else []
        return [
            str(changed_case_id).strip()
            for changed_case_id in list(raw_changed_case_ids or [])
            if str(changed_case_id).strip()
        ]

    def audit_log(self) -> list[dict[str, Any]]:
        return deepcopy(self._audit_log)

    def _migrate_legacy_active_relations(
        self,
        *,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        active_relations: list[dict[str, Any]],
        source_versions: dict[str, Any],
        eligible_batch_types: set[str],
    ) -> None:
        result: dict[str, Any] = {
            "changed": False,
            "changed_case_ids": [],
            "affected_months": [],
            "migrated_batch_ids": [],
            "skipped": [],
        }
        if self._relation_command_service is None:
            self._last_legacy_migration_result = result
            return
        rows_by_id = {self._row_id(row): row for row in rows if self._row_id(row)}
        single_side_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for legacy_relation in self._active_relations_for_no_oa_migration(
            active_relations,
            rows_by_id=rows_by_id,
            categories=categories,
            eligible_batch_types=eligible_batch_types,
        ):
            batch_type = (
                self._legacy_migration_service.batch_type_for_relation(legacy_relation)
                or self._manual_confirmed_internal_transfer_relation_batch_type(
                    legacy_relation,
                    rows_by_id=rows_by_id,
                    categories=categories,
                )
            )
            if not batch_type:
                continue
            row_ids = [str(row_id).strip() for row_id in list(legacy_relation.get("row_ids") or []) if str(row_id).strip()]
            relation_case_id = str(legacy_relation.get("case_id") or "").strip()
            relation_rows = [rows_by_id.get(row_id) for row_id in row_ids]
            if not row_ids or any(row is None for row in relation_rows):
                result["skipped"].append(
                    {
                        "legacy_case_id": relation_case_id,
                        "reason": "legacy_relation_rows_not_found",
                        "row_ids": row_ids,
                    }
                )
                continue
            resolved_rows = [row for row in relation_rows if isinstance(row, dict)]
            mismatched_row_ids = [
                row_id
                for row_id, row in zip(row_ids, resolved_rows, strict=True)
                if self._category_code(row, categories) != batch_type
            ]
            if mismatched_row_ids:
                changed_ids = self._cancel_no_oa_relation(
                    relation_case_id,
                    occurred_at=self._timestamp(),
                    reason="历史免OA候选关系分类已变化，取消旧关系。",
                    history_operation_type="no_oa_legacy_relation_category_mismatch",
                )
                if changed_ids:
                    result["changed"] = True
                    result["changed_case_ids"].extend(changed_ids)
                    result["affected_months"].extend(
                        month
                        for month in [self._legacy_relation_scope_month(legacy_relation, resolved_rows)]
                        if month and month != "all"
                    )
                result["skipped"].append(
                    {
                        "legacy_case_id": relation_case_id,
                        "reason": "legacy_relation_category_mismatch",
                        "row_ids": mismatched_row_ids,
                    }
                )
                continue

            if batch_type in SINGLE_SIDE_BATCH_TYPES:
                sorted_rows = sorted(resolved_rows, key=self._row_id)
                first_row = sorted_rows[0] if sorted_rows else {}
                scope_month = self._legacy_relation_scope_month(legacy_relation, sorted_rows)
                account_key = self._account_key(first_row)
                single_side_groups.setdefault((batch_type, scope_month, account_key), []).append(
                    {
                        "legacy_relation": legacy_relation,
                        "rows": sorted_rows,
                        "row_ids": row_ids,
                    }
                )
                continue

            migrated_at = self._timestamp()
            migrated_batch = self._migrated_submitted_batch(
                legacy_relation=legacy_relation,
                batch_type=batch_type,
                rows=resolved_rows,
                row_ids=row_ids,
                source_versions=source_versions,
                migrated_at=migrated_at,
            )
            existing_submitted_batch = self._existing_submitted_batch_for_legacy_relation(
                batch_type=batch_type,
                row_ids=row_ids,
                rows=rows,
                categories=categories,
            )
            batch = (
                self._merge_legacy_relation_into_submitted_batch(
                    existing_submitted_batch,
                    migrated_batch=migrated_batch,
                    source_versions=source_versions,
                    migrated_at=migrated_at,
                )
                if existing_submitted_batch is not None
                else migrated_batch
            )
            batch_id = str(batch["batch_id"])
            existing_batch = self._batches.get(batch_id)
            existing_evidence = (
                existing_batch.get("evidence")
                if isinstance(existing_batch, dict) and isinstance(existing_batch.get("evidence"), dict)
                else {}
            )
            is_new_batch = not (
                isinstance(existing_batch, dict)
                and existing_batch.get("status") == "submitted"
                and existing_evidence.get("migration_source") == NO_OA_LEGACY_RELATION_MIGRATION_SOURCE
            )
            self._batches[batch_id] = self._normalize_batch(batch)
            relation, changed_case_ids = self._legacy_migration_service.migrate_relation_to_no_oa(
                legacy_relation=legacy_relation,
                existing_relation=self._active_relation_by_case_id(active_relations, str(batch["relation_case_id"])),
                no_oa_relation_case_id=str(batch["relation_case_id"]),
                row_ids=row_ids,
                month_scope=str(batch.get("scope_month") or legacy_relation.get("month_scope") or "all"),
                created_at=migrated_at,
                special_metadata=self._no_oa_relation_metadata(batch),
                evidence=deepcopy(batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}),
                display_tags=self._display_tags(batch_type),
            )
            if relation:
                batch["relation_case_id"] = str(relation.get("case_id") or batch["relation_case_id"])
                self._batches[batch_id] = self._normalize_batch(batch)
            if is_new_batch:
                self._append_audit(
                    operation="migrate_legacy_relation",
                    batch_id=batch_id,
                    actor=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                    note=f"{legacy_relation.get('relation_mode')}:{relation_case_id}",
                    status="submitted",
                    relation_case_id=str(batch["relation_case_id"]),
                )
            if changed_case_ids or is_new_batch:
                result["changed"] = True
            result["changed_case_ids"].extend(changed_case_ids)
            result["affected_months"].extend(self._batch_affected_months(batch))
            result["migrated_batch_ids"].append(batch_id)
        for (batch_type, scope_month, account_key), group_items in single_side_groups.items():
            migrated_at = self._timestamp()
            legacy_relations = [
                item["legacy_relation"]
                for item in group_items
                if isinstance(item.get("legacy_relation"), dict)
            ]
            group_rows = [
                row
                for item in group_items
                for row in list(item.get("rows") or [])
                if isinstance(row, dict)
            ]
            batch = self._migrated_single_side_submitted_batch(
                legacy_relations=legacy_relations,
                batch_type=batch_type,
                rows=group_rows,
                source_versions=source_versions,
                migrated_at=migrated_at,
                scope_month=scope_month,
                account_key=account_key,
            )
            batch_id = str(batch["batch_id"])
            existing_batch = self._batches.get(batch_id)
            existing_evidence = (
                existing_batch.get("evidence")
                if isinstance(existing_batch, dict) and isinstance(existing_batch.get("evidence"), dict)
                else {}
            )
            is_new_batch = not (
                isinstance(existing_batch, dict)
                and existing_batch.get("status") == "submitted"
                and existing_evidence.get("migration_source") == NO_OA_LEGACY_RELATION_MIGRATION_SOURCE
            )
            self._batches[batch_id] = self._normalize_batch(batch)
            relation, changed_case_ids = self._legacy_migration_service.migrate_relations_to_no_oa(
                legacy_relations=legacy_relations,
                existing_relation=self._active_relation_by_case_id(active_relations, str(batch["relation_case_id"])),
                no_oa_relation_case_id=str(batch["relation_case_id"]),
                row_ids=[str(row_id) for row_id in list(batch.get("row_ids") or [])],
                month_scope=str(batch.get("scope_month") or "all"),
                created_at=migrated_at,
                special_metadata=self._no_oa_relation_metadata(batch),
                evidence=deepcopy(batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}),
                display_tags=self._display_tags(batch_type),
            )
            if relation:
                batch["relation_case_id"] = str(relation.get("case_id") or batch["relation_case_id"])
                self._batches[batch_id] = self._normalize_batch(batch)
            if is_new_batch:
                legacy_case_ids = [
                    str(relation.get("case_id") or "").strip()
                    for relation in legacy_relations
                    if str(relation.get("case_id") or "").strip()
                ]
                self._append_audit(
                    operation="migrate_legacy_relation",
                    batch_id=batch_id,
                    actor=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                    note=f"{batch_type}:{','.join(legacy_case_ids)}",
                    status="submitted",
                    relation_case_id=str(batch["relation_case_id"]),
                )
            if changed_case_ids or is_new_batch:
                result["changed"] = True
            result["changed_case_ids"].extend(changed_case_ids)
            result["affected_months"].extend(self._batch_affected_months(batch))
            result["migrated_batch_ids"].append(batch_id)
        result["changed_case_ids"] = sorted({str(case_id) for case_id in result["changed_case_ids"] if str(case_id)})
        result["affected_months"] = sorted({str(month) for month in result["affected_months"] if str(month)})
        result["migrated_batch_ids"] = sorted({str(batch_id) for batch_id in result["migrated_batch_ids"] if str(batch_id)})
        self._last_legacy_migration_result = result

    def _active_relations_for_no_oa_migration(
        self,
        active_relations: list[dict[str, Any]],
        *,
        rows_by_id: dict[str, dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        eligible_batch_types: set[str],
    ) -> list[dict[str, Any]]:
        relations: list[dict[str, Any]] = []
        seen_case_ids: set[str] = set()
        for relation in self._legacy_migration_service.active_legacy_relations(active_relations):
            case_id = str(relation.get("case_id") or "").strip()
            if not case_id or case_id in seen_case_ids:
                continue
            seen_case_ids.add(case_id)
            relations.append(relation)

        if "internal_transfer" not in eligible_batch_types:
            return relations

        for relation in list(active_relations or []):
            if not isinstance(relation, dict):
                continue
            if str(relation.get("status") or "active") != "active":
                continue
            case_id = str(relation.get("case_id") or "").strip()
            if not case_id or case_id in seen_case_ids:
                continue
            if not self._manual_confirmed_internal_transfer_relation_batch_type(
                relation,
                rows_by_id=rows_by_id,
                categories=categories,
            ):
                continue
            seen_case_ids.add(case_id)
            relations.append(deepcopy(relation))
        return relations

    @staticmethod
    def _active_relation_by_case_id(
        active_relations: list[dict[str, Any]],
        case_id: str,
    ) -> dict[str, Any] | None:
        resolved_case_id = str(case_id or "").strip()
        if not resolved_case_id:
            return None
        for relation in list(active_relations or []):
            if not isinstance(relation, dict):
                continue
            if str(relation.get("status") or "active") != "active":
                continue
            if str(relation.get("case_id") or "").strip() == resolved_case_id:
                return deepcopy(relation)
        return None

    def _manual_confirmed_internal_transfer_relation_batch_type(
        self,
        relation: dict[str, Any],
        *,
        rows_by_id: dict[str, dict[str, Any]],
        categories: dict[str, dict[str, Any]],
    ) -> str:
        if str(relation.get("relation_mode") or "").strip() != "manual_confirmed":
            return ""
        row_ids = [
            str(row_id).strip()
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        row_types = [
            str(row_type).strip()
            for row_type in list(relation.get("row_types") or [])
            if str(row_type).strip()
        ]
        if len(row_ids) != 2 or len(row_types) != len(row_ids):
            return ""
        if any(row_type not in {"bank", "bank_transaction"} for row_type in row_types):
            return ""
        relation_rows = [rows_by_id.get(row_id) for row_id in row_ids]
        if any(row is None for row in relation_rows):
            return ""
        resolved_rows = [row for row in relation_rows if isinstance(row, dict)]
        if any(self._category_code(row, categories) != "internal_transfer" for row in resolved_rows):
            return ""
        directions = {self._direction(row) for row in resolved_rows}
        if not {"inflow", "outflow"}.issubset(directions):
            return ""
        account_keys = {self._account_key(row) for row in resolved_rows if self._account_key(row)}
        if len(account_keys) < 2:
            return ""
        amounts = [self._amount(row) for row in resolved_rows]
        if any(amount is None for amount in amounts):
            return ""
        if len({self._format_amount(amount) for amount in amounts if amount is not None}) != 1:
            return ""
        return "internal_transfer"

    def _consolidate_submitted_single_side_batches(
        self,
        *,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> None:
        rows_by_id = {self._row_id(row): row for row in rows if self._row_id(row)}
        grouped_batches: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for batch in self._batches.values():
            batch_type = str(batch.get("batch_type") or "")
            if str(batch.get("status") or "") != "submitted" or batch_type not in SINGLE_SIDE_BATCH_TYPES:
                continue
            if not self._submitted_batch_still_current(batch, rows, categories):
                continue
            batch_rows = [
                rows_by_id.get(str(row_id))
                for row_id in list(batch.get("row_ids") or [])
                if str(row_id)
            ]
            if not batch_rows or any(row is None for row in batch_rows):
                continue
            resolved_rows = [row for row in batch_rows if isinstance(row, dict)]
            first_row = resolved_rows[0]
            scope_month = str(batch.get("scope_month") or self._scope_month(first_row)).strip()
            account_key = str(batch.get("account_key") or self._account_key(first_row)).strip()
            if not scope_month or not account_key:
                continue
            grouped_batches.setdefault((batch_type, scope_month, account_key), []).append(deepcopy(batch))

        for (batch_type, scope_month, account_key), source_batches in grouped_batches.items():
            source_batch_ids = sorted(
                {
                    str(batch.get("batch_id") or "").strip()
                    for batch in source_batches
                    if str(batch.get("batch_id") or "").strip()
                }
            )
            if len(source_batch_ids) <= 1:
                continue
            consolidated_at = self._timestamp()
            consolidated_rows = [
                rows_by_id[row_id]
                for row_id in sorted(
                    {
                        str(row_id)
                        for batch in source_batches
                        for row_id in list(batch.get("row_ids") or [])
                        if str(row_id) in rows_by_id
                    }
                )
            ]
            consolidated_batch = self._consolidated_single_side_submitted_batch(
                source_batches=source_batches,
                batch_type=batch_type,
                rows=consolidated_rows,
                source_versions=source_versions,
                consolidated_at=consolidated_at,
                scope_month=scope_month,
                account_key=account_key,
            )
            consolidated_batch_id = str(consolidated_batch["batch_id"])
            superseded_batch_ids = [
                batch_id for batch_id in source_batch_ids if batch_id != consolidated_batch_id
            ]
            if not superseded_batch_ids:
                continue

            self._batches[consolidated_batch_id] = self._normalize_batch(consolidated_batch)
            changed_case_ids = self._replace_consolidated_no_oa_relation(
                batch=consolidated_batch,
                source_batches=source_batches,
                superseded_batch_ids=superseded_batch_ids,
                consolidated_at=consolidated_at,
            )
            for superseded_batch_id in superseded_batch_ids:
                superseded_batch = deepcopy(self._batches.get(superseded_batch_id) or {})
                if not superseded_batch:
                    continue
                superseded_batch.update(
                    {
                        "status": "superseded",
                        "superseded_by_batch_id": consolidated_batch_id,
                        "updated_at": consolidated_at,
                        "version": int(superseded_batch.get("version") or 1) + 1,
                    }
                )
                superseded_evidence = (
                    deepcopy(superseded_batch.get("evidence"))
                    if isinstance(superseded_batch.get("evidence"), dict)
                    else {}
                )
                superseded_batch["evidence"] = {
                    **superseded_evidence,
                    "superseded_by_batch_id": consolidated_batch_id,
                    "superseded_at": consolidated_at,
                    "consolidation_source": "submitted_no_oa_single_side_batches",
                }
                self._batches[superseded_batch_id] = self._normalize_batch(superseded_batch)

            self._append_audit(
                operation="consolidate_submitted_single_side_batches",
                batch_id=consolidated_batch_id,
                actor=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                note=f"{batch_type}:{','.join(superseded_batch_ids)}",
                status="submitted",
                relation_case_id=str(consolidated_batch["relation_case_id"]),
            )
            self._merge_legacy_migration_result(
                changed_case_ids=changed_case_ids,
                affected_months=self._batch_affected_months(consolidated_batch),
                migrated_batch_ids=[consolidated_batch_id],
            )
        self._dedupe_consolidated_single_side_batches()

    def _dedupe_consolidated_single_side_batches(self) -> None:
        duplicate_groups: dict[tuple[str, str, tuple[str, ...]], list[dict[str, Any]]] = {}
        for batch in self._batches.values():
            evidence = batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}
            if (
                str(batch.get("status") or "") != "submitted"
                or str(batch.get("batch_type") or "") not in SINGLE_SIDE_BATCH_TYPES
                or evidence.get("consolidation_source") != "submitted_no_oa_single_side_batches"
            ):
                continue
            row_ids = tuple(sorted(str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id)))
            if not row_ids:
                continue
            key = (str(batch.get("batch_type") or ""), str(batch.get("scope_month") or ""), row_ids)
            duplicate_groups.setdefault(key, []).append(deepcopy(batch))

        for _key, batches in duplicate_groups.items():
            if len(batches) <= 1:
                continue
            retained = max(
                batches,
                key=lambda batch: (
                    1 if ":" in str(batch.get("account_key") or "") else 0,
                    len(str(batch.get("account_key") or "")),
                    str(batch.get("updated_at") or batch.get("created_at") or ""),
                    str(batch.get("batch_id") or ""),
                ),
            )
            retained_batch_id = str(retained.get("batch_id") or "")
            deduped_at = self._timestamp()
            changed_case_ids: list[str] = []
            for batch in batches:
                batch_id = str(batch.get("batch_id") or "")
                if not batch_id or batch_id == retained_batch_id:
                    continue
                existing = deepcopy(self._batches.get(batch_id) or {})
                if not existing:
                    continue
                existing.update(
                    {
                        "status": "superseded",
                        "superseded_by_batch_id": retained_batch_id,
                        "updated_at": deduped_at,
                        "version": int(existing.get("version") or 1) + 1,
                    }
                )
                evidence = deepcopy(existing.get("evidence")) if isinstance(existing.get("evidence"), dict) else {}
                existing["evidence"] = {
                    **evidence,
                    "superseded_by_batch_id": retained_batch_id,
                    "superseded_at": deduped_at,
                    "dedupe_source": "submitted_no_oa_single_side_batches",
                }
                self._batches[batch_id] = self._normalize_batch(existing)
                relation_case_id = str(existing.get("relation_case_id") or "")
                if relation_case_id:
                    changed_case_ids.extend(
                        self._cancel_no_oa_relation(
                            relation_case_id,
                            occurred_at=deduped_at,
                            reason="已提交单边免OA批次去重，取消重复批次关系。",
                            history_operation_type="dedupe_consolidated_no_oa_relation_cancel_duplicate",
                        )
                    )
            if changed_case_ids:
                self._merge_legacy_migration_result(
                    changed_case_ids=changed_case_ids,
                    affected_months=self._batch_affected_months(retained),
                    migrated_batch_ids=[retained_batch_id],
                )

    def _prune_submitted_single_side_batches_for_category_drift(
        self,
        *,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
    ) -> None:
        _ = (rows, categories)
        return

    def _repair_submitted_no_oa_relation_consistency(
        self,
        *,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
    ) -> None:
        for batch in list(self._batches.values()):
            if str(batch.get("status") or "") != "submitted":
                continue
            if not self._submitted_batch_still_current(batch, rows, categories):
                continue
            batch_id = str(batch.get("batch_id") or "").strip()
            relation_case_id = str(batch.get("relation_case_id") or batch_id).strip()
            row_ids = [str(row_id).strip() for row_id in list(batch.get("row_ids") or []) if str(row_id).strip()]
            if not batch_id or not relation_case_id or not row_ids:
                continue

            active_relation = self._relation_read_port.active_relation_by_case_id(relation_case_id)
            if self._active_relation_matches_submitted_no_oa_batch(active_relation, batch):
                continue
            blocking_relations = [
                relation
                for relation in self._relation_read_port.active_relations_for_row_ids(row_ids)
                if isinstance(relation, dict)
                and str(relation.get("case_id") or "").strip() != relation_case_id
                and not self._is_no_oa_relation(relation)
            ]
            if blocking_relations:
                result = deepcopy(self._last_legacy_migration_result)
                result["skipped"] = [
                    *list(result.get("skipped") or []),
                    {
                        "batch_id": batch_id,
                        "relation_case_id": relation_case_id,
                        "reason": "submitted_no_oa_rows_occupied_by_non_no_oa_relation",
                        "blocking_case_ids": sorted(
                            {
                                str(relation.get("case_id") or "").strip()
                                for relation in blocking_relations
                                if str(relation.get("case_id") or "").strip()
                            }
                        ),
                        "row_ids": row_ids,
                    },
                ]
                self._last_legacy_migration_result = result
                continue

            repaired_at = self._timestamp()
            changed_case_ids: list[str] = []
            stale_case_ids = self._submitted_batch_stale_relation_case_ids(batch)
            for stale_case_id in stale_case_ids:
                if stale_case_id == relation_case_id:
                    continue
                changed_case_ids.extend(
                    self._cancel_no_oa_relation(
                        stale_case_id,
                        occurred_at=repaired_at,
                        reason="修复已提交免OA批次关联关系，取消旧 relation。",
                        history_operation_type="repair_submitted_no_oa_relation_cancel_stale",
                    )
                )

            for stale_relation in self._relation_read_port.active_relations_for_row_ids(row_ids):
                if not self._is_no_oa_relation(stale_relation):
                    continue
                stale_case_id = str(stale_relation.get("case_id") or "").strip()
                if not stale_case_id or stale_case_id == relation_case_id:
                    continue
                stale_source_batch_id = self._relation_source_batch_id(stale_relation)
                if stale_case_id not in stale_case_ids and stale_source_batch_id not in stale_case_ids:
                    continue
                changed_case_ids.extend(
                    self._cancel_no_oa_relation(
                        stale_case_id,
                        occurred_at=repaired_at,
                        reason="修复已提交免OA批次关联关系，取消旧 relation。",
                        history_operation_type="repair_submitted_no_oa_relation_cancel_stale",
                    )
                )

            repaired_relation, repaired_changed_case_ids = self._confirm_no_oa_relation(
                case_id=relation_case_id,
                row_ids=row_ids,
                month_scope=str(batch.get("scope_month") or "all"),
                occurred_at=repaired_at,
                note="修复已提交免OA批次关联关系",
                special_metadata=self._no_oa_relation_metadata(batch),
                evidence=deepcopy(batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}),
                display_tags=self._display_tags(str(batch.get("batch_type") or "")),
                history_operation_type="repair_submitted_no_oa_relation",
            )
            changed_case_ids.extend(repaired_changed_case_ids or [str(repaired_relation.get("case_id") or relation_case_id)])
            self._append_audit(
                operation="repair_submitted_no_oa_relation",
                batch_id=batch_id,
                actor=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                note="repair_stale_pair_relation_snapshot",
                status="submitted",
                relation_case_id=relation_case_id,
            )
            self._merge_legacy_migration_result(
                changed_case_ids=changed_case_ids,
                affected_months=self._batch_affected_months(batch),
                migrated_batch_ids=[batch_id],
            )

    def _consolidated_single_side_submitted_batch(
        self,
        *,
        source_batches: list[dict[str, Any]],
        batch_type: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
        consolidated_at: str,
        scope_month: str,
        account_key: str,
    ) -> dict[str, Any]:
        rows_by_id = {
            self._row_id(row): row
            for row in list(rows or [])
            if isinstance(row, dict) and self._row_id(row)
        }
        sorted_rows = [rows_by_id[row_id] for row_id in sorted(rows_by_id)]
        sorted_row_ids = [self._row_id(row) for row in sorted_rows]
        sorted_source_batches = sorted(
            [batch for batch in list(source_batches or []) if isinstance(batch, dict)],
            key=lambda batch: str(batch.get("batch_id") or ""),
        )
        batch_key = f"legacy_single:{batch_type}:{scope_month}:{account_key}"
        batch_id = self._batch_id(batch_key)
        existing = self._batches.get(batch_id, {})
        source_batch_ids = [
            str(batch.get("batch_id") or "").strip()
            for batch in sorted_source_batches
            if str(batch.get("batch_id") or "").strip()
        ]
        superseded_batch_ids = [source_batch_id for source_batch_id in source_batch_ids if source_batch_id != batch_id]
        source_relation_case_ids = [
            str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
            for batch in sorted_source_batches
            if str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
        ]
        legacy_relations = self._legacy_relations_from_source_batches(sorted_source_batches)
        total_amount = self._legacy_relation_total_amount(batch_type, sorted_rows)
        first_row = sorted_rows[0] if sorted_rows else {}
        evidence = {
            "source": "submitted_no_oa_single_side_batches",
            "consolidation_source": "submitted_no_oa_single_side_batches",
            "consolidated_at": consolidated_at,
            "migration_source": NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
            "source_batch_ids": source_batch_ids,
            "superseded_batch_ids": superseded_batch_ids,
            "source_relation_case_ids": source_relation_case_ids,
            "legacy_relations": legacy_relations,
            "row_count": len(sorted_row_ids),
            "total_amount": self._format_amount(total_amount),
        }
        return self._normalize_batch(
            {
                "batch_id": batch_id,
                "batch_key": batch_key,
                "batch_type": batch_type,
                "batch_label": self._batch_label(batch_type),
                "scope_month": scope_month,
                "account_key": account_key,
                "bank_name": self._bank_name(first_row),
                "account_last4": self._account_last4(first_row),
                "status": "submitted",
                "row_ids": sorted_row_ids,
                "row_count": len(sorted_row_ids),
                "total_amount": self._format_amount(total_amount),
                "tag_counts": {batch_type: len(sorted_row_ids)},
                "direction_counts": self._direction_counts(sorted_rows),
                "relation_case_id": str(existing.get("relation_case_id") or batch_id),
                "source_versions": deepcopy(source_versions),
                "evidence": evidence,
                "category_source": "submitted_no_oa_consolidation",
                "created_by": NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                "created_at": str(existing.get("created_at") or consolidated_at),
                "submitted_by": NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                "submitted_at": str(existing.get("submitted_at") or consolidated_at),
                "withdrawn_by": "",
                "withdrawn_at": "",
                "withdraw_reason": "",
                "version": int(existing.get("version") or 1),
                "updated_at": consolidated_at,
            }
        )

    def _replace_consolidated_no_oa_relation(
        self,
        *,
        batch: dict[str, Any],
        source_batches: list[dict[str, Any]],
        superseded_batch_ids: list[str],
        consolidated_at: str,
    ) -> list[str]:
        relation_case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
        changed_case_ids: list[str] = []
        for source_batch in source_batches:
            source_case_id = str(
                source_batch.get("relation_case_id") or source_batch.get("batch_id") or ""
            ).strip()
            if not source_case_id or source_case_id == relation_case_id:
                continue
            changed_case_ids.extend(
                self._cancel_no_oa_relation(
                    source_case_id,
                    occurred_at=consolidated_at,
                    reason="已提交单边免OA批次归并，取消来源批次关系。",
                    history_operation_type="replace_consolidated_no_oa_relation_cancel_source",
                )
            )

        row_ids = [str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id)]
        relation, relation_changed_case_ids = self._confirm_no_oa_relation(
            case_id=relation_case_id,
            row_ids=row_ids,
            month_scope=str(batch.get("scope_month") or "all"),
            occurred_at=consolidated_at,
            note="已提交单边免OA批次归并",
            special_metadata=self._no_oa_relation_metadata(batch),
            evidence=deepcopy(batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}),
            display_tags=self._display_tags(str(batch.get("batch_type") or "")),
            history_operation_type="replace_consolidated_no_oa_relation",
        )
        changed_case_ids.extend(relation_changed_case_ids or [str(relation.get("case_id") or relation_case_id)])
        relation_batch_id = str(relation.get("special_metadata", {}).get("source_batch_id") or "")
        if relation_batch_id and relation_batch_id != str(batch.get("batch_id") or ""):
            changed_case_ids.extend(superseded_batch_ids)
        return changed_case_ids

    @staticmethod
    def _relation_source_batch_id(relation: dict[str, Any]) -> str:
        special_metadata = relation.get("special_metadata")
        if not isinstance(special_metadata, dict):
            return ""
        return str(special_metadata.get("source_batch_id") or "").strip()

    def _relation_backed_submitted_batches(
        self,
        active_relations: list[dict[str, Any]],
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        source_versions: dict[str, Any],
        *,
        relation_mode: str,
    ) -> dict[str, dict[str, Any]]:
        normalized_relation_mode = self._normalize_relation_mode(relation_mode)
        rows_by_id = {self._row_id(row): row for row in list(rows or []) if self._row_id(row)}
        batches: dict[str, dict[str, Any]] = {}
        for relation in list(active_relations or []):
            if not isinstance(relation, dict) or not self._relation_matches_mode(relation, normalized_relation_mode):
                continue
            case_id = str(relation.get("case_id") or "").strip()
            batch_id = self._relation_source_batch_id(relation) or case_id
            if not batch_id:
                continue
            row_ids = [
                str(row_id).strip()
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            ]
            if not row_ids:
                continue
            relation_metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
            resolved_rows = [rows_by_id[row_id] for row_id in row_ids if row_id in rows_by_id]
            batch_type = str(relation_metadata.get("batch_type") or "").strip()
            if not batch_type and resolved_rows:
                batch_type = self._category_code(resolved_rows[0], categories)
            if not batch_type:
                continue
            scope_month = self._relation_scope_month(relation, resolved_rows)
            total_amount = self._decimal(relation_metadata.get("total_amount"))
            if total_amount is None:
                total_amount = self._legacy_relation_total_amount(batch_type, resolved_rows)
            first_row = resolved_rows[0] if resolved_rows else {}
            evidence = deepcopy(relation.get("evidence") if isinstance(relation.get("evidence"), dict) else {})
            existing_batch = self._batches.get(batch_id)
            row_tag_snapshot_source = relation_metadata.get("row_tag_snapshot")
            if not isinstance(row_tag_snapshot_source, dict) and isinstance(existing_batch, dict):
                row_tag_snapshot_source = existing_batch.get("row_tag_snapshot")
            batch_label = str(relation_metadata.get("batch_label") or NO_OA_BANK_BATCH_LABELS.get(batch_type, batch_type))
            batch = {
                "batch_id": batch_id,
                "batch_key": str(evidence.get("batch_key") or f"relation:{case_id}"),
                "relation_mode": normalized_relation_mode,
                "batch_type": batch_type,
                "batch_label": batch_label,
                "scope_month": scope_month,
                "account_key": self._account_key(first_row) if batch_type != "internal_transfer" else "",
                "bank_name": self._bank_name(first_row),
                "account_last4": self._account_last4(first_row),
                "status": "submitted",
                "row_ids": row_ids,
                "row_count": int(relation_metadata.get("row_count") or len(row_ids)),
                "total_amount": self._format_amount(total_amount),
                "tag_counts": {batch_type: len(row_ids)},
                "direction_counts": self._direction_counts(resolved_rows),
                "row_tag_snapshot": self._normalize_row_tag_snapshot(
                    row_tag_snapshot_source,
                    row_ids=row_ids,
                    batch_type=batch_type,
                    batch_label=batch_label,
                ),
                "relation_case_id": case_id or batch_id,
                "source_versions": deepcopy(source_versions),
                "evidence": {
                    **evidence,
                    "source": f"active_{normalized_relation_mode}_relation",
                    "relation_backed_projection": True,
                    "relation_case_id": case_id,
                },
                "category_source": f"active_{normalized_relation_mode}_relation",
                "created_by": str(relation.get("created_by") or NO_OA_LEGACY_RELATION_MIGRATION_SOURCE),
                "created_at": str(relation.get("created_at") or self._timestamp()),
                "submitted_by": str(relation.get("created_by") or NO_OA_LEGACY_RELATION_MIGRATION_SOURCE),
                "submitted_at": str(relation.get("created_at") or self._timestamp()),
                "withdrawn_by": "",
                "withdrawn_at": "",
                "withdraw_reason": "",
                "version": int(relation_metadata.get("batch_version") or 1),
                "updated_at": str(relation.get("updated_at") or self._timestamp()),
            }
            if batch_type == "internal_transfer":
                batch["income_row_ids"] = [
                    self._row_id(row)
                    for row in resolved_rows
                    if self._direction(row) == "inflow"
                ]
                batch["expense_row_ids"] = [
                    self._row_id(row)
                    for row in resolved_rows
                    if self._direction(row) == "outflow"
                ]
                batch["account_pairs"] = [self._account_payload(row) for row in resolved_rows]
            batches[batch_id] = self._normalize_batch(batch)
        return batches

    def _relation_scope_month(self, relation: dict[str, Any], rows: list[dict[str, Any]]) -> str:
        raw_month = str(relation.get("month_scope") or "").strip()
        if len(raw_month) >= 7 and raw_month[:7] != "all":
            return raw_month[:7]
        months = {self._scope_month(row) for row in rows if self._scope_month(row)}
        if len(months) == 1:
            return next(iter(months))
        return raw_month or "all"

    def _submitted_batch_stale_relation_case_ids(self, batch: dict[str, Any]) -> set[str]:
        evidence = batch.get("evidence")
        normalized_evidence = evidence if isinstance(evidence, dict) else {}
        relation_case_ids = {
            str(case_id).strip()
            for case_id in list(normalized_evidence.get("source_relation_case_ids") or [])
            if str(case_id).strip()
        }
        relation_case_ids.update(
            str(batch_id).strip()
            for batch_id in list(normalized_evidence.get("superseded_batch_ids") or [])
            if str(batch_id).strip()
        )
        relation_case_ids.update(
            str(batch_id).strip()
            for batch_id in list(normalized_evidence.get("source_batch_ids") or [])
            if str(batch_id).strip()
        )
        return relation_case_ids

    def _active_relation_matches_submitted_no_oa_batch(
        self,
        relation: dict[str, Any] | None,
        batch: dict[str, Any],
    ) -> bool:
        if not isinstance(relation, dict) or not self._is_no_oa_relation(relation):
            return False
        batch_id = str(batch.get("batch_id") or "").strip()
        if self._relation_source_batch_id(relation) != batch_id:
            return False
        relation_row_ids = {str(row_id) for row_id in list(relation.get("row_ids") or []) if str(row_id)}
        batch_row_ids = {str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id)}
        return bool(batch_row_ids) and relation_row_ids == batch_row_ids

    def _legacy_relations_from_source_batches(self, source_batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        legacy_relations: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for batch in source_batches:
            evidence = batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}
            relation_payloads = evidence.get("legacy_relations")
            if isinstance(relation_payloads, list):
                for payload in relation_payloads:
                    if not isinstance(payload, dict):
                        continue
                    key = str(payload.get("legacy_case_id") or payload.get("legacy_relation_id") or payload)
                    if key in seen_keys:
                        continue
                    legacy_relations.append(deepcopy(payload))
                    seen_keys.add(key)
                continue

            legacy_case_id = str(evidence.get("legacy_case_id") or "").strip()
            if not legacy_case_id or legacy_case_id in seen_keys:
                continue
            legacy_relations.append(
                {
                    "legacy_relation_mode": str(evidence.get("legacy_relation_mode") or "").strip(),
                    "legacy_case_id": legacy_case_id,
                    "legacy_relation_id": str(evidence.get("legacy_relation_id") or legacy_case_id).strip(),
                    "migration_version": str(evidence.get("migration_version") or "").strip(),
                    "migration_source": str(evidence.get("migration_source") or "").strip(),
                    "migrated_at": str(evidence.get("migrated_at") or "").strip(),
                    "row_ids": [
                        str(row_id)
                        for row_id in list(batch.get("row_ids") or [])
                        if str(row_id)
                    ],
                }
            )
            seen_keys.add(legacy_case_id)
        return legacy_relations

    def _merge_legacy_migration_result(
        self,
        *,
        changed_case_ids: list[str],
        affected_months: list[str],
        migrated_batch_ids: list[str],
    ) -> None:
        result = deepcopy(self._last_legacy_migration_result)
        result["changed"] = True
        result["changed_case_ids"] = sorted(
            {
                *[str(case_id) for case_id in list(result.get("changed_case_ids") or []) if str(case_id)],
                *[str(case_id) for case_id in list(changed_case_ids or []) if str(case_id)],
            }
        )
        result["affected_months"] = sorted(
            {
                *[str(month) for month in list(result.get("affected_months") or []) if str(month)],
                *[str(month) for month in list(affected_months or []) if str(month)],
            }
        )
        result["migrated_batch_ids"] = sorted(
            {
                *[str(batch_id) for batch_id in list(result.get("migrated_batch_ids") or []) if str(batch_id)],
                *[str(batch_id) for batch_id in list(migrated_batch_ids or []) if str(batch_id)],
            }
        )
        result["skipped"] = list(result.get("skipped") or [])
        self._last_legacy_migration_result = result

    def _existing_submitted_batch_for_legacy_relation(
        self,
        *,
        batch_type: str,
        row_ids: list[str],
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        target_row_ids = {str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()}
        if not target_row_ids:
            return None
        for batch in self._batches.values():
            if str(batch.get("status") or "") != "submitted":
                continue
            if str(batch.get("batch_type") or "") != batch_type:
                continue
            batch_row_ids = {
                str(row_id).strip()
                for row_id in list(batch.get("row_ids") or [])
                if str(row_id).strip()
            }
            if batch_row_ids != target_row_ids:
                continue
            if not self._submitted_batch_still_current(batch, rows, categories):
                continue
            return deepcopy(batch)
        return None

    def _merge_legacy_relation_into_submitted_batch(
        self,
        existing_batch: dict[str, Any],
        *,
        migrated_batch: dict[str, Any],
        source_versions: dict[str, Any],
        migrated_at: str,
    ) -> dict[str, Any]:
        existing_evidence = existing_batch.get("evidence") if isinstance(existing_batch.get("evidence"), dict) else {}
        migrated_evidence = migrated_batch.get("evidence") if isinstance(migrated_batch.get("evidence"), dict) else {}
        batch_id = str(existing_batch.get("batch_id") or migrated_batch.get("batch_id") or "").strip()
        relation_case_id = str(existing_batch.get("relation_case_id") or batch_id).strip()
        return self._normalize_batch(
            {
                **deepcopy(migrated_batch),
                **deepcopy(existing_batch),
                "batch_id": batch_id,
                "batch_key": str(existing_batch.get("batch_key") or migrated_batch.get("batch_key") or "").strip(),
                "status": "submitted",
                "relation_case_id": relation_case_id,
                "source_versions": deepcopy(source_versions),
                "evidence": {
                    **deepcopy(existing_evidence),
                    **deepcopy(migrated_evidence),
                    "reused_submitted_batch_id": batch_id,
                },
                "updated_at": migrated_at,
            }
        )

    def _migrated_submitted_batch(
        self,
        *,
        legacy_relation: dict[str, Any],
        batch_type: str,
        rows: list[dict[str, Any]],
        row_ids: list[str],
        source_versions: dict[str, Any],
        migrated_at: str,
    ) -> dict[str, Any]:
        sorted_rows = sorted(rows, key=self._row_id)
        sorted_row_ids = [self._row_id(row) for row in sorted_rows]
        legacy_case_id = str(legacy_relation.get("case_id") or "").strip()
        legacy_mode = str(legacy_relation.get("relation_mode") or "").strip()
        batch_key = f"legacy:{legacy_mode}:{legacy_case_id}:{':'.join(sorted_row_ids)}"
        total_amount = self._legacy_relation_total_amount(batch_type, sorted_rows)
        first_row = sorted_rows[0] if sorted_rows else {}
        legacy_metadata = self._legacy_migration_service.legacy_metadata(legacy_relation, migrated_at=migrated_at)
        evidence = {
            **deepcopy(legacy_relation.get("evidence") if isinstance(legacy_relation.get("evidence"), dict) else {}),
            **legacy_metadata,
            "source": "legacy_active_pair_relation",
            "legacy_special_metadata": deepcopy(
                legacy_relation.get("special_metadata") if isinstance(legacy_relation.get("special_metadata"), dict) else {}
            ),
            "row_count": len(sorted_row_ids),
            "total_amount": self._format_amount(total_amount),
        }
        batch_id = self._batch_id(batch_key)
        existing = self._batches.get(batch_id, {})
        batch = self._normalize_batch(
            {
                "batch_id": batch_id,
                "batch_key": batch_key,
                "batch_type": batch_type,
                "batch_label": self._batch_label(batch_type),
                "scope_month": self._legacy_relation_scope_month(legacy_relation, sorted_rows),
                "account_key": self._account_key(first_row) if batch_type != "internal_transfer" else "",
                "bank_name": self._bank_name(first_row),
                "account_last4": self._account_last4(first_row),
                "status": "submitted",
                "row_ids": sorted_row_ids,
                "row_count": len(sorted_row_ids),
                "total_amount": self._format_amount(total_amount),
                "tag_counts": {batch_type: len(sorted_row_ids)},
                "direction_counts": self._direction_counts(sorted_rows),
                "relation_case_id": str(existing.get("relation_case_id") or batch_id),
                "source_versions": deepcopy(source_versions),
                "evidence": evidence,
                "category_source": "legacy_relation_migration",
                "created_by": str(legacy_relation.get("created_by") or NO_OA_LEGACY_RELATION_MIGRATION_SOURCE),
                "created_at": str(legacy_relation.get("created_at") or migrated_at),
                "submitted_by": NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                "submitted_at": str(existing.get("submitted_at") or migrated_at),
                "withdrawn_by": "",
                "withdrawn_at": "",
                "withdraw_reason": "",
                "version": int(existing.get("version") or 1),
                "updated_at": migrated_at,
            }
        )
        if batch_type == "internal_transfer":
            batch["income_row_ids"] = [self._row_id(row) for row in sorted_rows if self._direction(row) == "inflow"]
            batch["expense_row_ids"] = [self._row_id(row) for row in sorted_rows if self._direction(row) == "outflow"]
            batch["account_pairs"] = [self._account_payload(row) for row in sorted_rows]
        return self._normalize_batch(batch)

    def _migrated_single_side_submitted_batch(
        self,
        *,
        legacy_relations: list[dict[str, Any]],
        batch_type: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any],
        migrated_at: str,
        scope_month: str,
        account_key: str,
    ) -> dict[str, Any]:
        rows_by_id = {
            self._row_id(row): row
            for row in list(rows or [])
            if isinstance(row, dict) and self._row_id(row)
        }
        sorted_rows = [rows_by_id[row_id] for row_id in sorted(rows_by_id)]
        sorted_row_ids = [self._row_id(row) for row in sorted_rows]
        sorted_legacy_relations = sorted(
            [relation for relation in list(legacy_relations or []) if isinstance(relation, dict)],
            key=lambda relation: str(relation.get("case_id") or ""),
        )
        legacy_relation_payloads = [
            self._legacy_relation_payload(legacy_relation, migrated_at=migrated_at)
            for legacy_relation in sorted_legacy_relations
        ]
        total_amount = self._legacy_relation_total_amount(batch_type, sorted_rows)
        first_row = sorted_rows[0] if sorted_rows else {}
        batch_key = f"legacy_single:{batch_type}:{scope_month}:{account_key}"
        batch_id = self._batch_id(batch_key)
        existing = self._batches.get(batch_id, {})
        evidence: dict[str, Any] = {
            "source": "legacy_active_pair_relation",
            "legacy_relations": legacy_relation_payloads,
            "migration_version": legacy_relation_payloads[0].get("migration_version", "")
            if legacy_relation_payloads
            else "",
            "migration_source": NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
            "migrated_at": migrated_at,
            "row_count": len(sorted_row_ids),
            "total_amount": self._format_amount(total_amount),
        }
        if len(sorted_legacy_relations) == 1:
            legacy_relation = sorted_legacy_relations[0]
            legacy_payload = legacy_relation_payloads[0]
            evidence = {
                **deepcopy(legacy_relation.get("evidence") if isinstance(legacy_relation.get("evidence"), dict) else {}),
                **{
                    key: deepcopy(legacy_payload[key])
                    for key in (
                        "legacy_relation_mode",
                        "legacy_case_id",
                        "legacy_relation_id",
                        "migration_version",
                        "migration_source",
                        "migrated_at",
                    )
                    if key in legacy_payload
                },
                **evidence,
                "legacy_special_metadata": deepcopy(
                    legacy_relation.get("special_metadata")
                    if isinstance(legacy_relation.get("special_metadata"), dict)
                    else {}
                ),
            }

        return self._normalize_batch(
            {
                "batch_id": batch_id,
                "batch_key": batch_key,
                "batch_type": batch_type,
                "batch_label": self._batch_label(batch_type),
                "scope_month": scope_month,
                "account_key": account_key,
                "bank_name": self._bank_name(first_row),
                "account_last4": self._account_last4(first_row),
                "status": "submitted",
                "row_ids": sorted_row_ids,
                "row_count": len(sorted_row_ids),
                "total_amount": self._format_amount(total_amount),
                "tag_counts": {batch_type: len(sorted_row_ids)},
                "direction_counts": self._direction_counts(sorted_rows),
                "relation_case_id": str(existing.get("relation_case_id") or batch_id),
                "source_versions": deepcopy(source_versions),
                "evidence": evidence,
                "category_source": "legacy_relation_migration",
                "created_by": NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                "created_at": str(existing.get("created_at") or migrated_at),
                "submitted_by": NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                "submitted_at": str(existing.get("submitted_at") or migrated_at),
                "withdrawn_by": "",
                "withdrawn_at": "",
                "withdraw_reason": "",
                "version": int(existing.get("version") or 1),
                "updated_at": migrated_at,
            }
        )

    def _legacy_relation_payload(self, legacy_relation: dict[str, Any], *, migrated_at: str) -> dict[str, Any]:
        legacy_metadata = self._legacy_migration_service.legacy_metadata(legacy_relation, migrated_at=migrated_at)
        return {
            **legacy_metadata,
            "row_ids": [
                str(row_id).strip()
                for row_id in list(legacy_relation.get("row_ids") or [])
                if str(row_id).strip()
            ],
            "created_by": str(legacy_relation.get("created_by") or ""),
            "created_at": str(legacy_relation.get("created_at") or ""),
            "legacy_special_metadata": deepcopy(
                legacy_relation.get("special_metadata") if isinstance(legacy_relation.get("special_metadata"), dict) else {}
            ),
            "legacy_evidence": deepcopy(
                legacy_relation.get("evidence") if isinstance(legacy_relation.get("evidence"), dict) else {}
            ),
        }

    @classmethod
    def _row_tag_snapshot(
        cls,
        *,
        row_ids: list[str],
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        batch_type: str,
        batch_label: str,
    ) -> dict[str, dict[str, Any]]:
        rows_by_id = {cls._row_id(row): row for row in list(rows or []) if cls._row_id(row)}
        snapshot: dict[str, dict[str, Any]] = {}
        for row_id in [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]:
            row = rows_by_id.get(row_id, {})
            category = categories.get(row_id) if isinstance(categories, dict) else None
            snapshot[row_id] = cls._row_tag_payload(
                row_id=row_id,
                row=row if isinstance(row, dict) else {},
                category=category if isinstance(category, dict) else {},
                fallback_code=batch_type,
                fallback_label=batch_label,
            )
        return snapshot

    @classmethod
    def _normalize_row_tag_snapshot(
        cls,
        value: Any,
        *,
        row_ids: list[str],
        batch_type: str,
        batch_label: str,
    ) -> dict[str, dict[str, Any]]:
        incoming = value if isinstance(value, dict) else {}
        snapshot: dict[str, dict[str, Any]] = {}
        for row_id in [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]:
            row_snapshot = incoming.get(row_id)
            snapshot[row_id] = cls._row_tag_payload(
                row_id=row_id,
                row={},
                category=row_snapshot if isinstance(row_snapshot, dict) else {},
                fallback_code=batch_type,
                fallback_label=batch_label,
            )
        return snapshot

    @classmethod
    def _row_tag_payload(
        cls,
        *,
        row_id: str,
        row: dict[str, Any],
        category: dict[str, Any],
        fallback_code: str,
        fallback_label: str,
    ) -> dict[str, Any]:
        category_code = str(
            category.get("category_code")
            or category.get("effective_category_code")
            or row.get("category_code")
            or row.get("effective_category_code")
            or fallback_code
            or ""
        ).strip()
        category_label = str(
            category.get("category_label")
            or category.get("effective_category_label")
            or row.get("category_label")
            or row.get("effective_category_label")
            or fallback_label
            or category_code
        ).strip()
        primary_label = str(
            category.get("category_primary_label")
            or category.get("effective_category_primary_label")
            or row.get("category_primary_label")
            or row.get("effective_category_primary_label")
            or ""
        ).strip()
        sub_label = str(
            category.get("category_sub_label")
            or category.get("effective_category_sub_label")
            or row.get("category_sub_label")
            or row.get("effective_category_sub_label")
            or ""
        ).strip()
        label_path = cls._string_list(
            category.get("category_label_path")
            or category.get("effective_category_label_path")
            or row.get("category_label_path")
            or row.get("effective_category_label_path")
            or []
        )
        if not label_path:
            label_path = [label for label in [primary_label, sub_label] if label]
        if not label_path and category_label:
            label_path = [category_label]
        return {
            "transaction_id": row_id,
            "category_code": category_code,
            "category_label": category_label,
            "category_primary_label": primary_label,
            "category_sub_label": sub_label,
            "category_label_path": label_path,
            "category_source": str(category.get("category_source") or category.get("source") or row.get("category_source") or row.get("source") or "").strip(),
        }

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        return [str(item).strip() for item in list(value or []) if str(item).strip()] if isinstance(value, list) else []

    def _no_oa_relation_metadata(self, batch: dict[str, Any]) -> dict[str, Any]:
        batch_type = str(batch.get("batch_type") or "")
        evidence = batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}
        return {
            "source": "no_oa_bank_batch",
            "source_batch_id": str(batch.get("batch_id") or ""),
            "batch_version": int(batch.get("version") or 1),
            "batch_type": batch_type,
            "batch_label": str(batch.get("batch_label") or NO_OA_BANK_BATCH_LABELS.get(batch_type, "")),
            "row_count": int(batch.get("row_count") or 0),
            "total_amount": self._format_amount(self._decimal(batch.get("total_amount")) or ZERO),
            "row_tag_snapshot": self._normalize_row_tag_snapshot(
                batch.get("row_tag_snapshot"),
                row_ids=[str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id)],
                batch_type=batch_type,
                batch_label=str(batch.get("batch_label") or NO_OA_BANK_BATCH_LABELS.get(batch_type, "")),
            ),
            "cost_policy": "exclude_all" if batch_type == "internal_transfer" else "normal",
            "withdrawable": True,
            "relation_mode": NO_OA_BANK_BATCH_RELATION_MODE,
            "display_tags": self._display_tags(batch_type),
            **{
                key: deepcopy(evidence[key])
                for key in (
                    "legacy_relation_mode",
                    "legacy_case_id",
                    "legacy_relation_id",
                    "migration_version",
                    "migration_source",
                    "migrated_at",
                    "legacy_relations",
                    "consolidation_source",
                    "consolidated_at",
                    "source_batch_ids",
                    "superseded_batch_ids",
                    "source_relation_case_ids",
                )
                if key in evidence
            },
        }

    def _build_single_side_batches(
        self,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        occupied_row_ids: set[str],
        source_versions: dict[str, Any],
        eligible_batch_types: set[str],
    ) -> dict[str, dict[str, Any]]:
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            row_id = self._row_id(row)
            if not row_id or row_id in occupied_row_ids:
                continue
            batch_type = self._category_code(row, categories)
            if batch_type == "internal_transfer" or batch_type not in eligible_batch_types:
                continue
            scope_month = self._scope_month(row)
            account_key = self._account_key(row)
            if not scope_month or not account_key:
                continue
            grouped.setdefault((batch_type, scope_month, account_key), []).append(row)

        batches: dict[str, dict[str, Any]] = {}
        for (batch_type, scope_month, account_key), group_rows in grouped.items():
            sorted_rows = sorted(group_rows, key=self._row_id)
            base_batch_key = f"single:{batch_type}:{scope_month}:{account_key}"
            batch_key = base_batch_key
            row_ids = [self._row_id(row) for row in sorted_rows]
            evidence = {
                "matched_fields": ["category_code", "account_key", "scope_month"],
                "category_sources": self._category_sources(row_ids, categories),
            }
            existing_base_batch = self._batches.get(self._batch_id(base_batch_key))
            if existing_base_batch and str(existing_base_batch.get("status") or "") == "submitted":
                batch_key = f"{base_batch_key}:incremental:{self._row_set_digest(row_ids)}"
                evidence["incremental_after_submitted_batch_id"] = str(existing_base_batch.get("batch_id") or "")
            batches[self._batch_id(batch_key)] = self._draft_batch(
                batch_key=batch_key,
                batch_type=batch_type,
                scope_month=scope_month,
                account_key=account_key,
                rows=sorted_rows,
                row_ids=row_ids,
                total_amount=sum((self._amount(row) or ZERO for row in sorted_rows), ZERO),
                categories=categories,
                source_versions=source_versions,
                evidence=evidence,
            )
        return batches

    def _build_internal_transfer_batches(
        self,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        occupied_row_ids: set[str],
        source_versions: dict[str, Any],
        eligible_batch_types: set[str],
    ) -> dict[str, dict[str, Any]]:
        if "internal_transfer" not in eligible_batch_types:
            return {}
        internal_rows = [
            row
            for row in rows
            if self._row_id(row)
            and self._row_id(row) not in occupied_row_ids
            and self._category_code(row, categories) == "internal_transfer"
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
            inflows = [row for row in sorted_rows if self._direction(row) == "inflow"]
            outflows = [row for row in sorted_rows if self._direction(row) == "outflow"]
            if not inflows or not outflows:
                batches[self._batch_id(batch_key)] = self._conflict_batch(
                    batch_key=batch_key,
                    scope_month=scope_month,
                    rows=sorted_rows,
                    row_ids=row_ids,
                    total_amount=Decimal(amount_text),
                    categories=categories,
                    source_versions=source_versions,
                    conflict_code="missing_internal_transfer_counterpart",
                    conflict_reason="内部往来收入或支出单边缺失。",
                    evidence={"income_row_ids": [self._row_id(row) for row in inflows], "expense_row_ids": [self._row_id(row) for row in outflows]},
                )
                continue

            if len(inflows) != len(outflows):
                batches[self._batch_id(batch_key)] = self._conflict_batch(
                    batch_key=batch_key,
                    scope_month=scope_month,
                    rows=sorted_rows,
                    row_ids=row_ids,
                    total_amount=Decimal(amount_text),
                    categories=categories,
                    source_versions=source_versions,
                    conflict_code="multiple_internal_transfer_matches",
                    conflict_reason="内部往来存在多解，不能自动形成可提交批次。",
                    evidence={"income_count": len(inflows), "expense_count": len(outflows)},
                )
                continue

            matched_pairs = self._nearest_internal_transfer_pairs(outflows, inflows)
            if len(matched_pairs) != len(outflows):
                batches[self._batch_id(batch_key)] = self._conflict_batch(
                    batch_key=batch_key,
                    scope_month=scope_month,
                    rows=sorted_rows,
                    row_ids=row_ids,
                    total_amount=Decimal(amount_text),
                    categories=categories,
                    source_versions=source_versions,
                    conflict_code="multiple_internal_transfer_matches",
                    conflict_reason="内部往来存在多解，不能自动形成可提交批次。",
                    evidence={
                        "income_count": len(inflows),
                        "expense_count": len(outflows),
                        "matched_pair_count": len(matched_pairs),
                        "match_window_hours": 48,
                    },
                )
                continue

            for outflow, inflow, time_delta_seconds in matched_pairs:
                pair_rows = sorted([outflow, inflow], key=self._row_id)
                pair_row_ids = [self._row_id(row) for row in pair_rows]
                pair_batch_key = f"internal_transfer:{scope_month}:{amount_text}:{':'.join(pair_row_ids)}"
                evidence = {
                    "rule_code": "internal_transfer_pair",
                    "match_window_hours": 48,
                    "matched_fields": ["amount", "direction", "account", "transaction_at"],
                    "time_delta_seconds": time_delta_seconds,
                    "source_group_row_ids": row_ids,
                }
                batch = self._draft_batch(
                    batch_key=pair_batch_key,
                    batch_type="internal_transfer",
                    scope_month=scope_month,
                    account_key="",
                    rows=pair_rows,
                    row_ids=pair_row_ids,
                    total_amount=Decimal(amount_text),
                    categories=categories,
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

    def _nearest_internal_transfer_pairs(
        self,
        outflows: list[dict[str, Any]],
        inflows: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], dict[str, Any], int]]:
        candidates: list[tuple[int, str, str, dict[str, Any], dict[str, Any]]] = []
        for outflow in outflows:
            outflow_time = self._row_time(outflow)
            if outflow_time is None:
                continue
            for inflow in inflows:
                if self._account_key(outflow) == self._account_key(inflow):
                    continue
                inflow_time = self._row_time(inflow)
                if inflow_time is None:
                    continue
                delta = abs(inflow_time - outflow_time)
                if delta > INTERNAL_TRANSFER_MATCH_WINDOW:
                    continue
                candidates.append(
                    (
                        int(delta.total_seconds()),
                        self._row_id(outflow),
                        self._row_id(inflow),
                        outflow,
                        inflow,
                    )
                )

        pairs: list[tuple[dict[str, Any], dict[str, Any], int]] = []
        used_outflow_ids: set[str] = set()
        used_inflow_ids: set[str] = set()
        for delta_seconds, outflow_id, inflow_id, outflow, inflow in sorted(candidates):
            if outflow_id in used_outflow_ids or inflow_id in used_inflow_ids:
                continue
            used_outflow_ids.add(outflow_id)
            used_inflow_ids.add(inflow_id)
            pairs.append((outflow, inflow, delta_seconds))
        return pairs

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
        categories: dict[str, dict[str, Any]],
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
                "batch_label": self._batch_label(batch_type),
                "scope_month": scope_month,
                "account_key": account_key,
                "bank_name": self._bank_name(first_row),
                "account_last4": self._account_last4(first_row),
                "status": "draft",
                "row_ids": row_ids,
                "row_count": len(row_ids),
                "total_amount": self._format_amount(total_amount),
                "tag_counts": {batch_type: len(row_ids)},
                "direction_counts": self._direction_counts(rows),
                "row_tag_snapshot": self._row_tag_snapshot(
                    row_ids=row_ids,
                    rows=rows,
                    categories=categories,
                    batch_type=batch_type,
                    batch_label=self._batch_label(batch_type),
                ),
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
        categories: dict[str, dict[str, Any]],
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
            categories=categories,
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
        for row_id in list(batch.get("row_ids") or []):
            if rows_by_id.get(str(row_id)) is None:
                return False
        return True

    def _batch_affected_months(self, batch: dict[str, Any]) -> list[str]:
        months = {str(batch.get("scope_month") or "").strip()}
        return sorted(month for month in months if month)

    def _legacy_relation_total_amount(self, batch_type: str, rows: list[dict[str, Any]]) -> Decimal:
        amounts = [amount for row in rows if (amount := self._amount(row)) is not None]
        if not amounts:
            return ZERO
        if batch_type == "internal_transfer":
            return max(amounts)
        return sum(amounts, ZERO)

    def _legacy_relation_scope_month(self, legacy_relation: dict[str, Any], rows: list[dict[str, Any]]) -> str:
        month_scope = str(legacy_relation.get("month_scope") or "").strip()
        if month_scope and month_scope != "all":
            return month_scope
        months = {self._scope_month(row) for row in rows if self._scope_month(row)}
        if len(months) == 1:
            return next(iter(months))
        return month_scope or "all"

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

    @classmethod
    def _active_no_oa_relation_row_ids(cls, active_relations: list[dict[str, Any]]) -> set[str]:
        return cls._active_relation_row_ids(
            [
                relation
                for relation in list(active_relations or [])
                if isinstance(relation, dict) and cls._is_no_oa_relation(relation)
            ]
        )

    @staticmethod
    def _normalize_relation_mode(relation_mode: str | None) -> str:
        return str(relation_mode or NO_OA_BANK_BATCH_RELATION_MODE).strip() or NO_OA_BANK_BATCH_RELATION_MODE

    @classmethod
    def _relation_mode_from_relation(cls, relation: dict[str, Any]) -> str:
        direct_mode = str(relation.get("relation_mode") or "").strip()
        if direct_mode:
            return cls._normalize_relation_mode(direct_mode)
        special_metadata = relation.get("special_metadata")
        if isinstance(special_metadata, dict):
            metadata_mode = str(special_metadata.get("relation_mode") or special_metadata.get("source") or "").strip()
            if metadata_mode:
                return cls._normalize_relation_mode(metadata_mode)
        return NO_OA_BANK_BATCH_RELATION_MODE

    @classmethod
    def _relation_matches_mode(cls, relation: dict[str, Any], relation_mode: str) -> bool:
        return cls._relation_mode_from_relation(relation) == cls._normalize_relation_mode(relation_mode)

    @classmethod
    def _is_no_oa_relation(cls, relation: dict[str, Any]) -> bool:
        return cls._relation_matches_mode(relation, NO_OA_BANK_BATCH_RELATION_MODE)

    @classmethod
    def _batch_relation_mode(cls, batch: dict[str, Any]) -> str:
        return cls._normalize_relation_mode(str(batch.get("relation_mode") or ""))

    @classmethod
    def _assign_relation_mode(cls, batches: dict[str, dict[str, Any]], relation_mode: str) -> None:
        normalized_relation_mode = cls._normalize_relation_mode(relation_mode)
        for batch in batches.values():
            if isinstance(batch, dict):
                batch["relation_mode"] = normalized_relation_mode

    @staticmethod
    def _normalize_batch(batch: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(batch)
        normalized["batch_id"] = str(normalized.get("batch_id") or "")
        normalized["batch_key"] = str(normalized.get("batch_key") or normalized["batch_id"])
        normalized["relation_mode"] = NoOaBankBatchService._batch_relation_mode(normalized)
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
        tag_counts = normalized.get("tag_counts")
        normalized["tag_counts"] = (
            {str(key): int(value or 0) for key, value in tag_counts.items() if str(key)}
            if isinstance(tag_counts, dict)
            else {normalized["batch_type"]: normalized["row_count"]} if normalized["batch_type"] else {}
        )
        direction_counts = normalized.get("direction_counts")
        normalized["direction_counts"] = (
            {
                "income": int(direction_counts.get("income") or direction_counts.get("inflow") or 0),
                "expense": int(direction_counts.get("expense") or direction_counts.get("outflow") or 0),
            }
            if isinstance(direction_counts, dict)
            else {"income": 0, "expense": normalized["row_count"]}
        )
        normalized["row_tag_snapshot"] = NoOaBankBatchService._normalize_row_tag_snapshot(
            normalized.get("row_tag_snapshot"),
            row_ids=normalized["row_ids"],
            batch_type=normalized["batch_type"],
            batch_label=normalized["batch_label"],
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
        normalized["status_bucket"] = NoOaBankBatchService._status_bucket(normalized["status"])
        normalized["can_submit"] = normalized["status"] == "draft"
        normalized["can_withdraw"] = False
        normalized["blocked_reason"] = NoOaBankBatchService._blocked_reason(normalized)
        return normalized

    def _enrich_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        enriched = self._normalize_batch(batch)
        has_active_relation = self._has_active_relation_for_batch(enriched)
        if enriched["status"] == "stale" and has_active_relation:
            enriched["status"] = "submitted"
            enriched["status_bucket"] = "submitted"
            enriched["relation_backed_status"] = "stale"
        enriched["can_withdraw"] = enriched["status"] == "submitted" or (
            enriched["status"] == "stale" and has_active_relation
        )
        enriched["blocked_reason"] = self._blocked_reason(enriched)
        return deepcopy(enriched)

    def _has_active_relation_for_batch(self, batch: dict[str, Any]) -> bool:
        relation_case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
        relation = self._relation_read_port.active_relation_by_case_id(relation_case_id)
        if not isinstance(relation, dict):
            return False
        return self._relation_matches_mode(relation, self._batch_relation_mode(batch))

    def _has_active_no_oa_relation(self, batch: dict[str, Any]) -> bool:
        relation_case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
        relation = self._relation_read_port.active_relation_by_case_id(relation_case_id)
        return isinstance(relation, dict) and self._is_no_oa_relation(relation)

    @staticmethod
    def _status_bucket(status: str) -> str:
        return NO_OA_BANK_BATCH_STATUS_BUCKETS.get(str(status or "").strip(), "unsubmitted")

    @staticmethod
    def _blocked_reason(batch: dict[str, Any]) -> str:
        status = str(batch.get("status") or "").strip()
        if status == "draft":
            return ""
        if status == "conflict":
            return str(batch.get("conflict_reason") or "批次存在冲突，不能提交。")
        if status == "stale":
            return "源流水或分类已变化，需要复核后处理。"
        if status == "submitted":
            return "批次已提交，不能重复提交。"
        if status == "superseded":
            return "批次已归并到新的免OA批次。"
        if status == "withdrawn":
            return "批次已撤回，不能提交。"
        return "当前批次状态不能提交。"

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
            if "category_code" in category:
                value = category.get("category_code")
                return str(value).strip() if value is not None else ""
            if "effective_category_code" in category:
                value = category.get("effective_category_code")
                return str(value).strip() if value is not None else ""
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
    def _direction_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        counts = {"income": 0, "expense": 0}
        for row in rows:
            direction = NoOaBankBatchService._direction(row)
            if direction == "inflow":
                counts["income"] += 1
            elif direction == "outflow":
                counts["expense"] += 1
        return counts

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
    def _batch_label(batch_type: str) -> str:
        return NO_OA_BANK_BATCH_LABELS.get(str(batch_type or ""), str(batch_type or ""))

    @staticmethod
    def _eligible_batch_types(values: set[str] | list[str] | tuple[str, ...] | None) -> set[str]:
        if values is None:
            return set(SUPPORTED_BATCH_TYPES)
        return {str(value).strip() for value in values if str(value).strip()}

    @staticmethod
    def _is_month_scope_key(scope_key: str) -> bool:
        text = str(scope_key or "").strip()
        return len(text) == 7 and text[4:5] == "-" and text[:4].isdigit() and text[5:].isdigit()

    @staticmethod
    def _batch_scope_month(batch: dict[str, Any]) -> str:
        return str(batch.get("scope_month") or batch.get("month") or "").strip()

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
    def _row_set_digest(row_ids: list[str]) -> str:
        normalized_row_ids = sorted(str(row_id) for row_id in row_ids if str(row_id))
        return hashlib.sha256("|".join(normalized_row_ids).encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
