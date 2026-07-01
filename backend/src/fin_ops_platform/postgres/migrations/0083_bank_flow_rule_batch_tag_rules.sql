-- 0083_bank_flow_rule_batch_tag_rules
-- Split 流水规则批量处理 tag-rule settings from the no-OA settings family.

update app.app_settings
set
    settings_payload = jsonb_set(
        settings_payload,
        '{bank_flow_rule_batch_tag_rules}',
        coalesce(
            settings_payload->'bank_flow_rule_batch_tag_rules',
            settings_payload->'no_oa_bank_batch_tag_selection',
            '{"version":1,"selected_tag_codes":[],"requirements_by_tag_code":{}}'::jsonb
        ),
        true
    ),
    raw_payload = jsonb_set(
        coalesce(raw_payload, '{}'::jsonb),
        '{bank_flow_rule_batch_tag_rules_migration}',
        '{"migration":"0083_bank_flow_rule_batch_tag_rules","source":"no_oa_bank_batch_tag_selection"}'::jsonb,
        true
    ),
    updated_at = now()
where settings_key = 'app_settings'
  and not (settings_payload ? 'bank_flow_rule_batch_tag_rules');
