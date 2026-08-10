from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.bank_batch_application_service import (
    MONTH_SCOPE_RE,
    BankBatchApplicationService,
    BankBatchPersistenceError,
    BankBatchRelationMutationError,
    canonical_snapshot_version,
)
from fin_ops_platform.services.bank_batch_service import (
    BANK_FLOW_RULE_BATCH_ID_PREFIX,
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
    BankBatchService,
)
from fin_ops_platform.services.bank_flow_rule_batch_canonical_query import (
    bank_flow_rule_batch_candidate_guard,
    bank_flow_rule_batch_effective_categories,
    bank_flow_rule_batch_rule_proof,
    bank_flow_rule_batch_selected_row_proofs,
    build_live_bank_flow_rule_batch_service,
    eligible_bank_flow_rule_batch_codes,
)


class BankFlowRuleBatchPersistenceError(BankBatchPersistenceError):
    error_code = "bank_flow_rule_batch_persistence_failed"


class BankFlowRuleBatchApplicationService(BankBatchApplicationService):
    """Application boundary for 流水规则批量处理."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._query_repository = self._bank_batch_query_repository

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
        read_page = getattr(self._query_repository, "read_page", None)
        if not callable(read_page):
            raise RuntimeError("bank_flow_rule_batch canonical query repository requires read_page.")
        page_result = read_page(
            filters,
            summary_filters=summary_filters,
            page=pagination["page"] if pagination is not None else 1,
            page_size=pagination["page_size"] if pagination is not None else None,
        )
        tag_policy = page_result.get("tag_policy")
        tag_policy = tag_policy if isinstance(tag_policy, dict) else {}
        definitions_by_code = {
            str(definition.get("code") or "").strip(): dict(definition)
            for definition in list(tag_policy.get("active_tags") or [])
            if isinstance(definition, dict) and str(definition.get("code") or "").strip()
        }
        eligible_tag_codes = self._eligible_bank_flow_rule_batch_tag_codes(tag_policy)
        live_batch_service = self._live_batch_service(
            page_result,
            eligible_tag_codes=eligible_tag_codes,
        )
        live_batches = self._public_batches(
            live_batch_service.list_batches(
                {"relation_mode": relation_mode}
            )
        )
        batches_for_summary = self._filter_batches(live_batches, summary_filters)
        filtered_batches = self._filter_batches(live_batches, filters)
        filtered_batches.sort(key=lambda batch: str(batch.get("batch_id") or ""))
        filtered_batches.sort(key=lambda batch: str(batch.get("scope_month") or ""), reverse=True)
        total = len(filtered_batches)
        if pagination is not None:
            offset = (pagination["page"] - 1) * pagination["page_size"]
            filtered_batches = filtered_batches[offset : offset + pagination["page_size"]]
        batches = self.resolve_labels(
            filtered_batches,
            definitions_by_code=definitions_by_code,
        )
        payload: dict[str, object] = {
            "summary": self._summary_from_aggregates(
                self._aggregates_for_batches(batches_for_summary),
                eligible_tag_codes=eligible_tag_codes,
                definitions_by_code=definitions_by_code,
            ),
            "batches": batches,
            **self._bank_flow_pagination_payload(
                pagination,
                total=total,
            ),
        }
        return payload

    @staticmethod
    def _filter_batches(
        batches: list[dict[str, object]],
        filters: dict[str, object],
    ) -> list[dict[str, object]]:
        resolved = list(batches)
        for field_name, filter_key in (
            ("scope_month", "month"),
            ("batch_type", "type"),
            ("status", "status"),
            ("account_key", "account_key"),
            ("status_bucket", "bucket"),
        ):
            value = str(filters.get(filter_key) or "").strip()
            if value and value != "all":
                resolved = [
                    batch
                    for batch in resolved
                    if str(batch.get(field_name) or "") == value
                ]
        return resolved

    def _live_batch_service(
        self,
        page_result: dict[str, object],
        *,
        eligible_tag_codes: set[str],
    ) -> BankBatchService:
        return build_live_bank_flow_rule_batch_service(
            page_result,
            eligible_tag_codes=eligible_tag_codes,
        )

    @staticmethod
    def _aggregates_for_batches(
        batches: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        aggregates: dict[tuple[str, str], dict[str, object]] = {}
        for batch in batches:
            batch_type = str(batch.get("batch_type") or "").strip()
            status = str(batch.get("status") or "").strip()
            if not batch_type or status not in {"draft", "submitted", "withdrawn"}:
                continue
            key = (batch_type, status)
            aggregate = aggregates.setdefault(
                key,
                {
                    "batch_type": batch_type,
                    "presented_status": status,
                    "batch_count": 0,
                    "row_count": 0,
                    "batch_label": str(batch.get("batch_label") or batch_type),
                    "category_primary_label": str(batch.get("category_primary_label") or ""),
                    "category_sub_label": str(batch.get("category_sub_label") or ""),
                    "total_amount": Decimal("0.00"),
                },
            )
            aggregate["batch_count"] = int(aggregate["batch_count"]) + 1
            aggregate["row_count"] = int(aggregate["row_count"]) + int(
                batch.get("row_count") or len(list(batch.get("row_ids") or []))
            )
            try:
                amount = Decimal(str(batch.get("total_amount") or "0").replace(",", ""))
            except (InvalidOperation, ValueError):
                amount = Decimal("0.00")
            aggregate["total_amount"] = Decimal(str(aggregate["total_amount"])) + amount
        return [
            {
                **aggregate,
                "total_amount": f"{Decimal(str(aggregate['total_amount'])):.2f}",
            }
            for aggregate in aggregates.values()
        ]

    def active_relation_source_bundle_for_bank_rows(
        self,
        bank_rows: list[dict[str, object]],
        *,
        scope_key: str | None = None,
    ) -> dict[str, object]:
        row_ids = self._dedupe_ordered(
            [
                str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()
                for row in list(bank_rows or [])
                if isinstance(row, dict)
            ]
        )
        if not row_ids:
            return {"rows": [], "source_versions": {}}
        repository = getattr(self, "_relation_source_repository", None)
        load_bundle = getattr(repository, "workbench_relation_source_bundle_from_source", None)
        if not callable(load_bundle):
            raise RuntimeError(
                "bank_flow_rule_batch requires canonical workbench relation source repository."
            )
        months = self._months_for_bank_rows(bank_rows)
        resolved_scope_key = str(scope_key or "").strip()
        if not resolved_scope_key:
            resolved_scope_key = months[0] if len(months) == 1 else "all"
        payload = load_bundle(scope_key=resolved_scope_key, row_ids=row_ids)
        if not isinstance(payload, dict):
            raise RuntimeError("bank_flow_rule_batch canonical workbench relation source returned invalid payload.")
        rows = [dict(row) for row in list(payload.get("rows") or []) if isinstance(row, dict)]
        source_versions = payload.get("source_versions")
        return {
            "rows": rows,
            "source_versions": dict(source_versions) if isinstance(source_versions, dict) else {},
        }

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
        aggregate_by_code = {
            str(row.get("batch_type") or "").strip(): row
            for row in rows
            if str(row.get("batch_type") or "").strip()
        }
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
            aggregate = aggregate_by_code.get(code) or {}
            if not definition:
                definition = {
                    "code": code,
                    "label": str(aggregate.get("batch_label") or code),
                    "output_primary_label": str(aggregate.get("category_primary_label") or ""),
                    "output_sub_label": str(aggregate.get("category_sub_label") or ""),
                }
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
                "total_row_count": 0,
                "draft_row_count": 0,
                "submitted_row_count": 0,
                "withdrawn_row_count": 0,
                "total_amount": Decimal("0.00"),
            }
        total_amount = Decimal("0.00")
        row_counts = {"draft": 0, "submitted": 0, "withdrawn": 0}
        for row in rows:
            code = str(row.get("batch_type") or "").strip()
            status = str(row.get("presented_status") or "").strip()
            count = max(int(row.get("batch_count") or 0), 0)
            row_count = max(int(row.get("row_count") or 0), 0)
            try:
                amount = Decimal(str(row.get("total_amount") or "0").replace(",", ""))
            except (InvalidOperation, ValueError):
                amount = Decimal("0.00")
            if status in counts:
                counts[status] += count
            if status in row_counts:
                row_counts[status] += row_count
            total_amount += amount
            category = categories.get(code)
            if category is None:
                continue
            category["total"] = int(category["total"]) + count
            category["total_row_count"] = int(category["total_row_count"]) + row_count
            if status in counts:
                category[status] = int(category[status]) + count
            row_count_key = f"{status}_row_count"
            if row_count_key in category:
                category[row_count_key] = int(category[row_count_key]) + row_count
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
            "total_row_count": sum(row_counts.values()),
            "draft_row_count": row_counts["draft"],
            "submitted_row_count": row_counts["submitted"],
            "withdrawn_row_count": row_counts["withdrawn"],
            "conflict_count": counts["conflict"],
            "stale_count": counts["stale"],
            "total_amount": f"{total_amount:.2f}",
            "categories": category_payloads,
        }

    def _ensure_formal_bank_flow_rule_batch_runtime_item(
        self,
        batch_id: str,
        *,
        allowed_statuses: set[str],
    ) -> bool:
        try:
            batch = self._bank_batch_service.get_batch(batch_id)
            return str(batch.get("status") or "").strip() in allowed_statuses
        except KeyError:
            return self._restore_formal_bank_flow_rule_batch_runtime_item(
                batch_id,
                allowed_statuses=allowed_statuses,
            )

    def _restore_formal_bank_flow_rule_batch_runtime_item(
        self,
        batch_id: str,
        *,
        allowed_statuses: set[str],
    ) -> bool:
        normalized_batch_id = str(batch_id or "").strip()
        read_batch = getattr(self._query_repository, "read_batch", None)
        replace_snapshot = getattr(self._bank_batch_service, "replace_snapshot", None)
        snapshot = getattr(self._bank_batch_service, "snapshot", None)
        if not normalized_batch_id or not callable(read_batch) or not callable(replace_snapshot):
            return False
        batch = read_batch(normalized_batch_id)
        if (
            not isinstance(batch, dict)
            or str(batch.get("status") or "").strip() not in allowed_statuses
        ):
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

    def _prepare_batch_for_submit(
        self,
        batch_id: str,
        *,
        relation_mode: str,
        scope_month: str | None = None,
    ) -> dict[str, object] | None:
        if relation_mode != BANK_FLOW_RULE_BATCH_RELATION_MODE:
            super()._prepare_batch_for_submit(batch_id, relation_mode=relation_mode)
            return None
        try:
            current = self._bank_batch_service.get_batch(batch_id)
        except KeyError:
            current = None
        if isinstance(current, dict) and str(current.get("status") or "") == "submitted":
            return None
        if not str(scope_month or "").strip():
            if self._ensure_formal_bank_flow_rule_batch_runtime_item(
                batch_id,
                allowed_statuses={"submitted"},
            ):
                return None
            raise BankBatchRelationMutationError(
                "bank_flow_rule_batch_candidate_conflict",
                "流水规则候选月份缺失，请刷新列表后重试。",
            )
        candidate, source = self._live_candidate(batch_id, scope_month)
        snapshot = self._bank_batch_service.snapshot()
        batches = snapshot.get("batches") if isinstance(snapshot, dict) else None
        self._bank_batch_service.replace_snapshot(
            {
                **(snapshot if isinstance(snapshot, dict) else {}),
                "batches": {
                    **(batches if isinstance(batches, dict) else {}),
                    batch_id: candidate,
                },
            }
        )
        return {
            **bank_flow_rule_batch_candidate_guard(candidate),
            "rule_proof": bank_flow_rule_batch_rule_proof(
                source.get("tag_policy") if isinstance(source.get("tag_policy"), dict) else {},
                str(candidate.get("batch_type") or ""),
            ),
        }

    def _live_candidate(
        self,
        batch_id: str,
        scope_month: str | None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        source = self._live_candidate_source(scope_month)
        tag_policy = source.get("tag_policy") if isinstance(source, dict) else None
        tag_policy = tag_policy if isinstance(tag_policy, dict) else {}
        live_service = self._live_batch_service(
            source if isinstance(source, dict) else {},
            eligible_tag_codes=self._eligible_bank_flow_rule_batch_tag_codes(tag_policy),
        )
        try:
            candidate = live_service.get_batch(batch_id)
        except KeyError as exc:
            raise BankBatchRelationMutationError(
                "bank_flow_rule_batch_candidate_conflict",
                "流水规则候选已变化或被占用，请刷新列表后重试。",
            ) from exc
        normalized_month = str(scope_month or "").strip()
        if (
            str(candidate.get("status") or "") != "draft"
            or str(candidate.get("scope_month") or "") != normalized_month
        ):
            raise BankBatchRelationMutationError(
                "bank_flow_rule_batch_candidate_conflict",
                "流水规则候选已变化或被占用，请刷新列表后重试。",
            )
        return candidate, source

    def _live_candidate_source(self, scope_month: str | None) -> dict[str, object]:
        normalized_month = str(scope_month or "").strip()
        if not MONTH_SCOPE_RE.match(normalized_month):
            raise BankBatchRelationMutationError(
                "invalid_bank_flow_rule_batch_month",
                "流水规则候选月份无效，请刷新列表后重试。",
            )
        read_page = getattr(self._query_repository, "read_page", None)
        if not callable(read_page):
            raise RuntimeError("bank_flow_rule_batch canonical query repository requires read_page.")
        source = read_page(
            {"month": normalized_month, "bucket": "unsubmitted"},
            summary_filters={"month": normalized_month},
            page=1,
            page_size=None,
        )
        return source if isinstance(source, dict) else {}

    def _live_selected_rows(
        self,
        row_ids: list[str],
        *,
        scope_month: str | None,
    ) -> tuple[
        list[dict[str, object]],
        dict[str, dict[str, object]],
        dict[str, object],
    ]:
        source = self._live_candidate_source(scope_month)
        normalized_row_ids = self._dedupe_ordered(
            [
                str(row_id).strip()
                for row_id in row_ids
                if str(row_id).strip()
            ]
        )
        rows_by_id = {
            str(row.get("id") or row.get("transaction_id") or "").strip(): dict(row)
            for row in list(source.get("candidate_rows") or [])
            if isinstance(row, dict)
        }
        if not normalized_row_ids or any(row_id not in rows_by_id for row_id in normalized_row_ids):
            raise BankBatchRelationMutationError(
                "bank_flow_rule_batch_candidate_conflict",
                "所选流水已变化或被占用，请刷新列表后重试。",
            )
        rows = [rows_by_id[row_id] for row_id in normalized_row_ids]
        return rows, bank_flow_rule_batch_effective_categories(source), source

    @staticmethod
    def _requirement_metadata_from_rule_proof(
        rule_proof: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if not isinstance(rule_proof, dict):
            return None
        return {
            "paired_requires_oa": bool(rule_proof.get("requires_oa")),
            "paired_requires_invoice": bool(rule_proof.get("requires_invoice")),
            "paired_requirement_tag_code": str(rule_proof.get("tag_code") or ""),
            "paired_requirement_version": int(rule_proof.get("rule_version") or 1),
        }

    @staticmethod
    def _canonical_selected_source_versions(
        bank_rows: list[dict[str, object]],
        categories_by_transaction_id: dict[str, dict[str, object]],
        tag_policy: dict[str, object],
        relation_source_versions: dict[str, object],
    ) -> dict[str, object]:
        category_proof_rows = [
            {
                "transaction_id": str(row.get("id") or row.get("transaction_id") or "").strip(),
                "category_code": str(
                    categories_by_transaction_id.get(
                        str(row.get("id") or row.get("transaction_id") or "").strip(),
                        {},
                    ).get("effective_category_code")
                    or ""
                ),
                "category_source": str(
                    categories_by_transaction_id.get(
                        str(row.get("id") or row.get("transaction_id") or "").strip(),
                        {},
                    ).get("effective_category_source")
                    or ""
                ),
                "category_version": int(
                    categories_by_transaction_id.get(
                        str(row.get("id") or row.get("transaction_id") or "").strip(),
                        {},
                    ).get("category_version")
                    or 0
                ),
            }
            for row in bank_rows
        ]
        category_proof_rows.sort(key=lambda row: row["transaction_id"])
        source_versions: dict[str, object] = {
            "bank_flow_rule_batch_schema_version": BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            "bank_flow_rule_batch_eligibility_version": canonical_snapshot_version(
                sorted(eligible_bank_flow_rule_batch_codes(tag_policy))
            ),
            "category_source_proof": {
                "source": "bank_flow_rule_batch_canonical_query",
                "row_count": len(category_proof_rows),
                "membership_category_digest": canonical_snapshot_version(category_proof_rows),
            },
        }
        if relation_source_versions:
            source_versions["workbench_relation_source_versions"] = dict(
                relation_source_versions
            )
        return source_versions

    def submit_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        note: str | None,
        relation_mode: str = BANK_FLOW_RULE_BATCH_RELATION_MODE,
        persist: bool = True,
        scope_month: str | None = None,
    ) -> dict[str, object]:
        if relation_mode != BANK_FLOW_RULE_BATCH_RELATION_MODE:
            raise BankBatchRelationMutationError(
                "invalid_bank_flow_rule_batch_relation_mode",
                "流水规则批次服务只接受 bank_flow_rule_batch relation mode。",
            )
        previous_batch_snapshot = self._bank_batch_service.snapshot()
        relation_snapshot_port = getattr(self, "_pair_relation_snapshot_port", None)
        snapshot_case_ids = getattr(relation_snapshot_port, "snapshot_case_ids", None)
        previous_relation_snapshot = (
            snapshot_case_ids([batch_id])
            if callable(snapshot_case_ids)
            else {}
        )
        try:
            candidate_guard = self._prepare_batch_for_submit(
                batch_id,
                relation_mode=relation_mode,
                scope_month=scope_month,
            )
            before_batch = self._bank_batch_service.get_batch(batch_id)
            already_submitted = str(before_batch.get("status") or "") == "submitted"
            batch = self._bank_batch_service.submit_batch(
                batch_id,
                actor=actor,
                expected_version=expected_version,
                note=note,
            )
            if not already_submitted:
                rule_proof = (
                    candidate_guard.get("rule_proof")
                    if isinstance(candidate_guard, dict)
                    and isinstance(candidate_guard.get("rule_proof"), dict)
                    else None
                )
                self._confirm_relation_for_batch(
                    batch,
                    actor=actor,
                    note=note,
                    relation_mode=relation_mode,
                    requirement_metadata=self._requirement_metadata_from_rule_proof(rule_proof),
                )
            return self._mutation_result(
                batch,
                status="submitted",
                persist=persist,
                candidate_guard=candidate_guard,
            )
        except Exception:
            self._restore_batch_service_snapshot(self._bank_batch_service, previous_batch_snapshot)
            restore_case_ids = getattr(relation_snapshot_port, "restore_case_ids", None)
            if callable(restore_case_ids):
                restore_case_ids(previous_relation_snapshot, case_ids=[batch_id])
            raise

    def submit_selected_rows(
        self,
        *,
        row_ids: list[str],
        actor: str,
        note: str | None,
        relation_mode: str = BANK_FLOW_RULE_BATCH_RELATION_MODE,
        scope_month: str | None = None,
    ) -> dict[str, object]:
        if relation_mode != BANK_FLOW_RULE_BATCH_RELATION_MODE:
            raise BankBatchRelationMutationError(
                "invalid_bank_flow_rule_batch_relation_mode",
                "流水规则批次服务只接受 bank_flow_rule_batch relation mode。",
            )
        bank_rows, categories_by_transaction_id, source = self._live_selected_rows(
            row_ids,
            scope_month=scope_month,
        )
        if self._selected_rows_include_internal_transfer(bank_rows, categories_by_transaction_id):
            raise BankBatchRelationMutationError(
                "bank_flow_rule_batch_selection_internal_transfer_requires_pair",
                "内部往来批次请使用单批提交。",
            )
        previous_batch_snapshot = self._bank_batch_service.snapshot()
        relation_snapshot_port = getattr(self, "_pair_relation_snapshot_port", None)
        previous_relation_snapshot: dict[str, object] = {}
        submitted_batch_id = ""
        try:
            months = self._months_for_bank_rows(bank_rows)
            relation_bundle = self.active_relation_source_bundle_for_bank_rows(
                bank_rows,
                scope_key=months[0] if len(months) == 1 else "all",
            )
            relation_source_versions = relation_bundle.get("source_versions")
            tag_policy = source.get("tag_policy")
            tag_policy = tag_policy if isinstance(tag_policy, dict) else {}
            source_versions = self._canonical_selected_source_versions(
                bank_rows,
                categories_by_transaction_id,
                tag_policy,
                (
                    dict(relation_source_versions)
                    if isinstance(relation_source_versions, dict)
                    else {}
                ),
            )
            batch = self._bank_batch_service.submit_selected_rows(
                bank_rows=bank_rows,
                categories_by_transaction_id=categories_by_transaction_id,
                active_relations=[
                    dict(row)
                    for row in list(source.get("active_relations") or [])
                    if isinstance(row, dict)
                ],
                source_versions=source_versions,
                eligible_batch_types=eligible_bank_flow_rule_batch_codes(tag_policy),
                row_ids=row_ids,
                actor=actor,
                note=note,
                relation_mode=relation_mode,
            )
            submitted_batch_id = str(batch.get("batch_id") or "").strip()
            snapshot_case_ids = getattr(
                relation_snapshot_port,
                "snapshot_case_ids",
                None,
            )
            if callable(snapshot_case_ids) and submitted_batch_id:
                previous_relation_snapshot = snapshot_case_ids(
                    [submitted_batch_id]
                )
            candidate_guard = {
                **bank_flow_rule_batch_candidate_guard(batch),
                "guard_mode": "selected_rows",
                "selected_row_proofs": bank_flow_rule_batch_selected_row_proofs(
                    bank_rows,
                    categories_by_transaction_id,
                ),
                "rule_proof": bank_flow_rule_batch_rule_proof(
                    tag_policy,
                    str(batch.get("batch_type") or ""),
                ),
            }
            self._confirm_relation_for_batch(
                batch,
                actor=actor,
                note=note,
                relation_mode=relation_mode,
                requirement_metadata=self._requirement_metadata_from_rule_proof(
                    candidate_guard["rule_proof"]
                ),
            )
            return self._mutation_result(
                batch,
                status="submitted",
                persist=True,
                candidate_guard=candidate_guard,
            )
        except Exception:
            self._restore_batch_service_snapshot(self._bank_batch_service, previous_batch_snapshot)
            restore_case_ids = getattr(relation_snapshot_port, "restore_case_ids", None)
            if callable(restore_case_ids) and submitted_batch_id:
                restore_case_ids(
                    previous_relation_snapshot,
                    case_ids=[submitted_batch_id],
                )
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

    def detail_payload(
        self,
        batch_id: str,
        *,
        scope_month: str | None = None,
    ) -> dict[str, object]:
        normalized_month = str(scope_month or "").strip()
        if normalized_month and not MONTH_SCOPE_RE.match(normalized_month):
            raise BankBatchRelationMutationError(
                "invalid_bank_flow_rule_batch_month",
                "流水规则候选月份无效，请刷新列表后重试。",
            )
        read_detail = getattr(self._query_repository, "read_detail", None)
        if not callable(read_detail):
            raise RuntimeError("bank_flow_rule_batch canonical query repository requires read_detail.")
        detail = read_detail(batch_id)
        if not isinstance(detail, dict):
            if not normalized_month:
                raise KeyError("bank_flow_rule_batch_not_found")
            candidate, source = self._live_candidate(batch_id, normalized_month)
            detail = {
                "batch": candidate,
                "rows": source.get("candidate_rows"),
                "events": [],
                "tag_policy": source.get("tag_policy"),
                "tag_dictionary": source.get("tag_dictionary"),
            }
        batch = detail.get("batch")
        if not isinstance(batch, dict):
            raise KeyError("bank_flow_rule_batch_not_found")
        public_batch = self._public_batch(batch)
        if public_batch is None:
            raise KeyError("bank_flow_rule_batch_not_found")
        tag_policy = detail.get("tag_policy")
        tag_policy = tag_policy if isinstance(tag_policy, dict) else {}
        definitions_by_code = {
            str(definition.get("code") or "").strip(): dict(definition)
            for definition in list(tag_policy.get("active_tags") or [])
            if isinstance(definition, dict) and str(definition.get("code") or "").strip()
        }
        source_rows = [
            dict(row)
            for row in list(detail.get("rows") or [])
            if isinstance(row, dict)
        ]
        categories_by_transaction_id = bank_flow_rule_batch_effective_categories(
            {
                "rows": source_rows,
                "tag_dictionary": detail.get("tag_dictionary"),
            }
        )
        for row in source_rows:
            transaction_id = str(row.get("id") or "").strip()
            category = categories_by_transaction_id.get(transaction_id, {})
            category_code = str(
                category.get("effective_category_code")
                or category.get("category_code")
                or ""
            ).strip()
            definition = definitions_by_code.get(category_code, {})
            if not category_code:
                continue
            row["category_code"] = category_code
            row["category_source"] = str(
                category.get("effective_category_source")
                or category.get("category_source")
                or ""
            )
            row["category_label"] = str(
                category.get("effective_category_label")
                or category.get("category_label")
                or definition.get("label")
                or definition.get("output_sub_label")
                or definition.get("output_primary_label")
                or category_code
            )
            row["category_primary_label"] = str(
                category.get("effective_category_primary_label")
                or category.get("category_primary_label")
                or definition.get("output_primary_label")
                or row["category_label"]
            )
            row["category_sub_label"] = str(
                category.get("effective_category_sub_label")
                or category.get("category_sub_label")
                or definition.get("output_sub_label")
                or ""
            )
            row["category_label_path"] = [
                label
                for label in (
                    row["category_primary_label"],
                    row["category_sub_label"],
                )
                if label
            ]
        rows_by_id = {
            str(row.get("id") or "").strip(): row
            for row in source_rows
            if str(row.get("id") or "").strip()
        }
        row_ids = [
            str(row_id).strip()
            for row_id in list(batch.get("row_ids") or [])
            if str(row_id).strip()
        ]
        categories_by_transaction_id = {
            row_id: {
                "category_code": rows_by_id.get(row_id, {}).get("category_code"),
                "category_label": rows_by_id.get(row_id, {}).get("category_label"),
                "category_primary_label": rows_by_id.get(row_id, {}).get("category_primary_label"),
                "category_sub_label": rows_by_id.get(row_id, {}).get("category_sub_label"),
                "category_label_path": rows_by_id.get(row_id, {}).get("category_label_path"),
                "category_source": rows_by_id.get(row_id, {}).get("category_source"),
            }
            for row_id in row_ids
        }
        detail_rows = self._apply_submitted_row_tag_snapshot(
            public_batch,
            self.detail_rows(row_ids, rows_by_id, categories_by_transaction_id),
        )
        return {
            "batch": self.resolve_labels(
                [public_batch],
                definitions_by_code=definitions_by_code,
            )[0],
            "rows": detail_rows,
            "tag_counts": batch.get("tag_counts") if isinstance(batch.get("tag_counts"), dict) else {},
            "direction_counts": (
                batch.get("direction_counts")
                if isinstance(batch.get("direction_counts"), dict)
                else {}
            ),
            "categories_by_transaction_id": self._detail_categories_by_transaction_id(
                row_ids,
                categories_by_transaction_id,
                public_batch,
            ),
            "events": [
                dict(event)
                for event in list(detail.get("events") or [])
                if isinstance(event, dict)
            ],
        }

    def withdraw_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        reason: str | None,
    ) -> dict[str, object]:
        self._ensure_formal_bank_flow_rule_batch_runtime_item(
            batch_id,
            allowed_statuses={"submitted"},
        )
        return super().withdraw_batch(
            batch_id,
            actor=actor,
            expected_version=expected_version,
            reason=reason,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

    def persist_mutation(
        self,
        *,
        changed_case_ids: list[str],
        changed_scope_keys: list[str],
        changed_batch_ids: list[str] | None = None,
        candidate_guard: dict[str, object] | None = None,
    ) -> None:
        if self._state_store is None:
            return
        try:
            normalized_scope_keys = [
                str(scope_key).strip()
                for scope_key in changed_scope_keys
                if MONTH_SCOPE_RE.match(str(scope_key).strip())
            ]
            normalized_batch_ids = [
                str(batch_id).strip()
                for batch_id in list(changed_batch_ids or changed_case_ids)
                if str(batch_id).strip()
            ]
            save_mutation = getattr(self._state_store, "save_bank_flow_rule_batch_mutation", None)
            if not callable(save_mutation):
                raise RuntimeError("bank_flow_rule_batch mutation persistence requires save_bank_flow_rule_batch_mutation.")
            save_mutation(
                pair_relation_snapshot=self._pair_relation_snapshot_port.snapshot_case_ids(changed_case_ids)
                if changed_case_ids
                else self._pair_relation_snapshot_port.snapshot(),
                bank_flow_rule_batch_snapshot=self._bank_batch_public_snapshot(),
                changed_case_ids=changed_case_ids,
                changed_scope_keys=normalized_scope_keys,
                changed_batch_ids=normalized_batch_ids,
                candidate_guard=(
                    dict(candidate_guard)
                    if isinstance(candidate_guard, dict)
                    else None
                ),
            )
        except Exception as exc:
            if "bank_flow_rule_batch_candidate_guard_conflict" in str(exc):
                raise BankBatchRelationMutationError(
                    "bank_flow_rule_batch_candidate_conflict",
                    "流水规则候选已变化或被占用，请刷新列表后重试。",
                ) from exc
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
                label = (
                    self.bank_transaction_tag_label_from_definition(batch_type, definition)
                    if definition
                    else str(next_batch.get("batch_label") or batch_type)
                )
                next_batch["batch_label"] = label
                next_batch["display_tags"] = ["流水规则", label]
                next_batch["category_primary_label"] = str(
                    (definition or {}).get("output_primary_label")
                    or next_batch.get("category_primary_label")
                    or label
                )
                next_batch["category_sub_label"] = str(
                    (definition or {}).get("output_sub_label")
                    or next_batch.get("category_sub_label")
                    or ""
                )
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
        prepared = self._app_settings_service.normalize_bank_flow_rule_batch_tag_rules_update(
            payload,
            actor_id=actor_id,
        )
        previous_public = dict(prepared.get("previous_public_payload") or {})
        result = dict(prepared.get("public_payload") or {})
        if not bool(prepared.get("changed")):
            return self._tag_rule_update_response(
                result,
                changed_tag_codes=[],
                affected_scope_keys=[],
            )

        before_eligible = self._eligible_bank_flow_rule_batch_tag_codes(previous_public)
        after_eligible = self._eligible_bank_flow_rule_batch_tag_codes(result)
        changed_tag_codes = sorted(before_eligible.symmetric_difference(after_eligible))
        affected_scope_keys = self._affected_scope_keys_for_tag_rule_change(changed_tag_codes)
        prepared = {
            **prepared,
            "audit_event": {
                **dict(prepared.get("audit_event") or {}),
                "eligibility_changed_tag_codes": changed_tag_codes,
                "affected_months": affected_scope_keys,
            },
        }
        self._commit_tag_rule_update(prepared=prepared)
        return self._tag_rule_update_response(
            result,
            changed_tag_codes=changed_tag_codes,
            affected_scope_keys=affected_scope_keys,
        )

    def _affected_scope_keys_for_tag_rule_change(self, changed_tag_codes: list[str]) -> list[str]:
        if not changed_tag_codes:
            return []
        resolver = getattr(
            self._query_repository,
            "affected_scope_keys_for_tag_codes",
            None,
        )
        if callable(resolver):
            scope_keys = self._dedupe_ordered(resolver(changed_tag_codes))
        elif self._state_store_backend() in {"local_pickle", "memory"}:
            scope_keys = self._local_affected_scope_keys_for_tag_codes(changed_tag_codes)
        else:
            raise RuntimeError(
                "bank_flow_rule_batch read repository requires affected_scope_keys_for_tag_codes."
            )
        if any(not MONTH_SCOPE_RE.match(scope_key) for scope_key in scope_keys):
            raise RuntimeError("bank_flow_rule_batch tag-rule refresh requires month scopes.")
        return scope_keys

    def _local_affected_scope_keys_for_tag_codes(self, tag_codes: list[str]) -> list[str]:
        """Resolve exact local-store scopes without introducing a production scan fallback."""
        changed_codes = set(tag_codes)
        bank_rows = self.bank_transaction_rows(month="all", include_categories=False)
        categories = self.effective_categories_for_rows(bank_rows)
        affected = {
            self._month_from_bank_row(row)
            for row in bank_rows
            if str(
                (categories.get(str(row.get("id") or "").strip()) or {}).get(
                    "effective_category_code"
                )
                or (categories.get(str(row.get("id") or "").strip()) or {}).get("category_code")
                or ""
            ).strip()
            in changed_codes
        }
        return sorted(scope_key for scope_key in affected if MONTH_SCOPE_RE.match(scope_key))

    def _state_store_backend(self) -> str:
        if self._state_store is None:
            return "memory"
        storage_backend = getattr(self._state_store, "storage_backend", "")
        if callable(storage_backend):
            storage_backend = storage_backend()
        return str(storage_backend or "").strip()

    def _commit_tag_rule_update(
        self,
        *,
        prepared: dict[str, Any],
    ) -> None:
        state_store = self._state_store
        if state_store is None:
            self._app_settings_service.accept_bank_flow_rule_batch_tag_rules_update(
                next_snapshot=dict(prepared.get("next_snapshot") or {}),
                audit_event=dict(prepared.get("audit_event") or {}),
            )
            return
        if self._state_store_backend() == "postgres":
            connection = getattr(state_store, "_connection", None)
            save_settings = getattr(
                state_store,
                "save_app_settings_for_bank_flow_rule_version_in_transaction",
                None,
            )
            if connection is None or not callable(save_settings):
                raise BankFlowRuleBatchPersistenceError(
                    "bank_flow_rule_batch tag-rule transaction boundary is unavailable."
                )
            audit_event = dict(prepared.get("audit_event") or {})
            with connection.transaction() as transaction:
                saved_snapshot = save_settings(
                    dict(prepared.get("next_snapshot") or {}),
                    expected_version=int(audit_event.get("old_version") or 0),
                    transaction=transaction,
                )
                if not isinstance(saved_snapshot, dict):
                    raise AppSettingsValidationError(
                        "bank_flow_rule_batch_tag_rules_version_conflict",
                        "Bank flow rule batch tag rules version conflict.",
                    )
            self._app_settings_service.accept_bank_flow_rule_batch_tag_rules_update(
                next_snapshot=dict(saved_snapshot),
                audit_event=audit_event,
            )
            return

        next_snapshot = dict(prepared.get("next_snapshot") or {})
        save_app_settings = getattr(state_store, "save_app_settings", None)
        if not callable(save_app_settings):
            raise BankFlowRuleBatchPersistenceError(
                "bank_flow_rule_batch local settings persistence is unavailable."
            )
        save_app_settings(next_snapshot)
        self._app_settings_service.accept_bank_flow_rule_batch_tag_rules_update(
            next_snapshot=next_snapshot,
            audit_event=dict(prepared.get("audit_event") or {}),
        )

    @staticmethod
    def _tag_rule_update_response(
        payload: dict[str, Any],
        *,
        changed_tag_codes: list[str],
        affected_scope_keys: list[str],
    ) -> dict[str, Any]:
        return {
            **payload,
            "eligibility_changed": bool(changed_tag_codes),
            "eligibility_changed_tag_codes": list(changed_tag_codes),
            "affected_months": list(affected_scope_keys),
        }
