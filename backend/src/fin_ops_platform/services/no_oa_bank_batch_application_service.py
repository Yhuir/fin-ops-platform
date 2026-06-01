from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
import re
from typing import Any, Callable

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_transaction_category_service import (
    BANK_TRANSACTION_CATEGORY_LABELS,
    BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION,
    BankTransactionCategoryService,
)
from fin_ops_platform.services.no_oa_bank_batch_service import (
    NO_OA_BANK_BATCH_SCHEMA_VERSION,
    NoOaBankBatchService,
)
from fin_ops_platform.services.no_oa_managed_rule_policy import NO_OA_MANAGED_LABELS
from fin_ops_platform.services.read_model_freshness import source_version_mismatch_reasons
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService


SEARCH_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class NoOaBankBatchPersistenceError(RuntimeError):
    error_code = "no_oa_bank_batch_persistence_failed"


class NoOaBankBatchApplicationService:
    def __init__(
        self,
        *,
        import_service: Any,
        effective_category_provider: Any,
        no_oa_bank_batch_service: NoOaBankBatchService,
        app_settings_service: AppSettingsService,
        bank_transaction_category_service: BankTransactionCategoryService,
        pair_relation_service: WorkbenchPairRelationService,
        workbench_read_model_service: WorkbenchReadModelService,
        state_store: Any | None,
        tag_selection_service: Any | None = None,
        workbench_sql_read_repository: Any | None = None,
        workbench_matching_source_versions_provider: Callable[[], dict[str, object]] | None = None,
        bank_transaction_category_affected_months_provider: Callable[[list[str]], list[str]] | None = None,
        execute_derived_data_lifecycle_event: Callable[..., Any] | None = None,
        expand_workbench_read_model_scope_keys_for_base_scopes: Callable[[list[str]], list[str]] | None = None,
        search_cache_clearer: Callable[[], Any] | None = None,
        queue_repository: Any | None = None,
    ) -> None:
        self._import_service = import_service
        self._effective_category_provider = effective_category_provider
        self._no_oa_bank_batch_service = no_oa_bank_batch_service
        self._tag_selection_service = tag_selection_service
        self._app_settings_service = app_settings_service
        self._bank_transaction_category_service = bank_transaction_category_service
        self._pair_relation_service = pair_relation_service
        self._workbench_read_model_service = workbench_read_model_service
        self._state_store = state_store
        self._workbench_sql_read_repository = workbench_sql_read_repository
        self._workbench_matching_source_versions_provider = workbench_matching_source_versions_provider or (lambda: {})
        self._bank_transaction_category_affected_months_provider = (
            bank_transaction_category_affected_months_provider or (lambda _row_ids: [])
        )
        self._execute_derived_data_lifecycle_event = execute_derived_data_lifecycle_event or (lambda *_args, **_kwargs: None)
        self._expand_workbench_read_model_scope_keys_for_base_scopes = (
            expand_workbench_read_model_scope_keys_for_base_scopes or (lambda scope_keys: scope_keys)
        )
        self._search_cache_clearer = search_cache_clearer or (lambda: None)
        self._queue_repository = queue_repository

    def list_batches_payload(self, query: dict[str, list[str]]) -> dict[str, object]:
        filters = {
            "month": query.get("month", [""])[0],
            "type": query.get("type", [""])[0],
            "status": query.get("status", [""])[0],
            "bucket": query.get("bucket", [""])[0],
            "account_key": query.get("account_key", [""])[0],
        }
        summary_filters = {
            "month": filters["month"],
            "account_key": filters["account_key"],
        }
        list_read_model_batches = getattr(self._workbench_sql_read_repository, "list_no_oa_bank_batch_rows", None)
        if callable(list_read_model_batches):
            summary_read_model_batches = list_read_model_batches(summary_filters)
            read_model_batches = list_read_model_batches(filters)
            if summary_read_model_batches is not None and read_model_batches is not None:
                stale_reasons = self.no_oa_bank_batch_stale_reasons(summary_read_model_batches + read_model_batches)
                if stale_reasons:
                    return {
                        "summary": self.summary(summary_read_model_batches),
                        "batches": self.resolve_labels(read_model_batches),
                        "read_model_status": "stale",
                        "read_model_stale_reasons": stale_reasons,
                        "refresh_enqueued": self.enqueue_background_refresh(["all"], reason="api_no_oa_source_versions_stale"),
                        "refresh_reason": "api_no_oa_source_versions_stale",
                    }
                return {
                    "summary": self.summary(summary_read_model_batches),
                    "batches": self.resolve_labels(read_model_batches),
                    "read_model_status": "fresh",
                }
        self.refresh_batches()
        summary_batches = self._no_oa_bank_batch_service.list_batches(summary_filters)
        batches = self._no_oa_bank_batch_service.list_batches(filters)
        return {
            "summary": self.summary(summary_batches),
            "batches": self.resolve_labels(batches),
        }

    def tag_selection_payload(self) -> dict[str, Any]:
        if self._tag_selection_service is not None:
            return self._tag_selection_service.get_tag_selection_payload()
        return self._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()

    def update_tag_selection(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        if self._tag_selection_service is not None:
            return self._tag_selection_service.update_tag_selection(payload, actor_id=actor_id)
        result = self._app_settings_service.update_no_oa_bank_batch_tag_selection(payload, actor_id=actor_id)
        self.enqueue_background_refresh(["all"], reason="no_oa_bank_batch_tag_selection_changed")
        self.after_mutation(["all"], changed_case_ids=[], persist=False)
        return result

    def detail_payload(self, batch_id: str) -> dict[str, object]:
        bank_rows, categories_by_transaction_id = self.refresh_batches()
        rows_by_id = {str(row.get("id")): row for row in bank_rows if str(row.get("id") or "").strip()}
        batch = self._no_oa_bank_batch_service.get_batch(batch_id)
        row_ids = [str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id).strip()]
        return {
            "batch": self.resolve_labels([batch])[0],
            "rows": self.detail_rows(row_ids, rows_by_id, categories_by_transaction_id),
            "tag_counts": batch.get("tag_counts") if isinstance(batch.get("tag_counts"), dict) else {},
            "direction_counts": batch.get("direction_counts") if isinstance(batch.get("direction_counts"), dict) else {},
            "categories_by_transaction_id": {
                row_id: categories_by_transaction_id.get(row_id, {})
                for row_id in row_ids
            },
        }

    def submit_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        note: str | None,
        persist: bool = True,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._no_oa_bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_service.snapshot()
        try:
            self.refresh_batches()
            batch = self._no_oa_bank_batch_service.submit_batch(
                batch_id,
                actor=actor,
                expected_version=expected_version,
                note=note,
            )
            result = self._mutation_result(batch, status="submitted", persist=persist)
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        return result

    def submit_selected_rows(
        self,
        *,
        row_ids: list[str],
        actor: str,
        note: str | None,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._no_oa_bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_service.snapshot()
        try:
            bank_rows, categories_by_transaction_id = self.refresh_batches()
            self._validate_internal_transfer_selection(
                bank_rows=bank_rows,
                categories_by_transaction_id=categories_by_transaction_id,
                row_ids=row_ids,
            )
            batch = self._no_oa_bank_batch_service.submit_selected_rows(
                bank_rows=bank_rows,
                categories_by_transaction_id=categories_by_transaction_id,
                active_relations=self._pair_relation_service.list_active_relations(),
                source_versions=self.no_oa_bank_batch_source_versions(),
                eligible_batch_types=self.selected_tag_codes(),
                row_ids=row_ids,
                actor=actor,
                note=note,
            )
            result = self._mutation_result(batch, status="submitted", persist=True)
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        return result

    def withdraw_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        reason: str | None,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._no_oa_bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_service.snapshot()
        try:
            batch = self._no_oa_bank_batch_service.withdraw_batch(
                batch_id,
                actor=actor,
                expected_version=expected_version,
                reason=reason,
            )
            result = self._mutation_result(batch, status="withdrawn", persist=True)
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        return result

    def refresh_batches(self) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
        bank_rows = self.no_oa_bank_transaction_rows()
        categories_by_transaction_id = self.effective_categories_for_rows(bank_rows)
        self._no_oa_bank_batch_service.build_batches(
            bank_rows,
            categories_by_transaction_id,
            self._pair_relation_service.list_active_relations(),
            self.no_oa_bank_batch_source_versions(),
            eligible_batch_types=self.selected_tag_codes(),
        )
        migration_result = self._no_oa_bank_batch_service.last_legacy_migration_result()
        if migration_result.get("changed"):
            self.after_mutation(
                [
                    str(month)
                    for month in list(migration_result.get("affected_months") or [])
                    if str(month).strip()
                ],
                changed_case_ids=[
                    str(case_id)
                    for case_id in list(migration_result.get("changed_case_ids") or [])
                    if str(case_id).strip()
                ],
                persist=True,
            )
        return bank_rows, categories_by_transaction_id

    def no_oa_bank_transaction_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for transaction in list(self._import_service.list_transactions(month="all")):
            payload = self._serialize_value(transaction)
            if not isinstance(payload, dict):
                continue
            transaction_id = str(payload.get("id") or "").strip()
            if not transaction_id:
                continue
            row = dict(payload)
            row["id"] = transaction_id
            row["type"] = "bank"
            row["bank_name"] = str(
                row.get("bank_name")
                or row.get("imported_bank_name")
                or row.get("bank_short_name")
                or row.get("account_bank")
                or ""
            ).strip()
            account_no = str(row.get("account_no") or row.get("account_number") or "").strip()
            account_last4 = str(row.get("account_last4") or row.get("imported_bank_last4") or "").strip()
            if not account_last4:
                digits = "".join(ch for ch in account_no if ch.isdigit())
                account_last4 = digits[-4:] if digits else ""
            row["account_last4"] = account_last4
            row["account_key"] = str(row.get("account_key") or f"{row['bank_name']}:{account_last4}").strip(":")
            row["counterparty_name"] = str(row.get("counterparty_name") or row.get("counterparty_name_raw") or "").strip()
            amount = row.get("amount") or "0.00"
            direction = str(row.get("txn_direction") or row.get("direction") or "").strip().lower()
            if direction in {"outflow", "expense", "支", "出"}:
                row["direction"] = "expense"
                row["direction_label"] = "支"
                row["debit_amount"] = row.get("debit_amount") or amount
                row["credit_amount"] = row.get("credit_amount") or "0.00"
            elif direction in {"inflow", "income", "收", "进"}:
                row["direction"] = "income"
                row["direction_label"] = "收"
                row["debit_amount"] = row.get("debit_amount") or "0.00"
                row["credit_amount"] = row.get("credit_amount") or amount
            if "purpose" not in row:
                row["purpose"] = row.get("usage") or row.get("use") or ""
            rows.append(row)
        categories_by_transaction_id = self.effective_categories_for_rows(rows)
        for row in rows:
            transaction_id = str(row.get("id") or "").strip()
            category = categories_by_transaction_id.get(transaction_id, {})
            if category:
                row["category_code"] = category.get("category_code")
                row["category_label"] = category.get("category_label")
                row["category_path"] = list(category.get("category_path") or [])
                row["category_primary_label"] = category.get("category_primary_label") or category.get("effective_category_primary_label")
                row["category_sub_label"] = category.get("category_sub_label") or category.get("effective_category_sub_label")
                row["category_label_path"] = list(
                    category.get("category_label_path") or category.get("effective_category_label_path") or []
                )
                row["category_source"] = category.get("category_source") or category.get("source")
        return rows

    def effective_categories_for_rows(self, rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        categories_by_transaction_id = {
            str(transaction_id): dict(category)
            for transaction_id, category in dict(self._effective_category_provider.bulk_get_for_rows(rows) or {}).items()
            if isinstance(category, dict)
        }
        row_ids = {
            str(row.get("id") or "").strip()
            for row in list(rows or [])
            if str(row.get("id") or "").strip()
        }
        snapshot = self._bank_transaction_category_service.snapshot()
        manual_categories = snapshot.get("categories") if isinstance(snapshot, dict) else None
        if not isinstance(manual_categories, dict):
            return categories_by_transaction_id
        for transaction_id, category in manual_categories.items():
            normalized_transaction_id = str(transaction_id or "").strip()
            if normalized_transaction_id not in row_ids or not isinstance(category, dict):
                continue
            category_code = str(category.get("category_code") or "").strip()
            if category_code != "internal_transfer":
                continue
            merged = dict(categories_by_transaction_id.get(normalized_transaction_id) or {})
            merged.update(category)
            merged["transaction_id"] = normalized_transaction_id
            merged["category_code"] = category_code
            merged["effective_category_code"] = category_code
            merged["effective_category_label"] = category.get("category_label")
            merged["effective_category_primary_label"] = category.get("category_primary_label")
            merged["effective_category_sub_label"] = category.get("category_sub_label")
            merged["effective_category_label_path"] = list(category.get("category_label_path") or [])
            merged["effective_category_path"] = list(category.get("category_path") or [])
            merged["effective_category_source"] = category.get("source") or category.get("category_source") or "manual"
            categories_by_transaction_id[normalized_transaction_id] = merged
        return categories_by_transaction_id

    def selected_tag_codes(self) -> list[str]:
        payload = self._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
        return [str(code) for code in list(payload.get("selected_tag_codes") or []) if str(code).strip()]

    def summary(self, batches: list[dict[str, object]]) -> dict[str, object]:
        counts: dict[str, int] = {"draft": 0, "submitted": 0, "withdrawn": 0, "conflict": 0, "stale": 0}
        selected_or_existing_codes = [
            *self.selected_tag_codes(),
            *[
                str(batch.get("batch_type") or "").strip()
                for batch in batches
                if isinstance(batch, dict) and str(batch.get("batch_type") or "").strip()
            ],
        ]
        category_counts: dict[str, dict[str, object]] = {}
        for batch_type in selected_or_existing_codes:
            if not batch_type or batch_type in category_counts:
                continue
            definition = self.bank_transaction_tag_definition_current(batch_type)
            category_counts[batch_type] = {
                "code": batch_type,
                "label": self.bank_transaction_tag_label_from_definition(batch_type, definition),
                "primary_label": str((definition or {}).get("output_primary_label") or ""),
                "sub_label": str((definition or {}).get("output_sub_label") or ""),
                "label_path": [
                    item
                    for item in [
                        str((definition or {}).get("output_primary_label") or "").strip(),
                        str((definition or {}).get("output_sub_label") or "").strip(),
                    ]
                    if item
                ],
                "total": 0,
                "draft": 0,
                "submitted": 0,
                "withdrawn": 0,
                "conflict": 0,
                "stale": 0,
                "total_amount": Decimal("0.00"),
            }
        total_amount = Decimal("0.00")
        for batch in batches:
            status = str(batch.get("status") or "").strip()
            if status in counts:
                counts[status] += 1
            batch_type = str(batch.get("batch_type") or "").strip()
            try:
                amount = Decimal(str(batch.get("total_amount") or "0").replace(",", ""))
            except Exception:
                amount = Decimal("0.00")
            total_amount += amount
            if batch_type in category_counts:
                category = category_counts[batch_type]
                category["total"] = int(category["total"]) + 1
                if status in counts:
                    category[status] = int(category[status]) + 1
                category["total_amount"] = category["total_amount"] + amount
        categories = []
        for category in [dict(value) for value in category_counts.values()]:
            category["total_amount"] = f"{category['total_amount']:.2f}"
            categories.append(category)
        return {
            "total": len(batches),
            **counts,
            "draft_count": counts["draft"],
            "submitted_count": counts["submitted"],
            "withdrawn_count": counts["withdrawn"],
            "conflict_count": counts["conflict"],
            "stale_count": counts["stale"],
            "total_amount": f"{total_amount:.2f}",
            "categories": categories,
        }

    def resolve_labels(self, batches: list[dict[str, object]]) -> list[dict[str, object]]:
        resolved: list[dict[str, object]] = []
        for batch in list(batches or []):
            if not isinstance(batch, dict):
                continue
            next_batch = dict(batch)
            batch_type = str(next_batch.get("batch_type") or "").strip()
            if batch_type:
                definition = self.bank_transaction_tag_definition_current(batch_type)
                label = self.bank_transaction_tag_label_from_definition(batch_type, definition)
                next_batch["batch_label"] = label
                next_batch["display_tags"] = ["免OA", label]
                next_batch["category_primary_label"] = str((definition or {}).get("output_primary_label") or label)
                next_batch["category_sub_label"] = str((definition or {}).get("output_sub_label") or "")
                next_batch["category_label_path"] = [
                    item
                    for item in [
                        str(next_batch.get("category_primary_label") or "").strip(),
                        str(next_batch.get("category_sub_label") or "").strip(),
                    ]
                    if item
                ]
            resolved.append(next_batch)
        return resolved

    def no_oa_bank_batch_source_versions(self) -> dict[str, object]:
        no_oa_selection = self._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
        return {
            **self._workbench_matching_source_versions_provider(),
            "no_oa_bank_batch_schema_version": NO_OA_BANK_BATCH_SCHEMA_VERSION,
            "no_oa_bank_batch_tag_selection_version": int(no_oa_selection.get("version") or 1),
            "bank_transaction_category_schema_version": BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION,
            "pair_relation_snapshot_version": WorkbenchReadModelService.snapshot_version(
                self._pair_relation_service.snapshot()
            ),
            "bank_transaction_category_snapshot_version": WorkbenchReadModelService.snapshot_version(
                self._bank_transaction_category_service.snapshot()
            ),
        }

    def no_oa_bank_batch_stale_reasons(self, batches: object) -> list[str]:
        batch_rows = batches if isinstance(batches, list) else []
        if not batch_rows:
            return []
        expected = self.no_oa_bank_batch_source_versions()
        reasons: list[str] = []
        for batch in batch_rows:
            if not isinstance(batch, dict):
                continue
            source_versions = batch.get("source_versions")
            for reason in source_version_mismatch_reasons(
                expected=expected,
                actual=source_versions if isinstance(source_versions, dict) else {},
            ):
                if reason not in reasons:
                    reasons.append(reason)
        return reasons

    def after_mutation(
        self,
        affected_months: list[str],
        *,
        changed_case_ids: list[str],
        persist: bool,
    ) -> bool:
        normalized_months = [
            str(month).strip()
            for month in list(affected_months or [])
            if SEARCH_MONTH_RE.match(str(month).strip())
        ]
        scope_keys = ["all", *normalized_months]
        self._execute_derived_data_lifecycle_event(
            "no_oa_bank_batch_changed",
            months=normalized_months,
            metadata={"source": "no_oa_bank_batch"},
            schedule_cost_warmup=False,
        )
        if persist:
            self.persist_mutation(
                changed_case_ids=changed_case_ids,
                changed_scope_keys=self._expand_workbench_read_model_scope_keys_for_base_scopes(scope_keys),
            )
        return bool(normalized_months)

    def enqueue_background_refresh(self, scope_keys: list[str], *, reason: str) -> bool:
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        if not callable(enqueue):
            return False
        enqueued = False
        for scope_key in [str(item).strip() for item in list(scope_keys or []) if str(item).strip()]:
            enqueue(scope_type="no_oa_bank_batch", scope_key=scope_key, reason=reason)
            enqueued = True
        return enqueued

    def persist_mutation(self, *, changed_case_ids: list[str], changed_scope_keys: list[str]) -> None:
        if self._state_store is None:
            return
        try:
            self._search_cache_clearer()
            if changed_case_ids:
                self._state_store.save_workbench_pair_relations(
                    self._pair_relation_service.snapshot_case_ids(changed_case_ids),
                    changed_case_ids=changed_case_ids,
                )
            self._state_store.save_no_oa_bank_batches(self._no_oa_bank_batch_service.snapshot())
            self._state_store.save_workbench_read_models(
                self._workbench_read_model_service.snapshot(),
                changed_scope_keys=changed_scope_keys,
            )
        except Exception as exc:
            raise NoOaBankBatchPersistenceError(str(exc)) from exc

    def _mutation_result(self, batch: dict[str, object], *, status: str, persist: bool) -> dict[str, object]:
        relation_case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
        relation = self.pair_relation_snapshot_by_case_id(relation_case_id)
        affected_months = self.affected_months(batch)
        workbench_rebuild_queued = self.after_mutation(
            affected_months,
            changed_case_ids=[relation_case_id] if relation_case_id else [],
            persist=persist,
        )
        return {
            "batch": self.resolve_labels([batch])[0],
            "pair_relation": relation or {},
            "affected_months": affected_months,
            "workbench_rebuild_queued": workbench_rebuild_queued,
            "results": [{"batch_id": batch.get("batch_id"), "status": status}],
        }

    def affected_months(self, batch: dict[str, object]) -> list[str]:
        months = {
            str(batch.get("scope_month") or "").strip(),
            *self._bank_transaction_category_affected_months_provider(
                [str(row_id) for row_id in list(batch.get("row_ids") or []) if str(row_id).strip()]
            ),
        }
        return sorted(month for month in months if SEARCH_MONTH_RE.match(month))

    def pair_relation_snapshot_by_case_id(self, case_id: str) -> dict[str, object] | None:
        normalized_case_id = str(case_id or "").strip()
        if not normalized_case_id:
            return None
        pair_relations = self._pair_relation_service.snapshot().get("pair_relations", {})
        relation = pair_relations.get(normalized_case_id) if isinstance(pair_relations, dict) else None
        return dict(relation) if isinstance(relation, dict) else None

    def _validate_internal_transfer_selection(
        self,
        *,
        bank_rows: list[dict[str, object]],
        categories_by_transaction_id: dict[str, dict[str, object]],
        row_ids: list[str],
    ) -> None:
        rows_by_id = {
            str(row.get("id") or "").strip(): row
            for row in bank_rows
            if str(row.get("id") or "").strip()
        }
        selected_rows = [
            rows_by_id.get(str(row_id).strip())
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        ]
        if not selected_rows or any(row is None for row in selected_rows):
            return
        batch_types = {
            NoOaBankBatchService._category_code(row, categories_by_transaction_id)
            for row in selected_rows
            if isinstance(row, dict)
        }
        batch_types.discard("")
        if "internal_transfer" not in batch_types:
            return
        if len(batch_types) != 1:
            raise ValueError("no_oa_bank_batch_selection_internal_transfer_conflict")
        refreshed = self._no_oa_bank_batch_service.build_batches(
            bank_rows,
            categories_by_transaction_id,
            self._pair_relation_service.list_active_relations(),
            self.no_oa_bank_batch_source_versions(),
            eligible_batch_types=self.selected_tag_codes(),
        )
        selected_set = {str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()}
        matching_drafts = [
            batch for batch in refreshed
            if str(batch.get("batch_type") or "") == "internal_transfer"
            and str(batch.get("status") or "") == "draft"
            and set(str(item) for item in list(batch.get("row_ids") or [])) == selected_set
        ]
        if matching_drafts:
            return
        conflict_batches = [
            batch for batch in refreshed
            if str(batch.get("batch_type") or "") == "internal_transfer"
            and selected_set.intersection(str(item) for item in list(batch.get("row_ids") or []))
        ]
        if conflict_batches:
            conflict_codes = {
                str(batch.get("conflict_code") or "").strip()
                for batch in conflict_batches
                if str(batch.get("conflict_code") or "").strip()
            }
            if "missing_internal_transfer_counterpart" in conflict_codes:
                raise ValueError("no_oa_bank_batch_selection_internal_transfer_requires_pair")
            raise ValueError("no_oa_bank_batch_selection_internal_transfer_conflict")
        raise ValueError("no_oa_bank_batch_selection_internal_transfer_requires_pair")

    def _restore_snapshots(
        self,
        batch_snapshot: dict[str, Any],
        relation_snapshot: dict[str, Any],
    ) -> None:
        restored_batch_service = NoOaBankBatchService.from_snapshot(batch_snapshot)
        self._no_oa_bank_batch_service._batches = deepcopy(restored_batch_service._batches)
        self._no_oa_bank_batch_service._audit_log = deepcopy(restored_batch_service._audit_log)
        restored_relation_service = WorkbenchPairRelationService.from_snapshot(relation_snapshot)
        self._pair_relation_service._pair_relations = deepcopy(restored_relation_service._pair_relations)
        self._pair_relation_service._pair_relation_history = deepcopy(restored_relation_service._pair_relation_history)

    def bank_transaction_tag_definition_current(self, code: str) -> dict[str, object] | None:
        tag_code = str(code or "").strip()
        if not tag_code:
            return None
        payload = self._bank_transaction_category_service.tag_dictionary_payload()
        for definition in list(payload.get("definitions") or []):
            if isinstance(definition, dict) and str(definition.get("code") or "").strip() == tag_code:
                return dict(definition)
        return None

    @staticmethod
    def bank_transaction_tag_label_from_definition(code: str, definition: dict[str, object] | None) -> str:
        if isinstance(definition, dict):
            return str(definition.get("label") or definition.get("output_sub_label") or definition.get("output_primary_label") or code)
        return NO_OA_MANAGED_LABELS.get(code, BANK_TRANSACTION_CATEGORY_LABELS.get(code, code))

    @staticmethod
    def detail_rows(
        row_ids: list[str],
        rows_by_id: dict[str, dict[str, object]],
        categories_by_transaction_id: dict[str, dict[str, object]],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for row_id in row_ids:
            source_row = rows_by_id.get(row_id)
            if not isinstance(source_row, dict):
                continue
            row = dict(source_row)
            category = categories_by_transaction_id.get(row_id, {})
            if isinstance(category, dict):
                row["category_code"] = row.get("category_code") or category.get("category_code")
                row["category_label"] = row.get("category_label") or category.get("category_label")
                row["category_primary_label"] = (
                    row.get("category_primary_label")
                    or category.get("category_primary_label")
                    or category.get("effective_category_primary_label")
                )
                row["category_sub_label"] = (
                    row.get("category_sub_label")
                    or category.get("category_sub_label")
                    or category.get("effective_category_sub_label")
                )
                row["category_label_path"] = list(
                    row.get("category_label_path")
                    or category.get("category_label_path")
                    or category.get("effective_category_label_path")
                    or []
                )
                row["category_source"] = row.get("category_source") or category.get("category_source") or category.get("source")
            row.setdefault("category_code", "")
            row.setdefault("category_label", "")
            row.setdefault("category_primary_label", "")
            row.setdefault("category_sub_label", "")
            row.setdefault("category_label_path", [])
            row.setdefault("category_source", "")
            rows.append(row)
        return rows

    @staticmethod
    def _serialize_value(value: object) -> object:
        if is_dataclass(value):
            return {key: NoOaBankBatchApplicationService._serialize_value(val) for key, val in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): NoOaBankBatchApplicationService._serialize_value(val) for key, val in value.items()}
        if isinstance(value, list):
            return [NoOaBankBatchApplicationService._serialize_value(item) for item in value]
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        if isinstance(value, Enum):
            return value.value
        return value
