from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import re
from time import perf_counter
from typing import Any, Callable

from fin_ops_platform.services.workbench_free_matching_engine import (
    FormalRelationMatchResult,
    FormalRelationPlan,
    FormalRelationSearchLimits,
    WorkbenchFreeMatchingEngine,
)
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandService


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
LOGGER = logging.getLogger(__name__)
AUTO_RELATION_ACTOR = "system:workbench-deterministic-relation"


@dataclass(frozen=True, slots=True)
class WorkbenchFormalRelationCommand:
    plans: tuple[FormalRelationPlan, ...]
    batch_hash: str
    scope_keys: tuple[str, ...]
    idempotency_key: str
    request_fingerprint: str
    payload: dict[str, Any]
    refresh_metadata: dict[str, object]
    tenant_id: str = "default"
    actor_id: str = AUTO_RELATION_ACTOR
    action_name: str = "confirm_link"

    @classmethod
    def from_match_result(
        cls,
        result: FormalRelationMatchResult,
        *,
        batch_hash: str,
        request_id: str,
    ) -> "WorkbenchFormalRelationCommand":
        plans = tuple(sorted(result.plans, key=lambda plan: plan.relation_fingerprint))
        if not plans:
            raise ValueError("A formal relation command requires at least one plan.")
        scope_keys = tuple(sorted({scope for plan in plans for scope in plan.scope_keys}))
        fingerprints = [plan.relation_fingerprint for plan in plans]
        fingerprint_payload = {
            "batch_hash": batch_hash,
            "relation_fingerprints": fingerprints,
            "rule_versions": sorted({plan.rule_version for plan in plans}),
        }
        request_fingerprint = sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        row_types = {row_type for plan in plans for row_type in plan.row_types}
        downstream = {"search"}
        if "bank" in row_types:
            downstream.update({"bank_detail", "oa_pending_payment"})
        if "invoice" in row_types:
            downstream.update(
                {
                    "cost_statistics",
                    "input_invoice_usage",
                    "invoice_lifecycle",
                    "output_invoice_collection",
                    "pending_invoice",
                }
            )
        payload = {
            "batch_hash": batch_hash,
            "relation_fingerprints": fingerprints,
            "request_id": str(request_id or "").strip(),
        }
        return cls(
            plans=plans,
            batch_hash=batch_hash,
            scope_keys=scope_keys,
            idempotency_key=f"workbench:formal-relation-batch:{request_fingerprint}",
            request_fingerprint=request_fingerprint,
            payload=payload,
            refresh_metadata={
                "refresh_reason": "workbench_relation_changed",
                "origin": "system_deterministic",
                "downstream_scope_types": sorted(downstream),
                "row_ids": sorted({row_id for plan in plans for row_id in plan.row_ids}),
                "case_ids": sorted({plan.case_id for plan in plans}),
            },
        )


class WorkbenchMatchingOrchestrator:
    """Bulk canonical facts -> pure matcher -> one formal relation UoW."""

    def __init__(
        self,
        *,
        fact_repository: Any,
        matcher: WorkbenchFreeMatchingEngine,
        relation_uow: Any,
        relation_command_factory: Callable[[Any], WorkbenchRelationCommandService] | None = None,
        source_versions_provider: Callable[[], dict[str, object]] | None = None,
        search_limits: FormalRelationSearchLimits | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._fact_repository = fact_repository
        self._matcher = matcher
        self._relation_uow = relation_uow
        self._relation_command_factory = relation_command_factory or self._default_relation_command
        self._source_versions_provider = source_versions_provider
        self._search_limits = search_limits or FormalRelationSearchLimits()
        self._logger = logger or LOGGER

    def run(
        self,
        *,
        changed_scope_months: list[str],
        reason: str,
        request_id: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started_at = perf_counter()
        scope_months = self._normalize_scope_months(changed_scope_months)
        normalized_reason = self._required_text(reason, "reason")
        normalized_request_id = self._required_text(request_id, "request_id")
        source_versions = self._source_versions()
        batch = self._fact_repository.load_batch(scope_months, source_versions=source_versions)
        match_result = self._matcher.plan_relations(batch, self._search_limits)
        summary: dict[str, Any] = {
            "request_id": normalized_request_id,
            "reason": normalized_reason,
            "scope_months": scope_months,
            "processed_months": list(scope_months),
            "planned_relation_count": len(match_result.plans),
            "created_relation_count": 0,
            "extended_relation_count": 0,
            "preserved_active_count": match_result.preserved_active_count,
            "blocked_count": sum(count for _reason, count in match_result.blocked_reason_counts),
            "ambiguous_component_count": match_result.ambiguous_component_count,
            "resource_limited_count": match_result.resource_limited_component_count,
            "unsafe_component_count": match_result.unsafe_component_count,
            "blocked_reason_counts": dict(match_result.blocked_reason_counts),
            "relation_ids": [],
            "outbox_event_ids": [],
            "idempotent_replay": False,
            "duration_ms": 0,
        }
        if match_result.plans:
            command = WorkbenchFormalRelationCommand.from_match_result(
                match_result,
                batch_hash=batch.batch_hash,
                request_id=normalized_request_id,
            )

            def apply_formal_relations(context: Any) -> dict[str, Any]:
                service = self._relation_command_factory(context)
                return service.confirm_formal_relation_plans(
                    list(command.plans),
                    actor_id=AUTO_RELATION_ACTOR,
                )

            write_result = self._relation_uow.run(command, apply_formal_relations)
            relations = [item for item in list(write_result.get("relations") or []) if isinstance(item, dict)]
            summary["created_relation_count"] = sum(1 for plan in command.plans if not plan.target_case_id)
            summary["extended_relation_count"] = sum(1 for plan in command.plans if plan.target_case_id)
            summary["relation_ids"] = [
                str(relation.get("case_id") or "")
                for relation in relations
                if str(relation.get("case_id") or "")
            ]
            summary["outbox_event_ids"] = list(write_result.get("outbox_event_ids") or [])
            summary["idempotent_replay"] = bool(write_result.get("idempotent_replay"))
        summary["duration_ms"] = max(0, int((perf_counter() - started_at) * 1000))
        self._logger.info(
            "workbench_matching.formal_relations request_id=%s scopes=%s planned=%s created=%s extended=%s blocked=%s duration_ms=%s",
            normalized_request_id,
            scope_months,
            summary["planned_relation_count"],
            summary["created_relation_count"],
            summary["extended_relation_count"],
            summary["blocked_count"],
            summary["duration_ms"],
        )
        if progress_callback is not None:
            progress_callback(deepcopy(summary))
        return summary

    @staticmethod
    def _default_relation_command(context: Any) -> WorkbenchRelationCommandService:
        return WorkbenchRelationCommandService(
            relation_repository=context.pair_relations,
            idempotency_store=context.idempotency_store,
            require_fresh_relations=False,
        )

    def _source_versions(self) -> dict[str, object]:
        if self._source_versions_provider is None:
            return {}
        payload = self._source_versions_provider()
        if not isinstance(payload, dict):
            raise ValueError("source_versions_provider must return a dict.")
        return dict(payload)

    @staticmethod
    def _normalize_scope_months(changed_scope_months: list[str]) -> list[str]:
        if not isinstance(changed_scope_months, list):
            raise TypeError("changed_scope_months must be a list.")
        normalized: list[str] = []
        for raw_month in changed_scope_months:
            month = str(raw_month or "").strip()
            if not MONTH_RE.fullmatch(month):
                raise ValueError("changed_scope_months values must be YYYY-MM.")
            if not 1 <= int(month[-2:]) <= 12:
                raise ValueError("changed_scope_months values must contain a valid calendar month.")
            if month not in normalized:
                normalized.append(month)
        if not normalized:
            raise ValueError("changed_scope_months must include at least one month.")
        return normalized

    @staticmethod
    def _required_text(value: object, field_name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{field_name} is required.")
        return normalized
