from __future__ import annotations


def oa_source_aliases_sql(application_alias: str, source_payload: str) -> str:
    """Return every authoritative historical source id owned by one canonical OA."""

    return f"""array(
        select distinct source_alias.alias_value
        from (
            select payload_alias.value as alias_value
            from jsonb_array_elements_text(
                case when jsonb_typeof({source_payload}->'source_aliases') = 'array'
                     then {source_payload}->'source_aliases'
                     else '[]'::jsonb end
            ) payload_alias(value)
            union all
            select split_part(
                nullif(item.normalized_payload->>'source_expense_item_id', ''),
                ':item:',
                1
            )
            from app.oa_application_items item
            where item.oa_application_id = {application_alias}.id
            union all
            select split_part(
                nullif(attachment.normalized_payload->>'source_expense_item_id', ''),
                ':item:',
                1
            )
            from app.oa_attachments attachment
            where attachment.oa_application_id = {application_alias}.id
            union all
            select split_part(
                nullif(attachment.normalized_payload->>'derived_from_oa_id', ''),
                ':item:',
                1
            )
            from app.oa_attachments attachment
            where attachment.oa_application_id = {application_alias}.id
            union all
            select split_part(
                nullif(attachment.normalized_payload->>'source_oa_id', ''),
                ':item:',
                1
            )
            from app.oa_attachments attachment
            where attachment.oa_application_id = {application_alias}.id
            union all
            select split_part(
                nullif(cache_source.source_expense_item_id, ''),
                ':item:',
                1
            )
            from app.oa_attachments attachment
            join app.oa_attachment_invoice_cache_sources cache_source
              on cache_source.source_attachment_key = attachment.source_attachment_key
            where attachment.oa_application_id = {application_alias}.id
            union all
            select split_part(
                nullif(cache_source.source_expense_item_id, ''),
                ':item:',
                1
            )
            from app.oa_attachments attachment
            join app.oa_attachment_invoice_cache_sources cache_source
              on cache_source.cache_source_attachment_key = attachment.source_attachment_key
            where attachment.oa_application_id = {application_alias}.id
            union all
            select alias_row.alias_row_id
            from app.oa_source_aliases alias_row
            where alias_row.canonical_row_id = {application_alias}.row_id
              and alias_row.status = 'active'
        ) source_alias
        where nullif(btrim(source_alias.alias_value), '') is not null
    )"""
