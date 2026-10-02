-- 仅移除已退役的设置；项目记录、专用待找发票规则和关联事实保持不变。
update app.app_settings
set settings_payload = settings_payload - 'completed_project_ids' - 'oa_invoice_offset',
    raw_payload = jsonb_set(
        raw_payload, '{normalized_payload}',
        settings_payload - 'completed_project_ids' - 'oa_invoice_offset', true
    ),
    version = version + 1,
    updated_at = now()
where settings_key = 'app_settings'
  and settings_payload ?| array['completed_project_ids', 'oa_invoice_offset'];
