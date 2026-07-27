from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.external_control_evidence import EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION
from fin_ops_platform.services.page_audit_registry import PageAuditRegistration
from fin_ops_platform.services.postgres_repositories.audit_report import AuditIssue, evaluate_audit_issues
from fin_ops_platform.services.postgres_repositories.external_control_evidence_audit import (
    audit_external_control_evidence,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import COMPLETED_WORKFLOW_STATUS_ALIASES
from fin_ops_platform.services.read_model_manifest import READ_MODEL_MANIFEST
from fin_ops_platform.services.runtime_worker_registry import worker_registrations


def audit_app_health_system_snapshot(
    connection: Any,
    *,
    tenant_id: str,
    sample_limit: int,
    snapshot_identity: str,
    snapshot_generated_at: str,
    snapshot_consistency: str,
    database_snapshot: bool,
    registrations: tuple[PageAuditRegistration, ...],
    page_reports: list[dict[str, Any]],
    dashboard_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    dashboard = dict(dashboard_payload or {})
    issues = _page_report_issues(
        registrations=registrations,
        page_reports=page_reports,
        snapshot_identity=snapshot_identity,
    )
    expected_inventory = _expected_inventory(connection)
    actual_inventory = _dict(dashboard.get("data_inventory"))
    issues.extend(_inventory_issues(expected=expected_inventory, actual=actual_inventory))
    issues.extend(_outbox_runtime_issues(_dict(dashboard.get("runtime_performance"))))
    issues.extend(_read_model_runtime_issues(_dict(dashboard.get("runtime_performance"))))
    issues.extend(_worker_runtime_issues(_dict(dashboard.get("runtime_performance"))))
    evaluation = evaluate_audit_issues(issues, sample_limit=sample_limit)

    version_set = _version_set(registrations)
    external_evidence = audit_external_control_evidence(
        connection,
        tenant_id=tenant_id,
        as_of=snapshot_generated_at,
        sample_limit=sample_limit,
    )
    external_evidence["page_coverage"] = _external_page_coverage(registrations, external_evidence)
    evidence_fingerprint = _fingerprint(
        {
            "snapshot_identity": snapshot_identity,
            "version_set": version_set,
            "inventory": expected_inventory,
            "external_evidence": {
                "status": external_evidence.get("status"),
                "end_to_end_source_truth": external_evidence.get("end_to_end_source_truth"),
                "domains": [
                    {
                        "domain": row.get("domain"),
                        "status": row.get("status"),
                        "evidence_id": row.get("evidence_id"),
                        "manifest_fingerprint": row.get("manifest_fingerprint"),
                    }
                    for row in list(external_evidence.get("domains") or [])
                ],
            },
            "page_results": [
                {
                    "page_key": report.get("page_key"),
                    "overall_status": report.get("overall_status"),
                    "audit_status": report.get("audit_status"),
                    "contract_revision": _dict(report.get("audit_contract")).get("contract_revision"),
                }
                for report in page_reports
            ],
        }
    )
    database_internal_pass = evaluation.overall_status == "pass" and database_snapshot
    return {
        "mode": "app-health-system-audit",
        "tenant_id": tenant_id,
        "overall_status": "pass" if database_internal_pass else "issues_found",
        "audit_status": {
            **evaluation.audit_status,
            "external": str(external_evidence.get("status") or "unknown"),
        },
        "summary": {
            "registered_page_count": len(registrations),
            "audited_business_page_count": len(page_reports),
            "passed_business_page_count": sum(report.get("overall_status") == "pass" for report in page_reports),
            "database_internal_contracts": "pass" if database_internal_pass else "issues_found",
            "end_to_end_source_truth": str(external_evidence.get("end_to_end_source_truth") or "unproven"),
            **evaluation.summary,
        },
        "issues": evaluation.issue_samples,
        "database_system_snapshot": {
            "system_audit_id": f"system-audit:{evidence_fingerprint[:24]}",
            "snapshot_identity": snapshot_identity,
            "snapshot_generated_at": snapshot_generated_at,
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "evidence_fingerprint": evidence_fingerprint,
            "version_set": version_set,
            "page_results": page_reports,
            "expected_inventory": expected_inventory,
            "durable_runtime": {
                "outbox": _dict(_dict(dashboard.get("runtime_performance")).get("outbox")),
                "read_models": list(_dict(dashboard.get("runtime_performance")).get("read_models") or []),
                "workers": list(_dict(dashboard.get("runtime_performance")).get("workers") or []),
            },
        },
        "runtime_observation": {
            "observed_at": str(dashboard.get("generated_at") or datetime.now(UTC).isoformat()),
            "database_snapshot": False,
            "request_performance": _dict(dashboard.get("request_performance")),
            "transport_queues": list(_dict(dashboard.get("runtime_performance")).get("queues") or []),
            "warnings": list(_dict(dashboard.get("freshness")).get("warnings") or []),
            "claim_boundary": (
                "HTTP process metrics and optional transport/dependency observations are point-in-time runtime evidence, "
                "not PostgreSQL snapshot facts."
            ),
        },
        "external_evidence": external_evidence,
        "page_projection": dashboard,
        "audit_contract": {
            "source_tables": [
                "app.bank_transactions",
                "app.invoices",
                "app.import_batches",
                "app.oa_applications",
                "app.oa_application_items",
                "app.oa_sync_runs",
                "job.outbox_events",
                "job.read_model_dirty_scopes",
                "read_model.app_status_readiness",
                "job.runtime_worker_heartbeats",
            ],
            "read_model_tables": [],
            "canonical_expected_set": (
                "all registered page proof results plus independently recalculated App Health bank/invoice/OA/import "
                "inventory and current required worker evidence"
            ),
            "key_display_fields": [
                "bank/invoice/OA inventory totals and source counts",
                "import event identity/count/status/time",
                "required worker instance/kind/status/current-effective state",
                "page contract revisions and system evidence fingerprint",
            ],
            "relation_edge_equality": "not_applicable: App Health does not consume business pairing relations",
            "snapshot_consistency": snapshot_consistency,
            "database_snapshot": database_snapshot,
            "external_source_boundary": (
                "external bank/OA/invoice/ETC complete-snapshot manifests are proven by the dedicated external evidence owner; "
                "runtime dependency availability is reported separately"
            ),
            "pass_condition": (
                "every registered App-internal page proof passes in the same database snapshot and the App Health "
                "database inventory/required-worker contract has no blocking issue"
            ),
            "guarantee_boundary": (
                "Pass proves registered App-internal contracts only for this immutable database snapshot; it does not "
                "prove later writes. External source completeness requires external_evidence.status=pass and remains bounded "
                "to the registered source snapshots and observed_at timestamps."
            ),
            "write_policy": "read_only",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _page_report_issues(
    *,
    registrations: tuple[PageAuditRegistration, ...],
    page_reports: list[dict[str, Any]],
    snapshot_identity: str,
) -> list[AuditIssue]:
    expected_page_keys = [registration.page_key for registration in registrations if registration.page_key != "app-health-operations"]
    actual_page_keys = [str(report.get("page_key") or "") for report in page_reports]
    issues: list[AuditIssue] = []
    if actual_page_keys != expected_page_keys:
        issues.append(
            _issue(
                "system_page_registry_result_set_mismatch",
                "page-registry",
                {"expected": expected_page_keys, "actual": actual_page_keys},
            )
        )
    registration_by_key = {registration.page_key: registration for registration in registrations}
    for report in page_reports:
        page_key = str(report.get("page_key") or "")
        registration = registration_by_key.get(page_key)
        contract = _dict(report.get("audit_contract"))
        status = _dict(report.get("audit_status"))
        if registration is None:
            issues.append(_issue("system_unregistered_page_result", page_key, {}))
            continue
        if report.get("overall_status") != "pass" or status.get("integrity") != "pass":
            issues.append(_issue("system_page_integrity_failed", page_key, {"audit_status": status}))
        if status.get("freshness") != "fresh":
            issues.append(_issue("read_model_scope_not_fresh", page_key, {"audit_status": status}))
        if status.get("queue") != "drained":
            issues.append(_issue("page_runtime_queue_not_drained", page_key, {"audit_status": status}))
        if contract.get("contract_revision") != registration.contract_revision:
            issues.append(
                _issue(
                    "system_page_contract_revision_mismatch",
                    page_key,
                    {"expected": registration.contract_revision, "actual": contract.get("contract_revision")},
                )
            )
        if contract.get("database_snapshot") is not True or contract.get("snapshot_consistency") != "repeatable_read_read_only":
            issues.append(_issue("system_page_snapshot_contract_missing", page_key, {"snapshot_identity": snapshot_identity}))
        if contract.get("system_snapshot_identity") != snapshot_identity:
            issues.append(
                _issue(
                    "system_page_snapshot_identity_mismatch",
                    page_key,
                    {"expected": snapshot_identity, "actual": contract.get("system_snapshot_identity")},
                )
            )
    return issues


def _expected_inventory(connection: Any) -> dict[str, Any]:
    bank = connection.fetch_one(_EXPECTED_BANK_SQL) or {}
    invoice = connection.fetch_one(_EXPECTED_INVOICE_SQL) or {}
    completed_statuses = sorted(COMPLETED_WORKFLOW_STATUS_ALIASES)
    oa = connection.fetch_one(_EXPECTED_OA_SQL, (completed_statuses, completed_statuses)) or {}
    import_events = connection.fetch_all(_EXPECTED_IMPORT_EVENTS_SQL) or []
    bank_latest = _iso(bank.get("latest_synced_at"))
    invoice_latest = _iso(invoice.get("latest_synced_at"))
    oa_latest = _iso(oa.get("oa_latest_synced_at"))
    oa_in_progress_latest = _iso(oa.get("oa_pending_payment_in_progress_latest_synced_at")) or oa_latest
    return {
        "bank": _inventory(
            total_count=bank.get("total_count"),
            latest_synced_at=bank_latest,
            sources=[_source("bank_transactions", "银行流水", bank.get("total_count"), bank_latest)],
        ),
        "invoice": _inventory(
            total_count=invoice.get("total_count"),
            latest_synced_at=invoice_latest,
            sources=[
                _source("manual", "手工导入", invoice.get("manual_count"), _iso(invoice.get("manual_latest_synced_at"))),
                _source(
                    "input_invoice",
                    "进项发票",
                    invoice.get("input_invoice_count"),
                    _iso(invoice.get("input_invoice_latest_synced_at")),
                ),
                _source(
                    "output_invoice",
                    "销项发票",
                    invoice.get("output_invoice_count"),
                    _iso(invoice.get("output_invoice_latest_synced_at")),
                ),
                _source(
                    "oa_attachment",
                    "OA 解析",
                    invoice.get("oa_attachment_count"),
                    _iso(invoice.get("oa_attachment_latest_synced_at")),
                    supplementary_count=invoice.get("oa_attachment_non_manual_count"),
                ),
            ],
        ),
        "oa": _inventory(
            total_count=oa.get("oa_records_count"),
            latest_synced_at=oa_latest,
            sources=[
                _source("oa_records", "单据", oa.get("oa_records_count"), oa_latest),
                _source("oa_records_completed", "已完成 OA", oa.get("oa_records_completed_count"), oa_latest),
                _source(
                    "oa_records_in_progress",
                    "进行中 OA",
                    oa.get("oa_records_in_progress_count"),
                    oa_in_progress_latest,
                ),
                _source("oa_items", "明细", oa.get("oa_items_count"), oa_latest),
            ],
        ),
        "import_events": [
            {
                "key": str(row.get("event_id") or ""),
                "source_key": str(row.get("source_key") or ""),
                "label": str(row.get("label") or ""),
                "source_name": str(row.get("source_name") or ""),
                "imported_by": str(row.get("imported_by") or ""),
                "count": _integer(row.get("count")),
                "supplementary_count": None,
                "imported_at": _iso(row.get("imported_at")),
                "status": str(row.get("status") or ""),
            }
            for row in import_events
        ],
    }


def _inventory_issues(*, expected: dict[str, Any], actual: dict[str, Any]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for key in ("bank", "invoice", "oa"):
        if _normalized_json(expected.get(key)) != _normalized_json(actual.get(key)):
            issues.append(
                _issue(
                    "app_health_inventory_projection_mismatch",
                    key,
                    {"expected": expected.get(key), "actual": actual.get(key)},
                )
            )
    if _normalized_json(expected.get("import_events")) != _normalized_json(actual.get("import_events")):
        issues.append(
            _issue(
                "app_health_import_event_projection_mismatch",
                "import_events",
                {
                    "expected_count": len(list(expected.get("import_events") or [])),
                    "actual_count": len(list(actual.get("import_events") or [])),
                },
            )
        )
    return issues


def _worker_runtime_issues(runtime: dict[str, Any]) -> list[AuditIssue]:
    rows = [row for row in list(runtime.get("workers") or []) if isinstance(row, dict)]
    rows_by_instance = {str(row.get("worker_instance") or ""): row for row in rows}
    issues: list[AuditIssue] = []
    for registration in worker_registrations(required_only=True):
        row = rows_by_instance.get(registration.instance_name)
        if row is None:
            issues.append(_issue("required_worker_missing", registration.instance_name, {}))
            continue
        status = str(row.get("status") or row.get("worker_status") or "").strip().lower()
        warning_code = str(row.get("warning_code") or "").strip()
        if status in {"missing", "stale", "failed", "unavailable", "mismatch"} or warning_code:
            issues.append(
                _issue(
                    warning_code or "required_worker_unhealthy",
                    registration.instance_name,
                    {"status": status, "worker_kind": row.get("worker_kind")},
                )
            )
    return issues


def _outbox_runtime_issues(runtime: dict[str, Any]) -> list[AuditIssue]:
    outbox = _dict(runtime.get("outbox"))
    count_keys = ("pending_count", "publishing_count", "failed_count", "publish_failed_count")
    status = str(outbox.get("status") or "").strip().lower()
    warning_code = str(outbox.get("warning_code") or "").strip()
    if status != "available" or warning_code or any(outbox.get(key) is None for key in count_keys):
        return [
            AuditIssue(
                severity="error",
                code="page_runtime_queue_not_drained",
                message="App Health system proof cannot prove the durable outbox queue is drained.",
                subject_id="system-outbox",
                details={
                    "status": status,
                    "warning_code": warning_code or "outbox_runtime_metric_unavailable",
                    "missing_count_fields": [key for key in count_keys if outbox.get(key) is None],
                },
            )
        ]
    counts = {
        key: int(outbox.get(key) or 0)
        for key in count_keys
    }
    if sum(counts.values()) == 0:
        return []
    return [
        AuditIssue(
            severity="error",
            code="page_runtime_queue_not_drained",
            message="App Health system proof found current durable outbox attention rows.",
            subject_id="system-outbox",
            details=counts,
        )
    ]


def _read_model_runtime_issues(runtime: dict[str, Any]) -> list[AuditIssue]:
    rows = [row for row in list(runtime.get("read_models") or []) if isinstance(row, dict)]
    rows_by_key = {str(row.get("key") or ""): row for row in rows}
    issues: list[AuditIssue] = []
    manifest_keys = set(READ_MODEL_MANIFEST)
    status_keys = set(APP_STATUS_READ_MODEL_REGISTRY)
    if manifest_keys != status_keys:
        issues.append(
            _issue(
                "read_model_manifest_status_registry_mismatch",
                "read-model-registry",
                {"manifest_only": sorted(manifest_keys - status_keys), "status_only": sorted(status_keys - manifest_keys)},
            )
        )
    for key, definition in APP_STATUS_READ_MODEL_REGISTRY.items():
        row = rows_by_key.get(key)
        if row is None:
            issues.append(_issue("read_model_runtime_metric_missing", key, {"critical": definition.critical}))
            continue
        stale_count = int(row.get("stale_count") or 0)
        unavailable_count = int(row.get("unavailable_count") or 0)
        status = str(row.get("status") or "").strip().lower()
        warning_code = str(row.get("warning_code") or "").strip()
        if unavailable_count > 0 or status in {"unknown", "missing", "failed", "unavailable"}:
            issues.append(
                _issue(
                    warning_code or "read_model_runtime_unavailable",
                    key,
                    {"unavailable_count": unavailable_count, "status": status, "critical": definition.critical},
                )
            )
        elif stale_count > 0:
            issues.append(
                AuditIssue(
                    severity="error",
                    code="read_model_scope_not_fresh",
                    message="App Health system proof found stale current-effective read model scopes.",
                    subject_id=key,
                    details={"stale_count": stale_count, "critical": definition.critical},
                )
            )
    return issues


def _version_set(registrations: tuple[PageAuditRegistration, ...]) -> dict[str, Any]:
    pages = [
        {
            "page_key": registration.page_key,
            "executor": registration.executor,
            "contract_revision": registration.contract_revision,
            "read_model_keys": list(registration.read_model_keys),
            "external_evidence_keys": list(registration.external_evidence_keys),
        }
        for registration in registrations
    ]
    read_models = [asdict(READ_MODEL_MANIFEST[key]) for key in sorted(READ_MODEL_MANIFEST)]
    workers = [asdict(registration) for registration in worker_registrations()]
    return {
        "page_contracts": pages,
        "page_registry_fingerprint": _fingerprint(pages),
        "read_model_manifest_fingerprint": _fingerprint(read_models),
        "runtime_worker_registry_fingerprint": _fingerprint(workers),
        "external_control_evidence_contract_version": EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION,
    }


def _external_page_coverage(
    registrations: tuple[PageAuditRegistration, ...],
    external_evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    domain_status = {
        str(row.get("domain") or ""): str(row.get("status") or "unknown")
        for row in list(external_evidence.get("domains") or [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for registration in registrations:
        dependencies = list(registration.external_evidence_keys)
        statuses = [domain_status.get(domain, "unknown") for domain in dependencies]
        if not statuses:
            status = "not_applicable"
        elif "fail" in statuses:
            status = "fail"
        elif "unknown" in statuses:
            status = "unknown"
        else:
            status = "pass"
        rows.append(
            {
                "page_key": registration.page_key,
                "status": status,
                "dependency_keys": dependencies,
                "boundary": registration.external_source_boundary,
            }
        )
    return rows


def _inventory(*, total_count: Any, latest_synced_at: str | None, sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_count": _integer(total_count),
        "latest_synced_at": latest_synced_at,
        "sources": sources,
        "status": "available",
    }


def _source(
    key: str,
    label: str,
    count: Any,
    latest_synced_at: str | None,
    *,
    supplementary_count: Any = None,
) -> dict[str, Any]:
    row = {
        "key": key,
        "label": label,
        "count": _integer(count),
        "latest_synced_at": latest_synced_at,
        "status": "available",
    }
    if supplementary_count is not None or key == "oa_attachment":
        row["supplementary_count"] = _integer(supplementary_count)
    return row


def _issue(code: str, subject_id: str, details: dict[str, Any]) -> AuditIssue:
    return AuditIssue(
        severity="error",
        code=code,
        message=f"App Health system proof failed: {code}",
        subject_id=subject_id,
        details=details,
    )


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _integer(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat() if callable(isoformat) else value)


def _normalized_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_normalized_json(value).encode("utf-8")).hexdigest()


_EXPECTED_BANK_SQL = """
select
  count(*) filter (where coalesce(nullif(bank.status, ''), 'active') <> 'deleted')::bigint as total_count,
  max(coalesce(batch.imported_at, bank.updated_at, bank.created_at)) as latest_synced_at
from app.bank_transactions bank
left join app.import_batches batch
  on batch.id = bank.source_batch_id or batch.legacy_mongo_id = bank.legacy_source_batch_id
"""


_EXPECTED_INVOICE_SQL = """
with canonical as (
  select
    invoice.id,
    lower(coalesce(nullif(invoice.invoice_type, ''), '')) as invoice_type,
    coalesce(batch.imported_at, invoice.updated_at, invoice.created_at) as latest_synced_at,
    exists (
      select 1 from jsonb_array_elements(
        case when jsonb_typeof(invoice.source_links) = 'array' then invoice.source_links else '[]'::jsonb end
      ) link(value)
      where lower(coalesce(link.value->>'source_type', link.value->>'type', link.value->>'source', '')) = 'manual_invoice_import'
    ) as is_manual,
    exists (
      select 1 from jsonb_array_elements(
        case when jsonb_typeof(invoice.source_links) = 'array' then invoice.source_links else '[]'::jsonb end
      ) link(value)
      where lower(coalesce(link.value->>'source_type', link.value->>'type', link.value->>'source', '')) = 'oa_attachment_invoice'
    ) as is_oa_attachment
  from app.invoices invoice
  left join app.import_batches batch
    on batch.id = invoice.source_batch_id or batch.legacy_mongo_id = invoice.legacy_source_batch_id
  where coalesce(nullif(invoice.status, ''), 'active') <> 'deleted'
)
select
  count(*)::bigint as total_count,
  count(*) filter (where is_manual)::bigint as manual_count,
  count(*) filter (where invoice_type in ('input', 'input_invoice'))::bigint as input_invoice_count,
  count(*) filter (where invoice_type in ('output', 'output_invoice'))::bigint as output_invoice_count,
  count(*) filter (where is_oa_attachment)::bigint as oa_attachment_count,
  count(*) filter (where is_oa_attachment and not is_manual)::bigint as oa_attachment_non_manual_count,
  max(latest_synced_at) as latest_synced_at,
  max(latest_synced_at) filter (where is_manual) as manual_latest_synced_at,
  max(latest_synced_at) filter (where invoice_type in ('input', 'input_invoice')) as input_invoice_latest_synced_at,
  max(latest_synced_at) filter (where invoice_type in ('output', 'output_invoice')) as output_invoice_latest_synced_at,
  max(latest_synced_at) filter (where is_oa_attachment) as oa_attachment_latest_synced_at
from canonical
"""


_EXPECTED_OA_SQL = """
with pending_ids as (
  select row_id as oa_id,
         case when coalesce(nullif(workflow_status, ''), 'completed') = any(%s::text[])
              then 'completed' else 'in_progress' end as view_mode,
         synced_at as generated_at
  from app.oa_applications
  where status <> 'deleted'
  union all
  select admission.oa_id, 'in_progress', admission.updated_at
  from app.oa_pending_payment_admissions admission
  where not exists (
    select 1 from app.oa_applications source
    where source.row_id = admission.oa_id
      and source.status <> 'deleted'
  )
)
select
  (select count(*)::bigint from app.oa_applications) as oa_records_count,
  (select count(*)::bigint from app.oa_applications where coalesce(nullif(workflow_status, ''), 'completed') = any(%s::text[])) as oa_records_completed_count,
  (select count(distinct oa_id)::bigint from pending_ids where view_mode = 'in_progress') as oa_records_in_progress_count,
  (select max(generated_at) from pending_ids where view_mode = 'in_progress') as oa_pending_payment_in_progress_latest_synced_at,
  (select count(*)::bigint from app.oa_application_items) as oa_items_count,
  coalesce(
    (select max(coalesce(finished_at, started_at)) from app.oa_sync_runs where sync_type = 'oa_projection' and status in ('success', 'succeeded', 'done')),
    (select max(last_success_at) from app.oa_sync_watermarks),
    (select max(synced_at) from app.oa_applications)
  ) as oa_latest_synced_at
"""


_EXPECTED_IMPORT_EVENTS_SQL = """
select
  coalesce(legacy_mongo_id, id::text) as event_id,
  case when batch_type = 'bank_transaction' then 'bank_transactions' else 'manual' end as source_key,
  case when batch_type = 'bank_transaction' then '流水导入' else '手工导入' end as label,
  source_name,
  imported_by,
  success_count::bigint as count,
  imported_at,
  status
from app.import_batches
where batch_type in ('bank_transaction', 'input_invoice', 'output_invoice')
order by imported_at desc, event_id desc
"""
