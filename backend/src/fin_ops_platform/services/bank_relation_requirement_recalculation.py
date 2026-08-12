from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from fin_ops_platform.services.background_job_service import (
    TERMINAL_BACKGROUND_JOB_STATUSES,
    BackgroundJobService,
)
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.workbench_relation_requirements import (
    build_bank_relation_requirement_metadata,
)


BANK_RELATION_REQUIREMENT_RECALCULATION_EVENT = (
    "settings.bank_relation_requirements.recalculate.requested"
)
BANK_RELATION_REQUIREMENT_RECALCULATION_JOB_TYPE = (
    "bank_relation_requirement_recalculation"
)
REQUIREMENT_SOURCE = "bank_transaction_paired_policy"


def changed_requirement_tag_codes(
    previous_payload: dict[str, Any],
    next_payload: dict[str, Any],
) -> list[str]:
    previous = _requirements(previous_payload)
    current = _requirements(next_payload)
    return sorted(
        tag_code
        for tag_code in set(previous) | set(current)
        if previous.get(tag_code) != current.get(tag_code)
    )


class BankRelationRequirementRecalculationJobHandler:
    """Reapply current tag requirements to impacted active Workbench relations."""

    def __init__(
        self,
        *,
        state_store: Any,
        relation_repository: Any,
        relation_updater: Callable[..., dict[str, Any]],
        queue_repository: Any,
        background_jobs: BackgroundJobService,
        matching_dirty_marker: Callable[[list[str]], list[str]] | None = None,
    ) -> None:
        self._state_store = state_store
        self._relations = relation_repository
        self._relation_updater = relation_updater
        self._queue = queue_repository
        self._background_jobs = background_jobs
        self._matching_dirty_marker = matching_dirty_marker

    def handle_runtime_event(self, event: Any) -> dict[str, object]:
        payload = event.payload if isinstance(getattr(event, "payload", None), dict) else {}
        job_id = str(payload.get("job_id") or "").strip()
        owner_user_id = str(payload.get("owner_user_id") or "").strip()
        changed_tag_codes = _text_list(payload.get("changed_tag_codes"))
        supersedes_job_id = str(payload.get("supersedes_job_id") or "").strip()
        if not job_id or not owner_user_id or not changed_tag_codes:
            raise ValueError("bank relation requirement recalculation event is incomplete")
        if supersedes_job_id == job_id:
            raise ValueError("bank relation requirement recalculation cannot supersede itself")

        job = self._background_jobs.get_job(job_id, owner_user_id)
        if job.status in TERMINAL_BACKGROUND_JOB_STATUSES:
            return dict(job.result_summary)
        if job.status == "queued":
            job = self._background_jobs.start_job(job_id)

        if supersedes_job_id:
            try:
                superseded_job = self._background_jobs.get_job(
                    supersedes_job_id,
                    owner_user_id,
                )
            except (KeyError, PermissionError) as exc:
                self._background_jobs.fail_job(
                    job_id,
                    "关联要求重算失败，未修改任何关系。",
                    f"replacement target is unavailable: {supersedes_job_id}",
                )
                return {
                    "status": "failed",
                    "changed_tag_codes": changed_tag_codes,
                    "error": str(exc),
                    "written_relation_count": 0,
                }
            if superseded_job.status not in {"failed", "superseded"}:
                self._background_jobs.fail_job(
                    job_id,
                    "关联要求重算失败，未修改任何关系。",
                    f"replacement target is not failed: {supersedes_job_id}",
                )
                return {
                    "status": "failed",
                    "changed_tag_codes": changed_tag_codes,
                    "error": "replacement target is not failed",
                    "written_relation_count": 0,
                }

        previous_summary = dict(job.result_summary or {})
        affected_months = set(_text_list(previous_summary.get("affected_months")))
        changed_case_ids = set(_text_list(previous_summary.get("changed_case_ids")))
        current_rules = self._current_rules_payload()
        current_version = int(current_rules.get("version") or 1)
        relations = self._relations.load_active_bank_requirement_relations_for_tag_codes(
            changed_tag_codes
        )
        total = max(len(relations), 1)
        scanned = 0
        skipped = 0
        plans: list[tuple[dict[str, Any], str, str, dict[str, Any], dict[str, object]]] = []

        try:
            for relation in relations:
                case_id, month_scope, metadata, intended = self._plan_relation(
                    relation,
                    current_rules=current_rules,
                )
                plans.append((relation, case_id, month_scope, metadata, intended))
        except RuntimeError as exc:
            self._background_jobs.fail_job(
                job_id,
                "关联要求重算失败，未修改任何关系。",
                str(exc),
            )
            return {
                "status": "failed",
                "rule_version": current_version,
                "changed_tag_codes": changed_tag_codes,
                "error": str(exc),
                "written_relation_count": 0,
            }

        for _relation, case_id, month_scope, metadata, intended in plans:
            scanned += 1
            if _same_effective_requirements(metadata, intended):
                if metadata.get("paired_requirement_recalculation_job_id") == job_id:
                    changed_case_ids.add(case_id)
                    affected_months.add(month_scope)
                skipped += 1
                continue
            result = self._relation_updater(
                case_id=case_id,
                special_metadata={
                    **metadata,
                    **intended,
                    "paired_requirement_recalculation_job_id": job_id,
                },
                replace_special_metadata=True,
                actor_id="system:bank_relation_requirement_recalculation",
                note=(
                    "按已保存流水标签重应用当前关联要求；"
                    f"rule_version={current_version};job_id={job_id}"
                ),
                idempotency_key=(
                    f"bank-relation-requirements-v{current_version}:{job_id}:{case_id}"
                ),
                history_operation_type="bank_relation_requirement_recalculated",
            )
            changed_case_ids.add(case_id)
            affected_months.add(month_scope)
            affected_months.update(
                month
                for month in _text_list(result.get("affected_months"))
                if _is_month_scope(month)
            )
            self._background_jobs.update_progress(
                job_id,
                phase="recalculating",
                message="正在按变化标签重算关联要求。",
                current=scanned,
                total=total,
                result_summary={
                    "rule_version": current_version,
                    "changed_tag_codes": changed_tag_codes,
                    "changed_case_ids": sorted(changed_case_ids),
                    "affected_months": sorted(affected_months),
                },
            )

        metadata = {
            "source": "bank_relation_requirement_recalculation",
            "job_id": job_id,
            "rule_version": current_version,
            "changed_tag_codes": changed_tag_codes,
            "case_ids": sorted(changed_case_ids),
            "force_refresh": True,
        }
        gateway = ReadModelRefreshGateway(queue_repository=self._queue)
        for scope_type in ("workbench", "workbench_relation"):
            gateway.enqueue_many(
                scope_type,
                sorted(affected_months),
                reason="bank_relation_requirement_recalculation",
                priority="high",
                metadata=metadata,
            )
        dirty_months = (
            self._matching_dirty_marker(sorted(affected_months))
            if self._matching_dirty_marker is not None and affected_months
            else []
        )

        summary: dict[str, object] = {
            "rule_version": current_version,
            "changed_tag_codes": changed_tag_codes,
            "scanned_relation_count": scanned,
            "written_relation_count": len(changed_case_ids),
            "unchanged_relation_count": skipped,
            "changed_case_ids": sorted(changed_case_ids),
            "affected_months": sorted(affected_months),
            "matching_dirty_months": list(dirty_months),
        }
        if supersedes_job_id:
            self._background_jobs.supersede_job(
                supersedes_job_id,
                owner_user_id,
                superseded_by_job_id=job_id,
            )
            summary["superseded_job_id"] = supersedes_job_id
        self._background_jobs.succeed_job(
            job_id,
            "关联要求重算完成。",
            summary,
        )
        return summary

    @staticmethod
    def _plan_relation(
        relation: dict[str, Any],
        *,
        current_rules: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any], dict[str, object]]:
        case_id = str(relation.get("case_id") or "").strip()
        if not case_id:
            raise RuntimeError("active relation has no case id")
        metadata = relation.get("special_metadata")
        metadata = deepcopy(metadata) if isinstance(metadata, dict) else {}
        stored_tag_codes = _stored_tag_codes(metadata)
        if not stored_tag_codes:
            raise RuntimeError(
                f"active relation {case_id} has no persisted requirement tag proof"
            )
        missing_rules = [
            tag_code
            for tag_code in stored_tag_codes
            if tag_code not in _requirements(current_rules)
        ]
        if missing_rules:
            raise RuntimeError(
                f"active relation {case_id} references missing tag rules: "
                + ",".join(missing_rules)
            )
        month_scope = str(relation.get("month_scope") or "").strip()
        if not _is_month_scope(month_scope):
            raise RuntimeError(
                f"active relation {case_id} does not have an exact month scope"
            )
        intended = build_bank_relation_requirement_metadata(
            tag_codes=stored_tag_codes,
            rules_payload=current_rules,
        )
        return case_id, month_scope, metadata, intended

    def _current_rules_payload(self) -> dict[str, Any]:
        settings = self._state_store.load_app_settings()
        payload = settings.get("bank_flow_rule_batch_tag_rules")
        if not isinstance(payload, dict):
            raise RuntimeError("current bank flow tag requirement rules are unavailable")
        return dict(payload)


def _requirements(payload: dict[str, Any]) -> dict[str, tuple[bool, bool]]:
    raw = payload.get("requirements_by_tag_code")
    result: dict[str, tuple[bool, bool]] = {}
    if isinstance(raw, dict):
        for tag_code, rule in raw.items():
            normalized = str(tag_code or "").strip()
            if normalized and isinstance(rule, dict):
                result[normalized] = (
                    bool(rule.get("requires_oa")),
                    bool(rule.get("requires_invoice")),
                )
    for rule in list(payload.get("rules") or []):
        if not isinstance(rule, dict):
            continue
        tag_code = str(rule.get("tag_code") or rule.get("code") or "").strip()
        if tag_code:
            result[tag_code] = (
                bool(rule.get("requires_oa")),
                bool(rule.get("requires_invoice")),
            )
    return result


def _stored_tag_codes(metadata: dict[str, Any]) -> list[str]:
    values = metadata.get("paired_requirement_tag_codes")
    if not isinstance(values, list):
        values = [metadata.get("paired_requirement_tag_code")]
    return _text_list(values)


def _same_effective_requirements(
    current: dict[str, Any],
    intended: dict[str, object],
) -> bool:
    return (
        str(current.get("paired_requirement_source") or "") == REQUIREMENT_SOURCE
        and int(current.get("paired_requirement_version") or 0)
        == int(intended.get("paired_requirement_version") or 0)
        and bool(current.get("requires_oa")) == bool(intended.get("requires_oa"))
        and bool(current.get("requires_invoice"))
        == bool(intended.get("requires_invoice"))
    )


def _text_list(values: Any) -> list[str]:
    return list(
        dict.fromkeys(
            str(value or "").strip()
            for value in list(values or [])
            if str(value or "").strip()
        )
    )


def _is_month_scope(value: str) -> bool:
    return (
        len(value) == 7
        and value[4] == "-"
        and value[:4].isdigit()
        and value[5:].isdigit()
        and 1 <= int(value[5:]) <= 12
    )
