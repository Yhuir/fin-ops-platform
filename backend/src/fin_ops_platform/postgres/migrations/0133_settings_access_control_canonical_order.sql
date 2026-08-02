-- Repair the 0132 append order and make the persisted ACL match the application canonical shape.
with source as (
    select
        id,
        settings_key,
        settings_payload as old_payload,
        raw_payload as old_raw_payload,
        settings_payload || jsonb_build_object(
            'allowed_usernames',
                '["YNSYLP005"]'::jsonb
                || (settings_payload->'full_access_usernames')
                || (settings_payload->'readonly_export_usernames'),
            'admin_usernames', '["YNSYLP005"]'::jsonb
        ) as next_payload
    from app.app_settings
    where settings_key = 'app_settings'
), updated as (
    update app.app_settings as settings
    set
        settings_payload = source.next_payload,
        raw_payload = jsonb_set(
            source.old_raw_payload,
            '{normalized_payload}',
            source.next_payload,
            true
        ),
        updated_at = now()
    from source
    where settings.id = source.id
      and (
          settings.settings_payload is distinct from source.next_payload
          or settings.raw_payload->'normalized_payload' is distinct from source.next_payload
      )
    returning
        settings.settings_key,
        source.old_payload,
        source.next_payload
)
insert into audit.events(
    event_type,
    object_type,
    object_id,
    actor_id,
    scope,
    payload,
    raw_payload
)
select
    'settings.access_control.canonical_order_repaired',
    'app_settings',
    settings_key,
    'migration:0133',
    'access_control',
    jsonb_build_object(
        'protected_administrator', 'YNSYLP005',
        'before_acl_sha256', encode(
            digest(
                jsonb_build_object(
                    'allowed_usernames', old_payload->'allowed_usernames',
                    'readonly_export_usernames', old_payload->'readonly_export_usernames',
                    'admin_usernames', old_payload->'admin_usernames',
                    'full_access_usernames', old_payload->'full_access_usernames',
                    'access_control_version', old_payload->'access_control_version'
                )::text,
                'sha256'
            ),
            'hex'
        ),
        'after_acl_sha256', encode(
            digest(
                jsonb_build_object(
                    'allowed_usernames', next_payload->'allowed_usernames',
                    'readonly_export_usernames', next_payload->'readonly_export_usernames',
                    'admin_usernames', next_payload->'admin_usernames',
                    'full_access_usernames', next_payload->'full_access_usernames',
                    'access_control_version', next_payload->'access_control_version'
                )::text,
                'sha256'
            ),
            'hex'
        )
    ),
    jsonb_build_object(
        'normalized_payload', jsonb_build_object(
            'migration', '0133_settings_access_control_canonical_order'
        )
    )
from updated;

alter table app.app_settings
    drop constraint if exists app_settings_access_control_guard;

alter table app.app_settings
    drop constraint if exists app_settings_access_control_canonical_order_guard;

alter table app.app_settings
    add constraint app_settings_access_control_canonical_order_guard check (
        settings_key <> 'app_settings'
        or (
            jsonb_typeof(settings_payload) = 'object'
            and settings_payload ?& array[
                'allowed_usernames',
                'readonly_export_usernames',
                'admin_usernames',
                'full_access_usernames',
                'access_control_version'
            ]
            and jsonb_typeof(settings_payload->'allowed_usernames') = 'array'
            and jsonb_typeof(settings_payload->'readonly_export_usernames') = 'array'
            and jsonb_typeof(settings_payload->'full_access_usernames') = 'array'
            and settings_payload->'admin_usernames' = '["YNSYLP005"]'::jsonb
            and not (settings_payload->'readonly_export_usernames' @> '["YNSYLP005"]'::jsonb)
            and not (settings_payload->'full_access_usernames' @> '["YNSYLP005"]'::jsonb)
            and settings_payload->'allowed_usernames' = (
                '["YNSYLP005"]'::jsonb
                || (settings_payload->'full_access_usernames')
                || (settings_payload->'readonly_export_usernames')
            )
            and jsonb_typeof(settings_payload->'access_control_version') = 'number'
            and (settings_payload->>'access_control_version') ~ '^[1-9][0-9]*$'
            and jsonb_typeof(raw_payload) = 'object'
            and raw_payload ? 'normalized_payload'
            and raw_payload->'normalized_payload' = settings_payload
        )
    ) not valid;

alter table app.app_settings
    validate constraint app_settings_access_control_canonical_order_guard;
