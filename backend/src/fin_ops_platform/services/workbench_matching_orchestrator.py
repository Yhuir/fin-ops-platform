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
from fin_ops_platform.services.workbench_relation_requirements import (
    build_bank_relation_requirement_metadata,
)


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
LOGGER = logging.getLogger(__name__)
AUTO_RELATION_ACTOR = "system:workbench-deterministic-relation"


@dataclass(frozen=True, slots=True)
class WorkbenchFormalRelationCommand:
    plans: tuple[FormalRelationPlan, ...]
    etc_batch_links: tuple[dict[str, Any], ...]
    batch_hash: str
    scope_keys: tuple[str, ...]
    idempotency_key: str
    request_fingerprint: str
    payload: dict[str, Any]
    refresh_metadata: dict[str, object]
    paired_requirements_by_case_id: dict[str, dict[str, object]]
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
        etc_batch_links: tuple[dict[str, Any], ...] = (),
        paired_requirements_by_case_id: dict[str, dict[str, object]] | None = None,
    ) -> "WorkbenchFormalRelationCommand":
        plans = tuple(sorted(result.plans, key=lambda plan: plan.relation_fingerprint))
        links = tuple(sorted((deepcopy(link) for link in etc_batch_links), key=lambda link: str(link["case_id"])))
        if not plans and not links:
            raise ValueError("A formal relation command requires at least one plan or ETC batch link.")
        scope_keys = tuple(
            sorted(
                {
                    *{scope for plan in plans for scope in plan.scope_keys},
                    *{
                        scope
                        for link in links
                        for scope in _etc_batch_link_refresh_scope_keys(link)
                    },
                }
            )
        )
        fingerprints = [plan.relation_fingerprint for plan in plans]
        requirements = {
            str(case_id): deepcopy(metadata)
            for case_id, metadata in dict(paired_requirements_by_case_id or {}).items()
        }
        if set(requirements) - {plan.case_id for plan in plans}:
            raise ValueError("Paired requirements must belong to the formal relation plan batch.")
        fingerprint_payload = {
            "batch_hash": batch_hash,
            "relation_fingerprints": fingerprints,
            "rule_versions": sorted({plan.rule_version for plan in plans}),
            "etc_batch_links": links,
            "paired_requirements_by_case_id": requirements,
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
            "etc_batch_ids": [str(link["external_etc_batch_id"]) for link in links],
        }
        return cls(
            plans=plans,
            etc_batch_links=links,
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
                "case_ids": sorted({plan.case_id for plan in plans} | {str(link["case_id"]) for link in links}),
            },
            paired_requirements_by_case_id=requirements,
            action_name="confirm_link" if plans else "enrich_etc_relation",
        )


def _etc_batch_link_refresh_scope_keys(link: dict[str, Any]) -> tuple[str, ...]:
    scope_keys = {
        str(scope).strip()
        for scope in list(link.get("scope_keys") or [])
        if str(scope).strip()
    }
    specific_scope_keys = scope_keys - {"all"}
    if specific_scope_keys:
        return tuple(sorted(specific_scope_keys))
    return ("all",) if "all" in scope_keys else ()


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
        bank_flow_rule_tag_rules_payload: Callable[[], dict[str, object]],
        search_limits: FormalRelationSearchLimits | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._fact_repository = fact_repository
        self._matcher = matcher
        self._relation_uow = relation_uow
        self._relation_command_factory = relation_command_factory or self._default_relation_command
        self._source_versions_provider = source_versions_provider
        self._bank_flow_rule_tag_rules_payload = bank_flow_rule_tag_rules_payload
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
        requested_scope_months = self._normalize_scope_months(changed_scope_months)
        normalized_reason = self._required_text(reason, "reason")
        normalized_request_id = self._required_text(request_id, "request_id")
        source_versions = self._source_versions()
        etc_batch_link_candidates = self._fact_repository.load_etc_batch_link_candidates(
            requested_scope_months
        )
        scope_months = self._expanded_etc_batch_link_scopes(
            requested_scope_months,
            etc_batch_link_candidates,
        )
        batch = self._fact_repository.load_batch(scope_months, source_versions=source_versions)
        match_result = self._matcher.plan_relations(batch, self._search_limits)
        etc_batch_links, ambiguous_etc_batch_link_count, unowned_etc_batch_link_count = self._resolve_etc_batch_links(
            batch,
            match_result,
            etc_batch_link_candidates,
        )
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
            "enriched_relation_count": 0,
            "ambiguous_etc_batch_link_count": ambiguous_etc_batch_link_count,
            "unowned_etc_batch_link_count": unowned_etc_batch_link_count,
            "outbox_event_ids": [],
            "idempotent_replay": False,
            "duration_ms": 0,
        }
        if match_result.plans or etc_batch_links:
            paired_requirements_by_case_id = self._paired_requirements_by_case_id(
                match_result,
                etc_batch_links=etc_batch_links,
            )
            command = WorkbenchFormalRelationCommand.from_match_result(
                match_result,
                batch_hash=batch.batch_hash,
                request_id=normalized_request_id,
                etc_batch_links=etc_batch_links,
                paired_requirements_by_case_id=paired_requirements_by_case_id,
            )

            def apply_formal_relations(context: Any) -> dict[str, Any]:
                service = self._relation_command_factory(context)
                plan_case_ids = {str(plan.case_id) for plan in command.plans}
                plan_links = [
                    link for link in command.etc_batch_links if str(link["case_id"]) in plan_case_ids
                ]
                existing_links = [
                    link for link in command.etc_batch_links if str(link["case_id"]) not in plan_case_ids
                ]
                formal_result = service.confirm_formal_relation_plans(
                    list(command.plans),
                    actor_id=AUTO_RELATION_ACTOR,
                    etc_batch_links=plan_links,
                    paired_requirements_by_case_id=command.paired_requirements_by_case_id,
                    tenant_id=command.tenant_id,
                )
                enrichment_result = service.enrich_etc_batch_links(
                    existing_links, actor_id=AUTO_RELATION_ACTOR
                )
                return {
                    "status": "updated",
                    "relations": [
                        *list(formal_result.get("relations") or []),
                        *list(enrichment_result.get("relations") or []),
                    ],
                    "histories": [
                        *list(formal_result.get("histories") or []),
                        *list(enrichment_result.get("histories") or []),
                    ],
                    "changed_case_ids": sorted(
                        {
                            *list(formal_result.get("changed_case_ids") or []),
                            *list(enrichment_result.get("changed_case_ids") or []),
                        }
                    ),
                    "affected_months": sorted(
                        {
                            *list(formal_result.get("affected_months") or []),
                            *list(enrichment_result.get("affected_months") or []),
                        }
                    ),
                    "enriched_relation_count": int(formal_result.get("enriched_relation_count") or 0)
                    + int(enrichment_result.get("updated_count") or 0),
                }

            write_result = self._relation_uow.run(command, apply_formal_relations)
            relations = [item for item in list(write_result.get("relations") or []) if isinstance(item, dict)]
            summary["created_relation_count"] = sum(1 for plan in command.plans if not plan.target_case_id)
            summary["extended_relation_count"] = sum(1 for plan in command.plans if plan.target_case_id)
            summary["enriched_relation_count"] = int(write_result.get("enriched_relation_count") or 0)
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

    def _paired_requirements_by_case_id(
        self,
        match_result: FormalRelationMatchResult,
        *,
        etc_batch_links: tuple[dict[str, Any], ...],
    ) -> dict[str, dict[str, object]]:
        bank_row_ids = sorted(
            {
                row_id
                for plan in match_result.plans
                for row_id, row_type in zip(plan.row_ids, plan.row_types, strict=True)
                if row_type == "bank"
            }
        )
        if not bank_row_ids:
            return {}
        rows_by_id = dict(
            self._fact_repository.load_bank_effective_categories_by_ids(bank_row_ids)
            or {}
        )
        if set(bank_row_ids) - set(rows_by_id):
            raise RuntimeError("canonical_bank_category_rows_missing")
        rules_payload = self._bank_flow_rule_tag_rules_payload()
        etc_case_ids = {str(link["case_id"]) for link in etc_batch_links}
        requirements: dict[str, dict[str, object]] = {}
        for plan in match_result.plans:
            plan_bank_row_ids = [
                row_id
                for row_id, row_type in zip(plan.row_ids, plan.row_types, strict=True)
                if row_type == "bank"
            ]
            if not plan_bank_row_ids:
                continue
            metadata = build_bank_relation_requirement_metadata(
                tag_codes=(
                    str(rows_by_id[row_id].get("effective_category_code") or "")
                    for row_id in plan_bank_row_ids
                ),
                rules_payload=rules_payload,
            )
            if plan.case_id in etc_case_ids:
                metadata["requires_oa"] = True
                metadata["requires_invoice"] = False
            requirements[plan.case_id] = metadata
        return requirements

    @staticmethod
    def _resolve_etc_batch_links(
        batch: Any,
        match_result: FormalRelationMatchResult,
        raw_candidates: list[dict[str, Any]],
    ) -> tuple[tuple[dict[str, Any], ...], int, int]:
        facts_by_row_id = {
            fact.row_id: fact
            for fact in batch.facts
            if fact.row_type == "oa"
        }
        active_by_member = {
            member_key: anchor.case_id
            for anchor in batch.active_relations
            for member_key in anchor.member_keys
        }
        plan_by_member = {
            member_key: plan.case_id
            for plan in match_result.plans
            for member_key in plan.member_keys
        }
        candidates_by_external: dict[str, list[dict[str, Any]]] = {}
        for raw in list(raw_candidates or []):
            external_batch_id = str(raw.get("external_etc_batch_id") or "").strip()
            if external_batch_id:
                candidates_by_external.setdefault(external_batch_id, []).append(raw)
        ambiguous_external_ids = {
            external_batch_id
            for external_batch_id, candidates in candidates_by_external.items()
            if len(candidates) != 1
            or int(candidates[0].get("external_batch_owner_count") or 1) != 1
        }
        resolved: list[dict[str, Any]] = []
        unowned_count = 0
        for external_batch_id, candidates in candidates_by_external.items():
            if external_batch_id in ambiguous_external_ids:
                continue
            raw = candidates[0]
            oa_row_id = str(raw.get("oa_row_id") or "").strip()
            business_batch_id = str(raw.get("business_batch_id") or "").strip()
            fact = facts_by_row_id.get(oa_row_id)
            if fact is None or not external_batch_id or not business_batch_id:
                continue
            case_id = active_by_member.get(fact.member_key) or plan_by_member.get(fact.member_key)
            if not case_id:
                unowned_count += 1
                continue
            resolved.append(
                {
                    "case_id": case_id,
                    "oa_row_id": oa_row_id,
                    "business_batch_id": business_batch_id,
                    "external_etc_batch_id": external_batch_id,
                    "submission_batch_id": str(raw.get("submission_batch_id") or "").strip(),
                    "invoice_count": int(raw.get("invoice_count") or 0),
                    "total_amount": str(raw.get("total_amount") or "0"),
                    "scope_keys": sorted(
                        {
                            str(scope).strip()
                            for scope in list(raw.get("scope_keys") or [])
                            if str(scope).strip()
                        }
                    ),
                }
            )

        by_external: dict[str, list[dict[str, Any]]] = {}
        for item in resolved:
            by_external.setdefault(str(item["external_etc_batch_id"]), []).append(item)
        unique_external = [items[0] for items in by_external.values() if len(items) == 1]
        by_case: dict[str, list[dict[str, Any]]] = {}
        for item in unique_external:
            by_case.setdefault(str(item["case_id"]), []).append(item)
        links = tuple(
            sorted(
                (items[0] for items in by_case.values() if len(items) == 1),
                key=lambda item: str(item["case_id"]),
            )
        )
        ambiguous_count = len(ambiguous_external_ids) + len(resolved) - len(links)
        return links, ambiguous_count, unowned_count

    @classmethod
    def _expanded_etc_batch_link_scopes(
        cls,
        requested_scope_months: list[str],
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        discovered_scope_months = [
            str(scope).strip()
            for candidate in list(candidates or [])
            if isinstance(candidate, dict)
            for scope in list(candidate.get("scope_keys") or [])
            if str(scope).strip() != "all"
        ]
        return cls._normalize_scope_months(
            [*requested_scope_months, *discovered_scope_months]
        )

    @staticmethod
    def _default_relation_command(context: Any) -> WorkbenchRelationCommandService:
        return WorkbenchRelationCommandService(
            relation_repository=context.pair_relations,
            etc_batch_link_repository=context.etc_batch_links,
            idempotency_store=context.idempotency_store,
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
