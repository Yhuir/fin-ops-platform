from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Any, TypeVar
from uuid import UUID, uuid5


TRANSFORM_NAMESPACE = UUID("3b3a066c-8887-5c18-97c3-405d3d50d6fd")
TRANSFORM_VERSION = "stage04-v1"
T = TypeVar("T")


CORE_SOURCES = {
    "import_batches",
    "import_batches:row_results",
    "file_objects",
    "file_import_files",
    "file_import_sessions",
    "invoices",
    "bank_transactions",
}

WORKBENCH_SOURCES = {
    "matching_runs",
    "matching_results",
    "workbench_pair_relations",
    "workbench_pair_relations_meta",
    "workbench_row_overrides",
    "workbench_exception_cases",
    "workbench_exception_cases_meta",
    "no_oa_bank_batches",
    "no_oa_bank_batches_meta",
    "no_oa_bank_batch_audit_log",
    "bank_transaction_categories",
    "bank_transaction_categories_meta",
    "workbench_matching_dirty_scopes",
}

OPS_TAX_ETC_SOURCES = {
    "app_settings",
    "oa_sync_state",
    "manual_oa_imports",
    "oa_attachment_invoice_cache",
    "background_jobs",
    "app_health_alerts",
    "pending_invoice_manual_invoice_commands",
    "tax_certified_import_sessions",
    "tax_certified_import_batches",
    "tax_certified_import_records",
    "etc_state:etc_invoices",
    "etc_state:etc_import_sessions",
    "etc_state:etc_import_batches",
    "etc_state:etc_submission_batches",
    "etc_state:etc_business_batches",
    "etc_reconciliation_state:etc_reconciliation_tasks",
    "etc_reconciliation_state:etc_reconciliation_files",
    "historical_etc_repair_bundles",
    "historical_etc_repair_parsed_seeds",
    "historical_etc_repair_states",
    "turnover_relations",
    "turnover_relations_meta",
    "turnover_relation_audit_log",
    "turnover_ledger_extras",
}

READ_MODEL_SOURCES = {
    "workbench_read_models",
    "workbench_candidate_matches",
    "cost_statistics_read_models",
    "tax_offset_read_models",
}

ALL_DOMAINS = ("core", "workbench", "ops_tax_etc", "read_models")

TARGET_TABLE_ORDER = [
    ("audit", "events"),
    ("app", "import_batches"),
    ("app", "file_objects"),
    ("app", "import_files"),
    ("app", "invoices"),
    ("app", "bank_transactions"),
    ("app", "import_batch_rows"),
    ("app", "bank_transaction_categories"),
    ("app", "bank_transaction_category_events"),
    ("app", "matching_runs"),
    ("app", "matching_results"),
    ("app", "workbench_pair_relations"),
    ("app", "workbench_pair_relation_history"),
    ("app", "workbench_row_overrides"),
    ("app", "workbench_exception_cases"),
    ("app", "workbench_exception_case_events"),
    ("app", "no_oa_bank_batches"),
    ("app", "no_oa_bank_batch_events"),
    ("job", "workbench_matching_dirty_scopes"),
    ("app", "app_settings"),
    ("app", "pending_invoice_manual_invoice_commands"),
    ("app", "oa_sync_watermarks"),
    ("app", "manual_oa_imports"),
    ("app", "oa_attachment_invoice_cache"),
    ("job", "background_jobs"),
    ("audit", "app_health_alerts"),
    ("app", "tax_certified_import_sessions"),
    ("app", "tax_certified_import_batches"),
    ("app", "tax_certified_import_records"),
    ("app", "etc_import_sessions"),
    ("app", "etc_import_batches"),
    ("app", "etc_invoices"),
    ("app", "etc_submission_batches"),
    ("app", "etc_business_batches"),
    ("app", "etc_reconciliation_tasks"),
    ("app", "etc_reconciliation_files"),
    ("app", "historical_etc_repair_bundles"),
    ("app", "historical_etc_repair_parsed_seeds"),
    ("app", "historical_etc_repair_states"),
    ("app", "turnover_relations"),
    ("app", "turnover_relation_events"),
    ("app", "turnover_ledger_extras"),
    ("read_model", "workbench_snapshots"),
    ("read_model", "workbench_candidate_matches"),
    ("read_model", "cost_statistics_read_models"),
    ("read_model", "tax_offset_read_models"),
    ("read_model", "search_index_rows"),
]

TARGET_TABLES = tuple(TARGET_TABLE_ORDER)
TABLE_ORDER_INDEX = {table: index for index, table in enumerate(TARGET_TABLE_ORDER)}
FK_COLUMN_TARGETS = {
    ("app", "import_batch_rows", "import_batch_id"): ("app", "import_batches"),
    ("app", "import_files", "import_batch_id"): ("app", "import_batches"),
    ("app", "matching_results", "run_id"): ("app", "matching_runs"),
    ("app", "bank_transaction_categories", "bank_transaction_id"): ("app", "bank_transactions"),
    ("app", "tax_certified_import_batches", "session_id"): ("app", "tax_certified_import_sessions"),
    ("app", "tax_certified_import_records", "batch_id"): ("app", "tax_certified_import_batches"),
}
TARGET_CONFLICT_COLUMNS = {
    ("app", "app_settings"): ("settings_key",),
    ("app", "matching_runs"): ("run_id",),
    ("app", "workbench_pair_relations"): ("case_id",),
    ("app", "workbench_row_overrides"): ("row_id", "row_type"),
    ("app", "workbench_exception_cases"): ("case_id",),
    ("app", "no_oa_bank_batches"): ("batch_id",),
    ("job", "workbench_matching_dirty_scopes"): ("scope_month",),
    ("app", "pending_invoice_manual_invoice_commands"): ("command_id",),
}
REPLACE_EVENT_TARGETS = {
    ("app", "workbench_pair_relation_history"): "case_id",
    ("app", "workbench_exception_case_events"): "case_id",
    ("app", "no_oa_bank_batch_events"): "batch_id",
    ("app", "turnover_relation_events"): "relation_id",
}
FULL_REPLACE_EVENT_TABLES = {
    ("app", "bank_transaction_category_events"),
    ("app", "no_oa_bank_batch_events"),
    ("app", "turnover_relation_events"),
    ("app", "workbench_exception_case_events"),
    ("app", "workbench_pair_relation_history"),
}


class TransformError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class JsonValue:
    value: Any


@dataclass(frozen=True, slots=True)
class TextArray:
    value: list[str]


@dataclass(frozen=True, slots=True)
class StagingRecord:
    export_id: str
    source_collection: str
    legacy_mongo_id: str
    record_type: str | None
    normalized_payload: dict[str, Any]
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TargetRow:
    domain: str
    source_collection: str
    legacy_mongo_id: str
    target_schema: str
    target_table: str
    target_id: str
    columns: dict[str, Any]
    raw_payload: dict[str, Any]

    @property
    def table_key(self) -> tuple[str, str]:
        return (self.target_schema, self.target_table)


@dataclass(slots=True)
class TransformPlan:
    export_id: str
    source_database: str
    manifest_sha256: str | None
    manifest_total_records: int
    staging_raw_count: int
    rows: list[TargetRow]
    source_counts: dict[str, int]
    target_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def table_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.rows:
            key = f"{row.target_schema}.{row.target_table}"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    def mapping_count(self) -> int:
        return len({(row.source_collection, row.legacy_mongo_id, row.target_schema, row.target_table) for row in self.rows})

    def to_dict(self, *, dry_run: bool) -> dict[str, Any]:
        return {
            "status": "blocked" if self.blockers else "planned",
            "dry_run": dry_run,
            "export_id": self.export_id,
            "source_database": self.source_database,
            "manifest_sha256": self.manifest_sha256,
            "manifest_total_records": self.manifest_total_records,
            "staging_raw_count": self.staging_raw_count,
            "source_counts": self.source_counts,
            "planned_target_counts": self.table_counts(),
            "existing_target_counts": self.target_counts,
            "id_mappings": {"planned": self.mapping_count()},
            "warnings": self.warnings,
            "blockers": self.blockers,
            "transform_version": TRANSFORM_VERSION,
        }


def stable_target_id(source_collection: str, legacy_mongo_id: str, target_schema: str, target_table: str) -> str:
    if not source_collection or not legacy_mongo_id or not target_schema or not target_table:
        raise TransformError("stable target id requires source_collection, legacy_mongo_id, target_schema, and target_table")
    key = f"{source_collection}:{legacy_mongo_id}:{target_schema}.{target_table}"
    return str(uuid5(TRANSFORM_NAMESPACE, key))


def domain_for_source(source_collection: str) -> str | None:
    if source_collection in CORE_SOURCES:
        return "core"
    if source_collection in WORKBENCH_SOURCES:
        return "workbench"
    if source_collection in OPS_TAX_ETC_SOURCES:
        return "ops_tax_etc"
    if source_collection in READ_MODEL_SOURCES:
        return "read_models"
    if source_collection == "gridfs_files_manifest":
        return None
    return None


def build_transform_plan(
    *,
    export_row: dict[str, Any],
    records: list[StagingRecord],
    target_counts: dict[str, int] | None = None,
    only_domains: set[str] | None = None,
    skip_domains: set[str] | None = None,
) -> TransformPlan:
    manifest = export_row.get("manifest") or {}
    export_id = str(export_row["export_id"])
    source_database = str(export_row.get("source_database") or "")
    rows: list[TargetRow] = []
    warnings: list[str] = []
    source_counts: dict[str, int] = {}
    for record in records:
        source_counts[record.source_collection] = source_counts.get(record.source_collection, 0) + 1
        domain = domain_for_source(record.source_collection)
        if domain is None:
            if record.source_collection != "gridfs_files_manifest":
                warnings.append(f"unmapped_source_collection:{record.source_collection}")
            continue
        if only_domains and domain not in only_domains:
            continue
        if skip_domains and domain in skip_domains:
            continue
        rows.extend(build_rows_for_record(record, domain, warnings))

    rows.extend(build_generated_read_model_rows(records, only_domains=only_domains, skip_domains=skip_domains, warnings=warnings))
    sanitize_optional_foreign_keys(rows, warnings)
    sanitize_optional_unique_values(rows, warnings)
    rows.sort(key=lambda row: (TABLE_ORDER_INDEX.get(row.table_key, 10_000), row.target_id))
    total_records = int(manifest.get("total_records") or 0)
    plan = TransformPlan(
        export_id=export_id,
        source_database=source_database,
        manifest_sha256=manifest.get("manifest_sha256"),
        manifest_total_records=total_records,
        staging_raw_count=len(records),
        rows=rows,
        source_counts=dict(sorted(source_counts.items())),
        target_counts=target_counts or {},
        warnings=sorted(set(warnings)),
    )
    if export_row.get("status") != "imported":
        plan.blockers.append("staging_export_status_not_imported")
    if total_records and total_records != len(records):
        plan.blockers.append(f"staging_count_mismatch:manifest={total_records}:actual={len(records)}")
    return plan


def sanitize_optional_foreign_keys(rows: list[TargetRow], warnings: list[str]) -> None:
    known_ids = {(item.target_schema, item.target_table, item.target_id) for item in rows}
    for item in rows:
        for (schema, table, column), target in FK_COLUMN_TARGETS.items():
            if (item.target_schema, item.target_table) != (schema, table):
                continue
            value = item.columns.get(column)
            if value is None:
                continue
            if (target[0], target[1], str(value)) not in known_ids:
                warnings.append(f"missing_optional_fk:{schema}.{table}.{column}:{item.source_collection}:{item.legacy_mongo_id}")
                item.columns[column] = None


def sanitize_optional_unique_values(rows: list[TargetRow], warnings: list[str]) -> None:
    optional_unique_columns = {
        ("app", "invoices", "source_unique_key"),
        ("app", "invoices", "data_fingerprint"),
        ("app", "bank_transactions", "source_unique_key"),
        ("app", "bank_transactions", "data_fingerprint"),
    }
    for schema, table, column in optional_unique_columns:
        value_rows: dict[str, list[TargetRow]] = {}
        for item in rows:
            if (item.target_schema, item.target_table) != (schema, table):
                continue
            value = item.columns.get(column)
            if value in (None, ""):
                continue
            value_rows.setdefault(str(value), []).append(item)
        for value, duplicates in value_rows.items():
            if len(duplicates) < 2:
                continue
            for item in duplicates:
                item.columns[column] = None
            warnings.append(f"duplicate_optional_unique:{schema}.{table}.{column}:{len(duplicates)}:{value}")


def build_rows_for_record(record: StagingRecord, domain: str, warnings: list[str]) -> list[TargetRow]:
    p = record.normalized_payload or {}
    if record.source_collection == "import_batches":
        return [
            row(
                domain,
                record,
                "app",
                "import_batches",
                {
                    "legacy_mongo_id": record.legacy_mongo_id,
                    "batch_type": text(first(p, "batch_type", "type", default="unknown")),
                    "source_name": text(first(p, "source_name", "source", "template_name", default="unknown")),
                    "imported_by": text(first(p, "imported_by", "created_by", "operator", default="unknown")),
                    "row_count": integer(first(p, "row_count", default=len(p.get("row_results") or []))),
                    "success_count": integer(first(p, "success_count", default=0)),
                    "error_count": integer(first(p, "error_count", default=0)),
                    "duplicate_count": integer(first(p, "duplicate_count", default=0)),
                    "suspected_duplicate_count": integer(first(p, "suspected_duplicate_count", default=0)),
                    "updated_count": integer(first(p, "updated_count", default=0)),
                    "status": text(first(p, "status", default="completed")),
                    "imported_at": timestamp(first(p, "imported_at", "created_at", "updated_at")),
                    "raw_payload": JsonValue(full_raw(record)),
                },
            )
        ]
    if record.source_collection == "import_batches:row_results":
        result = dict_value(p.get("row_result"))
        normalized = dict_value(p.get("normalized_row"))
        legacy_batch_id = text(first(p, "batch_id", "legacy_batch_id"))
        batch_uuid = stable_target_id("import_batches", legacy_batch_id, "app", "import_batches") if legacy_batch_id else None
        return [
            row(
                domain,
                record,
                "app",
                "import_batch_rows",
                {
                    "legacy_mongo_id": record.legacy_mongo_id,
                    "import_batch_id": batch_uuid,
                    "legacy_batch_id": legacy_batch_id,
                    "row_no": integer(first(p, "row_no", default=1)),
                    "source_record_type": text(first(result, "source_record_type", "record_type", default="unknown")),
                    "source_unique_key": text(first(result, "source_unique_key", default=first(normalized, "source_unique_key"))),
                    "data_fingerprint": text(first(result, "data_fingerprint", default=first(normalized, "data_fingerprint"))),
                    "decision": text(first(result, "decision", default="unknown")),
                    "decision_reason": text(first(result, "decision_reason", "reason")),
                    "linked_object_type": text(first(result, "linked_object_type", "object_type")),
                    "linked_object_id": text(first(result, "linked_object_id", "object_id")),
                    "identity_kind": text(first(result, "identity_kind", default=first(normalized, "identity_kind"))),
                    "account_no": text(first(result, "account_no", default=first(normalized, "account_no"))),
                    "trade_time": timestamp(first(result, "trade_time", default=first(normalized, "trade_time"))),
                    "direction": text(first(result, "direction", "txn_direction", default=first(normalized, "direction", "txn_direction"))),
                    "amount": decimal_value(first(result, "amount", default=first(normalized, "amount"))),
                    "counterparty_name": text(first(result, "counterparty_name", default=first(normalized, "counterparty_name_raw", "counterparty_name"))),
                    "raw_payload": JsonValue(full_raw(record)),
                },
            )
        ]
    if record.source_collection == "file_objects":
        legacy_gridfs_id = text(first(p, "legacy_gridfs_id", default=record.legacy_mongo_id))
        bucket = text(first(p, "bucket_name", default="import_file_blobs"))
        return [
            row(
                domain,
                record,
                "app",
                "file_objects",
                {
                    "legacy_mongo_id": record.legacy_mongo_id,
                    "legacy_gridfs_id": legacy_gridfs_id,
                    "storage_backend": text(first(p, "storage_backend", default="gridfs")),
                    "storage_uri": f"gridfs://{bucket}/{legacy_gridfs_id}",
                    "bucket_name": bucket,
                    "object_key": legacy_gridfs_id,
                    "filename": text(first(p, "filename")),
                    "size_bytes": integer(first(p, "length", "size_bytes")),
                    "content_type": text(first(p, "content_type")),
                    "uploaded_at": timestamp(first(p, "upload_date", "uploaded_at")),
                    "file_metadata": JsonValue(first(p, "metadata", default={})),
                    "raw_payload": JsonValue(full_raw(record)),
                },
            )
        ]
    if record.source_collection == "file_import_files":
        batch_id = text(first(p, "batch_id", "preview_batch_id"))
        return [
            row(
                domain,
                record,
                "app",
                "import_files",
                {
                    "legacy_mongo_id": record.legacy_mongo_id,
                    "import_batch_id": stable_target_id("import_batches", batch_id, "app", "import_batches") if batch_id else None,
                    "session_id": text(first(p, "session_id")),
                    "stored_file_path": text(first(p, "stored_file_path", "file_path")),
                    "original_filename": text(first(p, "original_filename", "file_name", "filename")),
                    "template_kind": text(first(p, "template_kind", "template_code")),
                    "status": text(first(p, "status", default="stored")),
                    "uploaded_by": text(first(p, "uploaded_by", "imported_by")),
                    "uploaded_at": timestamp(first(p, "uploaded_at", "created_at", "updated_at")),
                    "raw_payload": JsonValue(full_raw(record)),
                },
            )
        ]
    if record.source_collection == "file_import_sessions":
        return [
            row(
                domain,
                record,
                "audit",
                "events",
                {
                    "event_type": "migration.file_import_session",
                    "object_type": "file_import_session",
                    "object_id": text(first(p, "session_id", "id", default=record.legacy_mongo_id)),
                    "actor_id": text(first(p, "imported_by", "created_by")),
                    "occurred_at": timestamp(first(p, "created_at", "updated_at")),
                    "payload": JsonValue(p),
                    "raw_payload": JsonValue(full_raw(record)),
                },
            )
        ]
    if record.source_collection == "invoices":
        invoice_date = date_value(first(p, "invoice_date", "date"))
        return [
            row(
                domain,
                record,
                "app",
                "invoices",
                {
                    "legacy_mongo_id": record.legacy_mongo_id,
                    "invoice_type": text(first(p, "invoice_type", default="input")),
                    "invoice_no": text(first(p, "invoice_no", "digital_invoice_no", default=record.legacy_mongo_id)),
                    "invoice_code": text(first(p, "invoice_code")),
                    "digital_invoice_no": text(first(p, "digital_invoice_no")),
                    "source_unique_key": text(first(p, "source_unique_key")),
                    "data_fingerprint": text(first(p, "data_fingerprint")),
                    "invoice_date": invoice_date,
                    "invoice_month": month_start(first(p, "invoice_month", default=invoice_date)),
                    "counterparty_id": text(first(p, "counterparty_id")),
                    "counterparty_name": text(first(p, "counterparty_name")),
                    "seller_name": text(first(p, "seller_name")),
                    "seller_tax_no": text(first(p, "seller_tax_no")),
                    "buyer_name": text(first(p, "buyer_name")),
                    "buyer_tax_no": text(first(p, "buyer_tax_no")),
                    "amount": decimal_value(first(p, "amount", default=0)),
                    "signed_amount": decimal_value(first(p, "signed_amount", default=first(p, "amount", default=0))),
                    "written_off_amount": decimal_value(first(p, "written_off_amount", default=0)),
                    "tax_rate": text(first(p, "tax_rate")),
                    "tax_amount": decimal_value(first(p, "tax_amount")),
                    "total_with_tax": decimal_value(first(p, "total_with_tax")),
                    "currency": text(first(p, "currency", default="CNY")),
                    "legacy_source_batch_id": text(first(p, "source_batch_id", "batch_id")),
                    "oa_form_id": text(first(p, "oa_form_id")),
                    "etc_invoice_id": text(first(p, "etc_invoice_id")),
                    "workbench_visibility": text(first(p, "workbench_visibility", default="visible")),
                    "status": text(first(p, "status", default="pending")),
                    "tags": TextArray(text_list(first(p, "tags", default=[]))),
                    "source_links": JsonValue(first(p, "source_links", default=[])),
                    "raw_payload": JsonValue(full_raw(record)),
                },
            )
        ]
    if record.source_collection == "bank_transactions":
        txn_date = date_value(first(p, "txn_date", "date"))
        direction = text(first(p, "txn_direction", "direction", default="inflow"))
        amount = decimal_value(first(p, "amount", default=0))
        signed_default = f"-{amount}" if direction == "outflow" and amount is not None else amount
        return [
            row(
                domain,
                record,
                "app",
                "bank_transactions",
                {
                    "legacy_mongo_id": record.legacy_mongo_id,
                    "account_no": text(first(p, "account_no", default="unknown")),
                    "account_name": text(first(p, "account_name")),
                    "txn_direction": direction,
                    "counterparty_name_raw": text(first(p, "counterparty_name_raw", "counterparty_name", default="unknown")),
                    "normalized_counterparty_name": text(first(p, "normalized_counterparty_name")),
                    "amount": amount,
                    "signed_amount": decimal_value(first(p, "signed_amount", default=signed_default)),
                    "written_off_amount": decimal_value(first(p, "written_off_amount", default=0)),
                    "txn_date": txn_date,
                    "txn_month": month_start(first(p, "txn_month", default=txn_date)),
                    "trade_time": timestamp(first(p, "trade_time")),
                    "pay_receive_time": timestamp(first(p, "pay_receive_time")),
                    "bank_serial_no": text(first(p, "bank_serial_no")),
                    "source_unique_key": text(first(p, "source_unique_key")),
                    "data_fingerprint": text(first(p, "data_fingerprint")),
                    "legacy_source_batch_id": text(first(p, "source_batch_id", "batch_id")),
                    "counterparty_id": text(first(p, "counterparty_id")),
                    "project_id": text(first(p, "project_id")),
                    "balance": decimal_value(first(p, "balance")),
                    "currency": text(first(p, "currency", default="CNY")),
                    "summary": text(first(p, "summary")),
                    "remark": text(first(p, "remark")),
                    "bank_text_fields": JsonValue(first(p, "bank_text_fields", default=[])),
                    "status": text(first(p, "status", default="pending")),
                    "raw_payload": JsonValue(full_raw(record)),
                },
            )
        ]
    return build_generic_rows(record, domain, warnings)


def build_generic_rows(record: StagingRecord, domain: str, warnings: list[str]) -> list[TargetRow]:
    p = record.normalized_payload or {}
    sc = record.source_collection
    if sc == "matching_runs":
        return [generic_row(domain, record, "app", "matching_runs", {"run_id": one(p, record.legacy_mongo_id, "run_id", "id"), "triggered_by": text(first(p, "triggered_by")), "invoice_count": integer(first(p, "invoice_count", default=0)), "transaction_count": integer(first(p, "transaction_count", default=0)), "result_count": integer(first(p, "result_count", default=0)), "executed_at": timestamp(first(p, "executed_at", "created_at")), "status": text(first(p, "status", default="completed"))})]
    if sc == "matching_results":
        run_id = text(first(p, "run_id"))
        return [generic_row(domain, record, "app", "matching_results", {"run_id": stable_target_id("matching_runs", run_id, "app", "matching_runs") if run_id else None, "legacy_run_id": run_id, "result_type": text(first(p, "result_type", default="unknown")), "confidence": text(first(p, "confidence", default="unknown")), "rule_code": text(first(p, "rule_code")), "invoice_ids": TextArray(text_list(first(p, "invoice_ids", default=[]))), "transaction_ids": TextArray(text_list(first(p, "transaction_ids", default=[]))), "amount": decimal_value(first(p, "amount", default=0)), "difference_amount": decimal_value(first(p, "difference_amount", default=0)), "counterparty_name": text(first(p, "counterparty_name")), "explanation": text(first(p, "explanation"))})]
    if sc == "workbench_pair_relations":
        return [generic_row(domain, record, "app", "workbench_pair_relations", {"case_id": one(p, record.legacy_mongo_id, "case_id", "id"), "relation_mode": text(first(p, "relation_mode", default="unknown")), "status": text(first(p, "status", default="active")), "version": integer(first(p, "version", default=1)), "month_scope": month_start(first(p, "month_scope", "scope_month")), "row_ids": TextArray(text_list(first(p, "row_ids", default=[]))), "row_types": TextArray(text_list(first(p, "row_types", default=[]))), "note": text(first(p, "note")), "amount_check": JsonValue(first(p, "amount_check", default={})), "special_metadata": JsonValue(first(p, "special_metadata", default={})), "source_versions": JsonValue(first(p, "source_versions", default={})), "created_by": text(first(p, "created_by")), "created_at": timestamp(first(p, "created_at")), "updated_at": timestamp(first(p, "updated_at")), "withdrawn_by": text(first(p, "withdrawn_by")), "withdrawn_at": timestamp(first(p, "withdrawn_at"))})]
    if sc == "workbench_pair_relations_meta":
        return pair_relation_history_rows(domain, record)
    if sc == "workbench_row_overrides":
        return [generic_row(domain, record, "app", "workbench_row_overrides", {"row_id": one(p, record.legacy_mongo_id, "row_id", "id"), "row_type": text(first(p, "row_type", default="unknown")), "scope_month": month_start(first(p, "scope_month")), "status": text(first(p, "status", default="active")), "projection_version": integer(first(p, "projection_version")) or 1, "override_payload": JsonValue(first(p, "override_payload", default=p)), "source_versions": JsonValue(first(p, "source_versions", default={})), "changed_row_ids": TextArray(text_list(first(p, "changed_row_ids", default=[]))), "updated_by": text(first(p, "updated_by")), "updated_at": timestamp(first(p, "updated_at"))})]
    if sc == "workbench_exception_cases":
        return [generic_row(domain, record, "app", "workbench_exception_cases", {"case_id": one(p, record.legacy_mongo_id, "case_id", "id"), "status": text(first(p, "status", default="active")), "version": integer(first(p, "version", default=1)), "business_line": text(first(p, "business_line")), "scenario": text(first(p, "scenario")), "resolution": text(first(p, "resolution")), "scope_month": month_start(first(p, "scope_month")), "row_ids": TextArray(text_list(first(p, "row_ids", default=[]))), "candidate_ids": TextArray(text_list(first(p, "candidate_ids", default=[]))), "source_versions": JsonValue(first(p, "source_versions", default={})), "history_payload": JsonValue(first(p, "history", "history_payload", default=[])), "created_by": text(first(p, "created_by")), "created_at": timestamp(first(p, "created_at")), "updated_by": text(first(p, "updated_by")), "updated_at": timestamp(first(p, "updated_at"))})]
    if sc == "workbench_exception_cases_meta":
        return [generic_event(domain, record, "app", "workbench_exception_case_events", "case_id", "exception_snapshot")]
    if sc == "no_oa_bank_batches":
        return [generic_row(domain, record, "app", "no_oa_bank_batches", {"batch_id": one(p, record.legacy_mongo_id, "batch_id", "id"), "status": text(first(p, "status", default="active")), "status_bucket": text(first(p, "status_bucket")), "version": integer(first(p, "version", default=1)), "scope_month": month_start(first(p, "scope_month")), "account_key": text(first(p, "account_key")), "total_amount": decimal_value(first(p, "total_amount", default=0)), "bank_transaction_ids": TextArray(text_list(first(p, "bank_transaction_ids", "row_ids", default=[]))), "submitted_by": text(first(p, "submitted_by")), "submitted_at": timestamp(first(p, "submitted_at")), "withdrawn_by": text(first(p, "withdrawn_by")), "withdrawn_at": timestamp(first(p, "withdrawn_at")), "source_versions": JsonValue(first(p, "source_versions", default={}))})]
    if sc == "no_oa_bank_batch_audit_log":
        return [generic_event(domain, record, "app", "no_oa_bank_batch_events", "batch_id", text(first(p, "operation", "event_type", default="audit")))]
    if sc == "no_oa_bank_batches_meta":
        return [settings_snapshot_row(domain, record, "state:no_oa_bank_batches")]
    if sc == "bank_transaction_categories":
        txn = text(first(p, "bank_transaction_id", "transaction_id"))
        return [generic_row(domain, record, "app", "bank_transaction_categories", {"bank_transaction_id": stable_target_id("bank_transactions", txn, "app", "bank_transactions") if txn else None, "legacy_transaction_id": txn, "category": text(first(p, "category", "category_code", default="unknown")), "source": text(first(p, "source", default="migration")), "confidence": decimal_value(first(p, "confidence")), "status": text(first(p, "status", default="active")), "version": integer(first(p, "version", default=1)), "updated_by": text(first(p, "updated_by")), "updated_at": timestamp(first(p, "updated_at"))})]
    if sc == "bank_transaction_categories_meta":
        return [
            *category_audit_event_rows(domain, record),
            settings_snapshot_row(domain, record, "state:bank_transaction_categories"),
        ]
    if sc == "workbench_matching_dirty_scopes":
        return [generic_row(domain, record, "job", "workbench_matching_dirty_scopes", {"scope_month": month_start(first(p, "scope_month", "month", default=record.legacy_mongo_id)), "reason": text(first(p, "reason")), "status": text(first(p, "status", default="dirty")), "attempt_count": integer(first(p, "attempt_count", default=0)), "last_error": text(first(p, "last_error")), "available_at": timestamp(first(p, "available_at")), "source_versions": JsonValue(first(p, "source_versions", default={}))})]
    if sc == "app_settings":
        return [generic_row(domain, record, "app", "app_settings", {"settings_key": text(first(p, "settings_key", "key", default="app_settings")), "version": integer(first(p, "version", default=1)), "settings_payload": JsonValue(p), "updated_by": text(first(p, "updated_by")), "updated_at": timestamp(first(p, "updated_at"))})]
    if sc == "pending_invoice_manual_invoice_commands":
        return [
            generic_row(
                domain,
                record,
                "app",
                "pending_invoice_manual_invoice_commands",
                {
                    "legacy_mongo_id": record.legacy_mongo_id,
                    "command_id": one(p, record.legacy_mongo_id, "request_id", "command_id", "id"),
                    "request_id": text(first(p, "request_id", "command_id", default=record.legacy_mongo_id)),
                    "request_key": text(first(p, "request_key")),
                    "status": text(first(p, "status", default="unknown")),
                    "invoice_id": text(first(p, "invoice_id")),
                    "relation_case_id": text(first(p, "relation_case_id", "case_id")),
                    "actor_id": text(first(p, "actor_id", "actor")),
                    "error_code": text(first(p, "error_code")),
                    "error_message": text(first(p, "error", "error_message", "last_error")),
                    "last_successful_status": text(first(p, "last_successful_status")),
                    "attempt_count": integer(first(p, "attempt_count", default=0)),
                    "status_history": TextArray(text_list(first(p, "status_history", default=[]))),
                    "result_payload": JsonValue(first(p, "result", default={})),
                    "command_payload": JsonValue(p),
                    "created_at": timestamp(first(p, "created_at")),
                    "updated_at": timestamp(first(p, "updated_at")),
                },
            )
        ]
    if sc == "oa_sync_state":
        return [generic_row(domain, record, "app", "oa_sync_watermarks", {"sync_key": text(first(p, "sync_key", "key", default=record.legacy_mongo_id)), "form_id": text(first(p, "form_id")), "source_updated_after": timestamp(first(p, "source_updated_after")), "last_success_at": timestamp(first(p, "last_success_at", "updated_at")), "status": text(first(p, "status", default="idle")), "version": integer(first(p, "version", default=1)), "payload": JsonValue(p), "updated_at": timestamp(first(p, "updated_at"))})]
    if sc == "manual_oa_imports":
        return child_rows(record, domain, "app", "manual_oa_imports", p, "entries", lambda child, legacy: {"legacy_mongo_id": legacy, "row_id": one(child, legacy, "row_id", "id"), "source": text(first(child, "source", default="manual")), "actor_id": text(first(child, "actor_id", "imported_by")), "imported_at": timestamp(first(child, "imported_at", "created_at")), "status": text(first(child, "status", default="active")), "audit_payload": JsonValue(first(child, "audit_payload", default={}))})
    if sc == "oa_attachment_invoice_cache":
        return [generic_row(domain, record, "app", "oa_attachment_invoice_cache", {"source_attachment_key": one(p, record.legacy_mongo_id, "source_attachment_key", "cache_key", "id"), "parser_version": text(first(p, "parser_version", default="unknown")), "cache_schema_version": text(first(p, "cache_schema_version", default="unknown")), "source_size_bytes": integer(first(p, "source_size_bytes", "size_bytes")), "source_modified_at": timestamp(first(p, "source_modified_at")), "parsed_at": timestamp(first(p, "parsed_at", "updated_at")), "evidences": JsonValue(first(p, "evidences", default=[])), "invoices": JsonValue(first(p, "invoices", default=[])), "artifacts": JsonValue(first(p, "artifacts", default={})), "normalized_payload": JsonValue(p)})]
    if sc == "background_jobs":
        return [generic_row(domain, record, "job", "background_jobs", {"job_id": one(p, record.legacy_mongo_id, "job_id", "id"), "job_type": text(first(p, "job_type", "type", default="unknown")), "status": text(first(p, "status", default="unknown")), "owner_id": text(first(p, "owner_id")), "visibility": text(first(p, "visibility")), "source": text(first(p, "source")), "affected_months": TextArray(text_list(first(p, "affected_months", "months", default=[]))), "progress": JsonValue(first(p, "progress", default={})), "result_summary": JsonValue(first(p, "result_summary", default={})), "error": text(first(p, "error", "last_error")), "retry_mode": text(first(p, "retry_mode")), "attention": JsonValue(first(p, "attention", default={})), "superseded_by_job_id": text(first(p, "superseded_by_job_id")), "created_at": timestamp(first(p, "created_at")), "updated_at": timestamp(first(p, "updated_at"))})]
    if sc == "app_health_alerts":
        return child_rows(record, domain, "audit", "app_health_alerts", p, "alerts", lambda child, legacy: {"legacy_mongo_id": legacy, "alert_id": one(child, legacy, "alert_id", "id"), "kind": text(first(child, "kind", default="snapshot")), "scope": text(first(child, "scope")), "severity": text(first(child, "severity", default="unknown")), "status": text(first(child, "status", default="active")), "active_at": timestamp(first(child, "active_at", "created_at")), "recovered_at": timestamp(first(child, "recovered_at")), "acknowledged_by": text(first(child, "acknowledged_by")), "acknowledged_at": timestamp(first(child, "acknowledged_at")), "payload": JsonValue(child)})
    if sc == "tax_certified_import_sessions":
        return [generic_row(domain, record, "app", "tax_certified_import_sessions", {"session_id": one(p, record.legacy_mongo_id, "session_id", "id"), "status": text(first(p, "status", default="unknown")), "scope_month": month_start(first(p, "scope_month", "month")), "imported_by": text(first(p, "imported_by")), "imported_at": timestamp(first(p, "imported_at", "created_at")), "record_count": integer(first(p, "record_count", default=0))})]
    if sc == "tax_certified_import_batches":
        session = text(first(p, "session_id"))
        return [generic_row(domain, record, "app", "tax_certified_import_batches", {"batch_id": one(p, record.legacy_mongo_id, "batch_id", "id"), "session_id": stable_target_id("tax_certified_import_sessions", session, "app", "tax_certified_import_sessions") if session else None, "status": text(first(p, "status", default="unknown")), "scope_month": month_start(first(p, "scope_month", "month")), "row_count": integer(first(p, "row_count", default=0))})]
    if sc == "tax_certified_import_records":
        batch = text(first(p, "batch_id"))
        return [generic_row(domain, record, "app", "tax_certified_import_records", {"batch_id": stable_target_id("tax_certified_import_batches", batch, "app", "tax_certified_import_batches") if batch else None, "certified_unique_key": one(p, record.legacy_mongo_id, "certified_unique_key", "unique_key", "id"), "invoice_no": text(first(p, "invoice_no")), "invoice_code": text(first(p, "invoice_code")), "digital_invoice_no": text(first(p, "digital_invoice_no")), "seller_name": text(first(p, "seller_name")), "seller_tax_no": text(first(p, "seller_tax_no")), "invoice_date": date_value(first(p, "invoice_date")), "scope_month": month_start(first(p, "scope_month", "month")), "amount": decimal_value(first(p, "amount")), "tax_amount": decimal_value(first(p, "tax_amount", default=0)), "matched_plan_id": text(first(p, "matched_plan_id")), "status": text(first(p, "status", default="unknown"))})]
    if sc.startswith("etc_state:"):
        return build_etc_state_rows(record, domain, p)
    if sc.startswith("etc_reconciliation_state:"):
        return build_etc_reconciliation_rows(record, domain, p)
    if sc == "historical_etc_repair_bundles":
        return [generic_row(domain, record, "app", "historical_etc_repair_bundles", {"bundle_id": one(p, record.legacy_mongo_id, "bundle_id", "id"), "status": text(first(p, "status", default="unknown")), "metadata": JsonValue(first(p, "metadata", default={}))})]
    if sc == "historical_etc_repair_parsed_seeds":
        return [generic_row(domain, record, "app", "historical_etc_repair_parsed_seeds", {"seed_id": one(p, record.legacy_mongo_id, "seed_id", "id", "bundle_id"), "bundle_id": text(first(p, "bundle_id")), "status": text(first(p, "status", default="unknown")), "parsed_payload": JsonValue(first(p, "parsed_payload", default=p))})]
    if sc == "historical_etc_repair_states":
        return [generic_row(domain, record, "app", "historical_etc_repair_states", {"state_id": one(p, record.legacy_mongo_id, "state_id", "id", "bundle_id"), "status": text(first(p, "status", default="unknown")), "version": integer(first(p, "version", default=1)), "state_payload": JsonValue(first(p, "state_payload", default=p))})]
    if sc == "turnover_relations":
        return [generic_row(domain, record, "app", "turnover_relations", {"relation_id": one(p, record.legacy_mongo_id, "relation_id", "id"), "bank_transaction_id": text(first(p, "bank_transaction_id")), "status": text(first(p, "status", default="unknown")), "relation_type": text(first(p, "relation_type", "business_type")), "scope_month": month_start(first(p, "scope_month", "month")), "counterparty_name": text(first(p, "counterparty_name")), "amount": decimal_value(first(p, "amount", "principal_amount")), "version": integer(first(p, "version", default=1)), "audit_payload": JsonValue(first(p, "audit_payload", "audit", default={})), "source_versions": JsonValue(first(p, "source_versions", default={}))})]
    if sc == "turnover_relations_meta":
        return [settings_snapshot_row(domain, record, "state:turnover_relations")]
    if sc == "turnover_relation_audit_log":
        return [generic_event(domain, record, "app", "turnover_relation_events", "relation_id", text(first(p, "action", "event_type", default="audit")))]
    if sc == "turnover_ledger_extras":
        return [generic_row(domain, record, "app", "turnover_ledger_extras", {"ledger_key": one(p, record.legacy_mongo_id, "ledger_key", "relation_id", "bank_transaction_id", "id"), "scope_month": month_start(first(p, "scope_month", "month")), "extra_payload": JsonValue(first(p, "extra_payload", default=p)), "updated_by": text(first(p, "updated_by")), "updated_at": timestamp(first(p, "updated_at"))})]
    if sc == "workbench_read_models":
        return [generic_row(domain, record, "read_model", "workbench_snapshots", {"scope_key": one(p, record.legacy_mongo_id, "scope_key", "id"), "scope_month": month_start(first(p, "scope_month", "month")), "source_versions": JsonValue(first(p, "source_versions", default={})), "generated_at": timestamp(first(p, "generated_at", "updated_at")), "cache_status": text(first(p, "cache_status", default="fresh")), "row_count": integer(first(p, "row_count", default=0)), "payload": JsonValue(p)})]
    if sc == "workbench_candidate_matches":
        return [generic_row(domain, record, "read_model", "workbench_candidate_matches", {"candidate_key": one(p, record.legacy_mongo_id, "candidate_key", "id"), "scope_month": month_start(first(p, "scope_month", "month")), "status": text(first(p, "status", default="active")), "row_ids": TextArray(text_list(first(p, "row_ids", default=[]))), "confidence": decimal_value(first(p, "confidence")), "source_versions": JsonValue(first(p, "source_versions", default={})), "generated_at": timestamp(first(p, "generated_at", "updated_at")), "cache_status": text(first(p, "cache_status", default="fresh")), "payload": JsonValue(p)})]
    if sc == "cost_statistics_read_models":
        return [generic_row(domain, record, "read_model", "cost_statistics_read_models", {"scope_key": one(p, record.legacy_mongo_id, "scope_key", "id"), "project_scope": text(first(p, "project_scope", "project_id", default="all")), "scope_month": month_start(first(p, "scope_month", "month")), "generated_at": timestamp(first(p, "generated_at", "updated_at")), "entry_count": integer(first(p, "entry_count", default=0)), "source_counts": JsonValue(first(p, "source_counts", default={})), "source_versions": JsonValue(first(p, "source_versions", default={})), "payload": JsonValue(p)})]
    if sc == "tax_offset_read_models":
        return [generic_row(domain, record, "read_model", "tax_offset_read_models", {"scope_key": one(p, record.legacy_mongo_id, "scope_key", "id"), "scope_month": month_start(first(p, "scope_month", "month")), "generated_at": timestamp(first(p, "generated_at", "updated_at")), "entry_count": integer(first(p, "entry_count", default=0)), "source_counts": JsonValue(first(p, "source_counts", default={})), "source_versions": JsonValue(first(p, "source_versions", default={})), "payload": JsonValue(p)})]
    warnings.append(f"unhandled_transform_record:{sc}:{record.legacy_mongo_id}")
    return []


def build_etc_state_rows(record: StagingRecord, domain: str, p: dict[str, Any]) -> list[TargetRow]:
    sc = record.source_collection
    if sc.endswith(":etc_invoices"):
        return child_rows(record, domain, "app", "etc_invoices", p, "invoices", lambda c, legacy: {"legacy_mongo_id": legacy, "etc_invoice_id": one(c, legacy, "etc_invoice_id", "invoice_id", "id"), "invoice_no": text(first(c, "invoice_no")), "invoice_code": text(first(c, "invoice_code")), "invoice_date": date_value(first(c, "invoice_date")), "scope_month": month_start(first(c, "scope_month", "month")), "seller_name": text(first(c, "seller_name")), "buyer_name": text(first(c, "buyer_name")), "amount": decimal_value(first(c, "amount")), "tax_amount": decimal_value(first(c, "tax_amount")), "total_with_tax": decimal_value(first(c, "total_with_tax")), "status": text(first(c, "status", default="unknown")), "batch_id": text(first(c, "batch_id")), "task_id": text(first(c, "task_id")), "business_batch_id": text(first(c, "business_batch_id")), "oa_detection_payload": JsonValue(first(c, "oa_detection_payload", default={})), "file_path": text(first(c, "file_path")), "file_sha256": text(first(c, "file_sha256")), "version": integer(first(c, "version", default=1))})
    if sc.endswith(":etc_import_sessions"):
        return child_rows(record, domain, "app", "etc_import_sessions", p, "import_sessions", lambda c, legacy: {"legacy_mongo_id": legacy, "session_id": one(c, legacy, "session_id", "id"), "status": text(first(c, "status", default="unknown")), "imported_by": text(first(c, "imported_by")), "imported_at": timestamp(first(c, "imported_at", "created_at"))})
    if sc.endswith(":etc_import_batches"):
        return child_rows(record, domain, "app", "etc_import_batches", p, "import_batches", lambda c, legacy: {"legacy_mongo_id": legacy, "batch_id": one(c, legacy, "batch_id", "id"), "status": text(first(c, "status", default="unknown")), "scope_month": month_start(first(c, "scope_month", "month")), "invoice_count": integer(first(c, "invoice_count", default=0))})
    if sc.endswith(":etc_submission_batches"):
        return child_rows(record, domain, "app", "etc_submission_batches", p, "batches", lambda c, legacy: {"legacy_mongo_id": legacy, "submission_batch_id": one(c, legacy, "submission_batch_id", "batch_id", "id"), "status": text(first(c, "status", default="unknown")), "scope_month": month_start(first(c, "scope_month", "month")), "invoice_ids": TextArray(text_list(first(c, "invoice_ids", default=[]))), "submitted_by": text(first(c, "submitted_by")), "submitted_at": timestamp(first(c, "submitted_at")), "version": integer(first(c, "version", default=1))})
    return child_rows(record, domain, "app", "etc_business_batches", p, "business_batches", lambda c, legacy: {"legacy_mongo_id": legacy, "business_batch_id": one(c, legacy, "business_batch_id", "batch_id", "id"), "task_id": text(first(c, "task_id")), "status": text(first(c, "status", default="unknown")), "scope_month": month_start(first(c, "scope_month", "month")), "invoice_count": integer(first(c, "invoice_count", default=0)), "total_amount": decimal_value(first(c, "total_amount", default=0)), "oa_detection_status": text(first(c, "oa_detection_status")), "oa_detection_payload": JsonValue(first(c, "oa_detection_payload", default={})), "import_attempts": JsonValue(first(c, "import_attempts", default=[])), "audit_events": JsonValue(first(c, "audit_events", default=[])), "version": integer(first(c, "version", default=1))})


def build_etc_reconciliation_rows(record: StagingRecord, domain: str, p: dict[str, Any]) -> list[TargetRow]:
    if record.source_collection.endswith(":etc_reconciliation_tasks"):
        return child_rows(record, domain, "app", "etc_reconciliation_tasks", p, "tasks", lambda c, legacy: {"legacy_mongo_id": legacy, "task_id": one(c, legacy, "task_id", "id"), "status": text(first(c, "status", default="unknown")), "scope_month": month_start(first(c, "scope_month", "month")), "source_file_id": text(first(c, "source_file_id")), "result_summary": JsonValue(first(c, "result_summary", default={})), "version": integer(first(c, "version", default=1))})
    return child_rows(record, domain, "app", "etc_reconciliation_files", p, "files", lambda c, legacy: {"legacy_mongo_id": legacy, "task_id": text(first(c, "task_id")), "file_id": one(c, legacy, "file_id", "id", "stored_file_path"), "file_kind": text(first(c, "file_kind", "kind", default="unknown")), "status": text(first(c, "status", default="stored")), "file_path": text(first(c, "file_path", "stored_file_path")), "file_sha256": text(first(c, "file_sha256", "sha256"))})


def build_generated_read_model_rows(
    records: list[StagingRecord],
    *,
    only_domains: set[str] | None,
    skip_domains: set[str] | None,
    warnings: list[str],
) -> list[TargetRow]:
    if only_domains and "read_models" not in only_domains:
        return []
    if skip_domains and "read_models" in skip_domains:
        return []
    rows: list[TargetRow] = []
    for record in records:
        if record.source_collection not in {"invoices", "bank_transactions"}:
            continue
        p = record.normalized_payload or {}
        source_kind = "invoice" if record.source_collection == "invoices" else "bank_transaction"
        row_id = f"{source_kind}:{record.legacy_mongo_id}"
        title = text(first(p, "invoice_no", "bank_serial_no", default=record.legacy_mongo_id))
        counterparty = text(first(p, "counterparty_name", "counterparty_name_raw", "buyer_name", "seller_name"))
        searchable = " ".join(item for item in [title, counterparty, text(first(p, "summary", "remark"))] if item) or row_id
        target_id = stable_target_id(record.source_collection, record.legacy_mongo_id, "read_model", "search_index_rows")
        rows.append(
            TargetRow(
                domain="read_models",
                source_collection=record.source_collection,
                legacy_mongo_id=record.legacy_mongo_id,
                target_schema="read_model",
                target_table="search_index_rows",
                target_id=target_id,
                columns={
                    "row_id": row_id,
                    "source_kind": source_kind,
                    "scope_month": month_start(first(p, "invoice_month", "txn_month", "scope_month")),
                    "status": text(first(p, "status")),
                    "title": title,
                    "subtitle": counterparty,
                    "searchable_text": searchable,
                    "project_name": text(first(p, "project_name")),
                    "counterparty_name": counterparty,
                    "amount": decimal_value(first(p, "amount")),
                    "source_versions": JsonValue(first(p, "source_versions", default={})),
                    "generated_at": now_iso(),
                    "payload": JsonValue(p),
                    "raw_payload": JsonValue(full_raw(record)),
                },
                raw_payload=full_raw(record),
            )
        )
    return rows


def row(domain: str, record: StagingRecord, target_schema: str, target_table: str, columns: dict[str, Any]) -> TargetRow:
    return TargetRow(
        domain=domain,
        source_collection=record.source_collection,
        legacy_mongo_id=record.legacy_mongo_id,
        target_schema=target_schema,
        target_table=target_table,
        target_id=stable_target_id(record.source_collection, record.legacy_mongo_id, target_schema, target_table),
        columns=columns,
        raw_payload=full_raw(record),
    )


def generic_row(domain: str, record: StagingRecord, target_schema: str, target_table: str, columns: dict[str, Any]) -> TargetRow:
    return row(domain, record, target_schema, target_table, {**columns, "raw_payload": JsonValue(full_raw(record))})


def generic_event(
    domain: str,
    record: StagingRecord,
    target_schema: str,
    target_table: str,
    key_name: str,
    event_type: str,
) -> TargetRow:
    p = record.normalized_payload or {}
    columns: dict[str, Any] = {
        key_name: text(first(p, key_name, default=record.legacy_mongo_id)),
        "event_type": event_type,
        "actor_id": text(first(p, "actor_id", "updated_by", "created_by")),
        "occurred_at": timestamp(first(p, "occurred_at", "created_at", "updated_at")),
        "payload": JsonValue(p),
        "raw_payload": JsonValue(full_raw(record)),
    }
    return row(domain, record, target_schema, target_table, columns)


def pair_relation_history_rows(domain: str, record: StagingRecord) -> list[TargetRow]:
    p = record.normalized_payload or {}
    if isinstance(p.get("pair_relation_history"), (list, dict)):
        events = list_children({"pair_relation_history": p["pair_relation_history"]}, "pair_relation_history")
    else:
        events = [p] if p else []
    return [pair_relation_history_row(domain, record, event, index) for index, event in enumerate(events)]


def pair_relation_history_row(domain: str, record: StagingRecord, payload: dict[str, Any], index: int = 0) -> TargetRow:
    p = payload or {}
    child_record = StagingRecord(
        export_id=record.export_id,
        source_collection=record.source_collection,
        legacy_mongo_id=text(first(p, "event_id", "operation_id", "id")) or f"{record.legacy_mongo_id}:pair_relation_history:{index + 1}",
        record_type=record.record_type,
        normalized_payload=p,
        raw_payload={
            **record.raw_payload,
            "_stage04_child_index": index,
            "_stage04_child_key": "pair_relation_history",
            "_stage04_parent_legacy_id": record.legacy_mongo_id,
        },
    )
    columns: dict[str, Any] = {
        "case_id": text(first(p, "case_id", default=record.legacy_mongo_id)),
        "event_type": text(first(p, "operation_type", "event_type", default="relation_snapshot")),
        "actor_id": text(first(p, "actor_id", "updated_by", "created_by")),
        "occurred_at": timestamp(first(p, "occurred_at", "created_at", "updated_at")),
        "before_payload": JsonValue(first(p, "before_payload", default={})),
        "after_payload": JsonValue(first(p, "after_payload", "after_relations", default=p)),
        "raw_payload": JsonValue(full_raw(child_record)),
    }
    return row(domain, child_record, "app", "workbench_pair_relation_history", columns)


def category_audit_event_rows(domain: str, record: StagingRecord) -> list[TargetRow]:
    p = record.normalized_payload or {}
    events = list_children(p, "audit_log")
    rows: list[TargetRow] = []
    for index, event in enumerate(events):
        child_record = StagingRecord(
            export_id=record.export_id,
            source_collection=record.source_collection,
            legacy_mongo_id=text(first(event, "event_id", "id")) or f"{record.legacy_mongo_id}:audit_log:{index + 1}",
            record_type=record.record_type,
            normalized_payload=event,
            raw_payload={**record.raw_payload, "_stage04_child_key": "audit_log", "_stage04_parent_legacy_id": record.legacy_mongo_id},
        )
        rows.append(
            simple_event(
                domain,
                child_record,
                "app",
                "bank_transaction_category_events",
                text(first(event, "operation", "event_type", default="category_audit")),
            )
        )
    return rows


def settings_snapshot_row(domain: str, record: StagingRecord, settings_key: str) -> TargetRow:
    p = record.normalized_payload or {}
    return generic_row(
        domain,
        record,
        "app",
        "app_settings",
        {
            "settings_key": settings_key,
            "version": integer(first(p, "version", default=1)),
            "settings_payload": JsonValue(p),
            "updated_by": text(first(p, "updated_by", "actor_id", "created_by")),
            "updated_at": timestamp(first(p, "updated_at", "occurred_at", "created_at")),
        },
    )


def simple_event(domain: str, record: StagingRecord, target_schema: str, target_table: str, event_type: str) -> TargetRow:
    p = record.normalized_payload or {}
    columns: dict[str, Any] = {
        "event_type": event_type,
        "actor_id": text(first(p, "actor_id", "updated_by", "created_by")),
        "occurred_at": timestamp(first(p, "occurred_at", "created_at", "updated_at")),
        "payload": JsonValue(p),
        "raw_payload": JsonValue(full_raw(record)),
    }
    return row(domain, record, target_schema, target_table, columns)


def child_rows(
    record: StagingRecord,
    domain: str,
    target_schema: str,
    target_table: str,
    payload: dict[str, Any],
    key: str,
    builder: Any,
) -> list[TargetRow]:
    children = list_children(payload, key)
    rows: list[TargetRow] = []
    for index, child in enumerate(children):
        legacy = text(first(child, "legacy_mongo_id", "id", "row_id", "batch_id", "session_id", "task_id")) or f"{record.legacy_mongo_id}:{key}:{index + 1}"
        child_record = StagingRecord(
            export_id=record.export_id,
            source_collection=record.source_collection,
            legacy_mongo_id=legacy,
            record_type=record.record_type,
            normalized_payload=child,
            raw_payload={**record.raw_payload, "_stage04_child_key": key, "_stage04_parent_legacy_id": record.legacy_mongo_id},
        )
        rows.append(generic_row(domain, child_record, target_schema, target_table, builder(child, legacy)))
    return rows


def list_children(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if isinstance(value, dict):
        return [dict_value({**child, "id": child.get("id") or item_key}) for item_key, child in value.items() if isinstance(child, dict)]
    if isinstance(value, list):
        return [dict_value(item) for item in value if isinstance(item, dict)]
    return [payload] if payload else []


def full_raw(record: StagingRecord) -> dict[str, Any]:
    return {
        "export_id": record.export_id,
        "source_collection": record.source_collection,
        "legacy_mongo_id": record.legacy_mongo_id,
        "record_type": record.record_type,
        "normalized_payload": record.normalized_payload,
        "raw_payload": record.raw_payload,
        "transform_version": TRANSFORM_VERSION,
    }


def mapping_rows(plan: TransformPlan) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in plan.rows:
        key = (item.source_collection, item.legacy_mongo_id, item.target_schema, item.target_table)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source_collection": item.source_collection,
                "legacy_mongo_id": item.legacy_mongo_id,
                "target_schema": item.target_schema,
                "target_table": item.target_table,
                "target_id": item.target_id,
                "mapping_status": "applied",
                "raw_payload": JsonValue(
                    {
                        "export_id": plan.export_id,
                        "source_database": plan.source_database,
                        "manifest_sha256": plan.manifest_sha256,
                        "transform_version": TRANSFORM_VERSION,
                    }
                ),
            }
        )
    return rows


def build_transaction_sql(plan: TransformPlan, *, chunk_size: int = 250) -> str:
    statements = ["begin;", "select pg_advisory_xact_lock(hashtext('fin_ops_platform_stage04_transform'));"]
    mappings = mapping_rows(plan)
    for chunk in chunks(mappings, chunk_size):
        statements.append(mapping_conflict_guard_sql(chunk))
        statements.append(mapping_upsert_sql(chunk))
    statements.append(target_refresh_prelude_sql(plan.rows))
    for chunk in chunks(plan.rows, chunk_size):
        statements.append(target_upsert_sql(chunk))
    statements.append("commit;")
    return "\n".join(statement for statement in statements if statement.strip())


def mapping_conflict_guard_sql(rows: list[dict[str, Any]]) -> str:
    values = ",\n".join(
        "({source_collection}, {legacy_mongo_id}, {target_schema}, {target_table}, {target_id})".format(
            source_collection=sql_literal(row["source_collection"]),
            legacy_mongo_id=sql_literal(row["legacy_mongo_id"]),
            target_schema=sql_literal(row["target_schema"]),
            target_table=sql_literal(row["target_table"]),
            target_id=sql_literal(row["target_id"]),
        )
        for row in rows
    )
    return f"""
do $$
begin
  if exists (
    select 1
    from staging.id_mappings m
    join (values
{values}
    ) as incoming(source_collection, legacy_mongo_id, target_schema, target_table, target_id)
      on incoming.source_collection = m.source_collection
     and incoming.legacy_mongo_id = m.legacy_mongo_id
     and incoming.target_schema = m.target_schema
     and incoming.target_table = m.target_table
    where m.target_id::text <> incoming.target_id
  ) then
    raise exception 'stage04 id mapping conflict';
  end if;
end $$;
"""


def mapping_upsert_sql(rows: list[dict[str, Any]]) -> str:
    values = ",\n".join(
        "({source_collection}, {legacy_mongo_id}, {target_schema}, {target_table}, {target_id}, {mapping_status}, {raw_payload})".format(
            source_collection=sql_literal(row["source_collection"]),
            legacy_mongo_id=sql_literal(row["legacy_mongo_id"]),
            target_schema=sql_literal(row["target_schema"]),
            target_table=sql_literal(row["target_table"]),
            target_id=sql_literal(row["target_id"]),
            mapping_status=sql_literal(row["mapping_status"]),
            raw_payload=render_value(row["raw_payload"]),
        )
        for row in rows
    )
    return f"""
insert into staging.id_mappings(source_collection, legacy_mongo_id, target_schema, target_table, target_id, mapping_status, raw_payload)
values
{values}
on conflict (source_collection, legacy_mongo_id, target_schema, target_table)
do update set
  mapping_status = excluded.mapping_status,
  raw_payload = excluded.raw_payload
where staging.id_mappings.target_id = excluded.target_id;
"""


def target_upsert_sql(rows: list[TargetRow]) -> str:
    grouped: dict[tuple[str, str, tuple[str, ...]], list[TargetRow]] = {}
    for row_item in rows:
        columns = tuple(sorted({"id", *row_item.columns.keys()}))
        grouped.setdefault((row_item.target_schema, row_item.target_table, columns), []).append(row_item)
    statements: list[str] = []
    for (schema, table, columns), group in grouped.items():
        values = ",\n".join(
            "("
            + ", ".join(render_value(row_item.target_id) if column == "id" else render_value(row_item.columns.get(column)) for column in columns)
            + ")"
            for row_item in group
        )
        assignments = ", ".join(f"{column} = excluded.{column}" for column in columns if column != "id")
        conflict_columns = TARGET_CONFLICT_COLUMNS.get((schema, table), ("id",))
        statements.append(
            f"""
insert into {schema}.{table} ({", ".join(columns)})
values
{values}
on conflict ({", ".join(conflict_columns)}) do update set {assignments};
"""
        )
    return "\n".join(statements)


def target_refresh_prelude_sql(rows: list[TargetRow]) -> str:
    values_by_table: dict[tuple[str, str, str], set[str]] = {}
    full_replace_tables = {
        (row_item.target_schema, row_item.target_table)
        for row_item in rows
        if (row_item.target_schema, row_item.target_table) in FULL_REPLACE_EVENT_TABLES
    }
    for row_item in rows:
        if (row_item.target_schema, row_item.target_table) in full_replace_tables:
            continue
        key_column = REPLACE_EVENT_TARGETS.get((row_item.target_schema, row_item.target_table))
        if not key_column:
            continue
        value = row_item.columns.get(key_column)
        if value in (None, ""):
            continue
        values_by_table.setdefault((row_item.target_schema, row_item.target_table, key_column), set()).add(str(value))
    statements: list[str] = []
    for schema, table in sorted(full_replace_tables):
        statements.append(f"delete from {schema}.{table};")
    for schema, table, key_column in sorted(values_by_table):
        values = sorted(values_by_table[(schema, table, key_column)])
        if not values:
            continue
        statements.append(
            f"""
delete from {schema}.{table}
where {key_column} in ({", ".join(sql_literal(value) for value in values)});
"""
        )
    return "\n".join(statements)


def sql_literal(value: object) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def render_value(value: Any) -> str:
    if isinstance(value, JsonValue):
        return f"{sql_literal(json.dumps(value.value, ensure_ascii=False, separators=(',', ':')))}::jsonb"
    if isinstance(value, TextArray):
        return "array[" + ", ".join(sql_literal(item) for item in value.value) + "]::text[]"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return sql_literal(value)


def chunks(items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict) and "value" in value:
            value = value["value"]
        if value not in (None, ""):
            return value
    return default


def one(payload: dict[str, Any], fallback: str, *keys: str) -> str:
    return text(first(payload, *keys, default=fallback)) or fallback


def text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def decimal_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return format(Decimal(str(value).replace(",", "")), "f")
    except (InvalidOperation, ValueError):
        return None


def date_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text_value = str(value)
    return text_value[:10].replace("/", "-") if len(text_value) >= 10 else None


def month_start(value: Any) -> str | None:
    if isinstance(value, str) and len(value) == 7 and value[4] in {"-", "/"}:
        return f"{value.replace('/', '-')}-01"
    parsed = date_value(value)
    if not parsed:
        return None
    return f"{parsed[:7]}-01"


def timestamp(value: Any) -> str:
    if value in (None, ""):
        return now_iso()
    if isinstance(value, datetime):
        resolved = value if value.tzinfo else value.replace(tzinfo=UTC)
        return resolved.isoformat()
    return str(value)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def text_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]
