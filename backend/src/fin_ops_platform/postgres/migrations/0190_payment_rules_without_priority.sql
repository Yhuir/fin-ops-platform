-- One transaction converts the stored contract; readers never repair old rules.
do $$
declare
    settings record;
    before_policy jsonb;
    after_policy jsonb;
    rule jsonb;
    conditions jsonb;
    converted jsonb;
    rules jsonb;
    split_id text;
    payload jsonb;
begin
    for settings in select id, settings_payload from app.app_settings
        where settings_key = 'app_settings'
        and settings_payload->'input_invoice_usage_payment_status_rules'->'rules' is not null
        for update
    loop
        before_policy := settings.settings_payload->'input_invoice_usage_payment_status_rules';
        if not exists (select 1 from jsonb_array_elements(before_policy->'rules') r
            where r ? 'priority' or r->'conditions' ?| array['fullyMatched','invoiceOaAmountMatched']
               or not (r->'conditions' ? 'hasBank')) then
            continue;
        end if;
        rules := '[]'::jsonb;
        for rule in select value from jsonb_array_elements(before_policy->'rules') loop
            conditions := (rule->'conditions') - 'fullyMatched' - 'invoiceOaAmountMatched';
            if not (conditions ? 'hasBank') and
               (conditions ? 'paymentComparison' or rule->'conditions'->>'fullyMatched' = 'true') then
                conditions := conditions || '{"hasBank":true}'::jsonb;
            end if;
            converted := rule - 'priority' - 'description' - 'reason' - 'parentStatus';
            if conditions ? 'hasBank' then
                rules := rules || jsonb_build_array(jsonb_set(converted, '{conditions}', conditions));
            else
                split_id := (rule->>'id') || '_unpaid';
                while exists (select 1 from jsonb_array_elements((before_policy->'rules') || rules) r where r->>'id' = split_id) loop
                    split_id := split_id || '_';
                end loop;
                rules := rules || jsonb_build_array(
                    jsonb_set(converted, '{conditions}', conditions || '{"hasBank":true}'::jsonb),
                    jsonb_set(jsonb_set(converted, '{id}', to_jsonb(split_id)), '{conditions}', conditions || '{"hasBank":false}'::jsonb));
            end if;
        end loop;
        after_policy := before_policy || jsonb_build_object('version', (before_policy->>'version')::integer + 1,
            'rules', rules, 'idempotencyRecords', '{}'::jsonb);
        payload := jsonb_set(settings.settings_payload, '{input_invoice_usage_payment_status_rules}', after_policy);
        update app.app_settings set settings_payload = payload,
            raw_payload = jsonb_set(raw_payload, '{normalized_payload}', payload, true), updated_at = now()
            where id = settings.id;
        insert into audit.events(event_type, object_type, object_id, actor_id, action, page_key, outcome, payload, raw_payload)
            values ('operation.completed', 'app_settings', 'input_invoice_usage_payment_status_rules', 'migration:0190',
                'input_invoice_usage_payment_rules_migrated', 'input-invoice-usage', 'success',
                jsonb_build_object('before', before_policy, 'after', after_policy), '{}'::jsonb);
    end loop;
end $$;
