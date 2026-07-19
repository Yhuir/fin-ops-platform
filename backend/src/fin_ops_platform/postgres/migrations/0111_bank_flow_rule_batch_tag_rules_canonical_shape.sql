-- 0111_bank_flow_rule_batch_tag_rules_canonical_shape
-- Remove the one-time no-OA selected-tag seed from the bank-flow settings family.

with current_policy as (
    select
        id,
        case
            when jsonb_typeof(settings_payload->'bank_flow_rule_batch_tag_rules') = 'object'
                then settings_payload->'bank_flow_rule_batch_tag_rules'
            else '{}'::jsonb
        end as policy
    from app.app_settings
    where settings_key = 'app_settings'
), canonical_policy as (
    select
        id,
        jsonb_build_object(
            'version', coalesce(policy->'version', '1'::jsonb),
            'requirements_by_tag_code',
                coalesce(
                    (
                        select jsonb_object_agg(
                            tag_code,
                            '{"requires_oa":false,"requires_invoice":false}'::jsonb
                        )
                        from jsonb_array_elements_text(
                            case
                                when jsonb_typeof(policy->'selected_tag_codes') = 'array'
                                    then policy->'selected_tag_codes'
                                else '[]'::jsonb
                            end
                        ) as selected(tag_code)
                        where btrim(tag_code) <> ''
                    ),
                    '{}'::jsonb
                )
                || case
                    when jsonb_typeof(policy->'requirements_by_tag_code') = 'object'
                        then policy->'requirements_by_tag_code'
                    else '{}'::jsonb
                end
        ) as policy
    from current_policy
)
update app.app_settings as settings
set
    settings_payload = jsonb_set(
        settings.settings_payload,
        '{bank_flow_rule_batch_tag_rules}',
        canonical_policy.policy,
        true
    ),
    raw_payload = jsonb_set(
        coalesce(settings.raw_payload, '{}'::jsonb),
        '{bank_flow_rule_batch_tag_rules_canonical_shape_migration}',
        '{"migration":"0111_bank_flow_rule_batch_tag_rules_canonical_shape","legacy_selected_tag_codes_removed":true}'::jsonb,
        true
    ),
    updated_at = now()
from canonical_policy
where settings.id = canonical_policy.id;
