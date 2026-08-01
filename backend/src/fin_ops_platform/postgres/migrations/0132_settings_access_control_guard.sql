-- Fail closed before the application begins treating ACL as a dedicated command.
with source as (
    select
        id,
        settings_key,
        coalesce(settings_payload, '{}'::jsonb) as old_payload,
        coalesce(raw_payload, '{}'::jsonb) as old_raw_payload,
        case
            when jsonb_typeof(settings_payload->'allowed_usernames') = 'array'
                then settings_payload->'allowed_usernames'
            else '[]'::jsonb
        end as old_allowed,
        case
            when jsonb_typeof(settings_payload->'readonly_export_usernames') = 'array'
                then settings_payload->'readonly_export_usernames'
            else '[]'::jsonb
        end as old_readonly,
        case
            when jsonb_typeof(settings_payload->'full_access_usernames') = 'array'
                then settings_payload->'full_access_usernames'
            else '[]'::jsonb
        end as old_full,
        case
            when jsonb_typeof(settings_payload->'admin_usernames') = 'array'
                then settings_payload->'admin_usernames'
            else '[]'::jsonb
        end as old_admin,
        case
            when jsonb_typeof(settings_payload->'access_control_version') = 'number'
             and (settings_payload->>'access_control_version') ~ '^[1-9][0-9]*$'
                then (settings_payload->>'access_control_version')::integer
            else 1
        end as next_version
    from app.app_settings
    where settings_key = 'app_settings'
), normalized as (
    select
        source.*,
        old_payload || jsonb_build_object(
            'allowed_usernames',
                case
                    when old_allowed @> '["YNSYLP005"]'::jsonb then old_allowed
                    else old_allowed || '["YNSYLP005"]'::jsonb
                end,
            'readonly_export_usernames',
                jsonb_path_query_array(old_readonly, '$[*] ? (@ != "YNSYLP005")'),
            'admin_usernames', '["YNSYLP005"]'::jsonb,
            'full_access_usernames',
                jsonb_path_query_array(old_full, '$[*] ? (@ != "YNSYLP005")'),
            'access_control_version', next_version
        ) as next_payload,
        (
            select count(*)::integer
            from jsonb_array_elements_text(old_admin) as item(username)
            where username <> 'YNSYLP005'
        ) as removed_admin_count,
        coalesce(
            (
                select jsonb_agg(
                    jsonb_build_object(
                        'algorithm', 'sha256',
                        'value', encode(digest(username, 'sha256'), 'hex')
                    )
                    order by username
                )
                from jsonb_array_elements_text(old_admin) as item(username)
                where username <> 'YNSYLP005'
            ),
            '[]'::jsonb
        ) as removed_admin_hashes
    from source
), updated as (
    update app.app_settings as settings
    set
        settings_payload = normalized.next_payload,
        raw_payload = jsonb_set(
            normalized.old_raw_payload,
            '{normalized_payload}',
            normalized.next_payload,
            true
        ),
        updated_at = now()
    from normalized
    where settings.id = normalized.id
      and (
          settings.settings_payload is distinct from normalized.next_payload
          or settings.raw_payload->'normalized_payload' is distinct from normalized.next_payload
      )
    returning
        settings.settings_key,
        normalized.old_payload,
        normalized.next_payload,
        normalized.removed_admin_count,
        normalized.removed_admin_hashes
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
    'settings.access_control.migrated',
    'app_settings',
    settings_key,
    'migration:0132',
    'access_control',
    jsonb_build_object(
        'protected_administrator', 'YNSYLP005',
        'removed_admin_count', removed_admin_count,
        'removed_admin_username_hashes', removed_admin_hashes,
        'before_version', coalesce(old_payload->'access_control_version', 'null'::jsonb),
        'after_version', next_payload->'access_control_version',
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
            'migration', '0132_settings_access_control_guard',
            'removed_admin_count', removed_admin_count
        )
    )
from updated;

alter table app.app_settings
    drop constraint if exists app_settings_access_control_guard;

alter table app.app_settings
    add constraint app_settings_access_control_guard check (
        settings_key <> 'app_settings'
        or (
            jsonb_typeof(settings_payload->'allowed_usernames') = 'array'
            and settings_payload->'allowed_usernames' @> '["YNSYLP005"]'::jsonb
            and jsonb_typeof(settings_payload->'readonly_export_usernames') = 'array'
            and not (settings_payload->'readonly_export_usernames' @> '["YNSYLP005"]'::jsonb)
            and settings_payload->'admin_usernames' = '["YNSYLP005"]'::jsonb
            and jsonb_typeof(settings_payload->'full_access_usernames') = 'array'
            and not (settings_payload->'full_access_usernames' @> '["YNSYLP005"]'::jsonb)
            and jsonb_typeof(settings_payload->'access_control_version') = 'number'
            and (settings_payload->>'access_control_version') ~ '^[1-9][0-9]*$'
            and raw_payload->'normalized_payload' = settings_payload
        )
    ) not valid;

alter table app.app_settings
    validate constraint app_settings_access_control_guard;
