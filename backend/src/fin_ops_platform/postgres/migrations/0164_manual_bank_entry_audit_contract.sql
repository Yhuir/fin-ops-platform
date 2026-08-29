set local lock_timeout = '10s';
set local statement_timeout = '1min';

update app.import_files
set audit_contract_revision = 'manual-bank-entry-audit.v1'
where template_kind = 'manual_bank_transaction_entry'
  and audit_contract_revision = 'import-page-audit.v1'
  and file_object_id is null
  and coalesce(btrim(stored_file_path), '') = ''
  and coalesce(raw_payload #>> '{normalized_payload,template_code}', '') =
      'manual_bank_transaction_entry';
