-- Persist the old evaluator's implicit conditions and base classifications once.
-- Later empty rule arrays stay empty; no runtime reconstruction is performed.
do $$
declare
    settings record;
    policy jsonb;
    rule jsonb;
    conditions jsonb;
    rules jsonb;
    code text;
    implied_bank boolean;
    comparison text;
    highest_priority integer;
    base record;
    base_id text;
    base_label text;
    payload jsonb;
begin
    for settings in select id,settings_payload from app.app_settings where settings_key='app_settings'
        and settings_payload->'input_invoice_usage_payment_status_rules'->'rules' is not null
    loop
        policy := settings.settings_payload->'input_invoice_usage_payment_status_rules';
        rules := '[]'::jsonb;
        highest_priority := 0;
        for rule in select value from jsonb_array_elements(policy->'rules') loop
            code := rule->>'statusCode';
            conditions := rule->'conditions';
            implied_bank := case when code in ('paid','cash_turnover','invoice_less_payment','invoice_greater_payment') then true
                                 when code in ('offset','waiting_payment') then false else null end;
            comparison := case code when 'paid' then 'equal' when 'invoice_less_payment' then 'less'
                                    when 'invoice_greater_payment' then 'greater' else null end;
            if (implied_bank is not null and conditions ? 'hasBank' and (conditions->>'hasBank')::boolean <> implied_bank)
               or (comparison is not null and conditions ? 'paymentComparison' and conditions->>'paymentComparison' <> comparison) then
                raise exception 'Payment rule % contradicts its former implicit category; resolve before conversion',rule->>'id';
            end if;
            if implied_bank is not null then
                conditions := conditions || jsonb_build_object('hasBank',implied_bank);
            end if;
            if comparison is not null then
                conditions := conditions || jsonb_build_object('paymentComparison',comparison);
            end if;
            rules := rules || jsonb_build_array(jsonb_set(rule - 'reason' - 'description' - 'parentStatus','{conditions}',conditions));
            highest_priority := greatest(highest_priority,(rule->>'priority')::integer);
        end loop;
        for base in select * from (values
            ('base_unpaid','waiting_payment','未关联流水',false,null::text),
            ('base_paid_equal','paid','发票＝付款',true,'equal'),
            ('base_paid_less','invoice_less_payment','发票＜付款',true,'less'),
            ('base_paid_greater','invoice_greater_payment','发票＞付款',true,'greater')
        ) as defaults(id,code,label,has_bank,comparison)
        loop
            base_id := base.id;
            while exists (select 1 from jsonb_array_elements(rules) r where r->>'id'=base_id) loop
                base_id := base_id || '_';
            end loop;
            select r->>'label' into base_label from jsonb_array_elements(rules) r where r->>'statusCode'=base.code limit 1;
            conditions := jsonb_build_object('hasBank',base.has_bank);
            if base.comparison is not null then
                conditions := conditions || jsonb_build_object('paymentComparison',base.comparison);
            end if;
            highest_priority := highest_priority + 1;
            rules := rules || jsonb_build_array(jsonb_build_object('id',base_id,'statusCode',base.code,
                'label',coalesce(base_label,base.label),'priority',highest_priority,'enabled',true,'conditions',conditions));
        end loop;
        payload := jsonb_set(settings.settings_payload,'{input_invoice_usage_payment_status_rules}',
            policy || jsonb_build_object('version',(policy->>'version')::integer+1,'rules',rules,'idempotencyRecords','{}'::jsonb));
        update app.app_settings set settings_payload=payload,
            raw_payload=jsonb_set(raw_payload,'{normalized_payload}',payload,true),updated_at=now()
        where id=settings.id;
    end loop;
end $$;
