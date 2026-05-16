-- Core financial fact tables for bank transactions, invoices, and inventory events.
-- This migration assumes 0001/0002 already created the app schema, pgcrypto,
-- pg_trgm, app.import_batches, app.import_files, and app.file_objects.

CREATE TABLE app.bank_transactions (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    txn_date date NOT NULL,
    txn_month date NOT NULL,
    trade_time timestamptz,
    pay_receive_time timestamptz,
    account_no text NOT NULL,
    account_name text,
    txn_direction text NOT NULL,
    amount numeric(20, 2) NOT NULL,
    signed_amount numeric(20, 2) NOT NULL,
    written_off_amount numeric(20, 2) NOT NULL DEFAULT 0,
    balance numeric(20, 2),
    currency text NOT NULL DEFAULT 'CNY',
    counterparty_name_raw text NOT NULL,
    counterparty_name_normalized text,
    counterparty_account_no text,
    counterparty_bank_name text,
    bank_serial_no text,
    enterprise_serial_no text,
    source_unique_key text,
    data_fingerprint text,
    source_batch_id uuid REFERENCES app.import_batches(id),
    project_id text,
    status text NOT NULL,
    summary text,
    remark text,
    bank_text_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    legacy_collection text,
    legacy_id text,
    legacy_payload_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text,
    CONSTRAINT bank_transactions_pkey PRIMARY KEY (txn_month, id),
    CONSTRAINT bank_transactions_txn_direction_chk CHECK (txn_direction IN ('inflow', 'outflow')),
    CONSTRAINT bank_transactions_status_chk CHECK (
        status IN (
            'pending',
            'partially_reconciled',
            'reconciled',
            'classified_as_prepayment',
            'classified_as_advance_receipt',
            'pending_refund',
            'pending_counterparty_confirmation'
        )
    ),
    CONSTRAINT bank_transactions_amount_chk CHECK (amount >= 0),
    CONSTRAINT bank_transactions_written_off_amount_chk CHECK (
        written_off_amount >= 0
        AND written_off_amount <= amount
    ),
    CONSTRAINT bank_transactions_signed_amount_chk CHECK (
        (txn_direction = 'inflow' AND signed_amount >= 0)
        OR (txn_direction = 'outflow' AND signed_amount <= 0)
    ),
    CONSTRAINT bank_transactions_txn_month_chk CHECK (
        txn_month = date_trunc('month', txn_date)::date
    ),
    CONSTRAINT bank_transactions_currency_chk CHECK (currency <> ''),
    CONSTRAINT bank_transactions_bank_text_fields_chk CHECK (jsonb_typeof(bank_text_fields) = 'array'),
    CONSTRAINT bank_transactions_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
) PARTITION BY RANGE (txn_month);

CREATE UNIQUE INDEX bank_transactions_source_unique_key_uk
    ON app.bank_transactions (txn_month, source_batch_id, source_unique_key)
    WHERE source_unique_key IS NOT NULL;

CREATE UNIQUE INDEX bank_transactions_data_fingerprint_uk
    ON app.bank_transactions (txn_month, data_fingerprint)
    WHERE data_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX bank_transactions_legacy_id_uk
    ON app.bank_transactions (txn_month, legacy_collection, legacy_id)
    WHERE legacy_collection IS NOT NULL AND legacy_id IS NOT NULL;

CREATE INDEX bank_transactions_account_date_idx
    ON app.bank_transactions (txn_month, account_no, txn_date DESC, id);

CREATE INDEX bank_transactions_status_date_idx
    ON app.bank_transactions (txn_month, status, txn_date DESC);

CREATE INDEX bank_transactions_counterparty_normalized_idx
    ON app.bank_transactions (txn_month, counterparty_name_normalized);

CREATE INDEX bank_transactions_amount_idx
    ON app.bank_transactions (txn_month, amount);

CREATE INDEX bank_transactions_source_batch_id_idx
    ON app.bank_transactions (source_batch_id);

CREATE INDEX bank_transactions_bank_serial_no_idx
    ON app.bank_transactions (bank_serial_no)
    WHERE bank_serial_no IS NOT NULL;

CREATE INDEX bank_transactions_counterparty_raw_trgm_idx
    ON app.bank_transactions USING gin (counterparty_name_raw gin_trgm_ops);

CREATE INDEX bank_transactions_summary_trgm_idx
    ON app.bank_transactions USING gin (summary gin_trgm_ops)
    WHERE summary IS NOT NULL;

CREATE TABLE app.bank_transaction_categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_transaction_month date NOT NULL,
    bank_transaction_id uuid NOT NULL,
    category_type text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    amount numeric(20, 2) NOT NULL,
    reason text,
    note text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    legacy_collection text,
    legacy_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text,
    cancelled_at timestamptz,
    cancelled_by text,
    CONSTRAINT bank_transaction_categories_bank_transaction_fkey
        FOREIGN KEY (bank_transaction_month, bank_transaction_id)
        REFERENCES app.bank_transactions(txn_month, id),
    CONSTRAINT bank_transaction_categories_category_type_chk CHECK (
        category_type IN (
            'prepayment',
            'advance_receipt',
            'pending_refund',
            'counterparty_confirmation',
            'other'
        )
    ),
    CONSTRAINT bank_transaction_categories_status_chk CHECK (status IN ('active', 'cancelled', 'replaced')),
    CONSTRAINT bank_transaction_categories_amount_chk CHECK (amount >= 0),
    CONSTRAINT bank_transaction_categories_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE UNIQUE INDEX bank_transaction_categories_active_uk
    ON app.bank_transaction_categories (bank_transaction_month, bank_transaction_id, category_type)
    WHERE status = 'active';

CREATE UNIQUE INDEX bank_transaction_categories_legacy_id_uk
    ON app.bank_transaction_categories (legacy_collection, legacy_id)
    WHERE legacy_collection IS NOT NULL AND legacy_id IS NOT NULL;

CREATE INDEX bank_transaction_categories_transaction_idx
    ON app.bank_transaction_categories (bank_transaction_month, bank_transaction_id);

CREATE INDEX bank_transaction_categories_type_status_idx
    ON app.bank_transaction_categories (category_type, status, created_at DESC);

CREATE TABLE app.bank_transaction_category_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id uuid REFERENCES app.bank_transaction_categories(id),
    bank_transaction_month date NOT NULL,
    bank_transaction_id uuid NOT NULL,
    event_type text NOT NULL,
    previous_status text,
    new_status text,
    amount numeric(20, 2),
    event_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    CONSTRAINT bank_transaction_category_events_bank_transaction_fkey
        FOREIGN KEY (bank_transaction_month, bank_transaction_id)
        REFERENCES app.bank_transactions(txn_month, id),
    CONSTRAINT bank_transaction_category_events_event_type_chk CHECK (
        event_type IN ('created', 'updated', 'cancelled', 'replaced', 'migrated')
    ),
    CONSTRAINT bank_transaction_category_events_status_chk CHECK (
        previous_status IS NULL OR previous_status IN ('active', 'cancelled', 'replaced')
    ),
    CONSTRAINT bank_transaction_category_events_new_status_chk CHECK (
        new_status IS NULL OR new_status IN ('active', 'cancelled', 'replaced')
    ),
    CONSTRAINT bank_transaction_category_events_amount_chk CHECK (amount IS NULL OR amount >= 0),
    CONSTRAINT bank_transaction_category_events_payload_chk CHECK (jsonb_typeof(event_payload) = 'object'),
    CONSTRAINT bank_transaction_category_events_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE UNIQUE INDEX bank_transaction_category_events_idempotency_key_uk
    ON app.bank_transaction_category_events (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX bank_transaction_category_events_category_idx
    ON app.bank_transaction_category_events (category_id, created_at DESC)
    WHERE category_id IS NOT NULL;

CREATE INDEX bank_transaction_category_events_transaction_idx
    ON app.bank_transaction_category_events (bank_transaction_month, bank_transaction_id, created_at DESC);

CREATE TABLE app.invoices (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    invoice_month date NOT NULL,
    invoice_date date,
    invoice_type text NOT NULL,
    invoice_no text NOT NULL,
    invoice_code text,
    digital_invoice_no text,
    source_unique_key text,
    data_fingerprint text,
    amount numeric(20, 2) NOT NULL,
    signed_amount numeric(20, 2) NOT NULL,
    tax_amount numeric(20, 2),
    total_with_tax numeric(20, 2),
    written_off_amount numeric(20, 2) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'CNY',
    seller_tax_no text,
    seller_name text,
    buyer_tax_no text,
    buyer_name text,
    tax_rate numeric(9, 6),
    quantity numeric(24, 6),
    unit_price numeric(24, 6),
    invoice_status_from_source text,
    status text NOT NULL,
    risk_level text,
    issuer text,
    project_id text,
    department_id text,
    source_batch_id uuid REFERENCES app.import_batches(id),
    oa_form_id text,
    etc_invoice_id text,
    etc_import_batch_id text,
    etc_submission_batch_id text,
    etc_submission_status text,
    workbench_visibility text NOT NULL DEFAULT 'visible',
    tags text[] NOT NULL DEFAULT '{}',
    source_links jsonb NOT NULL DEFAULT '[]'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    remark text,
    legacy_collection text,
    legacy_id text,
    legacy_payload_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text,
    CONSTRAINT invoices_pkey PRIMARY KEY (invoice_month, id),
    CONSTRAINT invoices_invoice_type_chk CHECK (invoice_type IN ('output', 'input')),
    CONSTRAINT invoices_status_chk CHECK (
        status IN (
            'pending',
            'partially_reconciled',
            'reconciled',
            'pending_offline_confirmation',
            'pending_offset',
            'pending_invoice_issue',
            'pending_invoice_receive'
        )
    ),
    CONSTRAINT invoices_amount_chk CHECK (amount >= 0),
    CONSTRAINT invoices_tax_amount_chk CHECK (tax_amount IS NULL OR tax_amount >= 0),
    CONSTRAINT invoices_total_with_tax_chk CHECK (total_with_tax IS NULL OR total_with_tax >= 0),
    CONSTRAINT invoices_written_off_amount_chk CHECK (
        written_off_amount >= 0
        AND written_off_amount <= amount
    ),
    CONSTRAINT invoices_tax_rate_chk CHECK (tax_rate IS NULL OR (tax_rate >= 0 AND tax_rate <= 1)),
    CONSTRAINT invoices_quantity_chk CHECK (quantity IS NULL OR quantity >= 0),
    CONSTRAINT invoices_workbench_visibility_chk CHECK (workbench_visibility IN ('visible', 'hidden')),
    CONSTRAINT invoices_invoice_month_chk CHECK (
        invoice_date IS NULL
        OR invoice_month = date_trunc('month', invoice_date)::date
    ),
    CONSTRAINT invoices_source_links_chk CHECK (jsonb_typeof(source_links) = 'array'),
    CONSTRAINT invoices_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
) PARTITION BY RANGE (invoice_month);

CREATE UNIQUE INDEX invoices_source_unique_key_uk
    ON app.invoices (invoice_month, source_batch_id, source_unique_key)
    WHERE source_unique_key IS NOT NULL;

CREATE UNIQUE INDEX invoices_data_fingerprint_uk
    ON app.invoices (invoice_month, data_fingerprint)
    WHERE data_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX invoices_invoice_no_with_code_uk
    ON app.invoices (invoice_month, invoice_type, invoice_no, invoice_code)
    WHERE invoice_code IS NOT NULL;

CREATE UNIQUE INDEX invoices_invoice_no_without_code_uk
    ON app.invoices (invoice_month, invoice_type, invoice_no)
    WHERE invoice_code IS NULL;

CREATE UNIQUE INDEX invoices_digital_invoice_no_uk
    ON app.invoices (invoice_month, invoice_type, digital_invoice_no)
    WHERE digital_invoice_no IS NOT NULL;

CREATE UNIQUE INDEX invoices_legacy_id_uk
    ON app.invoices (invoice_month, legacy_collection, legacy_id)
    WHERE legacy_collection IS NOT NULL AND legacy_id IS NOT NULL;

CREATE INDEX invoices_type_no_idx
    ON app.invoices (invoice_month, invoice_type, invoice_no);

CREATE INDEX invoices_status_date_idx
    ON app.invoices (invoice_month, status, invoice_date DESC);

CREATE INDEX invoices_buyer_name_idx
    ON app.invoices (invoice_month, buyer_name);

CREATE INDEX invoices_seller_name_idx
    ON app.invoices (invoice_month, seller_name);

CREATE INDEX invoices_total_with_tax_idx
    ON app.invoices (invoice_month, total_with_tax);

CREATE INDEX invoices_source_batch_id_idx
    ON app.invoices (source_batch_id);

CREATE INDEX invoices_invoice_no_trgm_idx
    ON app.invoices USING gin (invoice_no gin_trgm_ops);

CREATE INDEX invoices_buyer_name_trgm_idx
    ON app.invoices USING gin (buyer_name gin_trgm_ops)
    WHERE buyer_name IS NOT NULL;

CREATE INDEX invoices_seller_name_trgm_idx
    ON app.invoices USING gin (seller_name gin_trgm_ops)
    WHERE seller_name IS NOT NULL;

CREATE TABLE app.invoice_certifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_month date NOT NULL,
    invoice_id uuid NOT NULL,
    certification_month date NOT NULL,
    certification_source text NOT NULL,
    source_unique_key text,
    status text NOT NULL,
    certified_amount numeric(20, 2) NOT NULL DEFAULT 0,
    certified_tax_amount numeric(20, 2) NOT NULL DEFAULT 0,
    source_batch_id uuid REFERENCES app.import_batches(id),
    certified_at timestamptz,
    cancelled_at timestamptz,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    legacy_collection text,
    legacy_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text,
    CONSTRAINT invoice_certifications_invoice_fkey
        FOREIGN KEY (invoice_month, invoice_id)
        REFERENCES app.invoices(invoice_month, id),
    CONSTRAINT invoice_certifications_status_chk CHECK (
        status IN ('planned', 'certified', 'uncertified', 'cancelled')
    ),
    CONSTRAINT invoice_certifications_source_chk CHECK (
        certification_source IN ('tax_certified_import', 'manual', 'migration', 'etc')
    ),
    CONSTRAINT invoice_certifications_amount_chk CHECK (certified_amount >= 0),
    CONSTRAINT invoice_certifications_tax_amount_chk CHECK (certified_tax_amount >= 0),
    CONSTRAINT invoice_certifications_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE UNIQUE INDEX invoice_certifications_source_unique_key_uk
    ON app.invoice_certifications (certification_source, source_unique_key)
    WHERE source_unique_key IS NOT NULL;

CREATE UNIQUE INDEX invoice_certifications_legacy_id_uk
    ON app.invoice_certifications (legacy_collection, legacy_id)
    WHERE legacy_collection IS NOT NULL AND legacy_id IS NOT NULL;

CREATE INDEX invoice_certifications_invoice_idx
    ON app.invoice_certifications (invoice_month, invoice_id);

CREATE INDEX invoice_certifications_month_status_idx
    ON app.invoice_certifications (certification_month, status);

CREATE TABLE app.invoice_inventory_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_month date NOT NULL,
    invoice_id uuid NOT NULL,
    event_type text NOT NULL,
    event_status text NOT NULL DEFAULT 'recorded',
    amount numeric(20, 2),
    tax_amount numeric(20, 2),
    source_batch_id uuid REFERENCES app.import_batches(id),
    event_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    CONSTRAINT invoice_inventory_events_invoice_fkey
        FOREIGN KEY (invoice_month, invoice_id)
        REFERENCES app.invoices(invoice_month, id),
    CONSTRAINT invoice_inventory_events_event_type_chk CHECK (
        event_type IN (
            'imported',
            'status_changed',
            'certified',
            'uncertified',
            'submitted_to_etc',
            'reconciled',
            'cancelled',
            'migrated'
        )
    ),
    CONSTRAINT invoice_inventory_events_event_status_chk CHECK (
        event_status IN ('recorded', 'superseded', 'reverted')
    ),
    CONSTRAINT invoice_inventory_events_amount_chk CHECK (amount IS NULL OR amount >= 0),
    CONSTRAINT invoice_inventory_events_tax_amount_chk CHECK (tax_amount IS NULL OR tax_amount >= 0),
    CONSTRAINT invoice_inventory_events_payload_chk CHECK (jsonb_typeof(event_payload) = 'object'),
    CONSTRAINT invoice_inventory_events_raw_payload_chk CHECK (jsonb_typeof(raw_payload) = 'object')
);

CREATE UNIQUE INDEX invoice_inventory_events_idempotency_key_uk
    ON app.invoice_inventory_events (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX invoice_inventory_events_invoice_idx
    ON app.invoice_inventory_events (invoice_month, invoice_id, created_at DESC);

CREATE INDEX invoice_inventory_events_type_idx
    ON app.invoice_inventory_events (event_type, created_at DESC);

CREATE OR REPLACE FUNCTION app.create_financial_fact_month_partition(
    parent_table regclass,
    partition_month date
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    parent_schema text;
    parent_name text;
    month_start date;
    next_month date;
    partition_name text;
BEGIN
    SELECT n.nspname, c.relname
    INTO parent_schema, parent_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.oid = parent_table;

    IF parent_schema <> 'app' OR parent_name NOT IN ('bank_transactions', 'invoices') THEN
        RAISE EXCEPTION 'unsupported financial fact partition parent: %', parent_table;
    END IF;

    month_start := date_trunc('month', partition_month)::date;
    next_month := (month_start + INTERVAL '1 month')::date;
    partition_name := parent_name || '_' || to_char(month_start, 'YYYY_MM');

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I.%I PARTITION OF %s FOR VALUES FROM (%L) TO (%L)',
        parent_schema,
        partition_name,
        parent_table,
        month_start,
        next_month
    );

    RETURN format('%I.%I', parent_schema, partition_name);
END;
$$;
