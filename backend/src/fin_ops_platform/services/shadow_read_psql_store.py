from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any

from fin_ops_platform.services.cutover_preflight import redact_secret_text
from fin_ops_platform.services.postgres_snapshot_contracts import (
    normalize_app_health_alerts,
    normalize_bank_transaction_categories,
    normalize_no_oa_bank_batches,
    normalize_turnover_relations,
    normalize_workbench_pair_relations,
)


class PsqlShadowReadStore:
    """Small read-only psql-backed store for production one-off shadow reads."""

    storage_backend = "postgres_psql_json"
    storage_mode = "postgres_psql_json"

    def __init__(self, *, database: str = "fin_ops", psql_command: str = "psql") -> None:
        self._database = _validate_database_name(database)
        self._psql_command = tuple(shlex.split(psql_command))
        if not self._psql_command:
            raise ValueError("psql command is required.")

    def load_app_settings(self) -> dict[str, Any]:
        payload = self._load_settings("app_settings")
        if not isinstance(payload, dict):
            payload = {}
        return {**_default_app_settings_payload(), **payload}

    def load_background_jobs(self) -> dict[str, Any]:
        snapshot = self._load_snapshot("background_jobs")
        if snapshot:
            return snapshot
        return self._query_json_object(
            """
            select coalesce(jsonb_object_agg(job_id, coalesce(raw_payload->'normalized_payload', raw_payload) order by created_at, job_id), '{}'::jsonb)
            from job.background_jobs
            """
        )

    def load_pending_invoice_commands(self) -> dict[str, Any]:
        commands = self._query_json_object(
            """
            select coalesce(jsonb_object_agg(command_id, coalesce(command_payload, raw_payload->'normalized_payload', raw_payload) order by created_at, command_id), '{}'::jsonb)
            from app.pending_invoice_manual_invoice_commands
            """
        )
        if commands:
            return commands
        return self._load_snapshot("pending_invoice_commands")

    def load_app_health_alerts(self) -> dict[str, Any]:
        snapshot = self._load_snapshot("app_health_alerts")
        if snapshot:
            return snapshot
        return normalize_app_health_alerts(
            self._query_json_object(
                """
                select coalesce(jsonb_object_agg(alert_id, coalesce(raw_payload->'normalized_payload', raw_payload) order by alert_id), '{}'::jsonb)
                from audit.app_health_alerts
                """
            )
        )

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        pair_relations = self._query_json_object(
            """
            select coalesce(jsonb_object_agg(case_id, coalesce(raw_payload->'normalized_payload', raw_payload) order by case_id), '{}'::jsonb)
            from app.workbench_pair_relations
            """
        )
        if not pair_relations:
            return self._load_snapshot("workbench_pair_relations")
        history = self._query_json_array(
            """
            select coalesce(
                jsonb_agg(
                    coalesce(raw_payload->'normalized_payload', raw_payload)
                    order by (raw_payload->'raw_payload'->>'_stage04_child_index')::integer nulls last, occurred_at, case_id
                ),
                '[]'::jsonb
            )
            from app.workbench_pair_relation_history
            """
        )
        return normalize_workbench_pair_relations(
            pair_relations,
            history,
            snapshot=self._load_snapshot("workbench_pair_relations"),
        )

    def load_no_oa_bank_batches(self) -> dict[str, Any]:
        batches = self._query_json_object(
            """
            select coalesce(jsonb_object_agg(batch_id, coalesce(raw_payload->'normalized_payload', raw_payload) order by batch_id), '{}'::jsonb)
            from app.no_oa_bank_batches
            """
        )
        if not batches:
            return self._load_snapshot("no_oa_bank_batches")
        audit_log = self._query_json_array(
            """
            select coalesce(jsonb_agg(coalesce(raw_payload->'normalized_payload', raw_payload) order by occurred_at, batch_id), '[]'::jsonb)
            from app.no_oa_bank_batch_events
            """
        )
        return normalize_no_oa_bank_batches(
            batches,
            audit_log,
            snapshot=self._load_snapshot("no_oa_bank_batches"),
        )

    def load_bank_transaction_categories(self) -> dict[str, Any]:
        categories = self._query_json_object(
            """
            select coalesce(jsonb_object_agg(key, payload order by key), '{}'::jsonb)
            from (
                select coalesce(legacy_transaction_id, id::text) as key,
                       coalesce(raw_payload->'normalized_payload', raw_payload) as payload
                from app.bank_transaction_categories
            ) rows
            """
        )
        audit_log = self._query_json_array(
            """
            select coalesce(jsonb_agg(coalesce(raw_payload->'normalized_payload', raw_payload) order by occurred_at), '[]'::jsonb)
            from app.bank_transaction_category_events
            """
        )
        return normalize_bank_transaction_categories(
            categories,
            audit_log,
            snapshot=self._load_snapshot("bank_transaction_categories"),
        )

    def load_turnover_relations(self) -> dict[str, Any]:
        relations = self._query_json_array(
            """
            select coalesce(jsonb_agg(
                coalesce(raw_payload->'normalized_payload', raw_payload)
                || jsonb_build_object('relation_id', coalesce(coalesce(raw_payload->'normalized_payload', raw_payload)->>'relation_id', relation_id))
                order by relation_id
            ), '[]'::jsonb)
            from app.turnover_relations
            """
        )
        audit_log = self._query_json_array(
            """
            select coalesce(jsonb_agg(coalesce(raw_payload->'normalized_payload', raw_payload) order by occurred_at, relation_id), '[]'::jsonb)
            from app.turnover_relation_events
            """
        )
        return normalize_turnover_relations(
            relations,
            audit_log,
            snapshot=self._load_snapshot("turnover_relations"),
        )

    def _query_json_object(self, sql: str) -> dict[str, Any]:
        payload = self._query_json(sql)
        return dict(payload) if isinstance(payload, dict) else {}

    def _query_json_array(self, sql: str) -> list[Any]:
        payload = self._query_json(sql)
        return list(payload) if isinstance(payload, list) else []

    def _load_snapshot(self, key: str) -> dict[str, Any]:
        return self._load_settings(f"state:{key}")

    def _load_settings(self, settings_key: str) -> dict[str, Any]:
        settings_key = _validate_settings_key(settings_key)
        payload = self._query_json(
            f"""
            select coalesce(
                (
                    select coalesce(settings_payload, raw_payload->'normalized_payload', raw_payload)
                    from app.app_settings
                    where settings_key = '{settings_key}'
                    limit 1
                ),
                '{{}}'::jsonb
            )
            """
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def _query_json(self, sql: str) -> Any:
        wrapped_sql = (
            "begin transaction read only; "
            "set local statement_timeout = '30s'; "
            f"select ({sql})::jsonb::text; "
            "commit;"
        )
        command = [
            *self._psql_command,
            "-X",
            "-q",
            "-t",
            "-A",
            "-v",
            "ON_ERROR_STOP=1",
            "-d",
            self._database,
            "-c",
            wrapped_sql,
        ]
        try:
            completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        except subprocess.CalledProcessError as exc:
            stderr = redact_secret_text(exc.stderr or str(exc))
            raise RuntimeError(f"psql shadow read query failed: {stderr}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("psql shadow read query timed out.") from exc
        raw_output = completed.stdout.strip()
        if not raw_output:
            return None
        try:
            return json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("psql shadow read query returned invalid JSON.") from exc


def _validate_database_name(database: str) -> str:
    normalized = str(database or "").strip()
    if not normalized:
        raise ValueError("PostgreSQL database name is required.")
    if not all(character.isalnum() or character in {"_", "-"} for character in normalized):
        raise ValueError("PostgreSQL database name contains unsupported characters.")
    return normalized


def _validate_settings_key(settings_key: str) -> str:
    normalized = str(settings_key or "").strip()
    if not normalized:
        raise ValueError("settings key is required.")
    if not all(character.isalnum() or character in {"_", "-", ":"} for character in normalized):
        raise ValueError("settings key contains unsupported characters.")
    return normalized


def _default_app_settings_payload() -> dict[str, Any]:
    return {
        "completed_project_ids": [],
        "manual_projects": [],
        "synced_projects": [],
        "bank_account_mappings": [],
        "allowed_usernames": [],
        "readonly_export_usernames": [],
        "admin_usernames": [],
        "workbench_column_layouts": {},
        "oa_retention": {},
        "oa_import": {},
        "oa_invoice_offset": {},
        "bank_transaction_tags": {},
        "pending_invoice_tag_groups": {},
        "pending_output_invoice_tag_groups": {},
        "input_invoice_usage_payment_status_rules": {},
    }
