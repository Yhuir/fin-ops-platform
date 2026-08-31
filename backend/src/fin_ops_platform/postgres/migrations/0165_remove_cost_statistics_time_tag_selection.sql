-- 0165_remove_cost_statistics_time_tag_selection
-- Retire the removed Cost Statistics time/tag setting from both canonical
-- settings and its formal raw mirror. No other setting key is changed.

with target as (
    select
        settings_key,
        settings_payload - 'cost_statistics_time_tag_selection' as next_payload
    from app.app_settings
    where settings_key = 'app_settings'
      and (
          settings_payload ? 'cost_statistics_time_tag_selection'
          or coalesce(raw_payload->'normalized_payload', '{}'::jsonb)
              ? 'cost_statistics_time_tag_selection'
      )
)
update app.app_settings as settings
set
    settings_payload = target.next_payload,
    raw_payload = jsonb_set(
        coalesce(settings.raw_payload, '{}'::jsonb),
        '{normalized_payload}',
        target.next_payload,
        true
    ),
    updated_at = now()
from target
where settings.settings_key = target.settings_key;
