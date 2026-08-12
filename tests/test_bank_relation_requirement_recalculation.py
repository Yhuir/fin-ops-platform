from __future__ import annotations

from types import SimpleNamespace

from fin_ops_platform.services.background_job_service import BackgroundJobService
from fin_ops_platform.services.bank_relation_requirement_recalculation import (
    BANK_RELATION_REQUIREMENT_RECALCULATION_JOB_TYPE,
    BankRelationRequirementRecalculationJobHandler,
    changed_requirement_tag_codes,
)


def _rules(*, version: int = 12) -> dict[str, object]:
    return {
        "version": version,
        "requirements_by_tag_code": {
            "sales_income": {"requires_oa": False, "requires_invoice": True},
            "strict": {"requires_oa": True, "requires_invoice": False},
        },
    }


def _relation(
    case_id: str,
    *,
    month: str = "2026-07",
    tags: list[str] | None = None,
    requires_oa: bool = True,
    requires_invoice: bool = True,
    rule_version: int = 11,
    canonical_months: list[str] | None = None,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "month_scope": month,
        "_canonical_bank_months": list(
            canonical_months if canonical_months is not None else ([month] if month else [])
        ),
        "special_metadata": {
            "paired_requirement_source": "bank_transaction_paired_policy",
            "paired_requirement_tag_codes": list(tags or ["sales_income"]),
            "paired_requirement_version": rule_version,
            "requires_oa": requires_oa,
            "requires_invoice": requires_invoice,
        },
    }


def _handler(
    relations: list[dict[str, object]],
    *,
    rules: dict[str, object] | None = None,
    supersedes_failed_job: bool = False,
):
    jobs = BackgroundJobService()
    job = jobs.create_job(
        job_type=BANK_RELATION_REQUIREMENT_RECALCULATION_JOB_TYPE,
        label="重算流水关联要求",
        owner_user_id="finance-user",
        visibility="system",
        result_summary={"changed_case_ids": [], "affected_months": []},
    )
    superseded_job_id = ""
    if supersedes_failed_job:
        superseded = jobs.create_job(
            job_type=BANK_RELATION_REQUIREMENT_RECALCULATION_JOB_TYPE,
            label="旧规则收敛任务",
            owner_user_id="system:migration:0145",
            visibility="system",
        )
        jobs.fail_job(superseded.job_id, "旧任务失败。", "candidate relation")
        superseded_job_id = superseded.job_id
    writes: list[dict[str, object]] = []
    refreshes: list[dict[str, object]] = []
    dirty_calls: list[list[str]] = []
    handler = BankRelationRequirementRecalculationJobHandler(
        state_store=SimpleNamespace(
            load_app_settings=lambda: {
                "bank_flow_rule_batch_tag_rules": dict(rules or _rules())
            }
        ),
        relation_repository=SimpleNamespace(
            load_active_bank_requirement_relations_for_tag_codes=(
                lambda _codes: list(relations)
            )
        ),
        relation_updater=lambda **kwargs: (writes.append(dict(kwargs)) or {}),
        queue_repository=SimpleNamespace(
            enqueue_read_model_refresh=lambda **kwargs: refreshes.append(dict(kwargs))
        ),
        background_jobs=jobs,
        matching_dirty_marker=lambda months: dirty_calls.append(list(months)) or list(months),
    )
    event = SimpleNamespace(
        payload={
            "job_id": job.job_id,
            "owner_user_id": "finance-user",
            "changed_tag_codes": ["sales_income"],
            "supersedes_job_id": superseded_job_id,
        }
    )
    return (
        handler,
        event,
        jobs,
        job.job_id,
        writes,
        refreshes,
        dirty_calls,
        superseded_job_id,
    )


def test_changed_requirement_tag_codes_detects_oa_invoice_semantic_diff() -> None:
    previous = {
        "requirements_by_tag_code": {
            "sales_income": {"requires_oa": True, "requires_invoice": True},
            "unchanged": {"requires_oa": False, "requires_invoice": False},
        }
    }
    current = {
        "requirements_by_tag_code": {
            "sales_income": {"requires_oa": False, "requires_invoice": True},
            "unchanged": {"requires_oa": False, "requires_invoice": False},
        }
    }

    assert changed_requirement_tag_codes(previous, current) == ["sales_income"]


def test_handler_recomputes_full_tag_set_and_refreshes_only_exact_months() -> None:
    relations = [
        _relation(
            "case-1",
            tags=["sales_income", "strict"],
            requires_oa=False,
        ),
        _relation("case-2", month="2026-05"),
    ]
    handler, event, jobs, job_id, writes, refreshes, dirty_calls, _ = _handler(relations)

    summary = handler.handle_runtime_event(event)

    assert summary["written_relation_count"] == 2
    assert summary["affected_months"] == ["2026-05", "2026-07"]
    assert writes[0]["special_metadata"]["requires_oa"] is True
    assert writes[0]["special_metadata"]["requires_invoice"] is True
    assert writes[1]["special_metadata"]["requires_oa"] is False
    assert writes[1]["special_metadata"]["requires_invoice"] is True
    assert {(row["scope_type"], row["scope_key"]) for row in refreshes} == {
        ("workbench_relation", "2026-05"),
        ("workbench_relation", "2026-07"),
    }
    assert dirty_calls == [["2026-05", "2026-07"]]
    assert jobs.get_job(job_id, "finance-user").status == "succeeded"


def test_handler_skips_relation_when_aggregate_requirements_are_unchanged() -> None:
    relation = _relation(
        "case-noop",
        requires_oa=False,
        requires_invoice=True,
        rule_version=12,
    )
    handler, event, jobs, job_id, writes, refreshes, dirty_calls, _ = _handler([relation])

    summary = handler.handle_runtime_event(event)

    assert summary["written_relation_count"] == 0
    assert summary["unchanged_relation_count"] == 1
    assert writes == []
    assert refreshes == []
    assert dirty_calls == []
    assert jobs.get_job(job_id, "finance-user").status == "succeeded"


def test_handler_fails_closed_before_any_write_when_relation_proof_is_incomplete() -> None:
    invalid = _relation("case-invalid")
    invalid["special_metadata"] = {
        "paired_requirement_source": "bank_transaction_paired_policy",
        "requires_oa": True,
        "requires_invoice": True,
    }
    handler, event, jobs, job_id, writes, refreshes, dirty_calls, _ = _handler(
        [_relation("case-valid"), invalid]
    )

    summary = handler.handle_runtime_event(event)

    assert summary["status"] == "failed"
    assert summary["written_relation_count"] == 0
    assert writes == []
    assert refreshes == []
    assert dirty_calls == []
    assert jobs.get_job(job_id, "finance-user").status == "failed"


def test_handler_supersedes_failed_rollout_only_after_replacement_succeeds() -> None:
    handler, event, jobs, job_id, writes, _refreshes, _dirty_calls, old_job_id = _handler(
        [_relation("case-rollout")],
        supersedes_failed_job=True,
    )

    summary = handler.handle_runtime_event(event)

    assert len(writes) == 1
    assert summary["superseded_job_id"] == old_job_id
    assert jobs.get_job(old_job_id, "finance-user").status == "superseded"
    assert jobs.get_job(old_job_id, "finance-user").superseded_by_job_id == job_id
    assert jobs.get_job(job_id, "finance-user").status == "succeeded"


def test_handler_keeps_failed_rollout_visible_when_replacement_fails_closed() -> None:
    invalid = _relation("case-invalid")
    invalid["month_scope"] = "all"
    invalid["_canonical_bank_months"] = []
    handler, event, jobs, job_id, writes, _refreshes, _dirty_calls, old_job_id = _handler(
        [invalid],
        supersedes_failed_job=True,
    )

    summary = handler.handle_runtime_event(event)

    assert summary["status"] == "failed"
    assert writes == []
    assert jobs.get_job(old_job_id, "finance-user").status == "failed"
    assert jobs.get_job(job_id, "finance-user").status == "failed"


def test_handler_derives_exact_scope_from_canonical_bank_month_for_legacy_relation() -> None:
    relation = _relation(
        "case-legacy-scope",
        month="",
        canonical_months=["2026-05"],
    )
    handler, event, _jobs, _job_id, writes, refreshes, dirty_calls, _ = _handler(
        [relation]
    )

    summary = handler.handle_runtime_event(event)

    assert len(writes) == 1
    assert summary["affected_months"] == ["2026-05"]
    assert {(row["scope_type"], row["scope_key"]) for row in refreshes} == {
        ("workbench_relation", "2026-05"),
    }
    assert dirty_calls == [["2026-05"]]


def test_handler_refreshes_every_canonical_bank_month_for_cross_month_relation() -> None:
    relation = _relation(
        "case-cross-month",
        month="",
        canonical_months=["2026-07", "2026-08"],
    )
    handler, event, _jobs, _job_id, writes, _refreshes, dirty_calls, _ = _handler(
        [relation]
    )

    summary = handler.handle_runtime_event(event)

    assert len(writes) == 1
    assert summary["affected_months"] == ["2026-07", "2026-08"]
    assert dirty_calls == [["2026-07", "2026-08"]]


def test_handler_updates_rule_version_even_when_booleans_are_unchanged() -> None:
    relation = _relation(
        "case-version-drift",
        requires_oa=False,
        requires_invoice=True,
        rule_version=11,
    )
    handler, event, _jobs, _job_id, writes, _refreshes, _dirty_calls, _ = _handler(
        [relation]
    )

    summary = handler.handle_runtime_event(event)

    assert summary["written_relation_count"] == 1
    assert writes[0]["special_metadata"]["paired_requirement_version"] == 12
