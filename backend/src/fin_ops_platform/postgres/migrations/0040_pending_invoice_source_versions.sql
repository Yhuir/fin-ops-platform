alter table read_model.pending_invoice_scopes
    add column if not exists source_versions jsonb not null default '{}'::jsonb;

update read_model.pending_invoice_scopes
set
    source_versions = coalesce(
        nullif(source_versions, '{}'::jsonb),
        case
            when raw_payload ? 'source_versions' then raw_payload->'source_versions'
            else '{}'::jsonb
        end
    )
where source_versions = '{}'::jsonb;
