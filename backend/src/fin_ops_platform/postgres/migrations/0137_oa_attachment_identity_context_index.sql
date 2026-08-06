create index if not exists oa_attachment_invoice_cache_sources_identity_context_idx
    on app.oa_attachment_invoice_cache_sources (
        source_expense_item_id,
        source_attachment_name,
        cache_source_attachment_key,
        source_kind
    )
    where source_kind in ('invoice', 'evidence', 'artifact')
      and nullif(source_expense_item_id, '') is not null
      and nullif(source_attachment_name, '') is not null;
