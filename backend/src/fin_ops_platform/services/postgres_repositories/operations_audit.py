from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fin_ops_platform.services.page_audit_registry import (
    PAGE_AUDIT_REGISTRY,
    PageAuditRegistration,
    page_audit_registration,
)
from fin_ops_platform.services.postgres_repositories.app_health_system_audit import (
    audit_app_health_system_snapshot,
)
from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    AuditSnapshot,
    evaluate_audit_issues,
    read_only_audit_snapshot,
    use_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.bank_transaction_import_page_audit import (
    audit_bank_transaction_import_page,
)
from fin_ops_platform.services.postgres_repositories.common import jsonb, serialize_value
from fin_ops_platform.services.postgres_repositories.cost_statistics_page_audit import audit_cost_statistics_page
from fin_ops_platform.services.postgres_repositories.etc_import_page_audit import audit_etc_import_page
from fin_ops_platform.services.postgres_repositories.etc_tickets_page_audit import audit_etc_tickets_page
from fin_ops_platform.services.postgres_repositories.invoice_import_page_audit import audit_invoice_import_page
from fin_ops_platform.services.postgres_repositories.page_business_audit import audit_page_business_read_model
from fin_ops_platform.services.postgres_repositories.settings_page_audit import audit_settings_page
from fin_ops_platform.services.postgres_repositories.tax_offset_page_audit import audit_tax_offset_page
from fin_ops_platform.services.postgres_repositories.workbench_page_audit import audit_workbench_relation_display


class PostgresOperationsAuditRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def append_operation_event(self, event: dict[str, Any]) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            insert into audit.events(
                event_type, object_type, object_id, actor_id, actor_name, scope,
                trace_id, occurred_at, action, page_key, operation_location,
                reason, outcome, request_id, payload, raw_payload
            )
            values (
                %s, %s, %s, %s, %s, %s,
                %s, coalesce(%s::timestamptz, now()), %s, %s, %s,
                %s, %s, %s, %s, '{}'::jsonb
            )
            returning id::text as id, occurred_at
            """,
            (
                event.get("event_type") or "operation.action",
                event.get("object_type"),
                event.get("object_id"),
                event.get("actor_id"),
                event.get("actor_name"),
                event.get("scope"),
                event.get("trace_id"),
                event.get("occurred_at"),
                event.get("action"),
                event.get("page_key"),
                event.get("operation_location"),
                event.get("reason"),
                event.get("outcome") or "success",
                event.get("request_id"),
                jsonb(serialize_value(event.get("payload") or {})),
            ),
        )
        if row is None:
            raise RuntimeError("Audit event was not persisted.")
        return row

    def list_operation_events(
        self,
        *,
        limit: int,
        cursor_occurred_at: str | None = None,
        cursor_id: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        page_key: str | None = None,
        object_type: str | None = None,
        outcome: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = [
            "occurred_at >= coalesce((select max(occurred_at) from audit.events where event_type = 'audit.coverage_started'), '-infinity'::timestamptz)"
        ]
        params: list[Any] = []
        if cursor_occurred_at and cursor_id:
            conditions.append("(occurred_at, id) < (%s::timestamptz, %s::uuid)")
            params.extend((cursor_occurred_at, cursor_id))
        for column, value in (
            ("actor_id", actor_id),
            ("action", action),
            ("page_key", page_key),
            ("object_type", object_type),
            ("outcome", outcome),
        ):
            if value:
                conditions.append(f"{column} = %s")
                params.append(value)
        if date_from:
            conditions.append("occurred_at >= %s::timestamptz")
            params.append(date_from)
        if date_to:
            conditions.append("occurred_at < (%s::date + interval '1 day')")
            params.append(date_to)
        if search:
            conditions.append(
                "lower(concat_ws(' ', actor_id, actor_name, event_type, action, page_key, object_type, object_id, payload->>'summary')) like %s"
            )
            params.append(f"%{search.lower()}%")
        params.append(max(1, min(int(limit), 201)))
        return self._connection.fetch_all(
            f"""
            select id::text as id, event_type, object_type, object_id, actor_id, actor_name,
                   scope, trace_id, occurred_at, action, page_key, operation_location,
                   reason, outcome, request_id, payload
            from audit.events
            where {' and '.join(conditions)}
            order by occurred_at desc, id desc
            limit %s
            """,
            tuple(params),
        )

    def get_operation_event(self, event_id: str) -> dict[str, Any] | None:
        return self._connection.fetch_one(
            """
            select id::text as id, event_type, object_type, object_id, actor_id, actor_name,
                   scope, trace_id, occurred_at, action, page_key, operation_location,
                   reason, outcome, request_id, payload
            from audit.events
            where id = %s::uuid
              and occurred_at >= coalesce(
                  (select max(occurred_at) from audit.events where event_type = 'audit.coverage_started'),
                  '-infinity'::timestamptz
              )
            """,
            (event_id,),
        )

    def audit_page(
        self,
        *,
        page_key: str,
        tenant_id: str,
        sample_limit: int,
    ) -> dict[str, Any]:
        registration = page_audit_registration(page_key)
        if registration.executor == "system":
            raise ValueError("App Health system audit requires the explicit system orchestration boundary.")
        return self._audit_registration(
            registration,
            tenant_id=tenant_id,
            sample_limit=sample_limit,
        )

    def audit_system(
        self,
        *,
        tenant_id: str,
        sample_limit: int,
        dashboard_payload_builder: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_tenant = str(tenant_id or "default").strip() or "default"
        limit = max(int(sample_limit or 50), 1)
        registrations = tuple(PAGE_AUDIT_REGISTRY.values())
        if any(registration.availability != "ready" for registration in registrations):
            unavailable = [
                registration.page_key for registration in registrations if registration.availability != "ready"
            ]
            raise ValueError(f"System audit requires every registered page proof to be ready: {unavailable}")
        with read_only_audit_snapshot(self._connection) as snapshot:
            identity_row = snapshot.connection.fetch_one(
                "select pg_current_snapshot()::text as snapshot_identity, transaction_timestamp() as snapshot_generated_at"
            ) or {}
            snapshot_identity = str(identity_row.get("snapshot_identity") or "").strip()
            if snapshot.database_snapshot and not snapshot_identity:
                raise ValueError("PostgreSQL system audit snapshot identity is unavailable.")
            snapshot_generated_at = _isoformat(identity_row.get("snapshot_generated_at"))
            page_reports = [
                self._audit_registration(
                    registration,
                    tenant_id=normalized_tenant,
                    sample_limit=limit,
                    audit_snapshot=snapshot,
                    system_snapshot_identity=snapshot_identity,
                )
                for registration in registrations
                if registration.executor != "system"
            ]
            dashboard_payload = dashboard_payload_builder(snapshot.connection)
            payload = audit_app_health_system_snapshot(
                snapshot.connection,
                tenant_id=normalized_tenant,
                sample_limit=limit,
                snapshot_identity=snapshot_identity,
                snapshot_generated_at=snapshot_generated_at,
                snapshot_consistency=snapshot.consistency,
                database_snapshot=snapshot.database_snapshot,
                registrations=registrations,
                page_reports=page_reports,
                dashboard_payload=dashboard_payload,
            )
            system_registration = page_audit_registration("app-health-operations")
            return self._registered_payload(payload, system_registration, system_snapshot_identity=snapshot_identity)

    def _audit_registration(
        self,
        registration: PageAuditRegistration,
        *,
        tenant_id: str,
        sample_limit: int,
        audit_snapshot: AuditSnapshot | None = None,
        system_snapshot_identity: str = "",
    ) -> dict[str, Any]:
        if registration.executor == "workbench":
            payload = audit_workbench_relation_display(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "cost_statistics":
            payload = audit_cost_statistics_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "page_business":
            payload = audit_page_business_read_model(
                self._connection,
                domain_key=str(registration.executor_domain_key),
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "tax_offset":
            payload = audit_tax_offset_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "etc_tickets":
            payload = audit_etc_tickets_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "etc_import":
            payload = audit_etc_import_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "settings":
            payload = audit_settings_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "imports_center":
            payload = audit_import_center_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "bank_transaction_import":
            payload = audit_bank_transaction_import_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "invoice_import":
            payload = audit_invoice_import_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "operation_history":
            payload = audit_operation_history_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        else:
            raise ValueError(f"Page audit proof is unavailable for {registration.page_key}.")
        return self._registered_payload(
            payload,
            registration,
            system_snapshot_identity=system_snapshot_identity,
        )

    @staticmethod
    def _registered_payload(
        payload: dict[str, Any],
        registration: PageAuditRegistration,
        *,
        system_snapshot_identity: str = "",
    ) -> dict[str, Any]:
        audit_contract = dict(payload.get("audit_contract") or {})
        audit_contract.update(
            {
                "contract_revision": registration.contract_revision,
                "proof_availability": registration.availability,
                "registered_read_model_keys": list(registration.read_model_keys),
                "relation_proof_required": registration.relation_proof_required,
                **(
                    {"system_snapshot_identity": system_snapshot_identity}
                    if system_snapshot_identity
                    else {}
                ),
            }
        )
        return {
            **payload,
            "page_key": registration.page_key,
            "label": registration.label,
            "audit_contract": audit_contract,
        }


def audit_import_center_page(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        reports = (
            audit_bank_transaction_import_page(
                connection,
                tenant_id=tenant_id,
                example_limit=example_limit,
                audit_snapshot=snapshot,
            ),
            audit_invoice_import_page(
                connection,
                tenant_id=tenant_id,
                example_limit=example_limit,
                audit_snapshot=snapshot,
            ),
            audit_etc_import_page(
                connection,
                tenant_id=tenant_id,
                example_limit=example_limit,
                audit_snapshot=snapshot,
            ),
        )
        integrity = "issues_found" if any(report["audit_status"]["integrity"] != "pass" for report in reports) else "pass"
        freshness = "not_fresh" if any(report["audit_status"]["freshness"] != "fresh" for report in reports) else "fresh"
        queue = "backlog" if any(report["audit_status"]["queue"] != "drained" for report in reports) else "drained"
        issues = [issue for report in reports for issue in report.get("issues", [])]
        return {
            "mode": "import-center-page-audit",
            "tenant_id": tenant_id,
            "overall_status": "issues_found" if any(report["overall_status"] != "pass" for report in reports) else "pass",
            "audit_status": {"integrity": integrity, "freshness": freshness, "queue": queue},
            "summary": {
                "component_count": len(reports),
                "blocking_component_count": sum(report["overall_status"] != "pass" for report in reports),
                "issue_sample_count": len(issues),
            },
            "issues": issues[: max(int(example_limit or 50), 1)],
            "audit_contract": {
                "source_tables": [
                    "app.import_files",
                    "app.file_objects",
                    "app.import_batches",
                    "app.import_batch_rows",
                    "app.etc_import_sessions",
                    "app.etc_import_session_files",
                    "job.import_jobs",
                    "job.outbox_events",
                ],
                "read_model_tables": [],
                "canonical_expected_set": "all registered bank, invoice, and ETC import file/session/batch facts",
                "key_display_fields": ["file, batch type, status, row counts, operator, and time"],
                "relation_edge_equality": "delegated to the three canonical import page proofs in the same snapshot",
                "proof_checks": ["bank_import_page_proof", "invoice_import_page_proof", "etc_import_page_proof"],
                "snapshot_consistency": snapshot.consistency,
                "database_snapshot": snapshot.database_snapshot,
                "external_source_boundary": "external bank, invoice, and ETC source completeness before upload",
                "downstream_impact_targets": [],
                "pass_condition": (
                    "all three import page proofs pass integrity, freshness, and queue checks in one read-only snapshot"
                ),
                "guarantee_boundary": "the center is a read-only summary and does not own a second import fact model",
                "write_policy": "read_only",
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }

def _isoformat(value: Any) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat() if callable(isoformat) else value)


def audit_operation_history_page(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
    audit_snapshot: AuditSnapshot | None = None,
) -> dict[str, Any]:
    with use_audit_snapshot(connection, audit_snapshot) as snapshot:
        row = snapshot.connection.fetch_one(
            """
            select
                (select count(*) from audit.events where event_type = 'audit.coverage_started') as coverage_count,
                exists (
                    select 1 from pg_trigger
                    where tgrelid = 'audit.events'::regclass
                      and tgname = 'audit_events_append_only'
                      and not tgisinternal
                ) as audit_append_only,
                exists (
                    select 1 from pg_trigger
                    where tgrelid = 'app.financial_fact_corrections'::regclass
                      and tgname = 'financial_fact_corrections_append_only'
                      and not tgisinternal
                ) as correction_append_only,
                exists (
                    select 1 from pg_trigger
                    where tgrelid = 'app.workbench_pair_relation_history'::regclass
                      and tgname = 'workbench_pair_relation_history_append_only'
                      and not tgisinternal
                ) as relation_history_append_only
            """
        ) or {}
        checks = {
            "coverage_marker": int(row.get("coverage_count") or 0) == 1,
            "audit_append_only": bool(row.get("audit_append_only")),
            "correction_append_only": bool(row.get("correction_append_only")),
            "relation_history_append_only": bool(row.get("relation_history_append_only")),
        }
        issues = [
            AuditIssue(
                "error",
                "operation_audit_append_only_contract_missing",
                "操作历史追加写保护未完整启用。",
                subject_id=name,
            )
            for name, passed in checks.items()
            if not passed
        ]
        evaluation = evaluate_audit_issues(issues, sample_limit=max(int(example_limit or 50), 1))
        return {
            "mode": "operation-history-page-audit",
            "tenant_id": str(tenant_id or "default").strip() or "default",
            "overall_status": evaluation.overall_status,
            "audit_status": evaluation.audit_status,
            "summary": {"checks": checks, **evaluation.summary},
            "issues": evaluation.issue_samples,
            "audit_contract": {
                "source_tables": [
                    "audit.events",
                    "app.financial_fact_corrections",
                    "app.workbench_pair_relation_history",
                ],
                "read_model_tables": [],
                "canonical_expected_set": "post-coverage append-only operation and financial correction events",
                "key_display_fields": [
                    "operator and time",
                    "page and operation location",
                    "action and outcome",
                    "before and after values",
                    "reason",
                ],
                "relation_edge_equality": "not_applicable: this page reads audit facts only",
                "snapshot_consistency": snapshot.consistency,
                "database_snapshot": snapshot.database_snapshot,
                "external_source_boundary": "not_applicable: audit events are App-internal durable facts",
                "pass_condition": "coverage marker and all append-only database triggers exist",
                "guarantee_boundary": "proves database append-only controls at this snapshot; later writes are not inferred",
                "write_policy": "read_only",
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }
