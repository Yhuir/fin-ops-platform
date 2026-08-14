from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    use_audit_snapshot,
)


ACTIVE_JOB_STATUSES = frozenset({"queued", "running"})
ATTENTION_JOB_STATUSES = frozenset({"failed", "partial_success"})
SENSITIVE_KEY_PARTS = ("password", "token", "secret", "encrypted", "content", "raw_file")


def audit_settings_page(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        settings_rows = snapshot.connection.fetch_all(_SETTINGS_SQL)
        credential_rows = snapshot.connection.fetch_all(_CREDENTIAL_SQL)
        job_rows = snapshot.connection.fetch_all(_RESET_JOB_SQL)
        issues = _settings_issues(settings_rows)
        issues.extend(_credential_issues(credential_rows))
        issues.extend(_reset_job_issues(job_rows))
        evaluation = evaluate_audit_issues(issues, sample_limit=max(int(example_limit or 50), 1))
        return {
            "mode": "settings-page-audit",
            "tenant_id": str(tenant_id or "default").strip() or "default",
            "overall_status": evaluation.overall_status,
            "audit_status": evaluation.audit_status,
            "summary": {
                "settings_singleton_count": len(settings_rows),
                "credential_summary_count": len(credential_rows),
                "settings_reset_job_count": len(job_rows),
                **evaluation.summary,
            },
            "issues": evaluation.issue_samples,
            "audit_contract": {
                "source_tables": [
                    "app.app_settings",
                    "app.oa_applicant_credentials",
                    "job.background_jobs",
                ],
                "derived_tables": [],
                "canonical_expected_set": (
                    "the persisted app_settings singleton normalized by the production settings contract, "
                    "secret-safe OA applicant credential summaries, and registered settings reset jobs"
                ),
                "key_display_fields": [
                    "projects and completed project membership",
                    "bank account mappings",
                    "access-control role sets",
                    "Workbench column layouts",
                    "OA retention/import/promotion/offset controls",
                    "pending invoice and cross-module tag-selection families",
                    "credential target/name/username/status/enabled summary",
                    "settings reset job status/progress/attention state",
                ],
                "relation_edge_equality": "not_applicable: Settings does not consume or display pairing relations",
                "proof_checks": [
                    "settings_singleton_and_version",
                    "formal_payload_and_normalized_contract_equality",
                    "configuration_family_set_and_reference_normalization",
                    "credential_metadata_and_configured_state_without_secret_read",
                    "settings_reset_job_queue_and_attention_gate",
                ],
                "snapshot_consistency": snapshot.consistency,
                "database_snapshot": snapshot.database_snapshot,
                "external_source_boundary": (
                    "OA project completeness, applicant login validity, manual OA search/import results, "
                    "and post-reset multi-page smoke require separate external gates"
                ),
                "pass_condition": (
                    "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' "
                    "and audit_status.queue == 'drained' and audit_contract.database_snapshot == true"
                ),
                "guarantee_boundary": (
                    "Persisted App control-plane settings, non-sensitive credential registration, and reset job state agree; "
                    "no external OA/provider result or credential login is inferred."
                ),
                "write_policy": "read_only",
                "secret_policy": "credential ciphertext, passwords, tokens, and raw credential payloads are not selected",
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }


def _settings_issues(rows: list[dict[str, Any]]) -> list[AuditIssue]:
    if len(rows) != 1:
        return [_issue("settings_singleton_count_mismatch", "app_settings", {"count": len(rows)})]
    row = rows[0]
    payload = _dict(row.get("settings_payload"))
    raw_payload = _dict(row.get("raw_payload"))
    normalized_raw = _dict(raw_payload.get("normalized_payload"))
    issues: list[AuditIssue] = []
    if int(row.get("version") or 0) < 1:
        issues.append(_issue("settings_version_invalid", "app_settings", {"version": row.get("version")}))
    if normalized_raw != payload:
        issues.append(
            _issue(
                "settings_formal_raw_payload_mismatch",
                "app_settings",
                {"mismatched_keys": _mismatched_keys(payload, normalized_raw)},
            )
        )
    normalized = AppSettingsService._normalize_settings(
        payload,
        validate_pending_invoice_tag_groups=False,
    )
    if normalized != payload:
        issues.append(
            _issue(
                "settings_payload_not_normalized",
                "app_settings",
                {"mismatched_keys": _mismatched_keys(payload, normalized)},
            )
        )
    sensitive_paths = _sensitive_paths(payload)
    if sensitive_paths:
        issues.append(
            _issue(
                "settings_payload_contains_secret_field",
                "app_settings",
                {"field_paths": sensitive_paths},
            )
        )
    return issues


def _credential_issues(rows: list[dict[str, Any]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    seen: set[str] = set()
    for row in rows:
        code = str(row.get("target_applicant_code") or "").strip()
        if not code or code in seen:
            issues.append(_issue("settings_credential_duplicate_or_missing_code", code or "credential", None))
        seen.add(code)
        status = str(row.get("credential_status") or "").strip()
        has_credential = bool(row.get("has_credential"))
        if status not in {"configured", "unconfigured"} or has_credential != (status == "configured"):
            issues.append(
                _issue(
                    "settings_credential_status_mismatch",
                    code,
                    {"status": status, "has_credential": has_credential},
                )
            )
        if status == "configured" and (
            not str(row.get("target_applicant_name") or "").strip()
            or not str(row.get("oa_username") or "").strip()
        ):
            issues.append(_issue("settings_credential_identity_missing", code, None))
    return issues


def _reset_job_issues(rows: list[dict[str, Any]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for row in rows:
        job_id = str(row.get("job_id") or "").strip()
        status = str(row.get("status") or "").strip()
        payload = _dict(row.get("normalized_payload"))
        if str(payload.get("job_id") or job_id).strip() != job_id or str(
            payload.get("status") or status
        ).strip() != status:
            issues.append(_issue("settings_reset_job_formal_payload_mismatch", job_id, {"status": status}))
        if status in ACTIVE_JOB_STATUSES:
            issues.append(
                AuditIssue(
                    "error",
                    "page_runtime_queue_not_drained",
                    "设置数据重置任务尚未排空。",
                    job_id,
                    "settings_data_reset",
                    {"status": status},
                )
            )
        elif status in ATTENTION_JOB_STATUSES and not (
            payload.get("acknowledged_at") or payload.get("superseded_at") or row.get("superseded_by_job_id")
        ):
            issues.append(_issue("settings_reset_job_attention_required", job_id, {"status": status}))
    return issues


def _sensitive_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS):
                paths.append(path)
            else:
                paths.extend(_sensitive_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_sensitive_paths(item, f"{prefix}[{index}]"))
    return paths


def _mismatched_keys(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _issue(code: str, subject_id: str, details: dict[str, Any] | None) -> AuditIssue:
    return AuditIssue(
        "error",
        code,
        "设置 canonical facts、控制合同或任务状态不一致。",
        subject_id,
        "settings",
        details,
    )


_SETTINGS_SQL = """select settings_key, version, settings_payload, raw_payload, updated_by, updated_at from app.app_settings where settings_key = 'app_settings' order by settings_key"""
_CREDENTIAL_SQL = """select target_applicant_code, target_applicant_name, oa_username, credential_status, enabled, (credential_status = 'configured' and encrypted_password is not null) as has_credential, updated_by, updated_at from app.oa_applicant_credentials order by target_applicant_code"""
_RESET_JOB_SQL = """select job_id, status, superseded_by_job_id, raw_payload->'normalized_payload' as normalized_payload from job.background_jobs where job_type = 'settings_data_reset' order by created_at, job_id"""
