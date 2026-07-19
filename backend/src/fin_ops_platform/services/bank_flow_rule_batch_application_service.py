from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from fin_ops_platform.services.bank_batch_application_service import (
    SEARCH_MONTH_RE,
    BankBatchApplicationService,
    BankBatchPersistenceError,
    BankBatchRelationMutationError,
)
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE, BankBatchService
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.read_model_write_targets import write_target_envelope


BANK_FLOW_RULE_BATCH_ONLINE_MUTATION_ACTIONS = frozenset(
    {
        "bank_flow_rule_batch_submit",
        "bank_flow_rule_batch_withdraw",
        "bank_flow_rule_batch_reset_submitted",
    }
)


class BankFlowRuleBatchPersistenceError(BankBatchPersistenceError):
    error_code = "bank_flow_rule_batch_persistence_failed"


class BankFlowRuleBatchApplicationService(BankBatchApplicationService):
    """Application boundary for 流水规则批量处理."""

    def list_batches_payload(
        self,
        query: dict[str, list[str]],
        *,
        relation_mode: str = BANK_FLOW_RULE_BATCH_RELATION_MODE,
    ) -> dict[str, object]:
        if relation_mode != BANK_FLOW_RULE_BATCH_RELATION_MODE:
            raise BankBatchRelationMutationError(
                "invalid_bank_flow_rule_batch_relation_mode",
                "流水规则批次服务只接受 bank_flow_rule_batch relation mode。",
            )
        pagination = self._pagination_from_query(query)
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
        read_page = getattr(self._bank_batch_read_model_repository, "read_page", None)
        if not callable(read_page):
            raise RuntimeError("bank_flow_rule_batch read repository requires read_page.")
        page_result = read_page(
            filters,
            summary_filters=summary_filters,
            page=pagination["page"] if pagination is not None else 1,
            page_size=pagination["page_size"] if pagination is not None else None,
        )
        refresh_scope_keys = self._refresh_scope_keys_for_filters(filters)
        if page_result is None:
            refresh_enqueued = self.enqueue_background_refresh(
                refresh_scope_keys,
                reason="api_bank_flow_rule_batch_read_model_missing",
                metadata=self._read_model_refresh_metadata_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE),
            )
            return {
                "summary": self._summary_from_aggregates([]),
                "batches": [],
                **self._bank_flow_pagination_payload(pagination, total=0),
                "read_model_status": "missing",
                "read_model_stale_reasons": [],
                "refresh_enqueued": refresh_enqueued,
                "refresh_reason": "api_bank_flow_rule_batch_read_model_missing",
            }

        source_summary = page_result.get("source_versions_summary")
        source_summary = source_summary if isinstance(source_summary, dict) else {}
        repository_status = str(source_summary.get("read_model_status") or "missing").strip()
        read_model_status = repository_status
        stale_reasons = (
            ["bank_flow_rule_batch_source_versions_inconsistent"]
            if repository_status == "schema_mismatch"
            else []
        )
        refresh_enqueued = False
        refresh_reason = ""
        if read_model_status in {"missing", "stale", "schema_mismatch"}:
            refresh_reason = (
                "api_bank_flow_rule_batch_source_versions_stale"
                if read_model_status in {"stale", "schema_mismatch"}
                else "api_bank_flow_rule_batch_read_model_missing"
            )
            refresh_enqueued = self.enqueue_background_refresh(
                refresh_scope_keys,
                reason=refresh_reason,
                metadata=self._read_model_refresh_metadata_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE),
            )
        tag_dictionary = self._bank_transaction_category_service.tag_dictionary_payload()
        definitions_by_code = {
            str(definition.get("code") or "").strip(): dict(definition)
            for definition in list(tag_dictionary.get("definitions") or [])
            if isinstance(definition, dict) and str(definition.get("code") or "").strip()
        }
        tag_rules_payload = self._tag_rules_payload_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE)
        eligible_tag_codes = {
            str(tag.get("code") or "").strip()
            for tag in list(tag_rules_payload.get("active_tags") or [])
            if isinstance(tag, dict) and str(tag.get("code") or "").strip()
        }
        batches = self.resolve_labels(
            self._public_batches(page_result.get("items")),
            definitions_by_code=definitions_by_code,
        )
        payload: dict[str, object] = {
            "summary": self._summary_from_aggregates(
                page_result.get("aggregates"),
                eligible_tag_codes=eligible_tag_codes,
                definitions_by_code=definitions_by_code,
            ),
            "batches": batches,
            **self._bank_flow_pagination_payload(
                pagination,
                total=int(page_result.get("total") or 0),
            ),
            "read_model_status": read_model_status,
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = stale_reasons
        if refresh_reason:
            payload["refresh_enqueued"] = refresh_enqueued
            payload["refresh_reason"] = refresh_reason
        return payload

    @staticmethod
    def _bank_flow_pagination_payload(
        pagination: dict[str, int] | None,
        *,
        total: int,
    ) -> dict[str, object]:
        if pagination is None:
            return {}
        page_size = pagination["page_size"]
        return {
            "pagination": {
                "page": pagination["page"],
                "page_size": page_size,
                "pageSize": page_size,
                "total": max(int(total), 0),
            }
        }

    def _summary_from_aggregates(
        self,
        aggregates: object,
        *,
        eligible_tag_codes: set[str] | None = None,
        definitions_by_code: dict[str, dict[str, object]] | None = None,
    ) -> dict[str, object]:
        rows = [row for row in list(aggregates or []) if isinstance(row, dict)] if isinstance(aggregates, list) else []
        aggregate_codes = [str(row.get("batch_type") or "").strip() for row in rows]
        category_codes = self._dedupe_ordered(
            [
                *sorted(
                    eligible_tag_codes
                    if eligible_tag_codes is not None
                    else self._eligible_tag_codes_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE)
                ),
                *aggregate_codes,
            ]
        )
        counts = {"draft": 0, "submitted": 0, "withdrawn": 0, "conflict": 0, "stale": 0}
        categories: dict[str, dict[str, object]] = {}
        for code in category_codes:
            if not code:
                continue
            definition = (
                definitions_by_code.get(code)
                if isinstance(definitions_by_code, dict)
                else self.bank_transaction_tag_definition_current(code)
            )
            categories[code] = {
                "code": code,
                "label": self.bank_transaction_tag_label_from_definition(code, definition),
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
        for row in rows:
            code = str(row.get("batch_type") or "").strip()
            status = str(row.get("presented_status") or "").strip()
            count = max(int(row.get("batch_count") or 0), 0)
            try:
                amount = Decimal(str(row.get("total_amount") or "0").replace(",", ""))
            except (InvalidOperation, ValueError):
                amount = Decimal("0.00")
            if status in counts:
                counts[status] += count
            total_amount += amount
            category = categories.get(code)
            if category is None:
                continue
            category["total"] = int(category["total"]) + count
            if status in counts:
                category[status] = int(category[status]) + count
            category["total_amount"] = Decimal(str(category["total_amount"])) + amount
        category_payloads: list[dict[str, object]] = []
        for category in categories.values():
            next_category = dict(category)
            next_category["total_amount"] = f"{Decimal(str(category['total_amount'])):.2f}"
            category_payloads.append(next_category)
        total = counts["draft"] + counts["submitted"] + counts["withdrawn"]
        return {
            "total": total,
            **counts,
            "draft_count": counts["draft"],
            "submitted_count": counts["submitted"],
            "withdrawn_count": counts["withdrawn"],
            "conflict_count": counts["conflict"],
            "stale_count": counts["stale"],
            "total_amount": f"{total_amount:.2f}",
            "categories": category_payloads,
        }

    def _refresh_bank_flow_rule_batch_runtime_snapshot(self) -> None:
        self.refresh_batches(
            apply_relation_repairs=False,
            scope_key="all",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

    def _refresh_bank_flow_rule_batch_runtime_snapshot_if_missing(self, batch_id: str) -> None:
        try:
            self._bank_batch_service.get_batch(batch_id)
            return
        except KeyError:
            if self._restore_bank_flow_rule_batch_runtime_item(batch_id):
                return
            if self._restore_bank_flow_rule_batch_runtime_snapshot(batch_id):
                return
            self._refresh_bank_flow_rule_batch_runtime_snapshot()

    def _restore_bank_flow_rule_batch_runtime_item(self, batch_id: str) -> bool:
        normalized_batch_id = str(batch_id or "").strip()
        read_repository = getattr(self, "_bank_batch_read_model_repository", None)
        list_rows = getattr(read_repository, "list_bank_flow_rule_batch_rows", None)
        replace_snapshot = getattr(self._bank_batch_service, "replace_snapshot", None)
        snapshot = getattr(self._bank_batch_service, "snapshot", None)
        if not normalized_batch_id or not callable(list_rows) or not callable(replace_snapshot):
            return False
        rows = list_rows({"batch_id": normalized_batch_id})
        if not rows:
            return False
        batch = next(
            (
                {**row, "batch_id": normalized_batch_id}
                for row in rows
                if isinstance(row, dict) and str(row.get("batch_id") or "").strip() == normalized_batch_id
            ),
            None,
        )
        if batch is None:
            return False
        current_snapshot = snapshot() if callable(snapshot) else {}
        current_batches = current_snapshot.get("batches") if isinstance(current_snapshot, dict) else None
        replace_snapshot(
            {
                **(current_snapshot if isinstance(current_snapshot, dict) else {}),
                "batches": {
                    **(current_batches if isinstance(current_batches, dict) else {}),
                    normalized_batch_id: batch,
                },
            }
        )
        try:
            self._bank_batch_service.get_batch(normalized_batch_id)
            return True
        except KeyError:
            return False

    def _restore_bank_flow_rule_batch_runtime_snapshot(self, batch_id: str) -> bool:
        state_store = getattr(self, "_state_store", None)
        load_snapshot = getattr(state_store, "load_bank_flow_rule_batches", None)
        replace_snapshot = getattr(self._bank_batch_service, "replace_snapshot", None)
        if not callable(load_snapshot) or not callable(replace_snapshot):
            return False
        snapshot = load_snapshot()
        if not isinstance(snapshot, dict):
            return False
        batches = snapshot.get("batches")
        if not isinstance(batches, dict) or str(batch_id or "").strip() not in batches:
            return False
        replace_snapshot(snapshot)
        try:
            self._bank_batch_service.get_batch(batch_id)
            return True
        except KeyError:
            return False

    def _prepare_batch_for_submit(self, batch_id: str, *, relation_mode: str) -> None:
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            self._refresh_bank_flow_rule_batch_runtime_snapshot_if_missing(batch_id)
            return
        super()._prepare_batch_for_submit(batch_id, relation_mode=relation_mode)

    def submit_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        note: str | None,
        relation_mode: str = BANK_FLOW_RULE_BATCH_RELATION_MODE,
        persist: bool = True,
    ) -> dict[str, object]:
        if relation_mode != BANK_FLOW_RULE_BATCH_RELATION_MODE:
            raise BankBatchRelationMutationError(
                "invalid_bank_flow_rule_batch_relation_mode",
                "流水规则批次服务只接受 bank_flow_rule_batch relation mode。",
            )
        previous_batch_snapshot = self._bank_batch_service.snapshot()
        try:
            self._prepare_batch_for_submit(batch_id, relation_mode=relation_mode)
            before_batch = self._bank_batch_service.get_batch(batch_id)
            already_submitted = str(before_batch.get("status") or "") == "submitted"
            batch = self._bank_batch_service.submit_batch(
                batch_id,
                actor=actor,
                expected_version=expected_version,
                note=note,
            )
            if not already_submitted:
                self._confirm_relation_for_batch(batch, actor=actor, note=note, relation_mode=relation_mode)
            return self._mutation_result(
                batch,
                status="submitted",
                persist=persist,
                read_model_key=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            )
        except Exception:
            self._restore_batch_service_snapshot(self._bank_batch_service, previous_batch_snapshot)
            raise

    def submit_selected_rows(
        self,
        *,
        row_ids: list[str],
        actor: str,
        note: str | None,
        relation_mode: str = BANK_FLOW_RULE_BATCH_RELATION_MODE,
    ) -> dict[str, object]:
        if relation_mode != BANK_FLOW_RULE_BATCH_RELATION_MODE:
            raise BankBatchRelationMutationError(
                "invalid_bank_flow_rule_batch_relation_mode",
                "流水规则批次服务只接受 bank_flow_rule_batch relation mode。",
            )
        bank_rows = self.bank_transaction_rows_by_ids(row_ids)
        categories_by_transaction_id = self.effective_categories_for_rows(bank_rows)
        if self._selected_rows_include_internal_transfer(bank_rows, categories_by_transaction_id):
            raise BankBatchRelationMutationError(
                "bank_flow_rule_batch_selection_internal_transfer_requires_pair",
                "内部往来批次请使用单批提交。",
            )
        previous_batch_snapshot = self._bank_batch_service.snapshot()
        try:
            months = self._months_for_bank_rows(bank_rows)
            source_versions = (
                self.read_model_scope_source_versions(
                    scope_key=months[0],
                    relation_mode=relation_mode,
                )
                if len(months) == 1
                else self.bank_batch_source_versions(relation_mode=relation_mode)
            )
            batch = self._bank_batch_service.submit_selected_rows(
                bank_rows=bank_rows,
                categories_by_transaction_id=categories_by_transaction_id,
                active_relations=self._workbench_relation_active_relations_for_bank_rows(bank_rows),
                source_versions=source_versions,
                eligible_batch_types=self._eligible_tag_codes_for_relation_mode(relation_mode),
                row_ids=row_ids,
                actor=actor,
                note=note,
                relation_mode=relation_mode,
            )
            self._confirm_relation_for_batch(batch, actor=actor, note=note, relation_mode=relation_mode)
            return self._mutation_result(
                batch,
                status="submitted",
                persist=True,
                read_model_key=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            )
        except Exception:
            self._restore_batch_service_snapshot(self._bank_batch_service, previous_batch_snapshot)
            raise

    def _selected_rows_include_internal_transfer(
        self,
        bank_rows: list[dict[str, object]],
        categories_by_transaction_id: dict[str, dict[str, object]],
    ) -> bool:
        return "internal_transfer" in {
            BankBatchService._category_code(row, categories_by_transaction_id)
            for row in list(bank_rows or [])
            if isinstance(row, dict)
        }

    def detail_payload(self, batch_id: str) -> dict[str, object]:
        self._refresh_bank_flow_rule_batch_runtime_snapshot_if_missing(batch_id)
        return super().detail_payload(batch_id)

    def withdraw_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        reason: str | None,
    ) -> dict[str, object]:
        self._refresh_bank_flow_rule_batch_runtime_snapshot_if_missing(batch_id)
        return super().withdraw_batch(
            batch_id,
            actor=actor,
            expected_version=expected_version,
            reason=reason,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

    def reset_submitted_bank_flow_rule_batches(
        self,
        *,
        actor: str,
        reason: str | None,
    ) -> dict[str, object]:
        previous_batch_snapshot = self._bank_batch_service.snapshot()
        previous_relation_snapshot = self._pair_relation_snapshot_port.snapshot()
        candidates = self._submitted_batches_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE)
        if not candidates:
            return {
                "summary": {
                    "reset_count": 0,
                    "batch_count": 0,
                    "row_count": 0,
                    "affected_months": [],
                },
                "affected_months": [],
                **write_target_envelope(targets=[], scope_keys=[], fallback_scope_key="all"),
                "workbench_rebuild_queued": False,
                "results": [],
            }

        withdrawn_batches: list[dict[str, object]] = []
        affected_months: set[str] = set()
        resolved_reason = str(reason or "").strip() or "流水规则批量处理：重置全部已提交批次为未提交"
        try:
            for candidate in candidates:
                batch_id = str(candidate.get("batch_id") or "").strip()
                if not batch_id:
                    continue
                before_batch = self._bank_batch_service.get_batch(batch_id)
                withdrawn = self._bank_batch_service.withdraw_batch(
                    batch_id,
                    actor=actor,
                    expected_version=int(before_batch.get("version") or 1),
                    reason=resolved_reason,
                )
                withdrawn_batches.append(withdrawn)
                affected_months.update(self.affected_months(withdrawn))

            case_ids = [
                str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
                for batch in withdrawn_batches
                if str(batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
            ]
            version_fingerprint = "|".join(
                f"{batch.get('batch_id')}:{batch.get('version')}"
                for batch in sorted(withdrawn_batches, key=lambda item: str(item.get("batch_id") or ""))
            )
            cancel_result = self._require_relation_command_service().cancel_relations_by_case_ids(
                case_ids=case_ids,
                actor_id=str(actor or ""),
                reason=resolved_reason,
                idempotency_key=(
                    "bank_flow_rule_batch:reset_submitted:"
                    f"{sha256(version_fingerprint.encode('utf-8')).hexdigest()[:20]}"
                ),
                history_operation_type="bank_flow_rule_batch_reset_submitted_withdraw",
            )
            changed_case_ids = [
                str(case_id).strip()
                for case_id in list(cancel_result.get("changed_case_ids") or [])
                if str(case_id).strip()
            ]
            workbench_rebuild_queued = self.after_mutation(
                sorted(affected_months),
                changed_case_ids=changed_case_ids,
                changed_batch_ids=[
                    str(batch.get("batch_id") or "").strip()
                    for batch in withdrawn_batches
                    if str(batch.get("batch_id") or "").strip()
                ],
                persist=True,
                action_name="bank_flow_rule_batch_reset_submitted",
            )
        except Exception:
            self._restore_snapshots(previous_batch_snapshot, previous_relation_snapshot)
            raise
        return {
            "summary": {
                "reset_count": len(withdrawn_batches),
                "batch_count": len(withdrawn_batches),
                "row_count": sum(int(batch.get("row_count") or 0) for batch in withdrawn_batches),
                "affected_months": sorted(affected_months),
            },
            "affected_months": sorted(affected_months),
            **write_target_envelope(
                targets=self._mutation_barrier_targets(
                    BANK_FLOW_RULE_BATCH_RELATION_MODE,
                    sorted(affected_months),
                ),
                scope_keys=sorted(affected_months),
                fallback_scope_key="all",
            ),
            "workbench_rebuild_queued": workbench_rebuild_queued,
            "results": [
                {"batch_id": batch.get("batch_id"), "status": "withdrawn"}
                for batch in withdrawn_batches
            ],
        }

    def after_mutation(
        self,
        affected_months: list[str],
        *,
        changed_case_ids: list[str],
        changed_batch_ids: list[str] | None = None,
        persist: bool,
        action_name: str | None = None,
    ) -> bool:
        normalized_action_name = str(action_name or "").strip()
        if not normalized_action_name.startswith("bank_flow_rule_batch"):
            return super().after_mutation(
                affected_months,
                changed_case_ids=changed_case_ids,
                persist=persist,
                action_name=action_name,
            )
        normalized_months = [
            str(month).strip()
            for month in list(affected_months or [])
            if SEARCH_MONTH_RE.match(str(month).strip())
        ]
        if normalized_action_name not in BANK_FLOW_RULE_BATCH_ONLINE_MUTATION_ACTIONS:
            self._execute_derived_data_lifecycle_event(
                "bank_flow_rule_batch_changed",
                months=normalized_months,
                metadata={
                    "source": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                    "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                    **({"action_name": normalized_action_name} if normalized_action_name else {}),
                },
            )
        if persist:
            self.persist_mutation(
                changed_case_ids=changed_case_ids,
                changed_scope_keys=["all", *normalized_months],
                changed_batch_ids=changed_batch_ids,
            )
        return bool(normalized_months)

    def persist_mutation(
        self,
        *,
        changed_case_ids: list[str],
        changed_scope_keys: list[str],
        changed_batch_ids: list[str] | None = None,
    ) -> None:
        if self._state_store is None:
            return
        try:
            self._search_cache_clearer()
            save_mutation = getattr(self._state_store, "save_bank_flow_rule_batch_mutation", None)
            if not callable(save_mutation):
                raise RuntimeError("bank_flow_rule_batch mutation persistence requires save_bank_flow_rule_batch_mutation.")
            save_mutation(
                pair_relation_snapshot=self._pair_relation_snapshot_port.snapshot_case_ids(changed_case_ids)
                if changed_case_ids
                else self._pair_relation_snapshot_port.snapshot(),
                bank_flow_rule_batch_snapshot=self._bank_batch_public_snapshot(),
                changed_case_ids=changed_case_ids,
                changed_scope_keys=changed_scope_keys,
                changed_batch_ids=list(changed_batch_ids or []),
            )
        except Exception as exc:
            raise BankFlowRuleBatchPersistenceError(str(exc)) from exc

    def resolve_labels(
        self,
        batches: list[dict[str, object]],
        *,
        definitions_by_code: dict[str, dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        resolved: list[dict[str, object]] = []
        for batch in list(batches or []):
            if not isinstance(batch, dict):
                continue
            next_batch = self._presentation_batch(batch)
            batch_type = str(next_batch.get("batch_type") or "").strip()
            if batch_type:
                definition = (
                    definitions_by_code.get(batch_type)
                    if isinstance(definitions_by_code, dict)
                    else self.bank_transaction_tag_definition_current(batch_type)
                )
                label = self.bank_transaction_tag_label_from_definition(batch_type, definition)
                next_batch["batch_label"] = label
                next_batch["display_tags"] = ["流水规则", label]
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

    def _require_relation_command_service(self) -> Any:
        if self._relation_command_service is None:
            raise ValueError("bank_flow_rule_batch_relation_command_unavailable")
        return self._relation_command_service

    @staticmethod
    def _relation_idempotency_key(batch: dict[str, object], *, operation: str) -> str:
        return ":".join(
            [
                "bank_flow_rule_batch",
                operation,
                str(batch.get("batch_id") or ""),
                str(batch.get("relation_case_id") or batch.get("batch_id") or ""),
                str(batch.get("version") or ""),
            ]
        )

    @staticmethod
    def _relation_command_error(exc: Any) -> BankBatchRelationMutationError:
        if exc.error_code in {"workbench_relation_read_model_not_fresh", "workbench_relation_read_model_unavailable"}:
            return BankBatchRelationMutationError(
                "bank_flow_rule_batch_relation_read_model_not_fresh",
                "bank_flow_rule_batch_relation_read_model_not_fresh",
                payload=exc.payload,
            )
        if exc.error_code == "workbench_relation_active_row_conflict":
            return BankBatchRelationMutationError(
                "bank_flow_rule_batch_relation_active_row_conflict",
                "bank_flow_rule_batch_relation_active_row_conflict",
                payload=exc.payload,
            )
        if exc.error_code == "workbench_relation_not_found":
            return BankBatchRelationMutationError(
                "bank_flow_rule_batch_relation_not_found",
                "bank_flow_rule_batch_relation_not_found",
                payload=exc.payload,
            )
        return BankBatchRelationMutationError(exc.error_code, exc.error_code, payload=exc.payload)

    def tag_selection_payload(self) -> dict[str, Any]:
        return self._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload()

    def update_tag_selection(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        result = self._app_settings_service.update_bank_flow_rule_batch_tag_rules(
            payload,
            actor_id=actor_id,
        )
        requested_version = int(
            BankTransactionCategoryService._normalize_version(
                payload.get("expected_version", payload.get("version", 0))
            )
        )
        if int(result.get("version") or 0) == requested_version:
            return result
        self.enqueue_background_refresh(
            ["all"],
            reason="bank_flow_rule_batch_tag_rules_changed",
            metadata=self._read_model_refresh_metadata_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE),
        )
        return result
