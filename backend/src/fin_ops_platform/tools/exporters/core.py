from __future__ import annotations

from fin_ops_platform.tools.exporters import ExportDefinition


CORE_EXPORTS: tuple[ExportDefinition, ...] = (
    ExportDefinition(
        output_file="import_batches.ndjson",
        source_collection="import_batches",
        record_type="import_batch",
        identity_fields=("id", "batch_id", "legacy_mongo_id"),
    ),
    ExportDefinition(
        output_file="import_batch_rows.ndjson",
        source_collection="imports_meta",
        record_type="import_batch_rows_snapshot",
        identity_fields=("id", "batch_id"),
        raw_note="Rows are retained in the imports meta snapshot for stage 04 transform.",
    ),
    ExportDefinition(
        output_file="invoices.ndjson",
        source_collection="invoices",
        record_type="invoice",
        identity_fields=("id", "invoice_id", "source_unique_key", "data_fingerprint", "invoice_no"),
    ),
    ExportDefinition(
        output_file="bank_transactions.ndjson",
        source_collection="bank_transactions",
        record_type="bank_transaction",
        identity_fields=("id", "transaction_id", "source_unique_key", "data_fingerprint", "bank_serial_no"),
    ),
    ExportDefinition(
        output_file="import_files.ndjson",
        source_collection="file_import_files",
        record_type="import_file",
        identity_fields=("id", "file_id", "stored_file_path"),
    ),
    ExportDefinition(
        output_file="file_import_sessions.ndjson",
        source_collection="file_import_sessions",
        record_type="file_import_session",
        identity_fields=("id", "session_id"),
    ),
    ExportDefinition(
        output_file="file_objects.ndjson",
        source_collection=None,
        record_type="file_object",
        identity_fields=("_id", "legacy_gridfs_id", "filename"),
        raw_note="Generated from GridFS files metadata; file content is not migrated in stage 03.",
    ),
    ExportDefinition(
        output_file="gridfs_files_manifest.ndjson",
        source_collection=None,
        record_type="gridfs_file",
        identity_fields=("_id", "filename"),
        raw_note="Generated from GridFS files metadata with bounded checksum sampling.",
    ),
)
