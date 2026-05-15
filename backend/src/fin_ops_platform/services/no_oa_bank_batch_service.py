from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
from typing import Any

from fin_ops_platform.services.no_oa_legacy_relation_migration_service import NoOaLegacyRelationMigrationService
from fin_ops_platform.services.no_oa_managed_rule_policy import (
    NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
    NO_OA_MANAGED_LABELS,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


NO_OA_BANK_BATCH_SCHEMA_VERSION = "2026-05-no-oa-bank-batch-v1"
NO_OA_BANK_BATCH_RELATION_MODE = "no_oa_bank_batch"
INTERNAL_TRANSFER_MATCH_WINDOW = timedelta(hours=48)
CENT = Decimal("0.01")
ZERO = Decimal("0.00")

NO_OA_BANK_BATCH_LABELS = dict(NO_OA_MANAGED_LABELS)
SINGLE_SIDE_BATCH_TYPES = {"fee", "salary", "holiday_bonus", "bonus"}
SUPPORTED_BATCH_TYPES = {*SINGLE_SIDE_BATCH_TYPES, "internal_transfer"}
NO_OA_BANK_BATCH_STATUS_BUCKETS = {
    "draft": "unsubmitted",
    "conflict": "unsubmitted",
    "stale": "unsubmitted",
    "submitted": "submitted",
    "superseded": "superseded",
    "withdrawn": "withdrawn",
}


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
        self._legacy_migration_service = NoOaLegacyRelationMigrationService(
            pair_relation_service=self._pair_relation_service
        )
        self._last_legacy_migration_result: dict[str, Any] = {
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
        source_version_payload = dict(source_versions or {})

        self._migrate_legacy_active_relations(
            rows=rows,
            categories=categories,
            active_relations=active_relations,
            source_versions=source_version_payload,
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
        current_active_relations = self._pair_relation_service.list_active_relations()
        effective_active_relations = self._effective_active_relations_after_migration(active_relations, current_active_relations)
        occupied_row_ids = self._active_relation_row_ids(effective_active_relations)
        no_oa_occupied_row_ids = self._active_no_oa_relation_row_ids(effective_active_relations)

        generated: dict[str, dict[str, Any]] = {}
        generated.update(self._build_single_side_batches(rows, categories, occupied_row_ids, source_version_payload))
        generated.update(
            self._build_internal_transfer_batches(
                rows,
                categories,
                occupied_row_ids,
                no_oa_occupied_row_ids,
                source_version_payload,
            )
        )

        submitted_or_withdrawn = {
            batch_id: deepcopy(batch)
            for batch_id, batch in self._batches.items()
            if batch.get("status") in {"submitted", "withdrawn", "stale", "superseded"}
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

        self._batches = {batch_id: self._normalize_batch(batch) for batch_id, batch in generated.items()}
        return self.list_batches()

    def last_legacy_migration_result(self) -> dict[str, Any]:
        return deepcopy(self._last_legacy_migration_result)

    def _effective_active_relations_after_migration(
        self,
        original_active_relations: list[dict[str, Any]],
        current_active_relations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        current_case_ids = {
            str(relation.get("case_id") or "").strip()
            for relation in list(current_active_relations or [])
            if isinstance(relation, dict)
        }
        migrated_case_ids = {
            str(case_id).strip()
            for case_id in list(self._last_legacy_migration_result.get("changed_case_ids") or [])
            if str(case_id).strip()
        }
        effective_relations = [
            deepcopy(relation)
            for relation in list(current_active_relations or [])
            if isinstance(relation, dict)
        ]
        for relation in list(original_active_relations or []):
            if not isinstance(relation, dict):
                continue
            case_id = str(relation.get("case_id") or "").strip()
            if case_id and (case_id in current_case_ids or case_id in migrated_case_ids):
                continue
            effective_relations.append(deepcopy(relation))
        return effective_relations

    def list_batches(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        resolved_filters = filters if isinstance(filters, dict) else {}
        batches = [
            batch
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
        bucket = str(resolved_filters.get("bucket") or "").strip()
        if bucket and bucket != "all":
            batches = [batch for batch in batches if self._status_bucket(str(batch.get("status") or "")) == bucket]
        return [
            self._enrich_batch(batch)
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
        if batch.get("status") not in {"submitted", "stale"}:
            raise ValueError("only_submitted_no_oa_bank_batch_can_be_withdrawn")
        if batch.get("status") == "stale" and not self._has_active_no_oa_relation(batch):
            raise ValueError("stale_no_oa_bank_batch_has_no_active_relation_to_withdraw")
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

    def _migrate_legacy_active_relations(
        self,
        *,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
        active_relations: list[dict[str, Any]],
        source_versions: dict[str, Any],
    ) -> None:
        result: dict[str, Any] = {
            "changed": False,
            "changed_case_ids": [],
            "affected_months": [],
            "migrated_batch_ids": [],
            "skipped": [],
        }
        rows_by_id = {self._row_id(row): row for row in rows if self._row_id(row)}
        single_side_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for legacy_relation in self._legacy_migration_service.active_legacy_relations(active_relations):
            batch_type = self._legacy_migration_service.batch_type_for_relation(legacy_relation)
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
                cancelled = self._pair_relation_service.cancel_relation(relation_case_id, cancelled_at=self._timestamp())
                if cancelled is not None:
                    result["changed"] = True
                    result["changed_case_ids"].append(relation_case_id)
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
            batch = self._migrated_submitted_batch(
                legacy_relation=legacy_relation,
                batch_type=batch_type,
                rows=resolved_rows,
                row_ids=row_ids,
                source_versions=source_versions,
                migrated_at=migrated_at,
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

    def _prune_submitted_single_side_batches_for_category_drift(
        self,
        *,
        rows: list[dict[str, Any]],
        categories: dict[str, dict[str, Any]],
    ) -> None:
        rows_by_id = {self._row_id(row): row for row in rows if self._row_id(row)}
        for batch_id, batch in list(self._batches.items()):
            batch_type = str(batch.get("batch_type") or "").strip()
            if str(batch.get("status") or "") != "submitted" or batch_type not in SINGLE_SIDE_BATCH_TYPES:
                continue
            original_row_ids = [
                str(row_id).strip()
                for row_id in list(batch.get("row_ids") or [])
                if str(row_id).strip()
            ]
            if not original_row_ids:
                continue
            current_rows = [
                rows_by_id[row_id]
                for row_id in original_row_ids
                if row_id in rows_by_id and self._category_code(rows_by_id[row_id], categories) == batch_type
            ]
            current_row_ids = [self._row_id(row) for row in current_rows]
            if current_row_ids == original_row_ids:
                continue

            pruned_row_ids = [row_id for row_id in original_row_ids if row_id not in set(current_row_ids)]
            repaired_at = self._timestamp()
            relation_case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
            changed_case_ids: list[str] = []
            if current_row_ids:
                updated_batch = deepcopy(batch)
                total_amount = sum((self._amount(row) or ZERO for row in current_rows), ZERO)
                updated_batch.update(
                    {
                        "row_ids": current_row_ids,
                        "row_count": len(current_row_ids),
                        "total_amount": self._format_amount(total_amount),
                        "tag_counts": {batch_type: len(current_row_ids)},
                        "direction_counts": self._direction_counts(current_rows),
                        "version": int(updated_batch.get("version") or 1) + 1,
                        "updated_at": repaired_at,
                    }
                )
                evidence = deepcopy(updated_batch.get("evidence") if isinstance(updated_batch.get("evidence"), dict) else {})
                evidence["category_drift_pruned_row_ids"] = sorted(
                    {
                        *[str(row_id) for row_id in list(evidence.get("category_drift_pruned_row_ids") or []) if str(row_id)],
                        *pruned_row_ids,
                    }
                )
                evidence["category_drift_pruned_at"] = repaired_at
                updated_batch["evidence"] = evidence
                self._batches[batch_id] = self._normalize_batch(updated_batch)
                relation = self._pair_relation_service.create_active_relation(
                    case_id=relation_case_id,
                    row_ids=current_row_ids,
                    row_types=["bank" for _ in current_row_ids],
                    relation_mode=NO_OA_BANK_BATCH_RELATION_MODE,
                    created_by=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                    month_scope=str(updated_batch.get("scope_month") or "all"),
                    created_at=repaired_at,
                    note="按当前流水分类剔除免OA批次明细",
                    special_metadata=self._no_oa_relation_metadata(updated_batch),
                    evidence=deepcopy(evidence),
                    display_tags=self._display_tags(batch_type),
                )
                changed_case_ids.append(str(relation.get("case_id") or relation_case_id))
                self._append_audit(
                    operation="prune_submitted_no_oa_batch_rows",
                    batch_id=batch_id,
                    actor=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                    note=",".join(pruned_row_ids),
                    status="submitted",
                    relation_case_id=relation_case_id,
                )
                self._merge_legacy_migration_result(
                    changed_case_ids=changed_case_ids,
                    affected_months=self._batch_affected_months(updated_batch),
                    migrated_batch_ids=[batch_id],
                )
                continue

            cancelled = self._pair_relation_service.cancel_relation(relation_case_id, cancelled_at=repaired_at)
            if cancelled is not None:
                changed_case_ids.append(relation_case_id)
            self._append_audit(
                operation="clear_submitted_no_oa_batch_relation_after_category_drift",
                batch_id=batch_id,
                actor=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                note=",".join(pruned_row_ids),
                status="stale",
                relation_case_id=relation_case_id,
            )
            self._merge_legacy_migration_result(
                changed_case_ids=changed_case_ids,
                affected_months=self._batch_affected_months(batch),
                migrated_batch_ids=[batch_id],
            )

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

            active_relation = self._pair_relation_service.get_active_relation_by_case_id(relation_case_id)
            if self._active_relation_matches_submitted_no_oa_batch(active_relation, batch):
                continue

            repaired_at = self._timestamp()
            changed_case_ids: list[str] = []
            stale_case_ids = self._submitted_batch_stale_relation_case_ids(batch)
            for stale_case_id in stale_case_ids:
                if stale_case_id == relation_case_id:
                    continue
                cancelled = self._pair_relation_service.cancel_relation(stale_case_id, cancelled_at=repaired_at)
                if cancelled is not None:
                    changed_case_ids.append(stale_case_id)

            for stale_relation in self._pair_relation_service.active_relations_for_row_ids(row_ids):
                if not self._is_no_oa_relation(stale_relation):
                    continue
                stale_case_id = str(stale_relation.get("case_id") or "").strip()
                if not stale_case_id or stale_case_id == relation_case_id:
                    continue
                stale_source_batch_id = self._relation_source_batch_id(stale_relation)
                if stale_case_id not in stale_case_ids and stale_source_batch_id not in stale_case_ids:
                    continue
                cancelled = self._pair_relation_service.cancel_relation(stale_case_id, cancelled_at=repaired_at)
                if cancelled is not None:
                    changed_case_ids.append(stale_case_id)

            repaired_relation = self._pair_relation_service.create_active_relation(
                case_id=relation_case_id,
                row_ids=row_ids,
                row_types=["bank" for _ in row_ids],
                relation_mode=NO_OA_BANK_BATCH_RELATION_MODE,
                created_by=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                month_scope=str(batch.get("scope_month") or "all"),
                created_at=repaired_at,
                note="修复已提交免OA批次关联关系",
                special_metadata=self._no_oa_relation_metadata(batch),
                evidence=deepcopy(batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}),
                display_tags=self._display_tags(str(batch.get("batch_type") or "")),
            )
            changed_case_ids.append(str(repaired_relation.get("case_id") or relation_case_id))
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
                "batch_label": NO_OA_BANK_BATCH_LABELS[batch_type],
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
            cancelled = self._pair_relation_service.cancel_relation(source_case_id, cancelled_at=consolidated_at)
            if cancelled is not None:
                changed_case_ids.append(source_case_id)

        row_ids = [str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id)]
        relation = self._pair_relation_service.create_active_relation(
            case_id=relation_case_id,
            row_ids=row_ids,
            row_types=["bank" for _ in row_ids],
            relation_mode=NO_OA_BANK_BATCH_RELATION_MODE,
            created_by=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
            month_scope=str(batch.get("scope_month") or "all"),
            created_at=consolidated_at,
            note="已提交单边免OA批次归并",
            special_metadata=self._no_oa_relation_metadata(batch),
            evidence=deepcopy(batch.get("evidence") if isinstance(batch.get("evidence"), dict) else {}),
            display_tags=self._display_tags(str(batch.get("batch_type") or "")),
        )
        changed_case_ids.append(str(relation.get("case_id") or relation_case_id))
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
                "batch_label": NO_OA_BANK_BATCH_LABELS[batch_type],
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
                "batch_label": NO_OA_BANK_BATCH_LABELS[batch_type],
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
        no_oa_occupied_row_ids: set[str],
        source_versions: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        internal_rows = [
            row
            for row in rows
            if self._row_id(row)
            and self._row_id(row) not in no_oa_occupied_row_ids
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
                "tag_counts": {batch_type: len(row_ids)},
                "direction_counts": self._direction_counts(rows),
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
    def _is_no_oa_relation(relation: dict[str, Any]) -> bool:
        if str(relation.get("relation_mode") or "").strip() == NO_OA_BANK_BATCH_RELATION_MODE:
            return True
        special_metadata = relation.get("special_metadata")
        return (
            isinstance(special_metadata, dict)
            and str(special_metadata.get("relation_mode") or special_metadata.get("source") or "").strip()
            in {NO_OA_BANK_BATCH_RELATION_MODE, "no_oa_bank_batch"}
        )

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
        enriched["can_withdraw"] = enriched["status"] == "submitted" or (
            enriched["status"] == "stale" and self._has_active_no_oa_relation(enriched)
        )
        enriched["blocked_reason"] = self._blocked_reason(enriched)
        return deepcopy(enriched)

    def _has_active_no_oa_relation(self, batch: dict[str, Any]) -> bool:
        relation_case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
        relation = self._pair_relation_service.get_active_relation_by_case_id(relation_case_id)
        if not isinstance(relation, dict):
            return False
        if str(relation.get("relation_mode") or "").strip() == NO_OA_BANK_BATCH_RELATION_MODE:
            return True
        special_metadata = relation.get("special_metadata")
        return (
            isinstance(special_metadata, dict)
            and str(special_metadata.get("relation_mode") or special_metadata.get("source") or "").strip()
            in {NO_OA_BANK_BATCH_RELATION_MODE, "no_oa_bank_batch"}
        )

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
