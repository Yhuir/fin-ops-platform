CREATE INDEX invoices_certified_digital_buyer_idx ON app.invoices(digital_invoice_no,buyer_tax_no)
    WHERE invoice_type='input' AND status<>'deleted' AND digital_invoice_no IS NOT NULL;
CREATE INDEX invoices_certified_code_number_buyer_idx ON app.invoices(invoice_code,invoice_no,buyer_tax_no)
    WHERE invoice_type='input' AND status<>'deleted' AND invoice_code IS NOT NULL;
ALTER TABLE app.tax_certified_import_records
    ADD COLUMN invoice_id uuid REFERENCES app.invoices(id) ON DELETE SET NULL,
    ADD COLUMN buyer_tax_no text,
    ADD COLUMN deductible_tax_amount numeric(20,6),
    ADD COLUMN selection_time timestamp without time zone,
    ADD COLUMN invoice_kind_label text,
    ADD COLUMN match_status text NOT NULL DEFAULT 'unresolved',
    ADD COLUMN version integer NOT NULL DEFAULT 1;
ALTER TABLE app.tax_certified_import_records ALTER COLUMN tax_amount DROP NOT NULL;
ALTER TABLE app.tax_certified_import_records ALTER COLUMN tax_amount DROP DEFAULT;
ALTER TABLE app.tax_certified_import_batches ADD COLUMN version integer NOT NULL DEFAULT 1;
-- Preserve historical evidence; association requires an unambiguous strong identity and buyer verification.
UPDATE app.tax_certified_import_records SET status='active' WHERE status IN ('已勾选','已认证');
UPDATE app.tax_certified_import_records SET
    buyer_tax_no=nullif(raw_payload->'normalized_payload'->>'taxpayer_tax_no',''),
    deductible_tax_amount=CASE WHEN (raw_payload->'normalized_payload'->>'deductible_tax_amount') ~ '^-?[0-9]+([.][0-9]+)?$'
        THEN (raw_payload->'normalized_payload'->>'deductible_tax_amount')::numeric END,
    selection_time=CASE WHEN pg_input_is_valid(raw_payload->'normalized_payload'->>'selection_time','timestamp')
        THEN (raw_payload->'normalized_payload'->>'selection_time')::timestamp END,
    invoice_kind_label=raw_payload->'normalized_payload'->>'invoice_kind_label';
WITH candidates AS (
    SELECT c.id, min(i.id::text)::uuid AS invoice_id
    FROM app.tax_certified_import_records c JOIN app.invoices i
      ON i.status <> 'deleted' AND i.invoice_type='input'
      AND nullif(c.buyer_tax_no,'') IS NOT NULL AND c.buyer_tax_no=i.buyer_tax_no
      AND ((nullif(c.digital_invoice_no,'') IS NOT NULL AND c.digital_invoice_no=i.digital_invoice_no)
        OR (nullif(c.digital_invoice_no,'') IS NULL AND nullif(c.invoice_code,'') IS NOT NULL
            AND nullif(c.invoice_no,'') IS NOT NULL AND c.invoice_code=i.invoice_code AND c.invoice_no=i.invoice_no))
      AND (nullif(c.invoice_code,'') IS NULL OR nullif(i.invoice_code,'') IS NULL OR c.invoice_code=i.invoice_code)
      AND (nullif(c.invoice_no,'') IS NULL OR nullif(i.invoice_no,'') IS NULL OR c.invoice_no=i.invoice_no)
      AND (c.amount IS NULL OR i.amount IS NULL OR c.amount=i.amount)
      AND (c.tax_amount IS NULL OR i.tax_amount IS NULL OR c.tax_amount=i.tax_amount)
      AND replace(replace(btrim(coalesce(i.raw_payload->'normalized_payload',i.raw_payload)->>'invoice_kind'),'（','('),'）',')')
          IN ('进项专票','增值税专用发票','增值税电子专用发票','电子专用发票','电子发票(增值税专用发票)','数电票(专用发票)','数电发票(增值税专用发票)')
    WHERE c.status='active'
    GROUP BY c.id HAVING count(*)=1
), unambiguous AS (
    SELECT id,invoice_id,count(*) OVER (PARTITION BY invoice_id) AS record_count FROM candidates
)
UPDATE app.tax_certified_import_records c SET invoice_id=u.invoice_id,match_status='matched_invoice'
FROM unambiguous u WHERE c.id=u.id AND u.record_count=1;
UPDATE app.tax_certified_import_batches b SET raw_payload=jsonb_set(
    b.raw_payload,'{normalized_payload}',
    coalesce(b.raw_payload->'normalized_payload',b.raw_payload) || jsonb_build_object('record_keys',
      coalesce((SELECT jsonb_agg(r.certified_unique_key ORDER BY r.certified_unique_key)
                FROM app.tax_certified_import_records r WHERE r.batch_id=b.id AND r.status='active'),'[]'::jsonb)));
CREATE UNIQUE INDEX tax_certified_active_invoice_uidx
    ON app.tax_certified_import_records(invoice_id) WHERE status='active' AND invoice_id IS NOT NULL;
CREATE INDEX tax_certified_active_selection_idx
    ON app.tax_certified_import_records(selection_time DESC NULLS LAST, id) WHERE status='active';
CREATE INDEX tax_certified_batch_idx ON app.tax_certified_import_records(batch_id);
