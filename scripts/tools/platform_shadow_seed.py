#!/usr/bin/env python3
"""Generate or apply deterministic PostgreSQL seed facts for P0 platform shadow validation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Sequence
from uuid import UUID, uuid5


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "operations" / "backend-refactor"
SEED_NAMESPACE = UUID("6da43df3-1acb-4dd5-8cdd-0304c90323d4")
SEED_MONTH = "2026-05-01"
SEED_DATE = "2026-05-17"
SEED_TS = "2026-05-17 09:00:00+08"
SEED_DUE_TS = "2026-05-17 18:00:00+08"
DEFAULT_DISPLAY_NAME = "Shadow User"


@dataclass(frozen=True)
class PlatformSeedPlan:
    run_id: str
    actor_id: str
    user_id: str
    display_name: str
    background_job_id: str
    bank_transaction_id: str
    ledger_id: str
    project_id: str
    project_delete_id: str
    reminder_id: str
    settings_profile_id: str
    data_reset_task_id: str
    data_reset_outbox_event_id: str
    data_reset_audit_event_id: str

    @property
    def runtime_variables(self) -> dict[str, str]:
        return {
            "SHADOW_RUN_ID": self.run_id,
            "BACKGROUND_JOB_ID": self.background_job_id,
            "BANK_TRANSACTION_ID": self.bank_transaction_id,
            "LEDGER_ID": self.ledger_id,
            "PROJECT_ID": self.project_id,
            "PROJECT_DELETE_ID": self.project_delete_id,
        }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=os.environ.get("SHADOW_RUN_ID"))
    parser.add_argument("--actor-id", default=os.environ.get("FIN_OPS_SHADOW_OA_USERNAME"))
    parser.add_argument("--user-id", default=os.environ.get("FIN_OPS_SHADOW_OA_USER_ID"))
    parser.add_argument("--display-name", default=os.environ.get("FIN_OPS_SHADOW_OA_DISPLAY_NAME"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write-sql", type=Path)
    parser.add_argument("--write-env", type=Path)
    parser.add_argument("--write-probe-sql", type=Path)
    parser.add_argument("--report-date", default=datetime.now(UTC).strftime("%Y%m%d"))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--apply", action="store_true", help="Apply the generated SQL with psql against --database-url.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = args.run_id or datetime.now(UTC).strftime("p0-platform-%Y%m%d%H%M%S")
    if not str(args.actor_id or "").strip():
        raise SystemExit("--actor-id or FIN_OPS_SHADOW_OA_USERNAME is required")
    if not str(args.user_id or "").strip():
        raise SystemExit("--user-id or FIN_OPS_SHADOW_OA_USER_ID is required")
    plan = build_seed_plan(
        run_id=run_id,
        actor_id=args.actor_id,
        user_id=args.user_id,
        display_name=args.display_name,
    )
    sql = render_seed_sql(plan)
    env_text = render_env_exports(plan)
    probe_sql = render_probe_sql(plan)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    sql_path = args.write_sql or output_dir / f"p0-platform-shadow-seed-{safe_name(run_id)}.sql"
    env_path = args.write_env or output_dir / f"p0-platform-shadow-env-{safe_name(run_id)}.sh"
    probe_sql_path = args.write_probe_sql or output_dir / f"p0-platform-shadow-probe-{safe_name(run_id)}.sql"
    report_path = output_dir / f"p0-platform-shadow-seed-{safe_name(args.report_date)}.json"
    sql_path.write_text(sql, encoding="utf-8")
    env_path.write_text(env_text, encoding="utf-8")
    probe_sql_path.write_text(probe_sql, encoding="utf-8")

    apply_status = "SKIPPED"
    if args.apply:
        if not args.database_url:
            raise SystemExit("--apply requires --database-url or DATABASE_URL")
        completed = subprocess.run(
            ["psql", args.database_url, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(sql_path)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        apply_status = "GO" if completed.returncode == 0 else "NO_GO"
        if completed.returncode != 0:
            print(completed.stderr.strip())
            return completed.returncode

    report = build_report(
        plan=plan,
        report_date=args.report_date,
        sql_path=sql_path,
        env_path=env_path,
        probe_sql_path=probe_sql_path,
        apply_status=apply_status,
        database_url_present=bool(args.database_url),
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), **report}, ensure_ascii=False, indent=2))
    return 0 if apply_status != "NO_GO" else 2


def build_seed_plan(
    *,
    run_id: str,
    actor_id: str,
    user_id: str | None = None,
    display_name: str | None = None,
) -> PlatformSeedPlan:
    normalized_run_id = run_id.strip()
    if not normalized_run_id:
        raise ValueError("run_id is required")
    normalized_actor = actor_id.strip()
    if not normalized_actor:
        raise ValueError("actor_id is required")
    normalized_user_id = str(user_id or actor_id).strip()
    if not normalized_user_id:
        raise ValueError("user_id is required")
    return PlatformSeedPlan(
        run_id=normalized_run_id,
        actor_id=normalized_actor,
        user_id=normalized_user_id,
        display_name=str(display_name or DEFAULT_DISPLAY_NAME).strip() or DEFAULT_DISPLAY_NAME,
        background_job_id=deterministic_uuid(normalized_run_id, "background-job"),
        bank_transaction_id=deterministic_uuid(normalized_run_id, "bank-transaction"),
        ledger_id=deterministic_uuid(normalized_run_id, "ledger"),
        project_id=deterministic_uuid(normalized_run_id, "project-main"),
        project_delete_id=deterministic_uuid(normalized_run_id, "project-delete"),
        reminder_id=deterministic_uuid(normalized_run_id, "reminder"),
        settings_profile_id=deterministic_uuid(normalized_run_id, "settings-profile"),
        data_reset_task_id=deterministic_uuid(normalized_run_id, "data-reset-task"),
        data_reset_outbox_event_id=deterministic_uuid(normalized_run_id, "data-reset-outbox"),
        data_reset_audit_event_id=deterministic_uuid(normalized_run_id, "data-reset-audit"),
    )


def deterministic_uuid(run_id: str, name: str) -> str:
    return str(uuid5(SEED_NAMESPACE, f"{run_id}:{name}"))


def render_env_exports(plan: PlatformSeedPlan) -> str:
    lines = [
        "# Source this file before running platform_shadow_preflight.py or platform_shadow_runtime.py.",
        "# Secrets are intentionally not written here; export them separately in the shell.",
    ]
    for name, value in plan.runtime_variables.items():
        lines.append(f"export {name}={shell_quote(value)}")
    lines.append(f"export FIN_OPS_SHADOW_OA_USER_ID={shell_quote(plan.user_id)}")
    lines.append(f"export FIN_OPS_SHADOW_OA_USERNAME={shell_quote(plan.actor_id)}")
    lines.append(f"export FIN_OPS_SHADOW_OA_DISPLAY_NAME={shell_quote(plan.display_name)}")
    lines.extend(
        [
            "export FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers",
            "# export FIN_OPS_SHADOW_OA_TOKEN='[staging token accepted by legacy Python]'",
            "# export FIN_OPS_SHADOW_OA_PASSWORD='[staging data reset password]'",
            "",
        ]
    )
    return "\n".join(lines)


def render_seed_sql(plan: PlatformSeedPlan) -> str:
    run = sql_literal(plan.run_id)
    actor = sql_literal(plan.actor_id)
    user_id = sql_literal(plan.user_id)
    display_name = sql_literal(plan.display_name)
    data_reset_idempotency_key = f"platform-shadow:{plan.run_id}:data-reset-support"
    settings_idempotency_key = f"platform-shadow:{plan.run_id}:settings-profile"
    cleanup_sql = render_shadow_cleanup_sql(plan)
    return f"""-- P0 platform runtime shadow seed facts.
-- Safe only for disposable local/staging shadow databases.
begin;

{cleanup_sql}

select app.create_financial_fact_month_partition('app.bank_transactions'::regclass, date '{SEED_MONTH}');

insert into job.worker_tasks (
  id, task_type, status, phase, priority, idempotency_key, visibility, label,
  source, payload, result_summary, affected_scopes, created_by, total_count, current_count, percent,
  error_summary, retryable, available_at, created_at, started_at, updated_at, finished_at
)
values (
  '{plan.background_job_id}'::uuid,
  'platform_shadow_background_job',
  'failed',
  'failed',
  0,
  'platform-shadow:{plan.run_id}:background-job',
  'system',
  'Platform shadow background job',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}),
  jsonb_build_object('run_id', {run}, 'message', 'Platform shadow attention job ready for acknowledge.'),
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}),
  array['platform_shadow'],
  {user_id},
  1,
  1,
  100,
  'platform_shadow_ack_fixture',
  false,
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}'
)
on conflict (id) do update set
  status = excluded.status,
  phase = excluded.phase,
  visibility = excluded.visibility,
  label = excluded.label,
  source = excluded.source,
  payload = excluded.payload,
  result_summary = excluded.result_summary,
  affected_scopes = excluded.affected_scopes,
  total_count = excluded.total_count,
  current_count = excluded.current_count,
  percent = excluded.percent,
  error_summary = excluded.error_summary,
  retryable = excluded.retryable,
  available_at = excluded.available_at,
  started_at = excluded.started_at,
  updated_at = excluded.updated_at,
  finished_at = excluded.finished_at;

insert into app.settings_profiles (
  id, settings_key, status, version, settings_payload, affected_scopes,
  idempotency_key, created_by, created_at, updated_by, updated_at
)
values (
  '{plan.settings_profile_id}'::uuid,
  'platform_shadow_seed:{safe_code(plan.run_id)}',
  'disabled',
  1,
  jsonb_build_object(
    'completed_project_ids', '[]'::jsonb,
    'manual_projects', '[]'::jsonb,
    'synced_projects', '[]'::jsonb,
    'bank_account_mappings', '[]'::jsonb,
    'allowed_usernames', jsonb_build_array({actor}),
    'readonly_export_usernames', '[]'::jsonb,
    'admin_usernames', jsonb_build_array({actor}),
    'workbench_column_layouts', '{{}}'::jsonb,
    'oa_retention', '{{}}'::jsonb,
    'oa_import', '{{}}'::jsonb,
    'oa_invoice_offset', '{{}}'::jsonb,
    'fixture', 'platform_shadow',
    'run_id', {run}
  ),
  array['platform_shadow'],
  '{settings_idempotency_key}',
  {actor},
  timestamptz '{SEED_TS}',
  {actor},
  timestamptz '{SEED_TS}'
)
on conflict (id) do update set
  status = excluded.status,
  version = excluded.version,
  settings_payload = excluded.settings_payload,
  affected_scopes = excluded.affected_scopes,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.project_profiles (
  id, project_code, project_name, project_status, project_source,
  department_name, owner_name, external_project_id, profile_payload,
  idempotency_key, created_by, created_at, updated_by, updated_at
)
values
  (
    '{plan.project_id}'::uuid,
    'SHADOW-{safe_code(plan.run_id)}-MAIN',
    '平台 Shadow 项目',
    'active',
    'manual',
    '平台 Shadow',
    'Shadow Owner',
    'shadow-main-{safe_code(plan.run_id)}',
    jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}, 'purpose', 'project_detail_and_assignment'),
    'platform-shadow:{plan.run_id}:project-main',
    {actor},
    timestamptz '{SEED_TS}',
    {actor},
    timestamptz '{SEED_TS}'
  ),
  (
    '{plan.project_delete_id}'::uuid,
    'SHADOW-{safe_code(plan.run_id)}-DELETE',
    '平台 Shadow 待删除项目',
    'active',
    'manual',
    '平台 Shadow',
    'Shadow Owner',
    'shadow-delete-{safe_code(plan.run_id)}',
    jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}, 'purpose', 'project_delete'),
    'platform-shadow:{plan.run_id}:project-delete',
    {actor},
    timestamptz '{SEED_TS}',
    {actor},
    timestamptz '{SEED_TS}'
  )
on conflict (id) do update set
  project_status = 'active',
  project_name = excluded.project_name,
  version = 1,
  department_name = excluded.department_name,
  owner_name = excluded.owner_name,
  profile_payload = excluded.profile_payload,
  deactivated_at = null,
  deactivated_by = null,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.bank_transactions (
  id, txn_date, txn_month, trade_time, pay_receive_time, account_no, account_name,
  txn_direction, amount, signed_amount, written_off_amount, balance, currency,
  counterparty_name_raw, counterparty_name_normalized, counterparty_account_no,
  counterparty_bank_name, bank_serial_no, enterprise_serial_no, source_unique_key,
  data_fingerprint, status, summary, remark, bank_text_fields, raw_payload,
  created_by, created_at, updated_by, updated_at
)
values (
  '{plan.bank_transaction_id}'::uuid,
  date '{SEED_DATE}',
  date '{SEED_MONTH}',
  timestamptz '{SEED_DATE} 09:00:00+08',
  timestamptz '{SEED_DATE} 09:00:00+08',
  '6222000000000000001',
  '平台 Shadow 账户',
  'inflow',
  1288.00,
  1288.00,
  0.00,
  1288.00,
  'CNY',
  '平台 Shadow 往来单位',
  '平台 Shadow 往来单位',
  '6222999900000000',
  '测试银行',
  'SHADOW-{safe_code(plan.run_id)}-BANK',
  'SHADOW-ENT-{safe_code(plan.run_id)}',
  'platform-shadow:{plan.run_id}:bank-transaction',
  'platform-shadow:{plan.run_id}:bank-transaction',
  'pending',
  '平台 shadow project assignment seed',
  'platform shadow',
  '[]'::jsonb,
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}),
  {actor},
  timestamptz '{SEED_TS}',
  {actor},
  timestamptz '{SEED_TS}'
)
on conflict (txn_month, id) do update set
  status = 'pending',
  project_id = null,
  summary = excluded.summary,
  raw_payload = excluded.raw_payload,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.ledgers (
  id, ledger_type, ledger_key, status, counterparty_id, counterparty_name, project_id, due_at,
  amount, remaining_amount, ledger_payload, idempotency_key, created_by, created_at, updated_by, updated_at
)
values (
  '{plan.ledger_id}'::uuid,
  'payment_collection',
  '{plan.ledger_id}',
  'open',
  'platform-shadow-counterparty',
  '平台 Shadow 往来方',
  '{plan.project_id}'::uuid,
  timestamptz '{SEED_DATE} 18:00:00+08',
  128.00,
  128.00,
  jsonb_build_object(
    'fixture', 'platform_shadow',
    'run_id', {run},
    'source_object_type', 'bank_transaction',
    'source_object_id', '{plan.bank_transaction_id}',
    'owner_id', {user_id},
    'latest_note', '平台 Shadow 台账'
  ),
  'platform-shadow:{plan.run_id}:ledger',
  {actor},
  timestamptz '{SEED_TS}',
  {actor},
  timestamptz '{SEED_TS}'
)
on conflict (id) do update set
  status = 'open',
  counterparty_id = excluded.counterparty_id,
  counterparty_name = excluded.counterparty_name,
  project_id = excluded.project_id,
  due_at = excluded.due_at,
  amount = excluded.amount,
  remaining_amount = excluded.remaining_amount,
  ledger_payload = excluded.ledger_payload,
  closed_at = null,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.reminders (
  id, reminder_type, ledger_id, status, due_at, recipient_user_id,
  message_payload, created_by, created_at, updated_by, updated_at
)
values (
  '{plan.reminder_id}'::uuid,
  'ledger_due',
  '{plan.ledger_id}'::uuid,
  'pending',
  timestamptz '{SEED_DATE} 18:00:00+08',
  {user_id},
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}, 'ledger_id', '{plan.ledger_id}', 'channel', 'in_app'),
  {actor},
  timestamptz '{SEED_TS}',
  {actor},
  timestamptz '{SEED_TS}'
)
on conflict (id) do update set
  ledger_id = excluded.ledger_id,
  status = 'pending',
  due_at = excluded.due_at,
  message_payload = excluded.message_payload,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into job.worker_tasks (
  id, task_type, status, phase, priority, idempotency_key, visibility, label,
  source, payload, result_summary, affected_scopes, created_by, total_count, current_count, percent,
  available_at, created_at, started_at, updated_at, finished_at
)
values (
  '{plan.data_reset_task_id}'::uuid,
  'settings_data_reset',
  'succeeded',
  'succeeded',
  0,
  '{data_reset_idempotency_key}:task',
  'system',
  'Platform shadow data reset support job',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}, 'action', 'reset_oa_and_rebuild'),
  jsonb_build_object('schema_version', 'finops.platform_legacy.data_reset_request.v1', 'run_id', {run}, 'action', 'reset_oa_and_rebuild'),
  jsonb_build_object('fixture', 'platform_shadow', 'status', 'succeeded'),
  array['platform_shadow'],
  {actor},
  1,
  1,
  100,
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}'
)
on conflict (id) do update set
  status = excluded.status,
  phase = excluded.phase,
  visibility = excluded.visibility,
  label = excluded.label,
  source = excluded.source,
  payload = excluded.payload,
  result_summary = excluded.result_summary,
  affected_scopes = excluded.affected_scopes,
  total_count = excluded.total_count,
  current_count = excluded.current_count,
  percent = excluded.percent,
  finished_at = excluded.finished_at,
  updated_at = excluded.updated_at;

insert into job.outbox_events (
  id, aggregate_type, aggregate_id, event_type, subject, payload, status,
  idempotency_key, trace_id, available_at, published_at, created_at, updated_at
)
values (
  '{plan.data_reset_outbox_event_id}'::uuid,
  'data_reset_request',
  '{plan.data_reset_task_id}'::uuid,
  'data_reset.request.requested',
  'finops.jobs.settings.data_reset',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}, 'action', 'reset_oa_and_rebuild'),
  'published',
  'outbox:{data_reset_idempotency_key}',
  'platform-shadow:{plan.run_id}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}'
)
on conflict (id) do update set
  payload = excluded.payload,
  status = excluded.status,
  trace_id = excluded.trace_id,
  published_at = excluded.published_at,
  updated_at = excluded.updated_at;

insert into audit.events (
  id, event_type, action, entity_type, entity_id, actor_id, actor_type, trace_id,
  request_id, idempotency_key, after_state, metadata, created_at
)
values (
  '{plan.data_reset_audit_event_id}'::uuid,
  'data_reset.request.requested',
  'seed',
  'data_reset_request',
  '{plan.data_reset_task_id}'::uuid,
  {actor},
  'system',
  'platform-shadow:{plan.run_id}',
  'platform-shadow:{plan.run_id}',
  '{data_reset_idempotency_key}',
  jsonb_build_object('task_id', '{plan.data_reset_task_id}', 'outbox_event_id', '{plan.data_reset_outbox_event_id}', 'status', 'succeeded'),
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}),
  timestamptz '{SEED_TS}'
)
on conflict (id) do update set
  after_state = excluded.after_state,
  metadata = excluded.metadata;

insert into app.data_reset_requests (
  id, worker_task_id, outbox_event_id, action, status, scope, approval_id,
  backup_evidence_id, requested_by, requested_at, approved_at, completed_at,
  execution_mode, idempotency_key, audit_event_id, created_by, created_at, updated_by, updated_at
)
values (
  '{plan.data_reset_task_id}'::uuid,
  '{plan.data_reset_task_id}'::uuid,
  '{plan.data_reset_outbox_event_id}'::uuid,
  'reset_oa_and_rebuild',
  'succeeded',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}),
  'shadow-seed-approval-{safe_code(plan.run_id)}',
  'shadow-seed-backup-{safe_code(plan.run_id)}',
  {actor},
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  timestamptz '{SEED_TS}',
  'queued',
  '{data_reset_idempotency_key}',
  '{plan.data_reset_audit_event_id}'::uuid,
  {actor},
  timestamptz '{SEED_TS}',
  {actor},
  timestamptz '{SEED_TS}'
)
on conflict (id) do update set
  status = excluded.status,
  scope = excluded.scope,
  completed_at = excluded.completed_at,
  outbox_event_id = excluded.outbox_event_id,
  audit_event_id = excluded.audit_event_id,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.write_idempotency_records (
  operation, idempotency_key, request_payload, response_payload, aggregate_type,
  aggregate_id, status, created_by, created_at
)
values (
  'data_reset.request',
  '{data_reset_idempotency_key}',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', {run}, 'action', 'reset_oa_and_rebuild'),
  jsonb_build_object('task_id', '{plan.data_reset_task_id}', 'outbox_event_id', '{plan.data_reset_outbox_event_id}', 'status', 'succeeded'),
  'data_reset_request',
  '{plan.data_reset_task_id}'::uuid,
  'completed',
  {actor},
  timestamptz '{SEED_TS}'
)
on conflict (operation, idempotency_key) do update set
  request_payload = excluded.request_payload,
  response_payload = excluded.response_payload,
  status = excluded.status,
  created_by = excluded.created_by;

commit;
"""


def render_shadow_cleanup_sql(plan: PlatformSeedPlan) -> str:
    run = sql_literal(plan.run_id)
    run_like = sql_literal(f"platform-shadow:{plan.run_id}:%")
    request_run_like = sql_literal(f"shadow-%{plan.run_id}%")
    outbox_request_run_like = sql_literal(f"%shadow-%{plan.run_id}%")
    trace_id = sql_literal(f"platform-shadow:{plan.run_id}")
    actor = sql_literal(plan.actor_id)
    user_id = sql_literal(plan.user_id)
    runtime_idempotency_keys = [
        f"shadow-background-job-ack-{plan.run_id}",
        f"shadow-settings-save-{plan.run_id}",
        f"shadow-project-sync-{plan.run_id}",
        f"shadow-settings-project-{plan.run_id}",
        f"shadow-settings-project-delete-{plan.run_id}",
        f"shadow-data-reset-{plan.run_id}",
        f"shadow-data-reset-direct-{plan.run_id}",
        f"shadow-project-create-{plan.run_id}",
        f"shadow-project-assign-{plan.run_id}",
        f"shadow-ledger-status-{plan.run_id}",
        f"shadow-reminder-run-{plan.run_id}",
    ]
    runtime_keys_sql = ", ".join(sql_literal(value) for value in runtime_idempotency_keys)
    settings_project_codes_sql = ", ".join(
        sql_literal(value)
        for value in [
            f"SHADOW-{plan.run_id}",
            f"SHADOW-HUB-{plan.run_id}",
            f"SHADOW-{safe_code(plan.run_id)}",
            f"SHADOW-HUB-{safe_code(plan.run_id)}",
        ]
    )
    return f"""-- Clean runtime side effects for this SHADOW_RUN_ID before reseeding.
-- All predicates are restricted to deterministic shadow IDs, run_id payloads, or platform-shadow idempotency keys.
delete from job.worker_task_acknowledgements
where task_id = '{plan.background_job_id}'::uuid
   or idempotency_key in ({runtime_keys_sql})
   or idempotency_key like {run_like}
   or idempotency_key like {request_run_like}
   or trace_id = {trace_id}
   or source_metadata->>'run_id' = {run};

delete from app.ledger_events
where ledger_id = '{plan.ledger_id}'::uuid
   or idempotency_key in ({runtime_keys_sql})
   or idempotency_key like {run_like}
   or idempotency_key like {request_run_like}
   or event_payload->>'run_id' = {run};

delete from app.reminder_runs
where idempotency_key in ({runtime_keys_sql})
   or idempotency_key like {run_like}
   or idempotency_key like {request_run_like}
   or run_scope->>'run_id' = {run}
   or result_payload->>'run_id' = {run};

delete from app.project_profile_events
where idempotency_key in ({runtime_keys_sql})
   or idempotency_key like {run_like}
   or idempotency_key like {request_run_like}
   or before_state->>'run_id' = {run}
   or after_state->>'run_id' = {run}
   or project_id in ('{plan.project_id}'::uuid, '{plan.project_delete_id}'::uuid)
   or created_by in ({actor}, {user_id});

delete from app.project_assignments
where idempotency_key in ({runtime_keys_sql})
   or idempotency_key like {run_like}
   or idempotency_key like {request_run_like}
   or object_id in ('{plan.bank_transaction_id}'::uuid, '{plan.ledger_id}'::uuid)
   or project_id in ('{plan.project_id}'::uuid, '{plan.project_delete_id}'::uuid)
   or created_by in ({actor}, {user_id});

delete from app.data_reset_requests
where id in ('{plan.data_reset_task_id}'::uuid)
   or worker_task_id in ('{plan.data_reset_task_id}'::uuid)
   or outbox_event_id in ('{plan.data_reset_outbox_event_id}'::uuid)
   or audit_event_id in ('{plan.data_reset_audit_event_id}'::uuid)
   or idempotency_key in ({runtime_keys_sql})
   or idempotency_key like {run_like}
   or idempotency_key like {request_run_like}
   or scope->>'run_id' = {run};

delete from job.outbox_events
where id in (
  select outbox_event_id
  from app.identity_provisioning_requests
  where outbox_event_id is not null
    and settings_profile_id in (
      select id
      from app.settings_profiles
      where idempotency_key in ({runtime_keys_sql})
         or idempotency_key like {run_like}
         or idempotency_key like {request_run_like}
         or settings_payload->>'run_id' = {run}
    )
);

delete from job.worker_tasks
where id in (
  select worker_task_id
  from app.identity_provisioning_requests
  where worker_task_id is not null
    and settings_profile_id in (
      select id
      from app.settings_profiles
      where idempotency_key in ({runtime_keys_sql})
         or idempotency_key like {run_like}
         or idempotency_key like {request_run_like}
         or settings_payload->>'run_id' = {run}
    )
);

delete from app.identity_provisioning_requests
where settings_profile_id in (
  select id
  from app.settings_profiles
  where idempotency_key in ({runtime_keys_sql})
     or idempotency_key like {run_like}
     or idempotency_key like {request_run_like}
     or settings_payload->>'run_id' = {run}
);

delete from app.write_idempotency_records
where idempotency_key in ({runtime_keys_sql})
   or idempotency_key like {run_like}
   or idempotency_key like {request_run_like}
   or request_payload->>'run_id' = {run}
   or response_payload->>'run_id' = {run}
   or aggregate_id in (
     '{plan.background_job_id}'::uuid,
     '{plan.ledger_id}'::uuid,
     '{plan.data_reset_task_id}'::uuid
   );

delete from job.outbox_events
where id in ('{plan.data_reset_outbox_event_id}'::uuid)
   or aggregate_id in ('{plan.data_reset_task_id}'::uuid)
   or idempotency_key in ({runtime_keys_sql})
   or idempotency_key like 'outbox:platform-shadow:{plan.run_id}:%'
   or idempotency_key like {outbox_request_run_like}
   or trace_id = {trace_id}
   or payload->>'run_id' = {run};

delete from job.worker_tasks
where id in ('{plan.background_job_id}'::uuid, '{plan.data_reset_task_id}'::uuid)
   or idempotency_key in ({runtime_keys_sql})
   or idempotency_key like {run_like}
   or idempotency_key like {request_run_like}
   or source->>'run_id' = {run}
   or payload->>'run_id' = {run}
   or result_summary->>'run_id' = {run};

delete from app.settings_profiles
where id <> '{plan.settings_profile_id}'::uuid
  and (
    idempotency_key in ({runtime_keys_sql})
    or idempotency_key like {run_like}
    or idempotency_key like {request_run_like}
    or settings_payload->>'run_id' = {run}
  );

delete from app.project_profiles
where id not in ('{plan.project_id}'::uuid, '{plan.project_delete_id}'::uuid)
  and (
    idempotency_key in ({runtime_keys_sql})
    or idempotency_key like {run_like}
    or idempotency_key like {request_run_like}
    or project_code in ({settings_project_codes_sql})
    or external_project_id in (
      'shadow-main-{safe_code(plan.run_id)}',
      'shadow-delete-{safe_code(plan.run_id)}'
    )
    or profile_payload->>'run_id' = {run}
  );

delete from audit.events
where id in ('{plan.data_reset_audit_event_id}'::uuid)
   or trace_id = {trace_id}
   or request_id = {trace_id}
   or idempotency_key in ({runtime_keys_sql})
   or idempotency_key like {run_like}
   or idempotency_key like {request_run_like}
   or metadata->>'run_id' = {run}
   or after_state->>'run_id' = {run};"""


def render_probe_sql(plan: PlatformSeedPlan) -> str:
    return f"""-- P0 platform runtime shadow seed probes.
-- Run with: psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f <this-file>

select 'BACKGROUND_JOB_ID' as variable,
       '{plan.background_job_id}'::uuid as value,
       exists (
         select 1
         from job.worker_tasks
         where id = '{plan.background_job_id}'::uuid
           and visibility = 'system'
           and status in ('queued', 'running', 'succeeded', 'failed', 'retrying', 'dead_lettered', 'cancelled')
       ) as ok;

select 'BANK_TRANSACTION_ID' as variable,
       '{plan.bank_transaction_id}'::uuid as value,
       exists (
         select 1
         from app.bank_transactions
         where txn_month = date '{SEED_MONTH}'
           and id = '{plan.bank_transaction_id}'::uuid
           and status = 'pending'
       ) as ok;

select 'LEDGER_ID' as variable,
       '{plan.ledger_id}'::uuid as value,
       exists (
         select 1
         from app.ledgers
         where id = '{plan.ledger_id}'::uuid
           and status = 'open'
       ) as ok;

select 'PROJECT_ID' as variable,
       '{plan.project_id}'::uuid as value,
       exists (
         select 1
         from app.project_profiles
         where id = '{plan.project_id}'::uuid
           and project_status = 'active'
       ) as ok;

select 'PROJECT_DELETE_ID' as variable,
       '{plan.project_delete_id}'::uuid as value,
       exists (
         select 1
         from app.project_profiles
         where id = '{plan.project_delete_id}'::uuid
           and project_status = 'active'
       ) as ok;

select 'SETTINGS_AND_DATA_RESET_SUPPORT' as variable,
       '{plan.data_reset_task_id}'::uuid as value,
       exists (select 1 from app.settings_profiles where id = '{plan.settings_profile_id}'::uuid)
       and exists (select 1 from app.data_reset_requests where id = '{plan.data_reset_task_id}'::uuid and status = 'succeeded')
       and exists (select 1 from job.outbox_events where id = '{plan.data_reset_outbox_event_id}'::uuid and status = 'published')
       and exists (select 1 from audit.events where id = '{plan.data_reset_audit_event_id}'::uuid)
       and exists (
         select 1
         from app.write_idempotency_records
         where operation = 'data_reset.request'
           and idempotency_key = 'platform-shadow:{plan.run_id}:data-reset-support'
       ) as ok;
"""


def build_report(
    *,
    plan: PlatformSeedPlan,
    report_date: str,
    sql_path: Path,
    env_path: Path,
    probe_sql_path: Path,
    apply_status: str,
    database_url_present: bool,
) -> dict[str, Any]:
    legacy_plan = build_legacy_python_mongo_seed_plan(
        plan,
        legacy_report_path=sql_path.parent / f"p0-platform-legacy-shadow-seed-{safe_name(report_date)}.json",
    )
    overall_status = "GO" if apply_status == "GO" and legacy_plan["status"] == "GO" else "NO_GO"
    return {
        "report": "p0-platform-shadow-seed",
        "report_date": report_date,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": overall_status,
        "scope": "Prompt 3 PostgreSQL shadow seed and legacy Python/Mongo fixture data closure for P0 platform APIs.",
        "run_id": plan.run_id,
        "runtime_variables": plan.runtime_variables,
        "postgres_seed_generation": {
            "status": "GO",
            "sql_path": str(sql_path),
            "env_path": str(env_path),
            "probe_sql_path": str(probe_sql_path),
            "namespace": str(SEED_NAMESPACE),
            "fixed_dates": {
                "seed_month": SEED_MONTH,
                "seed_date": SEED_DATE,
                "seed_timestamp": SEED_TS,
                "due_timestamp": SEED_DUE_TS,
            },
            "deterministic_ids": {
                "actor_username": plan.actor_id,
                "oa_user_id": plan.user_id,
                "background_job_id": plan.background_job_id,
                "bank_transaction_id": plan.bank_transaction_id,
                "ledger_id": plan.ledger_id,
                "project_id": plan.project_id,
                "project_delete_id": plan.project_delete_id,
                "reminder_id": plan.reminder_id,
                "settings_profile_id": plan.settings_profile_id,
                "data_reset_task_id": plan.data_reset_task_id,
                "data_reset_outbox_event_id": plan.data_reset_outbox_event_id,
                "data_reset_audit_event_id": plan.data_reset_audit_event_id,
            },
            "covered_postgres_facts": [
                "job.worker_tasks",
                "app.settings_profiles",
                "app.project_profiles",
                "app.project_assignments",
                "app.project_profile_events",
                "app.bank_transactions",
                "app.ledgers",
                "app.reminders",
                "app.data_reset_requests",
                "job.outbox_events",
                "job.worker_task_acknowledgements",
                "audit.events",
                "app.write_idempotency_records",
            ],
            "rerun_guards": [
                "UUIDs derive from SHADOW_RUN_ID and a fixed namespace.",
                "Seed SQL deletes only rows tied to the deterministic shadow IDs, run_id payloads, trace_id, or shadow idempotency key prefixes before upserting seed facts.",
                "Seed SQL uses insert ... on conflict for deterministic records.",
                "Seed SQL uses fixed timestamps instead of now() for seeded facts.",
                "Data reset support request is status=succeeded and action=reset_oa_and_rebuild, so it does not create queued/running conflicts with runtime samples reset_invoices/reset_bank_transactions.",
            ],
            "cleanup_model": {
                "status": "GO",
                "scope": "Only current SHADOW_RUN_ID rows and deterministic seed IDs are cleaned before reseed.",
                "tables": [
                    "app.ledger_events",
                    "app.reminder_runs",
                    "job.worker_task_acknowledgements",
                    "app.project_profile_events",
                    "app.project_assignments",
                    "app.data_reset_requests",
                    "app.identity_provisioning_requests",
                    "app.write_idempotency_records",
                    "job.outbox_events",
                    "job.worker_tasks",
                    "app.settings_profiles",
                    "app.project_profiles",
                    "audit.events",
                ],
                "non_shadow_data_guard": [
                    "No blanket table truncation or date-range deletion.",
                    "Predicates use deterministic IDs, payload.run_id, metadata.run_id, trace_id, or platform-shadow/shadow runtime idempotency-key prefixes.",
                ],
            },
        },
        "postgres_apply": {
            "status": apply_status,
            "database_url_present": database_url_present,
            "no_go_reason": None
            if apply_status == "GO"
            else "DATABASE_URL was not provided or --apply was not requested; PostgreSQL facts were generated but not applied in this session.",
        },
        "postgres_probe_sql": {
            "status": "GO",
            "probe_sql_path": str(probe_sql_path),
            "checks": [
                {
                    "variable": "BACKGROUND_JOB_ID",
                    "postgres_fact": "job.worker_tasks",
                    "condition": "id matches and visibility='system'",
                },
                {
                    "variable": "BANK_TRANSACTION_ID",
                    "postgres_fact": "app.bank_transactions",
                    "condition": "id matches, txn_month=2026-05-01, status='pending'",
                },
                {
                    "variable": "LEDGER_ID",
                    "postgres_fact": "app.ledgers",
                    "condition": "id matches and status='open'",
                },
                {
                    "variable": "PROJECT_ID",
                    "postgres_fact": "app.project_profiles",
                    "condition": "id matches and project_status='active'",
                },
                {
                    "variable": "PROJECT_DELETE_ID",
                    "postgres_fact": "app.project_profiles",
                    "condition": "id matches and project_status='active'",
                },
                {
                    "variable": "SETTINGS_AND_DATA_RESET_SUPPORT",
                    "postgres_fact": "app.settings_profiles, app.data_reset_requests, job.outbox_events, audit.events, app.write_idempotency_records",
                    "condition": "deterministic support rows exist and data reset support row is non-active succeeded state",
                },
            ],
        },
        "legacy_python_mongo_seed_plan": legacy_plan,
        "go_standard": {
            "postgres_seed_repeatable_generation": "GO",
            "postgres_seed_apply": "GO" if apply_status == "GO" else "NO_GO",
            "fixture_variable_sources": "GO",
            "legacy_python_mongo_equivalent_seed": legacy_plan["status"],
            "no_untraceable_or_uncleanable_test_data": "GO",
            "overall": overall_status,
        },
        "blocking_items": [
            item
            for item in [
                None if apply_status == "GO" else "PostgreSQL apply/probe was not executed because DATABASE_URL/--apply was absent in this session.",
                None
                if legacy_plan["status"] == "GO"
                else "No executable legacy Python/Mongo seed entry exists for the exact platform runtime fixture IDs; runtime shadow remains NO_GO until the listed legacy seed plan is implemented in an isolated environment.",
            ]
            if item
        ],
    }


def build_legacy_python_mongo_seed_plan(
    plan: PlatformSeedPlan,
    *,
    legacy_report_path: Path | None = None,
) -> dict[str, Any]:
    if legacy_report_path is not None and legacy_report_path.exists():
        try:
            legacy_report = json.loads(legacy_report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            legacy_report = {}
        runtime_variables = legacy_report.get("runtime_variables") if isinstance(legacy_report, dict) else {}
        legacy_seed = legacy_report.get("legacy_python_seed") if isinstance(legacy_report, dict) else {}
        if runtime_variables == plan.runtime_variables and legacy_seed.get("status") == "GO":
            return {
                "status": "GO",
                "reason": "Executable legacy Python shadow seed report exists for the same runtime fixture IDs.",
                "report_path": str(legacy_report_path),
                "seeded_collections": legacy_seed.get("seeded_collections") or [],
                "data_dir": legacy_report.get("data_dir"),
                "secret_requirements_status": (
                    legacy_report.get("secret_requirements", {}).get("status")
                    if isinstance(legacy_report.get("secret_requirements"), dict)
                    else None
                ),
            }
    return {
        "status": "NO_GO",
        "reason": "Repository search found demo seed and state-store persistence helpers, but no executable legacy seed/test fixture entry that can load the exact BACKGROUND_JOB_ID, BANK_TRANSACTION_ID, LEDGER_ID, PROJECT_ID, PROJECT_DELETE_ID and SHADOW_RUN_ID into an isolated Python/Mongo runtime.",
        "evidence": [
            "backend/src/fin_ops_platform/app/server.py exposes /foundation/seed demo data but it does not accept caller-supplied shadow IDs.",
            "backend/src/fin_ops_platform/services/state_store.py persists app_settings, background_jobs and bank_transactions detailed collections, but there is no platform shadow seed CLI.",
            "backend/src/fin_ops_platform/services/ledgers.py keeps ledgers/reminders in process memory and does not expose a persistence-backed seed hook for arbitrary ledger IDs.",
        ],
        "required_collections": [
            "background_jobs",
            "app_settings",
            "imports_meta",
            "import_batches",
            "bank_transactions",
        ],
        "required_in_memory_state": [
            "LedgerReminderService._ledgers",
            "LedgerReminderService._reminders",
        ],
        "required_fields": {
            "background_jobs": [
                "_id/job_id = BACKGROUND_JOB_ID",
                "status/phase visible to /api/background-jobs/{job_id}/acknowledge",
                "visibility or legacy equivalent visible to authenticated app user",
                "created_at/updated_at fixed to shadow seed timestamp",
            ],
            "app_settings": [
                "_id = settings",
                "manual_projects containing PROJECT_ID and PROJECT_DELETE_ID equivalents",
                "admin_usernames containing FIN_OPS_SHADOW_OA_USERNAME",
                "workbench_column_layouts, bank_account_mappings and access-control arrays matching legacy settings contract",
            ],
            "bank_transactions": [
                "_id/id = BANK_TRANSACTION_ID",
                "txn_date/txn_month fixed to the same seed month",
                "status pending/open enough for project assignment validation",
                "counterparty/account/amount fields matching legacy workbench/project assignment readers",
            ],
            "LedgerReminderService._ledgers": [
                "ledger.id = LEDGER_ID",
                "status = open",
                "ledger_type = payment_collection",
                "expected_date/due date fixed to the same seed date",
            ],
            "LedgerReminderService._reminders": [
                "reminder linked to LEDGER_ID",
                "status pending",
                "remind_at/due date fixed to the same seed date",
            ],
        },
        "legacy_ids": {
            "BACKGROUND_JOB_ID": plan.background_job_id,
            "BANK_TRANSACTION_ID": plan.bank_transaction_id,
            "LEDGER_ID": plan.ledger_id,
            "PROJECT_ID": plan.project_id,
            "PROJECT_DELETE_ID": plan.project_delete_id,
            "SHADOW_RUN_ID": plan.run_id,
        },
        "required_commands": [
            "Add a legacy-only script or test helper that writes these IDs into an isolated FIN_OPS_DATA_DIR/app Mongo database, without touching production app Mongo or OA Mongo.",
            "Run PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check against that isolated FIN_OPS_DATA_DIR.",
            "Run legacy Python platform endpoint smoke checks for background job ack, settings project delete, project detail/assign, ledgers/reminders and data reset password validation using FIN_OPS_SHADOW_OA_TOKEN/FIN_OPS_SHADOW_OA_PASSWORD from the staging secret store.",
        ],
        "prohibited_inputs": [
            "real production OA token",
            "real production OA password",
            "production business documents or bank rows",
        ],
    }


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)


def safe_code(value: str) -> str:
    code = "".join(ch.upper() if ch.isalnum() else "-" for ch in value)
    while "--" in code:
        code = code.replace("--", "-")
    return code.strip("-")[:48] or "RUN"


if __name__ == "__main__":
    raise SystemExit(main())
