with target as (
    select
        settings_key,
        jsonb_set(
            settings_payload,
            '{batch_accounting_tag_selection}',
            jsonb_build_object(
                'version', 1,
                'selected_tag_codes', coalesce(
                    (
                        select jsonb_agg(definition->>'code' order by definition->>'code')
                        from jsonb_array_elements(
                            coalesce(settings_payload->'bank_transaction_tags'->'definitions', '[]'::jsonb)
                        ) definition
                        where coalesce(definition->>'status', 'active') = 'active'
                          and nullif(btrim(definition->>'code'), '') is not null
                    ),
                    '[]'::jsonb
                )
            ),
            true
        ) as next_payload
    from app.app_settings
    where settings_key = 'app_settings'
      and not (settings_payload ? 'batch_accounting_tag_selection')
      and jsonb_array_length(
          coalesce(settings_payload->'bank_transaction_tags'->'definitions', '[]'::jsonb)
      ) > 0
)
update app.app_settings settings
set
    settings_payload = target.next_payload,
    raw_payload = jsonb_set(
        coalesce(settings.raw_payload, '{}'::jsonb),
        '{normalized_payload}',
        target.next_payload,
        true
    ),
    updated_at = now()
from target
where settings.settings_key = target.settings_key;
