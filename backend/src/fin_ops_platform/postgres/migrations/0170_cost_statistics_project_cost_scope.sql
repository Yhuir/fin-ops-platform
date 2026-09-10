-- Explicit, one-time initialization. Empty selections remain empty on later runs.
insert into app.app_settings (settings_key, settings_payload)
values ('app_settings', '{"access_control_version":1,"page_access_accounts":[]}'::jsonb)
on conflict (settings_key) do nothing;

with target as (
    select settings_key, jsonb_set(settings_payload, '{cost_statistics_project_cost_scope}',
        jsonb_build_object('version', 1, 'selected_tag_codes', coalesce((
            select jsonb_agg(code order by code) from (
                select distinct definition->>'code' as code
                from jsonb_array_elements(coalesce(settings_payload->'bank_transaction_tags'->'definitions', '[]'::jsonb)) definition
                where nullif(btrim(definition->>'code'), '') is not null
                  and definition->>'code' not in ('internal_transfer', 'uncategorized')
                  and coalesce(definition->>'direction', 'any') <> 'income'
                  and (jsonb_typeof(definition->'rules') = 'object' or definition->>'code' in (
                      'fee', 'holiday_bonus', 'salary', 'bonus', 'treasury_tax_collection', 'social_security', 'tax_payment', 'external_turnover'
                  ))
            ) codes
        ), '[]'::jsonb)), true) as next_payload
    from app.app_settings
    where settings_key = 'app_settings' and not (settings_payload ? 'cost_statistics_project_cost_scope')
)
update app.app_settings settings set settings_payload = target.next_payload,
    raw_payload = jsonb_set(coalesce(settings.raw_payload, '{}'::jsonb), '{normalized_payload}', target.next_payload, true),
    updated_at = now()
from target where settings.settings_key = target.settings_key;
