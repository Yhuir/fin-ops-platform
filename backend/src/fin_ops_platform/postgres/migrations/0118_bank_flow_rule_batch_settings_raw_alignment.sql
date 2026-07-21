-- 0118_bank_flow_rule_batch_settings_raw_alignment
-- Repair the formal/raw drift left by 0111 without changing the canonical rule value.

update app.app_settings
set
    raw_payload = jsonb_set(
        jsonb_set(
            coalesce(raw_payload, '{}'::jsonb),
            '{normalized_payload}',
            jsonb_set(
                coalesce(raw_payload->'normalized_payload', '{}'::jsonb),
                '{bank_flow_rule_batch_tag_rules}',
                settings_payload->'bank_flow_rule_batch_tag_rules',
                true
            ),
            true
        ),
        '{bank_flow_rule_batch_tag_rules_raw_alignment_migration}',
        '{"migration":"0118_bank_flow_rule_batch_settings_raw_alignment","canonical_value_changed":false}'::jsonb,
        true
    ),
    updated_at = now()
where settings_key = 'app_settings'
  and settings_payload ? 'bank_flow_rule_batch_tag_rules'
  and raw_payload->'normalized_payload'->'bank_flow_rule_batch_tag_rules'
      is distinct from settings_payload->'bank_flow_rule_batch_tag_rules';
