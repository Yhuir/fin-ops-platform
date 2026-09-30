-- Convert the name condition once; account identity is not present in OA facts.
-- The approved “刘树刚不付” rule now covers the merged 刘树刚 name.
with converted as (
    select s.id, s.settings_payload->'input_invoice_usage_payment_status_rules' as policy,
           jsonb_agg(
               case when rule->'conditions' ? 'applicantName' then
                   jsonb_set(rule, '{conditions}', ((rule->'conditions') - 'applicantName') ||
                       jsonb_build_object('applicantNames', jsonb_build_array(
                           case when rule->>'id' = 'offset_liu_shugang_no_pay'
                                     and rule->'conditions'->>'applicantName' = '刘树刚不付'
                                then '刘树刚'
                                else regexp_replace(rule->'conditions'->>'applicantName', '[[:space:]​﻿]+', '', 'g') end)))
               else rule end order by ordinal
           ) as rules
    from app.app_settings s,
         jsonb_array_elements(s.settings_payload->'input_invoice_usage_payment_status_rules'->'rules')
         with ordinality as entries(rule, ordinal)
    where s.settings_key = 'app_settings'
    group by s.id
    having bool_or(rule->'conditions' ? 'applicantName')
), next_settings as (
    select s.id, jsonb_set(s.settings_payload, '{input_invoice_usage_payment_status_rules}',
        converted.policy || jsonb_build_object(
            'version', (converted.policy->>'version')::integer + 1,
            'rules', converted.rules, 'idempotencyRecords', '{}'::jsonb
        )) as payload
    from app.app_settings s join converted on converted.id = s.id
)
update app.app_settings s
set settings_payload = n.payload,
    raw_payload = jsonb_set(s.raw_payload, '{normalized_payload}', n.payload, true),
    updated_at = now()
from next_settings n where s.id = n.id;
