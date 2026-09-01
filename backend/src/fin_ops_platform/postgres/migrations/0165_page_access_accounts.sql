-- Replace global access tiers with one canonical page list per ordinary account.
with source as (
    select
        id,
        settings_key,
        coalesce(settings_payload, '{}'::jsonb) as old_payload,
        coalesce(raw_payload, '{}'::jsonb) as old_raw_payload,
        case
            when jsonb_typeof(settings_payload->'full_access_usernames') = 'array'
                then settings_payload->'full_access_usernames'
            else '[]'::jsonb
        end as old_full_access,
        case
            when jsonb_typeof(settings_payload->'readonly_export_usernames') = 'array'
                then settings_payload->'readonly_export_usernames'
            else '[]'::jsonb
        end as old_read_only,
        case
            when jsonb_typeof(settings_payload->'access_control_version') = 'number'
             and (settings_payload->>'access_control_version') ~ '^[1-9][0-9]*$'
                then (settings_payload->>'access_control_version')::integer
            else 1
        end as current_version
    from app.app_settings
    where settings_key = 'app_settings'
), normalized as (
    select
        source.*,
        (
            old_payload
            - array[
                'allowed_usernames',
                'readonly_export_usernames',
                'admin_usernames',
                'full_access_usernames'
            ]
        ) || jsonb_build_object(
            'page_access_accounts', coalesce(
                (
                    select jsonb_agg(
                        jsonb_build_object(
                            'username', username,
                            'page_keys', jsonb_build_array(
                                'app-health-operations',
                                'bank-details',
                                'bank-flow-rule-batches',
                                'batch-accounting',
                                'cost-statistics',
                                'etc-tickets',
                                'imports.bank-transactions',
                                'imports.etc-invoices',
                                'imports.invoices',
                                'input-invoice-usage',
                                'oa-pending-payments',
                                'output-invoice-collections',
                                'pending-invoices',
                                'reconciliation-workbench',
                                'settings',
                                'tax-offset',
                                'turnover-ledger'
                            )
                        )
                        order by username
                    )
                    from jsonb_array_elements_text(old_full_access) as item(username)
                    where username <> 'YNSYLP005'
                ),
                '[]'::jsonb
            ),
            'access_control_version', current_version
        ) as next_payload,
        jsonb_array_length(old_read_only) as removed_read_only_count
    from source
)
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
where settings.id = normalized.id;

alter table app.app_settings
    drop constraint if exists app_settings_access_control_guard;

alter table app.app_settings
    drop constraint if exists app_settings_access_control_canonical_order_guard;

alter table app.app_settings
    add constraint app_settings_page_access_accounts_guard check (
        settings_key <> 'app_settings'
        or (
            jsonb_typeof(settings_payload) = 'object'
            and settings_payload ?& array['page_access_accounts', 'access_control_version']
            and not settings_payload ?| array[
                'allowed_usernames',
                'readonly_export_usernames',
                'admin_usernames',
                'full_access_usernames'
            ]
            and jsonb_typeof(settings_payload->'page_access_accounts') = 'array'
            and jsonb_typeof(settings_payload->'access_control_version') = 'number'
            and (settings_payload->>'access_control_version') ~ '^[1-9][0-9]*$'
            and jsonb_typeof(raw_payload) = 'object'
            and raw_payload->'normalized_payload' = settings_payload
        )
    ) not valid;

alter table app.app_settings
    validate constraint app_settings_page_access_accounts_guard;
