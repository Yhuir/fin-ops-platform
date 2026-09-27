-- Convert the existing fixed-template configuration once. No read-time repair.
-- The settings row and migration record commit together in the migration runner.
do $$
begin
    if exists (
        select 1
        from app.app_settings settings,
             jsonb_array_elements(settings.settings_payload->'input_invoice_usage_payment_status_rules'->'rules') rule
        where settings.settings_key = 'app_settings'
          and rule->>'statusCode' in ('offset_zhou_jieying', 'offset_liu_shugang_no_pay', 'offset_wei_dailian', 'offset')
        group by settings.id
        having count(distinct rule->>'label') > 1
    ) then
        raise exception 'Payment offset rules have conflicting labels; resolve explicitly before migration';
    end if;
end $$;

with converted as (
    select settings.id, settings.settings_payload->'input_invoice_usage_payment_status_rules' as policy,
           coalesce((
               select jsonb_agg(
                   (rule - 'reason' - 'description') || jsonb_build_object(
                       'statusCode', case when rule->>'statusCode' in (
                           'offset_zhou_jieying', 'offset_liu_shugang_no_pay', 'offset_wei_dailian'
                       ) then 'offset' else rule->>'statusCode' end,
                       'label', case when rule->>'statusCode' = 'waiting_payment' and rule->>'label' = '待付款'
                           then '未关联流水' else rule->>'label' end
                   ) order by ordinal
               )
               from jsonb_array_elements(settings.settings_payload->'input_invoice_usage_payment_status_rules'->'rules')
                    with ordinality as entries(rule, ordinal)
               where rule->>'id' <> 'pending_default'
           ), '[]'::jsonb) as rules
    from app.app_settings settings
    where settings.settings_key = 'app_settings'
      and settings.settings_payload->'input_invoice_usage_payment_status_rules'->'rules' is not null
), next_settings as (
    select settings.id, jsonb_set(settings.settings_payload, '{input_invoice_usage_payment_status_rules}',
        (converted.policy - 'pendingDirections' - 'pending_directions') || jsonb_build_object(
            'version', (converted.policy->>'version')::integer + 1,
            'rules', converted.rules,
            'idempotencyRecords', '{}'::jsonb
        )) as payload
    from app.app_settings settings join converted on converted.id = settings.id
)
update app.app_settings settings
set settings_payload = next_settings.payload,
    raw_payload = jsonb_set(settings.raw_payload, '{normalized_payload}', next_settings.payload, true),
    updated_at = now()
from next_settings
where settings.id = next_settings.id;
