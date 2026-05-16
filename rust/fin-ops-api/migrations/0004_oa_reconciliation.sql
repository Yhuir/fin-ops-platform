-- OA normalization and reconciliation fact tables.
-- OA source databases remain read-only; this migration only stores normalized
-- application facts, sync watermarks, and reconciliation/workbench facts in PostgreSQL.

CREATE TABLE app.oa_sync_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL DEFAULT 'oa',
    scope text NOT NULL,
    triggered_by text NOT NULL,
    status text NOT NULL,
    pulled_count integer NOT NULL DEFAULT 0,
    success_count integer NOT NULL DEFAULT 0,
    failed_count integer NOT NULL DEFAULT 0,
    retry_of_run_id uuid REFERENCES app.oa_sync_runs(id),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    watermark_before jsonb NOT NULL DEFAULT '{}'::jsonb,
    watermark_after jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT oa_sync_runs_source_system_chk CHECK (source_system <> ''),
    CONSTRAINT oa_sync_runs_status_chk CHECK (
        status IN ('pending', 'running', 'succeeded', 'partially_succeeded', 'failed', 'cancelled')
    ),
    CONSTRAINT oa_sync_runs_counts_chk CHECK (
        pulled_count >= 0
        AND success_count >= 0
        AND failed_count >= 0
    ),
    CONSTRAINT oa_sync_runs_finished_at_chk CHECK (finished_at IS NULL OR finished_at >= started_at),
    CONSTRAINT oa_sync_runs_watermark_before_chk CHECK (jsonb_typeof(watermark_before) = 'object'),
    CONSTRAINT oa_sync_runs_watermark_after_chk CHECK (jsonb_typeof(watermark_after) = 'object'),
    CONSTRAINT oa_sync_runs_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE INDEX oa_sync_runs_status_started_idx
    ON app.oa_sync_runs (status, started_at DESC);

CREATE INDEX oa_sync_runs_scope_started_idx
    ON app.oa_sync_runs (source_system, scope, started_at DESC);

CREATE TABLE app.oa_sync_watermarks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL DEFAULT 'oa',
    scope text NOT NULL,
    watermark jsonb NOT NULL,
    last_successful_run_id uuid REFERENCES app.oa_sync_runs(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT oa_sync_watermarks_source_system_chk CHECK (source_system <> ''),
    CONSTRAINT oa_sync_watermarks_watermark_chk CHECK (jsonb_typeof(watermark) = 'object'),
    CONSTRAINT oa_sync_watermarks_source_scope_uk UNIQUE (source_system, scope)
);

CREATE TABLE app.oa_applications (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    source_updated_month date NOT NULL,
    approved_month date,
    oa_source_id text NOT NULL,
    source_collection text,
    form_type text NOT NULL,
    workflow_no text,
    title text,
    status text NOT NULL,
    applicant text,
    applicant_id text,
    department_id text,
    department_name text,
    project_id text,
    project_name text,
    counterparty_name text,
    amount numeric(20, 2),
    currency text NOT NULL DEFAULT 'CNY',
    submitted_at timestamptz,
    approved_at timestamptz,
    source_updated_at timestamptz NOT NULL,
    sync_run_id uuid REFERENCES app.oa_sync_runs(id),
    normalized_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload_hash text NOT NULL,
    legacy_collection text,
    legacy_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text,
    CONSTRAINT oa_applications_pkey PRIMARY KEY (source_updated_month, id),
    CONSTRAINT oa_applications_status_chk CHECK (
        status IN ('approved', 'in_progress', 'rejected', 'cancelled', 'unknown')
    ),
    CONSTRAINT oa_applications_amount_chk CHECK (amount IS NULL OR amount >= 0),
    CONSTRAINT oa_applications_currency_chk CHECK (currency <> ''),
    CONSTRAINT oa_applications_source_updated_month_chk CHECK (
        source_updated_month = date_trunc('month', source_updated_at)::date
    ),
    CONSTRAINT oa_applications_approved_month_chk CHECK (
        approved_month IS NULL
        OR approved_at IS NULL
        OR approved_month = date_trunc('month', approved_at)::date
    ),
    CONSTRAINT oa_applications_normalized_payload_chk CHECK (jsonb_typeof(normalized_payload) = 'object'),
    CONSTRAINT oa_applications_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
) PARTITION BY RANGE (source_updated_month);

CREATE UNIQUE INDEX oa_applications_source_id_uk
    ON app.oa_applications (source_updated_month, oa_source_id);

CREATE UNIQUE INDEX oa_applications_workflow_no_uk
    ON app.oa_applications (source_updated_month, form_type, workflow_no)
    WHERE workflow_no IS NOT NULL;

CREATE UNIQUE INDEX oa_applications_legacy_id_uk
    ON app.oa_applications (source_updated_month, legacy_collection, legacy_id)
    WHERE legacy_collection IS NOT NULL AND legacy_id IS NOT NULL;

CREATE INDEX oa_applications_source_updated_idx
    ON app.oa_applications (source_updated_month, source_updated_at DESC);

CREATE INDEX oa_applications_approved_idx
    ON app.oa_applications (approved_month, approved_at DESC)
    WHERE approved_month IS NOT NULL;

CREATE INDEX oa_applications_form_status_idx
    ON app.oa_applications (form_type, status);

CREATE INDEX oa_applications_project_id_idx
    ON app.oa_applications (project_id)
    WHERE project_id IS NOT NULL;

CREATE INDEX oa_applications_applicant_trgm_idx
    ON app.oa_applications USING gin (applicant gin_trgm_ops)
    WHERE applicant IS NOT NULL;

CREATE INDEX oa_applications_project_name_trgm_idx
    ON app.oa_applications USING gin (project_name gin_trgm_ops)
    WHERE project_name IS NOT NULL;

CREATE INDEX oa_applications_counterparty_name_trgm_idx
    ON app.oa_applications USING gin (counterparty_name gin_trgm_ops)
    WHERE counterparty_name IS NOT NULL;

CREATE TABLE app.oa_application_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_month date NOT NULL,
    application_id uuid NOT NULL,
    item_type text NOT NULL,
    line_no integer NOT NULL,
    amount numeric(20, 2),
    tax_amount numeric(20, 2),
    counterparty_name text,
    project_id text,
    project_name text,
    expense_type text,
    invoice_no text,
    bank_account_no text,
    normalized_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT oa_application_items_application_fkey
        FOREIGN KEY (application_month, application_id)
        REFERENCES app.oa_applications(source_updated_month, id),
    CONSTRAINT oa_application_items_line_no_chk CHECK (line_no >= 1),
    CONSTRAINT oa_application_items_item_type_chk CHECK (
        item_type IN ('expense', 'payment', 'invoice', 'bank', 'project', 'other')
    ),
    CONSTRAINT oa_application_items_amount_chk CHECK (amount IS NULL OR amount >= 0),
    CONSTRAINT oa_application_items_tax_amount_chk CHECK (tax_amount IS NULL OR tax_amount >= 0),
    CONSTRAINT oa_application_items_normalized_payload_chk CHECK (jsonb_typeof(normalized_payload) = 'object'),
    CONSTRAINT oa_application_items_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object'),
    CONSTRAINT oa_application_items_line_uk UNIQUE (application_month, application_id, item_type, line_no)
);

CREATE INDEX oa_application_items_application_idx
    ON app.oa_application_items (application_month, application_id);

CREATE INDEX oa_application_items_project_idx
    ON app.oa_application_items (project_id)
    WHERE project_id IS NOT NULL;

CREATE INDEX oa_application_items_invoice_no_idx
    ON app.oa_application_items (invoice_no)
    WHERE invoice_no IS NOT NULL;

CREATE TABLE app.oa_attachments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_month date NOT NULL,
    application_id uuid NOT NULL,
    file_object_id uuid REFERENCES app.file_objects(id),
    oa_attachment_id text,
    file_name text NOT NULL,
    content_type text,
    invoice_cache_key text,
    parsed_invoice_month date,
    parsed_invoice_id uuid,
    normalized_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT oa_attachments_application_fkey
        FOREIGN KEY (application_month, application_id)
        REFERENCES app.oa_applications(source_updated_month, id),
    CONSTRAINT oa_attachments_parsed_invoice_fkey
        FOREIGN KEY (parsed_invoice_month, parsed_invoice_id)
        REFERENCES app.invoices(invoice_month, id),
    CONSTRAINT oa_attachments_parsed_invoice_pair_chk CHECK (
        (parsed_invoice_month IS NULL AND parsed_invoice_id IS NULL)
        OR (parsed_invoice_month IS NOT NULL AND parsed_invoice_id IS NOT NULL)
    ),
    CONSTRAINT oa_attachments_normalized_payload_chk CHECK (jsonb_typeof(normalized_payload) = 'object'),
    CONSTRAINT oa_attachments_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE UNIQUE INDEX oa_attachments_source_attachment_uk
    ON app.oa_attachments (application_month, application_id, oa_attachment_id)
    WHERE oa_attachment_id IS NOT NULL;

CREATE INDEX oa_attachments_application_idx
    ON app.oa_attachments (application_month, application_id);

CREATE INDEX oa_attachments_file_object_idx
    ON app.oa_attachments (file_object_id)
    WHERE file_object_id IS NOT NULL;

CREATE INDEX oa_attachments_invoice_cache_key_idx
    ON app.oa_attachments (invoice_cache_key)
    WHERE invoice_cache_key IS NOT NULL;

CREATE TABLE app.reconciliation_cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_type text NOT NULL,
    biz_side text NOT NULL,
    counterparty_id text,
    counterparty_name text,
    total_amount numeric(20, 2) NOT NULL,
    difference_amount numeric(20, 2) NOT NULL DEFAULT 0,
    difference_reason text,
    difference_note text,
    status text NOT NULL,
    project_id text,
    approval_form_id text,
    source_result_id text,
    exception_code text,
    resolution_type text,
    remark text,
    idempotency_key text NOT NULL,
    confirmed_at timestamptz,
    cancelled_at timestamptz,
    created_by text NOT NULL,
    approved_by text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reconciliation_cases_case_type_chk CHECK (
        case_type IN ('automatic', 'manual', 'difference', 'offset', 'offline')
    ),
    CONSTRAINT reconciliation_cases_biz_side_chk CHECK (
        biz_side IN ('receivable', 'payable', 'mixed', 'unknown')
    ),
    CONSTRAINT reconciliation_cases_status_chk CHECK (
        status IN ('draft', 'confirmed', 'follow_up_required', 'cancelled')
    ),
    CONSTRAINT reconciliation_cases_total_amount_chk CHECK (total_amount >= 0),
    CONSTRAINT reconciliation_cases_difference_reason_chk CHECK (
        difference_reason IS NULL
        OR difference_reason IN ('fee', 'rounding', 'fx', 'tax', 'other')
    ),
    CONSTRAINT reconciliation_cases_cancelled_at_chk CHECK (
        (status = 'cancelled' AND cancelled_at IS NOT NULL)
        OR status <> 'cancelled'
    ),
    CONSTRAINT reconciliation_cases_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object'),
    CONSTRAINT reconciliation_cases_idempotency_key_uk UNIQUE (idempotency_key)
);

CREATE INDEX reconciliation_cases_status_created_idx
    ON app.reconciliation_cases (status, created_at DESC);

CREATE INDEX reconciliation_cases_type_status_idx
    ON app.reconciliation_cases (case_type, status);

CREATE INDEX reconciliation_cases_project_created_idx
    ON app.reconciliation_cases (project_id, created_at DESC)
    WHERE project_id IS NOT NULL;

CREATE INDEX reconciliation_cases_counterparty_created_idx
    ON app.reconciliation_cases (counterparty_id, created_at DESC)
    WHERE counterparty_id IS NOT NULL;

CREATE TABLE app.reconciliation_case_rows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL REFERENCES app.reconciliation_cases(id),
    object_type text NOT NULL,
    object_id uuid NOT NULL,
    object_month date,
    side_role text NOT NULL,
    applied_amount numeric(20, 2) NOT NULL,
    binding_status text NOT NULL DEFAULT 'active',
    source_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reconciliation_case_rows_object_type_chk CHECK (
        object_type IN (
            'bank_transaction',
            'invoice',
            'oa_application',
            'oa_application_item',
            'turnover_relation',
            'offline_payment',
            'offset_note'
        )
    ),
    CONSTRAINT reconciliation_case_rows_side_role_chk CHECK (
        side_role IN ('bank', 'invoice', 'oa', 'turnover', 'offline', 'offset')
    ),
    CONSTRAINT reconciliation_case_rows_binding_status_chk CHECK (
        binding_status IN ('active', 'cancelled', 'reverted')
    ),
    CONSTRAINT reconciliation_case_rows_applied_amount_chk CHECK (applied_amount >= 0),
    CONSTRAINT reconciliation_case_rows_source_snapshot_chk CHECK (jsonb_typeof(source_snapshot) = 'object'),
    CONSTRAINT reconciliation_case_rows_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object'),
    CONSTRAINT reconciliation_case_rows_case_object_uk UNIQUE (case_id, object_type, object_id, side_role)
);

CREATE INDEX reconciliation_case_rows_case_idx
    ON app.reconciliation_case_rows (case_id);

CREATE INDEX reconciliation_case_rows_object_idx
    ON app.reconciliation_case_rows (object_type, object_id);

CREATE INDEX reconciliation_case_rows_month_object_idx
    ON app.reconciliation_case_rows (object_month, object_type)
    WHERE object_month IS NOT NULL;

CREATE INDEX reconciliation_case_rows_active_object_idx
    ON app.reconciliation_case_rows (object_type, object_id)
    WHERE binding_status = 'active';

CREATE TABLE app.workbench_row_overrides (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    row_type text NOT NULL,
    source_object_type text NOT NULL,
    source_object_id uuid NOT NULL,
    scope_month date,
    override_type text NOT NULL,
    override_payload jsonb NOT NULL,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT workbench_row_overrides_row_type_chk CHECK (row_type IN ('oa', 'bank', 'invoice')),
    CONSTRAINT workbench_row_overrides_source_object_type_chk CHECK (
        source_object_type IN ('bank_transaction', 'invoice', 'oa_application', 'oa_application_item')
    ),
    CONSTRAINT workbench_row_overrides_override_type_chk CHECK (
        override_type IN ('note', 'ignore', 'project_assignment', 'status', 'tag')
    ),
    CONSTRAINT workbench_row_overrides_status_chk CHECK (status IN ('active', 'cancelled', 'superseded')),
    CONSTRAINT workbench_row_overrides_payload_chk CHECK (jsonb_typeof(override_payload) = 'object'),
    CONSTRAINT workbench_row_overrides_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE UNIQUE INDEX workbench_row_overrides_active_uk
    ON app.workbench_row_overrides (source_object_type, source_object_id, override_type)
    WHERE status = 'active';

CREATE INDEX workbench_row_overrides_scope_idx
    ON app.workbench_row_overrides (scope_month, row_type, status);

CREATE TABLE app.workbench_exception_cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_case_id uuid REFERENCES app.reconciliation_cases(id),
    biz_side text NOT NULL,
    exception_code text NOT NULL,
    exception_title text NOT NULL,
    status text NOT NULL,
    resolution_action text,
    follow_up_ledger_type text,
    note text,
    source_invoice_ids uuid[] NOT NULL DEFAULT '{}',
    source_bank_txn_ids uuid[] NOT NULL DEFAULT '{}',
    created_by text NOT NULL,
    resolved_by text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT workbench_exception_cases_biz_side_chk CHECK (
        biz_side IN ('receivable', 'payable', 'mixed', 'unknown')
    ),
    CONSTRAINT workbench_exception_cases_status_chk CHECK (
        status IN ('open', 'in_progress', 'resolved', 'ignored', 'cancelled')
    ),
    CONSTRAINT workbench_exception_cases_resolution_action_chk CHECK (
        resolution_action IS NULL
        OR resolution_action IN ('none', 'manual_reconcile', 'mark_no_oa', 'create_turnover', 'ignore')
    ),
    CONSTRAINT workbench_exception_cases_resolved_at_chk CHECK (
        (status IN ('resolved', 'ignored', 'cancelled') AND resolved_at IS NOT NULL)
        OR status NOT IN ('resolved', 'ignored', 'cancelled')
    ),
    CONSTRAINT workbench_exception_cases_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE INDEX workbench_exception_cases_status_idx
    ON app.workbench_exception_cases (status, created_at DESC);

CREATE INDEX workbench_exception_cases_source_case_idx
    ON app.workbench_exception_cases (source_case_id)
    WHERE source_case_id IS NOT NULL;

CREATE TABLE app.no_oa_bank_batches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_month date NOT NULL,
    status text NOT NULL,
    reason text NOT NULL,
    bank_transaction_ids uuid[] NOT NULL,
    total_amount numeric(20, 2) NOT NULL,
    created_by text NOT NULL,
    submitted_at timestamptz,
    cancelled_at timestamptz,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT no_oa_bank_batches_status_chk CHECK (
        status IN ('draft', 'submitted', 'confirmed', 'cancelled')
    ),
    CONSTRAINT no_oa_bank_batches_bank_transaction_ids_chk CHECK (cardinality(bank_transaction_ids) > 0),
    CONSTRAINT no_oa_bank_batches_total_amount_chk CHECK (total_amount >= 0),
    CONSTRAINT no_oa_bank_batches_cancelled_at_chk CHECK (
        (status = 'cancelled' AND cancelled_at IS NOT NULL)
        OR status <> 'cancelled'
    ),
    CONSTRAINT no_oa_bank_batches_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE INDEX no_oa_bank_batches_scope_status_idx
    ON app.no_oa_bank_batches (scope_month, status, created_at DESC);

CREATE TABLE app.turnover_relations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    relation_type text NOT NULL,
    source_object_type text NOT NULL,
    source_object_id uuid NOT NULL,
    counterparty_id text,
    counterparty_name text,
    receivable_amount numeric(20, 2) NOT NULL DEFAULT 0,
    payable_amount numeric(20, 2) NOT NULL DEFAULT 0,
    offset_amount numeric(20, 2) NOT NULL DEFAULT 0,
    status text NOT NULL,
    project_id text,
    note text,
    created_by text NOT NULL,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    cancelled_at timestamptz,
    CONSTRAINT turnover_relations_relation_type_chk CHECK (
        relation_type IN ('receivable', 'payable', 'offset', 'transfer', 'other')
    ),
    CONSTRAINT turnover_relations_source_object_type_chk CHECK (
        source_object_type IN (
            'bank_transaction',
            'invoice',
            'oa_application',
            'oa_application_item',
            'reconciliation_case',
            'manual'
        )
    ),
    CONSTRAINT turnover_relations_status_chk CHECK (status IN ('active', 'settled', 'cancelled')),
    CONSTRAINT turnover_relations_amount_chk CHECK (
        receivable_amount >= 0
        AND payable_amount >= 0
        AND offset_amount >= 0
        AND offset_amount <= receivable_amount + payable_amount
    ),
    CONSTRAINT turnover_relations_cancelled_at_chk CHECK (
        (status = 'cancelled' AND cancelled_at IS NOT NULL)
        OR status <> 'cancelled'
    ),
    CONSTRAINT turnover_relations_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE UNIQUE INDEX turnover_relations_active_source_uk
    ON app.turnover_relations (source_object_type, source_object_id, relation_type)
    WHERE status = 'active';

CREATE INDEX turnover_relations_status_idx
    ON app.turnover_relations (status, created_at DESC);

CREATE INDEX turnover_relations_project_idx
    ON app.turnover_relations (project_id, created_at DESC)
    WHERE project_id IS NOT NULL;

CREATE INDEX turnover_relations_counterparty_idx
    ON app.turnover_relations (counterparty_id, created_at DESC)
    WHERE counterparty_id IS NOT NULL;

CREATE OR REPLACE FUNCTION app.create_oa_applications_month_partition(
    partition_month date
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    month_start date;
    next_month date;
    partition_name text;
BEGIN
    month_start := date_trunc('month', partition_month)::date;
    next_month := (month_start + INTERVAL '1 month')::date;
    partition_name := 'oa_applications_' || to_char(month_start, 'YYYY_MM');

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS app.%I PARTITION OF app.oa_applications FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        month_start,
        next_month
    );

    RETURN format('%I.%I', 'app', partition_name);
END;
$$;
