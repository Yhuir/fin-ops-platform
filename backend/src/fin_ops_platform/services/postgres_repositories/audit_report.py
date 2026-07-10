from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


FRESHNESS_ISSUE_CODES = frozenset({"read_model_scope_not_fresh", "read_model_outbox_not_drained"})
QUEUE_ISSUE_CODES = frozenset({"read_model_outbox_not_drained"})


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    message: str
    subject_id: str = ""
    scope_key: str = ""
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class AuditEvaluation:
    overall_status: str
    audit_status: dict[str, str]
    summary: dict[str, Any]
    issue_samples: list[dict[str, Any]]


def evaluate_audit_issues(issues: list[AuditIssue], *, sample_limit: int) -> AuditEvaluation:
    limit = max(int(sample_limit or 1), 1)
    samples: list[AuditIssue] = []
    samples_by_code: Counter[str] = Counter()
    for issue in issues:
        if samples_by_code[issue.code] >= limit:
            continue
        samples.append(issue)
        samples_by_code[issue.code] += 1

    has_blocking_issue = any(issue.severity == "error" for issue in issues)
    has_freshness_issue = any(
        issue.severity == "error" and issue.code in FRESHNESS_ISSUE_CODES
        for issue in issues
    )
    has_integrity_issue = any(
        issue.severity == "error" and issue.code not in FRESHNESS_ISSUE_CODES
        for issue in issues
    )
    has_queue_issue = any(
        issue.severity == "error" and issue.code in QUEUE_ISSUE_CODES
        for issue in issues
    )
    error_samples = sum(1 for issue in samples if issue.severity == "error")
    warning_samples = sum(1 for issue in samples if issue.severity == "warning")
    return AuditEvaluation(
        overall_status="issues_found" if has_blocking_issue else "pass",
        audit_status={
            "integrity": "issues_found" if has_integrity_issue else "pass",
            "freshness": "not_fresh" if has_freshness_issue else "fresh",
            "queue": "backlog" if has_queue_issue else "drained",
        },
        summary={
            "issue_sample_count": len(samples),
            "error_sample_count": error_samples,
            "warning_sample_count": warning_samples,
            "blocking_issue_sample_count": error_samples,
            "issue_sample_counts_by_code": dict(sorted(samples_by_code.items())),
            "issue_sample_limit_per_code": limit,
            "issue_samples_truncated": len(samples) < len(issues),
            "detected_issue_code_count": len({issue.code for issue in issues}),
        },
        issue_samples=[asdict(issue) for issue in samples],
    )
