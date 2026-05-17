alter table app.project_assignments
  drop constraint if exists project_assignments_object_type_chk;

alter table app.project_assignments
  add constraint project_assignments_object_type_chk check (
    object_type in (
      'bank_transaction',
      'invoice',
      'reconciliation_case',
      'follow_up_ledger',
      'oa_application',
      'oa_application_item',
      'workbench_row'
    )
  );
