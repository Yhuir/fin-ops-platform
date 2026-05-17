-- P0 platform runtime shadow seed probes.
-- Run with: psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f <this-file>

select 'BACKGROUND_JOB_ID' as variable,
       'ad1d1132-89ff-5198-a096-f45ad3573ed1'::uuid as value,
       exists (
         select 1
         from job.worker_tasks
         where id = 'ad1d1132-89ff-5198-a096-f45ad3573ed1'::uuid
           and visibility = 'system'
           and status in ('queued', 'running', 'succeeded', 'failed', 'retrying', 'dead_lettered', 'cancelled')
       ) as ok;

select 'BANK_TRANSACTION_ID' as variable,
       '210895bd-e515-5488-bae8-1815b291a72f'::uuid as value,
       exists (
         select 1
         from app.bank_transactions
         where txn_month = date '2026-05-01'
           and id = '210895bd-e515-5488-bae8-1815b291a72f'::uuid
           and status = 'pending'
       ) as ok;

select 'LEDGER_ID' as variable,
       '29c2554f-c6a3-5b69-9fb1-bf0cd431ec91'::uuid as value,
       exists (
         select 1
         from app.ledgers
         where id = '29c2554f-c6a3-5b69-9fb1-bf0cd431ec91'::uuid
           and status = 'open'
       ) as ok;

select 'PROJECT_ID' as variable,
       'fce10a80-61e0-520c-88dc-57f34e5afaf0'::uuid as value,
       exists (
         select 1
         from app.project_profiles
         where id = 'fce10a80-61e0-520c-88dc-57f34e5afaf0'::uuid
           and project_status = 'active'
       ) as ok;

select 'PROJECT_DELETE_ID' as variable,
       '35d0adce-fb9b-5b11-ae5b-78e4ecf90262'::uuid as value,
       exists (
         select 1
         from app.project_profiles
         where id = '35d0adce-fb9b-5b11-ae5b-78e4ecf90262'::uuid
           and project_status = 'active'
       ) as ok;

select 'SETTINGS_AND_DATA_RESET_SUPPORT' as variable,
       'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid as value,
       exists (select 1 from app.settings_profiles where id = '26232b50-9e6b-599b-939e-e96de970a6ea'::uuid)
       and exists (select 1 from app.data_reset_requests where id = 'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid and status = 'succeeded')
       and exists (select 1 from job.outbox_events where id = '45f9d274-d9dc-571a-8bb1-6793e144f072'::uuid and status = 'published')
       and exists (select 1 from audit.events where id = 'a79c7d79-e79d-5101-a322-a82178205dd7'::uuid)
       and exists (
         select 1
         from app.write_idempotency_records
         where operation = 'data_reset.request'
           and idempotency_key = 'platform-shadow:p0-platform-local:data-reset-support'
       ) as ok;
