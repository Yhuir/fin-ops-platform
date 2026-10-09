-- Register first-match semantics and invalidate drafts from the unordered runtime.
do $$
declare
    settings record;
    before_policy jsonb;
    after_policy jsonb;
    ordered_rules jsonb;
    payload jsonb;
begin
    for settings in select id, settings_payload from app.app_settings
        where settings_key = 'app_settings'
          and settings_payload->'input_invoice_usage_payment_status_rules'->'rules' is not null
        for update
    loop
        if exists (select 1 from audit.events event
            where event.actor_id = 'migration:0191'
              and event.action = 'input_invoice_usage_payment_rule_order_migrated'
              and event.payload->>'settings_id' = settings.id::text) then
            continue;
        end if;
        before_policy := settings.settings_payload->'input_invoice_usage_payment_status_rules';
        select coalesce(jsonb_agg(value order by (value->'conditions'->>'hasBank')::boolean desc, ordinal), '[]'::jsonb)
            into ordered_rules
            from jsonb_array_elements(before_policy->'rules') with ordinality as rules(value, ordinal);
        after_policy := before_policy || jsonb_build_object(
            'version', (before_policy->>'version')::integer + 1,
            'rules', ordered_rules, 'idempotencyRecords', '{}'::jsonb);
        payload := jsonb_set(settings.settings_payload, '{input_invoice_usage_payment_status_rules}', after_policy);
        update app.app_settings set settings_payload = payload,
            raw_payload = jsonb_set(raw_payload, '{normalized_payload}', payload, true), updated_at = now()
            where id = settings.id;
        insert into audit.events(event_type, object_type, object_id, actor_id, action, page_key, outcome, payload, raw_payload)
            values ('operation.completed', 'app_settings', 'input_invoice_usage_payment_status_rules', 'migration:0191',
                'input_invoice_usage_payment_rule_order_migrated', 'input-invoice-usage', 'success',
                jsonb_build_object('settings_id', settings.id::text, 'before', before_policy, 'after', after_policy), '{}'::jsonb);
    end loop;
end $$;
