"""Read-only import scope projection shared by task reads and monitoring."""
from __future__ import annotations


def scoped_import_jobs(selection: str) -> str:
    """Selection is repository-owned SQL, never request input; bind values separately."""
    return f"""
    with selected_jobs as materialized ({selection}),
    file_domains as (
      select j.id, array_agg(distinct case
        when coalesce(f.raw_payload->'normalized_payload'->>'batch_type',
                      f.raw_payload->'normalized_payload'->>'override_batch_type',
                      f.raw_payload->>'batch_type', f.raw_payload->>'override_batch_type') = 'bank_transaction'
          then 'imports_bank_transactions'
        when coalesce(f.raw_payload->'normalized_payload'->>'batch_type',
                      f.raw_payload->'normalized_payload'->>'override_batch_type',
                      f.raw_payload->>'batch_type', f.raw_payload->>'override_batch_type') in ('input_invoice','output_invoice')
          then 'imports_invoices'
        else 'import_unknown' end) as domains
      from selected_jobs j join app.import_files f on f.session_id=j.import_session_id
        and (coalesce(j.payload->'selected_file_ids','[]'::jsonb) = '[]'::jsonb
             or j.payload->'selected_file_ids' ? coalesce(f.legacy_mongo_id,f.id::text))
      where j.import_type='file_import.confirm'
      group by j.id
    ), scoped_jobs as (
      select j.*, case j.import_type
        when 'file_import.confirm' then coalesce(f.domains, array['import_unknown']::text[])
        when 'etc_invoice_import.confirm' then array['imports_etc_invoices','etc_tickets']::text[]
        when 'tax_certified_import.confirm' then array['tax_offset']::text[]
        when 'oa_manual_import.create' then array['settings']::text[]
        else array['import_unknown']::text[] end as affected_domains
      from selected_jobs j left join file_domains f on f.id=j.id
    )
    """
